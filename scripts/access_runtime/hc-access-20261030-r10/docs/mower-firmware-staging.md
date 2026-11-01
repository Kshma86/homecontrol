# Mower firmware HC staging — 2026-10-10

This slice adds **durable HC retention only** to the existing VG RFU2/ELF
preflight. It needs no rover connection and never creates a native update job,
resets hardware, sends image bytes, ABORTs, FINISHes, arms or starts anything.
Legacy Mower and RTK Editor remain unchanged. Native preparation/status, raw
image sending and explicit exit exist separately in `mower-firmware-sessions.md`.
The independently reviewed server catalog remains empty by default;
no test fixture has been approved or saved in the production database.

## Explicit operator workflow

1. Select the exact RFU2 image, matching ELF and server-reviewed release.
2. Run HC preflight explicitly; selection/mount does not submit files.
3. After operator login, explicitly choose **Jóváhagyott fájlpár mentése a HC-ba**.
4. The backend repeats independent catalog/hash/ELF/RAM checks, then retains
   both exact files and an immutable `HC_STAGED` job in one transaction.

`HC_STAGED` / `hc_job_id` are HC identifiers, never native `update_id`, loader
READY, STM execution or install success. `release_verified_at_staging` and
`elf_verified_at_staging` describe historical review only, not current catalog
authorization or hardware qualification. No live profile/identity match is
claimed. Native preparation revalidates the current catalog, retained bytes and
live authenticated identity; history must never authorize a write.

## HC routes

All are below `/api/mower/v3/firmware` and return no-store/nosniff:

- `POST /jobs`: same-origin + authenticated operator, raw unencoded HC envelope
  `u32LE(image length) + image + ELF`, bounded exactly as preflight. Required
  `X-HC-Release` selects a server-approved entry; `X-HC-Request-ID` is an ASCII
  letters/digits/underscore/hyphen token, 1..64 characters. No metadata override.
- `GET /jobs`: authenticated, up to 20 newest metadata-only jobs and HC limits.
- `GET /jobs/<hc_job_id>`: authenticated, exact nonzero uppercase 32-hex HC ID.
- `GET /jobs/requests/<request_id>`: authenticated retention lookup. `found:false`
  does not prove an in-flight transaction cannot still commit; do not retry.

Staging exposes no browser binary download, delete, approval or native mutation.
Native create/status/image/abort/finish belong to the separate session slice.
The HC envelope must never be forwarded as native raw image
upload. Only the exact `/firmware/preflight` and `/firmware/jobs` paths receive
the 17 MiB limit on both nginx hops; unrelated routes keep their current limits.
Both share the single-flight audit guard. Database errors are sanitized;
uncertain POST acknowledgement is `SAVE_UNKNOWN`, not a claimed rollback.

## Durable schema and transaction policy

Migration `infra/db/053_mower_firmware_staging.sql` matches lazy service bootstrap
byte-for-byte. `hc.mower_firmware_artifact` retains image/ELF as PostgreSQL bytea;
artifact ID is SHA256 of the entire exact HC envelope. `hc.mower_firmware_job`
retains immutable job/request/release IDs, preflight report and server timestamp.
The tables are included in ordinary PostgreSQL backup retention; no additional
filesystem directory or user-provided path is used. Initial authenticated reads
can initialize empty tables; ordinary job reads never contact a rover.

Global transaction advisory lock `hc.mower.firmware.staging` serializes initial
save, durable request replay, deduplication and quotas across HC connections:

- at most 32 distinct retained file pairs;
- at most 256 MiB combined image/ELF bytes;
- at most 1024 HC jobs, including deduplicated-file jobs.

These are conservative **HC resource policies**, not native hardware limits.
Quota rejection rolls back and never silently deletes/evicts anything. Admin
retention tooling is not part of this slice. Identical request-ID/bytes/release
replay returns the original job across service restart, even if the catalog has
subsequently changed; it is not a renewed approval. Different bytes or selected
release with the same request ID are `ID_CONFLICT`. New request IDs still require
current complete review even when their file pair already exists in storage.

## UNKNOWN and browser persistence

Before the explicit POST the browser saves a bounded request ID, release ID,
image/ELF hashes and image length in `sessionStorage`; never files, passwords or
rover credentials. Missing/unusable storage prevents POST. Lost or malformed
replies retain UNKNOWN and disable new saves. Login/remount may perform a
GET-only lookup; there is no automatic retry/POST, firmware restore or native
session restore. Manual GET reconciliation is available as well.

Only a strictly correlated retained HC_STAGED descriptor clears UNKNOWN. A
negative, mismatched or unavailable GET does not clear it. Recognized HC
pre-write rejection (auth/origin/format/audit/quota) can release the pending
intent; unknown gateway/server failures and ID conflicts cannot. Corrupt local
correlation requires administrative reconciliation rather than silent forgetting.
Correlation uses 128-bit `crypto.getRandomValues` bytes without a `randomUUID`
dependency or weak random fallback; unavailable browser crypto prevents POST.

## Verification

```sh
cd infra/backend
python3 -B -m unittest tests.test_mower_firmware tests.test_mower_firmware_routes tests.test_mower_firmware_staging tests.test_mower_firmware_postgres
```

Optional real SQL tests need `MOWER_TEST_POSTGRES=1` plus the existing private
`DATABASE_URL`; they use only `pg_temp` tables in force-rollback transactions.
They verify exact byte retention, dedup, restart replay, conflicts, bounded
history, independent count/byte/job quotas, lock admission and atomic rollback
after an artifact insert. They do not seed/delete production artifacts.

`npm run test:mower` includes metadata/intent bounds, explicit-only save,
authentication/review/storage prerequisites, double-click, lost/malformed reply,
GET-only restore, negative/mismatched lookup and known rejection cases. Existing
firmware/parameters/manual/STOP and inactive-Legacy regression tests still run.

Verified and deployed 2026-10-10: 148 Mower backend tests passed including real
PostgreSQL temporary-table tests, plus 15 shared API/context/command regressions.
All 38 frontend tests and the production build passed. Both nginx configurations
validated; 2,101,588-byte synthetic requests through both hops passed preflight
without review/persistence and received AUTH_REQUIRED on staging without login.
Production staging tables were initialized empty (0 artifacts / 0 jobs). Health
reported DB/MQTT OK; rover stayed UNCONFIGURED. No live rover mutation was sent.
The pre-existing npm audit report (1 moderate / 4 high) is unchanged; dependency
versions were not altered by this slice. Legacy/RTK source checksums are unchanged.

## Native updater continuation

Native create/status reconciliation is implemented separately; see
`mower-firmware-sessions.md`. It persists send intent before any native create
and never auto-retries an unknown mutation. The supplied
native GET update schema does **not** include request_id, so an arbitrary active
job observed after a lost create reply cannot safely be adopted as HC-owned.
Bind only a durably retained correlated returned update_id; otherwise retain
UNKNOWN/unbound observation. The separate native integration enforces fresh
loader READY, matching identity/boot/profile and exact single-send raw image,
then explicit ABORT/FINISH and independently verified HC normal-mode exit.
