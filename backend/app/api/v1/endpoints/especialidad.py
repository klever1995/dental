from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import requests
import os
import json
from dotenv import load_dotenv

from app.db.base import get_db
from app.models.especialidad import Especialidad
from app.models.empresa import Empresa
from app.schemas.especialidad import EspecialidadCreate, EspecialidadResponse, EspecialidadUpdate
from app.services.rag import RAGService

load_dotenv()

router = APIRouter(prefix="/especialidades", tags=["Especialidades"])

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY")
CALCOM_API_VERSION = "2024-06-14"

def crear_evento_calcom(titulo: str, slug: str, descripcion: str) -> int:
    """
    Crea un nuevo evento en Cal.com con la misma configuración que el evento "Prueba"
    """
    url = "https://api.cal.com/v2/event-types"
    headers = {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": CALCOM_API_VERSION
    }
    
    payload = {
        "title": titulo,
        "slug": slug,
        "lengthInMinutes": 60,
        "description": descripcion,
        "locations": [
            {
                "type": "address",
                "address": "https://maps.app.goo.gl/TWmaZKTjFWNtHJFJ6",
                "public": False
            }
        ],
        "bookingFields": [
            {
                "isDefault": True,
                "type": "name",
                "slug": "name",
                "required": True,
                "disableOnPrefill": False
            },
            {
                "isDefault": False,
                "type": "text",
                "slug": "cedula",
                "label": "Cédula",
                "required": True,
                "placeholder": "Ingresa tu número de cédula",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "email",
                "slug": "email",
                "required": True,
                "label": "",
                "placeholder": "",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "phone",
                "slug": "attendeePhoneNumber",
                "required": True,
                "label": "Teléfono",
                "placeholder": "Ingresa tu número",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "radioInput",
                "slug": "location",
                "required": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "text",
                "slug": "title",
                "required": True,
                "disableOnPrefill": False,
                "hidden": True
            },
            {
                "isDefault": True,
                "type": "textarea",
                "slug": "notes",
                "required": False,
                "label": "",
                "placeholder": "",
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "multiemail",
                "slug": "guests",
                "required": False,
                "disableOnPrefill": False,
                "hidden": False
            },
            {
                "isDefault": True,
                "type": "textarea",
                "slug": "rescheduleReason",
                "required": False,
                "disableOnPrefill": False,
                "hidden": False
            }
        ],
        "disableGuests": False,
        "minimumBookingNotice": 120,
        "seats": {
            "disabled": True
        }
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code not in [200, 201]:
        raise Exception(f"Error creando evento en Cal.com: {response.text}")
    
    data = response.json()
    evento_creado = data.get("data", {})
    event_type_id = evento_creado.get("id")
    
    if not event_type_id:
        raise Exception("No se recibió ID del evento creado")
    
    return event_type_id

# ============================================
# ENDPOINTS
# ============================================

@router.post("/", response_model=EspecialidadResponse, status_code=status.HTTP_201_CREATED)
def crear_especialidad(especialidad: EspecialidadCreate, db: Session = Depends(get_db)):
    """
    Crea una nueva especialidad.
    Automáticamente crea un evento en Cal.com con la misma configuración que el evento "Prueba".
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
        slug = especialidad.nombre.lower().replace(" ", "-")
        
        event_type_id = crear_evento_calcom(
            titulo=especialidad.nombre.capitalize(),
            slug=slug,
            descripcion=especialidad.descripcion or f"Cita de {especialidad.nombre}"
        )
        
        nueva_especialidad = Especialidad(
            empresa_id=especialidad.empresa_id,
            nombre=especialidad.nombre,
            descripcion=especialidad.descripcion,
            event_type_id=event_type_id,
            activa=especialidad.activa if hasattr(especialidad, 'activa') else True
        )
        
        db.add(nueva_especialidad)
        db.commit()
        db.refresh(nueva_especialidad)
        
        # 🔥 Sincronizar especialidades con el RAG (actualizar chunks)
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
    for field, value in update_data.items():
        setattr(especialidad, field, value)
    
    db.commit()
    db.refresh(especialidad)
    
    # 🔥 Sincronizar especialidades con el RAG (actualizar chunks)
    rag = RAGService(db, especialidad.empresa_id)
    rag.sincronizar_especialidades()
    
    return especialidad

@router.delete("/{especialidad_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_especialidad(especialidad_id: int, db: Session = Depends(get_db)):
    especialidad = db.query(Especialidad).filter(Especialidad.id == especialidad_id).first()
    if not especialidad:
        raise HTTPException(status_code=404, detail="Especialidad no encontrada")
    
    empresa_id = especialidad.empresa_id
    
    db.delete(especialidad)
    db.commit()
    
    # 🔥 Sincronizar especialidades con el RAG (actualizar chunks, elimina los de la especialidad borrada)
    rag = RAGService(db, empresa_id)
    rag.sincronizar_especialidades()
    
    return {"ok": True}