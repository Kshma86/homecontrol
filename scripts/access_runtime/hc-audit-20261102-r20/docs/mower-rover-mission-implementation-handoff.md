# Rover mission execution implementation handoff

> Historical implementation notes. The canonical, copyable wire/storage and
> safety contract is now `ROVER_HC_CONTRACT.md` v2.1.0 section 8. Where this
> document differs, the root contract wins.

Status: rover-side implementation specification. The HomeControl RTK Editor
already edits boundaries and exclusion zones, generates a cell-decomposed
coverage preview, simulates it in the browser and exports GeoJSON. Durable HC
mission storage, mission upload and rover execution are not implemented yet.

This document is intended to be given to the AI/developer working on the ESP32
and STM32 rover firmware.

## 1. Objective

Extend the rover so that it can safely receive, validate, store and execute a
HomeControl-generated mowing mission containing substantially more than the
current 10 waypoint limit.

The rover must execute a mission without a live HomeControl, Wi-Fi or MQTT
connection. Loss of HC/ESP connectivity must never cause the STM32 to continue
using a stale motion command or to resume a stopped mission automatically.

Do not replace or weaken the existing emergency stop, fault, safety, manual
WebSocket or low-rate MQTT controls.

## 2. Current HC behavior and assumptions

The RTK Editor currently supports:

- WGS84 boundary polygons;
- multiple WGS84 exclusion polygons;
- draggable vertices and centimetre-scale editing;
- configurable cut width, overlap, boundary clearance, rover width, turn
  radius, sweep heading and planned speed;
- boustrophedon-style logical cell decomposition;
- straight cutting lanes inside each cell;
- obstacle-aware connectors around inflated exclusion zones;
- validation of connectors against the boundary and exclusions;
- browser simulation and GeoJSON export.

The exported GeoJSON is a planning artifact, not a rover command format. Map
tiles and satellite imagery must never be sent to the rover.

The current legacy route implementation publishes `status/route`, supports at
most 10 points and accepts these MQTT commands:

```text
homecontrol/mower/cmd/route/record
homecontrol/mower/cmd/route/clear
homecontrol/mower/cmd/route/play
homecontrol/mower/cmd/route/stop
```

Keep this legacy path operational during development. Implement the new mission
system beside it and use distinct topics/endpoints.

Existing pose conventions are defined in `docs/mower-rtk-map-contract.md`:

- heading is navigation heading (`0°` north, `90°` east, clockwise positive);
- RTK position is WGS84 latitude/longitude;
- IMU compass heading is preferred, GNSS course is fallback only when valid;
- activated autonomous movement requires a valid north reference.

Existing manual control is defined in `docs/mower-websocket-contract.md` and
must retain priority over autonomous execution only through an explicit,
safe ownership transition.

## 3. Required responsibility split

### HomeControl

- owns editable boundary and exclusion geometry;
- owns mission versions and planning parameters;
- generates logical cells, lanes and safe connectors;
- converts the approved plan into the rover mission format;
- uploads, validates and explicitly activates a staged mission;
- displays rover validation and execution telemetry.

### ESP32

- exposes the mission upload/status HTTP API to HC;
- owns upload/session arbitration and chunk transfer;
- verifies transport size and CRC before forwarding/committing;
- transfers the complete mission to STM32 using a framed, acknowledged
  protocol;
- bridges STM32 mission state to MQTT;
- never performs the real-time steering controller;
- never treats upload or activation as permission to move.

### STM32

- owns the active mission used for motion;
- independently validates every mission before activation;
- owns the autonomous state machine and real-time path tracking;
- applies antenna/body/cutter offsets;
- continuously enforces geofence, exclusion and RTK/safety gates;
- stops locally without waiting for ESP/HC;
- persists enough progress metadata for diagnosis, but never auto-resumes motion
  after reset or power loss.

## 4. Mission format (`hc.mower.mission.v1`)

Use a compact binary representation on the wire and in STM storage. JSON below
is the canonical semantic representation and should also be supported by
development tools/tests.

