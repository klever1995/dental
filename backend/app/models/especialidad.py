from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Especialidad(Base):
    __tablename__ = "especialidades"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(100), nullable=False)  # ej: "odontologia", "pediatria"
    descripcion = Column(Text, nullable=True)  # descripción amigable para el bot
    event_type_id = Column(Integer, nullable=True)  # 🔥 NUEVO: ID del evento en Cal.com
    activa = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    empresa = relationship("Empresa", backref="especialidades")

    def __repr__(self):
        return f"<Especialidad {self.nombre} (Empresa {self.empresa_id}) event_type_id={self.event_type_id}>"