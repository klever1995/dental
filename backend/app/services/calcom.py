import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

# Cargar variables de entorno
load_dotenv(dotenv_path=r"C:\Users\Klever\Desktop\dental\dental\.env")
CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
TIMEZONE = "America/Guayaquil"

def obtener_slots_disponibles(
    event_type_id: int, 
    fecha_inicio: str = None, 
    dias_a_mostrar: int = 5
) -> dict:
    """
    Consulta slots disponibles usando API v2 de Cal.com
    
    Args:
        event_type_id: ID del tipo de evento en Cal.com
        fecha_inicio: Fecha específica en formato 'YYYY-MM-DD' (opcional)
        dias_a_mostrar: Si no hay fecha_inicio, muestra esta cantidad de días
    
    Returns:
        dict: {
            "exito": bool,
            "slots_por_fecha": {"YYYY-MM-DD": ["09:00", "10:00", ...]},
            "mensaje": str
        }
    """
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
            fin = inicio + timedelta(days=1)  # Solo ese día
        except ValueError:
            return {
                "exito": False,
                "slots_por_fecha": {},
                "mensaje": f"Formato de fecha inválido. Usa YYYY-MM-DD"
            }
    else:
        # Desde mañana
        inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        fin = inicio + timedelta(days=dias_a_mostrar)
    
    # Convertir a UTC para la API
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
                
                # Ordenar horas
                for fecha in slots_por_fecha:
                    slots_por_fecha[fecha].sort()
                
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
            else:
                return {
                    "exito": False,
                    "slots_por_fecha": {},
                    "mensaje": "La respuesta de Cal.com no contiene datos"
                }
        else:
            return {
                "exito": False,
                "slots_por_fecha": {},
                "mensaje": f"Error de API: {response.status_code}"
            }
    except Exception as e:
        return {
            "exito": False,
            "slots_por_fecha": {},
            "mensaje": f"Error en la consulta: {str(e)}"
        }

def agendar_cita(event_type_id: int, cliente_nombre: str, cliente_email: str, hora: datetime) -> dict:
    import requests
    import pytz

    if not hora:
        return {
            "exito": False,
            "error": "Se requiere una hora específica"
        }

    # Zona horaria Ecuador
    ecuador = pytz.timezone("America/Guayaquil")
    if hora.tzinfo is None:
        hora = ecuador.localize(hora)

    # Convertir a UTC
    hora_utc = hora.astimezone(pytz.utc)

    url = "https://api.cal.com/v2/bookings"

    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }

    # ✅ PAYLOAD CORRECTO (según tu error 400)
    data = {
        "start": hora_utc.isoformat(),
        "eventTypeId": event_type_id,
        "attendee": {   # 🔥 singular, no lista
            "name": cliente_nombre,
            "email": cliente_email,
            "timeZone": "America/Guayaquil"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)

        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)

        if response.status_code in [200, 201]:
            return {
                "exito": True,
                "data": response.json()
            }
        else:
            return {
                "exito": False,
                "error": f"Error {response.status_code}",
                "detalles": response.text
            }

    except Exception as e:
        return {
            "exito": False,
            "error": str(e)
        }
    
