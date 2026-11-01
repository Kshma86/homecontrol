# Mower v3.1 foundation — 2026-10-09

The Mower navigation entry now opens the new v3.1 page. Mower Legacy
opens a static preview of the old sections and fields, with all controls disabled
and no network effects (including map/notes loading). Values are unknown, not
historical or live telemetry. `MowerControl.jsx` is preserved unchanged and
not imported by application navigation. `RtkEditor.jsx`, the legacy context and
legacy backend APIs are intentionally retained for the unchanged RTK editor.
This does not globally disable all legacy backend routes.

## Implemented

- A dedicated backend HTTP/WS transport using the provisioned origin and Bearer
  token; no redirects, proxy forwarding or legacy fallback. Snapshot reads never
  mutate the device.
- Bounded JSON decoding, exact types, required fields, source boot matching and
  whitelisted browser diagnostics.
- Uncached `/api/mower/v3/snapshot` endpoint and 2 Hz non-overlapping frontend
  polling, paused while hidden and aborted on unmount.
- STM state, stopped/armed evidence, masks, epoch, mission/store/progress,
  firmware/profile/boot identity and advertised capabilities.
- Monotonic freshness tracking: repeated/older source sequences cannot renew
  freshness, and browser-local ageing expires evidence during HTTP silence.
- Separate mower operator authentication: one-hour signed HttpOnly/SameSite
  cookie, origin checks before mutation/WS upgrade, bounded login attempts and
  revocable sessions. Viewing the tab does not log in or claim control.
- Explicit `arm`, `disarm`, `pause`, `reset_fault`, `heading_set`, `start`,
  `resume` and dedicated STOP. Start/resume reference the mission already
  reported by the STM; this slice does not upload/compile missions.
- Correlated STM ACK is required for APPLIED. Admission is PENDING; after
  1500 ms without an ACK the result is UNKNOWN. Reconciliation uses GET only,
  never a repeated mutation. Tab remount restores request IDs from sessionStorage.
- STOP bypasses boot/epoch/freshness/profile preflight and ordinary ledger
  saturation. A native `503 NOT_READY` is an explicit rejection, not APPLIED,
  and does not translate into an update ABORT.
- Backend manual WS relay with one owner, matching lease, full integer frames,
  10 Hz held deadman, fresh latest-only forwarding and no replay/reconnect.
  Browser receive timestamps, 512-byte messages, four queued arrivals and
  20 messages/s bound buffered traffic. Frames older than 100 ms are dropped.
  Deadman release sends full zero; disconnect sends only matching lease release,
  never global STOP. Native 350 ms lease remains the safety backstop.
- Manual blade target stays zero until a verified cutter profile/feedback UI is
  implemented.
- HC-local RCP1 editor: exact reference schema/codec, partial drafts, PostgreSQL
  immutable revisions/CAS/replay, import/export and saved-draft differences.
  See `mower-parameters-rcp1.md`. No live parameter API is invented or enabled.
- HC-only VG firmware preflight: RFU2/RTE2 plus actual ELF/RAM audit, full hash
  and embedded metadata matching against an independently reviewed server-side
  release catalog. Preflight itself has no rover contact or native mutation.
  See `mower-firmware-preflight.md`; structural verification is not release
  approval, installed-profile agreement or hardware qualification.
- Durable authenticated HC firmware retention and immutable HC_STAGED jobs;
  exact files deduplicated in PostgreSQL, request replay and quota admission
  serialized, lost replies reconciled with GET only. See `mower-firmware-staging.md`.
  HC_STAGED is not a native update_id, READY or installation result.
- Explicit VG native STM session create and 2 Hz GET-only observation, with
  durable pre-send intent, strict loader evidence, UNKNOWN/unbound recovery and
  fail-closed ordinary control isolation. See `mower-firmware-sessions.md`.
  READY-gated raw RFU2 upload, explicit ABORT/FINISH and separate HC-only
  verified normal-mode return are implemented. Bring-up: `mower-v3-bringup.md`.

