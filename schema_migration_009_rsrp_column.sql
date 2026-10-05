-- Rename only; preserve all values, NULLs and the SMALLINT type.
BEGIN;
ALTER TABLE handover_record RENAME COLUMN rssi_strongest TO rsrp;
COMMENT ON COLUMN handover_record.rsrp IS
    'RSRP in dBm from the NetMonitor CSV field rssi_strongest, per user verification of this app. NULL when unavailable.';
COMMIT;
