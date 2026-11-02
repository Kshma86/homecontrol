# HC RCP1 parameter editor — 2026-10-09

The new Mower page includes a 27-field parameter editor that does not require a
connected rover. It edits **HC drafts**, never an active/commissioned controller
configuration. The legacy Mower archive and RTK Editor are unchanged.

## Operator workflow

1. Open Mower and find Roverparaméterek · RCP1.
2. Enter a HC rover key (1–32 ASCII letters, numbers, `_`, `-`) and explicitly
   load its draft. An unused key opens an empty revision-0 template.
3. Edit the grouped fields or import JSON/RCP1. All operational values initially
   are null/unknown; version 1 is the only supplied default. Missing array
   elements can remain null. The robot_id inside the parameter package is
   separate from the HC storage key; neither proves the physical STM identity.
4. Review validation and differences from the loaded HC revision. Units are
   explicit, including mm/s, millidegrees, scaled quaternion and gear ratio.
5. Sign in as HC operator to save to PostgreSQL. **Saving does not require
   MOWER_V3_REMOTE_URL or ROVER_API_TOKEN**, but requires the independent HC
   operator settings documented in `mower-v3-foundation.md`. No auth bypass is
   provided when these are absent. Editing/validation/import/local JSON export
   remain available without login.
6. Save incomplete, structurally correct drafts for later work. A complete valid
   saved draft additionally permits a 256-byte RCP1 download. JSON export can
   contain nulls; RCP1 cannot. Import only replaces local editing after explicit
   confirmation, never saves or applies by itself.
7. Historical revisions remain unchanged. Bringing one into the editor and
   saving creates a new revision, not an overwrite/rollback of history.

The sessionStorage cache preserves local work and unresolved save IDs within
the browser tab. It is not the durable source of truth and does not certify a
save. After lost replies, use Mentés egyeztetése: GET the stored request ID.
There is no automatic POST retry. Until the save is confirmed, the editor blocks
further saves/target changes but preserves local edits and JSON export.

CAS conflicts preserve local edits and do not update expected_revision behind
the operator's back. Export local JSON before explicitly reloading a conflicting
newer HC revision if the edits need to be kept/merged.

## Contract and validation

Authority: handoff ZIP `docs/HC_PARAMETERS_RCP1.md`,
`docs/HC_PARAMETER_MANAGEMENT.md`, `tools/rover_parameters.py` and its null-only
template. `infra/backend/rover_parameters.py` is a byte-for-byte copy of that
reference, SHA256:

`0b8b8081a3918af1dd3600de3e08184c9e1b70afaf6fc9c789d1376344a7f4fa`

The complete codec/schema is unchanged. HC adds partial-draft validation: exact
27 keys, version 1, strict types/ranges and fixed-length arrays, permitting null
operational values/items without substituting defaults. Missing keys, unknown
keys, hardware/commissioning fields, bool-as-number, floating point (including
`500.0`), duplicate JSON keys and nonfinite values are rejected. Request/import
bodies are at most 16 KiB, UTF-8 JSON nesting at most six levels. Cross-checks
cover motor ±1 directions, mechanical/electrical blade limits and quaternion
norm ±0.1%; known invalid cross-fields cannot be saved even in a partial draft.
Complete drafts pass the original reference validator before RCP1 export.

Binary import verifies exact size/header/version, CRC32 and full byte-for-byte
canonical re-encoding, including reserved bytes/padding. A repaired CRC does not
make nonzero padding valid. A zero CRC is not interpreted as missing data.

`draft_sha256` hashes canonical JSON (including nulls for incomplete drafts).
`rcp1_crc32` is available only for complete valid parameter data and is **not**
firmware `profile_crc`, `X-Profile-CRC32`, board identity or commissioning proof.
`draft_revision` is HC-local, not an active rover revision.

## Storage and routes

