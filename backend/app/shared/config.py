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

    max_upload_size_mb: int = 20
    allowed_extensions: str = ".xlsx"

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
