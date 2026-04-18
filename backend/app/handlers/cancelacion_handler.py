import re
import datetime
from app.services.calcom import obtener_citas_cliente_por_cedula, eliminar_cita

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
            "step": "esperando_cedula",  # 🔥 CAMBIADO: antes era "esperando_email"
            "data": {}
        }
    
    estado = agendamientos_temp[cliente_id]
    step = estado.get("step")
    
    # ==============================================
    # PASO 1: ESPERANDO CÉDULA (antes email)
    # ==============================================
    if step == "esperando_cedula":
        cedula_cliente = None
        
        # Intentar extraer cédula del texto (números de 6 a 10 dígitos)
        cedula_match = re.search(r'\b(\d{6,10})\b', texto_mensaje)
        if cedula_match:
            cedula_cliente = cedula_match.group(1)
        elif cliente.datos_estructurados and cliente.datos_estructurados.get("cedula"):
            cedula_cliente = cliente.datos_estructurados.get("cedula")
        
        if not cedula_cliente:
            # Clasificar si el mensaje es una interrupción
            clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "cedula", historial)
            if not clasificacion.get("es_valido"):
                respuesta_texto = clasificacion.get("respuesta_rag", "No entendí tu cédula.")
                respuesta_texto += "\n\nPara cancelar una cita, necesito tu número de cédula. ¿Cuál es tu cédula?"
                return respuesta_texto, agendamientos_temp
            else:
                cedula_cliente = clasificacion.get("dato_extraido")
        
        if cedula_cliente:
            # Guardar cédula en cliente
            if not cliente.datos_estructurados:
                cliente.datos_estructurados = {}
            cliente.datos_estructurados["cedula"] = cedula_cliente
            db.add(cliente)
            db.commit()
            
            # Consultar citas por cédula
            citas_resultado = obtener_citas_cliente_por_cedula(cedula_cliente)  # 🔥 NUEVA FUNCIÓN
            if citas_resultado.get("exito"):
                citas = citas_resultado.get("citas", [])
                if citas:
                    estado["step"] = "mostrando_citas"
                    estado["data"]["citas"] = citas
                    estado["data"]["cedula"] = cedula_cliente
                    lista_citas = []
                    for i, cita in enumerate(citas, 1):
                        fecha_iso = cita["fecha"]
                        fecha_obj = datetime.datetime.fromisoformat(fecha_iso)
                        fecha_legible = fecha_obj.strftime("%d/%m/%Y")
                        hora_legible = fecha_obj.strftime("%H:%M")
                        lista_citas.append(f"{i}. 📅 {fecha_legible} a las {hora_legible}")
                    respuesta_texto = "📋 *Tus citas agendadas:*\n\n" + "\n".join(lista_citas)
                    respuesta_texto += "\n\nResponde con el número de la cita que deseas cancelar (ej: '1')."
                else:
                    respuesta_texto = "No tienes citas futuras agendadas."
                    del agendamientos_temp[cliente_id]
            else:
                respuesta_texto = f"No pude consultar tus citas: {citas_resultado.get('error')}. Por favor, intenta de nuevo más tarde."
                del agendamientos_temp[cliente_id]
        else:
            respuesta_texto = "No entendí tu cédula. Por favor, ingresa un número de cédula válido (solo números)."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 2: MOSTRANDO CITAS (esperando selección)
    # ==============================================
    if step == "mostrando_citas":
        citas = estado["data"].get("citas", [])
        
        match_num = re.search(r'(\d+)', texto_mensaje)
        if match_num:
            idx = int(match_num.group(1)) - 1
            if 0 <= idx < len(citas):
                cita = citas[idx]
                resultado = eliminar_cita(cita["booking_id"])
                if resultado.get("exito"):
                    respuesta_texto = f"✅ Cita del {cita['fecha'][:10]} a las {cita['fecha'][11:16]} ha sido cancelada exitosamente."
                else:
                    respuesta_texto = f"❌ Error al cancelar: {resultado.get('error')}."
                del agendamientos_temp[cliente_id]
                return respuesta_texto, agendamientos_temp
            else:
                respuesta_texto = f"Número inválido. Responde con el número de la cita (1, 2, 3...)."
                return respuesta_texto, agendamientos_temp
        
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "numero_cita", historial)
        if not clasificacion.get("es_valido"):
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu consulta.")
            lista_citas = []
            for i, cita in enumerate(citas, 1):
                fecha_iso = cita["fecha"]
                fecha_obj = datetime.datetime.fromisoformat(fecha_iso)
                fecha_legible = fecha_obj.strftime("%d/%m/%Y")
                hora_legible = fecha_obj.strftime("%H:%M")
                lista_citas.append(f"{i}. 📅 {fecha_legible} a las {hora_legible}")
            respuesta_texto = f"{respuesta_rag}\n\n📋 *Tus citas agendadas:*\n\n" + "\n".join(lista_citas)
            respuesta_texto += "\n\nResponde con el número de la cita que deseas cancelar (ej: '1')."
        else:
            respuesta_texto = "Por favor, responde con el número de la cita que deseas cancelar (ej: '1')."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # ESTADO DESCONOCIDO
    # ==============================================
    respuesta_texto = "Ocurrió un error. Por favor, inicia de nuevo."
    del agendamientos_temp[cliente_id]
    return respuesta_texto, agendamientos_temp
