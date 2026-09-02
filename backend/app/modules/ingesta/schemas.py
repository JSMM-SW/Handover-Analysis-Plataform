from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SheetInfo(BaseModel):
    """Información básica de una hoja del Excel, sin interpretar su contenido
    (eso corresponde a las etapas de negocio: Validate/Clean/Normalize)."""

    name: str
    num_rows: int
    num_cols: int
    headers: list[str] = Field(
        description="Valores de la primera fila de la hoja, tal cual se leen del archivo."
    )


class UploadResponse(BaseModel):
    """Resultado de recibir y almacenar el archivo (etapas Validate de
    archivo + Extract de estructura). Todavía no crea una ejecución en base
    de datos ni corre las reglas de negocio por registro: eso ocurre en
    POST /ingestion/process, usando `upload_id`/`stored_filename` de aquí.
    """

    upload_id: str
    original_filename: str
    stored_filename: str
    file_size_bytes: int
    upload_timestamp: datetime
    sheets: list[SheetInfo]
    status: Literal["uploaded"]


class ProcessRequest(BaseModel):
    stored_filename: str
    original_filename: str


class ProcessResult(BaseModel):
    """Resultado trazable de una corrida completa del pipeline ETL,
    reflejando la fila persistida en `etl_execution`."""

    execution_id: str
    filename: str
    records_read: int
    records_valid: int
    records_rejected: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    processing_time_seconds: float
    status: Literal["completed", "failed"]


class StatusResponse(BaseModel):
    """Lectura del estado persistido de una ejecución (GET /ingestion/status/{id})."""

    execution_id: str
    filename: str
    status: str
    processing_date: datetime
    records_read: int
    records_valid: int
    records_rejected: int
    warnings: list[str]
    errors: list[str]
    processing_time_seconds: float | None
