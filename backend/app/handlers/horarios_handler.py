import datetime
from app.services.calcom import obtener_slots_disponibles
from app.db.base import SessionLocal
from app.models.especialidad import Especialidad

async def manejar_horarios(fecha: str, especialidad: str = None, empresa_id: int = 1) -> str:
    # Si no hay especialidad, no podemos determinar el event_type_id
    if not especialidad:
        return "Por favor, indícame para qué especialidad deseas consultar los horarios (ej: odontología, pediatría)."
    
    # Consultar el event_type_id en la base de datos
    db = SessionLocal()
    esp = db.query(Especialidad).filter(
        Especialidad.empresa_id == empresa_id,
        Especialidad.nombre.ilike(especialidad),  # búsqueda insensible a mayúsculas
        Especialidad.activa == True
    ).first()
    db.close()
    
    if not esp:
        return f"Lo siento, no tengo registrada la especialidad '{especialidad}'. Las especialidades disponibles son: odontología, pediatría, gastroenterología, cardiología, dermatología, traumatología."
    
    event_type_id = esp.event_type_id
    
    slots_resultado = obtener_slots_disponibles(
        event_type_id=event_type_id,  # 🔥 AHORA DINÁMICO
        fecha_inicio=fecha, 
        dias_a_mostrar=1
    )
    
    if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
        slots_dia = slots_resultado["slots_por_fecha"].get(fecha, [])
        if slots_dia:
            horas = []
            for slot in slots_dia:
                if isinstance(slot, dict):
                    horas.append(slot.get("hora"))
                else:
                    horas.append(slot)
            
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
            return f"Para el {fecha_legible} en {especialidad} tenemos los siguientes horarios: {', '.join(horas)}. ¿Cuál te interesa?"
        else:
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
            return f"No hay horarios disponibles para {especialidad} el {fecha_legible}. ¿Otra fecha?"
    else:
        return f"No encontré horarios para {especialidad} en esa fecha. ¿Otra fecha?"