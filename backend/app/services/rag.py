# ==============================
# Servicio RAG (Retrieval-Augmented Generation)
# Embeddings, búsqueda semántica, generación de respuestas y sincronización de especialidades
# ==============================
import os 
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session
from openai import OpenAI
from PyPDF2 import PdfReader
from io import BytesIO
import hashlib
import json
from datetime import datetime
import pytz

# Inicializar cliente de OpenAI estándar
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")

class RAGService:
    def __init__(self, db: Session, empresa_id: int, cliente_id: int = None):
        self.db = db
        self.empresa_id = empresa_id
        self.cliente_id = cliente_id
        self.DOCUMENTO_ESPECIALIDADES_ID = 9999  

# ==============================
# Obtener historial reciente de conversación (últimos N mensajes)
# ==============================    
    def obtener_historial_reciente(self, limite: int = 20) -> str:
        """Obtiene los últimos mensajes de la conversación actual"""
        if not self.cliente_id:
            return ""
        
        from app.models.conversacion import Conversacion, TipoEmisor
        
        mensajes = self.db.query(Conversacion).filter(
            Conversacion.cliente_id == self.cliente_id
        ).order_by(Conversacion.timestamp.desc()).limit(limite).all()
        
        mensajes.reverse()
        
        historial = []
        for msg in mensajes:
            emisor = "Cliente" if msg.emisor == TipoEmisor.CLIENTE else "Bot"
            historial.append(f"{emisor}: {msg.mensaje}")
        
        return "\n".join(historial)
    
# ==============================
# Extraer intención, fecha, hora, nombre, especialidad y booking_id del mensaje
# ==============================    
    def extraer_intencion_y_fecha(self, mensaje: str, historial: str = "") -> dict:

        ecuador = pytz.timezone("America/Guayaquil")
        hoy = datetime.now(ecuador).strftime("%Y-%m-%d")
        
        prompt = f"""Eres un asistente que analiza mensajes de clientes de una clínica médica con múltiples especialidades.

Hoy es {hoy}.

Analiza el siguiente mensaje y devuelve SOLO un JSON con estos campos:

{{
    "intencion": "HORARIOS" | "AGENDAR" | "CANCELAR" | "REAGENDAR" | "CONSULTAR_CITAS" | "INFO" | "OTRO",
    "fecha": "YYYY-MM-DD" o null,
    "hora": "HH:MM" o null,
    "nombre": "nombre extraído" o null,
    "especialidad": "nombre de la especialidad médica" o null,
    "booking_id": null o número entero
}}

REGLAS IMPORTANTES:

1. EXTRACCIÓN DE NOMBRE:
- SOLO extrae un nombre si es claramente un nombre propio de persona.
- NO extraigas como nombre palabras como: "abuela", "mamá", "papá", "tío", "mi hermano", etc.
- Si el usuario dice "para mi abuela", el campo "nombre" DEBE ser null.
- Si el usuario dice "soy Klever" o "me llamo Ana", SÍ extrae el nombre.

2. EXTRACCIÓN DE ESPECIALIDAD (NUEVO - INFERENCIA SEMÁNTICA):
- Extrae la especialidad médica que el usuario menciona o SUGIERE por síntomas.
- Ejemplos de palabras clave y su especialidad asociada:
  * "muela", "diente", "dentista", "limpieza dental", "caries" → "odontologia"
  * "niño", "pediatra", "vacunas infantiles" → "pediatria"
  * "estómago", "digestión", "gastro", "acidez" → "gastroenterologia"
  * "corazón", "pecho", "presión arterial", "cardiólogo" → "cardiologia"
  * "piel", "alergia", "sarpullido", "dermatólogo" → "dermatologia"
  * "hueso", "fractura", "esguince", "traumatólogo" → "traumatologia"
- Si el usuario dice explícitamente "para cardiología" → "cardiologia"
- Si el usuario dice "me duele el pecho" → infiere "cardiologia"
- Si el usuario dice "me duele la muela" → infiere "odontologia"
- Si no hay indicios, devuelve null.

3. INTENCIÓN:
- "AGENDAR": si el usuario quiere agendar una cita (explícita o implícitamente).
- "HORARIOS": si pregunta por disponibilidad de horarios.
- "CANCELAR": si quiere cancelar una cita.
- "REAGENDAR": si quiere reagendar/cambiar una cita.
- "CONSULTAR_CITAS": si pregunta por sus citas agendadas.
- "INFO": si pregunta por información general (precios, ubicación).
- "OTRO": cualquier otra cosa.

4. FECHAS: entiende expresiones como "martes de la próxima semana", "mañana", "31 de marzo".

Historial reciente:
{historial}

Mensaje: "{mensaje}"

RESPONDE SOLO EL JSON, sin texto adicional."""
        
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        try:
            resultado = json.loads(response.choices[0].message.content)

            if "especialidad" not in resultado:
                resultado["especialidad"] = None
            return resultado
        except:
            return {"intencion": "OTRO", "fecha": None, "hora": None, "nombre": None, "especialidad": None, "booking_id": None}
        
