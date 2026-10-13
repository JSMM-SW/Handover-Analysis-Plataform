"""Read and validate cellular measurement CSV exports."""
import codecs
import csv
import logging
import re
import unicodedata
from pathlib import Path
import pandas as pd
from app.shared.exceptions import ExtractionError, FileValidationError, SchemaValidationError
from app.modules.ingesta.etl.constants import (
    COLUMN_ALIASES_CSV,
    EXTRA_COLUMNS_CSV,
    MANDATORY_COLUMNS_CSV,
    ORIGEN_CSV,
    REQUIRED_COLUMNS_CSV,
)
from app.modules.ingesta.schemas import SheetInfo

logger = logging.getLogger(__name__)

def detect_format(filename: str) -> str:
    if Path(filename).suffix.lower() != ".csv":
        raise FileValidationError("Solo se permiten archivos CSV (.csv).")
    return ORIGEN_CSV


def normalize_header(name) -> str:
    """Forma comparable de un encabezado: sin BOM, tildes ni espacios en los
    extremos, en minúsculas, y con cualquier secuencia de espacios/'_'
    colapsada a un solo '_'. Así 'Cell ID', 'cell_id' y ' Cell  Id ' son lo
    mismo, y 'Tecnologia' encuentra 'Tecnología'.
    """
    text = "" if name is None else str(name).replace("﻿", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[\s_]+", "_", text.strip().lower())


def resolve_columns(
    headers: list, expected: list[str], aliases: dict[str, list[str]]
) -> dict[str, str]:
    """Busca cada columna de `expected` por nombre (no por posición) entre
    los `headers` reales del archivo. Devuelve {nombre_canónico: encabezado
    real} solo para las columnas encontradas; si dos encabezados reales
    coinciden con la misma columna, gana el primero.
    """
    by_normalized: dict[str, str] = {}
    for header in headers:
        by_normalized.setdefault(normalize_header(header), header)

    resolved: dict[str, str] = {}
    for column in expected:
        for candidate in [column, *aliases.get(column, [])]:
            actual = by_normalized.get(normalize_header(candidate))
            if actual is not None:
                resolved[column] = actual
                break
    return resolved


def missing_optional_columns_csv(sheets: list[SheetInfo]) -> list[str]:
    """Columnas de REQUIRED_COLUMNS_CSV que no existen en el archivo (ninguna
    obligatoria: esas ya se validaron en `validate_required_columns_csv`).
    """
    resolved = resolve_columns(sheets[0].headers, REQUIRED_COLUMNS_CSV, COLUMN_ALIASES_CSV)
    return [col for col in REQUIRED_COLUMNS_CSV if col not in resolved]


MENSAJE_SIN_REGISTROS = "El archivo no contiene registros (está vacío o solo tiene el encabezado)."

# Codificaciones aceptadas para CSV, en orden de preferencia: UTF-8 (con o sin
# BOM) y las dos variantes típicas de exportar desde Windows/Excel. latin-1
# decodifica cualquier byte, así que es el último recurso (nunca falla).
_CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
_ENCODING_CHUNK_BYTES = 1024 * 1024


def detect_csv_encoding(path: Path) -> str:
    """Primera codificación de _CSV_ENCODINGS que decodifica el archivo
    completo sin errores. Lee por bloques: no carga el archivo en memoria."""
    for encoding in _CSV_ENCODINGS[:-1]:
        decoder = codecs.getincrementaldecoder(encoding)()
        try:
            with open(path, "rb") as fh:
                while chunk := fh.read(_ENCODING_CHUNK_BYTES):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return encoding
        except UnicodeDecodeError:
            continue
        except OSError as exc:
            raise ExtractionError("El archivo CSV no pudo ser leído.") from exc
    return _CSV_ENCODINGS[-1]


def validate_has_data_rows(sheets: list[SheetInfo]) -> None:
    """Rechaza en la carga un archivo sin filas de datos, con un mensaje
    claro, en vez de dejar que termine como una ejecución "completed" vacía.
    `num_rows` ya cuenta solo filas de datos no vacías (Extract vuelve a
    verificarlo sobre las filas reales).
    """
    if sum(sheet.num_rows for sheet in sheets) == 0:
        raise ExtractionError(MENSAJE_SIN_REGISTROS)


def extract_csv_preview(path: Path, execution_id: str) -> list[SheetInfo]:
    """Lee solo los encabezados y cuenta filas de un CSV. Un CSV se
    representa como una única "hoja" sintética (`SheetInfo`), para no tener
    que cambiar `UploadResponse`.
    """
    encoding = detect_csv_encoding(path)
    try:
        with open(path, encoding=encoding, errors="strict") as fh:
            header_line = fh.readline()
            num_rows = sum(1 for line in fh if line.strip())  # sin líneas en blanco
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
    """Chequeo estructural previo a procesar registros (un solo "sheet"
    sintético): solo bloquea si faltan las columnas obligatorias
    (MANDATORY_COLUMNS_CSV). Las opcionales ausentes nunca bloquean.
    """
    resolved = resolve_columns(sheets[0].headers, MANDATORY_COLUMNS_CSV, COLUMN_ALIASES_CSV)
    missing = [col for col in MANDATORY_COLUMNS_CSV if col not in resolved]
    if missing:
        details = ", ".join(missing)
        logger.warning("[%s] Columnas obligatorias ausentes en CSV: %s", execution_id, details)
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {details}."
        )


