import datetime
from app.services.calcom import obtener_slots_disponibles

async def manejar_horarios(fecha: str, especialidad: str = None) -> str:
    slots_resultado = obtener_slots_disponibles(
        event_type_id=1288606, 
        fecha_inicio=fecha, 
        dias_a_mostrar=1,
        especialidad=especialidad,  # 🔥 NUEVO: filtrar por especialidad
        cupos_por_especialidad=1     # 🔥 NUEVO: solo una cita por especialidad por hora
    )
    
    if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
        slots_dia = slots_resultado["slots_por_fecha"].get(fecha, [])
        if slots_dia:
            # Extraer horas (pueden ser strings o diccionarios)
            horas = []
            for slot in slots_dia:
                if isinstance(slot, dict):
                    horas.append(slot.get("hora"))
                else:
                    horas.append(slot)
            
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
            especialidad_texto = f" para {especialidad}" if especialidad else ""
            return f"Para el {fecha_legible}{especialidad_texto} tenemos los siguientes horarios: {', '.join(horas)}. ¿Cuál te interesa?"
        else:
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
            especialidad_texto = f" para {especialidad}" if especialidad else ""
            return f"No hay horarios disponibles{fecha_legible}{especialidad_texto}. ¿Otra fecha?"
    else:
        return "No encontré horarios para esa fecha. ¿Otra fecha?"   