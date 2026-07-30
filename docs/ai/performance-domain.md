# Performance And System Status Domain Context

## Scope

The performance module publishes operational health for the HomeControl host,
backend, Docker containers, PostgreSQL, MQTT, background workers, server power,
and latest backup status.

Primary implementation:

- `infra/backend/system_status_service.py`
- `infra/backend/energy_device_service.py`
- `infra/backend/backup_service.py`
- `infra/backend/api_route_modules.py`

## Ownership

- Read-model owner: `SystemStatusService.performance_snapshot()`.
- Context section: `performance`.
- Related context: `backup`, `power_wall`.
- Mutation owner: none.

## API Endpoints

Read endpoints:

- `GET /api/context/performance`
- `GET /api/performance`
- `GET /api/homecontrol/statistics`

## Data Sources

Performance snapshot reads:

- `/proc/stat` for CPU percent.
- `/proc/meminfo` for memory usage.
- Docker socket or Docker CLI for container list/stats.
- PostgreSQL `pg_stat_activity` and `pg_settings`.
- MQTT monitor snapshot.
- Active entity heartbeat/presence rows.
- Python thread list for background workers.
- API performance log callback.
- Server plug power history.
- Latest backup info.

Important naming rule:

- `HC szerver` means the physical HomeControl server's Tuya smart plug /
  consumption meter.
- It is not the AI server container, not Ollama, and not the remote AI node.
- For questions like "mennyi az átlag fogyasztása a HC szervernek?", use
  `server_power`, not irrigation pump statistics and not Docker runtime stats.
- If `server_power` is missing but `power_wall.devices` contains `HC szerver`,
  only answer with the available instantaneous plug data and clearly say that
  7/30 day energy averages are not available in the current AI context.

## Docker Rules

- Prefer Docker socket if available.
- Fall back to `docker ps` and `docker stats` CLI.
- Docker status is cached by `DOCKER_STATUS_CACHE_TTL`, default `30` seconds.
- If neither socket nor CLI works, return `ok: false` in Docker section rather
  than failing the whole performance payload.

## Worker Checks

Workers currently reported:

- `irrigation-safety`
- `openweather-poll`
- `irrigation-mqtt-monitor`

Worker status is based on Python thread names.

## Payload Shape

`performance_snapshot()` returns:

- `ok`
- `generated_at`
- `cpu`
- `memory`
- `postgres`
- `mqtt`
- `heartbeats`
- `docker`
- `workers`
- `thread_count`
- `api`
- `api_log`
- `server_power`
- `backup`
- `summary`

`GET /api/context/ai/summary` includes a compact `server_power` block:

- `current_power_w`
- `avg_power_w_24h`
- `max_power_w_24h`
- `today_energy_kwh`
- `avg_daily_energy_kwh_7d`
- `avg_daily_energy_kwh_30d`
- `total_energy_kwh`
- device identity and status

Interpretation:

- `avg_power_w_24h` is average power in watts over sampled points.
- `avg_daily_energy_kwh_7d` and `avg_daily_energy_kwh_30d` are average daily
  energy consumption in kWh/day.
- Do not describe energy as "minutes" and do not label watt-hours as kWh.
- Do not infer average energy from a single instantaneous `power_w` value.

## Safety Rules

- Performance reads must be non-mutating.
- Host/Docker probing errors should be represented in payloads, not thrown to
  the user when possible.
- Keep slow external checks cached or time-limited.
- Do not run destructive Docker commands from this module.
