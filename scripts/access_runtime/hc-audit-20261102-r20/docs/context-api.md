# HC Context API

The HC Context API is the shared read model for Web UI, AI, mobile clients, and future modules. PostgreSQL and domain services remain the durable truth and mutation path.

## Versions

- Main context: `context.v1`
- AI summary: `context.ai.v1`

Every context payload includes a `contract` object with the contract name, version, available sections, and TTL category metadata.

## Endpoints

- `GET /api/context`: default lightweight context
- `GET /api/context?full=1`: all registered context sections
- `GET /api/context?sections=weather,irrigation`: selected sections
- `GET /api/context/<section>`: one section
- `GET /api/context/ai/summary`: compact AI-ready context
- `POST /api/context/invalidate`: invalidate one section with `{"section":"weather"}` or all sections with `{}`
- `GET /api/context/events`: recent command/context events

## Default Sections

The default `/api/context` response is intentionally lightweight:

- `weather`
- `irrigation`
- `climate`
- `robot`
- `power_wall`
- `solar`
- `tuya`
- `backup`
- `notes`

The response includes:

- `compact`: `true` for the default response
- `default_sections`: sections included by default
- `omitted_sections`: sections available through direct section calls or `?full=1`
- `full_context_url`: currently `/api/context?full=1`

Large default sections are trimmed to summaries. Use `GET /api/context/<section>` for detailed devices, histories, and archive lists.

## Lazy Or Expensive Sections

These sections are available, but are not included in the default context:

- `scheduler`
- `irrigation_pilot`
- `irrigation_statistics`
- `climate_power_history`
- `climate_schedules`
- `performance`
- `home_statistics`
- `scheduler_ai`

`scheduler_ai` is a lightweight section used by `GET /api/context/ai/summary`. It avoids fetching full scheduler jobs, run history, and V2 chain diagnostics.

`scheduler`, `irrigation_pilot`, and `climate_schedules` are realtime read models with a longer TTL because they are more expensive than sensor-like state. Statistics sections also use the longer statistics TTL.

## Response Shape

```json
{
  "ok": true,
  "schema_version": "context.v1",
  "generated_at": "2026-07-24T12:00:00+00:00",
  "contract": {
    "name": "hc_context",
    "version": "context.v1",
    "available_sections": ["weather", "irrigation"],
    "statistics_sections": ["performance"],
    "expensive_realtime_sections": ["scheduler"]
  },
  "source": {
    "truth": "postgres",
    "mode": "read_through_memory_cache",
    "realtime_ttl_sec": 5,
    "statistics_ttl_sec": 60
  },
  "house": {},
  "realtime": {},
  "statistics": {},
  "events": {}
}
```

## Command Responses

Mutation endpoints stay domain-specific. When a command changes state, the response should include `context` metadata:

```json
{
  "context": {
    "invalidated": ["irrigation"],
    "read_after": ["/api/context/irrigation"]
  }
}
```

Clients should refresh the listed `read_after` endpoints instead of guessing which domain state changed.

## Runtime Refresh

The backend can keep selected context sections warm in a background loop.

- `HC_CONTEXT_REFRESH_ENABLED`: default `1`
- `HC_CONTEXT_REFRESH_SECONDS`: default `4`
- `HC_CONTEXT_REFRESH_SECTIONS`: comma-separated section list

By default the refresh loop warms the default context sections plus `scheduler`, `scheduler_ai`, and `performance`. The context service still honors per-section TTLs, so expensive sections are not rebuilt every loop.

## Smoke And Performance Budget

Run:

```bash
python3 scripts/smoke_backend.py --base-url http://127.0.0.1:5000
```

The script validates status codes and selected latency budgets. Use `--no-perf-budget` when only API availability matters.

## Compatibility Endpoints

Legacy read endpoints remain available as wrappers over context sections, for example:

- `GET /api/irrigation/state`
- `GET /api/climate/gree/state`
- `GET /api/xiaomi-x10/state`
- `GET /api/power-wall/state`
- `GET /api/backup`

New clients should prefer `/api/context` and `/api/context/<section>`.
