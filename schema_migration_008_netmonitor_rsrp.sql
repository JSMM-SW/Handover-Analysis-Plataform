-- App-specific interpretation confirmed by the user: NetMonitor rssi_strongest = RSRP.
-- Preserve original values and column names; never derive RSRP from RSSI.
BEGIN;
COMMENT ON COLUMN handover_record.rssi_strongest IS
    'RSRP from NetMonitor CSV rssi_strongest, per user verification of this app. Original value in dBm; NULL when unavailable.';

UPDATE eventos_handover e
SET delta_rsrp_db = posterior.rssi_strongest - previa.rssi_strongest
FROM handover_record previa, handover_record posterior
WHERE e.medicion_previa_id::text = previa.id_registro::text
  AND e.medicion_posterior_id::text = posterior.id_registro::text
  AND e.sesion_id::text = previa.execution_id::text
  AND e.sesion_id::text = posterior.execution_id::text;
COMMIT;
