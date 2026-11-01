# Mower subsystem scenarios

## HC_BRINGUP: current default, native metadata lock is diagnostic

Given the exact reviewed HC_BRINGUP firmware with locked ERROR/METADATA_ERROR,
default Mower mounts only its read-only identity/state/update/health view.
Fresh native DISARMED/EMPTY with matching boots and progressing source_seq
means HC communication works, not physical stop or commissioning. Null safety
and VESC evidence stay unknown; can_finish and all write capabilities false.
No native POST (including STOP), manual socket, unlock/bootstrap or retry.
Read-only deployment gate rejects authenticated native writes before I/O/DB
reservation even when explicitly choosing the preserved operational view.

## HC_BRINGUP: identity, freshness, outages and separate drafts

Wrong firmware/mode/schema or mixed boot responses cannot assert current state.
Source age includes all subsequent GET wait and HC/browser elapsed time.
Repeated source_seq cannot renew it, old seq is stale, regressing epoch invalid,
uint32 wrap advances, and new boot resets binding without inheriting authority.
After 1500 ms or HTTP outage current state is unknown. Health expires at 3000 ms,
including repeated published_ms; unavailable sensors are never healthy zeros.
Native update lock never bypasses a durable HC_UPDATE_PENDING/storage outage.
Parameter editor is a separate HC-only draft; no service STAGED import/apply.

## First-install service: explicit read-only connection

Given the historical standalone LAN service firmware, explicitly selecting its view performs service
GET status/parameters only, no operational/legacy polls or control mounting.
Only fixed provisioned origin and private credential are used; missing token
does not cause discovery or a tokenless rover poll. Explicit view change mounts
the preserved operational adapter, never maps service PING to v3 STATE.

## First-install service: strict evidence and local expiry

Given matching fresh service UID/FW with exact ABI1 and motion/applied/OTA false,
HTTP is shown separately from current STM. Aged/disconnected/changed peer,
invalid/missing flags, auth failure, malformed JSON or maintenance lock cannot
assert current parked/disarmed/inhibited evidence. Historical rows are labelled.
After 3000 ms including transit/elapsed time, current flags expire even without
a new response. Revision never renews source evidence. Tokens are stripped.

## First-install service: stored is not applied

Given a complete reference-valid saved RCP1 with matching CRC, the view shows
storage/revision/readback only, never ACTIVE/APPLIED/motion qualification or
automatic import into HC drafts. EMPTY/revision=0 does not create defaults.
GET is the sole device action on mount/refresh/reconnect. No parameter POST,
firmware update, ARM, manual socket or commissioning occurs.

## New v3 tab: inactive legacy

Given the user opens `mower-legacy`, HC displays the original sections/fields as
a static preview, including diagnostics and route fields formerly conditional
on live state. All controls (including STOP, uploads, links and notes) are
disabled, and values are explicitly unknown, not historical or live telemetry.
HC does not mount `MowerControl`, the live map or notes widget, poll endpoints,
load map tiles, claim a session or open a WebSocket. The original source is
preserved. RTK Editor is unchanged in this stage.

## New v3 tab: missing deployment

Given MOWER_V3_REMOTE_URL or ROVER_API_TOKEN is absent, the new tab shows that
the backend is unconfigured, makes no rover request and leaves state/stopped/
armed unknown. It does not discover credentials or use a legacy fallback.

## New v3 tab: stale or repeated snapshots

Given the same source_seq is repeatedly returned with source_age_ms zero, HC
keeps growing effective age from the original reception. After 1500 ms the UI
shows unknown current state, retaining the last observation only as historical
diagnostics. Network silence also expires source evidence locally.

## New v3 tab: maintenance and capability

Given identity.update_locked=true, HC shows update mode and does not query
ordinary state. An unknown ABI/layout, wrong VG capacity, non-null VG slots,
zero profile or disabled capability cannot advertise supported STM updating.
Advertised support does not create an implemented UI control or motion grant.

## New v3 tab: authentication and source identity

Given HTTP auth failure, redirect, malformed JSON, missing/null evidence or
identity/state boot mismatch, HC shows unavailable/invalid evidence. Tokens and
remote response bodies never appear in errors. Read paths issue only v3 GETs.

## New v3 tab: unauthenticated and cross-origin control

Given no valid operator cookie or a missing/foreign Origin, command/STOP and
manual upgrade are rejected before rover contact. A revoked/expired cookie
also ends an existing manual relay; a new backend process requires login.

## New v3 tab: command admission and uncertain execution

Given POST admission 202, the UI shows PENDING, not APPLIED. Only the matching
request/command/STM boot ACK proves execution. After 1500 ms or a lost reply it
shows UNKNOWN and performs GET reconciliation only. Exact repeated IDs are not
resent while retained; altered payloads conflict. Restored browser history never
resubmits a mutation, including after backend restart.

## New v3 tab: STOP while stale or update-locked

