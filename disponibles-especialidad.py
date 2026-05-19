import os
import sys
import requests
import json
from dotenv import load_dotenv
from datetime import datetime

# ============================================
# AGREGAR BACKEND AL PATH
# ============================================
sys.path.append(
    r"C:\Users\Klever\Desktop\dental\dental\backend"
)

# ============================================
# IMPORTAR MÉTODO
# ============================================
from app.services.calcom import (
    obtener_slots_disponibles
)

# ============================================
# CARGAR VARIABLES
# ============================================
load_dotenv(
    r"C:\Users\Klever\Desktop\dental\.env"
)

# ============================================
# CONFIG
# ============================================
EVENT_TYPE_ID = 1288606
SEATS_PER_SLOT = 5
CUPOS_POR_ESPECIALIDAD = 1
CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")

# ============================================
# FUNCIÓN DE DEPURACIÓN: VER BOOKINGS FUTUROS
# ============================================
def depurar_bookings():
    print("\n" + "=" * 60)
    print("🔍 DEPURACIÓN: CONSULTANDO BOOKINGS FUTUROS")
    print("=" * 60)
    
    url = "https://api.cal.com/v2/bookings"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "cal-api-version": "2024-08-13"
    }
    params = {
        "eventTypeId": EVENT_TYPE_ID,
        "status": "upcoming",
        "take": 250
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            bookings = []
            if isinstance(data, dict) and "data" in data:
                bookings = data["data"]
            elif isinstance(data, list):
                bookings = data
            
            print(f"✅ Se encontraron {len(bookings)} bookings futuros")
            
            for i, booking in enumerate(bookings[:5], 1):  # Mostrar primeros 5
                print(f"\n📌 Booking {i}:")
                print(f"   ID: {booking.get('id')}")
                print(f"   UID: {booking.get('uid')}")
                print(f"   Start: {booking.get('startTime')}")
                print(f"   Status: {booking.get('status')}")
                
                # Extraer especialidad
                attendees = booking.get("attendees", [])
                if attendees:
                    metadata = attendees[0].get("metadata", {})
                    especialidad = metadata.get("especialidad")
                    booking_fields = attendees[0].get("bookingFieldsResponses", {})
                    cedula = booking_fields.get("cedula")
                    print(f"   Especialidad: {especialidad}")
                    print(f"   Cédula: {cedula}")
                else:
                    # Buscar en metadata del booking
                    metadata = booking.get("metadata", {})
                    especialidad = metadata.get("especialidad")
                    print(f"   Especialidad (booking): {especialidad}")
            
            if len(bookings) > 5:
                print(f"\n... y {len(bookings) - 5} bookings más")
        else:
            print(f"❌ Error al consultar bookings: {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Error en depuración: {e}")

# ============================================
# MOSTRAR SLOTS
# ============================================
def mostrar_slots(resultado):

    print("\n" + "=" * 60)

    if not resultado.get("exito"):

        print(
            f"❌ ERROR: {resultado.get('mensaje')}"
        )

        print("=" * 60)

        return

    print("✅ CONSULTA EXITOSA")

    print("=" * 60)

    slots = resultado.get(
        "slots_por_fecha",
        {}
    )

    if not slots:

        print("⚠️ No se encontraron slots")

        return

    for fecha, horas in slots.items():

        print(f"\n📅 FECHA: {fecha}")

        print("-" * 40)

        for slot in horas:

            hora = slot.get("hora", "N/A")
            attendees_count = slot.get("attendeesCount", 0)
            booking_uid = slot.get("bookingUid")
            cupos_libres_especialidad = slot.get("cupos_libres_especialidad")

            cupos_libres = SEATS_PER_SLOT - attendees_count

            print(f"🕐 {hora} | Ocupados total: {attendees_count} | Cupos libres total: {cupos_libres}")

            if cupos_libres_especialidad is not None:
                print(f"   🩺 Cupos libres para esta especialidad: {cupos_libres_especialidad}")

            if booking_uid:
                print(f"   📌 Booking UID del slot ocupado: {booking_uid}")
            else:
                print(f"   📌 Slot completamente libre")

# ============================================
# PROBAR MÉTODO
# ============================================
def probar_slots():

    print(
        "\n🚀 PROBANDO obtener_slots_disponibles (CON SEATS Y ESPECIALIDAD)"
    )

    print(
        f"📌 EVENT TYPE ID: {EVENT_TYPE_ID}"
    )
    
    print(f"📌 Plazas por horario: {SEATS_PER_SLOT}")
    print(f"🩺 Cupos máximos por especialidad por horario: {CUPOS_POR_ESPECIALIDAD}")

    # ========================================
    # PRUEBA 1 - Sin filtrar por especialidad
    # ========================================
    print(
        "\n\n🔍 PRUEBA 1 - Próximos 3 días (SIN filtrar por especialidad)"
    )

    resultado = obtener_slots_disponibles(
        event_type_id=EVENT_TYPE_ID,
        dias_a_mostrar=3
    )

    mostrar_slots(resultado)

    # ========================================
    # PRUEBA 2 - Filtrando por odontologia
    # ========================================
    print(
        "\n\n🔍 PRUEBA 2 - Próximos 3 días (SOLO odontologia)"
    )

    resultado = obtener_slots_disponibles(
        event_type_id=EVENT_TYPE_ID,
        dias_a_mostrar=3,
        especialidad="odontologia",
        cupos_por_especialidad=CUPOS_POR_ESPECIALIDAD
    )

    mostrar_slots(resultado)

    # ========================================
    # PRUEBA 3 - Fecha específica con pediatria
    # ========================================
    print(
        "\n\n🔍 PRUEBA 3 - Fecha específica 2026-05-11 (SOLO pediatria)"
    )

    resultado = obtener_slots_disponibles(
        event_type_id=EVENT_TYPE_ID,
        fecha_inicio="2026-05-11",
        especialidad="pediatria",
        cupos_por_especialidad=CUPOS_POR_ESPECIALIDAD
    )

    mostrar_slots(resultado)

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    # Primero depurar: ver qué bookings futuros existen
    depurar_bookings()
    
    # Luego probar slots
    probar_slots()