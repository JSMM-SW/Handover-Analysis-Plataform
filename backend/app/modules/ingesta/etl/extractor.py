"""Read and validate cellular measurement CSV exports."""
import logging
from pathlib import Path
import pandas as pd
from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.modules.ingesta.etl.constants import ORIGEN_CSV, REQUIRED_COLUMNS_CSV
from app.modules.ingesta.schemas import SheetInfo

logger = logging.getLogger(__name__)

def detect_format(filename: str) -> str:
    if Path(filename).suffix.lower() != ".csv":
        raise FileValidationError("Solo se permiten archivos CSV (.csv).")
    return ORIGEN_CSV


def extract_csv_preview(path: Path, execution_id: str) -> list[SheetInfo]:
    """Return CSV headers and row count using the upload metadata contract."""
    try:
        with open(path, encoding="utf-8-sig", errors="strict") as fh:
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
    """Check the required CSV headers before processing any records."""
    sheet = sheets[0]
    missing = [col for col in REQUIRED_COLUMNS_CSV if col not in sheet.headers]
    if missing:
        details = ", ".join(missing)
        logger.warning("[%s] Columnas requeridas ausentes en CSV: %s", execution_id, details)
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {details}."
        )


def extract_records_csv(path: Path, execution_id: str) -> list[dict]:
    """Read CSV observations; retain the source row number for rejected records."""
    try:
        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ExtractionError(
            "El archivo CSV no pudo ser leído (delimitador, codificación o formato incompatible)."
        ) from exc

    missing = [col for col in REQUIRED_COLUMNS_CSV if col not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {', '.join(missing)}."
        )

    columns = REQUIRED_COLUMNS_CSV + (["rssi_strongest"] if "rssi_strongest" in df.columns else [])
    df = df.astype(object).where(pd.notna(df), None)
    records: list[dict] = []
    for row_index, row in df[columns].iterrows():
        records.append(
            {
                "hoja_origen": None,
                "fila_excel": row_index + 2,  # +2: encabezado es la fila 1
                "data": row.to_dict(),
            }
        )

    logger.info("[%s] Extracción CSV completa: %d registros crudos", execution_id, len(records))
    return records