Given stale/missing STM evidence or a saturated ordinary command ledger, a new
authenticated STOP still uses only `{v,request_id}` and the separate native
STOP endpoint. A native 503 NOT_READY does not prove stopped and never triggers
ABORT. Missing deployment/auth settings cannot send a STOP.

## New v3 tab: deadman, backlog and lease release

Given a fresh IDLE/stopped source, an authenticated operator can explicitly
claim the exact boot/epoch. No GNSS requirement is invented by HC. Native claim
supplies lease/limits. Full frames at 10 Hz require held deadman and blade zero;
old arrivals (>100 ms), overlarge/binary/duplicate/nonfinite payloads and
non-increasing sequences cannot become motion. Only latest unsent held-drive
is forwarded; a deadman-false zero discards earlier pending motion.

Given release, blur, hiding the tab, socket failure or invalid source/session,
HC stops held sends and zeros/releases the matching lease where possible. It
never automatically reconnects/reclaims or uses global STOP on tab unmount,
since AUTO ownership might already have changed. Native 350 ms lease remains
responsible for a stalled HC; the UI does not claim hardware timing is verified.

## New v3 tab: offline parameter editing

Given no rover URL/token or runtime parameter capability, the RCP1 editor still
loads the exact null-only schema, validates and imports/exports HC drafts. HC
save requires operator login, not fresh STM state. The local rover key is not
inferred from a boot ID or mistaken for physical identity.

## New v3 tab: partial drafts and strict reference validation

Given unknown operational values, nulls remain unknown, not false/zero/default.
Structurally correct partial drafts can be saved and JSON-exported. Only complete
reference-valid data permits RCP1 export. Invalid types, floats, bool-as-number,
extra/commissioning fields, directions, blade cross-limits or quaternion norm
cannot be saved. Repaired binary CRC with nonzero reserved bytes still rejects.

## New v3 tab: concurrent HC draft saves and uncertain results

Given two editors loaded revision N, the first save appends N+1; the second
expected=N receives REVISION_CONFLICT without losing its local edits or
overwriting history. Exact repeated request ID returns the original revision
after restart; changed content conflicts. Lost reply is UNKNOWN, with persisted
browser request metadata and GET-only reconciliation, never automatic POST.

## New v3 tab: data is not activation

Given a valid imported/saved/exported RCP1, HC shows HC_DRAFT, not active or
hardware-qualified. CRC is not profile_crc and HC revision is not native runtime
revision. Apply has no route and stays disabled even if runtime_parameters=true
appears later. No OTA, UART, ARM/START/MANUAL or commissioning occurs through
parameter editing. Active readback/comparison stays unavailable; draft
differences explicitly compare only the loaded HC revision.

## New v3 tab: offline firmware preflight is not an update

Given no rover/operator configuration, an operator can explicitly submit a VG
RFU2/ELF pair to HC-only preflight. Mount/file selection never submits it. Exact
RFU2/RTE2/header/vector/profile and real ELF/image/RAM proof must pass. No
padding/relocation, RFU1/RFI2/loader fallback, native mutation, database write or
stored firmware artifact occurs. Upload remains disabled even on a valid result.

## New v3 tab: structural verification is not release approval

Given no selected server-reviewed release, a valid file pair reports structural
and ELF agreement but release_verified=false. A caller-supplied hash/metadata
cannot approve it. A selected release requires both independently reviewed full
hashes, firmware ID, exact size and profile from the server-only catalog. Missing,
corrupt or unknown entries fail closed. A matching release still does not prove
active rover profile, fresh loader READY, installation or hardware qualification.

## New v3 tab: unsafe inputs and stale UI proof

Given a compressed/extended/out-of-bounds ELF, excessive symbols, corrupt startup
RAM proof, truncated/oversized encoded request or foreign Origin, preflight
rejects without audit/rover side effects as appropriate. Concurrent preflight
returns 429. A changed file/release clears the previous result; lost/malformed
responses never show verified success or cause automatic resubmission.

## New v3 tab: HC staging is not a native update session

Given a server-reviewed RFU2/ELF pair, an authenticated operator explicitly saves
it to HC. The server rechecks the full files and selected catalog entry before
atomic retention. HC_STAGED has a separate hc_job_id and update_id=null. No
rover identity/session/reset/upload or motion grant occurs; a configured rover
is not needed. Unapproved files, missing auth or foreign Origin cannot be saved.

## New v3 tab: durable firmware replay, dedup and quotas

Given an identical saved request ID after HC restart, replay returns the original
HC job without new artifact/job rows. Different exact bytes or release ID cause
ID_CONFLICT. Repeated files with new request IDs deduplicate the blob, not the
job. Catalog removal does not erase historical review or turn replay into new
approval. Quota limits are serialized; failures roll back both inserts and never
delete existing artifacts. History shows at most 20 metadata-only records.

## New v3 tab: lost firmware-save acknowledgement

