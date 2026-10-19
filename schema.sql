-- CSV ingestion schema. Existing installations: use migration 007 with a backup.

BEGIN;
CREATE TABLE IF NOT EXISTS etl_execution (
    execution_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sesion_label             INTEGER NULL UNIQUE,      -- NULL hasta 'completed'; lo asigna trg_etl_execution_sesion_label (migración 010)
    filename                 TEXT NOT NULL,
    filename_clave           TEXT GENERATED ALWAYS AS (lower(btrim(regexp_replace(filename, '^.*[\\/]', '')))) STORED,
    processing_date          TIMESTAMPTZ NOT NULL DEFAULT now(),
    records_read             INTEGER NOT NULL DEFAULT 0 CHECK (records_read >= 0),
    records_valid            INTEGER NOT NULL DEFAULT 0 CHECK (records_valid >= 0),
    records_rejected         INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    warnings                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    processing_time_seconds  NUMERIC(10,3),
    status                   TEXT NOT NULL DEFAULT 'pending'
                              CONSTRAINT etl_execution_status_check
                              CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Migración 011: avance, latido y cancelación. etapa/progreso/updated_at/
    -- cancel_requested se escriben y leen desde una conexión aparte en
    -- autocommit (no desde la transacción del Load).
    etapa                    TEXT NULL,                -- subida, extract, validate, clean, normalize, load, verify, done
    progreso                 SMALLINT NULL CONSTRAINT chk_etl_execution_progreso CHECK (progreso BETWEEN 0 AND 100),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),   -- latido; processing sin latido reciente = interrumpida
    cancel_requested         BOOLEAN NOT NULL DEFAULT false,       -- cancelación cooperativa (POST /ingestion/cancel/{id})
    stored_filename          TEXT NULL                 -- temporal en data/input/ (prefijo upload_id); se borra al terminar
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
    tech                TEXT NULL,   -- LTE, WCDMA, GSM (RAT de la celda medida; fuente de `tecnologia` en cargas nuevas, ver etl/tecnologia.py)
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

-- Número de sesión sin huecos (migración 010): se asigna al pasar a 'completed',
-- dentro de la transacción del Load, desde esta fila bloqueada. Un rollback,
-- fallo o cancelación no consume número; dos cargas simultáneas no lo repiten.
CREATE TABLE IF NOT EXISTS etl_sesion_contador (
    id      SMALLINT PRIMARY KEY CONSTRAINT chk_etl_sesion_contador_unica CHECK (id = 1),
    ultimo  INTEGER NOT NULL CONSTRAINT chk_etl_sesion_contador_ultimo CHECK (ultimo >= 0)
);

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

-- Un mismo archivo (nombre normalizado) no puede tener dos ejecuciones
-- processing/completed; failed no bloquea el nombre (migración 010).
CREATE UNIQUE INDEX IF NOT EXISTS ux_etl_execution_filename_activo
    ON etl_execution (filename_clave)
    WHERE status IN ('processing', 'completed');

CREATE INDEX IF NOT EXISTS idx_handover_record_execution_id
    ON handover_record (execution_id);

-- Matches the geospatial keyset reader; avoids sorting a full session per page.
CREATE INDEX IF NOT EXISTS idx_handover_record_execution_order
    ON handover_record (execution_id, timestamp_medicion, report_index ASC NULLS LAST, id_registro);

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

