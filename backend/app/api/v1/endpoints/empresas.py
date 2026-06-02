# ==============================
# Endpoint de gestión de empresas
# CRUD completo para entidades empresariales (multitenencia) + Embedded Signup de WhatsApp
# ==============================
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
import secrets
import os
import requests
from datetime import datetime, timedelta

from app.db.base import get_db
from app.models.empresa import Empresa as EmpresaModel
from app.schemas.empresa import Empresa, EmpresaCreate, EmpresaUpdate

router = APIRouter(prefix="/empresas", tags=["empresas"])

# ==============================
# Crear una nueva empresa con token API único
# ==============================
@router.post("/", response_model=Empresa, status_code=status.HTTP_201_CREATED)
def crear_empresa(empresa: EmpresaCreate, db: Session = Depends(get_db)):
    db_empresa = db.query(EmpresaModel).filter(
        EmpresaModel.telefono_whatsapp == empresa.telefono_whatsapp
    ).first()
    
    if db_empresa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una empresa registrada con este número de WhatsApp"
        )
    
    token_api = secrets.token_urlsafe(32)
    
    nueva_empresa = EmpresaModel(
        **empresa.model_dump(),
        token_api=token_api
    )
    
    db.add(nueva_empresa)
    db.commit()
    db.refresh(nueva_empresa)
    
    return nueva_empresa

# ==============================
# Listar empresas con paginación
# ==============================
@router.get("/", response_model=List[Empresa])
def listar_empresas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    empresas = db.query(EmpresaModel).offset(skip).limit(limit).all()
    return empresas

# ==============================
# Obtener una empresa por ID
# ==============================
@router.get("/{empresa_id}", response_model=Empresa)
def obtener_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(EmpresaModel).filter(EmpresaModel.id == empresa_id).first()
    
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa no encontrada"
        )
    
    return empresa

# ==============================
# Actualizar datos de una empresa (incluye campos de WhatsApp)
# ==============================
@router.put("/{empresa_id}", response_model=Empresa)
def actualizar_empresa(
    empresa_id: int, 
    empresa_data: EmpresaUpdate, 
    db: Session = Depends(get_db)
):
    empresa = db.query(EmpresaModel).filter(EmpresaModel.id == empresa_id).first()
    
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa no encontrada"
        )
    
    if empresa_data.telefono_whatsapp and empresa.telefono_whatsapp != empresa_data.telefono_whatsapp:
        telefono_existe = db.query(EmpresaModel).filter(
            EmpresaModel.telefono_whatsapp == empresa_data.telefono_whatsapp,
            EmpresaModel.id != empresa_id
        ).first()
        
        if telefono_existe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe otra empresa con este número de WhatsApp"
            )
    
    update_data = empresa_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(empresa, field, value)
    
    db.commit()
    db.refresh(empresa)
    
    return empresa

# ==============================
# Endpoint para callback de Embedded Signup de WhatsApp (Meta)
# Recibe los datos del evento 'message' después de que el cliente completa el flujo
# ==============================
@router.post("/{empresa_id}/whatsapp/callback")
async def whatsapp_embedded_callback(
    empresa_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # Recibir los datos que envía el frontend desde el evento 'message'
        body = await request.json()
        
        # Extraer los datos del cliente (según la estructura de Meta)
        phone_number_id = body.get("phone_number_id")
        waba_id = body.get("waba_id")
        business_id = body.get("business_id")
        
        if not phone_number_id or not waba_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Faltan datos: phone_number_id y waba_id son requeridos"
            )
        
        # Buscar la empresa en la base de datos
        empresa = db.query(EmpresaModel).filter(EmpresaModel.id == empresa_id).first()
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada"
            )
        
        # Guardar los datos en la base de datos
        empresa.whatsapp_business_account_id = waba_id
        empresa.whatsapp_phone_number_id = phone_number_id
        empresa.whatsapp_connected = True
        # Opcional: guardar business_id si tienes un campo para él
        # empresa.whatsapp_business_id = business_id
        
        db.commit()
        
        return {
            "success": True,
            "message": "WhatsApp conectado exitosamente",
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "business_id": business_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error en callback de WhatsApp: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )