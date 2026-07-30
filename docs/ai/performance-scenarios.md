# Performance Scenarios And Eval Cases

## Docker Socket Available

Given:

- Docker socket exists and responds.

Expected:

- Container list comes from the socket.
- Running containers include live stats when available.
- Per-container stats errors are attached to container rows without failing the
  whole payload.

## Docker Unavailable

Given:

- Docker socket is missing and Docker CLI is unavailable.

Expected:

- `docker.ok` is false.
- `docker.containers` is empty.
- Performance payload still returns `ok: true`.

## Postgres Stats Failure

Given:

- PostgreSQL stats query fails.

Expected:

- `postgres.ok` is false with an error message.
- Performance payload still includes other sections.

## Worker Status

Given:

- Python threads include `irrigation-safety`.

Expected:

- Matching worker row has `running: true`.

## HC Server Consumption

Given:

- User asks: `mennyi az átlag fogyasztása a hc szervernek?`
- AI context contains `server_power`.

Expected:

- Treat `HC szerver` as the physical HomeControl server smart plug /
  consumption meter.
- Do not treat it as the AI server, remote Ollama node, or irrigation pump.
- Answer with `avg_power_w_24h` in watts when asking average power.
- Include `avg_daily_energy_kwh_7d` or `avg_daily_energy_kwh_30d` as kWh/day
  when asking energy consumption.
- Do not mix minutes, watts, watt-hours, and kWh.

## Suggested Tests

- Docker fallback path does not crash.
- Postgres error is represented as payload data.
- Summary counts match docker and worker rows.
