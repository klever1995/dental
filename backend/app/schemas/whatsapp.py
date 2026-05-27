# ==============================
# Esquemas Pydantic para WhatsApp
# Define la estructura de datos para recibir mensajes del webhook y enviar respuestas
# ==============================
from pydantic import BaseModel, Field
from typing import Optional

class WhatsAppMensaje(BaseModel):
    telefono_cliente: str = Field(..., max_length=20)
    mensaje: str = Field(..., max_length=4096)
    nombre_cliente: Optional[str] = None

class WhatsAppRespuesta(BaseModel):
    mensaje: str
    requiere_humano: bool = False