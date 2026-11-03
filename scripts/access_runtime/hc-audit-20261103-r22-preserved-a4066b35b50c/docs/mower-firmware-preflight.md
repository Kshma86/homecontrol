# Mower VG firmware preflight — 2026-10-10

This implementation is **HC-only inspection**, not an updater or release-signing
system. The new Mower tab accepts a VG RFU2 `.bin` plus its actual ARM `.elf`.
It works without rover/operator deployment settings. Explicit inspection sends
the files to HC only, never to a rover; no update session, storage row, reset,
ARM, START, ABORT or FINISH is performed by preflight. No native upload/activation
route exists. A separate explicit authenticated HC retention flow has now been
added; see `docs/mower-firmware-staging.md`. Preflight remains non-persistent.
Legacy Mower and RTK Editor source/behavior are unchanged.

## Checks and authority

`infra/backend/mower_firmware_service.py` wraps unchanged references copied
from `hc-v31-qspi-handoff-20261009-rcp1-foundation.zip`, verified byte-for-byte
against its manifest in tests:

- `rover_qspi_image.py`: RFU2 format, VG target, exact size/alignment, vectors,
  embedded firmware/profile and RTE2 entry; ELF load placement and exact image
  reconstruction including FF padding, RAM boundaries, preserved boot capsule,
  reset/IRQ ordering and actual startup RAM-verification instruction sequence.
- `rover_ram_audit.py`: reset-only RAM verification macro audit.
- `rover_image.py` and `rover_profile.py`: unchanged import dependencies.
  HC calls neither their CLI nor profile install/header generation functions.

`pyelftools==0.32` is pinned for ELF parsing. Uploaded ELF is read using an
in-memory read-only adapter: no caller paths, archive extraction, subprocess,
compiler or `esptool` execution. HC rejects compressed/extended ELF tables,
out-of-file regions, >64 program headers, >256 sections, >8192 symbols per
symbol table, >128-byte section names and >256-byte symbol names before the
reference auditor. These are conservative HC resource limits, not a relaxed
rover contract. Actual release artifacts must fit them.

RFU2 length is 1280..524288, a multiple of 32; header layout is
`H743_1M_QSPI_REC2`, slot `APP`, target `STM32H743VG`, service ABI 2,
link address `08100000`, nonzero uppercase profile CRC. ELF is <=16 MiB.
HC never pads, relocates, converts RFU1, or accepts RFI2/factory/loader inputs.
ABI1 A/B and ESP OTA preflight are not implemented by this slice.

## Independent release review

The backend reads `infra/backend/static/mower-approved-releases.json`, copied
read-only-in-practice with the backend image to `/app/static/`. It starts with:

```json
{"format":"HC_FIRMWARE_RELEASES_V1","releases":[]}
```

An administrator must review the release through the trusted development/release
workflow before editing that server-side file and rebuilding the backend. Each
entry has exactly these fields:

```text
release_id       1..64 ASCII letters/digits/underscore/dot/hyphen; unique
firmware_id      exact embedded firmware token, 1..48 same characters
image_sha256     independently reviewed complete-image hash, lowercase 64 hex
elf_sha256       independently reviewed ELF hash, lowercase 64 hex
profile_crc      matching nonzero uppercase 8 hex
image_bytes      exact padded image length
layout           H743_1M_QSPI_REC2
slot             APP
```

The catalog is <=64 KiB and <=64 entries, exact-schema and duplicate-key
validated. Missing/corrupt catalog fails closed, not an empty approval fallback.
There is no browser/API endpoint to approve/edit it; a selected release ID
cannot supply or override any trusted hashes or tokens. A file's computed hash
or user-provided metadata JSON is not approval. The catalog/ZIP manifest are
not publisher signatures and must not be represented as such.

Without a selected approved release, successful inspection reports structural
and ELF agreement only, `release_verified=false`. With one, **both** complete
hashes plus embedded firmware/profile and exact length must match the catalog.
Even then `upload_available`, `persisted`, `hardware_qualified` and
`rover_contacted` remain false. The image profile is not evidence of installed
rover profile agreement or runtime RCP1 activation.

## HC API, not a native rover API

- `GET /api/mower/v3/firmware/releases`: public catalog and resource limits;
  no rover request, no database mutation.
- `POST /api/mower/v3/firmware/preflight`: exact same-origin required,
  `application/octet-stream`, no content/transfer encoding and exact length.
  Body is `image_length:u32 little-endian + exact image + exact ELF`.
  Optional `X-HC-Release` selects a server-reviewed release ID only.
  This HC envelope is never sent to the native rover image endpoint.

Both return `Cache-Control: no-store` / `X-Content-Type-Options: nosniff`.
Maximum body is 4+524288+16777216 bytes; one active preflight per process,
429 for concurrent inspection. Parser failures are sanitized and do not expose
raw file content/server paths. Both nginx hops permit 17 MiB only on the exact
preflight and HC job-staging paths; other endpoint limits remain unchanged. nginx may temporarily
buffer request bytes using its ordinary request buffering; HC creates no
retained artifact file and never logs request contents.

UI mount/file selection sends no inspection POST. Inspection is explicit, with
bounded request timeout/unmount abort, no automatic retry or saved/restored
firmware request. New file/release selection clears previous proof. Lost or
malformed replies show unverified results, not install success. The rover upload
button is always disabled, even when a release and rover capability are known.

## Verification

```sh
cd infra/backend
python3 -B -m unittest tests.test_mower_firmware tests.test_mower_firmware_routes
```

Use repository root as a read-only mount when running the tests from the backend
image: the vendoring test reads the original ZIP. Synthetic tests construct
RFU2 plus an actual 32-bit ARM ELF with auditable RAM startup bytes; they are
NOT bootable firmware, installable profiles or hardware acceptance evidence.
Cases include selected/unselected review, both hashes, forged metadata,
header/vector/RTE2/reserved corruption, image/ELF mismatch, RAM proof corruption
even when both files are altered identically, IRQ mask order, ELF resource
limits, cross-origin rejection, truncated body and concurrent admission.

`npm run test:mower` additionally checks the HC binary envelope, frontend bounds,
proof invalidation, malformed/lost results, explicit-only requests and disabled
rover upload. The Docker frontend build executes these tests.

Verified/deployed on 2026-10-10: 150 backend tests ran (147 passed, 3 optional
PostgreSQL tests skipped); all 32 frontend tests and the Vite build passed.
Both nginx configurations passed validation. A 2,101,588-byte synthetic request
through the main proxy and direct frontend hop returned ELF-verified but
unapproved/non-persistent/no-rover-contact results. Health reports DB/MQTT OK;
the native rover remains UNCONFIGURED. No live rover command or hardware test
was performed. Legacy controller and RTK Editor checksums remain unchanged.

## Remaining updater work

Durable PostgreSQL HC_STAGED jobs/artifact retention are now implemented separately.
Authenticated native session creation, 2 Hz source-age-preserving polling and
durable UNKNOWN/GET reconciliation now exist in `mower-firmware-sessions.md`,
with live identity/profile checks and strict loader READY evidence. Single-send
raw upload, explicit ABORT/FINISH and a separate verified HC exit are implemented
there as well. Real installed capability/physical stopping/qualification still
need hardware evidence; none is inferred from this preflight.
