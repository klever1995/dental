from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
import requests
import os

from app.db.base import get_db
from app.models.usuarios import Usuario
from app.api.v1.endpoints.usuarios import get_current_active_user
from app.services.calcom import (
    obtener_slots_disponibles,
    agendar_cita,
    eliminar_cita,
    reagendar_cita,
)

router = APIRouter(prefix="/citas", tags=["citas"])

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
TIMEZONE = "America/Guayaquil"

# Endpoint para listar TODAS las citas de la empresa (CORREGIDO)
# Endpoint para listar TODAS las citas (sin usar services/calcom.py)
@router.get("/")
def listar_todas_citas(
    current_user: Usuario = Depends(get_current_active_user)
):
    event_type_id = 1288606
    
    url = f"https://api.cal.com/v2/bookings?eventTypeId={event_type_id}"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            bookings = data.get("data", {}).get("bookings", [])
            
            citas_formateadas = []
            for booking in bookings:
                cita = {
                    "booking_id": booking.get("id"),
                    "uid": booking.get("uid"),
                    "title": booking.get("title"),
                    "start_time": booking.get("startTime"),
                    "end_time": booking.get("endTime"),
                    "status": booking.get("status"),
                    "created_at": booking.get("createdAt"),
                    "updated_at": booking.get("updatedAt"),
                    "cliente_nombre": None,
                    "cliente_email": None
                }
                
                attendees = booking.get("attendees", [])
                if attendees:
                    cita["cliente_nombre"] = attendees[0].get("name")
                    cita["cliente_email"] = attendees[0].get("email")
                else:
                    responses = booking.get("responses", {})
                    cita["cliente_nombre"] = responses.get("name")
                    cita["cliente_email"] = responses.get("email")
                
                citas_formateadas.append(cita)
            
            return citas_formateadas
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error de API: {response.status_code}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la consulta: {str(e)}"
        )

# Endpoint para consultar slots disponibles
@router.get("/slots")
def consultar_slots(
    fecha_inicio: str = None,
    dias_a_mostrar: int = 5,
    current_user: Usuario = Depends(get_current_active_user)
):
    event_type_id = 1288606
    ecuador = pytz.timezone(TIMEZONE)
    ahora = datetime.now(ecuador)
    
    # Determinar fechas de inicio y fin
    if fecha_inicio:
        try:
            inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            inicio = ecuador.localize(inicio)
            if inicio.date() < ahora.date():
                inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                inicio = inicio.replace(hour=0, minute=0, second=0, microsecond=0)
            fin = inicio + timedelta(days=1)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de fecha inválido. Usa YYYY-MM-DD"
            )
    else:
        inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        fin = inicio + timedelta(days=dias_a_mostrar)
    
    start_utc = inicio.astimezone(pytz.utc).isoformat()
    end_utc = fin.astimezone(pytz.utc).isoformat()
    
    url = "https://api.cal.com/v2/slots"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "cal-api-version": "2024-09-04"
    }
    params = {
        "eventTypeId": event_type_id,
        "start": start_utc,
        "end": end_utc,
        "timeZone": TIMEZONE,
        "duration": 60
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            slots_por_fecha = {}
            
            if "data" in data:
                for fecha_utc_str, slots_dia in data["data"].items():
                    for slot in slots_dia:
                        hora_obj = datetime.fromisoformat(slot["start"]).astimezone(ecuador)
                        fecha_local = hora_obj.strftime("%Y-%m-%d")
                        hora_local = hora_obj.strftime("%H:%M")
                        
                        if fecha_local not in slots_por_fecha:
                            slots_por_fecha[fecha_local] = []
                        if hora_local not in slots_por_fecha[fecha_local]:
                            slots_por_fecha[fecha_local].append(hora_local)
                
                for fecha in slots_por_fecha:
                    slots_por_fecha[fecha].sort()
                
                return slots_por_fecha
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La respuesta de Cal.com no contiene datos"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error de API: {response.status_code}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la consulta: {str(e)}"
        )

