import csv
import io
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Callable
from zoneinfo import ZoneInfo

import psycopg
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from app.shared.config import Settings
from app.shared.db.database import SessionLocal
from app.shared.exceptions import (
    DuplicateFileError,
    ExtractionError,
    FileValidationError,
    IngestionCancelled,
    LoadVerificationError,
    SchemaValidationError,
)
from app.shared.file_utils import sanitize_filename
from app.modules.ingesta.etl.cleaner import apply_sentinels_csv, deduplicate
from app.modules.ingesta.etl.constants import (
    DEDUP_KEY_CSV,
    MOTIVO_DUPLICADO,
    MOTIVO_VALOR_NO_INTERPRETABLE,
    ORIGEN_CSV,
)
from app.modules.ingesta.etl.extractor import (
    detect_format,
    extract_csv_preview,
    extract_records_csv,
    missing_optional_columns_csv,
    validate_has_data_rows,
    validate_required_columns_csv,
)
from app.modules.ingesta.etl.normalizer import (
    normalize_record_csv,
)
from app.modules.ingesta.etl.tecnologia import net_type_audit_warnings
from app.modules.ingesta.etl.transformer import structure_record
from app.modules.ingesta.etl.validator import (
    validate_record_csv,
    validate_upload_metadata,
)
from app.modules.ingesta.etl.velocity import compute_velocities
from app.modules.ingesta.monitor import ExecutionMonitor, default_monitor
from app.modules.ingesta.repository import HandoverRepository
from app.modules.ingesta.schemas import CancelResponse, ProcessRequest, ProcessResult, UploadResponse

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    records_read: int
    valid_records: list[dict] = field(default_factory=list)
    rejected_records: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_rejected(record: dict, motivo: str, datos_crudos: dict | None = None) -> dict:
    return {
        "hoja_origen": record["hoja_origen"],
        "fila_excel": record["fila_excel"],
        "motivo_rechazo": motivo,
        "datos_crudos": record["data"] if datos_crudos is None else datos_crudos,
    }


# Errores que puede lanzar un valor presente pero no interpretable (ej. texto
# en una columna numérica): rechazan esa fila, nunca el archivo entero.
_ERRORES_DE_VALOR = (ValueError, TypeError, OverflowError)

# Efecto de que falte una columna opcional, cuando no es el genérico "NULL".
_EFECTO_COLUMNA_AUSENTE = {
    # Fuente de `tecnologia` (NOT NULL): sin ella no hay fila que se pueda
    # guardar (ver etl/tecnologia.py).
    "tech": "no se puede asignar `tecnologia` (NOT NULL): todas las filas se rechazan",
}
_EFECTO_GENERICO = "el campo se guarda como NULL en todas las filas"


def _missing_column_warning(column: str) -> str:
    """UN warning por columna ausente y por ejecución (no por fila)."""
    efecto = _EFECTO_COLUMNA_AUSENTE.get(column, _EFECTO_GENERICO)
    return f"Columna '{column}' ausente en el archivo: {efecto}"


def _rejected_unparseable(record: dict, exc: Exception, datos_crudos: dict | None = None) -> dict:
    return _build_rejected(record, f"{MOTIVO_VALOR_NO_INTERPRETABLE}: {exc}", datos_crudos)


