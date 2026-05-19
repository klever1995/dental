import os
import sys
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Agregar el directorio backend al path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

# Cargar variables de entorno
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Importar funciones
from app.services.calcom import obtener_slots_disponibles, agendar_cita

def agendar_nueva_cita():
    print("🚀 AGENDANDO NUEVA CITA CON CÉDULA, NOTAS Y ESPECIALIDAD")
    
    EVENT_TYPE_ID = 1288606
    paciente_nombre = "Segundo Paciente"
    paciente_email = "segundo@test.com"
    paciente_cedula = "9876543210"
    paciente_telefono = "+593987654321"
    paciente_notas = "El paciente solicita limpieza dental y revisión de caries. Prefiere cita por la mañana."
    paciente_especialidad = "odontologia"
    
    # Fecha específica
    fecha_objetivo = "2026-05-12"
    
    # Obtener slots para esa fecha
    slots = obtener_slots_disponibles(event_type_id=EVENT_TYPE_ID, fecha_inicio=fecha_objetivo, dias_a_mostrar=1)
    if not slots["exito"] or not slots["slots_por_fecha"]:
        print(f"❌ No hay slots disponibles para {fecha_objetivo}")
        return
    
    # Tomar el primer horario disponible de ese día
    primer_slot = slots["slots_por_fecha"][fecha_objetivo][0]
    
    # 🔥 CORRECCIÓN: si es diccionario, extraer 'hora'; si es string, usarlo directamente
    if isinstance(primer_slot, dict):
        primera_hora = primer_slot.get("hora")
    else:
        primera_hora = primer_slot
    
    # Crear datetime
    ecuador = pytz.timezone("America/Guayaquil")
    año, mes, dia = map(int, fecha_objetivo.split('-'))
    hora, minuto = map(int, primera_hora.split(':'))
    fecha_hora = ecuador.localize(datetime(año, mes, dia, hora, minuto))
    
    print(f"📅 Slot: {fecha_objetivo} {primera_hora}")
    print(f"👤 Nombre: {paciente_nombre}")
    print(f"📧 Email: {paciente_email}")
    print(f"🆔 Cédula: {paciente_cedula}")
    print(f"📞 Teléfono: {paciente_telefono}")
    print(f"📝 Notas: {paciente_notas}")
    print(f"🩺 Especialidad: {paciente_especialidad}")
    
    # Agendar con especialidad
    resultado = agendar_cita(
        event_type_id=EVENT_TYPE_ID,
        cliente_nombre=paciente_nombre,
        cliente_email=paciente_email,
        cliente_cedula=paciente_cedula,
        cliente_telefono=paciente_telefono,
        hora=fecha_hora,
        notas_adicionales=paciente_notas,
        especialidad=paciente_especialidad
    )
    
    if resultado["exito"]:
        datos = resultado["data"]["data"]
        print(f"\n✅ CITA AGENDADA: ID {datos.get('id')} | UID {datos.get('uid')}")
        print("📝 bookingFieldsResponses:", datos.get("bookingFieldsResponses", {}))
        if datos.get("bookingFieldsResponses", {}).get("notes"):
            print(f"📝 Notas guardadas: {datos['bookingFieldsResponses']['notes']}")
        if datos.get("metadata", {}).get("especialidad"):
            print(f"🩺 Especialidad guardada en metadata: {datos['metadata']['especialidad']}")
    else:
        print(f"\n❌ ERROR: {resultado.get('error')}")
        print(f"Detalles: {resultado.get('detalles')}")

if __name__ == "__main__":
    agendar_nueva_cita()