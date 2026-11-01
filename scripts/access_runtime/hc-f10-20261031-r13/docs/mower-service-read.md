# Mower LAN szerviznézet — 2026-10-10

Történeti LAN2 nézet: 2026-10-11-től a Mower alapértelmezése HC_BRINGUP,
nem ez a service firmware. Az aktuális bekötés:
[mower-hc-bringup-read.md](mower-hc-bringup-read.md).

Authority: `hc-rover-lan-backend-20261010.zip`, especially
`HC_AI_SZERVIZ_ATADAS_20261010.md`, `docs/HC_ROVER_LAN_BACKEND_20261010.md`
and `docs/HC_ROVER_CONNECT_NOW_20261010.md`. This is the separate
FIRST_INSTALL_SERVICE / service_abi=1 contract, not operational v3.1/VG ABI2.

## Implemented surface

The preserved historical view is **Régi LAN2 szerviz — csak olvasás**. Explicit view selection
can mount the preserved operational v3.1 component instead. Only the selected
view mounts/polls; there is no auto-detection, API alias or fallback. Legacy and
RTK remain unchanged. The service view contains no device mutation controls.

`GET /api/mower/v3/service/snapshot` calls, serially and only:

- `GET /api/v3/service/status`
- `GET /api/v3/service/parameters`

`mower_service_read.py` uses a backend-only Bearer credential, fixed provisioned
origin, no proxies/redirects, 3-second timeout per request, 8192-byte response
limit, duplicate/nonfinite JSON rejection and a response whitelist. ServiceHttp
rejects POST, firmware mutations and manual sockets. There is no generic proxy,
service write route, database write or shared legacy context invalidation.

Accepted service/ABI/version are exact; motion_permitted, applied, commissioned
and both OTA capabilities must be false. Peer UID/firmware must match across
the two GETs. Saved parameter JSON passes the unchanged exact 27-field RCP1
validator and checksum; null EMPTY/revision=0 is not an operational default.
STAGED means stored, never ACTIVE/APPLIED, and is not auto-imported into drafts.

HTTP availability is distinct from STM freshness. Source age includes both
request transit/wait and frontend elapsed time; above 3000 ms, current STM
flags become unknown. Service has no source sequence/boot/epoch: revision is
not a heartbeat, and service PING cannot synthesize operational STATE evidence.
Historical firmware/network/readback rows are explicitly last observations.

Poll interval is 1 second, hidden tabs do not request, requests cannot overlap,
and browser requests abort after 7 seconds/unmount. Backend shares the existing
single-worker activity mutex and consults the durable update maintenance guard;
service polling cannot bypass a pending native firmware lock. HTTP responses
are no-store/nosniff. Tokens, Wi-Fi credentials and unknown fields are stripped.

## Private provisioning

Set the exact LAN HTTP(S) origin in `MOWER_V3_REMOTE_URL`. The setup AP address
is not the service API. Current operator-supplied LAN address: `192.168.1.119`.

Choose exactly one credential source:

- Existing private `ROVER_API_TOKEN` environment value, or
- `ROVER_API_TOKEN_FILE`, a backend-readable private JSON with an `api_token`
  field containing the provisioned 64-hex token.

Both configured, unreadable/missing/oversized/invalid JSON file, duplicate keys
or invalid token fail closed. Credentials are read at backend startup and are
excluded from settings repr/browser responses. No token value or helper script
is copied from the rover development machine automatically.

The local deployment uses the private-file option:

`/srv/docker/homecontrol/infra/private/rover-access.json`

The `infra` directory is already mounted into the backend at the same path;
there is no new broad secrets mount. `infra/private` is git-ignored and should
be mode 700; the access file should be mode 600. Never add the actual access
file to a ZIP, Git, prompt, browser storage, URL, log or command-line argument.
The operational adapter uses the same privately loaded token but its admission
checks are unchanged; service connectivity is not operational compatibility.

After privately placing the access JSON, restart the backend:

```sh
docker compose -f infra/docker-compose.yml restart backend
python3 -B scripts/check_mower_v3.py --url http://127.0.0.1 --service
```

Run from `/srv/docker/homecontrol`. The checklist reads only the HC service
snapshot; it never logs in, sends a POST, firmware action or motion command.
Its successful exit means the check ran, not that the rover is connected.

## Verification boundary

Backend tests: `tests.test_mower_service_read` plus mower regression suite.
Frontend: `npm run test:mower` (including service model/render/read-only tests)
and `npm run build`. Tests use synthetic peers/parameters, not robot defaults.

One token-free GET from the running HC backend to the operator's LAN address
returned HTTP 401 on 2026-10-10. This proves an HTTP response on that path, not
authenticated STM telemetry, LAN reset persistence, parameter staging/apply,
OTA, CAN mechanical stop or hardware qualification. Those are separate checks.

Deployment verification: 213 mower backend tests ran (198 passed, 15 optional
PostgreSQL tests skipped); all 55 frontend tests and Vite build passed. Backend
and frontend images were deployed. The new no-store/read-only snapshot and
service bundle are served by backend, direct frontend and main HC proxy. Legacy
and RTK source SHA256 values are unchanged. At the initial deployment the LAN
origin was configured but the private access file was absent (UNCONFIGURED).

Subsequent operator-authorized provisioning on 2026-10-10 installed the private
access file with mode 600 and restarted only the backend. The read-only HC
service checklist now confirms SERVICE_CONNECTED, fresh STM, ESP firmware
esp-service-20261010-lan2, STM service-20261010 and UID
004C00333131511431333732. Storage is EMPTY/revision=0; applied and
motion_permitted remain false. HC health reports PostgreSQL and MQTT OK.
No parameter, firmware, reset or motion command was sent to the rover.

