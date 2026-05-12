import datetime
import pytz
import re
from app.services.calcom import obtener_slots_disponibles, agendar_cita
from openai import OpenAI
import os

# Inicializar cliente de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
            "cedula": None,
            "fecha": fecha,
            "hora": hora,
            "email": email,
            "activo": True
        }
    else:
        datos = agendamientos_temp[cliente_id]
        if nombre and not datos.get("nombre"):
            datos["nombre"] = nombre
        if fecha and not datos.get("fecha"):
            datos["fecha"] = fecha
        if hora and not datos.get("hora"):
            datos["hora"] = hora
        if email and not datos.get("email"):
            datos["email"] = email
    
    datos = agendamientos_temp[cliente_id]
    respuesta_texto = ""
    
    # ==============================================
    # PASO 1: PEDIR NOMBRE
    # ==============================================
    if not datos.get("nombre"):
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "nombre", historial)
        
        if clasificacion.get("es_valido"):
            datos["nombre"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            # ✅ CORREGIDO: No llamar recursivamente, retornar pregunta siguiente
            respuesta_texto = "Gracias. Por favor, ingresa tu número de cédula (solo números)."
            return respuesta_texto, agendamientos_temp
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu nombre.")
            # ✅ CORREGIDO: No concatenar texto extra, solo la respuesta RAG
            return respuesta_rag, agendamientos_temp
    
    # ==============================================
    # PASO 2: PEDIR CÉDULA
    # ==============================================
    if not datos.get("cedula"):
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "cedula", historial)
        
        if clasificacion.get("es_valido"):
            datos["cedula"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            # ✅ CORREGIDO: No llamar recursivamente
            respuesta_texto = "Gracias. ¿Para qué día quieres la cita? (ej: mañana, lunes)"
            return respuesta_texto, agendamientos_temp
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu cédula.")
            return respuesta_rag, agendamientos_temp
    
    # ==============================================
    # PASO 3: PEDIR FECHA
    # ==============================================
    if not datos.get("fecha"):
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "fecha", historial)
        
        if clasificacion.get("es_valido"):
            datos["fecha"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            # ✅ CORREGIDO: No llamar recursivamente, continuar con la lógica de horarios
            # Continuamos al siguiente paso (mostrar horarios) sin recursión
            pass
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí la fecha.")
            return respuesta_rag, agendamientos_temp
    
    # ==============================================
    # PASO 4: PEDIR HORA (mostrar horarios disponibles)
    # ==============================================
    if not datos.get("hora"):
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
        
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "hora", historial)
        
        if clasificacion.get("es_valido"):
            hora_seleccionada = clasificacion.get("dato_extraido")
            horas_disponibles = datos.get("horas_disponibles", [])
            
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
    # PASO 5: PEDIR EMAIL
    # ==============================================
    if not datos.get("email"):
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', texto_mensaje)
        if email_match:
            datos["email"] = email_match.group(0)
            agendamientos_temp[cliente_id] = datos
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "email", historial)
        
        if clasificacion.get("es_valido"):
            datos["email"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp
            )
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu correo.")
            respuesta_texto = f"{respuesta_rag}"
            if "correo" not in respuesta_rag.lower() and "email" not in respuesta_rag.lower():
                respuesta_texto += "\n\nPor cierto, para completar el agendamiento, necesito tu correo electrónico."
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 6: AGENDAR
    # ==============================================
    try:
        ecuador = pytz.timezone("America/Guayaquil")
        año, mes, dia = map(int, datos["fecha"].split('-'))
        hora, minuto = map(int, datos["hora"].split(':'))
        fecha_hora_cita = ecuador.localize(datetime.datetime(año, mes, dia, hora, minuto))
        
        from app.models.cliente import Cliente
        from app.db.base import SessionLocal
        db = SessionLocal()
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        telefono_cliente = cliente.telefono if cliente else None
        
        notas_adicionales = None
        try:
            if rag and cliente_id:
                historial_completo = rag.obtener_historial_reciente(limite=20)
                lineas = historial_completo.split("\n")
                mensajes_cliente = [linea.replace("Cliente: ", "") for linea in lineas if linea.startswith("Cliente: ")]
                historial_cliente = "\n".join(mensajes_cliente)
                if historial_cliente.strip():
                    prompt_resumen = f"""Extrae un resumen corto (máximo 200 caracteres) de lo que el cliente ha dicho sobre su problema dental o servicio requerido. Ignora saludos, despedidas y frases de agradecimiento. Si no hay información relevante, responde "Sin observaciones".

                    Historial del cliente:
                    {historial_cliente}

                    Resumen:"""
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": prompt_resumen}],
                        temperature=0.3,
                        max_tokens=100
                    )
                    notas_adicionales = response.choices[0].message.content.strip()
                    if notas_adicionales == "Sin observaciones" or not notas_adicionales:
                        notas_adicionales = None
        except Exception as e:
            print(f"⚠️ Error generando resumen: {e}")
        
        db.close()
        
        resultado = agendar_cita(
            event_type_id=1288606,
            cliente_nombre=datos["nombre"],
            cliente_email=datos["email"],
            cliente_cedula=datos["cedula"],
            cliente_telefono=telefono_cliente,
            hora=fecha_hora_cita,
            notas_adicionales=notas_adicionales
        )
        
        if resultado.get("exito"):
            respuesta_texto = f"✅ ¡Cita agendada para {datos['fecha']} a las {datos['hora']}! Te enviaremos confirmación a {datos['email']}."
            db = SessionLocal()
            cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
            if cliente:
                if not cliente.datos_estructurados:
                    cliente.datos_estructurados = {}
                cliente.datos_estructurados["cedula"] = datos["cedula"]
                db.add(cliente)
                db.commit()
            db.close()
            del agendamientos_temp[cliente_id]
        else:
            respuesta_texto = f"❌ Error: {resultado.get('error')}. Intenta de nuevo."
            del agendamientos_temp[cliente_id]
    except Exception as e:
        respuesta_texto = f"❌ Error: {str(e)}. Intenta de nuevo."
        del agendamientos_temp[cliente_id]
    
    return respuesta_texto, agendamientos_temp