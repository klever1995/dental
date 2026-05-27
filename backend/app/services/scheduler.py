# ==============================
# Servicio Scheduler para webhooks de Google Calendar
# Renueva automáticamente las suscripciones antes de que expiren (cada 24 horas)
# ==============================
import os
import time
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from app.db.base import SessionLocal
from app.models.suscripcion_webhook import SuscripcionWebhook
from app.models.especialidad import Especialidad

TIMEZONE = "America/Guayaquil"

# ==============================
# Renovar suscripciones a punto de expirar (menos de 24 horas restantes)
# ==============================
def renovar_suscripciones():
    db = SessionLocal()
    expiracion_limite = (datetime.now(pytz.utc).timestamp() * 1000) + (24 * 60 * 60 * 1000)
    suscripciones = db.query(SuscripcionWebhook).filter(
        SuscripcionWebhook.activa == True,
        SuscripcionWebhook.expiration < expiracion_limite
    ).all()
    
    if not suscripciones:
        db.close()
        return
    
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://efe3-191-99-12-8.ngrok-free.app/api/v1/citas/webhook/google")
    
    for sub in suscripciones:
        try:
            esp = db.query(Especialidad).filter(Especialidad.id == sub.especialidad_id).first()
            if not esp or not esp.calendar_id:
                continue
            
            timestamp = int(time.time())
            clean_suffix = esp.calendar_id.replace('@', '_').replace('.', '_')[-20:]
            new_channel_id = f"webhook_{esp.id}_{clean_suffix}_{timestamp}"
            
            body = {
                "id": new_channel_id,
                "type": "web_hook",
                "address": WEBHOOK_URL,
                "params": {"ttl": "604800"}
            }
            
            result = service.events().watch(calendarId=esp.calendar_id, body=body).execute()
            
            try:
                service.channels().stop(body={
                    "id": sub.channel_id,
                    "resourceId": sub.resource_id
                }).execute()
            except:
                pass
            
            sub.channel_id = result.get("id")
            sub.resource_id = result.get("resourceId")
            sub.expiration = int(result.get("expiration"))
            db.commit()
            print(f"✅ Renovado: {esp.calendar_id}")
        except Exception as e:
            print(f"❌ Error renovando {sub.id}: {e}")
    db.close()

# ==============================
# Iniciar el scheduler de fondo con ejecución cada 24 horas
# ==============================
def start_scheduler():
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(renovar_suscripciones, trigger=IntervalTrigger(hours=24), id='renovar_webhooks', replace_existing=True)
    renovar_suscripciones()
    scheduler.start()
    print("✅ Scheduler iniciado")