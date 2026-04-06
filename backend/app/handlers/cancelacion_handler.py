import re
import datetime
from app.services.calcom import obtener_citas_cliente, eliminar_cita

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
        # Nuevo flujo de cancelación
        agendamientos_temp[cliente_id] = {
            "flow": "CANCELAR",
            "step": "esperando_email",
            "data": {}
        }
    
    estado = agendamientos_temp[cliente_id]
    step = estado.get("step")
    
    # ==============================================
    # PASO 1: ESPERANDO EMAIL
    # ==============================================
    if step == "esperando_email":
        email_cliente = None
        
        # Intentar extraer email con regex
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_mensaje)
        if email_match:
            email_cliente = email_match.group(0)
        elif email:
            email_cliente = email
        elif cliente.datos_estructurados and cliente.datos_estructurados.get("email"):
            email_cliente = cliente.datos_estructurados.get("email")
        
        if not email_cliente:
            # Clasificar si el mensaje es una interrupción
            clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "email", historial)
            if not clasificacion.get("es_valido"):
                respuesta_texto = clasificacion.get("respuesta_rag", "No entendí tu correo.")
                respuesta_texto += "\n\nPara cancelar una cita, necesito tu correo electrónico. ¿Cuál es tu email?"
                return respuesta_texto, agendamientos_temp
            else:
                email_cliente = clasificacion.get("dato_extraido")
        
        if email_cliente:
            # Guardar email en cliente
            if not cliente.datos_estructurados:
                cliente.datos_estructurados = {}
            cliente.datos_estructurados["email"] = email_cliente
            db.add(cliente)
            db.commit()
            
            # Consultar citas
            citas_resultado = obtener_citas_cliente(email_cliente)
            if citas_resultado.get("exito"):
                citas = citas_resultado.get("citas", [])
                if citas:
                    estado["step"] = "mostrando_citas"
                    estado["data"]["citas"] = citas
                    estado["data"]["email"] = email_cliente
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
            respuesta_texto = "No entendí tu correo. Por favor, ingresa un correo electrónico válido (ej: nombre@dominio.com)."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 2: MOSTRANDO CITAS (esperando selección)
    # ==============================================
    if step == "mostrando_citas":
        citas = estado["data"].get("citas", [])
        
        # Verificar si el mensaje es un número de cita válido
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
        
        # Si no es un número, clasificar como interrupción
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