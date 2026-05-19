import os
import requests
import json
from dotenv import load_dotenv

# ==========================================
# CARGAR VARIABLES
# ==========================================
load_dotenv()

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")

# ==========================================
# CREAR EVENTO
# ==========================================
def crear_evento():
    url = "https://api.cal.com/v2/event-types"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-06-14"
    }

    # ==========================================
    # PAYLOAD CON LOS CAMPOS EXACTOS DE LA PLANTILLA
    # ==========================================
    payload = {
        "title": "Pediatria",  # Cambia según la especialidad
        "slug": "pediatria",   # Cambia según la especialidad
        "lengthInMinutes": 60,
        "description": "Consultas pediátricas",  # Cambia según la especialidad
        "locations": [
            {
                "type": "address",
                "address": "https://maps.app.goo.gl/TWmaZKTjFWNtHJFJ6",
                "public": False
            }
        ],
        "bookingFields": [
            {
                "isDefault": True,
                "type": "name",
                "slug": "name",
                "required": True,
                "disableOnPrefill": False
            },
            {
                "isDefault": False,
                "type": "text",
                "slug": "cedula",
                "label": "Cédula",
                "required": True,
                "placeholder": "Ingresa tu número de cédula",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "email",
                "slug": "email",
                "required": True,
                "label": "",
                "placeholder": "",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "phone",
                "slug": "attendeePhoneNumber",
                "required": True,
                "label": "Teléfono",
                "placeholder": "Ingresa tu número",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "radioInput",
                "slug": "location",
                "required": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "text",
                "slug": "title",
                "required": True,
                "disableOnPrefill": False,
                "hidden": True
            },
            {
                "isDefault": True,
                "type": "textarea",
                "slug": "notes",
                "required": False,
                "label": "",
                "placeholder": "",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "multiemail",
                "slug": "guests",
                "required": False,
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "textarea",
                "slug": "rescheduleReason",
                "required": False,
                "disableOnPrefill": False,
                "hidden": False
            }
        ],
        "disableGuests": False,
        "minimumBookingNotice": 120,
        "seats": {
            "disabled": True
        }
    }

    print("\n🚀 CREANDO EVENTO...")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        print("\n📡 STATUS:", response.status_code)
        print("\n📡 RESPONSE:")
        print(response.text)

        if response.status_code not in [200, 201]:
            print("\n❌ ERROR CREANDO EVENTO")
            return

        data = response.json()
        evento = data.get("data", {})

        print("\n===================================")
        print("✅ EVENTO CREADO")
        print("===================================\n")
        print("🆔 ID:", evento.get("id"))
        print("📌 TITLE:", evento.get("title"))
        print("🔗 SLUG:", evento.get("slug"))
        print("⏱️ DURACIÓN:", evento.get("lengthInMinutes"))
        print("\n🌐 BOOKING URL:", evento.get("bookingUrl"))

    except Exception as e:
        print("\n❌ EXCEPCIÓN:", str(e))

if __name__ == "__main__":
    crear_evento()