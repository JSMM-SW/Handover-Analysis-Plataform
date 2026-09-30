-- =============================================================================
-- Migración 006 — GPS sin fix (csv) deja de rechazar el registro
--
-- Confirmado con Session_43_20260623_165825.csv (86,398 filas reales): solo
-- el 8.0% trae fix de GPS, así que rechazar por "gps sin fix" tiraba el 92%
-- del archivo — contradice R3 del módulo de visualización temporal (no usa
-- coordenadas) y el propósito de la ingesta. Desde ahora, esos registros
-- csv se conservan (cid/tech/rsrp/timestamp intactos) con latitud/longitud
-- en NULL en vez de rechazarse por completo.
--
-- No destructiva: solo relaja NOT NULL en dos columnas ya existentes. Los
-- CHECK de rango y `chk_gps_con_fix` no cambian — un valor NULL los
-- satisface automáticamente (semántica de 3 valores de SQL). El
-- comportamiento de xlsx (sigue rechazando GPS sin fix) no cambia.
-- =============================================================================

BEGIN;

ALTER TABLE handover_record
    ALTER COLUMN latitud DROP NOT NULL,
    ALTER COLUMN longitud DROP NOT NULL;

COMMENT ON COLUMN handover_record.latitud IS
    'NULL solo posible en origen csv, cuando gps sin fix (centinela lat/long = -1) '
    'ya no rechaza el registro completo (confirmado necesario con '
    'Session_43_20260623_165825.csv: 92% del archivo no trae fix de GPS). '
    'Siempre poblado para xlsx, que sigue rechazando GPS sin fix sin cambios.';
COMMENT ON COLUMN handover_record.longitud IS
    'Ver comentario de latitud: misma regla de NULL para csv con gps sin fix.';

COMMIT;
