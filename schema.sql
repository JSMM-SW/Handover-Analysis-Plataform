-- =============================================================================
-- Plataforma de Análisis y Visualización de Handovers
-- Módulo: Ingesta y Procesamiento de Datos de Handover (ETL)
-- Etapa: Load (Persistencia)
-- Motor: PostgreSQL 13+
--
-- Este script es la fuente de verdad del esquema para instalaciones nuevas.
-- Si ya tienes una base con datos, NO reejecutes este CREATE TABLE — usa los
-- scripts de migración incremental en orden:
--   schema_migration_002_csv_support.sql
--   schema_migration_003_sesion_label.sql
--
-- NOTA DE ALCANCE: este archivo describe únicamente las tablas del módulo de
-- ingesta (etl_execution, handover_record, handover_record_rejected). La
-- tabla `eventos_handover` pertenece al módulo de visualización temporal
-- (otro componente del TIC) y no se documenta ni se modifica aquí.
--
-- Origen 1, xlsx (Datos_Tesis.xlsx, 3 hojas, 495 registros). Las reglas de
-- CHECK reflejan hallazgos reales del dataset, no supuestos:
--   - Cell ID/ECI = 0 y RSRP = 99 aparecen juntos en 23 filas (marcador de
--     desconexión / error del equipo de medición).
--   - Esas mismas filas traen Latitud = 0 y Longitud = 0 (GPS sin fix).
--   - PCI/PSC, Column10 y Column12 son prácticamente nulas (valor "-") en
--     todo el dataset -> se descartan, no se persisten.
--
-- Origen 2, csv (Network Cell Info, dataset_unificado.csv, 11,954 registros,
-- alimenta al módulo de visualización geoespacial). Columnas nuevas todas
-- NULLABLE porque solo existen para este origen. Hallazgos reales:
--   - El centinela 2147483647 (INT32_MAX) significa "sin dato" en cid,
--     node_id, psc_pci, rssi, rsrq, rssnr, arfcn, lac_tac. En cid implica
--     rechazo (equivalente a Cell ID/ECI=0 del xlsx); en el resto, el campo
--     se guarda NULL (rssnr trae este centinela en 92% de las filas reales).
--   - GPS sin fix se marca con gps=0 y lat=long=-1 (siempre coinciden en los
--     11,954 registros reales), distinto del (0,0) del xlsx.
--   - tech y net_type pueden discrepar brevemente durante una transición real
--     de tecnología (net_type cambia primero, tech y cid van ~1-8s detrás);
--     net_type es la fuente de verdad para `tecnologia`.
-- =============================================================================

