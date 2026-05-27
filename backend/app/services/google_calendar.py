# ==============================
# Servicio de Google Calendar
# Autenticación y operaciones CRUD sobre calendarios y eventos
# ==============================

import os
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Cargar variables de entorno
load_dotenv(dotenv_path=r"C:\Users\Klever\Desktop\dental\dental\.env")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']
TIMEZONE = "America/Guayaquil"

# ==============================
# Obtener servicio autenticado de Google Calendar
# ==============================
def get_google_calendar_service():
    """Obtiene el servicio de Google Calendar autenticado con cuenta de servicio"""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def obtener_slots_disponibles(
    calendar_id: str, 
    fecha_inicio: str = None, 
    dias_a_mostrar: int = 5,
    duracion_minutos: int = 60
) -> dict:

    ecuador = pytz.timezone(TIMEZONE)
    ahora = datetime.now(ecuador)
    
    # Determinar fechas de inicio y fin
    if fecha_inicio:
        try:
            inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            inicio = ecuador.localize(inicio)
            # Si la fecha ya pasó, empezar desde mañana
            if inicio.date() < ahora.date():
                inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                print(f"⚠️ Fecha pasada, mostrando desde {inicio.strftime('%Y-%m-%d')}")
            else:
                inicio = inicio.replace(hour=0, minute=0, second=0, microsecond=0)
            fin = inicio + timedelta(days=1)  
        except ValueError:
            return {
                "exito": False,
                "slots_por_fecha": {},
                "mensaje": f"Formato de fecha inválido. Usa YYYY-MM-DD"
            }
    else:

        inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        fin = inicio + timedelta(days=dias_a_mostrar)
    
    # Convertir a UTC para la API de Google
    start_utc = inicio.astimezone(pytz.utc).isoformat()
    end_utc = fin.astimezone(pytz.utc).isoformat()
    
    try:
        service = get_google_calendar_service()
        
        # Obtener los eventos ocupados en el rango de fechas
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_utc,
            timeMax=end_utc,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        eventos = events_result.get('items', [])
        
        # Crear un conjunto de horarios ocupados (formato "YYYY-MM-DD HH:MM")
        ocupados = set()
        for event in eventos:
            start = event['start'].get('dateTime')
            if start:
                # Convertir a hora local de Ecuador
                start_utc = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_utc.tzinfo is None:
                    start_utc = pytz.utc.localize(start_utc)
                start_local = start_utc.astimezone(ecuador)
                hora_ocupada = start_local.strftime("%Y-%m-%d %H:%M")
                ocupados.add(hora_ocupada)
        
        # Generar todos los slots posibles en el rango de fechas
        slots_por_fecha = {}
        dia_actual = inicio
        hora_inicio_laboral = 9  
        hora_fin_laboral = 17   
        
        while dia_actual < fin:
            fecha_str = dia_actual.strftime("%Y-%m-%d")
            slots_por_fecha[fecha_str] = []
            
            # Generar slots desde hora_inicio hasta hora_fin - duracion
            hora = hora_inicio_laboral
            while hora + (duracion_minutos / 60) <= hora_fin_laboral:
                hora_str = f"{hora:02d}:00"
                slot_datetime = dia_actual.replace(hour=hora, minute=0, second=0, microsecond=0)
                slot_key = slot_datetime.strftime("%Y-%m-%d %H:%M")
                
                # Verificar si el slot está ocupado
                if slot_key not in ocupados:
                    slots_por_fecha[fecha_str].append(hora_str)
                
                hora += 1  
            
            dia_actual += timedelta(days=1)
        
        # Eliminar fechas sin slots
        slots_por_fecha = {k: v for k, v in slots_por_fecha.items() if v}
        
        if slots_por_fecha:
            return {
                "exito": True,
                "slots_por_fecha": slots_por_fecha,
                "mensaje": f"Se encontraron {sum(len(h) for h in slots_por_fecha.values())} horarios disponibles"
            }
        else:
            return {
                "exito": False,
                "slots_por_fecha": {},
                "mensaje": "No hay horarios disponibles en el rango consultado"
            }
            
    except HttpError as error:
        return {
            "exito": False,
            "slots_por_fecha": {},
            "mensaje": f"Error de API de Google Calendar: {error}"
        }
    except Exception as e:
        return {
            "exito": False,
            "slots_por_fecha": {},
            "mensaje": f"Error en la consulta: {str(e)}"
        }

