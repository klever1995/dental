import datetime
import pytz
import re
from app.services.calcom import obtener_slots_disponibles, agendar_cita

async def manejar_agendamiento(
    cliente_id: int,
    nombre: str,
    fecha: str,
    hora: str,
    email: str,
    texto_mensaje: str,
    rag,
    historial: str,
    agendamientos_temp: dict
) -> tuple:
    """
    Maneja el flujo de agendamiento con manejo de interrupciones.
    Retorna (respuesta_texto, agendamientos_temp_actualizado)
    """
    # Obtener o crear datos temporales
    if cliente_id not in agendamientos_temp:
        agendamientos_temp[cliente_id] = {
            "nombre": nombre,
            "fecha": fecha,
            "hora": hora,
            "email": email,
            "activo": True
        }
    else:
        datos = agendamientos_temp[cliente_id]
        if nombre and not datos["nombre"]:
            datos["nombre"] = nombre
        if fecha and not datos["fecha"]:
            datos["fecha"] = fecha
        if hora and not datos["hora"]:
            datos["hora"] = hora
        if email and not datos["email"]:
            datos["email"] = email
    
    datos = agendamientos_temp[cliente_id]
    respuesta_texto = ""
    
    # ==============================================
    # PASO 1: PEDIR NOMBRE
    # ==============================================
    if not datos["nombre"]:
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "nombre", historial)
        
        if clasificacion.get("es_valido"):
            datos["nombre"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            # Continuar al siguiente paso
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu nombre.")
            respuesta_texto = f"{respuesta_rag}\n\nClaro, ¿cuál es tu nombre completo?"
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 2: PEDIR FECHA
    # ==============================================
    if not datos["fecha"]:
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "fecha", historial)
        
        if clasificacion.get("es_valido"):
            datos["fecha"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí la fecha.")
            respuesta_texto = f"{respuesta_rag}\n\nGracias {datos['nombre']}. ¿Para qué día quieres la cita? (ej: mañana, lunes)"
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 3: PEDIR HORA (mostrar horarios disponibles)
    # ==============================================
    if not datos["hora"]:
        # Si no tenemos horarios disponibles guardados, consultarlos
        if "horas_disponibles" not in datos:
            slots = obtener_slots_disponibles(event_type_id=1288606, fecha_inicio=datos["fecha"], dias_a_mostrar=1)
            if slots.get("exito") and slots.get("slots_por_fecha"):
                horas = slots["slots_por_fecha"].get(datos["fecha"], [])
                if horas:
                    datos["horas_disponibles"] = horas
                    agendamientos_temp[cliente_id] = datos
                    respuesta_texto = f"Para {datos['fecha']} tenemos: {', '.join(horas)}. ¿Cuál prefieres?"
                    return respuesta_texto, agendamientos_temp
                else:
                    respuesta_texto = f"No hay horarios para {datos['fecha']}. ¿Otra fecha?"
                    datos["fecha"] = None
                    agendamientos_temp[cliente_id] = datos
                    return respuesta_texto, agendamientos_temp
            else:
                respuesta_texto = f"No encontré horarios para {datos['fecha']}. ¿Otra fecha?"
                datos["fecha"] = None
                agendamientos_temp[cliente_id] = datos
                return respuesta_texto, agendamientos_temp
        
        # Clasificar la respuesta del usuario
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "hora", historial)
        
        if clasificacion.get("es_valido"):
            hora_seleccionada = clasificacion.get("dato_extraido")
            horas_disponibles = datos.get("horas_disponibles", [])
            
            # Normalizar hora
            match = re.search(r'(\d{1,2})', hora_seleccionada)
            if match:
                hora_num = int(match.group(1))
                if 'pm' in hora_seleccionada.lower() and hora_num < 12:
                    hora_num += 12
                elif 'am' in hora_seleccionada.lower() and hora_num == 12:
                    hora_num = 0
                hora_normalizada = f"{hora_num:02d}:00"
            else:
                hora_normalizada = hora_seleccionada
            
            if hora_normalizada in horas_disponibles:
                datos["hora"] = hora_normalizada
                agendamientos_temp[cliente_id] = datos
                # Pasar directamente a pedir email
                respuesta_texto = "Perfecto. Por último, ¿cuál es tu correo electrónico?"
                return respuesta_texto, agendamientos_temp
            else:
                respuesta_texto = f"La hora {hora_seleccionada} no está disponible. Horarios: {', '.join(horas_disponibles)}. ¿Cuál prefieres?"
                return respuesta_texto, agendamientos_temp
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí la hora.")
            horas_disponibles = datos.get("horas_disponibles", [])
            respuesta_texto = f"{respuesta_rag}\n\nPara {datos['fecha']} tenemos: {', '.join(horas_disponibles)}. ¿Cuál prefieres?"
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 4: PEDIR EMAIL
    # ==============================================
    if not datos["email"]:
        # Verificar si el mensaje contiene un email
        import re
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_mensaje)
        if email_match:
            datos["email"] = email_match.group(0)
            agendamientos_temp[cliente_id] = datos
            # Ir a agendar
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        
        # Si no es un email, clasificar si es interrupción
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "email", historial)
        
        if clasificacion.get("es_valido"):
            datos["email"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu correo.")
            # No repetir la pregunta del email si ya la hemos hecho antes
            respuesta_texto = f"{respuesta_rag}"
            # Solo añadir la pregunta si no está ya incluida en la respuesta del RAG
            if "correo" not in respuesta_rag.lower() and "email" not in respuesta_rag.lower():
                respuesta_texto += "\n\nPor cierto, para completar el agendamiento, necesito tu correo electrónico."
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 5: AGENDAR
    # ==============================================
    try:
        ecuador = pytz.timezone("America/Guayaquil")
        año, mes, dia = map(int, datos["fecha"].split('-'))
        hora, minuto = map(int, datos["hora"].split(':'))
        fecha_hora_cita = ecuador.localize(datetime.datetime(año, mes, dia, hora, minuto))
        
        resultado = agendar_cita(
            event_type_id=1288606,
            cliente_nombre=datos["nombre"],
            cliente_email=datos["email"],
            hora=fecha_hora_cita
        )
        
        if resultado.get("exito"):
            respuesta_texto = f"✅ ¡Cita agendada para {datos['fecha']} a las {datos['hora']}! Te enviaremos confirmación a {datos['email']}."
            del agendamientos_temp[cliente_id]
        else:
            respuesta_texto = f"❌ Error: {resultado.get('error')}. Intenta de nuevo."
            del agendamientos_temp[cliente_id]
    except Exception as e:
        respuesta_texto = f"❌ Error: {str(e)}. Intenta de nuevo."
        del agendamientos_temp[cliente_id]
    
    return respuesta_texto, agendamientos_temp