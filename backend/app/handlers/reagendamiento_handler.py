import re
import datetime
from app.services.calcom import obtener_citas_cliente, obtener_slots_disponibles, reagendar_cita

async def manejar_reagendamiento(
    cliente_id: int,
    email: str,
    texto_mensaje: str,
    fecha: str,
    hora: str,
    cliente,
    db,
    rag,
    historial: str,
    agendamientos_temp: dict,
    booking_id: int = None
) -> tuple:
    """
    Maneja el flujo de reagendamiento con máquina de estados (flow + step).
    Retorna (respuesta_texto, agendamientos_temp_actualizado)
    """
    respuesta_texto = ""
    
    # ==============================================
    # INICIALIZAR O RECUPERAR ESTADO
    # ==============================================
    if cliente_id not in agendamientos_temp or agendamientos_temp[cliente_id].get("flow") != "REAGENDAR":
        agendamientos_temp[cliente_id] = {
            "flow": "REAGENDAR",
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
        
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_mensaje)
        if email_match:
            email_cliente = email_match.group(0)
        elif email:
            email_cliente = email
        elif cliente.datos_estructurados and cliente.datos_estructurados.get("email"):
            email_cliente = cliente.datos_estructurados.get("email")
        
        if not email_cliente:
            clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "email", historial)
            if not clasificacion.get("es_valido"):
                respuesta_texto = clasificacion.get("respuesta_rag", "No entendí tu correo.")
                respuesta_texto += "\n\nPara reagendar una cita, necesito tu correo electrónico. ¿Cuál es tu email?"
                return respuesta_texto, agendamientos_temp
            else:
                email_cliente = clasificacion.get("dato_extraido")
        
        if email_cliente:
            if not cliente.datos_estructurados:
                cliente.datos_estructurados = {}
            cliente.datos_estructurados["email"] = email_cliente
            db.add(cliente)
            db.commit()
            
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
                    respuesta_texto += "\n\nResponde con el número de la cita que deseas reagendar (ej: '1')."
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
        
        match_num = re.search(r'(\d+)', texto_mensaje)
        if match_num:
            idx = int(match_num.group(1)) - 1
            if 0 <= idx < len(citas):
                cita_seleccionada = citas[idx]
                booking_id_original = cita_seleccionada["booking_id"]
                cliente_nombre = cita_seleccionada.get("asistentes", [{}])[0].get("name", "Cliente")
                cliente_email = estado["data"].get("email")
                
                estado["step"] = "esperando_nueva_fecha"
                estado["data"]["reagendar_booking_id"] = booking_id_original
                estado["data"]["reagendar_nombre"] = cliente_nombre
                estado["data"]["reagendar_email"] = cliente_email
                respuesta_texto = "Perfecto. ¿Para qué nueva fecha y hora deseas reagendar la cita? (ej: 'mañana a las 11:00' o '7 de abril a las 12:00')"
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
            respuesta_texto += "\n\nResponde con el número de la cita que deseas reagendar (ej: '1')."
        else:
            respuesta_texto = "Por favor, responde con el número de la cita que deseas reagendar (ej: '1')."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 3: ESPERANDO NUEVA FECHA Y HORA (con manejo de desvíos)
    # ==============================================
    if step == "esperando_nueva_fecha":
        # Primero, verificar si el mensaje es una interrupción (pregunta fuera del flujo)
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "fecha_hora", historial)
        
        # Si es una interrupción, responder con RAG y repetir la pregunta
        if not clasificacion.get("es_valido"):
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu consulta.")
            respuesta_texto = f"{respuesta_rag}\n\nPerfecto. ¿Para qué nueva fecha y hora deseas reagendar la cita? (ej: 'mañana a las 11:00' o '7 de abril a las 12:00')"
            return respuesta_texto, agendamientos_temp
        
        # Si no es interrupción, continuar con el procesamiento normal
        analisis_fecha = rag.extraer_intencion_y_fecha(texto_mensaje, historial)
        nueva_fecha = analisis_fecha.get("fecha")
        nueva_hora = analisis_fecha.get("hora")
        
        # CASO 1: El usuario dio fecha y hora completas
        if nueva_fecha and nueva_hora:
            slots_resultado = obtener_slots_disponibles(
                event_type_id=1288606,
                fecha_inicio=nueva_fecha,
                dias_a_mostrar=1
            )
            if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
                horas_disponibles = slots_resultado["slots_por_fecha"].get(nueva_fecha, [])
                if nueva_hora in horas_disponibles:
                    booking_id_original = estado["data"].get("reagendar_booking_id")
                    cliente_nombre = estado["data"].get("reagendar_nombre")
                    cliente_email = estado["data"].get("reagendar_email")
                    
                    resultado = reagendar_cita(
                        booking_id=booking_id_original,
                        event_type_id=1288606,
                        cliente_nombre=cliente_nombre,
                        cliente_email=cliente_email,
                        nueva_fecha=nueva_fecha,
                        nueva_hora=nueva_hora
                    )
                    
                    if resultado.get("exito"):
                        respuesta_texto = f"✅ Cita reagendada exitosamente para {nueva_fecha} a las {nueva_hora}."
                        del agendamientos_temp[cliente_id]
                    else:
                        respuesta_texto = f"❌ Error al reagendar: {resultado.get('error')}."
                        if resultado.get("horarios_disponibles"):
                            respuesta_texto += f" Horarios disponibles: {', '.join(resultado['horarios_disponibles'])}"
                        del agendamientos_temp[cliente_id]
                else:
                    respuesta_texto = f"La hora {nueva_hora} no está disponible para {nueva_fecha}. Horarios disponibles: {', '.join(horas_disponibles)}. Por favor, elige otra hora."
            else:
                respuesta_texto = f"No encontré horarios disponibles para {nueva_fecha}. Por favor, elige otra fecha."
        
        # CASO 2: El usuario dio solo una fecha (sin hora)
        elif nueva_fecha and not nueva_hora:
            estado["data"]["fecha_seleccionada"] = nueva_fecha
            
            slots_resultado = obtener_slots_disponibles(
                event_type_id=1288606,
                fecha_inicio=nueva_fecha,
                dias_a_mostrar=1
            )
            if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
                horas = slots_resultado["slots_por_fecha"].get(nueva_fecha, [])
                if horas:
                    fecha_legible = datetime.datetime.strptime(nueva_fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
                    respuesta_texto = f"Para el {fecha_legible} tenemos los siguientes horarios: {', '.join(horas)}. ¿Cuál prefieres?"
                else:
                    respuesta_texto = f"No hay horarios disponibles para {fecha_legible}. Por favor, elige otra fecha."
            else:
                respuesta_texto = f"No encontré horarios disponibles para esa fecha. Por favor, elige otra fecha."
        
        # CASO 3: El usuario dio solo una hora (sin fecha)
        elif not nueva_fecha and nueva_hora:
            fecha_guardada = estado["data"].get("fecha_seleccionada")
            if fecha_guardada:
                slots_resultado = obtener_slots_disponibles(
                    event_type_id=1288606,
                    fecha_inicio=fecha_guardada,
                    dias_a_mostrar=1
                )
                if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
                    horas_disponibles = slots_resultado["slots_por_fecha"].get(fecha_guardada, [])
                    if nueva_hora in horas_disponibles:
                        booking_id_original = estado["data"].get("reagendar_booking_id")
                        cliente_nombre = estado["data"].get("reagendar_nombre")
                        cliente_email = estado["data"].get("reagendar_email")
                        
                        resultado = reagendar_cita(
                            booking_id=booking_id_original,
                            event_type_id=1288606,
                            cliente_nombre=cliente_nombre,
                            cliente_email=cliente_email,
                            nueva_fecha=fecha_guardada,
                            nueva_hora=nueva_hora
                        )
                        
                        if resultado.get("exito"):
                            respuesta_texto = f"✅ Cita reagendada exitosamente para {fecha_guardada} a las {nueva_hora}."
                            del agendamientos_temp[cliente_id]
                        else:
                            respuesta_texto = f"❌ Error al reagendar: {resultado.get('error')}."
                            if resultado.get("horarios_disponibles"):
                                respuesta_texto += f" Horarios disponibles: {', '.join(resultado['horarios_disponibles'])}"
                            del agendamientos_temp[cliente_id]
                    else:
                        respuesta_texto = f"La hora {nueva_hora} no está disponible para {fecha_guardada}. Horarios disponibles: {', '.join(horas_disponibles)}. Por favor, elige otra hora."
                else:
                    respuesta_texto = f"No encontré horarios disponibles para {fecha_guardada}. Por favor, elige otra fecha."
                    estado["data"]["fecha_seleccionada"] = None
            else:
                respuesta_texto = "Primero indícame la fecha para la cita (ej: 'miércoles', 'mañana', '10 de abril')."
        
        # CASO 4: El usuario dio algo que no es fecha ni hora
        else:
            respuesta_texto = "No entendí la fecha y hora. Por favor, indícame la nueva fecha y hora (ej: 'mañana a las 11:00' o '7 de abril a las 12:00')."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # ESTADO DESCONOCIDO
    # ==============================================
    respuesta_texto = "Ocurrió un error. Por favor, inicia de nuevo."
    del agendamientos_temp[cliente_id]
    return respuesta_texto, agendamientos_temp