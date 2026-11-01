# Mower subsystem domain contract

## Scope

### Native HC_BRINGUP read-only view — 2026-10-11

Current authority: HC_AI_BRINGUP_ATADAS_20261010.md inside
hc-rover-bringup-20261010.zip; root service handoff explicitly marks LAN2
historical. Default Mower view is now HC_BRINGUP, separate from both adapters
below. Only selected component mounts; HC-only parameter drafts stay available.

- `mower_bringup_read.py`, GET `/api/mower/v3/bringup/snapshot`: fixed native
  identity/state/update/health GETs via the existing bounded auth transport.
- Exact reviewed ESP/STM bringup FW, contract/mode/standalone ABI1/zero profile
  and disabled flags. Native update_locked permits diagnostic STATE ONLY in
  this schema; no change to operational state/updater/release validators.
- STM source expiry 1500 ms includes later GET waits and HC/browser elapsed
  time; repeated seq cannot rejuvenate, old seq/regressing epoch invalid,
  uint32 wrap supported. Matching boots required; new boot binds anew.
- Null safety/source unknown and hex fault mask are diagnostic-only. False
  stopped is absent physical proof, never a claim of motion/physical stop.
  Health network evidence expires at 3000 ms with anti-rejuvenation.
- Native ERROR/METADATA_ERROR lock retained, can_finish=false, no provisioning,
  reset, auto-STOP or update session. All capabilities and qualification false.
- MOWER_V3_READ_ONLY=1 in this deployment blocks all native writes/manual,
  including independent STOP, before I/O or firmware reservations. Preserved
  operational STOP independence still holds when read-only is false. Do not
  auto-clear this deployment gate when firmware/mode changes. UI also disables
  preserved operational controls. HC-only draft CRUD is unaffected.
- Existing private origin/token and durable maintenance guard reused. No
  migration/legacy/context mutation. See `docs/mower-hc-bringup-read.md`.
- Checklist defaults to bringup; --service and --operational are explicit
  historical/operational checks. No credentials or device writes in any mode.

### LAN first-install service read-only view — 2026-10-10

Historical authority for the preceding standalone service FW is
`hc-rover-lan-backend-20261010.zip`, LAN/CONNECT_NOW/service handoff docs.
This supplements, never aliases or replaces, the operational v3.1 adapter below.
The historical service remains an explicit selectable view; only the selected
service or operational component mounts. No silent fallback or dual polling.

- `mower_service_read.py` / GET `/api/mower/v3/service/snapshot` read only native
  `/api/v3/service/status` then `/api/v3/service/parameters`; no POST/WS/MQTT.
- Fixed configured LAN origin and backend-only Bearer token; 3 s/request,
  bounded strict JSON, no proxy/redirect and allowlisted response fields.
- Exact FIRST_INSTALL_SERVICE/ABI1 with motion/applied/commissioned/OTA false;
  matching STM UID/FW, 3000 ms source-age limit including transit/browser age.
  HTTP reachability is not fresh STM or operational compatibility. Revision is
  storage, not a boot/session/heartbeat. No operational proof is synthesized.
- Complete saved RCP1 passes reference validation and CRC; EMPTY null is not a
  default. STAGED_NOT_APPLIED is only storage; no automatic draft import/apply.
- Shares single-worker activity lock and dynamic durable update guard. Reads
  are no-store/nosniff, independent from cached legacy contexts; no DB writes.
- Existing credential env is supported; optional ROVER_API_TOKEN_FILE loads
  bounded private access JSON once at startup. Ambiguous sources fail closed;
  token and private path are excluded from settings repr. No secret enters UI.
- Service UI has refresh only. Original operational controls, firmware workflow,
  HC parameter editor and validators are retained under explicit v3.1 selection.

See `docs/mower-service-read.md`; read-only checklist uses `--service`.

### New Mower tab — 2026-10-09