def _run_pipeline_csv(
    path: Path, archivo_origen: str, execution_id: str, on_stage: Callable[[str], None]
) -> PipelineResult:
    on_stage("extract")
    sheets = extract_csv_preview(path, execution_id)
    validate_required_columns_csv(sheets, execution_id)

    raw_records = extract_records_csv(path, execution_id)

    rejected: list[dict] = []
    candidates: list[dict] = []
    nulled_field_counts: dict[str, int] = {}

    on_stage("validate")
    for record in raw_records:
        try:
            motivo = validate_record_csv(record["data"])
            if not motivo:
                cleaned_data, nulled_fields = apply_sentinels_csv(record["data"])
        except _ERRORES_DE_VALOR as exc:
            rejected.append(_rejected_unparseable(record, exc))
            continue
        if motivo:
            rejected.append(_build_rejected(record, motivo))
            continue

        for field_name in nulled_fields:
            label = field_name
            nulled_field_counts[label] = nulled_field_counts.get(label, 0) + 1

        candidates.append(
            {
                "hoja_origen": record["hoja_origen"],
                "fila_excel": record["fila_excel"],
                "data": cleaned_data,
                "datos_crudos_originales": record["data"],
            }
        )

    on_stage("clean")
    unique, duplicates = deduplicate(candidates, DEDUP_KEY_CSV)
    rejected.extend(
        _build_rejected(record, MOTIVO_DUPLICADO, datos_crudos=record["datos_crudos_originales"])
        for record in duplicates
    )

    on_stage("normalize")
    valid_records: list[dict] = []
    for record in unique:
        try:
            normalized = normalize_record_csv(record["data"])
        except _ERRORES_DE_VALOR as exc:
            rejected.append(
                _rejected_unparseable(record, exc, datos_crudos=record["datos_crudos_originales"])
            )
            continue
        valid_records.append(
            structure_record(normalized, record["hoja_origen"], archivo_origen, ORIGEN_CSV)
        )

    on_stage("structure")
    warnings: list[str] = [
        _missing_column_warning(column) for column in missing_optional_columns_csv(sheets)
    ]
    warnings.extend(net_type_audit_warnings(valid_records))
    for field_name, count in sorted(nulled_field_counts.items()):
        if field_name == "gps":
            # Ya no es motivo de rechazo (ver validator.py/cleaner.py): se
            # anulan latitud/longitud y se conserva el resto del registro
            # (cid/tech/rsrp/timestamp), en vez de rechazar el registro
            # completo — confirmado necesario con Session_43_20260623_165825.csv.
            warnings.append(
                f"{count} registro(s) csv con gps sin fix (centinela lat/long = -1), "
                "latitud/longitud guardadas como NULL"
            )
        else:
            warnings.append(
                f"{count} registro(s) csv con {field_name} = centinela (sin dato), guardado como NULL"
            )

    # No hay `gps_reject_anchors` para csv: gps sin fix ya no rechaza el
    # registro, así que nunca aparece en `rejected` con ese motivo. El
    # "romper la cadena" de velocidad para estos casos lo maneja
    # compute_velocities directamente vía has_position (latitud/longitud NULL
    # en el propio valid_record).
    warnings.extend(compute_velocities(valid_records, []))

    logger.info(
        "[%s] Pipeline csv: %d leídos, %d válidos, %d rechazados",
        execution_id,
        len(raw_records),
        len(valid_records),
        len(rejected),
    )

    return PipelineResult(
        records_read=len(raw_records),
        valid_records=valid_records,
        rejected_records=rejected,
        warnings=warnings,
    )


