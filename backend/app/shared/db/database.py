from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.shared.config import settings

# pool_pre_ping evita errores por conexiones muertas cuando el proveedor
# (Supabase) las recicla del lado del servidor y el backend sigue corriendo.
# connect_timeout: abrir una conexión nunca espera indefinidamente.
# keepalives TCP: el pooler/NAT no corta una conexión que parece inactiva
# durante un proceso largo (ej. el Load de un archivo grande), y una conexión
# realmente caída se detecta en segundos en vez de quedar colgada.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": settings.db_connect_timeout_seconds,
        "keepalives": 1,
        "keepalives_idle": settings.db_keepalives_idle_seconds,
        "keepalives_interval": settings.db_keepalives_interval_seconds,
        "keepalives_count": settings.db_keepalives_count,
    },
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar la request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
