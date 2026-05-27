# ==============================
# Endpoint de autenticación y gestión de usuarios
# Registro, login, JWT y CRUD de usuarios con roles (admin/doctor)
# ==============================
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from app.db.base import get_db
from app.models.usuarios import Usuario
from app.models.empresa import Empresa
from app.models.especialidad import Especialidad 
from app.schemas.usuarios import (
    UsuarioCreate, UsuarioResponse, UsuarioUpdate,
    UsuarioLogin, Token, TokenData
)
import os

# ==============================
# Configuración de JWT
# ==============================
SECRET_KEY = os.getenv("SECRET_KEY", "tu_secreto_super_seguro_cambia_esto")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/usuarios/login")

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

# ==============================
# Funciones auxiliares de seguridad
# ==============================
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ==============================
# Dependencias de autenticación
# ==============================
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: int = payload.get("sub")
        if usuario_id is None:
            raise credentials_exception
        token_data = TokenData(
            usuario_id=usuario_id,
            empresa_id=payload.get("empresa_id"),
            email=payload.get("email"),
            rol=payload.get("rol"),
            especialidad_id=payload.get("especialidad_id")  
        )
    except JWTError:
        raise credentials_exception
    usuario = db.query(Usuario).filter(Usuario.id == token_data.usuario_id).first()
    if usuario is None:
        raise credentials_exception
    return usuario

async def get_current_active_user(current_user: Usuario = Depends(get_current_user)):
    if not current_user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

# ==============================
# Endpoint público: registro de usuario
# ==============================
@router.post("/registro", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    usuario: UsuarioCreate,
    db: Session = Depends(get_db)
):
    # Verificar que la empresa existe
    empresa = db.query(Empresa).filter(Empresa.id == usuario.empresa_id).first()
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa no encontrada"
        )
    
    # Verificar que el email no esté registrado
    usuario_existente = db.query(Usuario).filter(Usuario.email == usuario.email).first()
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email ya registrado"
        )
    
    # Si se asignó una especialidad, verificar que existe y está activa
    if usuario.especialidad_id:
        especialidad = db.query(Especialidad).filter(
            Especialidad.id == usuario.especialidad_id,
            Especialidad.activa == True
        ).first()
        if not especialidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Especialidad no encontrada o inactiva"
            )
    
    # Crear nuevo usuario
    nuevo_usuario = Usuario(
        empresa_id=usuario.empresa_id,
        email=usuario.email,
        nombre=usuario.nombre,
        password_hash=get_password_hash(usuario.password),
        rol=usuario.rol,
        especialidad_id=usuario.especialidad_id,  
        activo=True
    )
    
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    return nuevo_usuario

# ==============================
# Endpoint público: login (retorna JWT)
# ==============================
@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    # Buscar usuario por email
    usuario = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    
    if not usuario or not verify_password(form_data.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    
    # Actualizar último acceso
    usuario.ultimo_acceso = datetime.now()
    db.commit()
    
    # Crear token incluyendo especialidad_id
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": str(usuario.id),
            "empresa_id": usuario.empresa_id,
            "email": usuario.email,
            "rol": usuario.rol,
            "especialidad_id": usuario.especialidad_id  
        },
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# ==============================
# Endpoint protegido: perfil propio
# ==============================
@router.get("/me", response_model=UsuarioResponse)
def leer_usuario_actual(current_user: Usuario = Depends(get_current_active_user)):
    return current_user

# ==============================
# Listar usuarios (con filtros por empresa y rol)
# ==============================
@router.get("/", response_model=List[UsuarioResponse])
def listar_usuarios(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Solo usuarios de la misma empresa
    query = db.query(Usuario).filter(Usuario.empresa_id == current_user.empresa_id)
    
    # Si no es admin, solo puede ver usuarios de su misma especialidad (doctores)
    if current_user.rol != "admin":
        query = query.filter(Usuario.especialidad_id == current_user.especialidad_id)
    
    usuarios = query.offset(skip).limit(limit).all()
    return usuarios

# ==============================
# Obtener un usuario por ID
# ==============================
@router.get("/{usuario_id}", response_model=UsuarioResponse)
def obtener_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    query = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == current_user.empresa_id
    )
    
    # Si no es admin, solo puede ver usuarios de su misma especialidad
    if current_user.rol != "admin":
        query = query.filter(Usuario.especialidad_id == current_user.especialidad_id)
    
    usuario = query.first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    return usuario

# ==============================
# Actualizar usuario (solo admin o el mismo usuario)
# ==============================
@router.put("/{usuario_id}", response_model=UsuarioResponse)
def actualizar_usuario(
    usuario_id: int,
    usuario_update: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Solo admin puede modificar otros usuarios (o el mismo usuario)
    if current_user.id != usuario_id and current_user.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar este usuario"
        )
    
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == current_user.empresa_id
    ).first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Si se está cambiando la especialidad, verificar que existe
    if usuario_update.especialidad_id is not None:
        especialidad = db.query(Especialidad).filter(
            Especialidad.id == usuario_update.especialidad_id,
            Especialidad.activa == True
        ).first()
        if not especialidad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Especialidad no encontrada o inactiva"
            )
    
    # Actualizar campos
    update_data = usuario_update.dict(exclude_unset=True)
    
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    
    if "email" in update_data:
        # Verificar que el nuevo email no esté en uso
        email_existente = db.query(Usuario).filter(
            Usuario.email == update_data["email"],
            Usuario.id != usuario_id
        ).first()
        if email_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email ya registrado"
            )
    
    for field, value in update_data.items():
        setattr(usuario, field, value)
    
    usuario.fecha_actualizacion = datetime.now()
    db.commit()
    db.refresh(usuario)
    
    return usuario

# ==============================
# Eliminar usuario (solo admin, no puede eliminarse a sí mismo)
# ==============================
@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_active_user)
):
    # Solo admin puede eliminar usuarios (y no puede eliminarse a sí mismo)
    if current_user.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el administrador puede eliminar usuarios"
        )
    
    if current_user.id == usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminarte a ti mismo"
        )
    
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id,
        Usuario.empresa_id == current_user.empresa_id
    ).first()
    
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    db.delete(usuario)
    db.commit()
    
    return None