Migration: `infra/db/052_mower_parameter_drafts.sql`. Matching lazy bootstrap
creates only `hc.mower_parameter_revision`; it does not change existing domain
tables. Every save appends an immutable revision with expected_revision,
request_id, full JSON, draft SHA256 and timestamp. Transaction-scoped PostgreSQL
advisory locking serializes first creation and later CAS saves per HC rover key,
including through the existing transaction-pooling connection. Unique
`(rover_key, revision)` and `(rover_key, request_id)` constraints retain history
and durable idempotency after backend restart. Exact replay returns its original
revision; altered request ID/body conflicts. GET history is bounded to 20
revisions, rover catalog to 100 keys; a known key is always directly addressable.

HC-only API prefix: `/api/mower/v3/parameters`:

- GET `/schema`, `/drafts`, `/drafts/<key>`, `/drafts/<key>/history`.
- GET `/drafts/<key>/revisions/<revision>` and
  `/drafts/<key>/revisions/<revision>/export.json|export.rcp1`.
- POST `/validate` and `/import` are pure, same-origin operations; no storage or
  device mutation. Import accepts application/json or application/octet-stream.
- POST `/drafts/<key>` requires same-origin operator login and exactly
  `{request_id, expected_revision, parameters}`. Save performs no rover I/O.
- GET `/drafts/<key>/requests/<request_id>` reconciles a possibly lost save.

All responses are no-store/nosniff. Read access follows existing HC state-view
semantics; operator authentication gates durable writes. There is no delete or
apply endpoint. This separate draft read model does not mutate/invalidate legacy
mower/context or RTK state. DB failures are sanitized; uncertain save outcomes
are `SAVE_UNKNOWN`, not invented success.

## Unavailable by design

No parameter HTTP setter/ACK contract is provided by the rover package. Live
apply stays unavailable even if identity later advertises runtime_parameters;
implementing it requires the agreed native API and verification, not just a
capability flag. Active configuration/readback is unknown, so active-rover
comparison is unavailable. The UI instead labels comparisons explicitly as
differences against the loaded **HC draft**.

Correct data is not proof of geometry, motor direction, braking, calibration or
physical safety. This slice cannot assert inhibited/disarmed/stopped hardware,
commit live parameters, commission, ARM, START, claim manual, run firmware OTA
or write raw UART. Firmware update and parameter management remain separate.

## Verification

```sh
cd infra/backend
python3 -B -m unittest tests.test_mower_parameters tests.test_mower_parameters_routes tests.test_mower_parameters_postgres
```

The SQL integration tests are opt-in with `MOWER_TEST_POSTGRES=1` and
`DATABASE_URL`. They use only `pg_temp` tables inside a force-rollback
transaction; they never populate/delete production draft data. They verify real
queries, replay/restart, CAS/ID conflicts, history, multiple keys and that the
transaction-scoped lock excludes another connection.

```sh
cd infra/frontend
npm run test:mower
npm run build
```

Frontend tests include null-safe form conversion, strict integer text, exact
save correlation, corrupted cache handling and React rendering against the
actual reference schema. A deterministic hook/effect harness checks same-content
draft loading, persistence of uncertain save IDs, GET-only recovery and
preservation of edits/expected revision on conflict. The schema fixture is
checked against the Python reference by backend tests. Physical rover acceptance
is intentionally outside this HC-only slice.

On 2026-10-09, 134 focused/regression backend tests (including opt-in real
PostgreSQL temporary-table checks) and 25 frontend tests passed. Frontend/backend
production images built successfully. The existing npm audit warnings remain
(1 moderate, 4 high); dependency versions were not changed by this slice.

Deployment smoke checks passed through the HC proxy: schema/no-store, empty
PostgreSQL catalog, absent-key revision-0 template, offline validation,
unauthenticated save rejection (401), absent live-apply route (404), and DB/MQTT
health. Only the new draft table was bootstrapped; no production parameter
revision/test fixture was saved and no rover operation was sent. Operator/rover
connection provisioning remains separate from this deployed editor.
