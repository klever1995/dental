import os
import sys
from dotenv import load_dotenv

# ==============================
# CONFIGURACIÓN INICIAL
# ==============================

# Ruta base del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar variables de entorno (.env)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Agregar backend al path
sys.path.append(os.path.join(BASE_DIR, "backend"))

# Importar función
from app.services.calcom import obtener_citas_cliente_por_cedula2


# ==============================
# FUNCIÓN DE PRUEBA
# ==============================

def probar_obtener_todas_las_citas():
    print("🔍 PROBANDO OBTENER TODAS LAS CITAS (SIN FILTRAR POR CÉDULA)")
    print("=" * 60)

    # Llamar a la función sin pasar cédula (None) para obtener todas las citas
    resultado = obtener_citas_cliente_por_cedula2(None)  # 🔥 MODIFICADO: None = todas las citas

    print("\n📋 RESULTADO:")
    print(f"   Éxito: {resultado.get('exito')}")
    print(f"   Total citas encontradas: {len(resultado.get('citas', []))}")

    if resultado.get("exito"):
        citas = resultado.get("citas", [])

        if len(citas) == 0:
            print("\n⚠️ No se encontraron citas futuras agendadas")
            return

        print(f"\n📅 Se encontraron {len(citas)} cita(s) futura(s):\n")
        print("=" * 70)

        for i, cita in enumerate(citas, 1):
            print(f"\n📍 CITA {i}:")
            print(f"   🆔 Booking ID: {cita.get('booking_id')}")
            print(f"   🔖 UID: {cita.get('uid')}")
            print(f"   📅 Fecha: {cita.get('fecha')}")
            print(f"   📌 Estado: {cita.get('estado')}")
            print(f"   🆔 Cédula: {cita.get('cedula')}")
            print(f"   📝 Notas: {cita.get('notas') or '—'}")
            
            # 🔥 MOSTRAR ESPECIALIDAD
            especialidad = cita.get('especialidad')
            if especialidad:
                print(f"   🩺 ESPECIALIDAD: {especialidad.upper()} ✅")
            else:
                print(f"   🩺 ESPECIALIDAD: NO REGISTRADA ⚠️")
            
            # Mostrar asistentes
            asistentes = cita.get("asistentes", [])
            if asistentes:
                print(f"   👥 Asistentes: {len(asistentes)} asistente(s)")
                for j, asistente in enumerate(asistentes):
                    print(f"      Asistente {j+1}: {asistente.get('name')} - {asistente.get('email')}")
                    if asistente.get('bookingFieldsResponses'):
                        cedula_asistente = asistente['bookingFieldsResponses'].get('cedula', 'No tiene')
                        print(f"         Cédula en asistente: {cedula_asistente}")
            print()

    else:
        print(f"\n❌ Error en la consulta: {resultado.get('error')}")
        if resultado.get('detalles'):
            print(f"   Detalles: {resultado['detalles']}")


# ==============================
# EJECUCIÓN
# ==============================

if __name__ == "__main__":
    print("\n🚀 INICIANDO PRUEBA DE OBTENCIÓN DE TODAS LAS CITAS")
    print("=" * 60)
    probar_obtener_todas_las_citas()
    print("\n🏁 Prueba finalizada")