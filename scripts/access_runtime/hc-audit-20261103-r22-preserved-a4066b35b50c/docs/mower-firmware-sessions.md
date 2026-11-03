# Mower native STM update lifecycle — 2026-10-10

This connects explicit session creation, single-send raw image, ABORT, FINISH
and separately verified HC exit to retained HC_STAGED firmware jobs. Legacy
Mower and RTK Editor are unchanged. No synthetic release is production-approved.

## Operator workflow and destructive boundary

1. Independently review the server release catalog; preflight and retain the exact
   image/ELF pair in HC as described in `mower-firmware-staging.md`.
2. Log in, select a retained job and inspect current native identity/status.
3. Explicitly confirm preparation **discards runtime mission, checkpoint, heading
   and manual session**, and enters maintenance. The browser closes manual control
   before attempting create; the backend independently rejects an active owner.
4. The backend rechecks retained bytes, current catalog/ELF audit, live profile,
   exact VG capability and unlocked IDLE, commits durable send intent, then issues
   exactly one native POST. Mount/login/polling never creates a session.

Every action requires separate confirmation and fresh prerequisites. FINISH
admission does not unlock HC; a separate HC-only check verifies return.
Neither 202 admission, TRIAL, a byte counter nor APP ACK is installation
success. No ARM, START, reset, firmware approval or legacy fallback is performed.

## HC API

All routes return no-store/nosniff and require the independent HC operator cookie:

- `GET /api/mower/v3/firmware/session`: observe the durable active HC attempt,
  or current native identity/update status when no HC attempt is active.
- `GET /api/mower/v3/firmware/sessions/requests/<request_id>`: reconcile that HC
  request. `found:false` cannot prove an in-flight reservation will not commit.
- Same-origin `POST /api/mower/v3/firmware/jobs/<hc_job_id>/session`: exact JSON
  `{request_id, confirm_runtime_discard:true}`, at most 1024 unencoded bytes.
  IDs are bounded ASCII letters/digits/underscore/hyphen, 1..64 characters.
  HC errors marked `mutation_sent:false` occur before native create; generic
  server/gateway errors must not be interpreted as proof of non-delivery.
- `GET /api/mower/v3/firmware/operations/requests/<request_id>`: durable native
  action or HC exit-proof lookup. Negative/mismatched GET never permits resend.
- Same-origin `POST /api/mower/v3/firmware/sessions/requests/<session_request_id>/<image|abort|finish|verify-exit>`:
  exact `{request_id}` JSON, <=1024 bytes. Image uses the retained session job,
  not browser files/hash/metadata; verify-exit sends no native mutation.

Native transport permits only GET `/api/v3/identity`, GET `/api/v3/update`, GET
`/api/v3/update/<nonzero-uppercase-32-hex-id>` and POST `/api/v3/update` for this
slice. Create sends exactly `{v:3, request_id, esp_boot, target:"STM"}`. Separate
narrow binary transport permits only that ID's /image, /abort and /finish, no
ACTIVATE/legacy/raw UART. Image is exact raw RFU2 with Content-Length/full
lowercase SHA/fw token/profile/contract, **image layout H743_1M_QSPI_REC2** and
slot APP; identity layout H743_1M_QSPI2 is not the image-header literal.
ABORT/FINISH use empty bodies. No redirects/proxies or auto-retry; URLs ignored.

Create requires advertised `stm_remote_update:true`, service ABI 2,
`H743_1M_QSPI2`, 524288-byte STM image capacity, nonzero profile CRC and explicitly
null confirmed/inactive slots. Current reviewed image profile must match the
authenticated identity. Ordinary STM responsiveness, GNSS, IMU, ARM and the
ordinary compatibility/conformance flags are not invented preparation gates.

## Durable intent and UNKNOWN

Migration 054 exactly matches `mower_firmware_sessions_store.py` bootstrap SQL.
`hc.mower_firmware_session` references the immutable HC job and retains the request,
origin fingerprint, expected ESP boot/profile, native ID if admitted, timestamps
and revision. It stores no credential or image duplicate. Staging initializes first.

