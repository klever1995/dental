import re
import datetime
from app.services.google_calendar import obtener_citas_cliente_por_cedula, eliminar_cita
from app.db.base import SessionLocal
from app.models.especialidad import Especialidad

async def manejar_cancelacion(
    cliente_id: int,
    email: str,
    texto_mensaje: str,
    fecha: str,
    cliente,
    db,
    rag,
    historial: str,
    agendamientos_temp: dict
) -> tuple:
    """
    Maneja el flujo de cancelación con máquina de estados (flow + step).
    Retorna (respuesta_texto, agendamientos_temp_actualizado)
    """
    respuesta_texto = ""
    
    # ==============================================
    # INICIALIZAR O RECUPERAR ESTADO
    # ==============================================
    if cliente_id not in agendamientos_temp or agendamientos_temp[cliente_id].get("flow") != "CANCELAR":
        agendamientos_temp[cliente_id] = {
            "flow": "CANCELAR",
            "step": "esperando_cedula",
            "data": {}
        }
    
    estado = agendamientos_temp[cliente_id]
    step = estado.get("step")
    
    # ==============================================
    # PASO 1: ESPERANDO CÉDULA (siempre preguntar)
    # ==============================================
    if step == "esperando_cedula":
        cedula_cliente = None
        
        # Extraer cédula del mensaje (si la escribió)
        cedula_match = re.search(r'\b(\d{6,10})\b', texto_mensaje)
        if cedula_match:
            cedula_cliente = cedula_match.group(1)
        
        if not cedula_cliente:
            # Si no, usar clasificación del RAG
            clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "cedula", historial)
            if clasificacion.get("es_valido"):
                cedula_cliente = clasificacion.get("dato_extraido")
            else:
                respuesta_texto = "Para cancelar una cita, necesito tu número de cédula. ¿Cuál es tu cédula?"
                return respuesta_texto, agendamientos_temp
        
        if cedula_cliente:
            # Guardar cédula en datos estructurados del cliente
            if not cliente.datos_estructurados:
                cliente.datos_estructurados = {}
            cliente.datos_estructurados["cedula"] = cedula_cliente
            db.add(cliente)
            db.commit()
            
            # Obtener todas las citas futuras del cliente (sin filtrar por calendario)
            citas_resultado = obtener_citas_cliente_por_cedula(cedula_cliente, calendar_id=None)
            if citas_resultado.get("exito"):
                citas = citas_resultado.get("citas", [])
                if citas:
                    estado["step"] = "mostrando_citas"
                    estado["data"]["citas"] = citas
                    estado["data"]["cedula"] = cedula_cliente
                    
                    # Mostrar lista de citas con especialidad (obtener nombre desde calendar_id)
                    lista_citas = []
                    for i, cita in enumerate(citas, 1):
                        fecha_iso = cita["fecha"]
                        fecha_obj = datetime.datetime.fromisoformat(fecha_iso)
                        fecha_legible = fecha_obj.strftime("%d/%m/%Y")
                        hora_legible = fecha_obj.strftime("%H:%M")
                        
                        # Obtener nombre de la especialidad desde calendar_id
                        calendar_id = cita.get("calendar_id")
                        especialidad_nombre = "Desconocida"
                        if calendar_id:
                            db_temp = SessionLocal()
                            esp = db_temp.query(Especialidad).filter(
                                Especialidad.calendar_id == calendar_id,
                                Especialidad.activa == True
                            ).first()
                            if esp:
                                especialidad_nombre = esp.nombre
                            db_temp.close()
                        
                        lista_citas.append(f"{i}. 📅 {fecha_legible} a las {hora_legible} - 🩺 {especialidad_nombre}")
                    
                    respuesta_texto = "📋 *Tus citas agendadas:*\n\n" + "\n".join(lista_citas)
                    respuesta_texto += "\n\n¿Cuál deseas cancelar? Puedes decirme el número, la fecha o la hora."
                else:
                    respuesta_texto = "No tienes citas futuras agendadas."
                    del agendamientos_temp[cliente_id]
            else:
                respuesta_texto = f"No pude consultar tus citas. Por favor, intenta de nuevo más tarde."
                del agendamientos_temp[cliente_id]
        else:
            respuesta_texto = "No entendí tu cédula. Por favor, ingresa un número de cédula válido (solo números)."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 2: MOSTRANDO CITAS (esperando selección)
    # ==============================================
    if step == "mostrando_citas":
        citas = estado["data"].get("citas", [])
        cita_seleccionada = None
        
        # 🔥 1. INTENTAR POR NÚMERO DE LISTA
        match_num = re.search(r'(\d+)', texto_mensaje)
        if match_num:
            idx = int(match_num.group(1)) - 1
            if 0 <= idx < len(citas):
                cita_seleccionada = citas[idx]
        
        # 🔥 2. SI NO, INTENTAR POR FECHA
        if not cita_seleccionada:
            analisis = rag.extraer_intencion_y_fecha(texto_mensaje, historial)
            fecha_extraida = analisis.get("fecha")
            if fecha_extraida:
                fecha_obj = datetime.datetime.strptime(fecha_extraida, "%Y-%m-%d").date()
                for cita in citas:
                    fecha_cita_obj = datetime.datetime.fromisoformat(cita["fecha"]).date()
                    if fecha_cita_obj == fecha_obj:
                        cita_seleccionada = cita
                        break
        
        # 🔥 3. SI NO, INTENTAR POR HORA
        if not cita_seleccionada:
            hora_match = re.search(r'(\d{1,2})\s*(?::\s*00)?\s*(?:am|pm|horas|hrs)?', texto_mensaje.lower())
            if hora_match:
                hora_buscada = int(hora_match.group(1))
                if 'pm' in texto_mensaje.lower() and hora_buscada < 12:
                    hora_buscada += 12
                elif 'am' in texto_mensaje.lower() and hora_buscada == 12:
                    hora_buscada = 0
                
                for cita in citas:
                    fecha_cita_obj = datetime.datetime.fromisoformat(cita["fecha"])
                    if fecha_cita_obj.hour == hora_buscada:
                        cita_seleccionada = cita
                        break
        
        # 🔥 SI SE ENCONTRÓ UNA CITA, CANCELAR
        if cita_seleccionada:
            event_id = cita_seleccionada.get("booking_id")
            calendar_id = cita_seleccionada.get("calendar_id")
            
            if not calendar_id:
                respuesta_texto = "❌ No se pudo identificar el calendario de la cita. Por favor, intenta de nuevo."
                del agendamientos_temp[cliente_id]
                return respuesta_texto, agendamientos_temp
            
            resultado = eliminar_cita(event_id=event_id, calendar_id=calendar_id)
            if resultado.get("exito"):
                fecha_legible = datetime.datetime.fromisoformat(cita_seleccionada["fecha"]).strftime("%d/%m/%Y a las %H:%M")
                respuesta_texto = f"✅ Cita del {fecha_legible} ha sido cancelada exitosamente."
            else:
                respuesta_texto = f"❌ Error al cancelar: {resultado.get('error')}."
            del agendamientos_temp[cliente_id]
            return respuesta_texto, agendamientos_temp
        
        # 🔥 SI NO SE ENCONTRÓ, MANEJAR INTERRUPCIÓN O REPETIR LISTA
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "numero_cita", historial)
        if not clasificacion.get("es_valido"):
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu consulta.")
            # Regenerar lista de citas con especialidad (igual que arriba)
            lista_citas = []
            for i, cita in enumerate(citas, 1):
                fecha_iso = cita["fecha"]
                fecha_obj = datetime.datetime.fromisoformat(fecha_iso)
                fecha_legible = fecha_obj.strftime("%d/%m/%Y")
                hora_legible = fecha_obj.strftime("%H:%M")
                
                calendar_id = cita.get("calendar_id")
                especialidad_nombre = "Desconocida"
                if calendar_id:
                    db_temp = SessionLocal()
                    esp = db_temp.query(Especialidad).filter(
                        Especialidad.calendar_id == calendar_id,
                        Especialidad.activa == True
                    ).first()
                    if esp:
                        especialidad_nombre = esp.nombre
                    db_temp.close()
                
                lista_citas.append(f"{i}. 📅 {fecha_legible} a las {hora_legible} - 🩺 {especialidad_nombre}")
            
            respuesta_texto = f"{respuesta_rag}\n\n📋 *Tus citas agendadas:*\n\n" + "\n".join(lista_citas)
            respuesta_texto += "\n\n¿Cuál deseas cancelar? Puedes decirme el número, la fecha o la hora."
        else:
            respuesta_texto = "No encontré esa cita. Por favor, indícame el número, la fecha o la hora de la cita que deseas cancelar."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # ESTADO DESCONOCIDO
    # ==============================================
    respuesta_texto = "Ocurrió un error. Por favor, inicia de nuevo."
    del agendamientos_temp[cliente_id]
    return respuesta_texto, agendamientos_temp