# ==============================
# Esquemas Pydantic para Usuario
# Define la estructura de datos para autenticación, tokens y gestión de usuarios
# ==============================
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str
    rol: Optional[str] = "admin"
    activo: Optional[bool] = True

class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=6)
    empresa_id: int
    especialidad_id: Optional[int] = None

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class UsuarioResponse(UsuarioBase):
    id: int
    empresa_id: int
    especialidad_id: Optional[int] = None
    ultimo_acceso: Optional[datetime] = None
    fecha_registro: datetime
    fecha_actualizacion: Optional[datetime] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    usuario_id: Optional[int] = None
    empresa_id: Optional[int] = None
    email: Optional[str] = None
    rol: Optional[str] = None
    especialidad_id: Optional[int] = None

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    rol: Optional[str] = None
    activo: Optional[bool] = None
    especialidad_id: Optional[int] = None