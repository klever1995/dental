from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# ============================================
# SCHEMA BASE
# ============================================
class EspecialidadBase(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=100, description="Nombre de la especialidad (ej: odontologia, pediatria)")
    descripcion: Optional[str] = Field(None, max_length=500, description="Descripción amigable para el bot")
    activa: Optional[bool] = True

# ============================================
# SCHEMA PARA CREAR (desde frontend)
# ============================================
class EspecialidadCreate(EspecialidadBase):
    empresa_id: int
    # NOTA: event_type_id se obtendrá de Cal.com al crear el evento, no se envía desde el frontend

# ============================================
# SCHEMA PARA CREAR EVENTO EN CAL.COM (API interna)
# ============================================
class EspecialidadCalEventCreate(BaseModel):
    nombre: str
    duracion: int = Field(60, description="Duración en minutos")
    color: Optional[str] = Field("#292929", description="Color del evento en calendario")
    descripcion: Optional[str] = None

# ============================================
# SCHEMA PARA RESPUESTA (lo que devuelve la API)
# ============================================
class EspecialidadResponse(EspecialidadBase):
    id: int
    empresa_id: int
    event_type_id: int  # ID del evento en Cal.com
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ============================================
# SCHEMA PARA ACTUALIZAR
# ============================================
class EspecialidadUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=500)
    event_type_id: Optional[int] = None  # Solo si se necesita cambiar el ID del evento
    activa: Optional[bool] = None

# ============================================
# SCHEMA PARA LISTAR CON INFORMACIÓN ADICIONAL (opcional)
# ============================================
class EspecialidadWithDetails(EspecialidadResponse):
    cupos_ocupados_hoy: Optional[int] = 0
    citas_hoy: Optional[int] = 0