The `mower` tab now mounts `MowerV3.jsx`. `mower-legacy` displays a static preview
of the original sections/fields with every control disabled and unknown values.
It never imports/mounts `MowerControl.jsx`, the live map or notes widget, and
starts no network/WS effects. The original component is retained intact for reuse.
`RtkEditor.jsx` and its existing backend/context contracts remain unchanged.

For the NEW integration the authority is
`hc-v31-qspi-handoff-20261009-rcp1-foundation.zip`: baseline
`ROVER_SYSTEM_SPEC_v3.1.0.md`, updated by the VG/QSPI integration handoff and
the RCP1/runtime parameter requirement. Do not use the v2 rules below for v3.

Implemented slices: identity/state monitoring, authenticated command/manual
control, HC-local RCP1 parameter drafts, VG RFU2/ELF release preflight and durable
HC firmware staging and explicit native STM session create/status.

- `infra/backend/mower_v3_service.py` owns authenticated, bounded v3 GETs.
- `GET /api/mower/v3/snapshot` bypasses the shared context cache and returns
  `Cache-Control: no-store`, identity, source state, effective age and capabilities.
- `MOWER_V3_REMOTE_URL` explicitly supplies an HTTP(S) origin, independently
  from legacy `MOWER_REMOTE_URL` or MQTT-derived device addresses.
- `ROVER_API_TOKEN` is the backend-only 64-hex credential. Never print or copy
  it into UI configuration; the settings repr also excludes it.
- Without deployment settings, show UNCONFIGURED and unknown STM state.
- No redirects, environment HTTP proxies or v2 fallbacks. Read-model builders
  never issue device mutations.
- Strict JSON types, duplicate-key rejection, bounded response sizes, matching
  boot IDs and known state enums protect the read model.
- Same source_seq cannot refresh age; original age grows with monotonic HC
  elapsed time. Older sequences are not fresh; a new boot changes the session.
- The UI expires cached source evidence locally after 1500 ms, even if HTTP
  hangs or disconnects. Unknown/stale stopped and armed are shown as unknown.
- During update_locked, do not request ordinary STM state.
- `mower_operator_auth.py` owns revocable one-hour operator sessions, separate
  from rover Bearer credentials. Mutation/manual routes require the operator
  cookie and same-origin checks before a rover connection/WS upgrade.
- `mower_v3_commands.py` owns exact v3 payloads and single-send commands:
  arm/disarm/pause/reset_fault/heading_set/start/resume and independent STOP.
  HTTP admission is not execution; only correlated STM ACK permits APPLIED.
  No ACK after 1500 ms means UNKNOWN and GET-only reconciliation. The bounded
  process-local ledger retains 128 records plus 512 retired fingerprints; it
  is not a durable/unlimited audit. Never replay restored browser requests.
- STOP needs no source/boot/epoch/profile preflight; ordinary ledger saturation
  cannot block it. VG NOT_READY remains a rejection, never update ABORT.
- `mower_manual_service.py` owns a single-owner WS relay, exact native protocol,
  matching leases and strictly increasing full setpoint sequences. Only the
  freshest unsent held-drive is forwarded, with 100 ms age and bounded input.
  Deadman false sends full zero. No automatic heartbeat/reclaim/reconnect;
  close sends matching release only, never global STOP that could disrupt AUTO.
  Native lease is 350 ms; manual blade target is deliberately zero.
- Browser manual control loses authority on stale evidence, boot/epoch changes,
  auth loss, visibility loss or stalled send; blur/pointer release zero targets.
- `MOWER_OPERATOR_PASSWORD_HASH` and `MOWER_OPERATOR_SESSION_SECRET` configure
  the operator gate; both excluded from settings repr. Missing settings disable
  control. Current auth/owner/ledger require exactly one backend worker.
- Advertised rover capabilities are distinct from implemented HC controls.
  Native STM upload/ABORT/FINISH exist with strict per-action gates; live
  parameter apply, ESP OTA and RVM3 mission upload are not implemented yet.
