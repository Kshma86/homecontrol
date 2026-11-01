-- PostgreSQL query observability and measurement-history optimization.
--
-- IMPORTANT: CREATE INDEX CONCURRENTLY must be run outside a transaction.
-- This migration is intentionally idempotent and safe to apply statement by
-- statement after PostgreSQL has started with pg_stat_statements preloaded.

create extension if not exists pg_stat_statements;

alter table hc.measurement set (
  autovacuum_analyze_scale_factor = 0.02,
  autovacuum_analyze_threshold = 10000
);

create index concurrently if not exists ix_measurement_key_ts
  on hc.measurement (key, ts desc);

analyze hc.measurement;
