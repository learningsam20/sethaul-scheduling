-- 005: runtime indexes for messaging and operational flows
-- Idempotent index creation.

CREATE INDEX IF NOT EXISTS ix_operational_messages_shipment_sent
ON operational_messages(shipment_id, sent_at);

CREATE INDEX IF NOT EXISTS ix_chat_messages_thread
ON chat_messages(thread_id);

CREATE INDEX IF NOT EXISTS ix_penalty_requests_status
ON penalty_requests(status, created_at);

CREATE INDEX IF NOT EXISTS ix_allocation_policy_facility
ON allocation_policy(facility_id, active_flag);
