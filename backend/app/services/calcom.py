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

def agendar_cita(event_type_id: int, cliente_nombre: str, cliente_email: str, cliente_cedula: str, cliente_telefono: str, hora: datetime, notas_adicionales: str = None) -> dict:
    import requests
    import pytz

    if not hora:
        return {
            "exito": False,
            "error": "Se requiere una hora específica"
        }

    # 🔥 FORMATEAR TELÉFONO: agregar '+' si no tiene
    if cliente_telefono:
        cliente_telefono = str(cliente_telefono).strip()
        if not cliente_telefono.startswith("+"):
            cliente_telefono = f"+{cliente_telefono}"
    else:
        cliente_telefono = None

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

    data = {
        "start": hora_utc.isoformat(),
        "eventTypeId": event_type_id,
        "attendee": {
            "name": cliente_nombre,
            "email": cliente_email,
            "timeZone": "America/Guayaquil"
        },
        "bookingFieldsResponses": {
            "cedula": cliente_cedula
        }
    }

    # 🔥 AGREGAR NOTAS ADICIONALES SI EXISTEN
    if notas_adicionales:
        data["bookingFieldsResponses"]["notes"] = notas_adicionales

    # 🔥 AGREGAR TELÉFONO SI EXISTE
    if cliente_telefono:
        data["attendee"]["phoneNumber"] = cliente_telefono

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
    
def obtener_citas_cliente_por_cedula(cedula: str, event_type_id: int = None) -> dict:

    url = "https://api.cal.com/v2/bookings"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "cal-api-version": "2024-08-13"
    }
    params = {
        "status": "upcoming",
        "take": 250
    }
    
    # Solo agregar eventTypeId si se proporcionó
    if event_type_id is not None:
        params["eventTypeId"] = event_type_id

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"exito": False, "error": f"Error {response.status_code}", "detalles": response.text}

        data = response.json()
        # La respuesta puede ser {"data": [...]} o directamente una lista
        if isinstance(data, dict) and "data" in data:
            bookings = data["data"]
            if isinstance(bookings, dict) and "bookings" in bookings:
                bookings = bookings["bookings"]
            elif isinstance(bookings, list):
                bookings = bookings
            else:
                bookings = []
        elif isinstance(data, list):
            bookings = data
        else:
            bookings = []

        citas = []
        ahora = datetime.now(pytz.utc)
        ecuador = pytz.timezone("America/Guayaquil")

        for booking in bookings:
            if not isinstance(booking, dict):
                continue
            
            # Buscar cédula en attendees[0].bookingFieldsResponses
            attendees = booking.get("attendees", [])
            if attendees:
                booking_fields = attendees[0].get("bookingFieldsResponses", {})
                cedula_booking = str(booking_fields.get("cedula", "")).strip()
            else:
                # Si no hay attendees, buscar en responses
                responses = booking.get("responses", {}) or booking.get("bookingFieldsResponses", {})
                cedula_booking = str(responses.get("cedula") or responses.get("Cédula") or "").strip()
            
            if not cedula_booking or cedula_booking != str(cedula).strip():
                continue

            fecha_str = booking.get("startTime") or booking.get("start")
            if not fecha_str:
                continue

            try:
                fecha_utc = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
                if fecha_utc.tzinfo is None:
                    fecha_utc = pytz.utc.localize(fecha_utc)
                fecha_local = fecha_utc.astimezone(ecuador)
            except:
                continue

            telefono = None
            notas = None
            if attendees:
                booking_fields = attendees[0].get("bookingFieldsResponses", {})
                telefono = booking_fields.get("attendeePhoneNumber") or attendees[0].get("phoneNumber")
                notas = booking_fields.get("notes")
            if not notas:
                responses = booking.get("responses", {}) or booking.get("bookingFieldsResponses", {})
                notas = responses.get("notes")

            if fecha_utc >= ahora and booking.get("status") != "CANCELLED":
                citas.append({
                    "booking_id": booking.get("id"),
                    "uid": booking.get("uid"),
                    "fecha": fecha_local.isoformat(),
                    "estado": booking.get("status"),
                    "event_type_id": booking.get("eventTypeId") or booking.get("eventType", {}).get("id"),
                    "cedula": cedula_booking,
                    "telefono": telefono,
                    "notas": notas,
                    "asistentes": attendees
                })

        return {"exito": True, "citas": citas}
    except Exception as e:
        return {"exito": False, "error": str(e)}