Given a timeout, malformed reply or uncertain DB commit, the browser retains
only the attempted request ID/release/hashes/size and shows UNKNOWN. Refresh or
login uses GET-only lookup, never re-sends files or creates a native session.
Found correlated HC_STAGED resolves retention only; missing/mismatched evidence
keeps UNKNOWN and disables new saves. Corrupt local correlation fails closed.

## Legacy scenarios below

These describe the preserved v2 services and unchanged RTK integration, not the
new Mower tab.

## Status-only commissioning

Given the ESP is online and publishing mower status, when HC opens the Mower
tab, then HC displays telemetry without issuing any command. Missing or older
than 10-second required status topics make `integration.healthy` false.

## Non-retained command

Given a user sends arm, stop, heading or route commands, when HC publishes the
MQTT message, then `retain` is false. An ESP reconnect must not replay it.

## Emergency versus manual stop

Given manual control is active, when the manual stop is pressed, then HC sends
a WebSocket `stop`. When emergency stop is pressed, HC also publishes global
`cmd/stop`. The two operations are not interchangeable.

## Manual deadman

Given the ESP accepted HC's manual claim, when drive/heartbeat traffic ceases
for 700 ms or the socket disconnects, then the ESP must zero drive and release
the session. STM safety remains authoritative.

## Route start

Given GNSS fix, north reference and route points exist, when the user confirms
route play, then HC sends a non-retained route play command. Uploading, viewing
or editing a route must not start movement.

## Fault display

Given `status/fault` or the robot fault mask is non-zero, when HC renders the
safety panel, then it shows a human-readable cause when known and preserves the
numeric mask for diagnosis.

## New v3 tab: explicit destructive STM preparation

Given a retained job, authenticated operator and fresh unlocked VG ABI2 identity,
explicit confirmation permits preparation only after current release/bytes/ELF
and live profile checks. No ordinary STM/GNSS/IMU/ARM gate is invented. Durable
CREATE_INTENT commits before exactly one native create POST. Selection, login,
mount or duplicate request never sends it. Manual ownership/busy admission,
revoked release, mismatched profile or retained-byte corruption fail before send.

## New v3 tab: lost admission is UNKNOWN, never adopted or retried

Given lost/malformed native create reply or interrupted HC acknowledgement,
the durable active attempt survives restart and only GET reconciliation runs.
Native GET lacks request_id: a current job on the same boot is unbound unless
the correlated returned ID was durably retained. Negative lookup, native 404,
changed boot/profile/endpoint or a mismatched native ID does not clear intent,
create a replacement or restore controls. Missing/corrupt browser correlation
blocks create. Ordinary snapshot/commands/manual fail closed; STOP stays separate.

## New v3 tab: maintenance evidence cannot grant normal operation

Given a retained native ID, status GET uses only its derived safe path and never
follows reply URLs. Source age includes HTTP transit and browser elapsed time;
null physical evidence stays unknown. Only bound fresh STM_LOADER with CAN off,
outputs inhibited, lock and no error proves READY. TRIAL/APP ACK/202/counters do
not prove install. Observed loader COMPLETE must match retained size/full SHA/fw
ID but never auto-unlocks or claims hardware qualification. Failed GET preserves
only historical diagnostics. Image/ABORT/FINISH have independent fresh gates; no real hardware
mutation is used to verify these scenarios.

## New v3 tab: single-send image and explicit verified exit

Given a bound fresh VG loader READY, the explicit image action rechecks current
catalog and exact retained RFU2/actual ELF, persists intent, then sends only raw
image with REC2/APP headers. Revoked review, bytes mismatch, stale proof or a
recorded IMAGE action cannot send. Lost native/DB acknowledgement is UNKNOWN,
recovered GET-only; a new request ID cannot bypass single-send.

Given fresh native permission, ABORT retains lock and never implies rollback;
FINISH admission never releases HC. Only separate explicit HC verification of
authorized finish, unlocked IDLE and new compatible fresh EMPTY STM state permits
atomic exit proof/session closure. Physical-input FAULT is allowed, other faults,
stale/old boot, armed state or mission/lease/progress are not. HTTP zero targets
are not invented: native IDLE's verified restart barrier is the trust boundary.
Cached pre-update snapshot and old browser command objects cannot re-enable
normal control. No observed state, mount/login or 100% body auto-finishes/arms.
Database reservation/exit-lock delay cannot renew a positive source proof;
expired evidence records no native send or verified HC closure.

## Firmware update

Given a valid STM `.bin`, when it is uploaded, then HC stages and verifies it
through the ESP. STM activation requires a second explicit action and warns
that the controller will reset.

## Network loss

Given HC, MQTT or Wi-Fi disappears while the rover is operating, then HC cannot
be a required part of the real-time safety loop. ESP deadman and STM safety
must bring affected motion to the rover-defined safe state.

## CAN commissioning

Given the STM firmware starts with `CAN_STARTUP_LISTEN_ONLY=1`, when telemetry
works but VESC actuation does not, then commissioning checks rover-side CAN mode
before changing HC. HC must not silently issue `CAN NORMAL`.