- `rover_parameters.py` is the unchanged RCP1 reference from the handoff.
  `mower_parameters_service.py` adds null-aware drafts, strict exact 27-field
  validation, JSON/RCP1 import/export and canonical draft SHA256 / RCP1 CRC32.
  No operational defaults or hardware/commissioned fields are accepted.
- `mower_parameters_store.py` and migration 052 append PostgreSQL HC revisions.
  Per-key transaction advisory locks + expected_revision CAS protect concurrent
  editors, including first creation. Request replay is durable across restart;
  altered payload/expected revision with the same ID is ID_CONFLICT.
- `/api/mower/v3/parameters` is HC-only: public schema/read and pure same-origin
  validation/import, operator-authenticated save, GET-only unknown-save lookup,
  immutable history and exact saved-revision downloads. Read responses are
  no-store; no legacy context invalidation or rover/network side effects.
- Parameter editing does not require a connected/configured rover. HC draft
  save requires the independent HC operator configuration. Incomplete valid-
  shape drafts can be saved/exported JSON; binary export requires full validity.
- HC rover_key, package robot_id, draft_revision, draft_sha256 and rcp1_crc32 are
  not evidence of STM identity, native revision, firmware profile CRC or physical
  qualification. source is HC_DRAFT; active_configuration is null; live apply
  remains false even if a future identity capability turns true.
- Local/session-restored edits and lost-save IDs are never auto-submitted.
  UNKNOWN is reconciled by GET, conflict preserves local edits. Historical
  content can be brought into editing only explicitly; save creates a new row.
- `mower_firmware_service.py` / `mower_firmware_routes.py` add HC-only VG
  RFU2/RTE2 + actual ELF/RAM auditing using unchanged handoff references and
  bounded in-memory inputs. Preflight itself has no artifact persistence or rover
  transport. ABI1/ESP images are not connected; native STM session handling is
  a separate explicit workflow, never a side effect of preflight.
- GET `/api/mower/v3/firmware/releases` reads the independently reviewed
  server-side `static/mower-approved-releases.json` (empty by default).
  Same-origin POST `/api/mower/v3/firmware/preflight` accepts exact raw HC envelope
  (u32 image length + image + ELF), not the native rover upload format.
  One concurrent audit, bounded body/ELF tables and no-store responses.
- Full image/ELF hashes, firmware token, profile CRC and length must match a
  selected server-approved entry. No browser JSON/hash can approve a release.
  Structural success without that entry is not release approval. Even a
  reviewed match never proves installed profile agreement or hardware readiness;
  upload_available / hardware_qualified / persisted / rover_contacted stay false.
- File/release changes invalidate UI proof. Mount/selection sends only catalog
  GET, inspection is explicit, aborts on unmount and never auto-retries. Native
  image/ABORT/FINISH are a separate explicit retained-session workflow, not
  actions authorized solely by a passing preflight.
- `mower_firmware_staging.py`, `mower_firmware_store.py` and migration 053 add
  explicit authenticated same-origin POST `/api/mower/v3/firmware/jobs` using the
  same HC envelope plus required X-HC-Release / X-HC-Request-ID headers. New saves
  repeat full server-reviewed preflight; files and HC_STAGED job commit together.
  HC_STAGED / hc_job_id are not a native session, READY, update_id or installed
  image. No live identity dependency, rover request, reset or motion is issued.
- Both exact raw-file inputs are retained as PostgreSQL bytea, deduplicated by
  SHA256 of the entire HC envelope. Global transaction advisory lock serializes
  replay/dedup/quotas: 32 distinct artifacts, 256 MiB retained bytes, 1024 jobs.
  These are HC resource policies, not rover limits. Quota failure is atomic and
  never evicts old data; there is no browser delete/download/approval API.