# ==============================
# Clasificar respuesta dentro de un flujo (agendamiento, cancelación, etc.)
# ==============================    
    def clasificar_respuesta_flujo(self, mensaje: str, paso_actual: str, historial: str = "") -> dict:

        ecuador = pytz.timezone("America/Guayaquil")
        hoy = datetime.now(ecuador).strftime("%Y-%m-%d")
        
        prompt = f"""Eres un asistente que analiza mensajes de clientes durante un proceso de agendamiento de citas.

Hoy es {hoy}.

El bot está actualmente pidiendo al cliente: "{paso_actual}"

Analiza el siguiente mensaje del cliente y determina si está respondiendo directamente a lo que se le pide o si está haciendo una pregunta o comentario fuera del flujo.

Devuelve SOLO un JSON con estos campos:
{{
    "es_valido": true/false,
    "dato_extraido": "el valor si responde a lo pedido, sino null",
    "respuesta_rag": "si es inválido, una respuesta amable y útil usando el contexto"
}}

Ejemplos:
- Paso "nombre", mensaje "Klever Robalino" → válido, extrae "Klever Robalino"
- Paso "nombre", mensaje "¿Cuánto cuesta una limpieza?" → inválido, respuesta_rag con info de precios
- Paso "fecha", mensaje "mañana" → válido, extrae "2026-04-06"
- Paso "fecha", mensaje "¿Atienden sábados?" → inválido, respuesta_rag con horarios
- Paso "email", mensaje "Mi correo es klever@mail.com" → válido, extrae "klever@mail.com"
- Paso "email", mensaje "Espera un momento" → inválido, respuesta_rag amable

Historial reciente:
{historial}

Mensaje: "{mensaje}"

RESPONDE SOLO EL JSON, sin texto adicional."""
        
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        try:
            resultado = json.loads(response.choices[0].message.content)
            return resultado
        except:
            return {"es_valido": False, "dato_extraido": None, "respuesta_rag": "Lo siento, no entendí. ¿Podrías repetirlo?"}

# ==============================
# Generar respuesta conversacional con contexto RAG
# ==============================    
    def generar_respuesta_con_texto(self, consulta: str, contexto: str, resumen_cliente: str = "") -> str:

        historial = self.obtener_historial_reciente()
        
        system_prompt = f"""Eres un asistente virtual de una clínica dental llamada Sonrisa Dental Center.
Tu nombre es Aurelia.

Usa la siguiente información de la clínica para responder preguntas generales:
{contexto}

Historial del paciente: {resumen_cliente}

Conversación reciente:
{historial}

Instrucciones:
- Responde preguntas sobre la clínica (horarios de atención, servicios, precios, ubicación, políticas).
- Sé amable, natural y profesional.
- Responde en español.
- Si no sabes algo, di que consultarás con un asesor."""
        
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": consulta}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content
    
