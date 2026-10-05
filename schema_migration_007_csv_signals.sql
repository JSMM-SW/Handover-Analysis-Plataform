-- Run with a verified backup and the CSV-only application version.
-- Transactional: dependencies block DROP rather than being deleted with CASCADE.
BEGIN;
LOCK TABLE handover_record IN ACCESS EXCLUSIVE MODE;

ALTER TABLE handover_record ADD COLUMN IF NOT EXISTS rssi_strongest SMALLINT NULL;

-- Undo the old CSV mapping. These values were copied, not calculated.
-- Never reinterpret historical Excel RSRP as RSSI.
UPDATE handover_record
SET rssi = COALESCE(rssi, CASE tech
    WHEN 'LTE' THEN rsrp_dbm
    WHEN 'WCDMA' THEN rscp_dbm
    WHEN 'GSM' THEN rssi_dbm
END)
WHERE origen_formato = 'csv' AND rssi IS NULL;

ALTER TABLE handover_record
    DROP COLUMN rsrp_dbm,
    DROP COLUMN rscp_dbm,
    DROP COLUMN rssi_dbm;

ALTER TABLE handover_record DROP CONSTRAINT IF EXISTS handover_record_origen_formato_check;
ALTER TABLE handover_record DROP CONSTRAINT IF EXISTS chk_origen_formato_valido;
ALTER TABLE handover_record ADD CONSTRAINT chk_origen_formato_valido CHECK (origen_formato = 'csv');

COMMENT ON COLUMN handover_record.rssi IS 'Original CSV rssi; unavailable sentinel stored as NULL. No technology-based reinterpretation.';
COMMENT ON COLUMN handover_record.rssi_strongest IS 'Original CSV rssi_strongest. Not a verified RSRP measurement; NULL when absent or unavailable.';
COMMENT ON COLUMN handover_record.rsrq IS 'Original CSV rsrq; unavailable sentinel stored as NULL.';
COMMENT ON COLUMN handover_record.rssnr IS 'Original CSV rssnr; unavailable sentinel stored as NULL.';
COMMIT;