The global transaction advisory lock `hc.mower.firmware.native-session` and a
partial unique index admit only one active attempt. At most 1024 retained
attempts are allowed, with no automatic eviction. Reservation commits
`CREATE_INTENT` / revision 1 **before** the native POST; a single conditional
transition records `ADMITTED`, `UNKNOWN` or `REJECTED` / revision 2. Replays of
the same request/job return retained evidence without any native resend, even
after restart or catalog change. Changed job under the same ID is ID_CONFLICT.
Only a definite create rejection or separately verified HC exit releases the
active lock. Initial ordinary STM boot, if known, is retained at create.

A lost create reply, malformed admission, uncertain delivery or lost database
acknowledgement stays active. An interrupted CREATE_INTENT is not retried. The
native GET schema contains **no request_id**: an arbitrary current native job,
even on the same boot, must never be adopted after losing the returned ID.
UNKNOWN remains unbound, and a missing native job/changed boot/changed endpoint
does not authorize forgetting the attempt or making a replacement.

The browser persists only bounded `{jobId, requestId}` correlation in
sessionStorage before its explicit POST, never files/secrets. It restores via
GET only. Negative, mismatched or unavailable lookup keeps the pending intent.
A correlated durable attempt can clear browser uncertainty, but an active server
attempt still blocks controls. Corrupt/unavailable storage fails closed.
Native actions persist separate bounded `{action,sessionId,requestId}` browser
correlation, restored GET-only. Separate POST and non-overlapping 2 Hz GET flights
keep status available during admission. Only matching durable action/exit
evidence clears uncertainty; login/remount never submits any mutation.

## Status evidence and control isolation

Authenticated status polling is 2 Hz, non-overlapping, bounded and aborted on
auth loss/unmount. Backend validation covers the complete native update schema,
nullable evidence, counters/size, roles, tokens, slots and service boot. Only
whitelisted diagnostics are returned. HTTP transit delay is added to source age;
browser-local elapsed time expires evidence during a stalled connection.

Binding requires the durably returned native ID, STM target, same expected
origin/ESP boot/profile, VG identity and explicitly null VG slots. An origin
fingerprint is a fail-closed configuration guard, not physical rover identity;
token rotation alone does not change it. Freshness requires valid STM source
age at most 2000 ms. Only a fresh bound STM_LOADER, locked, CAN inactive, outputs
inhibited and error NONE can prove loader READY. Nullable physical data is unknown,
not false, and loader readiness is not a measured physical stop.

Observed COMPLETE additionally requires exact retained image size/full SHA/fw ID.
It is observed loader commit evidence, not proof this HC uploaded the image or
performed hardware qualification. `hardware_qualified` and
`normal_mode_verified` remain false. Last observation may remain visible as
historical diagnostic data, but does not retain READY/install authority.

Durable active intent blocks ordinary snapshots/commands/manual acquisition,
including after HC restart. Storage failure also fails closed. A single-worker
activity mutex protects the last ordinary send boundary and create admission;
create refuses a live manual owner. Do not scale workers/replicas without shared
auth/manual/activity ownership. Independent authenticated STOP bypasses these
ordinary guards; native NOT_READY is not APPLIED and never triggers ABORT.

Even COMPLETE, ABORTED or unlocked IDLE observation does **not** auto-clear an
active attempt. Explicit FINISH needs fresh bound locked STM_LOADER, CAN-off/
inhibited, terminal COMPLETE/ABORTED/ERROR and native can_finish=true. ABORT is
separate, with fresh bound nonterminal STM evidence; lock stays, confirmed commit
cannot be undone. Neither action auto-follows upload/lost response.

## Durable actions and separately verified exit

Migration 055 matches `mower_firmware_operations_store.py` bootstrap exactly.
It upgrades 054's PostgreSQL cross-column active CHECK to include closed, without
deleting data, and adds operation/exit tables. Unique session/action intent commits
before one native send and advances once to ADMITTED/UNKNOWN/REJECTED. Maximum
3072 action rows, no eviction. New request IDs cannot repeat a recorded action.
Image rechecks current catalog/bytes/ELF before fresh READY and reservation;
database wait cannot renew source evidence. No ELF/envelope/base64 is forwarded.