# Endpoint para agendar cita (desde el panel)
@router.post("/agendar")
def agendar_cita_desde_panel(
    cliente_nombre: str = Form(...),
    cliente_email: str = Form(...),
    fecha: str = Form(...),
    hora: str = Form(...),
    current_user: Usuario = Depends(get_current_active_user)
):
    event_type_id = 1288606
    ecuador = pytz.timezone(TIMEZONE)
    
    # Validar y construir fecha/hora
    try:
        fecha_hora = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        if fecha_hora.tzinfo is None:
            fecha_hora = ecuador.localize(fecha_hora)
        fecha_hora_utc = fecha_hora.astimezone(pytz.utc)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha/hora inválido: {str(e)}"
        )
    
    # Llamar a la API de Cal.com
    url = "https://api.cal.com/v2/bookings"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }
    data = {
        "start": fecha_hora_utc.isoformat(),
        "eventTypeId": event_type_id,
        "attendee": {
            "name": cliente_nombre,
            "email": cliente_email,
            "timeZone": TIMEZONE
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code in [200, 201]:
            return {
                "mensaje": "Cita agendada exitosamente",
                "cita": response.json()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error al agendar: {response.text}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de conexión: {str(e)}"
        )

# Endpoint para cancelar cita (corregido con API v2)
@router.delete("/{booking_uid}")
def cancelar_cita(
    booking_uid: str,  # Cambiado a string para recibir el UID
    current_user: Usuario = Depends(get_current_active_user)
):
    # Llamar a la API de Cal.com v2 para cancelar
    url = f"https://api.cal.com/v2/bookings/{booking_uid}/cancel"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }
    data = {
        "cancellationReason": "Cancelado por el usuario"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code in [200, 204]:
            return {"mensaje": "Cita cancelada exitosamente"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error al cancelar: {response.text}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de conexión: {str(e)}"
        )

# Endpoint para reagendar cita
@router.put("/{booking_uid}/reagendar")
def reagendar_cita_desde_panel(
    booking_uid: str,  # Cambiado a string para recibir el UID
    nueva_fecha: str = Form(...),
    nueva_hora: str = Form(...),
    cliente_nombre: str = Form(...),
    cliente_email: str = Form(...),
    current_user: Usuario = Depends(get_current_active_user)
):
    """
    Reagenda una cita existente.
    Se requiere el booking_uid (ej: "njn2N2J1d9Jz1kpiJ8Wb1z") y los datos del cliente
    """
    ecuador = pytz.timezone(TIMEZONE)
    
    # Construir fecha/hora en UTC
    try:
        fecha_hora = datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
        if fecha_hora.tzinfo is None:
            fecha_hora = ecuador.localize(fecha_hora)
        fecha_hora_utc = fecha_hora.astimezone(pytz.utc)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha/hora inválido: {str(e)}"
        )
    
    # Llamar a la API de Cal.com v2 para reagendar usando el UID
    url = f"https://api.cal.com/v2/bookings/{booking_uid}/reschedule"  # Ahora usa booking_uid
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }
    data = {
        "start": fecha_hora_utc.isoformat()
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code in [200, 201]:
            return {
                "mensaje": "Cita reagendada exitosamente",
                "nueva_cita": response.json()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error al reagendar: {response.text}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error de conexión: {str(e)}"
        )

# Endpoint para Dashboard - Estadísticas de citas
@router.get("/dashboard/stats")
def obtener_estadisticas(
    current_user: Usuario = Depends(get_current_active_user)
):
    """
    Devuelve estadísticas para el Dashboard:
    - total_citas: Total de citas
    - citas_hoy: Citas agendadas para hoy
    - citas_proximas: Citas en los próximos 7 días
    - citas_canceladas: Total de citas canceladas
    - porcentaje_ocupacion: Porcentaje de ocupación (próximos 7 días / slots disponibles)
    - total_slots: Total de slots disponibles en los próximos 7 días
    """
    event_type_id = 1288606
    ecuador = pytz.timezone(TIMEZONE)
    ahora = datetime.now(ecuador)
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # CORREGIDO: usar la misma lógica que el endpoint /slots
    # Comenzar desde mañana a las 00:00
    inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(days=7)  # 7 días a partir de mañana
    
    dentro_7_dias = fin  # Para comparar citas próximas
    
    # Obtener todas las citas
    url = f"https://api.cal.com/v2/bookings?eventTypeId={event_type_id}&limit=100"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al obtener citas: {response.status_code}"
            )
        
        data = response.json()
        bookings = data.get("data", {}).get("bookings", [])
        
        # Inicializar contadores
        total_citas = 0
        citas_hoy = 0
        citas_proximas = 0
        citas_canceladas = 0
        
        for booking in bookings:
            status = booking.get("status")
            start_time_str = booking.get("startTime")
            
            total_citas += 1
            
            if status == "CANCELLED":
                citas_canceladas += 1
            
            if start_time_str:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')).astimezone(ecuador)
                start_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if start_date == hoy:
                    citas_hoy += 1
                
                # Citas desde mañana hasta dentro de 7 días
                if inicio <= start_date <= dentro_7_dias:
                    citas_proximas += 1
        
        # Obtener slots disponibles usando la misma lógica de fechas
        start_utc = inicio.astimezone(pytz.utc).isoformat()
        end_utc = fin.astimezone(pytz.utc).isoformat()
        
        slots_url = "https://api.cal.com/v2/slots"
        slots_headers = {
            "Authorization": f"Bearer {CALCOM_API_KEY}",
            "cal-api-version": "2024-09-04"  # Misma versión que en /slots
        }
        slots_params = {
            "eventTypeId": event_type_id,
            "start": start_utc,
            "end": end_utc,
            "timeZone": TIMEZONE,
            "duration": 60
        }
        
        slots_response = requests.get(slots_url, headers=slots_headers, params=slots_params, timeout=10)
        total_slots = 0
        slots_por_dia = {}
        
        if slots_response.status_code == 200:
            slots_data = slots_response.json()
            for fecha_utc, slots_dia in slots_data.get("data", {}).items():
                cantidad_slots = len(slots_dia)
                total_slots += cantidad_slots
                fecha_local = datetime.fromisoformat(fecha_utc.replace('Z', '+00:00')).astimezone(ecuador)
                slots_por_dia[fecha_local.strftime("%Y-%m-%d")] = cantidad_slots
        
        porcentaje_ocupacion = 0
        if total_slots > 0:
            porcentaje_ocupacion = round((citas_proximas / total_slots) * 100, 1)
        
        return {
            "total_citas": total_citas,
            "citas_hoy": citas_hoy,
            "citas_proximas": citas_proximas,
            "citas_canceladas": citas_canceladas,
            "porcentaje_ocupacion": porcentaje_ocupacion,
            "total_slots": total_slots,
            "slots_por_dia": slots_por_dia,
            "periodo_proximas": "7 días",
            "fecha_actual": ahora.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en la consulta: {str(e)}"
        )