- Job/request/history reads require operator auth, return metadata only and are
  no-store. History is bounded to 20 jobs; reads lazily create schema if needed.
  Identical request-ID replay survives HC restart; changed release/bytes conflict.
  Replay is historical review, not renewed catalog approval: responses explicitly
  use release_verified_at_staging, never release_verified as current authority.
- Lost/malformed DB acknowledgement is SAVE_UNKNOWN. Browser saves only bounded
  request correlation in sessionStorage before an explicit POST, never files or
  credentials. Remount/login may GET that request ID, but never auto-POST. A
  negative/mismatched GET keeps UNKNOWN and blocks new saves; known pre-write
  rejection alone can clear the intent. Corrupt/unavailable correlation storage
  fails closed. Server release catalog remains empty until independent review.
- `mower_firmware_updates.py`, `mower_firmware_sessions_store.py` and migration
  054 add authenticated current/request status GET and same-origin explicit
  POST `/api/mower/v3/firmware/jobs/<hc_job_id>/session`. Exact JSON requires
  request_id and confirm_runtime_discard:true. Preparation discards runtime
  mission/checkpoint/heading/manual; other actions require separate confirmation.
- Retained bytes/current catalog/ELF audit and live VG ABI2 identity/profile are
  rechecked before reservation. Exact layout H743_1M_QSPI2/capacity 524288 and
  explicitly null slots are required, not ordinary STM/GNSS/IMU/ARM readiness.
- Global advisory lock and unique active index commit CREATE_INTENT before one
  native POST `{v:3,request_id,esp_boot,target:"STM"}`. Result is ADMITTED,
  UNKNOWN or definite REJECTED via revision CAS. Replay never sends again.
  Native GET has no request_id, so lost admission cannot adopt a current job.
  Only a durably returned native ID can bind; 404/boot/endpoint change stays locked.
- Browser stores correlation before POST and restores via GET only. 2 Hz
  polling ages STM source evidence with HTTP transit and browser elapsed time;
  only bound fresh STM_LOADER/CAN-off/inhibited/error-NONE proves READY.
  COMPLETE additionally matches retained size/SHA/fw ID, not hardware qualification.
- Durable active attempts/storage failure block ordinary snapshot/commands/manual.
  Single-worker activity mutex guards final send/admission; active manual rejects
  create. Independent STOP remains separate and NOT_READY never means APPLIED.
  No observed state automatically clears active intent.
- Migration 055 / `mower_firmware_operations_store.py` persist one send intent
  per session/action IMAGE/ABORT/FINISH, max 3072 records, durable CAS/replay.
  A new ID cannot repeat a recorded action. Raw image repeats current catalog/
  bytes/ELF/profile audit before fresh READY; sends only exact RFU2 image with
  H743_1M_QSPI_REC2 / APP headers, never the identity layout literal or ELF/envelope.
- Authenticated same-origin POST `/firmware/sessions/requests/<session>/<image|abort|finish|verify-exit>`
  takes only request_id; GET `/firmware/operations/requests/<id>` reconciles.
  ABORT needs fresh bound nonterminal STM and keeps lock; FINISH needs fresh
  bound terminal quiescent loader + native can_finish. Neither auto-follows image.
- HC-only verify-exit requires retained non-rejected explicit FINISH, same ESP/
  profile/origin, unlocked IDLE and compatible fresh new ordinary STM boot/epoch,
  EMPTY/inactive mission/lease/progress, DISARMED or physical-input-only FAULT.
  HTTP lacks motor targets; zero-target authority is the native §17.8 IDLE
  restart barrier, not fabricated HC fields or physical-stop proof. GNSS/IMU/
  released ESTOP/mechanical stopped feedback are not FINISH/HC-exit gates.
- Exit proof insert + session closed/active=false are atomic; lost acknowledgement
  stays uncertain/GET-only. Old command/source objects are discarded; browser
  command correlation is cleared and cached pre-update boot cannot re-enable
  controls. No automatic ARM/START/claim/mission replay occurs. Initial boot is
  saved when known without making ordinary STM a preparation prerequisite.
