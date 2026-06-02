from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger
from sqlalchemy.sql import func
from app.db.base import Base

# ==============================
# Modelo Empresa
# Representa cada negocio/cliente del sistema (multitenencia)
# ==============================
class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    telefono_whatsapp = Column(String(20), unique=True, nullable=False, index=True)
    token_api = Column(String(100), unique=True, nullable=False)
    prompt_personalizado = Column(Text, nullable=True) 
    telefono_dueño = Column(String(20), nullable=True)  
    activa = Column(Boolean, default=True)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())

    # ==============================
    # Campos para Embedded Signup de WhatsApp Business Platform
    # ==============================
    whatsapp_business_account_id = Column(String(255), nullable=True, unique=True)  
    whatsapp_phone_number_id = Column(String(255), nullable=True, unique=True)      
    whatsapp_access_token = Column(Text, nullable=True)                              
    whatsapp_token_expires_at = Column(BigInteger, nullable=True)                   
    whatsapp_connected = Column(Boolean, default=False)                             

    def __repr__(self):
        return f"<Empresa {self.nombre} ({self.telefono_whatsapp}) - WhatsApp conectado: {self.whatsapp_connected}>"