# ==============================
# Sincronizar especialidades como chunks RAG (documento virtual)
# ==============================
    def sincronizar_especialidades(self):

        from app.models.especialidad import Especialidad
        from app.models.documento import ChunkDocumento
        
        # Verificar que el documento especial existe; si no, crearlo
        from app.models.documento import Documento
        doc_especial = self.db.query(Documento).filter(Documento.id == self.DOCUMENTO_ESPECIALIDADES_ID).first()
        if not doc_especial:
            doc_especial = Documento(
                id=self.DOCUMENTO_ESPECIALIDADES_ID,
                empresa_id=self.empresa_id,
                nombre="especialidades",
                hash_contenido="especialidades_static"
            )
            self.db.add(doc_especial)
            self.db.commit()
        
        # Eliminar chunks antiguos de especialidades
        self.db.query(ChunkDocumento).filter(
            ChunkDocumento.documento_id == self.DOCUMENTO_ESPECIALIDADES_ID
        ).delete()
        
        # Obtener todas las especialidades activas de esta empresa
        especialidades = self.db.query(Especialidad).filter(
            Especialidad.empresa_id == self.empresa_id,
            Especialidad.activa == True
        ).all()
        
        # Crear nuevos chunks por cada especialidad
        for idx, esp in enumerate(especialidades):
            # Construir texto del chunk
            texto_chunk = f"""Especialidad: {esp.nombre}
Descripción: {esp.descripcion or f'{esp.nombre.capitalize()} es una especialidad médica disponible en la clínica.'}
Esta especialidad está activa y se pueden agendar citas consultando los horarios disponibles."""
            
            # Generar embedding
            embedding = self.generar_embedding(texto_chunk)
            
            # Guardar chunk
            chunk = ChunkDocumento(
                documento_id=self.DOCUMENTO_ESPECIALIDADES_ID,
                indice=idx,
                texto=texto_chunk,
                embedding=embedding
            )
            self.db.add(chunk)
        
        self.db.commit()
        print(f"✅ Sincronizadas {len(especialidades)} especialidades como chunks RAG")
    
# ==============================
# Extraer texto de un PDF
# ==============================
    def extraer_texto_pdf(self, archivo_bytes: bytes) -> str:
        texto = ""
        pdf = PdfReader(BytesIO(archivo_bytes))
        for pagina in pdf.pages:
            texto += pagina.extract_text()
        return texto

# ==============================
# Dividir texto en chunks superpuestos
# ==============================    
    def dividir_en_chunks(self, texto: str, tamano_chunk: int = 500, solapamiento: int = 50) -> List[str]:
        palabras = texto.split()
        chunks = []
        
        for i in range(0, len(palabras), tamano_chunk - solapamiento):
            chunk = " ".join(palabras[i:i + tamano_chunk])
            if chunk:
                chunks.append(chunk)
        
        return chunks

# ==============================
# Generar embedding con OpenAI
# ==============================    
    def generar_embedding(self, texto: str) -> List[float]:
        respuesta = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=texto
        )
        return respuesta.data[0].embedding

# ==============================
# Guardar documento (PDF) en la base de datos vectorial
# ==============================    
    def guardar_documento(self, nombre_archivo: str, contenido_bytes: bytes):
        from app.models.documento import Documento, ChunkDocumento
        
        texto = self.extraer_texto_pdf(contenido_bytes)
        
        doc = Documento(
            empresa_id=self.empresa_id,
            nombre=nombre_archivo,
            hash_contenido=hashlib.md5(contenido_bytes).hexdigest()
        )
        self.db.add(doc)
        self.db.flush()
        
        chunks = self.dividir_en_chunks(texto)
        for i, chunk_texto in enumerate(chunks):
            embedding = self.generar_embedding(chunk_texto)
            chunk = ChunkDocumento(
                documento_id=doc.id,
                indice=i,
                texto=chunk_texto,
                embedding=embedding
            )
            self.db.add(chunk)
        
        self.db.commit()
        return doc

# ==============================
# Búsqueda semántica: chunks similares a la consulta
# ==============================    
    def buscar_similares(self, consulta: str, top_k: int = 3) -> List[Dict[str, Any]]:
        from app.models.documento import ChunkDocumento
        
        embedding_consulta = self.generar_embedding(consulta)
        
        # Obtener todos los chunks de la empresa (incluye documentos y especialidades)
        chunks = self.db.query(ChunkDocumento).filter(
            ChunkDocumento.documento.has(empresa_id=self.empresa_id)
        ).all()
        
        resultados = []
        for chunk in chunks:
            similitud = np.dot(embedding_consulta, chunk.embedding) / (
                np.linalg.norm(embedding_consulta) * np.linalg.norm(chunk.embedding)
            )
            resultados.append({
                "texto": chunk.texto,
                "similitud": similitud,
                "documento_id": chunk.documento_id,
                "documento_nombre": chunk.documento.nombre if chunk.documento else "desconocido"
            })
        
        resultados.sort(key=lambda x: x["similitud"], reverse=True)
        return resultados[:top_k]