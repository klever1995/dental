from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
import requests
import os

from app.db.base import get_db
from app.models.usuarios import Usuario
from app.api.v1.endpoints.usuarios import get_current_active_user
from app.socket_manager import emitir_cita_actualizada

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
                attendees = booking.get("attendees", [])
                telefono = attendees[0].get("phoneNumber") if attendees else None
                
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
                    "cliente_email": None,
                    "cedula": None,
                    "telefono": telefono,
                    "notas": None  # 🔥 NUEVO CAMPO
                }
                
                if attendees:
                    cita["cliente_nombre"] = attendees[0].get("name")
                    cita["cliente_email"] = attendees[0].get("email")
                
                responses = booking.get("responses", {})
                
                if not cita["cliente_nombre"]:
                    cita["cliente_nombre"] = responses.get("name")
                
                if not cita["cliente_email"]:
                    cita["cliente_email"] = responses.get("email")
                
                cita["cedula"] = responses.get("cedula")
                cita["notas"] = responses.get("notes")  # 🔥 EXTRAER NOTAS
                
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
    cliente_cedula: str = Form(...),
    cliente_telefono: str = Form(...),
    cliente_notas: str = Form(None),  # 🔥 NUEVO CAMPO (opcional)
    fecha: str = Form(...),
    hora: str = Form(...),
    current_user: Usuario = Depends(get_current_active_user)
):
    event_type_id = 1288606
    ecuador = pytz.timezone(TIMEZONE)
    
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
            "timeZone": TIMEZONE,
            "phoneNumber": cliente_telefono
        },
        "bookingFieldsResponses": {
            "cedula": cliente_cedula
        }
    }
    
    # 🔥 AGREGAR NOTAS SI VIENEN
    if cliente_notas:
        data["bookingFieldsResponses"]["notes"] = cliente_notas
    
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
    booking_uid: str,
    nueva_fecha: str = Form(...),
    nueva_hora: str = Form(...),
    cliente_nombre: str = Form(...),
    cliente_email: str = Form(...),
    cliente_telefono: str = Form(...),  
    current_user: Usuario = Depends(get_current_active_user)
):
    """
    Reagenda una cita existente.
    Se requiere el booking_uid (ej: "njn2N2J1d9Jz1kpiJ8Wb1z") y los datos del cliente
    """
    ecuador = pytz.timezone(TIMEZONE)
    
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
    
    url = f"https://api.cal.com/v2/bookings/{booking_uid}/reschedule"
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
    