def eliminar_cita(booking_id: int, event_type_id: int) -> dict:
    import requests

    # 1. Obtener todas las citas para encontrar el UID
    url_list = f"https://api.cal.com/v2/bookings?eventTypeId={event_type_id}"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13"
    }

    try:
        response = requests.get(url_list, headers=headers, timeout=10)

        if response.status_code != 200:
            return {
                "exito": False,
                "error": f"Error al obtener citas: {response.status_code}",
                "detalles": response.text
            }

        data = response.json()
        # Manejar diferentes estructuras de respuesta
        if isinstance(data, dict) and "data" in data:
            bookings_data = data["data"]
            if isinstance(bookings_data, dict) and "bookings" in bookings_data:
                bookings = bookings_data["bookings"]
            elif isinstance(bookings_data, list):
                bookings = bookings_data
            else:
                bookings = []
        elif isinstance(data, list):
            bookings = data
        else:
            bookings = []

        # 2. Buscar el booking por ID
        booking_uid = None
        for booking in bookings:
            if booking.get("id") == booking_id:
                booking_uid = booking.get("uid")
                break

        if not booking_uid:
            return {
                "exito": False,
                "error": "No se encontró la cita con ese booking_id"
            }

        # 3. Cancelar usando UID (v2)
        url_cancel = f"https://api.cal.com/v2/bookings/{booking_uid}/cancel"
        headers_cancel = {
            "Authorization": f"Bearer {CALCOM_API_KEY}",
            "Content-Type": "application/json",
            "cal-api-version": "2024-08-13"
        }

        data_cancel = {
            "cancellationReason": "Cancelado desde sistema"
        }

        response_cancel = requests.post(
            url_cancel, headers=headers_cancel, json=data_cancel, timeout=10
        )

        print(f"🔍 RESPUESTA DE CAL.COM AL ELIMINAR: {response_cancel.status_code} - {response_cancel.text}")

        if response_cancel.status_code in [200, 204]:
            return {"exito": True}
        else:
            return {
                "exito": False,
                "error": f"Error {response_cancel.status_code}",
                "detalles": response_cancel.text
            }

    except Exception as e:
        return {
            "exito": False,
            "error": str(e)
        }

def reagendar_cita(booking_id: int, event_type_id: int, cliente_nombre: str, cliente_email: str, cliente_cedula: str, cliente_telefono: str, nueva_fecha: str, nueva_hora: str) -> dict:
    """
    Reagenda una cita: verifica disponibilidad, cancela la original y crea una nueva.
    
    Args:
        booking_id: ID de la cita original
        event_type_id: ID del tipo de evento
        cliente_nombre: Nombre del cliente
        cliente_email: Email del cliente
        cliente_cedula: Cédula del cliente
        cliente_telefono: Teléfono del cliente
        nueva_fecha: Nueva fecha en formato 'YYYY-MM-DD'
        nueva_hora: Nueva hora en formato 'HH:MM'
    
    Returns:
        dict: Resultado de la operación
    """
    
    # 🔥 OBTENER NOTAS DE LA CITA ORIGINAL ANTES DE CANCELARLA
    notas_originales = None
    try:
        url_list = f"https://api.cal.com/v2/bookings?eventTypeId={event_type_id}"
        headers = {"Authorization": f"Bearer {CALCOM_API_KEY}"}
        response = requests.get(url_list, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            bookings = data.get("data", {}).get("bookings", [])
            for booking in bookings:
                if booking.get("id") == booking_id:
                    # Buscar notas en responses o bookingFieldsResponses
                    responses = booking.get("responses", {})
                    notas_originales = responses.get("notes")
                    if not notas_originales:
                        booking_fields = booking.get("bookingFieldsResponses", {})
                        notas_originales = booking_fields.get("notes")
                    break
    except Exception as e:
        print(f"⚠️ Error al obtener notas originales: {e}")
    
    # 1. Verificar disponibilidad de la nueva fecha/hora
    ecuador = pytz.timezone("America/Guayaquil")
    
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
    
    # 4. Agendar la nueva cita (incluyendo cédula, teléfono y notas)
    resultado_agendar = agendar_cita(
        event_type_id=event_type_id,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        cliente_cedula=cliente_cedula,
        cliente_telefono=cliente_telefono,
        hora=nueva_hora_dt,
        notas_adicionales=notas_originales  # 🔥 PASAR LAS NOTAS
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