HC-only verify-exit requires a durable non-rejected explicit FINISH intent,
same expected ESP boot/profile/endpoint, compatible VG identity and unlocked
current IDLE without another job. Ordinary STATE must be <=1500 ms, with boot
different from finish service boot and initial ordinary boot if known. Nonzero
epoch, DISARMED/no fault or only physical-input FAULT corroborated by safety mask,
EMPTY/null mission, zero progress/lease/input and no arm/start/resume are required.
GNSS/IMU/mechanical stopped feedback/released ESTOP are not invented gates.
HTTP STATE exposes no motor targets: zero-target authority is the native §17.8
unlocked IDLE restart barrier, combined with new fresh EMPTY state. This explicit
trust boundary is not HC-measured physical stopping or hardware qualification.

Old process-local command/source objects are discarded before atomic exit proof
insert plus active=false/closed=true. Lost DB acknowledgement stays uncertain;
exit-request GET/exact replay returns historical proof, not a new native action.
Browser clears old command correlation and waits for snapshot from the proved
new boot before controls. Subsequent operation needs fresh normal evidence and
explicit operator request. No forget/unlock shortcut, auto ARM/START/manual claim.

## Verification

```sh
cd infra/backend
python3 -B -m unittest discover -s tests -p 'test_mower*.py'
python3 -B -m unittest tests.test_context_service_contract tests.test_command_service tests.test_api_route_modules
```

Opt-in SQL tests use `MOWER_TEST_POSTGRES=1` with the existing private
`DATABASE_URL`. Only `pg_temp` tables and force-rollback transactions are used;
production artifacts/jobs/sessions are never seeded or deleted. Tests cover
committed-before-send intent, single-active admission, CAS/restart replay,
lost acknowledgements, boot/profile/endpoint mismatch, unknown/unbound status,
404 retention, complete-schema validation, transit/cached ageing, ordinary
last-send guards, independent STOP, authentication/origin and revoked approval.

`npm run test:mower` verifies explicit-only create, bounded stored correlation,
double-click/lost/malformed admission, GET-only restoration, cached diagnostics,
null/stale/TRIAL evidence and independently gated image/ABORT/FINISH/HC-exit UI. Docker frontend
build runs these tests before compilation. Synthetic peers are not hardware
acceptance evidence. Bring-up: `mower-v3-bringup.md`. Real FW compatibility,
installation qualification, power cuts, timings and physical stopping still
need commissioned hardware tests. ESP OTA, RVM3 mission upload and live
parameter apply remain outside this integration.

Earlier preparation-only verification 2026-10-10: 174 Mower backend tests passed, including the
opt-in real PostgreSQL temporary-table suites; 15 shared API/context/command
regressions and all 46 frontend tests passed. Production frontend/backend builds
passed. Both nginx configurations validated, both frontend/proxy paths served
the new UI and rejected unauthenticated session GET/create with 401/no-store.
Migration 054 initialized an empty table; production retained 0 session intents,
0 artifacts and 0 jobs. Health reported DB/MQTT OK, rover remained UNCONFIGURED,
and no live rover mutation or hardware qualification was performed. Original
MowerControl, inactive Legacy preview and RTK Editor checksums stayed unchanged.

Full lifecycle verified/deployed 2026-10-10: 198 Mower backend tests (including
real pg_temp/rollback SQL), 15 shared API/context regressions and all 50 frontend
tests passed. Production frontend/backend builds passed. Migration 055 ran with
0 retained session/operation/exit/artifact/job rows; no fixtures or approvals
were inserted. Both nginx configurations validated; both frontend/proxy paths
served image/ABORT/FINISH/HC-exit UI and denied unauthenticated action POST/lookup
GET with 401/no-store. Health DB/MQTT OK. The read-only bring-up check reported
rover and HC operator unconfigured, empty release catalog. No real rover
mutation, reset, firmware transfer or hardware qualification occurred. Legacy/
RTK checksums and dependency versions remained unchanged. SQL lock wait cannot
renew either loader send proof or the normal STATE proof before HC exit commit.