# Endpoint para webhook de Cal.com (notificaciones en tiempo real)
@router.post("/webhook/calcom")
async def webhook_calcom(request: Request):
    """
    Recibe notificaciones de Cal.com cuando ocurren cambios en reservas.
    Luego emite evento vía WebSocket para actualizar el frontend.
    """
    # 1. Obtener el payload
    try:
        payload = await request.json()
        print(f"📨 [WEBHOOK] Payload recibido: {payload}")
    except Exception as e:
        print(f"❌ [WEBHOOK] Error al leer JSON: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # 2. Procesar evento (CORREGIDO: usar triggerEvent y payload)
    event = payload.get("triggerEvent")  # ✅ Cambiado de "event"
    booking_data = payload.get("payload", {})  # ✅ Cambiado de "data.booking"
    booking_uid = booking_data.get("uid")
    event_type_id = booking_data.get("eventTypeId")
    
    print(f"🔍 [WEBHOOK] Evento: {event}, Booking UID: {booking_uid}, EventTypeId: {event_type_id}")
    
    if event in ["BOOKING_CREATED", "BOOKING_CANCELLED", "BOOKING_RESCHEDULED"]:
        # Determinar empresa_id según event_type_id (ajusta según tus empresas)
        empresa_id = 1  # Por defecto
        if event_type_id == 1288606:  # Tu event type actual
            empresa_id = 1
        # Agrega más mapeos si tienes otras empresas con diferentes eventTypeId
        
        cita_data = {
            "evento": event,
            "booking_uid": booking_uid,
            "booking": booking_data
        }
        
        print(f"📡 [WEBHOOK] Intentando emitir evento a sala empresa_{empresa_id}")
        print(f"📡 [WEBHOOK] Datos a emitir: {cita_data}")
        
        try:
            await emitir_cita_actualizada(cita_data, empresa_id)
            print(f"✅ [WEBHOOK] Evento emitido correctamente para cita {booking_uid}")
        except Exception as e:
            print(f"❌ [WEBHOOK] Error al emitir evento WebSocket: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        print(f"⚠️ [WEBHOOK] Evento no relevante: {event}")
    
    return {"status": "ok", "evento_recibido": event}    

@router.get("/historial/{cedula}")
def historial_citas_cliente(
    cedula: str,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    current_user: Usuario = Depends(get_current_active_user)
):
    event_type_id = 1288606
    ecuador = pytz.timezone("America/Guayaquil")
    
    url = f"https://api.cal.com/v2/bookings?eventTypeId={event_type_id}&status=past"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Error de API: {response.status_code} - {response.text}")
        
        data = response.json()
        if isinstance(data.get("data"), list):
            bookings = data.get("data")
        else:
            bookings = data.get("data", {}).get("bookings", [])
        
        citas_pasadas = []
        for booking in bookings:
            responses = booking.get("responses") or booking.get("bookingFieldsResponses") or {}
            cedula_booking = None
            notas = None  # 🔥 NUEVO
            if isinstance(responses, dict):
                cedula_booking = responses.get("cedula") or responses.get("Cédula")
                if isinstance(cedula_booking, dict):
                    cedula_booking = cedula_booking.get("value")
                notas = responses.get("notes")  # 🔥 EXTRAER NOTAS
            elif isinstance(responses, list):
                for item in responses:
                    if isinstance(item, dict):
                        key = item.get("label") or item.get("key") or item.get("name")
                        if key and key.lower() == "cedula":
                            cedula_booking = item.get("value")
                        if key and key.lower() == "notes":
                            notas = item.get("value")
                        if cedula_booking and notas:
                            break
            
            if not cedula_booking or str(cedula_booking) != str(cedula):
                continue
            
            start_utc = datetime.fromisoformat(booking.get("start").replace("Z", "+00:00"))
            if start_utc.tzinfo is None:
                start_utc = pytz.utc.localize(start_utc)
            start_local = start_utc.astimezone(ecuador)
            
            if fecha_desde:
                fecha_desde_dt = datetime.strptime(fecha_desde, "%Y-%m-%d").replace(tzinfo=ecuador)
                if start_local < fecha_desde_dt:
                    continue
            if fecha_hasta:
                fecha_hasta_dt = datetime.strptime(fecha_hasta, "%Y-%m-%d").replace(tzinfo=ecuador)
                if start_local > fecha_hasta_dt:
                    continue
            
            end_utc = datetime.fromisoformat(booking.get("end").replace("Z", "+00:00"))
            if end_utc.tzinfo is None:
                end_utc = pytz.utc.localize(end_utc)
            end_local = end_utc.astimezone(ecuador)
            
            attendees = booking.get("attendees", [])
            telefono = attendees[0].get("phoneNumber") if attendees else None
            nombre = attendees[0].get("name") if attendees else None
            email = attendees[0].get("email") if attendees else None
            
            citas_pasadas.append({
                "booking_id": booking.get("id"),
                "uid": booking.get("uid"),
                "start_time": start_local.isoformat(),
                "end_time": end_local.isoformat(),
                "status": booking.get("status"),
                "cancellationReason": booking.get("cancellationReason"),
                "rescheduledFromUid": booking.get("rescheduledFromUid"),
                "cliente_nombre": nombre,
                "cliente_email": email,
                "cedula": cedula_booking,
                "telefono": telefono,
                "notas": notas  # 🔥 NUEVO CAMPO
            })
        
        return {
            "cedula": cedula,
            "total": len(citas_pasadas),
            "citas": citas_pasadas
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")