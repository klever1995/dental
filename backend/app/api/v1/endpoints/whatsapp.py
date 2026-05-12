from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import os
import datetime
import requests
from groq import Groq
from app.db.base import get_db
from app.models.empresa import Empresa
from app.models.cliente import Cliente
from app.models.conversacion import Conversacion, TipoEmisor
from app.services.rag import RAGService
from app.services.memoria import MemoriaService
from app.services.whatsapp_sender import enviar_mensaje_whatsapp
from app.services.calcom import obtener_slots_disponibles, agendar_cita, obtener_citas_cliente_por_cedula, eliminar_cita, reagendar_cita
from app.handlers.horarios_handler import manejar_horarios
from app.handlers.agendamiento_handler import manejar_agendamiento
from app.handlers.cancelacion_handler import manejar_cancelacion
from app.handlers.reagendamiento_handler import manejar_reagendamiento
import pytz
import re

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Diccionario temporal para guardar datos de agendamiento y cancelación por cliente
agendamientos_temp = {}

def transcribir_audio(url_audio: str) -> str:
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        headers = {"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}
        response = requests.get(url_audio, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error descargando audio: {response.status_code}")
        archivo = ("audio.ogg", response.content, "audio/ogg")
        transcripcion = client.audio.transcriptions.create(
            file=archivo,
            model="whisper-large-v3",
            response_format="text"
        )
        return transcripcion
    except Exception as e:
        print(f"❌ Error en transcripción: {e}")
        return "[Error al transcribir el audio]"

def extraer_cedula(mensaje: str) -> str:
    """Extrae un número de cédula de 6 a 10 dígitos del mensaje"""
    match = re.search(r'\b(\d{6,10})\b', mensaje)
    return match.group(1) if match else None

@router.post("/webhook")
async def webhook_whatsapp(request: Request, db: Session = Depends(get_db)):
    global agendamientos_temp
    try:
        body = await request.json()
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            return {"status": "ok", "message": "Sin mensajes"}
        
        print("📩 Mensaje recibido:", body)
        print(f"🔍 [ORIGEN] User-Agent: {request.headers.get('user-agent', '')} | IP: {request.client.host}")
        
        msg = messages[0]
        print(f"📌 [TIMESTAMP] {msg.get('timestamp')} - Texto: {msg.get('text', {}).get('body', '')[:50]}")
        
        timestamp_msg = int(msg.get("timestamp", 0))
        timestamp_actual = int(datetime.datetime.now().timestamp())
        if timestamp_actual - timestamp_msg > 30:
            print(f"⏰ Mensaje antiguo ignorado: timestamp={timestamp_msg}, actual={timestamp_actual}")
            return {"status": "ok", "message": "Mensaje antiguo ignorado"}
        
        telefono_cliente = msg.get("from")
        tipo_mensaje = msg.get("type", "text")
        texto_mensaje = ""
        audio_url = None
        
        if tipo_mensaje == "text":
            texto_mensaje = msg.get("text", {}).get("body", "")
            print(f"📝 Texto recibido: '{texto_mensaje}'")
        elif tipo_mensaje == "audio":
            audio_data = msg.get("audio", {})
            audio_url = audio_data.get("url")
            if audio_url:
                texto_mensaje = "🎤 [El cliente envió un audio]"
        
        metadata = value.get("metadata", {})
        telefono_empresa = metadata.get("display_phone_number", "").replace("+", "")
        
        if not telefono_cliente or not texto_mensaje:
            return {"status": "ok", "message": "Mensaje sin contenido"}
        
        empresa = db.query(Empresa).filter(
            Empresa.telefono_whatsapp == telefono_empresa,
            Empresa.activa == True
        ).first()
        
        if not empresa:
            print(f"⚠️ Empresa no encontrada")
            return {"status": "ok", "message": "Empresa no identificada"}
        
        cliente = db.query(Cliente).filter(
            Cliente.empresa_id == empresa.id,
            Cliente.telefono == telefono_cliente
        ).first()
        
        if not cliente:
            cliente = Cliente(
                empresa_id=empresa.id,
                telefono=telefono_cliente,
                nombre=msg.get("profile", {}).get("name", ""),
                resumen="Cliente nuevo",
                datos_estructurados={}
            )
            db.add(cliente)
            db.commit()
            db.refresh(cliente)
        
        if audio_url:
            try:
                transcripcion = transcribir_audio(audio_url)
                texto_mensaje = f"🎤 [Audio transcrito]: {transcripcion}"
            except Exception as e:
                print(f"❌ Error en audio: {e}")
                texto_mensaje = "🎤 [Error al procesar el audio]"
        
        mensaje_cliente = Conversacion(
            cliente_id=cliente.id,
            mensaje=texto_mensaje,
            emisor=TipoEmisor.CLIENTE
        )
        db.add(mensaje_cliente)
        db.commit()
        
        rag = RAGService(db, empresa.id, cliente.id)
        memoria = MemoriaService(db, cliente.id)
        
        email = None
        fecha = None
        hora = None
        nombre = None
        booking_id = None
        historial = ""
        
        if cliente.id in agendamientos_temp and agendamientos_temp[cliente.id].get("flow") in ["CANCELAR", "REAGENDAR"]:
            flow = agendamientos_temp[cliente.id].get("flow")
            print(f"🔍 [FLUJO ACTIVO] {flow} - procesando sin RAG")
            
            if flow == "CANCELAR":
                respuesta_texto, agendamientos_temp = await manejar_cancelacion(
                    cliente_id=cliente.id,
                    email=email,
                    texto_mensaje=texto_mensaje,
                    fecha=fecha,
                    cliente=cliente,
                    db=db,
                    rag=rag,
                    historial=historial,
                    agendamientos_temp=agendamientos_temp
                )
            elif flow == "REAGENDAR":
                respuesta_texto, agendamientos_temp = await manejar_reagendamiento(
                    cliente_id=cliente.id,
                    email=email,
                    texto_mensaje=texto_mensaje,
                    fecha=fecha,
                    hora=hora,
                    cliente=cliente,
                    db=db,
                    rag=rag,
                    historial=historial,
                    booking_id=booking_id,
                    agendamientos_temp=agendamientos_temp
                )
            
            if respuesta_texto:
                print(f"🔍 [RESPUESTA] {respuesta_texto[:100]}...")
                mensaje_bot = Conversacion(
                    cliente_id=cliente.id,
                    mensaje=respuesta_texto,
                    emisor=TipoEmisor.BOT
                )
                db.add(mensaje_bot)
                db.commit()
                enviar_mensaje_whatsapp(
                    telefono_destino=telefono_cliente,
                    mensaje=respuesta_texto
                )
                memoria.actualizar_resumen(texto_mensaje, respuesta_texto)
                return {"status": "ok", "cliente_id": cliente.id}
        
        historial_mensajes = db.query(Conversacion).filter(
            Conversacion.cliente_id == cliente.id
        ).order_by(Conversacion.timestamp.desc()).limit(5).all()
        historial_mensajes.reverse()
        historial = "\n".join([f"{m.emisor.value}: {m.mensaje}" for m in historial_mensajes])
        
        analisis = rag.extraer_intencion_y_fecha(texto_mensaje, historial)
        print(f"🔍 [ANÁLISIS] {analisis}")
        
        intencion = analisis.get("intencion", "OTRO")
        fecha = analisis.get("fecha")
        hora = analisis.get("hora")
        nombre = analisis.get("nombre")
        booking_id = analisis.get("booking_id")
        
        respuesta_texto = ""
        
        if intencion == "HORARIOS" and fecha:
            respuesta_texto = await manejar_horarios(fecha)
        
        # ==============================================
        # CONSULTAR CITAS POR CÉDULA (migrado)
        # ==============================================
        elif intencion == "CONSULTAR_CITAS":
            cedula_cliente = None
            # Intentar extraer cédula del mensaje
            cedula_match = re.search(r'\b(\d{6,10})\b', texto_mensaje)
            if cedula_match:
                cedula_cliente = cedula_match.group(1)
            elif cliente.datos_estructurados and cliente.datos_estructurados.get("cedula"):
                cedula_cliente = cliente.datos_estructurados.get("cedula")
            else:
                if cliente.id not in agendamientos_temp:
                    agendamientos_temp[cliente.id] = {"esperando_cedula_consulta": True}
                respuesta_texto = "Para consultar tus citas, necesito tu número de cédula. ¿Cuál es tu cédula?"
            
            if cedula_cliente:
                if not cliente.datos_estructurados or not cliente.datos_estructurados.get("cedula"):
                    if not cliente.datos_estructurados:
                        cliente.datos_estructurados = {}
                    cliente.datos_estructurados["cedula"] = cedula_cliente
                    db.add(cliente)
                    db.commit()
                
                # Usar la nueva función por cédula
                citas_resultado = obtener_citas_cliente_por_cedula(cedula_cliente)
                if citas_resultado.get("exito"):
                    citas = citas_resultado.get("citas", [])
                    if citas:
                        agendamientos_temp[cliente.id] = {"citas": citas, "cedula": cedula_cliente}
                        lista_citas = []
                        for i, cita in enumerate(citas, 1):
                            fecha_iso = cita["fecha"]
                            fecha_obj = datetime.datetime.fromisoformat(fecha_iso)
                            fecha_legible = fecha_obj.strftime("%d/%m/%Y")
                            hora_legible = fecha_obj.strftime("%H:%M")
                            lista_citas.append(f"{i}. 📅 {fecha_legible} a las {hora_legible}")
                        respuesta_texto = "📋 *Tus citas agendadas:*\n\n" + "\n".join(lista_citas)
                        respuesta_texto += "\n\n¿Qué deseas hacer? Responde 'cancelar 1' o 'reagendar 1' (ej: 'cancelar 1' o 'reagendar 1')."
                    else:
                        respuesta_texto = "No tienes citas futuras agendadas."
                else:
                    respuesta_texto = f"No pude consultar tus citas: {citas_resultado.get('error')}. Por favor, intenta de nuevo más tarde."
        
        elif intencion == "AGENDAR" or (cliente.id in agendamientos_temp and agendamientos_temp[cliente.id].get("activo")):
            respuesta_texto, agendamientos_temp = await manejar_agendamiento(
                cliente_id=cliente.id,
                nombre=nombre,
                fecha=fecha,
                hora=hora,
                email=email,
                texto_mensaje=texto_mensaje,
                rag=rag,
                historial=historial,
                agendamientos_temp=agendamientos_temp
            )
        
        elif intencion == "CANCELAR":
            respuesta_texto, agendamientos_temp = await manejar_cancelacion(
                cliente_id=cliente.id,
                email=email,
                texto_mensaje=texto_mensaje,
                fecha=fecha,
                cliente=cliente,
                db=db,
                rag=rag,
                historial=historial,
                agendamientos_temp=agendamientos_temp
            )
        
        elif intencion == "REAGENDAR":
            respuesta_texto, agendamientos_temp = await manejar_reagendamiento(
                cliente_id=cliente.id,
                email=email,
                texto_mensaje=texto_mensaje,
                fecha=fecha,
                hora=hora,
                cliente=cliente,
                db=db,
                rag=rag,
                historial=historial,
                booking_id=booking_id,
                agendamientos_temp=agendamientos_temp
            )
        
        else:
            documentos = rag.buscar_similares(texto_mensaje, top_k=3)
            contexto = "\n\n".join([doc["texto"] for doc in documentos])
            resumen = memoria.obtener_resumen()
            respuesta_texto = rag.generar_respuesta_con_texto(
                consulta=texto_mensaje,
                contexto=contexto,
                resumen_cliente=resumen
            )
            if audio_url:
                respuesta_texto = f"🎤 He recibido tu audio. {respuesta_texto}"
        
        if not respuesta_texto:
            respuesta_texto = "¿En qué puedo ayudarte?"
        
        print(f"🔍 [RESPUESTA] {respuesta_texto[:100]}...")
        
        mensaje_bot = Conversacion(
            cliente_id=cliente.id,
            mensaje=respuesta_texto,
            emisor=TipoEmisor.BOT
        )
        db.add(mensaje_bot)
        db.commit()
        
        enviar_mensaje_whatsapp(
            telefono_destino=telefono_cliente,
            mensaje=respuesta_texto
        )
        
        memoria.actualizar_resumen(texto_mensaje, respuesta_texto)
        
        return {"status": "ok", "cliente_id": cliente.id}
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@router.get("/webhook")
async def verificar_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "mi_token_secreto")
    if mode == "subscribe" and token == verify_token:
        return int(challenge)
    raise HTTPException(status_code=403, detail="Verificación fallida")
