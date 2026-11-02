-- Durable single-send create intent. Active UNKNOWN is not cleared by observation.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_session (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    hc_job_id text NOT NULL REFERENCES hc.mower_firmware_job(hc_job_id),
    connection_key text NOT NULL CHECK (connection_key ~ '^[0-9a-f]{64}$'),
    esp_boot text NOT NULL CHECK (esp_boot ~ '^[0-9A-F]{16}$' AND esp_boot <> repeat('0', 16)),
    profile_crc text NOT NULL CHECK (profile_crc ~ '^[0-9A-F]{8}$' AND profile_crc <> '00000000'),
    state text NOT NULL CHECK (state IN ('CREATE_INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    update_id text UNIQUE CHECK (update_id ~ '^[0-9A-F]{32}$' AND update_id <> repeat('0', 32)),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    revision integer NOT NULL CHECK (revision BETWEEN 1 AND 2),
    active boolean NOT NULL CHECK (active = (state <> 'REJECTED')),
    singleton boolean NOT NULL DEFAULT true CHECK (singleton),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'ADMITTED') = (update_id IS NOT NULL)),
    CHECK ((state = 'CREATE_INTENT') = (revision = 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS mower_firmware_one_active_session
    ON hc.mower_firmware_session(singleton) WHERE active;
