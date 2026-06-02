# ==============================
# Esquemas Pydantic para Empresa
# Define la estructura de datos para crear, leer y validar empresas
# ==============================
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class EmpresaBase(BaseModel):
    nombre: str = Field(..., max_length=100)
    telefono_whatsapp: str = Field(..., max_length=20)
    prompt_personalizado: Optional[str] = None
    telefono_dueño: Optional[str] = Field(None, max_length=20)
    activa: Optional[bool] = True

class EmpresaCreate(EmpresaBase):
    pass

# ==============================
# Schema para actualizar empresa (todos los campos opcionales)
# ==============================
class EmpresaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    telefono_whatsapp: Optional[str] = Field(None, max_length=20)
    prompt_personalizado: Optional[str] = None
    telefono_dueño: Optional[str] = Field(None, max_length=20)
    activa: Optional[bool] = None
    whatsapp_connected: Optional[bool] = None
    whatsapp_business_account_id: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    whatsapp_token_expires_at: Optional[int] = None

# ==============================
# Schema para respuesta (lo que devuelve la API)
# ==============================
class Empresa(EmpresaBase):
    id: int
    token_api: str
    fecha_registro: datetime
    fecha_actualizacion: Optional[datetime] = None
    whatsapp_business_account_id: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_connected: bool = False

    class Config:
        from_attributes = True