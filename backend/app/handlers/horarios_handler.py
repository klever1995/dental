import datetime
from app.services.calcom import obtener_slots_disponibles

async def manejar_horarios(fecha: str) -> str:
    slots_resultado = obtener_slots_disponibles(event_type_id=1288606, fecha_inicio=fecha, dias_a_mostrar=1)
    if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
        horas = slots_resultado["slots_por_fecha"].get(fecha, [])
        if horas:
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
            return f"Para el {fecha_legible} tenemos los siguientes horarios: {', '.join(horas)}. ¿Cuál te interesa?"
        else:
            return f"No hay horarios para {fecha_legible}. ¿Otra fecha?"
    else:
        return "No encontré horarios para esa fecha. ¿Otra fecha?"