# ==============================
# Crear una nueva cita en Google Calendar
# ==============================    
def agendar_cita(calendar_id: str, cliente_nombre: str, cliente_email: str, cliente_cedula: str, cliente_telefono: str, hora: datetime, notas_adicionales: str = None) -> dict:
    if not hora:
        return {
            "exito": False,
            "error": "Se requiere una hora específica"
        }

    # Zona horaria Ecuador
    ecuador = pytz.timezone("America/Guayaquil")
    if hora.tzinfo is None:
        hora = ecuador.localize(hora)

    # Convertir a UTC para la API de Google
    hora_utc = hora.astimezone(pytz.utc)
    fin_utc = (hora + timedelta(hours=1)).astimezone(pytz.utc)

    # Autenticación con cuenta de servicio
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        return {
            "exito": False,
            "error": f"Error autenticando con Google Calendar: {str(e)}"
        }

    # Construir el evento (sin attendees)
    event = {
        'summary': f"{cliente_nombre} - {cliente_cedula}",
        'description': f"Teléfono: {cliente_telefono}\nCorreo: {cliente_email if cliente_email else 'No proporcionado'}\nNotas: {notas_adicionales or 'Sin notas'}",
        'start': {
            'dateTime': hora_utc.isoformat(),
            'timeZone': 'America/Guayaquil',
        },
        'end': {
            'dateTime': fin_utc.isoformat(),
            'timeZone': 'America/Guayaquil',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 30},
            ],
        },
    }

    try:
        evento_creado = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        print("✅ Evento creado en Google Calendar")
        print(f"   ID: {evento_creado.get('id')}")
        print(f"   Link: {evento_creado.get('htmlLink')}")

        return {
            "exito": True,
            "data": {
                "id": evento_creado.get('id'),
                "link": evento_creado.get('htmlLink'),
                "summary": evento_creado.get('summary'),
                "start": evento_creado.get('start'),
                "end": evento_creado.get('end')
            }
        }

    except HttpError as error:
        return {
            "exito": False,
            "error": f"Error creando evento en Google Calendar: {error}",
            "detalles": str(error)
        }
    except Exception as e:
        return {
            "exito": False,
            "error": f"Error inesperado: {str(e)}"
        }

# ==============================
# Buscar citas de un paciente por número de cédula
# ==============================    
def obtener_citas_cliente_por_cedula(cedula: str, calendar_id: str = None) -> dict:

    # Configuración de Google Calendar
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        return {"exito": False, "error": f"Error autenticando con Google Calendar: {str(e)}"}

    # Determinar qué calendarios consultar
    calendarios_a_consultar = []
    if calendar_id:
        calendarios_a_consultar = [calendar_id]
    else:
        # Obtener todos los calendar_id de especialidades activas desde la BD
        from app.models.especialidad import Especialidad
        from app.db.base import SessionLocal
        db = SessionLocal()
        especialidades = db.query(Especialidad).filter(Especialidad.activa == True).all()
        db.close()
        calendarios_a_consultar = [esp.calendar_id for esp in especialidades if esp.calendar_id]

    if not calendarios_a_consultar:
        return {"exito": True, "citas": [], "mensaje": "No hay calendarios configurados"}

    # Rango de fechas: desde ahora hasta 1 año después
    ecuador = pytz.timezone("America/Guayaquil")
    ahora = datetime.now(ecuador)
    fin = ahora.replace(year=ahora.year + 1)
    
    time_min = ahora.astimezone(pytz.utc).isoformat()
    time_max = fin.astimezone(pytz.utc).isoformat()

    citas = []

    for cal_id in calendarios_a_consultar:
        try:
            # Obtener eventos del calendario
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            eventos = events_result.get('items', [])
            
            for event in eventos:
                # Extraer información del evento
                summary = event.get('summary', '')
                description = event.get('description', '')
                start = event.get('start', {}).get('dateTime')
                
                if not start:
                    continue
                
                # Buscar cédula en el summary (formato: "Nombre - Cédula")
                cedula_encontrada = None
                if ' - ' in summary:
                    partes = summary.split(' - ')
                    if len(partes) == 2:
                        cedula_encontrada = partes[1].strip()
                
                # Si no está en el summary, buscar en la descripción
                if not cedula_encontrada and 'Cédula:' in description:
                    for line in description.split('\n'):
                        if 'Cédula:' in line:
                            cedula_encontrada = line.split('Cédula:')[1].strip()
                            break
                
                if not cedula_encontrada or cedula_encontrada != str(cedula).strip():
                    continue
                
                # Convertir fecha a local
                start_utc = datetime.fromisoformat(start.replace('Z', '+00:00'))
                if start_utc.tzinfo is None:
                    start_utc = pytz.utc.localize(start_utc)
                start_local = start_utc.astimezone(ecuador)
                
                # Extraer teléfono y notas de la descripción
                telefono = None
                notas = None
                if description:
                    for line in description.split('\n'):
                        if 'Teléfono:' in line:
                            telefono = line.split('Teléfono:')[1].strip()
                        elif 'Notas:' in line:
                            notas = line.split('Notas:')[1].strip()
                
                citas.append({
                    "booking_id": event.get('id'),
                    "uid": event.get('id'),  
                    "fecha": start_local.isoformat(),
                    "estado": event.get('status', 'confirmed'),
                    "calendar_id": cal_id,
                    "cedula": cedula_encontrada,
                    "telefono": telefono,
                    "notas": notas or description,
                    "summary": summary,
                    "link": event.get('htmlLink')
                })
                
        except HttpError as error:
            print(f"⚠️ Error consultando calendario {cal_id}: {error}")
            continue

    return {"exito": True, "citas": citas}    

