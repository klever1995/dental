# ==============================
# Endpoint de gestión de citas con Google Calendar
# Listado, agendamiento, cancelación, reagendamiento, estadísticas y webhook
# ==============================
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta

    

from app.db.base import get_db
from app.models.usuarios import Usuario
from app.models.especialidad import Especialidad
from app.api.v1.endpoints.usuarios import get_current_active_user
from app.socket_manager import emitir_cita_actualizada
from app.services.google_calendar import obtener_citas_cliente_por_cedula, obtener_slots_disponibles, agendar_cita, eliminar_cita, reagendar_cita

router = APIRouter(prefix="/citas", tags=["citas"])

TIMEZONE = "America/Guayaquil"

# ==============================
# Listar todas las citas (futuras y pasadas) con filtro por especialidad
# ==============================
@router.get("/")
def listar_todas_citas(
    especialidad_id: Optional[int] = None,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    if current_user.rol != "admin":
        if not current_user.especialidad_id:
            return []
        especialidad_id = current_user.especialidad_id
    
    # Obtener los calendar_ids según el filtro
    especialidades_query = db.query(Especialidad).filter(
        Especialidad.activa == True,
        Especialidad.calendar_id.isnot(None)
    )
    
    if especialidad_id is not None:
        especialidades_query = especialidades_query.filter(Especialidad.id == especialidad_id)
    
    especialidades = especialidades_query.all()
    
    if not especialidades:
        return []
    
    ecuador = pytz.timezone(TIMEZONE)
    todas_las_citas = []
    
    # Autenticación con Google (una sola vez, fuera del bucle)
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error autenticando con Google Calendar: {str(e)}")
    
    for esp in especialidades:
        try:
            # Consultar eventos (últimos 6 meses hasta próximo año)
            now = datetime.now(ecuador)
            time_min = (now - timedelta(days=180)).astimezone(pytz.utc).isoformat()
            time_max = (now + timedelta(days=365)).astimezone(pytz.utc).isoformat()
            
            events_result = service.events().list(
                calendarId=esp.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            eventos = events_result.get('items', [])
            
            for event in eventos:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                summary = event.get('summary', '')
                description = event.get('description', '')
                event_id = event.get('id')
                status = event.get('status', 'confirmed')
                html_link = event.get('htmlLink')
                
                telefono = None
                correo = None
                notas = None
                cedula = None
                
                if description:
                    lines = description.split('\n')
                    for line in lines:
                        if line.startswith('Teléfono:'):
                            telefono = line.replace('Teléfono:', '').strip()
                        elif line.startswith('Correo:'):
                            correo = line.replace('Correo:', '').strip()
                        elif line.startswith('Notas:'):
                            notas = line.replace('Notas:', '').strip()
                
                if ' - ' in summary:
                    partes = summary.split(' - ')
                    if len(partes) == 2:
                        nombre = partes[0]
                        cedula = partes[1].strip()
                    else:
                        nombre = summary
                else:
                    nombre = summary
                
                if start and 'T' in start:
                    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    if start_dt.tzinfo is None:
                        start_dt = pytz.utc.localize(start_dt)
                    start_local = start_dt.astimezone(ecuador)
                    start_time = start_local.isoformat()
                else:
                    start_time = start
                
                if end and 'T' in end:
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    if end_dt.tzinfo is None:
                        end_dt = pytz.utc.localize(end_dt)
                    end_local = end_dt.astimezone(ecuador)
                    end_time = end_local.isoformat()
                else:
                    end_time = end
                
                todas_las_citas.append({
                    "booking_id": event_id,
                    "uid": event_id,
                    "title": summary,
                    "start_time": start_time,
                    "end_time": end_time,
                    "status": status,
                    "created_at": event.get('created', None),
                    "updated_at": event.get('updated', None),
                    "cliente_nombre": nombre,
                    "cliente_email": correo,
                    "cedula": cedula,
                    "telefono": telefono,
                    "notas": notas,
                    "especialidad": esp.nombre,
                    "calendar_id": esp.calendar_id,
                    "link": html_link
                })
                
        except Exception as e:
            print(f"⚠️ Error consultando calendario {esp.nombre}: {e}")
            continue
    
    todas_las_citas.sort(key=lambda x: x.get('start_time', ''), reverse=True)
    return todas_las_citas

# ==============================
# Consultar horarios disponibles (slots) para una especialidad
# ==============================
@router.get("/slots")
def consultar_slots(
    especialidad: str,
    fecha_inicio: str = None,
    dias_a_mostrar: int = 5,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Obtener calendar_id desde la base de datos
    esp = db.query(Especialidad).filter(
        Especialidad.nombre.ilike(especialidad),
        Especialidad.activa == True
    ).first()
    
    if not esp or not esp.calendar_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la especialidad '{especialidad}' o no tiene calendario asociado"
        )
    
    resultado = obtener_slots_disponibles(
        calendar_id=esp.calendar_id,
        fecha_inicio=fecha_inicio,
        dias_a_mostrar=dias_a_mostrar
    )
    
    if resultado.get("exito"):
        return resultado.get("slots_por_fecha", {})
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resultado.get("mensaje", "Error al consultar slots")
        )

# ==============================
# Agendar una nueva cita desde el panel de administración
# ==============================    
@router.post("/agendar")
def agendar_cita_desde_panel(
    especialidad: str = Form(...), 
    cliente_nombre: str = Form(...),
    cliente_email: str = Form(...),
    cliente_cedula: str = Form(...),
    cliente_telefono: str = Form(...),
    cliente_notas: str = Form(None),
    fecha: str = Form(...),
    hora: str = Form(...),
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Agendar cita en una especialidad específica usando Google Calendar.
    """
    # Obtener calendar_id desde la base de datos
    esp = db.query(Especialidad).filter(
        Especialidad.nombre.ilike(especialidad),
        Especialidad.activa == True
    ).first()
    
    if not esp or not esp.calendar_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró la especialidad '{especialidad}' o no tiene calendario asociado"
        )
    
    ecuador = pytz.timezone(TIMEZONE)
    
    try:
        fecha_hora = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        if fecha_hora.tzinfo is None:
            fecha_hora = ecuador.localize(fecha_hora)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha/hora inválido: {str(e)}"
        )
    
    resultado = agendar_cita(
        calendar_id=esp.calendar_id,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        cliente_cedula=cliente_cedula,
        cliente_telefono=cliente_telefono,
        hora=fecha_hora,
        notas_adicionales=cliente_notas
    )
    
    if resultado.get("exito"):
        return {
            "mensaje": "Cita agendada exitosamente",
            "cita": resultado.get("data")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resultado.get("error", "Error al agendar la cita")
        )    

# ==============================
# Cancelar una cita existente
# ==============================    
@router.delete("/{event_id}")
def cancelar_cita(
    event_id: str,
    calendar_id: str,  
    current_user: Usuario = Depends(get_current_active_user)
):
    """
    Cancela una cita en Google Calendar.
    """
    resultado = eliminar_cita(event_id=event_id, calendar_id=calendar_id)
    
    if resultado.get("exito"):
        return {"mensaje": "Cita cancelada exitosamente"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resultado.get("error", "Error al cancelar la cita")
        )    
    
# ==============================
# Reagendar una cita (cambiar fecha/hora)
# ==============================    
@router.put("/{event_id}/reagendar")
def reagendar_cita_desde_panel(
    event_id: str,
    calendar_id: str = Form(...),  
    nueva_fecha: str = Form(...),
    nueva_hora: str = Form(...),
    cliente_nombre: str = Form(...),
    cliente_email: str = Form(...),
    cliente_telefono: str = Form(...),
    cliente_cedula: str = Form(...),  
    cliente_notas: str = Form(None),  
    current_user: Usuario = Depends(get_current_active_user)
):
    
    ecuador = pytz.timezone(TIMEZONE)
    
    try:
        fecha_hora = datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
        if fecha_hora.tzinfo is None:
            fecha_hora = ecuador.localize(fecha_hora)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de fecha/hora inválido: {str(e)}"
        )
    
    resultado = reagendar_cita(
        event_id=event_id,
        calendar_id=calendar_id,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        cliente_cedula=cliente_cedula,
        cliente_telefono=cliente_telefono,
        nueva_fecha=nueva_fecha,
        nueva_hora=nueva_hora,
        notas_originales=cliente_notas
    )
    
    if resultado.get("exito"):
        return {
            "mensaje": "Cita reagendada exitosamente",
            "nueva_cita": resultado.get("nueva_cita")
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resultado.get("error", "Error al reagendar la cita")
        )    

# ==============================
# Obtener estadísticas del dashboard (totales, citas hoy, próximas, etc.)
# ==============================    
@router.get("/dashboard/stats")
def obtener_estadisticas(
    especialidad_id: Optional[int] = None, 
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    ecuador = pytz.timezone(TIMEZONE)
    ahora = datetime.now(ecuador)
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Determinar qué calendarios consultar
    calendarios_a_consultar = []
    
    if current_user.rol == "admin":
        if especialidad_id:
            # Admin con filtro: solo esa especialidad
            esp = db.query(Especialidad).filter(
                Especialidad.id == especialidad_id,
                Especialidad.activa == True,
                Especialidad.calendar_id.isnot(None)
            ).first()
            if esp:
                calendarios_a_consultar = [esp.calendar_id]
        else:
            # Admin sin filtro: todas las especialidades
            especialidades = db.query(Especialidad).filter(
                Especialidad.activa == True,
                Especialidad.calendar_id.isnot(None)
            ).all()
            calendarios_a_consultar = [esp.calendar_id for esp in especialidades]
    else:
        # Doctor: su propia especialidad (ignora especialidad_id)
        if current_user.especialidad_id:
            esp = db.query(Especialidad).filter(
                Especialidad.id == current_user.especialidad_id,
                Especialidad.activa == True
            ).first()
            if esp and esp.calendar_id:
                calendarios_a_consultar = [esp.calendar_id]
    
    if not calendarios_a_consultar:
        return {
            "total_citas": 0,
            "citas_hoy": 0,
            "citas_proximas": 0,
            "citas_canceladas": 0,
            "porcentaje_ocupacion": 0,
            "total_slots": 0,
            "slots_por_dia": {},
            "periodo_proximas": "7 días",
            "fecha_actual": ahora.isoformat()
        }
    
    # Autenticación con Google
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error autenticando con Google Calendar: {str(e)}")
    
    # Rango de fechas: desde hoy hasta dentro de 7 días (para slots)
    inicio_slots = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    fin_slots = inicio_slots + timedelta(days=7)
    
    # Rango de fechas para citas pasadas (últimos 6 meses)
    inicio_pasadas = (ahora - timedelta(days=180)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Contadores
    total_citas = 0
    citas_hoy = 0
    citas_proximas = 0
    citas_canceladas = 0
    total_slots = 0
    slots_por_dia = {}
    
    for cal_id in calendarios_a_consultar:
        try:
            # Consultar eventos (incluyendo cancelados)
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=inicio_pasadas.astimezone(pytz.utc).isoformat(),
                singleEvents=True,
                orderBy='startTime',
                showDeleted=True
            ).execute()
            
            eventos = events_result.get('items', [])
            
            for event in eventos:
                start = event['start'].get('dateTime')
                if not start:
                    continue
                
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = pytz.utc.localize(start_dt)
                start_local = start_dt.astimezone(ecuador)
                start_date = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
                event_status = event.get('status', 'confirmed')
                
                # Total de citas confirmadas (no canceladas)
                if event_status != 'cancelled':
                    total_citas += 1
                
                if event_status == 'cancelled':
                    citas_canceladas += 1
                
                if start_date == hoy and event_status != 'cancelled':
                    citas_hoy += 1
                
                if inicio_slots <= start_date <= fin_slots and event_status != 'cancelled':
                    citas_proximas += 1
            
            # Calcular slots disponibles (solo para el rango de 7 días)
            dia_actual = inicio_slots
            while dia_actual < fin_slots:
                fecha_str = dia_actual.strftime("%Y-%m-%d")
                if dia_actual.weekday() < 5:
                    if fecha_str not in slots_por_dia:
                        slots_por_dia[fecha_str] = 0
                    
                    day_start = dia_actual.astimezone(pytz.utc).isoformat()
                    day_end = (dia_actual + timedelta(days=1)).astimezone(pytz.utc).isoformat()
                    
                    day_events = service.events().list(
                        calendarId=cal_id,
                        timeMin=day_start,
                        timeMax=day_end,
                        singleEvents=True
                    ).execute()
                    
                    eventos_dia = day_events.get('items', [])
                    horas_ocupadas = set()
                    for ev in eventos_dia:
                        ev_start = ev['start'].get('dateTime')
                        if ev_start:
                            ev_start_dt = datetime.fromisoformat(ev_start.replace('Z', '+00:00'))
                            if ev_start_dt.tzinfo is None:
                                ev_start_dt = pytz.utc.localize(ev_start_dt)
                            ev_start_local = ev_start_dt.astimezone(ecuador)
                            horas_ocupadas.add(ev_start_local.strftime("%H:%M"))
                    
                    slots_dia = 0
                    for hora in range(9, 17):
                        hora_str = f"{hora:02d}:00"
                        if hora_str not in horas_ocupadas:
                            slots_dia += 1
                    
                    slots_por_dia[fecha_str] += slots_dia
                    total_slots += slots_dia
                dia_actual += timedelta(days=1)
                
        except Exception as e:
            print(f"⚠️ Error consultando calendario {cal_id}: {e}")
            continue
    
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

# ==============================
# Historial de citas de un paciente por cédula
# ==============================
@router.get("/historial/{cedula}")
def obtener_historial_citas(
    cedula: str,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    especialidad_id: Optional[int] = None,
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from datetime import datetime, timedelta
    import pytz
    import os
    
    ecuador = pytz.timezone(TIMEZONE)
    ahora = datetime.now(ecuador)
    
    # Determinar qué calendarios consultar
    calendarios_a_consultar = []
    especialidades = [] 
    
    if current_user.rol == "admin":
        if especialidad_id:
            esp = db.query(Especialidad).filter(
                Especialidad.id == especialidad_id,
                Especialidad.activa == True,
                Especialidad.calendar_id.isnot(None)
            ).first()
            if esp:
                calendarios_a_consultar = [esp.calendar_id]
                especialidades = [esp]
        else:
            especialidades = db.query(Especialidad).filter(
                Especialidad.activa == True,
                Especialidad.calendar_id.isnot(None)
            ).all()
            calendarios_a_consultar = [esp.calendar_id for esp in especialidades]
    else:
        if current_user.especialidad_id:
            esp = db.query(Especialidad).filter(
                Especialidad.id == current_user.especialidad_id,
                Especialidad.activa == True
            ).first()
            if esp and esp.calendar_id:
                calendarios_a_consultar = [esp.calendar_id]
                especialidades = [esp]
    
    if not calendarios_a_consultar:
        return {"cedula": cedula, "total": 0, "citas": []}
    
    # Autenticación con Google
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error autenticando con Google Calendar: {str(e)}")
    
    # Determinar rango de fechas
    if fecha_desde:
        try:
            time_min = datetime.strptime(fecha_desde, "%Y-%m-%d")
            time_min = ecuador.localize(time_min).astimezone(pytz.utc).isoformat()
        except:
            raise HTTPException(status_code=400, detail="Formato de fecha_desde inválido. Usa YYYY-MM-DD")
    else:
        time_min = (ahora - timedelta(days=365*2)).astimezone(pytz.utc).isoformat()
    
    if fecha_hasta:
        try:
            time_max = datetime.strptime(fecha_hasta, "%Y-%m-%d")
            time_max = ecuador.localize(time_max).replace(hour=23, minute=59, second=59).astimezone(pytz.utc).isoformat()
        except:
            raise HTTPException(status_code=400, detail="Formato de fecha_hasta inválido. Usa YYYY-MM-DD")
    else:
        time_max = ahora.astimezone(pytz.utc).isoformat()
    
    citas = []
    
    for cal_id in calendarios_a_consultar:
        try:
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            eventos = events_result.get('items', [])
            
            for event in eventos:
                start = event['start'].get('dateTime')
                if not start:
                    continue
                
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = pytz.utc.localize(start_dt)
                start_local = start_dt.astimezone(ecuador)
                
                # Incluir citas pasadas 
                if start_local > ahora:
                    continue
                
                summary = event.get('summary', '')
                description = event.get('description', '')
                event_id = event.get('id')
                html_link = event.get('htmlLink')
                
                # Extraer datos de la descripción
                telefono = None
                correo = None
                notas = None
                cedula_evento = None
                
                if description:
                    lines = description.split('\n')
                    for line in lines:
                        if line.startswith('Teléfono:'):
                            telefono = line.replace('Teléfono:', '').strip()
                        elif line.startswith('Correo:'):
                            correo = line.replace('Correo:', '').strip()
                        elif line.startswith('Notas:'):
                            notas = line.replace('Notas:', '').strip()
                
                # Extraer cédula del summary (formato "Nombre - Cédula")
                if ' - ' in summary:
                    partes = summary.split(' - ')
                    if len(partes) == 2:
                        nombre = partes[0]
                        cedula_evento = partes[1].strip()
                    else:
                        nombre = summary
                else:
                    nombre = summary
                
                if cedula_evento != cedula:
                    continue
                
                # Obtener nombre de especialidad
                especialidad_nombre = "Desconocida"
                for esp in especialidades:
                    if esp.calendar_id == cal_id:
                        especialidad_nombre = esp.nombre
                        break
                
                citas.append({
                    "booking_id": event_id,
                    "uid": event_id,
                    "start_time": start_local.isoformat(),
                    "end_time": (start_local + timedelta(hours=1)).isoformat(),
                    "status": event.get('status', 'confirmed'),
                    "cliente_nombre": nombre,
                    "cliente_email": correo,
                    "cedula": cedula_evento,
                    "telefono": telefono,
                    "notas": notas,
                    "link": html_link,
                    "especialidad": especialidad_nombre,
                    "calendar_id": cal_id
                })
                
        except Exception as e:
            print(f"⚠️ Error consultando calendario {cal_id}: {e}")
            continue
    
    # Ordenar por fecha descendente (más reciente primero)
    citas.sort(key=lambda x: x.get('start_time', ''), reverse=True)
    
    return {
        "cedula": cedula,
        "total": len(citas),
        "citas": citas
    }

# ==============================
# Webhook para notificaciones push de Google Calendar
# ==============================
@router.post("/webhook/google")
async def google_calendar_webhook(request: Request):

    resource_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    channel_id = request.headers.get("X-Goog-Channel-ID")
    
    print(f"📢 Webhook recibido - State: {resource_state}, ResourceID: {resource_id}, ChannelID: {channel_id}")
    
    if resource_state in ["exists", "update", "sync"]:
        await emitir_cita_actualizada()
        print("✅ Notificación enviada a frontend via Socket.IO")
    elif resource_state == "delete":
        await emitir_cita_actualizada()
        print("🗑️ Recurso eliminado, notificando frontend")
    
    return {"status": "ok"}