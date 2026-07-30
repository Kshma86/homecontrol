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
- Monthly production is calculated from daily max `energy_today_kwh`,
  `plant_energy_today_kwh`, or `solar_energy_today_kwh`.

## Editing Guidance

- Do not add inverter commands unless a separate command owner and safety model
  is designed.
- Keep this as a read-only context section.
- If new Growatt metrics are added, register them in a migration and decide
  whether they belong in `current`, charts, or only raw `state`.
- Preserve `json_ready()` conversion because this payload contains datetimes and
  database numeric values.
