import os
import sys
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(r"C:\Users\Klever\Desktop\dental\dental\.env")

# Agregar el directorio backend al path
sys.path.append(r"C:\Users\Klever\Desktop\dental\dental\backend")

# Importar funciones
from app.services.calcom import obtener_citas_cliente_por_cedula, reagendar_cita

def probar_reagendar_simple():
    print("🔍 PROBANDO REAGENDAMIENTO SIMPLE")
    print("="*50)
    
    cedula = "9876543210"
    EVENT_TYPE_ID = 1288606
    
    # 1. Obtener la cita con especialidad (la última)
    print(f"📋 Obteniendo citas para cédula {cedula}...")
    citas_resultado = obtener_citas_cliente_por_cedula(cedula)
    if not citas_resultado.get("exito"):
        print(f"❌ Error: {citas_resultado.get('error')}")
        return
    
    citas = citas_resultado.get("citas", [])
    # Filtrar la cita que tiene especialidad
    cita_especialidad = None
    for cita in citas:
        if cita.get("especialidad"):
            cita_especialidad = cita
            break
    
    if not cita_especialidad:
        print("❌ No hay citas con especialidad para reagendar")
        print("   Primero agenda una cita con especialidad usando agendar-especialidad.py")
        return
    
    booking_uid = cita_especialidad.get("uid")
    print(f"✅ Cita seleccionada: UID {booking_uid}")
    print(f"   📅 Fecha actual: {cita_especialidad.get('fecha')}")
    print(f"   🩺 Especialidad: {cita_especialidad.get('especialidad')}")
    
    # 2. Calcular nueva fecha (un día después)
    fecha_actual_str = cita_especialidad.get("fecha")
    # Extraer solo la fecha (sin hora)
    fecha_actual = datetime.fromisoformat(fecha_actual_str.replace('Z', '+00:00'))
    fecha_nueva = (fecha_actual + timedelta(days=1)).strftime("%Y-%m-%d")
    hora_nueva = "11:00"  # Hora fija para probar
    
    print(f"\n📋 Reagendando a: {fecha_nueva} a las {hora_nueva}")
    
    # 3. Obtener datos del cliente
    asistentes = cita_especialidad.get("asistentes", [])
    if asistentes:
        primer_asistente = asistentes[0]
        cliente_nombre = primer_asistente.get("name", "Cliente")
        cliente_email = primer_asistente.get("email", "")
        cliente_telefono = primer_asistente.get("phoneNumber")
        if not cliente_telefono:
            booking_fields = primer_asistente.get("bookingFieldsResponses", {})
            cliente_telefono = booking_fields.get("attendeePhoneNumber")
    else:
        cliente_nombre = "Cliente"
        cliente_email = "cliente@test.com"
        cliente_telefono = None
    
    cliente_cedula = cita_especialidad.get("cedula", cedula)
    
    # 4. Reagendar
    print("\n⏳ Ejecutando reagendamiento...")
    resultado = reagendar_cita(
        booking_uid=booking_uid,
        event_type_id=EVENT_TYPE_ID,
        cliente_nombre=cliente_nombre,
        cliente_email=cliente_email,
        cliente_cedula=cliente_cedula,
        cliente_telefono=cliente_telefono,
        nueva_fecha=fecha_nueva,
        nueva_hora=hora_nueva
    )
    
    if resultado.get("exito"):
        print(f"\n✅ REAGENDAMIENTO EXITOSO")
        print(f"   {resultado.get('mensaje')}")
    else:
        print(f"\n❌ Error: {resultado.get('error')}")
        if resultado.get("horarios_disponibles"):
            print(f"   Horarios disponibles: {resultado['horarios_disponibles']}")

if __name__ == "__main__":
    probar_reagendar_simple()