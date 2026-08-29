-- =============================================================================
-- Plataforma de Análisis y Visualización de Handovers
-- Módulo: Ingesta y Procesamiento de Datos de Handover (ETL)
-- Etapa: Load (Persistencia)
-- Motor: PostgreSQL 13+
--
-- Este script implementa el "Target Schema" definido en la etapa de análisis
-- del archivo real (Datos_Tesis.xlsx, 3 hojas, 495 registros). Las reglas de
-- CHECK reflejan hallazgos reales del dataset, no supuestos:
--   - Cell ID/ECI = 0 y RSRP = 99 aparecen juntos en 23 filas (marcador de
--     desconexión / error del equipo de medición).
--   - Esas mismas filas traen Latitud = 0 y Longitud = 0 (GPS sin fix).
--   - PCI/PSC, Column10 y Column12 son prácticamente nulas (valor "-") en
--     todo el dataset -> se descartan, no se persisten.
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
    tac                INTEGER NOT NULL,
    earfcn             INTEGER NOT NULL,
    tecnologia         SMALLINT NOT NULL CHECK (tecnologia IN (0, 1)),  -- 0 = sin señal, 1 = LTE/4G

    latitud             NUMERIC(10,6) NOT NULL CHECK (latitud BETWEEN -5 AND 2),
    longitud            NUMERIC(10,6) NOT NULL CHECK (longitud BETWEEN -92 AND -75),

    -- Rango físicamente posible de RSRP en LTE: -140 a -1 dBm. Esto excluye el
    -- marcador de error del equipo de medición (99) pero permite señales
    -- inusualmente fuertes como -29 (el ETL debe marcarlas como warning, no rechazarlas).
    rsrp_dbm            SMALLINT NOT NULL CHECK (rsrp_dbm BETWEEN -140 AND -1),

    archivo_origen      TEXT NOT NULL,
    hoja_origen         TEXT NOT NULL,               -- 'Datos 1' / 'Datos 2' / 'Datos 3'

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Un registro con GPS (0,0) es "sin fix", no una coordenada real en Ecuador.
    CONSTRAINT chk_gps_con_fix CHECK (NOT (latitud = 0 AND longitud = 0))
);

COMMENT ON TABLE handover_record IS
    'Dataset estructurado, validado y normalizado, listo para ser consumido '
    'por los módulos de visualización temporal, geoespacial y KPIs.';
COMMENT ON COLUMN handover_record.cell_id IS
    'Identificador de celda (Cell ID/ECI). Un handover se detecta cuando este valor '
    'cambia entre registros consecutivos del mismo recorrido.';
COMMENT ON COLUMN handover_record.rsrp_dbm IS
    'Reference Signal Received Power, en dBm. Rango real observado en el dataset: -128 a -29 dBm.';
COMMENT ON COLUMN handover_record.timestamp_medicion IS
    'Timestamp de la medición en UTC. Origen: Fecha+Hora del Excel en hora local America/Guayaquil (UTC-5), convertida por el ETL.';

-- -----------------------------------------------------------------------------
-- 3. CUARENTENA DE REGISTROS RECHAZADOS
--    Guarda la fila cruda + el motivo, para que la tesis pueda documentar
--    calidad de datos (sección 13) sin perder trazabilidad de lo descartado.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS handover_record_rejected (
    id_rechazo          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES etl_execution(execution_id) ON DELETE CASCADE,
    hoja_origen         TEXT,
    fila_excel          INTEGER,                     -- número de fila original en el Excel, si se conoce
    motivo_rechazo      TEXT NOT NULL,                -- ej. 'cell_id = 0', 'rsrp = 99', 'gps sin fix', 'duplicado'
    datos_crudos        JSONB NOT NULL,               -- fila completa tal como vino del Excel
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

CREATE INDEX IF NOT EXISTS idx_handover_rejected_execution_id
    ON handover_record_rejected (execution_id);

COMMIT;
