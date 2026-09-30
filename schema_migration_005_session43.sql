-- =============================================================================
-- Migración 005 — Soporte para el export real de NetMonitor Lite
-- (Session_43_20260623_165825.csv, 86,398 filas, 45 columnas)
--
-- No destructiva: solo agrega columnas NULLABLE y amplía el CHECK de
-- tecnologia. La columna `rssi` queda DEPRECATED pero NO se borra ni se
-- migra (las filas csv ya existentes la conservan tal cual).
-- =============================================================================

BEGIN;

ALTER TABLE handover_record
    ADD COLUMN IF NOT EXISTS rscp_dbm     SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS rssi_dbm     SMALLINT NULL,
    ADD COLUMN IF NOT EXISTS cid          BIGINT NULL,
    ADD COLUMN IF NOT EXISTS lac_tac_raw  INTEGER NULL,
    ADD COLUMN IF NOT EXISTS report_index INTEGER NULL,
    ADD COLUMN IF NOT EXISTS net_type     TEXT NULL,
    ADD COLUMN IF NOT EXISTS tech         TEXT NULL,
    ADD COLUMN IF NOT EXISTS data_state   TEXT NULL,
    ADD COLUMN IF NOT EXISTS call_state   TEXT NULL;

-- Ampliar tecnologia a 4 valores (0=sin señal, 1=LTE/4G, 2=3G, 3=2G).
-- Igual que en la migración 002: hay que tumbar tanto el nombre explícito
-- como el autogenerado por si la instalación viene de antes de esa migración.
ALTER TABLE handover_record
    DROP CONSTRAINT IF EXISTS chk_tecnologia_valida,
    DROP CONSTRAINT IF EXISTS handover_record_tecnologia_check;
ALTER TABLE handover_record
    ADD CONSTRAINT chk_tecnologia_valida CHECK (tecnologia IN (0, 1, 2, 3));

COMMENT ON COLUMN handover_record.cell_id IS
    'Identificador de celda (xlsx: Cell ID/ECI; csv: cid). Un handover se detecta cuando este valor '
    'cambia entre registros consecutivos del mismo recorrido. ADVERTENCIA (origen csv, verificado con '
    'Session_43_20260623_165825.csv): en LTE este valor es el SECTOR LOCAL dentro del eNodeB '
    '(rango 70-210), NO una identidad de celda confiable — el mismo cid aparece bajo múltiples '
    'node_id (9 de 26 valores de cid observados). Para identidad de celda correcta, usar '
    '(tech, node_id, cid, lac_tac_raw) directamente, no este campo.';
COMMENT ON COLUMN handover_record.tecnologia IS
    '0 = sin señal (xlsx), 1 = LTE/4G, 2 = 3G (UMTS/HSPA/HSPA+), 3 = 2G (GSM/EDGE/GPRS). Para csv se '
    'deriva de net_type (más confiable que tech: net_type refleja el cambio real de tecnología antes '
    'que tech/cid durante una transición); para xlsx viene directo de la columna Tecnología.';
COMMENT ON COLUMN handover_record.rsrp_dbm IS
    'Reference Signal Received Power, en dBm. xlsx: columna RSRP directa, rango real -128 a -29 dBm. '
    'csv: proviene de `rssi` cuando tech=LTE (mediana real -104 dBm); NULL para WCDMA/GSM (ver '
    'rscp_dbm/rssi_dbm) y para xlsx si no aplica.';
COMMENT ON COLUMN handover_record.rssi IS
    'DEPRECATED desde Session_43_20260623_165825.csv: mezclaba RSRP/RSCP/RSSI según tech en una sola '
    'columna. Filas csv anteriores a esa corrección la tienen poblada (no se migran); filas nuevas '
    'ya no la usan, van a rsrp_dbm/rscp_dbm/rssi_dbm según tech. NULL para xlsx o centinela.';
COMMENT ON COLUMN handover_record.rscp_dbm IS
    'Received Signal Code Power, en dBm (csv: `rssi` cuando tech=WCDMA, mediana real -102 dBm). '
    'NULL para xlsx, para LTE/GSM, o centinela.';
COMMENT ON COLUMN handover_record.rssi_dbm IS
    'Received Signal Strength Indicator propiamente dicho, en dBm (csv: `rssi` cuando tech=GSM, '
    'mediana real -95 dBm). NULL para xlsx, para LTE/WCDMA, o centinela.';
COMMENT ON COLUMN handover_record.cid IS
    'Identificador crudo de celda tal como lo reporta el csv (Network Cell Info), sin reinterpretar. '
    'NULL para xlsx. Ver advertencia de identidad en el comentario de cell_id.';
COMMENT ON COLUMN handover_record.lac_tac_raw IS
    'Tracking/Location Area Code crudo del csv (mismo valor que `tac`, con el nombre que espera el '
    'contrato de datos del módulo de visualización temporal). NULL para xlsx.';
COMMENT ON COLUMN handover_record.report_index IS
    'Contador secuencial del equipo de medición (csv: `report`, verificado 0..n-1 sin huecos). '
    'Da un orden estable cuando timestamp_medicion por sí solo no alcanza (resolución de 1s, con '
    'timestamps duplicados reales). NULL para xlsx.';
COMMENT ON COLUMN handover_record.net_type IS
    'Tipo de servicio de red tal como lo reporta el csv (LTE, HSPA, HSPA+, EDGE, UMTS, GPRS, '
    'UNKNOWN). Fuente de verdad para `tecnologia`. NULL para xlsx.';
COMMENT ON COLUMN handover_record.tech IS
    'RAT (Radio Access Technology) tal como lo reporta el csv (LTE, WCDMA, GSM). Puede discrepar '
    'brevemente de net_type durante una transición real de tecnología (net_type es la fuente de '
    'verdad, no tech). NULL para xlsx.';
COMMENT ON COLUMN handover_record.data_state IS
    'Estado de conexión de datos del csv (DISCONNECTED, CONNECTED, CONNECTING). Aproxima si el '
    'terminal estaba en modo RRC connected (posible handover real) o idle (posible reselección). '
    'NULL para xlsx.';
COMMENT ON COLUMN handover_record.call_state IS
    'Estado de llamada del csv (IDLE, OFFHOOK). Contexto de llamada activa. NULL para xlsx.';

COMMIT;
