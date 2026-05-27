# ==============================
# Esquemas Pydantic para Especialidad
# Define la validación y estructura de datos para los tipos de atención médica
# ==============================
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class EspecialidadBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    activa: Optional[bool] = True

class EspecialidadCreate(EspecialidadBase):
    empresa_id: int

class EspecialidadGoogleCalendarCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    timeZone: str = Field("America/Guayaquil")

class EspecialidadResponse(EspecialidadBase):
    id: int
    empresa_id: int
    calendar_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class EspecialidadUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    calendar_id: Optional[str] = None
    activa: Optional[bool] = None

class EspecialidadWithDetails(EspecialidadResponse):
    cupos_ocupados_hoy: Optional[int] = 0
    citas_hoy: Optional[int] = 0