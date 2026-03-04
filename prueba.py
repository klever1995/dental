import os
from openai import AzureOpenAI

# Crear cliente Azure OpenAI usando variables del .env
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("OPENAI_API_VERSION"),
)

try:
    print("🔎 Probando deployment de transcripción...")

    # Solo hacemos una llamada mínima para ver si el deployment existe
    response = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",  # EXACTAMENTE como aparece en Azure
        file=open("audio_prueba.ogg", "rb")  # pon aquí cualquier audio pequeño de prueba
    )

    print("✅ ÉXITO")
    print("Texto transcrito:", response.text)

except Exception as e:
    print("❌ ERROR DETECTADO:")
    print(str(e))