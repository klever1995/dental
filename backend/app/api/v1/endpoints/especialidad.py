from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.db.base import get_db
from app.models.especialidad import Especialidad
from app.models.empresa import Empresa
from app.schemas.especialidad import EspecialidadCreate, EspecialidadResponse, EspecialidadUpdate
from app.services.rag import RAGService

load_dotenv()

router = APIRouter(prefix="/especialidades", tags=["Especialidades"])

# Configuración de Google Calendar
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account-key.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_google_calendar_service():
    """Obtiene el servicio de Google Calendar autenticado con cuenta de servicio"""
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        raise Exception(f"Error autenticando con Google Calendar: {str(e)}")

def crear_calendario_google(titulo: str, descripcion: str) -> str:
    """
    Crea un nuevo calendario en Google Calendar para la especialidad
    Retorna el calendar_id del calendario creado
    """
    service = get_google_calendar_service()
    
    calendario = {
        'summary': titulo,
        'description': descripcion,
        'timeZone': 'America/Guayaquil'
    }
    
    try:
        calendario_creado = service.calendars().insert(body=calendario).execute()
        calendar_id = calendario_creado.get('id')
        return calendar_id
    except HttpError as error:
        raise Exception(f"Error creando calendario en Google Calendar: {error}")

def eliminar_calendario_google(calendar_id: str):
    """Elimina un calendario en Google Calendar"""
    service = get_google_calendar_service()
    try:
        service.calendars().delete(calendarId=calendar_id).execute()
    except HttpError as error:
        # Si el calendario no existe o ya fue eliminado, no hacemos nada
        print(f"Error eliminando calendario {calendar_id}: {error}")

def actualizar_calendario_google(calendar_id: str, titulo: str = None, descripcion: str = None):
    """Actualiza el nombre y/o descripción de un calendario en Google Calendar"""
    service = get_google_calendar_service()
    updates = {}
    if titulo:
        updates['summary'] = titulo
    if descripcion:
        updates['description'] = descripcion
    
    if updates:
        try:
            service.calendars().update(calendarId=calendar_id, body=updates).execute()
        except HttpError as error:
            raise Exception(f"Error actualizando calendario en Google Calendar: {error}")

# ============================================
# ENDPOINTS
# ============================================

@router.post("/", response_model=EspecialidadResponse, status_code=status.HTTP_201_CREATED)
def crear_especialidad(especialidad: EspecialidadCreate, db: Session = Depends(get_db)):
    """
    Crea una nueva especialidad.
    Automáticamente crea un calendario en Google Calendar.
    """
    empresa = db.query(Empresa).filter(Empresa.id == especialidad.empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    
    existente = db.query(Especialidad).filter(
        Especialidad.empresa_id == especialidad.empresa_id,
        Especialidad.nombre == especialidad.nombre
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una especialidad con ese nombre")
    
    try:
        # Crear calendario en Google Calendar
        titulo_calendario = especialidad.nombre.capitalize()
        descripcion_calendario = especialidad.descripcion or f"Citas de {especialidad.nombre}"
        calendar_id = crear_calendario_google(titulo_calendario, descripcion_calendario)
        
        # Guardar en la base de datos
        nueva_especialidad = Especialidad(
            empresa_id=especialidad.empresa_id,
            nombre=especialidad.nombre,
            descripcion=especialidad.descripcion,
            calendar_id=calendar_id,
            activa=especialidad.activa if hasattr(especialidad, 'activa') else True
        )
        
        db.add(nueva_especialidad)
        db.commit()
        db.refresh(nueva_especialidad)
        
        # Sincronizar especialidades con el RAG (actualizar chunks)
        rag = RAGService(db, especialidad.empresa_id)
        rag.sincronizar_especialidades()
        
        return nueva_especialidad
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear la especialidad: {str(e)}")

@router.get("/", response_model=List[EspecialidadResponse])
def listar_especialidades(
    empresa_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    especialidades = db.query(Especialidad).filter(
        Especialidad.empresa_id == empresa_id
    ).offset(skip).limit(limit).all()
    
    return especialidades

@router.get("/{especialidad_id}", response_model=EspecialidadResponse)
def obtener_especialidad(especialidad_id: int, db: Session = Depends(get_db)):
    especialidad = db.query(Especialidad).filter(Especialidad.id == especialidad_id).first()
    if not especialidad:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    return especialidad

@router.put("/{especialidad_id}", response_model=EspecialidadResponse)
def actualizar_especialidad(
    especialidad_id: int,
    especialidad_update: EspecialidadUpdate,
    db: Session = Depends(get_db)
):
    especialidad = db.query(Especialidad).filter(Especialidad.id == especialidad_id).first()
    if not especialidad:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    
    update_data = especialidad_update.dict(exclude_unset=True)
    
    # Si se actualiza el nombre o la descripción, actualizar el calendario en Google Calendar
    nuevo_nombre = update_data.get("nombre")
    nueva_descripcion = update_data.get("descripcion")
    if (nuevo_nombre or nueva_descripcion) and especialidad.calendar_id:
        try:
            titulo = nuevo_nombre.capitalize() if nuevo_nombre else None
            descripcion = nueva_descripcion or None
            actualizar_calendario_google(especialidad.calendar_id, titulo, descripcion)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error actualizando calendario en Google: {str(e)}")
    
    for field, value in update_data.items():
        setattr(especialidad, field, value)
    
    db.commit()
    db.refresh(especialidad)
    
    # Sincronizar especialidades con el RAG (actualizar chunks)
    rag = RAGService(db, especialidad.empresa_id)
    rag.sincronizar_especialidades()
    
    return especialidad

@router.delete("/{especialidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_especialidad(especialidad_id: int, db: Session = Depends(get_db)):
    especialidad = db.query(Especialidad).filter(Especialidad.id == especialidad_id).first()
    if not especialidad:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    
    empresa_id = especialidad.empresa_id
    calendar_id = especialidad.calendar_id
    
    # Eliminar el calendario de Google Calendar
    if calendar_id:
        try:
            eliminar_calendario_google(calendar_id)
        except Exception as e:
            # Si falla la eliminación, registramos el error pero continuamos
            print(f"Error eliminando calendario {calendar_id}: {e}")
    
    db.delete(especialidad)
    db.commit()
    
    # Sincronizar especialidades con el RAG
    rag = RAGService(db, empresa_id)
    rag.sincronizar_especialidades()
    
    return {"ok": True}