"""Extracción de información básica de un archivo Excel.

Alcance de esta iteración: identificar hojas y su forma (filas, columnas,
encabezados), sin interpretar el significado de las columnas. Las reglas de
qué hoja/columnas son relevantes para el dominio de handover se definirán
tras analizar un archivo real (Objetivo 2 del plan de tesis).
"""

import logging
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.modules.ingesta.etl.constants import (
    ORIGEN_CSV,
    ORIGEN_XLSX,
    REQUIRED_COLUMNS_CSV,
    REQUIRED_COLUMNS_XLSX,
)
from app.modules.ingesta.schemas import SheetInfo

logger = logging.getLogger(__name__)


def detect_format(filename: str) -> str:
    """Determina el origen ('xlsx' o 'csv') a partir de la extensión.

    Se asume que la extensión ya pasó `validate_uploaded_file` (que valida
    contra las extensiones permitidas en Settings); esta función solo
    traduce la extensión al identificador de origen usado en todo el pipeline.
    """
    extension = Path(filename).suffix.lower()
    if extension == ".xlsx":
        return ORIGEN_XLSX
    if extension == ".csv":
        return ORIGEN_CSV
    raise FileValidationError(f"Extensión '{extension}' no soportada por el pipeline ETL.")

_INVALID_EXCEL_MESSAGE = (
    "El archivo no pudo ser leído como un Excel válido (formato incompatible o corrupto)."
)


def _open_workbook(path: Path, execution_id: str):
    try:
        return openpyxl.load_workbook(path, read_only=True, data_only=True)
    except (InvalidFileException, OSError, KeyError) as exc:
        logger.warning("[%s] No se pudo abrir el archivo como Excel: %s", execution_id, exc)
        raise ExtractionError(_INVALID_EXCEL_MESSAGE) from exc
    except Exception as exc:  # zipfile.BadZipFile y otros errores internos de openpyxl
        logger.warning("[%s] Error inesperado al abrir el archivo: %s", execution_id, exc)
        raise ExtractionError(_INVALID_EXCEL_MESSAGE) from exc


def extract_basic_info(path: Path, execution_id: str) -> list[SheetInfo]:
    workbook = _open_workbook(path, execution_id)

    try:
        if not workbook.sheetnames:
            raise ExtractionError("El archivo no contiene hojas.")

        sheets: list[SheetInfo] = []
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            header_row = next(
                worksheet.iter_rows(min_row=1, max_row=1, values_only=True), ()
            )
            headers = ["" if value is None else str(value) for value in header_row]

            sheets.append(
                SheetInfo(
                    name=sheet_name,
                    num_rows=worksheet.max_row or 0,
                    num_cols=worksheet.max_column or 0,
                    headers=headers,
                )
            )
        return sheets
    finally:
        workbook.close()


def validate_required_columns_xlsx(sheets: list[SheetInfo], execution_id: str) -> None:
    """Verifica que cada hoja tenga las columnas de negocio requeridas.

    Es un chequeo estructural (bloquea todo el archivo si falla), distinto
    de las validaciones por registro que hace el Validator sobre cada fila.
    """
    missing_by_sheet: dict[str, list[str]] = {}
    for sheet in sheets:
        missing = [col for col in REQUIRED_COLUMNS_XLSX if col not in sheet.headers]
        if missing:
            missing_by_sheet[sheet.name] = missing

    if missing_by_sheet:
        details = "; ".join(
            f"'{sheet}' no tiene: {', '.join(cols)}"
            for sheet, cols in missing_by_sheet.items()
        )
        logger.warning("[%s] Columnas requeridas ausentes: %s", execution_id, details)
        raise SchemaValidationError(
            f"El archivo no tiene la estructura esperada. {details}."
        )


def extract_records_xlsx(path: Path, execution_id: str) -> list[dict]:
    """Lee todas las hojas del Excel y devuelve las filas de negocio crudas.

    Cada elemento es {"hoja_origen": str, "fila_excel": int, "data": {...}},
    donde "data" solo contiene REQUIRED_COLUMNS_XLSX con sus valores tal como
    vienen del Excel (sin limpiar ni normalizar todavía).
    """
    workbook = _open_workbook(path, execution_id)

    try:
        records: list[dict] = []
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            header_row = next(
                worksheet.iter_rows(min_row=1, max_row=1, values_only=True), ()
            )
            headers = ["" if value is None else str(value) for value in header_row]
            column_index = {
                col: headers.index(col) for col in REQUIRED_COLUMNS_XLSX if col in headers
            }

            for excel_row_number, row in enumerate(
                worksheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                if row is None or all(value is None for value in row):
                    continue  # fila completamente vacía, no es un registro
                data = {col: row[idx] for col, idx in column_index.items()}
                records.append(
                    {
                        "hoja_origen": sheet_name,
                        "fila_excel": excel_row_number,
                        "data": data,
                    }
                )

        logger.info("[%s] Extracción completa: %d registros crudos", execution_id, len(records))
        return records
    finally:
        workbook.close()


def extract_csv_preview(path: Path, execution_id: str) -> list[SheetInfo]:
    """Lee solo los encabezados y cuenta filas de un CSV, devolviendo el mismo
    tipo `SheetInfo` que usa el flujo xlsx (un CSV se representa como una
    única "hoja" sintética), para no tener que cambiar `UploadResponse`.
    """
    try:
        with open(path, encoding="utf-8", errors="strict") as fh:
            header_line = fh.readline()
            num_rows = sum(1 for _ in fh)
    except (OSError, UnicodeDecodeError) as exc:
        raise ExtractionError(
            "El archivo no pudo ser leído como CSV (codificación o formato incompatible)."
        ) from exc

    if not header_line.strip():
        raise ExtractionError("El archivo CSV está vacío.")

    delimiter = ";" if header_line.count(";") >= header_line.count(",") else ","
    headers = [h.strip() for h in header_line.rstrip("\r\n").split(delimiter)]

    return [
        SheetInfo(name=path.stem, num_rows=num_rows, num_cols=len(headers), headers=headers)
    ]


def validate_required_columns_csv(sheets: list[SheetInfo], execution_id: str) -> None:
    """Equivalente csv de `validate_required_columns_xlsx` (un solo "sheet" sintético)."""
    sheet = sheets[0]
    missing = [col for col in REQUIRED_COLUMNS_CSV if col not in sheet.headers]
    if missing:
        details = ", ".join(missing)
        logger.warning("[%s] Columnas requeridas ausentes en CSV: %s", execution_id, details)
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {details}."
        )


def extract_records_csv(path: Path, execution_id: str) -> list[dict]:
    """Lee un CSV completo (delimitador `;` o `,`, detectado automáticamente)
    y devuelve las filas de negocio crudas en el mismo formato que
    `extract_records_xlsx`: {"hoja_origen": None, "fila_excel": int, "data": {...}}.

    `hoja_origen` es None porque un CSV no tiene el concepto de hojas.
    """
    try:
        df = pd.read_csv(path, sep=None, engine="python")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ExtractionError(
            "El archivo CSV no pudo ser leído (delimitador, codificación o formato incompatible)."
        ) from exc

    missing = [col for col in REQUIRED_COLUMNS_CSV if col not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {', '.join(missing)}."
        )

    records: list[dict] = []
    for row_index, row in df[REQUIRED_COLUMNS_CSV].iterrows():
        records.append(
            {
                "hoja_origen": None,
                "fila_excel": row_index + 2,  # +2: encabezado es la fila 1
                "data": row.to_dict(),
            }
        )

    logger.info("[%s] Extracción CSV completa: %d registros crudos", execution_id, len(records))
    return records
