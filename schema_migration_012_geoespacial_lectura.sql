-- Speeds up complete-session geospatial reads without changing measurements.
-- Run outside a transaction (CONCURRENTLY permits ingestion during creation).
-- Do not wrap this file in BEGIN/COMMIT.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_handover_record_execution_order
    ON handover_record (execution_id, timestamp_medicion, report_index ASC NULLS LAST, id_registro);
