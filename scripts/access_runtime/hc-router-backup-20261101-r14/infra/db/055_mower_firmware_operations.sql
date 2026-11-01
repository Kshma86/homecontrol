-- One durable send intent per native session/action; explicit verified HC exit.
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS closed boolean NOT NULL DEFAULT false;
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS initial_stm_boot text
    CHECK (initial_stm_boot ~ '^[0-9A-F]{16}$' AND initial_stm_boot <> repeat('0', 16));
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_active_check;
-- Migration 054's cross-column inline CHECK receives this PostgreSQL name.
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_check;
ALTER TABLE hc.mower_firmware_session ADD CONSTRAINT mower_firmware_session_active_check
    CHECK (active = (state <> 'REJECTED' AND NOT closed));
CREATE TABLE IF NOT EXISTS hc.mower_firmware_operation (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL REFERENCES hc.mower_firmware_session(request_id),
    action text NOT NULL CHECK (action IN ('IMAGE', 'ABORT', 'FINISH')),
    state text NOT NULL CHECK (state IN ('INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    service_boot text NOT NULL CHECK (service_boot ~ '^[0-9A-F]{16}$' AND service_boot <> repeat('0', 16)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_request_id, action)
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_exit (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL UNIQUE REFERENCES hc.mower_firmware_session(request_id),
    proof jsonb NOT NULL CHECK (jsonb_typeof(proof) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
