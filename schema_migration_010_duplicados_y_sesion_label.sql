-- =============================================================================
-- Migración 010 — Archivos duplicados y sesion_label sin huecos (ingesta)
--
-- Prerrequisitos (ejecutados aparte, con confirmación del equipo):
--   * Sin dos ejecuciones processing/completed con el mismo nombre de archivo
--     normalizado (si existen, el CREATE UNIQUE INDEX de abajo falla y toda
--     la migración se revierte).
--
-- 1. sesion_label deja de ser IDENTITY. Una IDENTITY/SEQUENCE no se revierte
--    con el rollback: cada prueba, fallo o cancelación consumía un número.
--    Ahora el número se asigna al pasar la ejecución a 'completed', dentro de
--    la misma transacción del Load, desde una fila contador bloqueada
--    (UPDATE ... RETURNING toma el lock de fila hasta el commit):
--      - rollback, fallo o cancelación no consumen número;
--      - dos cargas simultáneas se serializan en esa fila: no repiten número;
--      - siguiente número = GREATEST(contador, MAX(sesion_label)) + 1.
--    Lo hace un trigger, no la aplicación, para que también funcione si algún
--    integrante corre una versión anterior del backend.
--    sesion_label queda NULL mientras la ejecución está processing/failed.
--    No se renumera ninguna sesión histórica.
-- 2. filename_clave: nombre original sin ruta, trim y minúsculas, calculado
--    por Postgres (columna generada). Índice único parcial: no puede haber
--    dos ejecuciones processing/completed con la misma clave (refuerzo contra
--    subidas simultáneas; failed no bloquea el nombre).
--
-- No toca eventos_handover ni tablas de otros módulos. Idempotente.
-- =============================================================================

BEGIN;

LOCK TABLE etl_execution IN ACCESS EXCLUSIVE MODE;

-- 1. sesion_label: de IDENTITY a contador asignado al completar ---------------

ALTER TABLE etl_execution ALTER COLUMN sesion_label DROP IDENTITY IF EXISTS;
ALTER TABLE etl_execution ALTER COLUMN sesion_label DROP NOT NULL;
-- La restricción UNIQUE (etl_execution_sesion_label_key) se conserva.

CREATE TABLE IF NOT EXISTS etl_sesion_contador (
    id      SMALLINT PRIMARY KEY CONSTRAINT chk_etl_sesion_contador_unica CHECK (id = 1),
    ultimo  INTEGER NOT NULL CONSTRAINT chk_etl_sesion_contador_ultimo CHECK (ultimo >= 0)
);

-- Se inicializa con el MAX(sesion_label) real (167 al preparar esta migración),
-- no con el último valor de la IDENTITY (203, inflado por pruebas y fallos).
INSERT INTO etl_sesion_contador (id, ultimo)
SELECT 1, COALESCE(MAX(sesion_label), 0) FROM etl_execution
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION etl_asignar_sesion_label() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'completed' AND NEW.sesion_label IS NULL THEN
        UPDATE etl_sesion_contador
           SET ultimo = GREATEST(ultimo, (SELECT COALESCE(MAX(sesion_label), 0) FROM etl_execution)) + 1
         WHERE id = 1
        RETURNING ultimo INTO NEW.sesion_label;
        IF NEW.sesion_label IS NULL THEN
            RAISE EXCEPTION 'etl_sesion_contador no está inicializado (falta la fila id = 1)';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_etl_execution_sesion_label ON etl_execution;
CREATE TRIGGER trg_etl_execution_sesion_label
    BEFORE INSERT OR UPDATE OF status ON etl_execution
    FOR EACH ROW EXECUTE FUNCTION etl_asignar_sesion_label();

COMMENT ON COLUMN etl_execution.sesion_label IS
    'Número de sesión para uso humano. NULL hasta que la ejecución queda completed; '
    'lo asigna trg_etl_execution_sesion_label desde etl_sesion_contador al confirmar la carga.';

-- 2. filename_clave + índice único parcial -----------------------------------

ALTER TABLE etl_execution
    ADD COLUMN IF NOT EXISTS filename_clave TEXT
    GENERATED ALWAYS AS (lower(btrim(regexp_replace(filename, '^.*[\\/]', '')))) STORED;

CREATE UNIQUE INDEX IF NOT EXISTS ux_etl_execution_filename_activo
    ON etl_execution (filename_clave)
    WHERE status IN ('processing', 'completed');

COMMENT ON COLUMN etl_execution.filename_clave IS
    'Nombre original del archivo sin ruta, trim y minúsculas. Clave de duplicados: '
    'ux_etl_execution_filename_activo impide dos ejecuciones processing/completed con la misma clave.';

-- Verificación: el contador quedó en el máximo real.
DO $$
BEGIN
    IF (SELECT ultimo FROM etl_sesion_contador WHERE id = 1)
       <> (SELECT COALESCE(MAX(sesion_label), 0) FROM etl_execution) THEN
        RAISE EXCEPTION 'etl_sesion_contador no coincide con MAX(sesion_label)';
    END IF;
END $$;

COMMIT;
