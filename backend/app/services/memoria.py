# ==============================
# Servicio de Memoria
# Gestiona resúmenes y datos estructurados de cada cliente (contexto persistente)
# ==============================
from sqlalchemy.orm import Session
from app.models.cliente import Cliente
from app.models.conversacion import Conversacion
import json

class MemoriaService:
    def __init__(self, db: Session, cliente_id: int):
        self.db = db
        self.cliente_id = cliente_id
        self.cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    
    # ==============================
    # Obtener resumen actual del cliente
    # ==============================
    def obtener_resumen(self) -> str:
        if self.cliente and self.cliente.resumen:
            return self.cliente.resumen
        return "Cliente sin historial previo"
    
    # ==============================
    # Obtener datos estructurados (JSON) del cliente
    # ==============================
    def obtener_datos_estructurados(self) -> dict:
        if self.cliente and self.cliente.datos_estructurados:
            return self.cliente.datos_estructurados
        return {}
    
    # ==============================
    # Actualizar resumen basado en última interacción
    # ==============================
    def actualizar_resumen(self, pregunta: str, respuesta: str):
        if not self.cliente:
            return
        
        nuevo_resumen = f"Última interacción - P: {pregunta[:50]}... R: {respuesta[:50]}..."
        
        self.cliente.resumen = nuevo_resumen
        self.cliente.ultima_interaccion = None  
        self.db.commit()
    
    # ==============================
    # Guardar datos estructurados (ej: producto_interes, tipo_cliente)
    # ==============================
    def guardar_dato_estructurado(self, clave: str, valor):
        if not self.cliente:
            return
        
        datos = self.cliente.datos_estructurados or {}
        datos[clave] = valor
        
        self.cliente.datos_estructurados = datos
        self.db.commit()