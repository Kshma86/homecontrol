# Solar Domain Context

## Scope

The solar module is a read-model for Growatt solar/inverter telemetry. It does
not command inverter hardware from the backend.

Primary implementation:

- `infra/backend/energy_device_service.py`
- `infra/backend/api_route_modules.py`
- `apps/ha-growatt-poller/ha_growatt_poller.py`
- `infra/db/018_growatt_solar_inverter.sql`
- `infra/db/019_ha_growatt_cloud.sql`

## Ownership

- Durable truth: `hc.device`, `hc.entity`, `hc.entity_state`,
  `hc.measurement`.
- External source: Growatt cloud poller and MQTT ingest.
- Backend owner: `EnergyDeviceService.solar_state_payload()`.
- Context section: `solar`.
- Mutation owner: none in this backend module.

## Topic And Entity

Default topic base:

```text
homecontrol/tele/growatt/cloud
```

The solar read model finds the entity by this topic base. If the entity is
missing, `/api/solar/state` returns:

```json
{
  "ok": false,
  "error": "Growatt cloud entity not found"
}
```

## Home Assistant Polling (HC-26)

The optional `ha-growatt` Compose profile runs the HA poller. Its measured
production configuration has 27 mapped entities; the inspected HA instance
returned 86 state objects in about 38 KiB. The HC-26 source repair replaces the
27 serial per-entity GETs with **one `GET /api/states` per poll**, then selects
only configured entities locally. No HA action/service or inverter command is
issued. See [HC-26 repair and measurements](../hc-26-repair.md).

The flat MQTT metric names, value conversion, topic, QoS/retain and existing
`source`, `entity_count`, `meta` fields remain compatible. Missing entities and
unknown/unavailable states produce no new metric; usable entities from the
same response still publish. A failed HTTP/JSON/body read produces an empty
cycle (`entity_count=0`, `meta={}`), without per-entity fallback or replay of
previous values. The next cycle makes a new single request. An omitted metric
does not delete the previously stored DB state; consumers still need to assess
its age.

`sample_time` is the UTC time **after the snapshot read**, not the inverter's
physical acquisition time. Each published metric retains its original
`meta[key].last_updated`, unit and friendly name, with two additive fields:

- `observed_at`: the snapshot observation timestamp, shared by the cycle.
- `ha_state_age_seconds`: age of the HA `last_updated` value at observation;
  null for missing, invalid, timezone-less or future timestamps.

An unchanged HA state gets older across polls. Its age is not reset by a fresh
HTTP read, and `last_updated` is not claimed to prove the inverter/cloud source's
physical measurement age. Old numeric values are not silently replaced or
removed by a newly invented freshness threshold. The existing SQL 019 `meta`
JSON-state metric and ingest generic mapping already carry this information;
no new schema or ingest path is required.

The interval uses monotonic elapsed time; the default remains 60 seconds, with
at least a one-second wait after an overrun. There is one existing configured
HTTP timeout per cycle, with no retry multiplier. Requests' connect/read timeout
is **not a hard whole-cycle deadline** (DNS, connect attempts and continuous
response bytes can take longer). The worker-health allowance is now based on
one request instead of entity count; it reports a stuck worker but does not
abort its socket. A hard transport deadline or HA freshness policy is separate
work, not an additional change in HC-26. MQTT success/readiness semantics are
unchanged.

This code repair is not yet deployed. A new Growatt-poller image is required;
the HA service, MQTT credentials and entity map need no migration. Live HA
measurements in the repair used GET only; tests use fake HA/MQTT transports.

## API Endpoints

Read endpoints:

- `GET /api/context/solar`
- `GET /api/solar/state`

No solar mutation endpoint currently exists.

## Payload Shape

`solar_state_payload()` returns:

- `ok`
- `entity`
- `state`
- `current`
- `state_rows`
- `recent_measurements`
- `charts.load_power_24h`
- `charts.production_power_24h`
- `charts.production_daily_30d`
- `summary`

Important `current` priority fields:

- `system_power_w`
- `output_power_w`
- `plant_output_power_w`
- `energy_today_kwh`
- `plant_energy_today_kwh`
- `lifetime_energy_kwh`
- `plant_lifetime_energy_kwh`
- `battery_soc_percent`
- `local_load_power_w`
- `import_power_w`
- `export_power_w`
- `load_consumption_today_kwh`
- `export_to_grid_today_kwh`
- `input_1_wattage_w`
- `input_2_wattage_w`
- `growatt_grid_voltage_l1_v`
- `growatt_grid_voltage_l2_v`
- `growatt_grid_voltage_l3_v`

## Chart Rules

- Load power chart covers the last 24 hourly buckets.
- Production power chart covers the last 24 hourly buckets.
- Daily production chart covers 30 days including today.
- Daily and monthly production are calculated from daily counter maximums after
  the first same-day reset sample, so stale pre-reset values just after midnight
  are ignored.
- Production prefers `plant_energy_today_kwh`, then `energy_today_kwh`, then
  `solar_energy_today_kwh`.

## Editing Guidance

- Do not add inverter commands unless a separate command owner and safety model
  is designed.
- Keep this as a read-only context section.
- If new Growatt metrics are added, register them in a migration and decide
  whether they belong in `current`, charts, or only raw `state`.
- Preserve `json_ready()` conversion because this payload contains datetimes and
  database numeric values.
