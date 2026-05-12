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
    
    def extraer_intencion_y_fecha(self, mensaje: str, historial: str = "") -> dict:
        """
        Extrae la intención del mensaje, fecha, hora, nombre y booking_id si corresponde.
        NO ejecuta funciones, solo devuelve JSON.
        """
        ecuador = pytz.timezone("America/Guayaquil")
        hoy = datetime.now(ecuador).strftime("%Y-%m-%d")
        
        prompt = f"""Eres un asistente que analiza mensajes de clientes de una clínica dental.

Hoy es {hoy}.

Analiza el siguiente mensaje y devuelve SOLO un JSON con estos campos:

{{
    "intencion": "HORARIOS" | "AGENDAR" | "CANCELAR" | "REAGENDAR" | "CONSULTAR_CITAS" | "INFO" | "OTRO",
    "fecha": "YYYY-MM-DD" o null,
    "hora": "HH:MM" o null,
    "nombre": "nombre extraído" o null,
    "booking_id": null o número entero (si el usuario menciona un ID de cita)
}}

REGLAS IMPORTANTES PARA EXTRACCIÓN DE NOMBRE:
- SOLO extrae un nombre si es claramente un nombre propio de persona (ej: "Klever Robalino", "Ana", "Juan Pérez").
- NO extraigas como nombre palabras como: "abuela", "mamá", "papá", "tío", "mi hermano", "esposa", "hijo", "yo", "para mí", "mi", "ella", "él".
- Si el usuario dice "para mi abuela", "para mi mamá", "quiero agendar para mi hijo", el campo "nombre" DEBE ser null.
- Si el usuario dice "soy Klever" o "me llamo Ana", ahí SÍ extrae el nombre.
- Si el usuario da un nombre y una relación familiar (ej: "mi abuela se llama Rosa"), extrae "Rosa" como nombre.

Para fechas, entiende expresiones como:
- "martes de la próxima semana" → calcula la fecha exacta
- "mañana" → fecha de mañana
- "31 de marzo" → 2026-03-31
- "el lunes" → próximo lunes

Para cancelación o reagendamiento, si el usuario menciona un número de ID de cita (ej: "cancelar la cita 17825362", "reagendar la cita 17906494"), extrae ese número en el campo booking_id.
Si menciona una fecha (ej: "cancelar la cita del 2 de abril", "reagendar la cita del 6 de abril"), extrae esa fecha en el campo fecha.

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
            return {"intencion": "OTRO", "fecha": None, "hora": None, "nombre": None, "booking_id": None}
    
    def clasificar_respuesta_flujo(self, mensaje: str, paso_actual: str, historial: str = "") -> dict:
        """
        Clasifica si el mensaje del usuario es una respuesta válida para el paso actual
        o si es una interrupción/pregunta fuera del flujo.
        
        Args:
            mensaje: Mensaje del usuario
            paso_actual: El paso actual del flujo (ej: "nombre", "fecha", "hora", "email")
            historial: Historial reciente de la conversación
        
        Returns:
            dict: {
                "es_valido": bool,  # True si el mensaje responde a lo que se pide
                "respuesta_rag": str,  # Si es inválido, respuesta generada por RAG
                "dato_extraido": str o null  # Si es válido, el dato extraído
            }
        """
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
    
    def generar_respuesta_con_texto(self, consulta: str, contexto: str, resumen_cliente: str = "") -> str:
        """
        Genera respuesta usando GPT-4o SOLO para conversación (sin function calling)
        """
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
    
    def extraer_texto_pdf(self, archivo_bytes: bytes) -> str:
        """Extrae texto de un archivo PDF"""
        texto = ""
        pdf = PdfReader(BytesIO(archivo_bytes))
        for pagina in pdf.pages:
            texto += pagina.extract_text()
        return texto
    
    def dividir_en_chunks(self, texto: str, tamano_chunk: int = 500, solapamiento: int = 50) -> List[str]:
        """Divide el texto en fragmentos más pequeños para embedding"""
        palabras = texto.split()
        chunks = []
        
        for i in range(0, len(palabras), tamano_chunk - solapamiento):
            chunk = " ".join(palabras[i:i + tamano_chunk])
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def generar_embedding(self, texto: str) -> List[float]:
        """Genera embedding usando OpenAI estándar"""
        respuesta = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=texto
        )
        return respuesta.data[0].embedding
    
    def guardar_documento(self, nombre_archivo: str, contenido_bytes: bytes):
        """Procesa y guarda un documento en la base de datos vectorial"""
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
    
    def buscar_similares(self, consulta: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Busca chunks similares a la consulta usando similitud de coseno"""
        from app.models.documento import ChunkDocumento
        
        embedding_consulta = self.generar_embedding(consulta)
        
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
                "documento": chunk.documento.nombre
            })
        
        resultados.sort(key=lambda x: x["similitud"], reverse=True)
        return resultados[:top_k]