# ==============================
# Configuración de base de datos PostgreSQL
# ==============================
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin123@localhost:5432/sublimados_db")

engine = create_engine(DATABASE_URL)

# ==============================
# Habilitar extensión vector en PostgreSQL
# ==============================
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ==============================
# Dependencia para obtener sesión de BD en FastAPI
# ==============================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()