- Read-only bring-up checklist: `scripts/check_mower_v3.py`; operational steps
  `docs/mower-v3-bringup.md`. First provisioning and actual hardware acceptance
  remain rover-owned; server release catalog is not auto-approved.

Reference tests and deployment notes: `docs/mower-v3-foundation.md`.
Parameter editor/storage/API details: `docs/mower-parameters-rcp1.md`.
Firmware preflight/release review/limits: `docs/mower-firmware-preflight.md`.
Firmware retention/job API/reconciliation: `docs/mower-firmware-staging.md`.
Native session/maintenance/UNKNOWN contract: `docs/mower-firmware-sessions.md`.

### Legacy and unchanged RTK integration

The canonical wire contract is `ROVER_HC_CONTRACT.md` v2.1.0. If this summary
conflicts with it, the root contract wins.

The mower is a first-class HomeControl subsystem, but HomeControl is not its
real-time controller. HC provides supervision, visualization, mission editing,
firmware staging and user commands. The ESP32 is the HC gateway. The STM32 owns
motor control, safety and autonomous movement.

Primary HC implementation:

- `ROVER_HC_CONTRACT.md`: canonical copyable HC–rover message contract
- `infra/backend/mower_service.py`
- `infra/backend/api_route_modules.py`
- `infra/backend/tests/test_mower_service.py`
- `infra/frontend/src/features/mower/MowerControl.jsx`
- `infra/frontend/src/features/mower/RtkEditor.jsx`
- `docs/mower-websocket-contract.md`
- `docs/mower-rtk-map-contract.md`
- `docs/mower-rover-mission-implementation-handoff.md`

Rover-side reference paths supplied by the rover project:

- `Core/Src/main.c`: STM32 real-time controller
- `tools/esp32_stm32_remote/esp32_stm32_remote.ino`: ESP32 gateway
- `docs/project_state.md`: rover integration state

These files live in the separate rover repository and are not vendored into HC.

## Ownership and architecture

```text
HC UI / backend
  | MQTT status and commands
  | WebSocket manual drive
  v
ESP32 remote
  | UART commands and telemetry (USART1: PB14 TX, PB15 RX)
  v
STM32 robot controller
  | FDCAN1 (PB8 RX, PB9 TX)
  v
VESC 1 left drive / VESC 2 right drive / VESC 3 blade
```

- Durable mission/map truth: HC until a mission is explicitly transferred and
  activated on the rover.
- Runtime motion and safety truth: STM32.
- Network/session gateway: ESP32.
- HC read model: `/api/context/mower`.
- HC must never bypass the ESP32 and talk directly to STM32.
- Loss of HC, Wi-Fi or MQTT must not defeat STM safety behavior.

## Safety principles

- Every MQTT command is published with `retain=false`, QoS 0, and a v2 JSON
  envelope containing a unique `request_id` and typed `value`.
- Missing or non-v2 `status/fw.contract` disables every control except online
  global stop, including manual WebSocket claim.
- Global stop is `homecontrol/mower/cmd/stop`; it is distinct from a WebSocket
  manual `stop`, which only zeros manual drive.
- Manual drive requires an accepted WebSocket claim and continuous drive or
  heartbeat traffic. ESP deadman timeout is 700 ms.
- HC never infers that publishing a command means it was executed; use
  `status/command` and subsequent robot telemetry as confirmation.
- Context reads and reconnect handling never publish `cmd/telemetry` as a side
  effect. The current rover maps it to persistent `TELEM FAST`, which can flood
  the shared UART and interfere with STM firmware-update acknowledgements.
- STM owns E-stop, bumper, lift, tilt, perimeter, motor and autonomous safety.
- Route play can cause motion and requires an explicit UI confirmation.
- Firmware activation is separate from upload/staging.
- `CAN_STARTUP_LISTEN_ONLY=1` is a rover-side safety setting. Motor testing may
  require the rover command `CAN NORMAL`; HC must not silently change it.