# ==============================
# Eliminar una cita de Google Calendar
# ==============================
def eliminar_cita(event_id: str, calendar_id: str) -> dict:

    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        print(f"✅ Evento {event_id} eliminado del calendario {calendar_id}")
        return {"exito": True}
    except HttpError as error:
        return {"exito": False, "error": f"Error eliminando evento: {error}"}
    except Exception as e:
        return {"exito": False, "error": f"Error inesperado: {str(e)}"}
    
def reagendar_cita(event_id: str, calendar_id: str, cliente_nombre: str, cliente_email: str, 
                   cliente_cedula: str, cliente_telefono: str, nueva_fecha: str, nueva_hora: str, 
                   notas_originales: str = None) -> dict:

    # 1. Verificar disponibilidad de la nueva fecha/hora en el mismo calendario
    slots_resultado = obtener_slots_disponibles(
        calendar_id=calendar_id,
        fecha_inicio=nueva_fecha,
        dias_a_mostrar=1
    )
    
    if not slots_resultado.get("exito"):
        return {
            "exito": False,
            "error": "No se pudo verificar disponibilidad",
            "detalles": slots_resultado.get("mensaje")
        }
    
    horas_disponibles = slots_resultado.get("slots_por_fecha", {}).get(nueva_fecha, [])
    if nueva_hora not in horas_disponibles:
        return {
            "exito": False,
            "error": "La nueva fecha/hora no está disponible",
            "horarios_disponibles": horas_disponibles
        }
    
    # 2. Construir datetime con la nueva fecha/hora
    ecuador = pytz.timezone("America/Guayaquil")
    año, mes, dia = map(int, nueva_fecha.split('-'))
    hora, minuto = map(int, nueva_hora.split(':'))
    nueva_hora_dt = ecuador.localize(datetime(año, mes, dia, hora, minuto))
    
    # 3. Cancelar la cita original
    resultado_eliminar = eliminar_cita(event_id=event_id, calendar_id=calendar_id)
    if not resultado_eliminar["exito"]:
        return {
            "exito": False,
            "error": "No se pudo cancelar la cita original",
            "detalles": resultado_eliminar
        }
    
    # 4. Agendar la nueva cita (conservando notas)
    resultado_agendar = agendar_cita(
        calendar_id=calendar_id,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        cliente_cedula=cliente_cedula,
        cliente_telefono=cliente_telefono,
        hora=nueva_hora_dt,
        notas_adicionales=notas_originales
    )
    
    if not resultado_agendar["exito"]:
        return {
            "exito": False,
            "error": "La cita original se canceló, pero no se pudo agendar la nueva",
            "detalles": resultado_agendar
        }
    
    return {
        "exito": True,
        "mensaje": "Cita reagendada exitosamente",
        "nueva_cita": resultado_agendar.get("data")
    }
