from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SheetInfo(BaseModel):
    """Información básica de una hoja del Excel, sin interpretar su contenido
    (eso corresponde a las etapas de Validate/Extract de negocio, aún no
    implementadas porque dependen de la estructura real del archivo)."""

    name: str
    num_rows: int
    num_cols: int
    headers: list[str] = Field(
        description="Valores de la primera fila de la hoja, tal cual se leen del archivo."
    )


class UploadResult(BaseModel):
    """Resultado trazable de la carga de un archivo.

    Los campos de trazabilidad completos (records_read/valid/rejected) se
    incorporarán cuando exista una etapa real de extracción de registros;
    en esta iteración el archivo solo se inspecciona a nivel de hoja.
    """

    execution_id: str
    original_filename: str
    stored_filename: str
    file_size_bytes: int
    upload_timestamp: datetime
    sheets: list[SheetInfo]
    processing_time_seconds: float
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    status: Literal["success", "error"]