## Environment

- `MOWER_BASE_TOPIC`: default `homecontrol/mower`.
- `MOWER_REMOTE_URL`: default `http://mower-remote.local/`.
- Shared broker defaults: `192.168.1.133:1883` in the rover configuration.

## MQTT status contract

HC subscribes below `homecontrol/mower/#`. Required operational status topics:

- `availability`
- `status/fw`
- `status/link`
- `status/imu`
- `status/gnss`
- `status/route`
- `status/robot`
- `status/fault`
- `status/safety`
- `status/auto`
- `status/heading`
- `status/motor/1`, `status/motor/2`, `status/motor/3`
- `status/command`

The context response exposes `integration.missing_topics`, `stale_topics` and
`invalid_topics`. Stale thresholds are link 10 s, IMU 2 s, GNSS and motors 3 s;
retained status is never fresh. `integration.healthy` additionally requires a
compatible v2 contract, valid payloads, availability online, STM alive and CAN
alive.

## MQTT command contract

Commands are published below `homecontrol/mower/cmd/` with QoS 0 and never
retained. Every payload is `{"request_id":"hc-...","value":...}`:

- `stop`, `arm`, `disarm`, `fault_clear`, `clear_estop`, `safety_reset`
- `telemetry`, `blade_rpm`, `blade_stop`
- `heading/north_set`, `heading/auto_north`, `heading/cancel`
- `heading/target_deg`, `heading/relative_deg`, `heading/assist`
- `route/record`, `route/clear`, `route/play`, `route/stop`

HC API command names differ slightly for heading commands; see `COMMANDS` and
`VALUE_COMMANDS` in `mower_service.py`.

## Manual WebSocket contract

- URL: `ws://<ESP address>/ws`
- Subprotocol: `homecontrol.mower.manual.v1`
- Claim: `{"type":"claim","client":"hc-...","protocol":"homecontrol.mower.manual.v1"}`
- Drive: `{"type":"drive","seq":1,"forward":1200,"turn":-250}`
- Keepalive: `{"type":"heartbeat","seq":2}`
- Local stop: `{"type":"stop","seq":3}`
- Release: `{"type":"release","seq":4}`

See `docs/mower-websocket-contract.md` for session and disconnect behavior.

## HC API endpoints

Read:

- `GET /api/context/mower`
- `GET /api/mower/state`
- `GET /api/mower/route`
- `GET /api/mower/firmware/status`

Mutation:

- `POST /api/mower/command`
- `POST /api/mower/route/<action>`
- `POST /api/mower/firmware/upload`
- `POST /api/mower/firmware/<activate|reset>`
- mower-scoped notes endpoints under `/api/mower/notes`

## UI ownership

- Mower tab: live status, safety, motors, GNSS/RTK, heading, legacy route,
  manual WebSocket control, global emergency stop and firmware staging.
- RTK Editor tab: boundaries, exclusion zones, coverage planning, simulation
  and mission artifact generation.
- Do not merge the full editor back into the operational Mower tab.

## Context payload

`/api/context/mower` contains:

- normalized `status` groups and `motors`;
- normalized `rtk_pose` for map rendering;
- `manual_control` URL, protocol and deadman timeout;
- `integration` architecture, ownership, topic health and transport metadata;
- raw monitored topics for diagnostics.

## Verification

```bash
cd infra/backend
python3 -m unittest tests.test_mower_service
```

Frontend:

```bash
cd infra/frontend
npm run build
```

## Do not

- Do not publish motion or command topics retained.
- Do not send manual drive through MQTT.
- Do not treat HC as a hard real-time or safety controller.
- Do not bypass the ESP session owner for firmware, route or manual operations.
- Do not equate manual stop with global emergency stop.
- Do not start autonomous movement merely because a mission was uploaded.
