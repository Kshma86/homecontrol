# Mower RTK pose and mapping notes

Status: HC live visualization and browser RTK Editor implemented; durable HC
mission storage and rover mission execution pending. Rover implementation is
specified in `docs/mower-rover-mission-implementation-handoff.md`.
The canonical live wire schema is `ROVER_HC_CONTRACT.md` v2.0.0; that file wins
if this mapping note conflicts with it.

The rover publishes periodically refreshed JSON under the MQTT base topic
`homecontrol/mower`. A retained status is historical and never counts as fresh.

## Required pose inputs

`status/gnss`:

```json
{
  "alive": true,
  "fix_quality": 4,
  "fix_name": "RTK FIX",
  "lat": 47.00000000,
  "lon": 19.00000000,
  "hdop": 0.7,
  "sats": 20,
  "speed_kmh": 0.2,
  "course_deg": 90.0,
  "correction_age_s": 0.8,
  "age_ms": 100
}
```

`status/imu`:

```json
{
  "alive": true,
  "compass_deg": 90.0,
  "north_valid": true,
  "auto_north_active": false,
  "auto_north_status": "IDLE",
  "age_ms": 100
}
```

Angles use navigation convention: `0°` north, `90°` east, increasing
clockwise. HC prefers `status/imu.compass_deg` for orientation and falls back
to `status/gnss.course_deg` when no IMU heading is available.

HC exposes a normalized `rtk_pose` object in the mower context. The current
frontend converts WGS84 latitude/longitude to a local east/north plane whose
origin is the first valid pose in the browser session. The displayed track is
temporary, limited to 500 samples, and does not command the rover.

## Planned survey extension

Durable survey mode should add explicit start, pause, resume and close events,
store every accepted raw sample with its quality metadata, and derive editable
boundary/exclusion polygons from that immutable sample set. Only RTK FIX
samples that pass correction-age and quality gates should enter an activated
working map.