## Configuration

Supply `MOWER_V3_REMOTE_URL` as a fixed HTTP(S) origin without userinfo, path,
query or fragment. Supply the authorized `ROVER_API_TOKEN` (64 hex characters)
privately to the backend deployment. Compose passes both settings through.
Do not paste the token into the browser, chat, CLI flags or logs. Missing or
invalid configuration leaves the page UNCONFIGURED and performs no rover GET.
The legacy MOWER_REMOTE_URL setting is independent.

To enable browser controls, separately provide `MOWER_OPERATOR_PASSWORD_HASH`
(Werkzeug-generated scrypt or PBKDF2-SHA256 hash) and
`MOWER_OPERATOR_SESSION_SECRET` (32 random bytes encoded as 64 hex characters).
Do not reuse the rover token as a browser password/session secret. Provision
secrets privately, keep `$` characters in password hashes literal when loading
Compose configuration, and do not paste passwords/hash/secret values into chat
or logs. Use HTTPS when authenticating outside a trusted local network.
Missing authentication settings leave all mutation/WS access disabled.
The frontend/proxy preserve the original Host including its port, so same-origin
checks also work when HC is opened through the directly published frontend port.

This first control slice uses the existing **one-worker** Gunicorn deployment:
operator sessions, the manual owner and command history are process-local.
Restart requires operator login again. Do not scale backend workers/replicas
without shared session/owner/command persistence. The bounded ledger retains
128 results and 512 retired request fingerprints; it is not a durable audit or
an unlimited idempotency store. Retired IDs return UNKNOWN/GET reconciliation,
not another POST. Browser code never resubmits a saved mutation across restarts.
Legacy APIs remain separate and unchanged; the new operator gate is not a
global authentication retrofit for all HomeControl or legacy rover endpoints.

The package's host fixtures are synthetic; actual rover deployment and hardware
acceptance still require the separate rover workflow. No physical rover access
is needed for the tests below.

## Verification

Backend, with the repository's dependencies available:

```sh
cd infra/backend
python3 -B -m unittest discover -s tests -p 'test_mower*.py'
python3 -B -m unittest tests.test_context_service_contract tests.test_command_service tests.test_api_route_modules
```

Frontend:

```sh
cd infra/frontend
npm run test:mower
npm run build
```

The frontend Docker build also executes the mower tests before Vite compilation.
The API route tests use an isolated Flask app and a deliberately failing legacy
service getter, proving the v3 snapshot cannot invoke legacy integration.
WebSocket integration tests use an isolated Flask server on an ephemeral
loopback port and synthetic auth/native responses, never the production app or
a physical rover. Hardware acceptance (including deadman/lease timing under
network failure) is still required before real actuation.

Control-slice verification on 2026-10-09: 106 focused/regression backend tests
and 10 frontend model/control tests passed; production frontend/backend images
built and were deployed. Health reports DB/MQTT OK. Both direct frontend and
proxy paths reject unauthenticated command/STOP with 401 while preserving Host
ports; the production Gunicorn manual upgrade also rejects unauthenticated
access with 401. The v3 rover connection and operator settings remain
UNCONFIGURED; no physical rover command or hardware test was performed.

## Next implementation slices

1. Commissioned-rover verification of the VG update/restart flow and hardware
   acceptance. HC implements session/status/raw RFU2/ABORT/FINISH/verified exit;
   ESP OTA, motion qualification and first provisioning are separate work.
2. Native parameter active-readback/live apply only after a matching rover
   contract becomes available. HC editor/draft storage is already implemented.
3. Separate later RTK migration: geometry validation, ECEF/ENU and RVM3 compiler.

The baseline specification and its VG/RCP1 overrides remain in the supplied
handoff ZIP at the repository root. Neither `conformant` nor runtime capability
is inferred from a passing HC test.
