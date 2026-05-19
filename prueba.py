import os
import requests
from dotenv import load_dotenv

# ==========================================
# CARGAR .ENV
# ==========================================
load_dotenv()

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")

# ==========================================
# VALIDAR API KEY
# ==========================================
if not CALCOM_API_KEY:

    print("❌ CALCOM_API_KEY no encontrada")
    exit()

# ==========================================
# ENDPOINT OFICIAL V2
# ==========================================
url = "https://api.cal.com/v2/event-types"

# ==========================================
# HEADERS
# ==========================================
headers = {
    "Authorization": f"Bearer {CALCOM_API_KEY}",
    "cal-api-version": "2024-06-14",
    "Content-Type": "application/json"
}

# ==========================================
# PARAMS
# ==========================================
params = {
    "limit": 100
}

try:

    print("\n🚀 CONSULTANDO EVENT TYPES...")
    print("URL:", url)

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=20
    )

    print("\n📡 STATUS:", response.status_code)

    print("\n📡 RESPONSE:")
    print(response.text)

    # ==========================================
    # ERROR
    # ==========================================
    if response.status_code != 200:

        print("\n❌ ERROR CONSULTANDO EVENT TYPES")
        exit()

    # ==========================================
    # JSON
    # ==========================================
    data = response.json()

    eventos = data.get(
        "data",
        []
    )

    # ==========================================
    # MOSTRAR EVENTOS
    # ==========================================
    print("\n===================================")
    print("✅ EVENTOS ENCONTRADOS")
    print("===================================\n")

    if not eventos:

        print("⚠️ No se encontraron eventos")
        exit()

    for evento in eventos:

        print(f"🆔 ID: {evento.get('id')}")

        print(
            f"📌 TÍTULO: "
            f"{evento.get('title')}"
        )

        print(
            f"🔗 SLUG: "
            f"{evento.get('slug')}"
        )

        print(
            f"⏱️ DURACIÓN: "
            f"{evento.get('length')} min"
        )

        print(
            f"📝 DESCRIPCIÓN: "
            f"{evento.get('description')}"
        )

        print(
            f"🎨 COLOR: "
            f"{evento.get('color')}"
        )

        print("-" * 50)

except Exception as e:

    print("\n❌ EXCEPCIÓN:")
    print(str(e))