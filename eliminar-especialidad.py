import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(r"C:\Users\Klever\Desktop\dental\dental\.env")

# Agregar el directorio backend al path
sys.path.append(r"C:\Users\Klever\Desktop\dental\dental\backend")

# Importar funciones
from app.services.calcom import eliminar_cita, obtener_citas_cliente_por_cedula

def probar_eliminar_cita_por_cedula():
    print("🔍 PROBANDO ELIMINAR CITA POR CÉDULA (CON SEATS)")
    print("="*60)
    
    # Usar la cédula de la cita que agendaste con especialidad
    cedula = "9876543210"
    print(f"🆔 Consultando citas para cédula: {cedula}")
    
    citas_resultado = obtener_citas_cliente_por_cedula(cedula)
    
    if not citas_resultado.get("exito"):
        print(f"❌ Error al obtener citas: {citas_resultado.get('error')}")
        return
    
    citas = citas_resultado.get("citas", [])
    if not citas:
        print("❌ No tienes citas futuras para cancelar")
        print("   Nota: Solo se muestran citas con fecha posterior a hoy")
        return
    
    print(f"\n📋 Tus citas actuales (por cédula {cedula}):")
    for i, cita in enumerate(citas, 1):
        # Extraer uid desde la cita (ahora está disponible en la respuesta)
        booking_uid = cita.get("uid")
        booking_id = cita.get("booking_id")
        fecha = cita.get("fecha")
        especialidad = cita.get("especialidad", "No especificada")
        print(f"{i}. UID: {booking_uid} | ID: {booking_id} | Fecha: {fecha} | Especialidad: {especialidad}")
    
    # Seleccionar la cita a eliminar
    try:
        seleccion = int(input("\nNúmero de la cita a eliminar: ")) - 1
        if seleccion < 0 or seleccion >= len(citas):
            print("❌ Selección inválida")
            return
        cita_seleccionada = citas[seleccion]
        booking_uid = cita_seleccionada.get("uid")
        booking_id = cita_seleccionada.get("booking_id")
        print(f"✅ Cita seleccionada: UID {booking_uid} (ID {booking_id}) - Fecha: {cita_seleccionada['fecha']}")
    except ValueError:
        print("❌ Debes ingresar un número")
        return
    
    confirmacion = input(f"¿Estás seguro de que quieres eliminar esta cita? (s/n): ").strip().lower()
    
    if confirmacion != 's':
        print("❌ Cancelación abortada")
        return
    
    print(f"\n⏳ Eliminando cita con UID {booking_uid}...")
    resultado = eliminar_cita(booking_uid)  # 🔥 Ahora pasamos el UID, no el ID numérico
    
    if resultado.get("exito"):
        print(f"✅ ¡Cita {booking_uid} eliminada exitosamente!")
        # Verificar que la cita ya no aparece
        print("\n🔍 Verificando que la cita ya no existe...")
        citas_restantes = obtener_citas_cliente_por_cedula(cedula)
        if citas_restantes.get("exito"):
            restantes = len(citas_restantes.get("citas", []))
            print(f"📋 Ahora tienes {restantes} cita(s) futura(s) para esta cédula.")
    else:
        print(f"❌ Error al eliminar: {resultado.get('error')}")
        if resultado.get("detalles"):
            print(f"Detalles: {resultado['detalles']}")

if __name__ == "__main__":
    probar_eliminar_cita_por_cedula()