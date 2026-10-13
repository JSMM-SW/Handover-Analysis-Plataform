from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_upload_size_mb: int = 100
    allowed_extensions: str = ".csv"

    # Zona horaria en la que se muestran fechas en mensajes al usuario (ej. el
    # rechazo por archivo duplicado: "ya fue cargado ... el 07/10/2026 07:42").
    display_timezone: str = "America/Guayaquil"

    # Tamaño de bloque con el que la subida se copia a data/input/ (streaming
    # a disco: el archivo nunca se carga completo en memoria).
    upload_chunk_bytes: int = 1024 * 1024

    # Filas por sentencia COPY durante el Load. Todas las tandas van en la
    # MISMA transacción (la sesión nunca queda a medias); partirlas mantiene
    # cada sentencia muy por debajo del statement_timeout del servidor (2 min
    # en Supabase) sin importar el tamaño del archivo.
    load_batch_rows: int = 50_000

    # Resiliencia de la conexión a la base (pooler de Supabase).
    db_connect_timeout_seconds: int = 10      # espera máxima para abrir conexión
    db_connect_retries: int = 3               # reintentos de la conexión INICIAL de una carga
    db_connect_retry_backoff_seconds: float = 2.0   # espera entre reintentos (se duplica cada vez)
    db_keepalives_idle_seconds: int = 30      # TCP keepalive: inactividad antes del primer sondeo
    db_keepalives_interval_seconds: int = 10  # TCP keepalive: intervalo entre sondeos
    db_keepalives_count: int = 5              # TCP keepalive: sondeos perdidos antes de cortar

    # Avance y latido de una ejecución (etapa, progreso, updated_at). Se
    # escriben desde una conexión aparte en autocommit, como mucho una vez
    # cada estos segundos dentro de una misma etapa (nunca por fila).
    heartbeat_min_interval_seconds: float = 5.0
    # Una ejecución en "processing" sin latido durante más de estos minutos se
    # considera interrumpida (ej. el servidor se reinició) y se marca "failed".
    # Debe ser bastante mayor que el intervalo más largo entre latidos (la
    # etapa más lenta o un lote de COPY: ~10 s medidos con 345k filas).
    stale_execution_minutes: int = 10

    # Limpieza de data/input/ al arrancar: solo archivos con prefijo de
    # upload_id (nunca los colocados a mano). Se borran si su ejecución ya no
    # está en "processing", o si no tienen ejecución y pasaron estas horas.
    orphan_cleanup_enabled: bool = True
    orphan_upload_max_age_hours: int = 24

    data_input_dir: Path = Path("data/input")
    data_processed_dir: Path = Path("data/processed")
    data_rejected_dir: Path = Path("data/rejected")

    # Placeholder no funcional: solo para que Settings() siga siendo
    # instanciable sin .env (usado por los tests de Iteración 1 que no
    # necesitan base de datos). La base real vive en Supabase; .env debe
    # sobrescribir esto con la cadena de conexión real.
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/postgres"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.allowed_extensions.split(",")}

    def resolved_data_input_dir(self) -> Path:
        path = PROJECT_ROOT / self.data_input_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Singleton de conveniencia para módulos que no participan del sistema de
# dependencias de FastAPI (p. ej. app.core.database, scripts, tests de
# integración del repositorio).
settings = get_settings()
