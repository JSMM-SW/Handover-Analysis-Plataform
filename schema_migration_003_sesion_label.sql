-- =============================================================================
-- Migración 003 — sesion_label en etl_execution
--
-- Columna autoincremental corta para uso humano (filtros de exportación,
-- referencias en UI) en vez del UUID largo de execution_id. Independiente
-- de cualquier otra tabla del proyecto: NO toca `eventos_handover` (módulo
-- de visualización temporal, fuera del alcance de este módulo) para nada.
-- =============================================================================

BEGIN;

ALTER TABLE etl_execution
    ADD COLUMN IF NOT EXISTS sesion_label INTEGER GENERATED ALWAYS AS IDENTITY UNIQUE;

COMMENT ON COLUMN etl_execution.sesion_label IS
    'Identificador corto autoincremental de la ejecución, para uso humano '
    '(filtros de exportación, referencias en UI) en vez del UUID largo de execution_id.';

COMMIT;
