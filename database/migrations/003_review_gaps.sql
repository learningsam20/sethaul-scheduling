-- Review-gap patches: exclusive soft-holds, dock events in availability, extra facility rules.
-- Idempotent (CREATE IF NOT EXISTS / DROP VIEW / INSERT OR IGNORE).

CREATE UNIQUE INDEX IF NOT EXISTS ux_active_slot_hold
ON slot_holds(slot_id)
WHERE status = 'ACTIVE';

DROP VIEW IF EXISTS v_slot_availability;
CREATE VIEW v_slot_availability AS
SELECT
    sl.slot_id,
    sl.facility_id,
    d.dock_code,
    d.dock_type,
    d.supports_refrigerated,
    d.max_vehicle_weight_kg,
    sl.slot_start_ts,
    sl.slot_end_ts,
    CASE
        WHEN sl.slot_status <> 'OPEN' THEN sl.slot_status
        WHEN EXISTS (
            SELECT 1 FROM dock_status_events e
            WHERE e.dock_id = sl.dock_id
              AND e.event_type IN ('MAINTENANCE','BREAKDOWN','CAPACITY_REDUCTION','MANUAL_BLOCK')
              AND e.event_start_ts < sl.slot_end_ts
              AND (e.event_end_ts IS NULL OR e.event_end_ts > sl.slot_start_ts)
        ) THEN 'BLOCKED'
        WHEN a.appointment_id IS NOT NULL THEN 'OCCUPIED'
        ELSE 'AVAILABLE'
    END AS availability_status,
    a.appointment_id,
    a.shipment_id,
    a.appointment_status
FROM appointment_slots sl
JOIN docks d ON d.dock_id = sl.dock_id
LEFT JOIN appointments a
    ON a.slot_id = sl.slot_id
   AND a.appointment_status IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS');

INSERT OR IGNORE INTO facility_rules(
    rule_id, facility_id, rule_type, rule_value, description, effective_from, effective_to, active_flag
) VALUES
    ('RULE007','FAC-JAI-01','PRODUCT_RESTRICTED','Hazmat,Explosives',
     'These product classes cannot be auto-booked at Jaipur DC.','2026-01-01',NULL,1),
    ('RULE008','FAC-JAI-01','CARRIER_BLOCKED','',
     'Comma-separated carrier_ids that may not auto-book at this facility.','2026-01-01',NULL,1),
    ('RULE009','FAC-GGN-01','PRODUCT_RESTRICTED','Hazmat',
     'Hazmat cannot be auto-booked at Gurugram.','2026-01-01',NULL,1);
