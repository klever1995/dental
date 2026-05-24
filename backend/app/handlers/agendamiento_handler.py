import datetime
import pytz
import re
from app.services.google_calendar import obtener_slots_disponibles, agendar_cita, obtener_citas_cliente_por_cedula
from openai import OpenAI
import os
from sqlalchemy.orm import Session

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
    agendamientos_temp: dict,
    especialidad: str = None
) -> tuple:
    """
    Maneja el flujo de agendamiento con manejo de interrupciones.
    Retorna (respuesta_texto, agendamientos_temp_actualizado)
    """
    # Importar SessionLocal dentro de la función para evitar conflictos
    from app.db.base import SessionLocal
    from app.models.especialidad import Especialidad
    from app.models.cliente import Cliente
    
    # Obtener o crear datos temporales
    if cliente_id not in agendamientos_temp:
        agendamientos_temp[cliente_id] = {
            "nombre": nombre,
            "cedula": None,
            "especialidad": especialidad,
            "calendar_id": None,  # 🔥 CAMBIADO: ahora calendar_id
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
        if especialidad and not datos.get("especialidad"):
            datos["especialidad"] = especialidad
    
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
            respuesta_texto = "Gracias. Por favor, ingresa tu número de cédula (solo números)."
            return respuesta_texto, agendamientos_temp
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu nombre.")
            return respuesta_rag, agendamientos_temp
    
    # ==============================================
    # PASO 2: PEDIR CÉDULA
    # ==============================================
    if not datos.get("cedula"):
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "cedula", historial)
        
        if clasificacion.get("es_valido"):
            datos["cedula"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            if datos.get("especialidad"):
                respuesta_texto = "Gracias. ¿Para qué día quieres la cita? (ej: mañana, lunes)"
            else:
                # Consultar especialidades desde base de datos
                db_temp = SessionLocal()
                especialidades_activas = db_temp.query(Especialidad).filter(
                    Especialidad.activa == True,
                    Especialidad.empresa_id == 1
                ).all()
                db_temp.close()
                lista_especialidades = ", ".join([esp.nombre for esp in especialidades_activas])
                respuesta_texto = f"Gracias. ¿Para qué especialidad necesitas la cita? ({lista_especialidades})"
            return respuesta_texto, agendamientos_temp
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu cédula.")
            return respuesta_rag, agendamientos_temp

    # ==============================================
    # PASO 2.5: PEDIR ESPECIALIDAD (solo si no vino del RAG)
    # ==============================================
    if not datos.get("especialidad"):
        import unicodedata
        
        def quitar_tildes(texto: str) -> str:
            return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        
        especialidad_detectada = None
        texto_mensaje_normalizado = quitar_tildes(texto_mensaje.lower())
        
        db = SessionLocal()
        especialidades_bd = db.query(Especialidad).filter(
            Especialidad.activa == True,
            Especialidad.empresa_id == 1
        ).all()
        db.close()
        
        especialidades_validas = []
        for esp in especialidades_bd:
            nombre_normalizado = quitar_tildes(esp.nombre.lower())
            especialidades_validas.append((nombre_normalizado, esp.nombre, esp.calendar_id))  # 🔥 calendar_id
        
        for nombre_norm, nombre_original, cal_id in especialidades_validas:
            if nombre_norm in texto_mensaje_normalizado or texto_mensaje_normalizado in nombre_norm:
                especialidad_detectada = nombre_original
                datos["calendar_id"] = cal_id
                break
        
        if especialidad_detectada:
            datos["especialidad"] = especialidad_detectada
            agendamientos_temp[cliente_id] = datos
            respuesta_texto = f"Perfecto, especialidad {especialidad_detectada}. ¿Para qué día quieres la cita? (ej: mañana, lunes)"
            return respuesta_texto, agendamientos_temp
        else:
            lista_esps = ", ".join([esp.nombre for esp in especialidades_bd])
            respuesta_texto = f"No entendí la especialidad. Las especialidades disponibles son: {lista_esps}. ¿Cuál necesitas?"
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 3: PEDIR FECHA
    # ==============================================
    if not datos.get("fecha"):
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "fecha", historial)
        
        if clasificacion.get("es_valido"):
            datos["fecha"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí la fecha.")
            return respuesta_rag, agendamientos_temp
    
    # ==============================================
    # PASO 4: PEDIR HORA (mostrar horarios disponibles)
    # ==============================================
    if not datos.get("hora"):
        if "horas_disponibles" not in datos:
            if not datos.get("calendar_id"):
                db = SessionLocal()
                esp_obj = db.query(Especialidad).filter(
                    Especialidad.nombre.ilike(datos["especialidad"]),
                    Especialidad.activa == True
                ).first()
                if esp_obj:
                    datos["calendar_id"] = esp_obj.calendar_id
                db.close()
            
            # 🔥 OBTENER SLOTS CON calendar_id
            slots = obtener_slots_disponibles(
                calendar_id=datos["calendar_id"],  # 🔥 CAMBIADO
                fecha_inicio=datos["fecha"],
                dias_a_mostrar=1
            )
            if slots.get("exito") and slots.get("slots_por_fecha"):
                slots_dia = slots["slots_por_fecha"].get(datos["fecha"], [])
                # En la nueva versión, slots_dia es una lista de strings
                horas = slots_dia
                if horas:
                    datos["horas_disponibles"] = horas
                    agendamientos_temp[cliente_id] = datos
                    respuesta_texto = f"Para {datos['fecha']} (especialidad {datos['especialidad']}) tenemos: {', '.join(horas)}. ¿Cuál prefieres?"
                    return respuesta_texto, agendamientos_temp
                else:
                    respuesta_texto = f"No hay horarios disponibles para {datos['fecha']} en {datos['especialidad']}. ¿Otra fecha?"
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
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp, datos.get("especialidad")
            )
        
        clasificacion = rag.clasificar_respuesta_flujo(texto_mensaje, "email", historial)
        
        if clasificacion.get("es_valido"):
            datos["email"] = clasificacion.get("dato_extraido")
            agendamientos_temp[cliente_id] = datos
            return await manejar_agendamiento(
                cliente_id, None, None, None, None, texto_mensaje, rag, historial, agendamientos_temp, datos.get("especialidad")
            )
        else:
            respuesta_rag = clasificacion.get("respuesta_rag", "No entendí tu correo.")
            respuesta_texto = f"{respuesta_rag}"
            if "correo" not in respuesta_rag.lower() and "email" not in respuesta_rag.lower():
                respuesta_texto += "\n\nPor cierto, para completar el agendamiento, necesito tu correo electrónico."
            return respuesta_texto, agendamientos_temp
    
    # ==============================================
    # PASO 6: VALIDAR UNICIDAD POR CÉDULA Y AGENDAR
    # ==============================================
    try:
        cedula_actual = datos["cedula"]
        fecha_seleccionada = datos["fecha"]
        hora_seleccionada = datos["hora"]
        
        # Consultar todas las citas del cliente (sin filtrar por calendario)
        citas_cliente = obtener_citas_cliente_por_cedula(cedula_actual)
        if citas_cliente.get("exito"):
            for cita in citas_cliente.get("citas", []):
                fecha_cita_str = cita.get("fecha")
                if fecha_cita_str:
                    fecha_cita_obj = datetime.datetime.fromisoformat(fecha_cita_str)
                    fecha_cita = fecha_cita_obj.strftime("%Y-%m-%d")
                    hora_cita = fecha_cita_obj.strftime("%H:%M")
                    
                    if fecha_cita == fecha_seleccionada and hora_cita == hora_seleccionada:
                        respuesta_texto = f"⚠️ Ya tienes una cita agendada para {fecha_seleccionada} a las {hora_seleccionada} con tu cédula {cedula_actual}. No puedes agendar dos citas a la misma hora. Por favor, elige otro horario."
                        datos["hora"] = None
                        datos["horas_disponibles"] = None
                        agendamientos_temp[cliente_id] = datos
                        return respuesta_texto, agendamientos_temp
        
        ecuador = pytz.timezone("America/Guayaquil")
        año, mes, dia = map(int, datos["fecha"].split('-'))
        hora, minuto = map(int, datos["hora"].split(':'))
        fecha_hora_cita = ecuador.localize(datetime.datetime(año, mes, dia, hora, minuto))
        
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
        
        # 🔥 AGENDAR CON calendar_id
        resultado = agendar_cita(
            calendar_id=datos["calendar_id"],  # 🔥 CAMBIADO
            cliente_nombre=datos["nombre"],
            cliente_email=datos["email"],
            cliente_cedula=datos["cedula"],
            cliente_telefono=telefono_cliente,
            hora=fecha_hora_cita,
            notas_adicionales=notas_adicionales
        )
        
        if resultado.get("exito"):
            respuesta_texto = f"✅ ¡Cita agendada para {datos['fecha']} a las {datos['hora']} para {datos['especialidad']}! Te enviaremos confirmación a {datos['email']}."
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