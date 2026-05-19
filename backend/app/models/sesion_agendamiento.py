from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class SesionAgendamiento(Base):
    __tablename__ = "sesiones_agendamiento"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    estado = Column(String(50), nullable=False)  # pidiendo_nombre, pidiendo_fecha, etc.
    nombre = Column(String(100), nullable=True)
    fecha = Column(String(10), nullable=True)
    hora = Column(String(5), nullable=True)
    email = Column(String(100), nullable=True)
    horas_disponibles = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relación con cliente
    cliente = relationship("Cliente", backref="sesiones_agendamiento")