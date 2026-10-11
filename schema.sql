-- CSV ingestion schema. Existing installations: use migration 007 with a backup.

BEGIN;
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

CREATE TABLE IF NOT EXISTS handover_record (
    id_registro       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id       UUID NOT NULL REFERENCES etl_execution(execution_id) ON DELETE CASCADE,
    timestamp_medicion TIMESTAMPTZ NOT NULL,

    cell_id            INTEGER NOT NULL CHECK (cell_id > 0),   -- excluye el marcador de desconexión (0)
    tac                INTEGER NULL,
    earfcn             INTEGER NULL,

    tecnologia         SMALLINT NOT NULL CHECK (tecnologia IN (0, 1, 2, 3)),  -- 0=sin señal, 1=LTE/4G, 2=3G, 3=2G (GSM/EDGE/GPRS)
    latitud             NUMERIC(10,6) NULL CHECK (latitud BETWEEN -5 AND 2),
    longitud            NUMERIC(10,6) NULL CHECK (longitud BETWEEN -92 AND -75),
    node_id             INTEGER NULL,
    psc_pci             INTEGER NULL,
    rssi                SMALLINT NULL,
    rsrp               SMALLINT NULL,
    rsrq                SMALLINT NULL,
    rssnr               SMALLINT NULL,
    accuracy            SMALLINT NULL,
    cid                 BIGINT NULL,
    lac_tac_raw         INTEGER NULL,
    report_index        INTEGER NULL,
    net_type            TEXT NULL,   -- LTE, HSPA, HSPA+, EDGE, UMTS, GPRS, UNKNOWN
    tech                TEXT NULL,   -- LTE, WCDMA, GSM (RAT real; fuente de verdad es net_type, no tech)
    data_state          TEXT NULL,   -- DISCONNECTED, CONNECTED, CONNECTING
    call_state          TEXT NULL,   -- IDLE, OFFHOOK

    archivo_origen      TEXT NOT NULL,
    hoja_origen         TEXT NULL,                   -- 'Datos 1'/'Datos 2'/'Datos 3' (xlsx); NULL en csv, que no tiene hojas
    origen_formato      TEXT NOT NULL CHECK (origen_formato = 'csv'),
    velocidad_kmh       NUMERIC(6,2) NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_gps_con_fix CHECK (NOT (latitud = 0 AND longitud = 0) AND NOT (latitud = -1 AND longitud = -1))
);

CREATE TABLE IF NOT EXISTS handover_record_rejected (
    id_rechazo          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES etl_execution(execution_id) ON DELETE CASCADE,
    hoja_origen         TEXT,                         -- nombre de hoja (xlsx) o NULL (csv, no aplica)
    fila_excel          INTEGER,                      -- número de fila en el archivo origen (Excel o CSV), si se conoce
    motivo_rechazo      TEXT NOT NULL,                -- ej. 'cell_id = 0', 'rsrp = 99', 'gps sin fix', 'registro duplicado'
    datos_crudos        JSONB NOT NULL,               -- fila completa tal como vino del archivo origen
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

COMMENT ON COLUMN handover_record.rsrp IS 'RSRP from NetMonitor rssi_strongest, per user verification of this app; original dBm value.';

-- Historial de reportes KPI exportados a PDF (HU-010, Paso 13 del plan de refactor).
CREATE TABLE IF NOT EXISTS kpi_reporte_historial (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha_generacion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    nombre_archivo        TEXT NOT NULL,                 -- nombre del PDF generado

    -- Filtros aplicados al exportar. Arreglo vacío = "todas/todos".
    fecha_inicio          DATE NOT NULL,
    fecha_fin             DATE NOT NULL,
    tecnologia            SMALLINT[] NOT NULL DEFAULT '{}',   -- {1,2,3} = LTE, 3G, 2G
    franja                TEXT[]     NOT NULL DEFAULT '{}',   -- {'manana','tarde','noche'}
    sesion_execution_id   UUID[]     NOT NULL DEFAULT '{}',   -- identificador estable de cada sesión
    sesion_label          INTEGER[]  NOT NULL DEFAULT '{}',   -- solo para mostrar "Sesión N"
    periodicidad          TEXT NOT NULL,
    periodo_seleccionado  TEXT NULL,                          -- clave de /kpis/trend si había uno (Paso 10)

    -- Copia de lo que mostraba el reporte y del criterio con que se calculó.
    resultados            JSONB NOT NULL,   -- tarjetas, panel de resumen y tabla por período
    parametros_calculo    JSONB NOT NULL,   -- ej. {"hueco_maximo_s":10,"ping_pong_ventana_s":60,
                                            --      "uho_rssi_min_dbm":-100,"uho_rsrq_min_db":-15}

    CONSTRAINT chk_kpi_reporte_rango_fechas
        CHECK (fecha_fin >= fecha_inicio),
    CONSTRAINT chk_kpi_reporte_periodicidad
        CHECK (periodicidad IN ('diario', 'semanal', 'mensual', 'anual')),
    CONSTRAINT chk_kpi_reporte_tecnologia
        CHECK (tecnologia <@ ARRAY[1, 2, 3]::SMALLINT[]),
    CONSTRAINT chk_kpi_reporte_franja
        CHECK (franja <@ ARRAY['manana', 'tarde', 'noche']::TEXT[])
);

CREATE INDEX IF NOT EXISTS idx_kpi_reporte_historial_fecha_generacion
    ON kpi_reporte_historial (fecha_generacion DESC);

COMMIT;

