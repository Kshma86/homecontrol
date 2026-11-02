-- HC-local RCP1 drafts only. Revision is not a native rover configuration revision.
CREATE TABLE IF NOT EXISTS hc.mower_parameter_revision (
    rover_key text NOT NULL CHECK (rover_key ~ '^[A-Za-z0-9_-]{1,32}$'),
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    expected_revision bigint NOT NULL CHECK (expected_revision = revision - 1),
    request_id text NOT NULL CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    draft_sha256 text NOT NULL CHECK (draft_sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rover_key, revision),
    UNIQUE (rover_key, request_id)
);
