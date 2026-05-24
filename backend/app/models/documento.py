from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
from pgvector.sqlalchemy import Vector

# ==============================
# Modelo Documento
# Almacena archivos subidos por la empresa (PDF, Word, etc.)
# ==============================
class Documento(Base):
    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    nombre = Column(String(255), nullable=False)
    hash_contenido = Column(String(64), unique=True)
    fecha_subida = Column(DateTime(timezone=True), server_default=func.now())
    
    empresa = relationship("Empresa", backref="documentos")
    chunks = relationship("ChunkDocumento", back_populates="documento", cascade="all, delete-orphan")

# ==============================
# Modelo ChunkDocumento
# Fragmentos del documento con embeddings para búsqueda semántica
# ==============================
class ChunkDocumento(Base):
    __tablename__ = "chunks_documento"

    id = Column(Integer, primary_key=True, index=True)
    documento_id = Column(Integer, ForeignKey("documentos.id"), nullable=False)
    indice = Column(Integer, nullable=False)
    texto = Column(Text, nullable=False)
    embedding = Column(Vector(1536))
    
    documento = relationship("Documento", back_populates="chunks")