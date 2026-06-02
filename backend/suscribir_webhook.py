import os
import sys
import time
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Cargar variables de entorno
load_dotenv()

# CAMBIA ESTA URL POR TU URL PÚBLICA DE NGROK O DOMINIO - USANDO LA URL CORRECTA DEL BACKEND (PUERTO 8001)
WEBHOOK_URL = "https://8821-191-99-12-8.ngrok-free.app/api/v1/citas/webhook/google"

# DATABASE_URL - CORREGIDO EL PUERTO A 5433
DATABASE_URL = "postgresql://admin:admin123@localhost:5433/dental_db"

def suscribir_calendario(service, calendar_id: str, especialidad_id: int):
    """Suscribe un calendario al webhook y guarda en BD"""
    timestamp = int(time.time())
    clean_suffix = calendar_id.replace('@', '_').replace('.', '_')[-20:]
    channel_id = f"webhook_{especialidad_id}_{clean_suffix}_{timestamp}"
    
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": WEBHOOK_URL,
        "params": {"ttl": "604800"}  # 7 días
    }
    
    result = service.events().watch(calendarId=calendar_id, body=body).execute()
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO suscripciones_webhook 
        (especialidad_id, channel_id, resource_id, expiration, activa)
        VALUES (%s, %s, %s, %s, %s)
    """, (especialidad_id, result.get("id"), result.get("resourceId"), 
          int(result.get("expiration")), True))
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"✅ Suscrito: {calendar_id}")
    print(f"   Channel ID: {result.get('id')}")
    print(f"   Resource ID: {result.get('resourceId')}")
    print(f"   Expira: {datetime.fromtimestamp(int(result.get('expiration'))/1000)}")
    return result

def main():
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"❌ No se encuentra: {SERVICE_ACCOUNT_FILE}")
        return
    
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, calendar_id FROM especialidades WHERE activa = true AND calendar_id IS NOT NULL")
    especialidades = cur.fetchall()
    cur.close()
    conn.close()
    
    if not especialidades:
        print("❌ No hay especialidades con calendar_id")
        return
    
    print(f"📋 Suscribiendo {len(especialidades)} calendarios...")
    for esp in especialidades:
        suscribir_calendario(service, esp['calendar_id'], esp['id'])

if __name__ == "__main__":
    main()