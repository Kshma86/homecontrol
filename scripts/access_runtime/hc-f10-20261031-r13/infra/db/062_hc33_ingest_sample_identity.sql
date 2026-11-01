-- HC-33: additive identity for new ingest samples only; old writers remain valid.
-- Explicit migration, never run by ingest startup. No historical backfill.
-- Run in a controlled migration window: the unique partial index scans measurement.
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='120s';
ALTER TABLE hc.measurement ADD COLUMN IF NOT EXISTS ingest_sample_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS ux_measurement_ingest_sample_id
  ON hc.measurement (ingest_sample_id) WHERE ingest_sample_id IS NOT NULL;