-- gen_random_uuid() es nativo desde PostgreSQL 13. En versiones anteriores,
-- descomentar la siguiente línea:
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. TRAZABILIDAD DE EJECUCIONES (Objetivo 5 del plan de tesis)
--    Cada carga de un Excel genera una fila aquí. Permite responder:
--    "¿qué archivo produjo este dataset y qué pasó durante el procesamiento?"
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_execution (
    execution_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sesion_label             INTEGER GENERATED ALWAYS AS IDENTITY UNIQUE,
    filename                 TEXT NOT NULL,
    processing_date          TIMESTAMPTZ NOT NULL DEFAULT now(),
    records_read             INTEGER NOT NULL DEFAULT 0 CHECK (records_read >= 0),
    records_valid            INTEGER NOT NULL DEFAULT 0 CHECK (records_valid >= 0),
    records_rejected         INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    warnings                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    processing_time_seconds  NUMERIC(10,3),
    status                   TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE etl_execution IS
    'Registro de trazabilidad de cada corrida del pipeline ETL (Objetivo 5: '
    'verificar consistencia, calidad y trazabilidad del procesamiento).';
COMMENT ON COLUMN etl_execution.sesion_label IS
    'Identificador corto autoincremental de la ejecución, para uso humano '
    '(filtros de exportación, referencias en UI) en vez del UUID largo de execution_id.';
COMMENT ON COLUMN etl_execution.warnings IS
    'Lista de advertencias no bloqueantes (ej. valores atípicos, nulos) generadas durante el procesamiento.';
COMMENT ON COLUMN etl_execution.errors IS
    'Lista de errores bloqueantes (ej. columnas faltantes, archivo corrupto).';

-- -----------------------------------------------------------------------------
-- 2. DATASET FINAL LIMPIO (Target Schema — consumido por los módulos de
--    visualización temporal, geoespacial y KPIs)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS handover_record (
    id_registro       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id       UUID NOT NULL REFERENCES etl_execution(execution_id) ON DELETE CASCADE,

    -- Fecha + Hora del Excel vienen en hora local America/Guayaquil (UTC-5, sin DST).
    -- El ETL debe convertir a UTC antes de insertar; se guarda con zona horaria
    -- para no perder esa conversión ni depender del TimeZone de la sesión de PostgreSQL.
    timestamp_medicion TIMESTAMPTZ NOT NULL,

    cell_id            INTEGER NOT NULL CHECK (cell_id > 0),   -- excluye el marcador de desconexión (0)

    -- NULL solo posible en origen csv, cuando el equipo reporta el centinela
    -- 2147483647 en lac_tac/arfcn (el registro no se rechaza por esto).
    tac                INTEGER NULL,
    earfcn             INTEGER NULL,

    tecnologia         SMALLINT NOT NULL CHECK (tecnologia IN (0, 1, 2)),  -- 0 = sin señal, 1 = LTE/4G, 2 = 3G/UMTS

    latitud             NUMERIC(10,6) NOT NULL CHECK (latitud BETWEEN -5 AND 2),
    longitud            NUMERIC(10,6) NOT NULL CHECK (longitud BETWEEN -92 AND -75),

    -- Rango físicamente posible de RSRP en LTE: -140 a -1 dBm. Esto excluye el
    -- marcador de error del equipo de medición (99) pero permite señales
    -- inusualmente fuertes como -29 (el ETL debe marcarlas como warning, no rechazarlas).
    -- NULL solo posible en origen csv (Network Cell Info no reporta RSRP,
    -- usa rssi/rsrq/rssnr en su lugar). El CHECK se satisface automáticamente
    -- cuando el valor es NULL (semántica de 3 valores de SQL).
    rsrp_dbm            SMALLINT NULL CHECK (rsrp_dbm BETWEEN -140 AND -1),

    -- Columnas exclusivas del origen csv (Network Cell Info). NULL para xlsx,
    -- y NULL también cuando el equipo reporta el centinela 2147483647.
    node_id             INTEGER NULL,
    psc_pci             INTEGER NULL,
    rssi                SMALLINT NULL,
    rsrq                SMALLINT NULL,
    rssnr               SMALLINT NULL,
    accuracy            SMALLINT NULL,

    archivo_origen      TEXT NOT NULL,
    hoja_origen         TEXT NULL,                   -- 'Datos 1'/'Datos 2'/'Datos 3' (xlsx); NULL en csv, que no tiene hojas
    origen_formato      TEXT NOT NULL CHECK (origen_formato IN ('xlsx', 'csv')),

    -- Distancia Haversine / tiempo contra el registro anterior de la misma
    -- sesión (misma hoja_origen). NULL si es el primero de su sesión, si el
    -- registro actual o el anterior fueron rechazados por GPS sin fix, o si
    -- la diferencia de tiempo es 0. Valores > 200 km/h se conservan con un
    -- warning en vez de rechazarse (podría ser ruido de GPS, no se fuerza).
    velocidad_kmh       NUMERIC(6,2) NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Un registro con GPS (0,0) [xlsx] o lat=long=-1 [csv] es "sin fix", no
    -- una coordenada real en Ecuador.
    CONSTRAINT chk_gps_con_fix CHECK (NOT (latitud = 0 AND longitud = 0) AND NOT (latitud = -1 AND longitud = -1))
);

COMMENT ON TABLE handover_record IS
    'Dataset estructurado, validado y normalizado, listo para ser consumido '
    'por los módulos de visualización temporal, geoespacial y KPIs.';
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
COMMENT ON COLUMN handover_record.rsrp_dbm IS
    'Reference Signal Received Power, en dBm. Rango real observado en el dataset xlsx: -128 a -29 dBm.';
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
COMMENT ON COLUMN handover_record.velocidad_kmh IS
    'Velocidad estimada (Haversine / tiempo) contra el registro anterior de la misma sesión '
    '(misma hoja_origen). NULL si es el primero de su sesión, si el registro actual o el '
    'anterior fueron rechazados por GPS sin fix, o si la diferencia de tiempo es 0. Valores '
    '> 200 km/h se conservan (con warning en la ejecución), no se rechazan ni se fuerzan a NULL.';

-- -----------------------------------------------------------------------------
-- 3. CUARENTENA DE REGISTROS RECHAZADOS
--    Guarda la fila cruda + el motivo, para que la tesis pueda documentar
--    calidad de datos (sección 13) sin perder trazabilidad de lo descartado.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS handover_record_rejected (
    id_rechazo          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES etl_execution(execution_id) ON DELETE CASCADE,
    hoja_origen         TEXT,                         -- nombre de hoja (xlsx) o NULL (csv, no aplica)
    fila_excel          INTEGER,                      -- número de fila en el archivo origen (Excel o CSV), si se conoce
    motivo_rechazo      TEXT NOT NULL,                -- ej. 'cell_id = 0', 'rsrp = 99', 'gps sin fix', 'registro duplicado'
    datos_crudos        JSONB NOT NULL,               -- fila completa tal como vino del archivo origen
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE handover_record_rejected IS
    'Registros descartados durante Validate/Clean, con el motivo y los datos '
    'crudos originales, para auditoría de calidad del dataset.';

-- -----------------------------------------------------------------------------
-- 4. ÍNDICES
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_handover_record_execution_id
    ON handover_record (execution_id);

CREATE INDEX IF NOT EXISTS idx_handover_record_cell_id
    ON handover_record (cell_id);

CREATE INDEX IF NOT EXISTS idx_handover_record_timestamp
    ON handover_record (timestamp_medicion);

CREATE INDEX IF NOT EXISTS idx_handover_record_geo
    ON handover_record (latitud, longitud);

CREATE INDEX IF NOT EXISTS idx_handover_record_origen_formato
    ON handover_record (origen_formato);

CREATE INDEX IF NOT EXISTS idx_handover_rejected_execution_id
    ON handover_record_rejected (execution_id);

COMMIT;