```json
{
  "schema": "hc.mower.mission.v1",
  "mission_id": "550e8400-e29b-41d4-a716-446655440000",
  "revision": 7,
  "created_at": "2026-09-23T10:00:00Z",
  "origin": {
    "lat_e7": 469894235,
    "lon_e7": 179729970
  },
  "geometry": {
    "rover_width_mm": 550,
    "cut_width_mm": 420,
    "antenna_forward_mm": 120,
    "antenna_left_mm": 0,
    "boundary_clearance_mm": 250
  },
  "limits": {
    "drive_speed_mm_s": 350,
    "turn_speed_mdeg_s": 30000,
    "max_cross_track_mm": 250,
    "max_heading_error_mdeg": 45000,
    "max_rtk_age_ms": 1500,
    "max_correction_age_ms": 3000
  },
  "boundary": [
    {"east_mm": 0, "north_mm": 0}
  ],
  "exclusions": [
    [{"east_mm": 1000, "north_mm": 1000}]
  ],
  "operations": [
    {"type": "BLADE_ON", "target_rpm": 6000},
    {"type": "TURN_IN_PLACE", "heading_mdeg": 90000},
    {
      "type": "DRIVE_LINE",
      "east_mm": 8500,
      "north_mm": 1200,
      "speed_mm_s": 350,
      "blade": true,
      "cell": 1,
      "lane": 1
    },
    {"type": "BLADE_OFF"},
    {"type": "STOP"}
  ],
  "payload_crc32": "8A31C20F"
}
```

### Coordinate rules

- All executable geometry uses a local East/North metric plane.
- `origin.lat_e7` and `origin.lon_e7` are signed WGS84 degrees times `1e7`.
- `east_mm` is positive east; `north_mm` is positive north.
- Angles use signed/unsigned millidegrees as appropriate, navigation convention.
- All integer fields have explicitly defined width and signedness in the binary
  schema. Do not transmit floats in the STM protocol.
- Define maximum counts and total payload size. Reject overflow instead of
  truncating.

Recommended initial limits:

```text
boundary vertices:       256
exclusion polygons:       32
vertices per exclusion:  128
operations:             4096
mission payload:       256 KiB
```

Adjust these only after checking actual MCU RAM and non-volatile storage. The
decoder must stream/validate or use bounded buffers; it must not trust counts
from the uploaded file.

### Initial operation set

Implement only deterministic primitives first:

- `TURN_IN_PLACE(target_heading_mdeg)`
- `DRIVE_LINE(target_east_mm, target_north_mm, speed_mm_s, blade)`
- `BLADE_ON(target_rpm)`
- `BLADE_OFF`
- `STOP`

Do not add spline/arc execution until straight-line tracking and stop behavior
are proven. Unknown operation types or schema versions must reject the whole
mission.

## 5. Storage model

Do not store missions in program ROM or compile them into firmware.

Preferred rover storage order:

1. STM-accessible external QSPI flash or SD card;
2. dedicated STM internal-flash sectors if writes are infrequent and wear is
   acceptable;
3. ESP flash only as an upload staging area, never as the sole active mission
   store required during execution.

Maintain two atomic slots:

```text
STAGED: completely received and validated, not executable
ACTIVE: explicitly activated and used by STM execution
```

Each slot header should include magic, schema version, mission UUID/revision,
payload length, CRC32, validation status and commit generation. Write payload
first and the valid/committed header last. Activation must be atomic or
recoverable after power loss.

Persist progress separately with wear control:

- active mission ID/revision;
- last completed operation index;
- last stop reason;
- timestamp/uptime marker.

Progress is diagnostic/resume-candidate information only. After any reset the
mission state must be `PAUSED_RESTART`; movement requires a new explicit start.

## 6. Upload and activation protocol

Follow the existing STM firmware update pattern (prepare, upload, verify,
activate), but use separate mission endpoints and ownership.

Proposed ESP HTTP API:

```text
GET  /api/mission/status
POST /api/mission/prepare?client=...&size=...&crc=...&mission_id=...&revision=...
POST /api/mission/upload?client=...
POST /api/mission/validate?client=...
POST /api/mission/activate?client=...&mission_id=...&revision=...
POST /api/mission/start?client=...
POST /api/mission/pause?client=...
POST /api/mission/stop?client=...
```

Requirements:

- use the existing remote-session ownership rules;
- reject upload while manual drive, route playback or mission execution owns
  control;
- use fixed-size chunks with sequence number, length and per-frame CRC;
- acknowledge every chunk; retries must be idempotent;
- verify whole-payload length and CRC32 at ESP and STM;
- `upload`, `validate`, `activate` and `start` are four separate actions;
- activation is allowed only for the exact validated ID/revision/CRC;
- start is allowed only from an explicit safe state;
- a failed upload must leave the old ACTIVE slot untouched.

Suggested ESP-to-STM framing:

```text
MISSION_BEGIN(id, revision, size, crc32)
MISSION_CHUNK(offset, length, chunk_crc16, data)
MISSION_END(size, crc32)
MISSION_VALIDATE
MISSION_ACTIVATE(id, revision, crc32)
MISSION_CONTROL(START|PAUSE|STOP)
```

