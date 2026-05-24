from sqlalchemy import Column, Integer, String, BigInteger, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

# ==============================
# Modelo SuscripcionWebhook
# Registra los canales de notificación creados en Google Calendar
# Permite renovar automáticamente las suscripciones antes de que expiren (7 días)
# ==============================
class SuscripcionWebhook(Base):
    __tablename__ = "suscripciones_webhook"

    id = Column(Integer, primary_key=True, index=True)
    especialidad_id = Column(Integer, ForeignKey("especialidades.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = Column(String(255), nullable=False, unique=True, index=True)
    resource_id = Column(String(255), nullable=False, unique=True, index=True)
    expiration = Column(BigInteger, nullable=False, index=True)
    activa = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    especialidad = relationship("Especialidad", backref="suscripciones_webhook")

    def __repr__(self):
        return f"<SuscripcionWebhook especialidad_id={self.especialidad_id} channel={self.channel_id}>"