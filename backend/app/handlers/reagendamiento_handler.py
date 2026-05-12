import re
import datetime
from app.services.calcom import obtener_citas_cliente_por_cedula, obtener_slots_disponibles, reagendar_cita

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
            "step": "esperando_cedula",
            "data": {}
        }
    
    estado = agendamientos_temp[cliente_id]
    step = estado.get("step")
    
    # ==============================================
    # PASO 1: ESPERANDO CÉDULA
    # ==============================================
    if step == "esperando_cedula":
        cedula_cliente = None
        
        cedula_match = re.search(r'\b(\d{6,10})\b', texto_mensaje)
        if cedula_match:
            cedula_cliente = cedula_match.group(1)
        elif cliente.datos_estructurados and cliente.datos_estructurados.get("cedula"):
            cedula_cliente = cliente.datos_estructurados.get("cedula")
        
        if not cedula_cliente:
            clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "cedula", historial)
            if not clasificacion.get("es_valido"):
                respuesta_texto = clasificacion.get("respuesta_rag", "No entendí tu cédula.")
                respuesta_texto += "\n\nPara reagendar una cita, necesito tu número de cédula. ¿Cuál es tu cédula?"
                return respuesta_texto, agendamientos_temp
            else:
                cedula_cliente = clasificacion.get("dato_extraido")
        
        if cedula_cliente:
            if not cliente.datos_estructurados:
                cliente.datos_estructurados = {}
            cliente.datos_estructurados["cedula"] = cedula_cliente
            db.add(cliente)
            db.commit()
            
            citas_resultado = obtener_citas_cliente_por_cedula(cedula_cliente)
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
                    respuesta_texto += "\n\n¿Cuál deseas reagendar? Puedes decirme el número, la fecha o la hora."
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
    # PASO 2: MOSTRANDO CITAS (esperando selección con número, fecha o hora)
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
        
        # 🔥 2. SI NO, INTENTAR POR FECHA (usando extraer_intencion_y_fecha)
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
        
        # 🔥 3. SI NO, INTENTAR POR HORA (ej. "la de las 10", "reagendar la de las 10")
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
        
        # 🔥 SI SE ENCONTRÓ UNA CITA, PASAR A SELECCIONAR NUEVA FECHA
        if cita_seleccionada:
            booking_id_original = cita_seleccionada["booking_id"]
            cliente_nombre = cita_seleccionada.get("asistentes", [{}])[0].get("name", "Cliente")
            cliente_email = cita_seleccionada.get("asistentes", [{}])[0].get("email", "")
            cliente_cedula = estado["data"].get("cedula")
            cliente_telefono = cita_seleccionada.get("asistentes", [{}])[0].get("phoneNumber")
            
            estado["step"] = "esperando_nueva_fecha"
            estado["data"]["reagendar_booking_id"] = booking_id_original
            estado["data"]["reagendar_nombre"] = cliente_nombre
            estado["data"]["reagendar_email"] = cliente_email
            estado["data"]["reagendar_cedula"] = cliente_cedula
            estado["data"]["reagendar_telefono"] = cliente_telefono
            respuesta_texto = "Perfecto. ¿Para qué nueva fecha y hora deseas reagendar la cita? (ej: 'mañana a las 11:00' o '7 de abril a las 12:00')"
            return respuesta_texto, agendamientos_temp
        
        # 🔥 SI NO SE ENCONTRÓ, MANEJAR INTERRUPCIÓN O REPETIR LISTA
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
            respuesta_texto += "\n\n¿Cuál deseas reagendar? Puedes decirme el número, la fecha o la hora."
        else:
            respuesta_texto = "No encontré esa cita. Por favor, indícame el número, la fecha o la hora de la cita que deseas reagendar."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 3: ESPERANDO NUEVA FECHA Y HORA (con extracción inteligente)
    # ==============================================
    if step == "esperando_nueva_fecha":
        # 🔥 PRIMERO: manejar interrupciones (desvíos)
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "fecha_hora", historial)
        if not clasificacion.get("es_valido"):
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu consulta.")
            respuesta_texto = f"{respuesta_rag}\n\nPara reagendar la cita, necesito que me indiques la nueva fecha y hora (ej: 'mañana a las 11:00' o '7 de abril a las 12:00'). ¿Cuándo prefieres la nueva cita?"
            return respuesta_texto, agendamientos_temp
        
        # 🔥 SEGUNDO: extraer fecha y hora con la misma lógica de agendamiento
        analisis_fecha = rag.extraer_intencion_y_fecha(texto_mensaje, historial)
        nueva_fecha = analisis_fecha.get("fecha")
        nueva_hora = analisis_fecha.get("hora")
        
        # Caso 1: Tiene fecha y hora completas
        if nueva_fecha and nueva_hora:
            slots_resultado = obtener_slots_disponibles(
                event_type_id=1288606,
                fecha_inicio=nueva_fecha,
                dias_a_mostrar=1
            )
            if slots_resultado.get("exito") and slots_resultado.get("slots_por_fecha"):
                horas_disponibles = slots_resultado["slots_por_fecha"].get(nueva_fecha, [])
                
                # Normalizar hora (por si viene como "11am", "11:00", etc.)
                hora_normalizada = nueva_hora
                match = re.search(r'(\d{1,2})', nueva_hora)
                if match:
                    hora_num = int(match.group(1))
                    if 'pm' in nueva_hora.lower() and hora_num < 12:
                        hora_num += 12
                    elif 'am' in nueva_hora.lower() and hora_num == 12:
                        hora_num = 0
                    hora_normalizada = f"{hora_num:02d}:00"
                
                if hora_normalizada in horas_disponibles:
                    booking_id_original = estado["data"].get("reagendar_booking_id")
                    cliente_nombre = estado["data"].get("reagendar_nombre")
                    cliente_email = estado["data"].get("reagendar_email")
                    cliente_cedula = estado["data"].get("reagendar_cedula")
                    cliente_telefono = estado["data"].get("reagendar_telefono")
                    
                    resultado = reagendar_cita(
                        booking_id=booking_id_original,
                        event_type_id=1288606,
                        cliente_nombre=cliente_nombre,
                        cliente_email=cliente_email,
                        cliente_cedula=cliente_cedula,
                        cliente_telefono=cliente_telefono,
                        nueva_fecha=nueva_fecha,
                        nueva_hora=hora_normalizada
                    )
                    
                    if resultado.get("exito"):
                        fecha_legible = datetime.datetime.strptime(nueva_fecha, "%Y-%m-%d").strftime("%d/%m/%Y")
                        respuesta_texto = f"✅ Cita reagendada exitosamente para el {fecha_legible} a las {hora_normalizada}."
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
        
        # Caso 2: Solo tiene fecha (sin hora)
        elif nueva_fecha and not nueva_hora:
            # Guardar la fecha seleccionada para después
            estado["data"]["fecha_seleccionada"] = nueva_fecha
            agendamientos_temp[cliente_id] = estado
            
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
                    respuesta_texto = f"No hay horarios disponibles para esa fecha. Por favor, elige otra fecha."
            else:
                respuesta_texto = f"No encontré horarios disponibles para esa fecha. Por favor, elige otra fecha."
        
        # Caso 3: Solo tiene hora (sin fecha, pero ya tenemos fecha guardada)
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
                    
                    hora_normalizada = nueva_hora
                    match = re.search(r'(\d{1,2})', nueva_hora)
                    if match:
                        hora_num = int(match.group(1))
                        if 'pm' in nueva_hora.lower() and hora_num < 12:
                            hora_num += 12
                        elif 'am' in nueva_hora.lower() and hora_num == 12:
                            hora_num = 0
                        hora_normalizada = f"{hora_num:02d}:00"
                    
                    if hora_normalizada in horas_disponibles:
                        booking_id_original = estado["data"].get("reagendar_booking_id")
                        cliente_nombre = estado["data"].get("reagendar_nombre")
                        cliente_email = estado["data"].get("reagendar_email")
                        cliente_cedula = estado["data"].get("reagendar_cedula")
                        cliente_telefono = estado["data"].get("reagendar_telefono")
                        
                        resultado = reagendar_cita(
                            booking_id=booking_id_original,
                            event_type_id=1288606,
                            cliente_nombre=cliente_nombre,
                            cliente_email=cliente_email,
                            cliente_cedula=cliente_cedula,
                            cliente_telefono=cliente_telefono,
                            nueva_fecha=fecha_guardada,
                            nueva_hora=hora_normalizada
                        )
                        
                        if resultado.get("exito"):
                            fecha_legible = datetime.datetime.strptime(fecha_guardada, "%Y-%m-%d").strftime("%d/%m/%Y")
                            respuesta_texto = f"✅ Cita reagendada exitosamente para el {fecha_legible} a las {hora_normalizada}."
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
                    agendamientos_temp[cliente_id] = estado
            else:
                respuesta_texto = "Primero indícame la fecha para la cita (ej: 'miércoles', 'mañana', '10 de abril')."
        
        # Caso 4: No entendió nada
        else:
            respuesta_texto = "No entendí la fecha y hora. Por favor, indícame la nueva fecha y hora (ej: 'mañana a las 11:00' o '7 de abril a las 12:00')."
        
        return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # ESTADO DESCONOCIDO
    # ==============================================
    respuesta_texto = "Ocurrió un error. Por favor, inicia de nuevo."
    del agendamientos_temp[cliente_id]
    return respuesta_texto, agendamientos_temp