Return structured NACK codes such as `BUSY`, `BAD_SCHEMA`, `BAD_LENGTH`,
`BAD_CRC`, `OUT_OF_RANGE`, `INVALID_POLYGON`, `UNSAFE_OPERATION`,
`STORAGE_FAILED`, `RTK_NOT_READY` and `SAFETY_BLOCKED`.

## 7. STM validation requirements

Never trust HC/ESP validation alone. Before marking STAGED valid, STM must check:

- supported schema and bounded counts/lengths;
- CRC and complete decode with no trailing/partial data;
- origin and all coordinates are within configured numeric limits;
- boundary has at least three non-duplicate points and no self-intersection;
- exclusions are valid and lie inside the boundary;
- every operation target lies inside the permitted boundary and outside every
  inflated exclusion polygon;
- every `DRIVE_LINE` segment is sampled/checked across its full length;
- speeds, RPM, heading and tolerances are within firmware hard limits;
- operation sequence starts/ends safely and contains a final `STOP`;
- mission size and estimated duration are reasonable;
- mission does not require capabilities absent in this firmware build.

Return a validation report containing warnings and errors. Warnings must never
silently override STM hard safety limits.

## 8. Execution state machine

Minimum states:

```text
NO_MISSION
STAGED_INVALID
STAGED_VALID
ACTIVE_IDLE
START_CHECK
TURNING
DRIVING
PAUSED
PAUSED_RESTART
COMPLETED
STOPPING
FAULT
```

Required transitions:

- `START_CHECK` verifies arm state, safety inputs, motor/CAN health, RTK FIX,
  correction age, heading validity and current position inside the geofence.
- Each operation transition first commands zero drive and waits for confirmed
  stop when direction/ownership changes.
- `PAUSE` stops drive and blade but retains the current operation/progress.
- `STOP` stops drive and blade, cancels autonomous control and requires a new
  explicit start from operation 0 unless a future resume command is designed.
- Any safety/fault/geofence/RTK violation transitions through `STOPPING` to
  `FAULT` or `PAUSED` according to a documented fault policy.
- Reset/power loss always returns to `PAUSED_RESTART`, never directly to motion.

## 9. Path tracking

Use STM's current RTK/IMU local pose and implement a bounded line tracker
(cross-track plus heading feedback, or a tested pure-pursuit/Stanley variant).

For each `DRIVE_LINE`:

1. transform WGS84 RTK pose to local East/North relative to mission origin;
2. compensate antenna offset to obtain the rover control point;
3. calculate along-track and cross-track errors;
4. calculate desired heading and wrapped heading error;
5. limit forward speed based on heading error and remaining distance;
6. generate bounded differential left/right targets;
7. stop at the target tolerance before changing operation;
8. publish errors and controller output for diagnosis.

The antenna compensation must rotate body-frame offsets by current heading.
Do not treat the antenna coordinate as the rover centre unless offsets are zero.

Initial conservative behavior:

- rotate in place before every straight lane/connector;
- blade off during connectors and turns;
- blade on only for operations explicitly marked as cutting;
- no reverse autonomous motion;
- low speed and generous target tolerance during first tests.

## 10. Runtime safety gates

STM must command drive zero and blade off if any of these occurs:

- E-stop, bumper, lift, tilt or configured IMU tilt;
- motor/CAN communication fault;
- RTK fix quality below the configured requirement;
- stale GNSS pose or RTCM correction;
- invalid/unavailable north reference;
- cross-track or heading error above limits for a bounded duration;
- pose outside boundary or inside an inflated exclusion;
- mission decode/storage inconsistency;
- controller watchdog expiry;
- ownership conflict with manual/legacy route control.

Geofence checks must run on the STM during motion, not only during mission
validation. Use rover footprint/clearance, not merely the antenna point.

Faults must be latched with a human-readable enum plus bitmask. Publish both;
HC already renders `status/fault.name` in a human-friendly way.

## 11. MQTT telemetry contract

Add the following rover publications under `homecontrol/mower`:

`status/mission` (1 Hz and immediately on state change):

```json
{
  "state": "DRIVING",
  "mission_id": "550e8400-e29b-41d4-a716-446655440000",
  "revision": 7,
  "crc32": "8A31C20F",
  "operation_index": 42,
  "operation_count": 860,
  "operation_type": "DRIVE_LINE",
  "cell": 3,
  "lane": 8,
  "progress_pct": 18.4,
  "cross_track_mm": -37,
  "heading_error_mdeg": 2100,
  "distance_remaining_mm": 4820,
  "blade_requested": true,
  "validation": "VALID",
  "stop_reason": "NONE"
}
```

`status/mission_storage` (on change and periodically at low rate):

