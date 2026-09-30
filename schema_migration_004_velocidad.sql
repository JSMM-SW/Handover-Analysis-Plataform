-- =============================================================================
-- Migración 004 — velocidad_kmh en handover_record
--
-- Columna calculada (Haversine / tiempo contra el registro anterior de la
-- misma sesión). No destructiva: solo agrega una columna NULLABLE.
-- =============================================================================

BEGIN;

ALTER TABLE handover_record
    ADD COLUMN IF NOT EXISTS velocidad_kmh NUMERIC(6,2) NULL;

COMMENT ON COLUMN handover_record.velocidad_kmh IS
    'Velocidad estimada (Haversine / tiempo) contra el registro anterior de la misma sesión '
    '(misma hoja_origen). NULL si es el primero de su sesión, si el registro actual o el '
    'anterior fueron rechazados por GPS sin fix, o si la diferencia de tiempo es 0. Valores '
    '> 200 km/h se conservan (con warning en la ejecución), no se rechazan ni se fuerzan a NULL.';

COMMIT;
