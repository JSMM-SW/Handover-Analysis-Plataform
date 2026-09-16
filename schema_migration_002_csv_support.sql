-- =============================================================================
-- Migración 002 — Soporte para archivos CSV (Network Cell Info)
--
-- Ejecutar UNA vez contra la base ya existente (tiene datos reales del
-- origen xlsx). No destructiva: solo agrega columnas NULLABLE, relaja dos
-- NOT NULL y amplía un CHECK. schema.sql ya quedó actualizado como fuente
-- de verdad para instalaciones nuevas; este archivo es el ALTER TABLE
-- incremental para no perder los datos existentes.
-- =============================================================================

BEGIN;

-- 1. Relajar tac/earfcn a NULLABLE (csv puede reportar el centinela
--    2147483647 en lac_tac/arfcn sin que el registro deba rechazarse).
--    rsrp_dbm también se relaja: el csv no tiene un campo equivalente a RSRP
--    (usa rssi/rsrq/rssnr en su lugar). El CHECK existente ya es compatible
--    con NULL sin cambios (semántica de 3 valores de SQL).
ALTER TABLE handover_record
    ALTER COLUMN tac DROP NOT NULL,
    ALTER COLUMN earfcn DROP NOT NULL,
    ALTER COLUMN rsrp_dbm DROP NOT NULL;

-- 2. Relajar hoja_origen a NULLABLE (csv no tiene el concepto de hojas).
ALTER TABLE handover_record
    ALTER COLUMN hoja_origen DROP NOT NULL;

-- 3. Columnas nuevas exclusivas del origen csv.
ALTER TABLE handover_record
    ADD COLUMN IF NOT EXISTS node_id  INTEGER  NULL,
    ADD COLUMN IF NOT EXISTS psc_pci  INTEGER  NULL,
    ADD COLUMN IF NOT EXISTS rssi     SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS rsrq     SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS rssnr    SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS accuracy SMALLINT NULL;

-- 4. origen_formato: se agrega con DEFAULT 'xlsx' para poblar retroactivamente
--    las filas existentes (todas vinieron de Excel), luego se quita el
--    DEFAULT para que toda fila nueva deba indicarlo explícitamente.
ALTER TABLE handover_record
    ADD COLUMN IF NOT EXISTS origen_formato TEXT NOT NULL DEFAULT 'xlsx';

ALTER TABLE handover_record
    ALTER COLUMN origen_formato DROP DEFAULT;

ALTER TABLE handover_record
    ADD CONSTRAINT chk_origen_formato_valido CHECK (origen_formato IN ('xlsx', 'csv'));

-- 5. Ampliar tecnologia a 3 valores (0=sin señal, 1=LTE/4G, 2=3G/UMTS).
--    El CHECK original de schema.sql v1 era una restricción de columna sin
--    nombre explícito, así que Postgres la nombró automáticamente
--    'handover_record_tecnologia_check' (no 'chk_tecnologia_valida'). Hay
--    que tumbar ambos nombres posibles o queda un CHECK viejo (0,1) activo
--    en paralelo al nuevo, bloqueando cualquier inserción con tecnologia=2.
ALTER TABLE handover_record
    DROP CONSTRAINT IF EXISTS chk_tecnologia_valida,
    DROP CONSTRAINT IF EXISTS handover_record_tecnologia_check;
ALTER TABLE handover_record
    ADD CONSTRAINT chk_tecnologia_valida CHECK (tecnologia IN (0, 1, 2));

-- 6. El centinela de GPS del csv es lat=long=-1 (distinto del (0,0) del
--    xlsx); ambos deben seguir bloqueados por el mismo CHECK.
ALTER TABLE handover_record
    DROP CONSTRAINT IF EXISTS chk_gps_con_fix;
ALTER TABLE handover_record
    ADD CONSTRAINT chk_gps_con_fix
        CHECK (NOT (latitud = 0 AND longitud = 0) AND NOT (latitud = -1 AND longitud = -1));

-- 7. Índice para filtrar/agrupar por origen.
CREATE INDEX IF NOT EXISTS idx_handover_record_origen_formato
    ON handover_record (origen_formato);

-- 8. Comentarios actualizados (ver schema.sql para el texto completo y
--    definitivo; se repiten aquí para que la base ya migrada quede
--    documentada igual que una instalación nueva).
COMMENT ON COLUMN handover_record.cell_id IS
    'Identificador de celda (xlsx: Cell ID/ECI; csv: cid). Un handover se detecta cuando este valor '
    'cambia entre registros consecutivos del mismo recorrido.';
COMMENT ON COLUMN handover_record.tac IS
    'Tracking/Location Area Code (xlsx: TAC/LAC; csv: lac_tac). NULL cuando el csv reporta '
    'el centinela 2147483647 (sin dato); siempre poblado para xlsx.';
COMMENT ON COLUMN handover_record.earfcn IS
    'E-UTRA Absolute Radio Frequency Channel Number (xlsx: EARFCN; csv: arfcn). NULL cuando el '
    'csv reporta el centinela 2147483647 (sin dato); siempre poblado para xlsx.';
COMMENT ON COLUMN handover_record.tecnologia IS
    '0 = sin señal (xlsx), 1 = LTE/4G, 2 = 3G/UMTS (HSPA+/UMTS). Para csv se deriva de '
    'net_type (más confiable que tech: net_type refleja el cambio real de tecnología antes '
    'que tech/cid durante una transición); para xlsx viene directo de la columna Tecnología.';
COMMENT ON COLUMN handover_record.node_id IS
    'Identificador del nodo de red servidor (csv: node_id). NULL para xlsx o cuando el csv '
    'reporta el centinela 2147483647.';
COMMENT ON COLUMN handover_record.psc_pci IS
    'Physical Cell Identity / PSC (csv: psc_pci). NULL para xlsx o cuando el csv reporta el '
    'centinela 2147483647.';
COMMENT ON COLUMN handover_record.rssi IS
    'Received Signal Strength Indicator en dBm (csv: rssi). NULL para xlsx o centinela.';
COMMENT ON COLUMN handover_record.rsrq IS
    'Reference Signal Received Quality en dB (csv: rsrq). NULL para xlsx, para tecnologías '
    'no-LTE, o cuando el csv reporta el centinela 2147483647.';
COMMENT ON COLUMN handover_record.rssnr IS
    'Relación señal de referencia / ruido (csv: rssnr). NULL para xlsx o centinela — en el '
    'dataset real de csv, el 92% de las filas trae este centinela.';
COMMENT ON COLUMN handover_record.accuracy IS
    'Precisión GPS estimada en metros (csv: accuracy). NULL para xlsx o cuando accuracy=-1 '
    '(desconocida para el equipo de medición).';
COMMENT ON COLUMN handover_record.hoja_origen IS
    'Nombre de la hoja del Excel de origen (ej. ''Datos 1''). NULL para origen csv, que no '
    'tiene el concepto de hojas.';
COMMENT ON COLUMN handover_record.origen_formato IS
    'Formato del archivo que produjo el registro: ''xlsx'' o ''csv''. Indica a los módulos '
    'consumidores qué columnas esperar pobladas (ej. rsrp_dbm solo en xlsx; rssi/rsrq/rssnr solo en csv).';
COMMENT ON COLUMN handover_record.timestamp_medicion IS
    'Timestamp de la medición en UTC. Origen: xlsx combina Fecha+Hora; csv parsea sys_time '
    '(AAAAMMDDHHMMSS). Ambos en hora local America/Guayaquil (UTC-5, sin DST), convertida por el ETL.';

COMMIT;