```json
{
  "staged_valid": true,
  "staged_id": "...",
  "staged_revision": 8,
  "active_valid": true,
  "active_id": "...",
  "active_revision": 7,
  "storage": "qspi",
  "free_bytes": 1234567
}
```

`status/mission_validation` (on validate):

```json
{
  "ok": false,
  "errors": [{"code":"SEGMENT_IN_EXCLUSION","operation":42}],
  "warnings": []
}
```

Do not put the full mission or large point arrays in periodic MQTT messages.
MQTT control commands should remain non-retained. Mission status may be
retained only if it clearly includes boot/session identity and cannot imply
that motion is still active after reboot; non-retained is safer initially.

## 12. Compatibility and ownership

Define exactly one motion owner:

```text
NONE | MANUAL_WS | LEGACY_ROUTE | MISSION
```

- owner acquisition requires zero commanded motion;
- a new owner cannot silently pre-empt another owner;
- emergency stop bypasses ownership and is always accepted;
- manual disconnect/deadman stops and releases as already specified;
- mission start fails while another owner exists;
- mission pause/stop releases or retains ownership according to one documented
  policy (recommended: pause retains mission context but commands zero; manual
  claim requires explicit mission stop/release).

Do not change existing topic meanings while adding mission support.

## 13. Implementation phases

### Phase A — format and storage, no movement

- define packed binary schema and host-side encoder/decoder test vectors;
- implement ESP upload API and STM framing;
- implement STAGED/ACTIVE slots, CRC and atomic activation;
- implement STM validator and MQTT status;
- prove power-loss recovery at every upload/activation boundary.

### Phase B — dry-run execution

- run the STM state machine with motor outputs forcibly disabled;
- feed recorded RTK/IMU samples;
- publish intended operation, heading and wheel targets;
- verify geofence and exclusion stops;
- compare STM decisions with HC simulation.

### Phase C — wheels raised / blade removed

- low speed, short two-line mission;
- verify turn-in-place and line completion;
- force RTK loss, stale correction, CAN fault and ESP disconnect;
- confirm local zero output and latched reason.

### Phase D — controlled outdoor test

- blade disabled, clear test area, physical E-stop observer;
- small convex boundary without exclusions;
- then one exclusion and multiple logical cells;
- only after repeatable tracking enable blade operations.

## 14. Required tests and acceptance criteria

Unit/property tests:

- binary decode rejects truncation, overflow and unknown schema/opcodes;
- CRC mismatch never creates a valid slot;
- activation never changes ACTIVE on failure/power interruption;
- WGS84-to-local conversion has known centimetre-level fixtures;
- heading wrap works across `359°/0°`;
- antenna offset rotation has cardinal-direction fixtures;
- segment/geofence intersection catches between-waypoint violations;
- every safety gate forces zero targets;
- state machine has no transition from boot/reset directly to motion.

Integration acceptance:

- upload at least 1,000 operations with chunk retry and one simulated dropped
  response;
- reboot ESP during upload: old ACTIVE remains usable and motion is stopped;
- reboot STM after staging and after activation: no automatic motion;
- start is rejected without RTK FIX, valid heading, clear safety and healthy CAN;
- HC/MQTT/Wi-Fi loss during execution does not impair local safety enforcement;
- crossing the configured cross-track/geofence limit stops within the defined
  maximum latency/distance;
- exclusion-zone mission is followed without entering the inflated exclusion;
- all telemetry IDs/revisions/indices match the active mission.

## 15. Deliverables expected from the rover implementation

The rover-side AI/developer should return:

1. the exact binary mission schema with field widths and byte order;
2. ESP HTTP endpoint implementation and request/response examples;
3. ESP-to-STM frame definitions, retry/timeouts and maximum sizes;
4. STM storage layout and atomic commit strategy;
5. STM validator and execution state machine;
6. controller equations, gains, clamps and update rate;
7. MQTT telemetry implementation;
8. automated test results and hardware test checklist;
9. a list of required HC backend/frontend changes based on the final rover
   contract;
10. explicit documentation of anything deferred or simulated.

## 16. Non-goals for the first rover release

- The STM does not generate coverage paths from polygons.
- The rover does not download or render map/satellite tiles.
- The rover does not dynamically re-plan around unmodelled obstacles.
- The rover does not automatically resume after reset, fault or RTK loss.
- The rover does not accept an unvalidated GeoJSON file as an executable
  mission.
- Upload/activation does not arm or start the mower.

These constraints are intentional. First establish deterministic mission
transfer, independent STM validation, safe straight-line tracking and reliable
stop behavior; optimize turns and add dynamic planning only afterward.