def obtener_citas_cliente(email: str) -> dict:
    url = "https://api.cal.com/v1/bookings"

    params = {
        "apiKey": CALCOM_API_KEY,
        "attendeeEmail": email
    }

    try:
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()

            citas = []
            ahora = datetime.now(pytz.utc)  # 👈 CAMBIADO: ahora usa pytz.utc
            ecuador = pytz.timezone("America/Guayaquil")  # 👈 NUEVO: zona horaria local

            bookings = data.get("bookings", data)

            for booking in bookings:

                fecha_str = booking.get("startTime") or booking.get("start")
                if not fecha_str:
                    continue

                # Convertir a datetime con zona horaria UTC
                fecha_utc = datetime.fromisoformat(
                    fecha_str.replace("Z", "+00:00")
                )

                # Asegurar que tenga zona horaria (por si acaso)
                if fecha_utc.tzinfo is None:
                    fecha_utc = pytz.utc.localize(fecha_utc)

                # Convertir a hora local de Ecuador
                fecha_local = fecha_utc.astimezone(ecuador)

                # solo citas futuras (comparar en UTC para evitar errores)
                if fecha_utc >= ahora and booking.get("status") != "CANCELLED":
                    citas.append({
                        "booking_id": booking.get("id"),
                        # 👇 GUARDAMOS LA FECHA EN FORMATO LOCAL ISO
                        "fecha": fecha_local.isoformat(),
                        "estado": booking.get("status"),
                        "event_type_id": booking.get("eventTypeId"),
                        "asistentes": booking.get("attendees", [])
                    })

            return {
                "exito": True,
                "citas": citas
            }

        else:
            return {
                "exito": False,
                "error": f"Error {response.status_code}",
                "detalles": response.text
            }

    except Exception as e:
        return {
            "exito": False,
            "error": str(e)
        }    

def eliminar_cita(booking_id: int) -> dict:
    """
    Elimina una cita existente usando API v1
    """
    url = f"https://api.cal.com/v1/bookings/{booking_id}"
    params = {"apiKey": CALCOM_API_KEY}
    response = requests.delete(url, params=params)
    print(f"🔍 RESPUESTA CRUDA DE CAL.COM AL ELIMINAR: {response.status_code} - {response.text}")
    
    if response.status_code in [200, 204]:
        return {"exito": True}
    else:
        return {
            "exito": False,
            "error": f"Error {response.status_code}",
            "detalles": response.json()
        }

def reagendar_cita(booking_id: int, event_type_id: int, cliente_nombre: str, cliente_email: str, nueva_fecha: str, nueva_hora: str) -> dict:
    """
    Reagenda una cita: verifica disponibilidad, cancela la original y crea una nueva.
    
    Args:
        booking_id: ID de la cita original
        event_type_id: ID del tipo de evento
        cliente_nombre: Nombre del cliente
        cliente_email: Email del cliente
        nueva_fecha: Nueva fecha en formato 'YYYY-MM-DD'
        nueva_hora: Nueva hora en formato 'HH:MM'
    
    Returns:
        dict: Resultado de la operación
    """
    
    # 1. Verificar disponibilidad de la nueva fecha/hora
    ecuador = pytz.timezone("America/Guayaquil")
    
    # Consultar slots disponibles para la nueva fecha
    slots_resultado = obtener_slots_disponibles(
        event_type_id=event_type_id,
        fecha_inicio=nueva_fecha,
        dias_a_mostrar=1
    )
    
    if not slots_resultado.get("exito"):
        return {
            "exito": False,
            "error": "No se pudo verificar disponibilidad",
            "detalles": slots_resultado.get("mensaje")
        }
    
    # Verificar si la hora solicitada está disponible
    horas_disponibles = slots_resultado.get("slots_por_fecha", {}).get(nueva_fecha, [])
    if nueva_hora not in horas_disponibles:
        return {
            "exito": False,
            "error": "La nueva fecha/hora no está disponible",
            "horarios_disponibles": horas_disponibles
        }
    
    # 2. Construir datetime con la nueva fecha/hora
    año, mes, dia = map(int, nueva_fecha.split('-'))
    hora, minuto = map(int, nueva_hora.split(':'))
    nueva_hora_dt = ecuador.localize(datetime(año, mes, dia, hora, minuto))
    
    # 3. Cancelar la cita original
    resultado_eliminar = eliminar_cita(booking_id)
    if not resultado_eliminar["exito"]:
        return {
            "exito": False,
            "error": "No se pudo cancelar la cita original",
            "detalles": resultado_eliminar
        }
    
    # 4. Agendar la nueva cita
    resultado_agendar = agendar_cita(
        event_type_id=event_type_id,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        hora=nueva_hora_dt
    )
    
    if not resultado_agendar["exito"]:
        # Si falla el agendamiento, la cita original ya se perdió (riesgo asumido)
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