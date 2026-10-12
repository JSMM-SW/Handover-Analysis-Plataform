-- =============================================================================
-- Migración 011 — Avance, latido y cancelación de ejecuciones (ingesta)
--
-- Requiere la migración 010. Solo toca etl_execution; no toca
-- eventos_handover ni tablas de otros módulos. Idempotente y transaccional.
--
-- 1. etapa / progreso: en qué etapa del pipeline va la ejecución y su avance
--    (0-100), para que GET /ingestion/status los muestre durante el polling.
-- 2. updated_at: latido. La carga lo actualiza periódicamente; si el servidor
--    se reinicia a mitad de un proceso, la ejecución deja de latir y se marca
--    como failed ("interrumpida") pasado un umbral, en vez de quedar en
--    processing para siempre bloqueando el nombre del archivo.
-- 3. cancel_requested: bandera de cancelación cooperativa. POST
--    /ingestion/cancel/{id} la enciende; el pipeline la revisa entre etapas y
--    entre lotes de COPY, hace rollback total y deja la ejecución cancelled.
-- 4. stored_filename: nombre del archivo temporal en data/input/ (lleva el
--    prefijo del upload_id), para poder borrarlo al cancelar/fallar/terminar.
-- 5. status admite 'cancelled'. El índice único parcial de la 010 no cambia:
--    cancelled, igual que failed, no bloquea el nombre del archivo.
--
-- etapa, progreso, updated_at y cancel_requested se escriben/leen desde una
-- conexión aparte en autocommit (no desde la transacción del Load), para que
-- /status los vea al instante. Verificado contra Supabase: ese UPDATE no se
-- bloquea con las filas que el Load tiene insertadas con FK a la ejecución
-- (el Load solo toma FOR KEY SHARE sobre la fila; un UPDATE de columnas no
-- clave toma FOR NO KEY UPDATE, que es compatible).
--
-- Compatibilidad: una versión anterior del backend sigue funcionando sobre
-- esta base (las columnas nuevas tienen DEFAULT o admiten NULL), pero NO
-- emite latidos: sus cargas largas podrían marcarse como interrumpidas por un
-- backend nuevo. Actualizar backend y frontend de todo el equipo a la vez.
-- =============================================================================

BEGIN;

LOCK TABLE etl_execution IN ACCESS EXCLUSIVE MODE;

ALTER TABLE etl_execution
    ADD COLUMN IF NOT EXISTS etapa            TEXT NULL,
    ADD COLUMN IF NOT EXISTS progreso         SMALLINT NULL
        CONSTRAINT chk_etl_execution_progreso CHECK (progreso BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS updated_at       TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS stored_filename  TEXT NULL;

-- Históricas: su último "latido" conocido es cuando se procesaron. Solo se
-- rellena la columna nueva (no cambia ningún dato existente ni el status).
UPDATE etl_execution SET updated_at = processing_date WHERE updated_at IS NULL;

ALTER TABLE etl_execution
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE etl_execution DROP CONSTRAINT IF EXISTS etl_execution_status_check;
ALTER TABLE etl_execution DROP CONSTRAINT IF EXISTS chk_status;
ALTER TABLE etl_execution ADD CONSTRAINT etl_execution_status_check
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled'));

COMMENT ON COLUMN etl_execution.etapa IS
    'Etapa actual del pipeline (subida, extract, validate, clean, normalize, load, verify, done). Informativa, para GET /ingestion/status.';
COMMENT ON COLUMN etl_execution.progreso IS
    'Avance estimado de la ejecución, 0-100. Informativo.';
COMMENT ON COLUMN etl_execution.updated_at IS
    'Latido: última señal de vida de la ejecución. En processing sin latido reciente = interrumpida (se marca failed).';
COMMENT ON COLUMN etl_execution.cancel_requested IS
    'Cancelación cooperativa solicitada por POST /ingestion/cancel/{id}; el pipeline la revisa entre etapas y lotes.';
COMMENT ON COLUMN etl_execution.stored_filename IS
    'Archivo temporal en data/input/ (con prefijo upload_id). Se borra al terminar, fallar o cancelar. NULL en históricas.';

-- Verificación: ninguna fila quedó fuera del nuevo CHECK ni sin latido.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM etl_execution WHERE updated_at IS NULL) THEN
        RAISE EXCEPTION 'Quedaron ejecuciones sin updated_at';
    END IF;
END $$;

COMMIT;
