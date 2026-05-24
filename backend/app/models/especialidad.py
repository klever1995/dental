from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

# ==============================
# Modelo Especialidad
# Define los tipos de atención médica (Odontología, Traumatología, etc.)
# Cada especialidad tiene un calendario propio en Google Calendar
# ==============================
class Especialidad(Base):
    __tablename__ = "especialidades"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=True)
    calendar_id = Column(String(255), nullable=True, unique=True)
    activa = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    empresa = relationship("Empresa", backref="especialidades")

    def __repr__(self):
        return f"<Especialidad {self.nombre} (Empresa {self.empresa_id}) calendar_id={self.calendar_id}>"