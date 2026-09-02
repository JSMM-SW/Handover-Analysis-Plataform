from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.shared.config import settings

# pool_pre_ping evita errores por conexiones muertas cuando el proveedor
# (Supabase) las recicla del lado del servidor y el backend sigue corriendo.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar la request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