def run_pipeline(
    path: Path,
    archivo_origen: str,
    execution_id: str,
    on_stage: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Orquesta las etapas puras del pipeline ETL (Extract -> Validate -> Clean
    -> Normalize -> Structure) para el formato detectado a partir del nombre
    del archivo. No conoce la base de datos ni el Repository: solo recibe una
    ruta de archivo y devuelve los registros listos para persistir.

    `on_stage(etapa)` se llama al entrar a cada etapa (avance, latido y
    cancelación cooperativa: si lanza IngestionCancelled, el pipeline se
    detiene ahí). No cambia el resultado.
    """
    detect_format(archivo_origen)
    detect_format(path.name)
    return _run_pipeline_csv(path, archivo_origen, execution_id, on_stage or (lambda etapa: None))


# Los archivos que guarda /upload llevan el upload_id (UUID) como prefijo. Solo
# esos se borran automáticamente: nunca un archivo colocado a mano en data/input/.
_UPLOAD_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", re.IGNORECASE
)


def stored_upload_path(settings: Settings, stored_filename: str) -> Path:
    """Ruta del archivo temporal dentro de data/input/. Rechaza cualquier
    `stored_filename` (lo envía el cliente) que apunte fuera de esa carpeta."""
    base = settings.resolved_data_input_dir().resolve()
    path = (base / stored_filename).resolve()
    if path.parent != base:
        raise FileValidationError("El archivo indicado no es una subida válida.")
    return path


def delete_stored_upload(settings: Settings, stored_filename: str | None, motivo: str) -> bool:
    """Borra un archivo temporal de data/input/ y lo registra en el log con
    su motivo. Solo borra archivos con prefijo de upload_id que estén dentro
    de data/input/. Devuelve True si borró algo."""
    if not stored_filename or not _UPLOAD_PREFIX.match(stored_filename):
        return False
    try:
        path = stored_upload_path(settings, stored_filename)
    except FileValidationError:
        logger.warning("No se borra '%s': está fuera de data/input/", stored_filename)
        return False
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError as exc:
        logger.warning("No se pudo borrar el archivo temporal '%s': %s", path.name, exc)
        return False
    logger.info("Archivo temporal borrado: '%s' (motivo: %s)", path.name, motivo)
    return True


def handle_upload(filename: str, content: bytes, settings: Settings) -> UploadResponse:
    """Variante de `handle_upload_stream` para contenido ya en memoria."""
    return handle_upload_stream(filename, io.BytesIO(content), len(content), settings)


MENSAJE_SUBIDA_INCOMPLETA = "El archivo no se subió correctamente"


class IncompleteUploadError(FileValidationError):
    """Los bytes recibidos no coinciden con el tamaño que declaró el cliente
    (subida cortada o corrupta)."""


def handle_upload_stream(
    filename: str,
    stream: BinaryIO,
    size_bytes: int | None,
    settings: Settings,
    declared_size: int | None = None,
) -> UploadResponse:
    """Recibe el archivo, lo valida a nivel de archivo, lo guarda y confirma
    que su estructura (columnas requeridas) es la esperada. No crea todavía
    una ejecución en base de datos ni aplica reglas de negocio por registro.

    El contenido se copia a data/input/ por bloques (nunca se carga completo
    en memoria). `size_bytes` es el tamaño conocido de antemano (None si no
    se conoce): permite rechazar por tamaño antes de escribir nada; el tope
    se vuelve a controlar mientras se copia. `declared_size` es el tamaño que
    el cliente dice haber enviado: si los bytes recibidos no coinciden, la
    subida se rechaza ("El archivo no se subió correctamente"). Si algo
    falla, el archivo parcial se borra.
    """
    upload_id = str(uuid.uuid4())
    logger.info("[%s] Carga recibida: '%s' (%s bytes)", upload_id, filename, size_bytes)

    # Sin tamaño conocido se valida nombre/extensión ahora y el tamaño al copiar.
    validate_upload_metadata(filename, size_bytes if size_bytes is not None else 1, settings)

    stored_filename = f"{upload_id}_{sanitize_filename(filename)}"
    destination = settings.resolved_data_input_dir() / stored_filename
    try:
        written = 0
        with open(destination, "wb") as out:
            while chunk := stream.read(settings.upload_chunk_bytes):
                written += len(chunk)
                if written > settings.max_upload_size_bytes:
                    break  # deja de recibir: el mensaje lo arma validate_upload_metadata
                out.write(chunk)
        if declared_size is not None and written != declared_size:
            logger.warning(
                "[%s] Subida incompleta de '%s': %d bytes recibidos, %d declarados",
                upload_id, filename, written, declared_size,
            )
            raise IncompleteUploadError(
                f"{MENSAJE_SUBIDA_INCOMPLETA}: se recibieron {written} de {declared_size} bytes. "
                "Vuelve a intentarlo."
            )
        validate_upload_metadata(filename, written, settings)
        logger.info("[%s] Archivo almacenado en '%s' (%d bytes)", upload_id, destination, written)

        sheets = extract_csv_preview(destination, upload_id)
        validate_required_columns_csv(sheets, upload_id)
        validate_has_data_rows(sheets)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    return UploadResponse(
        upload_id=upload_id,
        original_filename=filename,
        stored_filename=stored_filename,
        file_size_bytes=written,
        upload_timestamp=datetime.now(timezone.utc),
        sheets=sheets,
        status="uploaded",
    )


def _duplicate_message(filename: str, existing, settings: Settings) -> str:
    fecha = (
        existing.processing_date.astimezone(ZoneInfo(settings.display_timezone)).strftime("%d/%m/%Y %H:%M")
        if existing is not None and existing.processing_date is not None
        else None
    )
    if existing is not None and existing.status == "completed":
        sesion = f"Sesión {existing.sesion_label}" if existing.sesion_label is not None else "una sesión"
        cuando = f" el {fecha}" if fecha else ""
        return f"El archivo '{filename}' ya fue cargado como {sesion}{cuando}. No se volvió a procesar."
    cuando = f" (iniciado el {fecha})" if fecha else ""
    return f"El archivo '{filename}' ya se está procesando{cuando}. No se volvió a procesar."


def ensure_not_already_loaded(
    filename: str, repository: HandoverRepository, settings: Settings
) -> None:
    """Rechaza (DuplicateFileError, HTTP 409) un archivo cuyo nombre original
    normalizado ya tiene una ejecución "completed" o "processing". Se llama
    antes de guardar o procesar nada. Las ejecuciones "failed" no bloquean.
    """
    existing = repository.find_active_execution_by_filename(filename)
    if existing is not None:
        raise DuplicateFileError(_duplicate_message(filename, existing, settings))


def start_ingestion(
    payload: ProcessRequest, settings: Settings, repository: HandoverRepository
) -> ProcessResult:
    """Parte síncrona de POST /process: verifica que el archivo subido siga
    disponible y crea la ejecución en estado "processing". El pipeline y la
    carga corren después en segundo plano (`execute_ingestion`); el cliente
    consulta el avance con GET /status/{execution_id}.

    Un archivo ya cargado (o en proceso) se rechaza con DuplicateFileError y
    se borra su copia en data/input/: no se vuelve a procesar.
    """
    detect_format(payload.original_filename)
    detect_format(payload.stored_filename)
    path = stored_upload_path(settings, payload.stored_filename)
    if not path.exists():
        raise FileValidationError(
            "El archivo cargado ya no está disponible en el servidor; vuelve a subirlo."
        )

    try:
        ensure_not_already_loaded(payload.original_filename, repository, settings)
        execution_id = repository.create_execution(
            filename=payload.original_filename, stored_filename=payload.stored_filename
        )  # "processing"
    except DuplicateFileError as exc:
        delete_stored_upload(settings, payload.stored_filename, "archivo duplicado, no se procesa")
        existing = repository.find_active_execution_by_filename(payload.original_filename)
        message = _duplicate_message(payload.original_filename, existing, settings)
        logger.info("Archivo duplicado rechazado en /process: %s", message)
        raise DuplicateFileError(message) from exc
    logger.info("[%s] Ejecución creada para '%s'", execution_id, payload.original_filename)
    # sesion_label es None hasta que la ejecución queda "completed": el número
    # se asigna al confirmar la carga (ver trigger en schema.sql), así que un
    # fallo o cancelación no lo consume. GET /status lo devuelve al terminar.
    return ProcessResult(
        execution_id=str(execution_id),
        sesion_label=None,
        filename=payload.original_filename,
        records_read=0,
        records_valid=0,
        records_rejected=0,
        processing_time_seconds=0.0,
        status="processing",
    )


MENSAJE_SIN_CONEXION = (
    "No se pudo conectar con la base de datos para procesar el archivo. "
    "No se guardó ningún dato; vuelve a intentarlo."
)
MENSAJE_CONEXION_PERDIDA = (
    "Se perdió la conexión con la base de datos durante la carga. "
    "No se guardó ningún dato; vuelve a intentarlo."
)


def _open_repository(
    session_factory: Callable[[], Session], settings: Settings, execution_id: uuid.UUID
) -> tuple[Session, HandoverRepository]:
    """Abre la sesión de la carga y comprueba que la conexión responde, con
    reintentos y espera creciente. Es lo único que se reintenta: todavía no
    se escribió nada, así que repetirlo es seguro."""
    delay = settings.db_connect_retry_backoff_seconds
    for attempt in range(settings.db_connect_retries + 1):
        db = session_factory()
        try:
            repository = HandoverRepository(db, settings.load_batch_rows)
            repository.ping()
            return db, repository
        except DBAPIError as exc:
            db.close()
            if attempt == settings.db_connect_retries:
                raise
            logger.warning(
                "[%s] Conexión a la base fallida (intento %d de %d), reintento en %.1fs: %s",
                execution_id, attempt + 1, settings.db_connect_retries + 1, delay, exc,
            )
            time.sleep(delay)
            delay *= 2
    raise AssertionError("inalcanzable")  # pragma: no cover


def _mark_failed(
    db: Session | None,
    session_factory: Callable[[], Session],
    settings: Settings,
    execution_id: uuid.UUID,
    error: str,
    started_at: float,
) -> None:
    """Deja la ejecución en "failed" con su mensaje, sin registros (rollback
    total). Si la conexión original murió, usa una nueva; si tampoco hay
    conexión, queda registrado en el log con el execution_id."""
    def finish(repository: HandoverRepository) -> None:
        repository.finish_execution(
            execution_id,
            records_read=0,
            records_valid=0,
            records_rejected=0,
            warnings=[],
            errors=[error],
            processing_time_seconds=round(time.perf_counter() - started_at, 3),
        )

    if db is not None:
        try:
            db.rollback()
            finish(HandoverRepository(db, settings.load_batch_rows))
            return
        except DBAPIError:
            logger.warning("[%s] La conexión de la carga ya no responde; se usa una nueva", execution_id)
            db.close()
    try:
        fresh_db, repository = _open_repository(session_factory, settings, execution_id)
    except DBAPIError:
        logger.exception("[%s] No se pudo registrar el fallo de la ejecución: %s", execution_id, error)
        return
    try:
        finish(repository)
    finally:
        fresh_db.close()


MENSAJE_ERROR_INESPERADO = (
    "Ocurrió un error inesperado durante el procesamiento. No se guardó ningún dato; "
    "vuelve a intentarlo. Si el problema continúa, indica este identificador al equipo: {execution_id}"
)
MENSAJE_INTERRUMPIDA = (
    "Ejecución interrumpida: el servidor se detuvo antes de terminar el procesamiento. "
    "No se guardó ningún dato; el archivo se puede volver a cargar."
)
MENSAJE_CANCELADA = "Procesamiento cancelado. No se guardó ningún dato."


def _verify_load(
    repository: HandoverRepository, execution_id: uuid.UUID, expected_valid: int, expected_rejected: int
) -> None:
    """Verificación posterior al Load, antes del commit: las filas realmente
    insertadas deben coincidir con los contadores de la ejecución."""
    valid, rejected = repository.count_records(execution_id)
    if (valid, rejected) != (expected_valid, expected_rejected):
        logger.error(
            "[%s] Verificación post-Load fallida: esperados %d válidos / %d rechazados, en la base %d / %d",
            execution_id, expected_valid, expected_rejected, valid, rejected,
        )
        raise LoadVerificationError(
            "La verificación posterior a la carga no coincidió: se esperaban "
            f"{expected_valid} registros válidos y {expected_rejected} rechazados, y la base recibió "
            f"{valid} y {rejected}. No se guardó ningún dato; vuelve a intentarlo."
        )


def execute_ingestion(
    execution_id: uuid.UUID,
    payload: ProcessRequest,
    settings: Settings,
    session_factory: Callable[[], Session] = SessionLocal,
    monitor_factory: Callable[[uuid.UUID, Settings], ExecutionMonitor] = default_monitor,
) -> None:
    """Corre el pipeline ETL completo y persiste el resultado. Pensado para
    ejecutarse en segundo plano, con su propia sesión de base de datos.

    Nunca deja la ejecución en "processing": cualquier error (esperado o no)
    se registra como "failed" con su mensaje. El Load va en una sola
    transacción: registros y estado final se confirman en un solo commit
    (`finish_execution`); si algo falla antes (incluida la pérdida de la
    conexión a mitad de la carga) o el usuario cancela, se hace rollback
    total y no queda ninguna fila de esta ejecución en handover_record ni en
    handover_record_rejected, ni se consume número de sesión.

    El `monitor` escribe etapa, avance y latido por una conexión aparte y
    revisa la cancelación entre etapas y entre lotes de COPY. Al terminar
    (completed, failed o cancelled) se borra el archivo temporal.
    """
    started_at = time.perf_counter()
    path = settings.resolved_data_input_dir() / payload.stored_filename
    monitor = monitor_factory(execution_id, settings)
    db: Session | None = None
    try:
        try:
            db, repository = _open_repository(session_factory, settings, execution_id)
        except DBAPIError:
            logger.exception("[%s] Sin conexión a la base para iniciar la carga", execution_id)
            _mark_failed(None, session_factory, settings, execution_id, MENSAJE_SIN_CONEXION, started_at)
            delete_stored_upload(settings, payload.stored_filename, "ejecución fallida")
            return

        try:
            pipeline_result = run_pipeline(
                path, payload.original_filename, str(execution_id), on_stage=monitor.stage
            )
            n_valid, n_rejected = len(pipeline_result.valid_records), len(pipeline_result.rejected_records)
            total = n_valid + n_rejected

            monitor.stage("load")
            repository.save_valid_records(
                execution_id, pipeline_result.valid_records, lambda sent: monitor.load_progress(sent, total)
            )
            repository.save_rejected_records(
                execution_id,
                pipeline_result.rejected_records,
                lambda sent: monitor.load_progress(n_valid + sent, total),
            )

            monitor.stage("verify")
            _verify_load(repository, execution_id, n_valid, n_rejected)
            repository.finish_execution(
                execution_id,
                records_read=pipeline_result.records_read,
                records_valid=n_valid,
                records_rejected=n_rejected,
                warnings=pipeline_result.warnings,
                errors=[],
                processing_time_seconds=round(time.perf_counter() - started_at, 3),
            )
            logger.info("[%s] Ejecución completada", execution_id)
            delete_stored_upload(settings, payload.stored_filename, "ejecución completada")
            return
        except IngestionCancelled:
            logger.info("[%s] Ejecución cancelada por el usuario: rollback total", execution_id)
            _mark_cancelled(db, session_factory, settings, execution_id, started_at)
            delete_stored_upload(settings, payload.stored_filename, "ejecución cancelada")
            return
        except (ExtractionError, SchemaValidationError, FileValidationError, LoadVerificationError) as exc:
            logger.warning("[%s] Ejecución fallida: %s", execution_id, exc)
            error = str(exc)
        except (OperationalError, InterfaceError, psycopg.OperationalError, psycopg.InterfaceError):
            logger.exception("[%s] Conexión a la base perdida durante la carga", execution_id)
            error = MENSAJE_CONEXION_PERDIDA
        except Exception:  # noqa: BLE001 — la ejecución nunca debe quedar colgada
            # El detalle (tipo, mensaje, traza) va solo al log, con el
            # execution_id; al usuario se le muestra un mensaje sin rutas ni trazas.
            logger.exception("[%s] Error inesperado en la ejecución", execution_id)
            error = MENSAJE_ERROR_INESPERADO.format(execution_id=execution_id)

        _mark_failed(db, session_factory, settings, execution_id, error, started_at)
        delete_stored_upload(settings, payload.stored_filename, "ejecución fallida")
    finally:
        monitor.close()
        if db is not None:
            db.close()


def _mark_cancelled(
    db: Session,
    session_factory: Callable[[], Session],
    settings: Settings,
    execution_id: uuid.UUID,
    started_at: float,
) -> None:
    """Rollback total del Load y estado "cancelled" (si la ejecución ya fue
    cerrada desde fuera, p. ej. marcada como interrumpida, no la toca)."""
    elapsed = round(time.perf_counter() - started_at, 3)
    try:
        db.rollback()
        HandoverRepository(db, settings.load_batch_rows).mark_cancelled(execution_id, elapsed)
        return
    except DBAPIError:
        logger.warning("[%s] La conexión de la carga ya no responde; se usa una nueva", execution_id)
        db.close()
    try:
        fresh_db, repository = _open_repository(session_factory, settings, execution_id)
    except DBAPIError:
        logger.exception("[%s] No se pudo registrar la cancelación", execution_id)
        return
    try:
        repository.mark_cancelled(execution_id, elapsed)
    finally:
        fresh_db.close()


def request_cancellation(
    execution_id: uuid.UUID, repository: HandoverRepository, settings: Settings
) -> CancelResponse | None:
    """POST /cancel/{execution_id}. Enciende la bandera de cancelación; el
    pipeline la ve entre etapas o lotes, hace rollback y deja la ejecución
    "cancelled". Devuelve None si la ejecución no existe y lanza
    FileValidationError (-> 409) si ya terminó.

    Si la ejecución lleva más del umbral sin latido (nadie la está
    procesando: el servidor se reinició), se cancela aquí mismo.
    """
    execution = repository.get_execution(execution_id)
    if execution is None:
        return None
    if execution.status == "completed":
        raise FileValidationError(
            "La ejecución ya está completada: los datos ya se guardaron y no se puede cancelar."
        )
    if execution.status != "processing" or not repository.request_cancel(execution_id):
        raise FileValidationError("La ejecución ya terminó y no se puede cancelar.")

    sin_latido = datetime.now(timezone.utc) - execution.updated_at
    if sin_latido > timedelta(minutes=settings.stale_execution_minutes):
        # Nadie la está procesando: no hay Load que revertir, se cierra aquí.
        stored_filename = execution.stored_filename
        repository.mark_cancelled(execution_id)
        delete_stored_upload(settings, stored_filename, "ejecución interrumpida y cancelada")
        logger.info("[%s] Ejecución sin latido cancelada directamente", execution_id)
        return CancelResponse(execution_id=str(execution_id), status="cancelled", message=MENSAJE_CANCELADA)
    logger.info("[%s] Cancelación solicitada", execution_id)
    return CancelResponse(
        execution_id=str(execution_id),
        status="cancelling",
        message="Cancelación solicitada. El procesamiento se detendrá en unos segundos.",
    )


def expire_stale_executions(
    repository: HandoverRepository, settings: Settings, execution_id: uuid.UUID | None = None
) -> int:
    """Marca como "failed" ("interrumpida") las ejecuciones en "processing"
    sin latido desde hace más de STALE_EXECUTION_MINUTES y borra sus archivos
    temporales. Se llama al arrancar la app y al consultar /status."""
    stale = repository.mark_stale_executions(
        settings.stale_execution_minutes, MENSAJE_INTERRUMPIDA, execution_id
    )
    for stale_id, stored_filename in stale:
        logger.warning(
            "[%s] Ejecución sin latido desde hace más de %d min: marcada como interrumpida",
            stale_id, settings.stale_execution_minutes,
        )
        delete_stored_upload(settings, stored_filename, "ejecución interrumpida")
    return len(stale)


def cleanup_orphan_uploads(repository: HandoverRepository, settings: Settings) -> list[str]:
    """Limpia data/input/ de archivos temporales que ya no hacen falta. Solo
    considera archivos con prefijo de upload_id (nunca los colocados a mano):
    se borran si su ejecución ya no está en "processing", o si no tienen
    ejecución y llevan más de ORPHAN_UPLOAD_MAX_AGE_HOURS sin procesarse.
    Devuelve los nombres borrados (cada uno queda en el log con su motivo).
    """
    if not settings.orphan_cleanup_enabled:
        return []
    base = settings.resolved_data_input_dir().resolve()
    candidates = [
        entry for entry in base.iterdir() if entry.is_file() and _UPLOAD_PREFIX.match(entry.name)
    ]
    statuses = repository.statuses_by_stored_filename([entry.name for entry in candidates])
    max_age_seconds = settings.orphan_upload_max_age_hours * 3600
    deleted: list[str] = []
    for entry in candidates:
        status = statuses.get(entry.name)
        if status == "processing":
            continue
        if status is not None:
            motivo = f"su ejecución ya terminó ({status})"
        elif time.time() - entry.stat().st_mtime > max_age_seconds:
            motivo = f"subido hace más de {settings.orphan_upload_max_age_hours} h y nunca procesado"
        else:
            continue
        if delete_stored_upload(settings, entry.name, motivo):
            deleted.append(entry.name)
    return deleted


def startup_maintenance(settings: Settings, session_factory: Callable[[], Session] = SessionLocal) -> None:
    """Al arrancar la app: ejecuciones interrumpidas -> "failed", y limpieza de
    archivos temporales. Nunca impide que la app arranque."""
    try:
        db = session_factory()
    except Exception:  # noqa: BLE001
        logger.exception("Mantenimiento de ingesta al arrancar: no se pudo abrir la base")
        return
    try:
        repository = HandoverRepository(db, settings.load_batch_rows)
        expire_stale_executions(repository, settings)
        cleanup_orphan_uploads(repository, settings)
    except Exception:  # noqa: BLE001
        logger.exception("Mantenimiento de ingesta al arrancar: falló (la app continúa)")
    finally:
        db.close()


_EXPORT_COLUMNS = [
    "id_registro",
    "execution_id",
    "timestamp_medicion",
    "cell_id",
    "tac",
    "earfcn",
    "tecnologia",
    "latitud",
    "longitud",
    "node_id",
    "psc_pci",
    "rssi",
    "rsrp",
    "rsrq",
    "rssnr",
    "accuracy",
    "cid",
    "lac_tac_raw",
    "report_index",
    "net_type",
    "tech",
    "data_state",
    "call_state",
    "velocidad_kmh",
    "archivo_origen",
    "hoja_origen",
    "origen_formato",
    "created_at",
]


def export_valid_records_csv(
    repository: HandoverRepository, execution_id: uuid.UUID | None = None
) -> str:
    """Exporta `handover_record` (nunca handover_record_rejected) a CSV.

    Sin `execution_id`, exporta el dataset completo (todas las ejecuciones).
    """
    records = repository.get_valid_records(execution_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EXPORT_COLUMNS)
    for record in records:
        writer.writerow([getattr(record, column) for column in _EXPORT_COLUMNS])

    return buffer.getvalue()
