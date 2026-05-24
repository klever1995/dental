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
    # NOTA: calendar_id se obtendrá de Google Calendar al crear el calendario, no se envía desde el frontend

# ============================================
# SCHEMA PARA CREAR CALENDARIO EN GOOGLE (API interna)
# ============================================
class EspecialidadGoogleCalendarCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    timeZone: str = Field("America/Guayaquil", description="Zona horaria del calendario")

# ============================================
# SCHEMA PARA RESPUESTA (lo que devuelve la API)
# ============================================
class EspecialidadResponse(EspecialidadBase):
    id: int
    empresa_id: int
    calendar_id: Optional[str] = None  # 🔥 ID del calendario en Google Calendar
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
    calendar_id: Optional[str] = None  # 🔥 Solo si se necesita cambiar el ID del calendario
    activa: Optional[bool] = None

# ============================================
# SCHEMA PARA LISTAR CON INFORMACIÓN ADICIONAL (opcional)
# ============================================
class EspecialidadWithDetails(EspecialidadResponse):
    cupos_ocupados_hoy: Optional[int] = 0
    citas_hoy: Optional[int] = 0