from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.base import engine, Base
from app.api.v1.endpoints import empresas, documentos, whatsapp, usuarios, calcom, especialidad
from app.models import empresa, cliente, conversacion, documento, usuarios as usuario_modelo
from app.socket_manager import socket_app  # 🔥 NUEVA IMPORTACIÓN

# Crear las tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Chatbot Sublimados API")

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(empresas.router, prefix="/api/v1")
app.include_router(documentos.router, prefix="/api/v1")
app.include_router(whatsapp.router, prefix="/api/v1")
app.include_router(usuarios.router, prefix="/api/v1")
app.include_router(calcom.router, prefix="/api/v1")
app.include_router(especialidad.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "API funcionando correctamente"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

# Montar Socket.IO
app.mount("/socket.io", socket_app)