def _read_csv(path: Path, encoding: str) -> pd.DataFrame:
    """Lee el CSV completo con el motor C de pandas (varias veces más rápido
    que el motor "python"), reproduciendo lo que hacía
    `read_csv(sep=None, engine="python")`: el delimitador se detecta con
    csv.Sniffer sobre la primera línea (lo mismo que hace pandas con
    sep=None), los tipos se infieren sobre la columna completa
    (low_memory=False) y los decimales se convierten con el conversor por
    defecto de pandas, el mismo que usa el motor "python" (verificado campo
    por campo con Session_41..47: `round_trip` y `legacy` cambian el último
    dígito de lat/long). Si el delimitador no se puede detectar así, o no es
    de un solo carácter, se usa la lectura anterior tal cual.
    """
    try:
        with open(path, encoding=encoding, newline="") as fh:
            first_line = fh.readline()
        delimiter = csv.Sniffer().sniff(first_line).delimiter
    except (csv.Error, OSError, UnicodeDecodeError):
        delimiter = None
    if not delimiter or len(delimiter) != 1:
        return pd.read_csv(path, sep=None, engine="python", encoding=encoding)
    return pd.read_csv(
        path,
        sep=delimiter,
        engine="c",
        encoding=encoding,
        low_memory=False,
    )


def extract_records_csv(path: Path, execution_id: str) -> list[dict]:
    """Lee un CSV completo (delimitador `;` o `,`, detectado automáticamente)
    y devuelve las filas de negocio crudas:
    {"hoja_origen": None, "fila_excel": int, "data": {...}}.

    `hoja_origen` es None porque un CSV no tiene el concepto de hojas. Las
    columnas se buscan por nombre (`resolve_columns`); "data" siempre trae
    todas las REQUIRED_COLUMNS_CSV, con None si la columna no existe en el
    archivo o la celda viene vacía. Las EXTRA_COLUMNS_CSV (`rssi_strongest`)
    solo se incluyen si existen en el archivo.
    """
    try:
        df = _read_csv(path, detect_csv_encoding(path))
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ExtractionError(
            "El archivo CSV no pudo ser leído (delimitador, codificación o formato incompatible)."
        ) from exc

    resolved = resolve_columns(list(df.columns), REQUIRED_COLUMNS_CSV, COLUMN_ALIASES_CSV)
    missing = [col for col in MANDATORY_COLUMNS_CSV if col not in resolved]
    if missing:
        raise SchemaValidationError(
            f"El archivo CSV no tiene la estructura esperada. Faltan: {', '.join(missing)}."
        )
    extras = resolve_columns(list(df.columns), EXTRA_COLUMNS_CSV, COLUMN_ALIASES_CSV)

    subset = df[list(resolved.values()) + list(extras.values())].rename(
        columns={actual: col for col, actual in {**resolved, **extras}.items()}
    )
    # Celdas vacías (NaN) -> None, igual que una columna opcional ausente:
    # así ninguna etapa posterior ve NaN (int(NaN) rompería el archivo entero).
    subset = subset.astype(object).where(subset.notna(), None)
    for col in REQUIRED_COLUMNS_CSV:
        if col not in subset.columns:
            subset[col] = None

    columns = REQUIRED_COLUMNS_CSV + [col for col in EXTRA_COLUMNS_CSV if col in extras]
    # to_dict("records") arma todos los dicts de una vez (mismos valores y
    # tipos que row.to_dict() fila por fila con iterrows, que era ~70% del
    # tiempo del pipeline en archivos de ~86k filas).
    records: list[dict] = [
        {
            "hoja_origen": None,
            "fila_excel": row_index + 2,  # +2: encabezado es la fila 1
            "data": data,
        }
        for row_index, data in zip(subset.index, subset[columns].to_dict("records"))
    ]

    if not records:
        raise ExtractionError(MENSAJE_SIN_REGISTROS)
    logger.info("[%s] Extracción CSV completa: %d registros crudos", execution_id, len(records))
    return records
