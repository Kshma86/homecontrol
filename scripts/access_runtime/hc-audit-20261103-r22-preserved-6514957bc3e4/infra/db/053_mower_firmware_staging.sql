-- HC-local retained firmware only. HC_STAGED is NOT a native update session.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_artifact (
    artifact_id text PRIMARY KEY CHECK (artifact_id ~ '^[0-9a-f]{64}$'),
    image bytea NOT NULL CHECK (octet_length(image) BETWEEN 1280 AND 524288 AND octet_length(image) % 32 = 0),
    elf bytea NOT NULL CHECK (octet_length(elf) BETWEEN 52 AND 16777216),
    saved_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_job (
    hc_job_id text PRIMARY KEY CHECK (hc_job_id ~ '^[0-9A-F]{32}$' AND hc_job_id <> repeat('0', 32)),
    request_id text NOT NULL UNIQUE CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    artifact_id text NOT NULL REFERENCES hc.mower_firmware_artifact(artifact_id),
    release_id text NOT NULL CHECK (release_id ~ '^[A-Za-z0-9_.-]{1,64}$'),
    state text NOT NULL CHECK (state = 'HC_STAGED'),
    report jsonb NOT NULL CHECK (jsonb_typeof(report) = 'object'),
    saved_at timestamptz NOT NULL DEFAULT now()
);
