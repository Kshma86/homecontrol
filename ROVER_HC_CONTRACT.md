# ROVER–HC mission szerződés v2.4.0

**Állapot:** egységes implementációs cél, nem kész firmware-tanúsítvány. Ez a fájl a két 2026-09-24-i `ROVER–HC Contract v2.3.0` dokumentum missionre vonatkozó 8. fejezetét, valamint annak mission capabilityre utaló mondatait váltja fel. A többi MQTT, WS, fault és safety szabály változatlan. Mindkét projektben azonos példányt kell használni. A `2.4.0` értéket csak az új szabályokat ténylegesen megvalósító firmware publikálhatja.

## 1. Megállapított eltérések és döntések

| Ütközés a két v2.3.0 szövegben | Egységes döntés |
|---|---|
| Az alapkontrakt `mission.v1`-et teljes STM-validáláshoz, STM-végrehajtáshoz és geofence-hez köti. A rover kiegészítés ugyanezt ESP RAM executorral, pontkövetéssel, hiányos geometriavizsgálattal hirdeti. | `mission.v1` csak a teljes, STM által ellenőrzött és végrehajtott missionhöz jár. A jelenlegi RAM-alapú feltöltés külön `mission.upload_preview.v1` capabilityt kaphat; ez sem `start`-ot, sem `resume`-ot nem enged. |
| A 8.10 szerint a HC capability nélkül egyetlen mission endpointot sem hívhat, de az első diagnosztikai lépés éppen `GET /api/mission/status`. | A HC mindig hívhatja a read-only `GET /api/mission/status` végpontot online ESP-n. Az író végpontokhoz friss capability és kompatibilis szerződés kell. |
| `prepare` teljes tárfoglalást ígér, rover szerint csak `max_alloc_heap` alapján vizsgál és uploadkor foglal. | Sikeres `prepare` ténylegesen lefoglal pontosan `size` bájtot vagy garantált tárolóhelyet. Különben `507 INSUFFICIENT_STORAGE`, staging nélkül. |
| Alapkontrakt egyetlen raw HTTP body-t követel; rover mellékágon multipartot is támogat. | A HC kizárólag `application/octet-stream`, rögzített `Content-Length` mellett küld. A multipart legfeljebb nem szabványos diagnosztikai kompatibilitás, nem része ennek a protokollnak. |
| Az alapkontrakt `status/mission/storage` két CRC-t követel a GET-ben, de MQTT-ben csak `crc32` szerepel; rover szerint ez payload CRC. | Mind HTTP, mind MQTT státuszban `file_crc32` és `payload_crc32` explicit mező. Egyedülálló `crc32` tilos v2.4.0-ként. |
| Reset után `PAUSED_RESTART` és explicit resume szerepel, ám `/resume` nincs az API-ban. | `POST /api/mission/resume` kötelező teljes capability mellett, új safety-ellenőrzéssel. Tartós tár nélkül reset után `EMPTY`, nincs resume. |
| `mission_id`/revision ellenőrzése az STM validációnál aktiválási queryre hivatkozik, amely a validate pillanatában még nem létezik. | Validate a staged headerhez tartozó prepare-adatok egyezését ellenőrzi. Activate külön összeveti a staged ID/revisiont a queryvel. |
| A szemantikus JSON példa boundaryje háromszög, célpontja a boundary szélén van, és az exclusion részben kívül esik. | Ez csak alakot szemléltető, érvénytelen példa; tilos sikeres mission tesztvektorként használni. A 236 bájtos CRC vektor is kizárólag bájtszintű teszt: nincs DRIVE_LINE, tehát teljes mowing missionként elutasítandó. |
| Rover specifikus hibák (`NO_MEMORY`, `UPLOAD_CRC`, `CRC_MISMATCH`, `BAD_OPERATION_*`) és alapkontrakt hibái eltérnek. | A wire kódok kanonikusak az 5. fejezet szerint; régi kód csak diagnosztikai `legacy_code` mezőbe kerülhet. |

## 2. Capability és jogosultság

`status/fw` élő, nem retained üzenetében `contract:"2.4.0"` és `capabilities` tömb szerepel. A HC csak azonos 2-es major és legalább 2.4.0, online állapot, friss `status/fw`, valamint a `GET /api/mission/status` egyező `contract`/`capabilities` értékei mellett indít mission író műveletet. Eltérés esetén diagnosztika és globális stop engedett; a HC látható hibát mutat. A GET válasz nem jogosít fel, ha az MQTT capability hiányzik vagy stale.

| Capability | Engedélyezett viselkedés |
|---|---|
| `mission.upload_preview.v1` | `prepare`, `upload`, `validate`, staging diagnosztika fejlesztéshez; nem jogosít aktiválásra vagy mozgásra. ESP nem állíthatja `active_valid:true` értékre az STM validációja nélkül. |
| `mission.v1` | Valós ESP→STM bináris transzfer, független STM geometriai/safety validáció, atomikus STM ACTIVE slot, STM pályakövetés és folyamatos helyi geofence; teljes `prepare → upload → validate → activate → start/pause/resume/stop`. Csak sikeres integrációs próbák után hirdethető. |

Az ESP és STM build címke diagnosztika, önmagában nem capability. A rover kiegészítésben leírt `esp-rover-2026-09-24.5-mission-contract-validate` és `2026-09-24.3-stm-mission-contract-validate` verziókból nem következik `mission.v1`; leírásuk alapján a teljes képesség még hiányzik. A HC a feltöltés állapotát megmutathatja preview módban, a start gombot nem.

## 3. Bináris HCM1 formátum és CRC

A v2.3.0 8.4–8.5 formátuma marad az alap: schema `hc.mower.mission.v1`, little-endian, 116 bájtos header, majd boundary pontok (8 bájt/pont), exclusion fejléc és pontok (4 + 8 bájt/pont), végül 24 bájtos operation rekordok. `total_length = 116 + 8*boundary_count + Σ(4 + 8*vertex_count) + 24*operation_count`; túlcsordulást minden oldalon ellenőrizni kell. Maximum 256 boundary pont, 32 exclusion, zónánként 128 pont, 4096 operation és **teljes fájlra** 256 KiB. Az `origin` WGS84 e7; minden útvonalpont mm egészekkel mért lokális ENU; a geometriai és operation mezők értelmezése a v2.3.0 8.4–8.5 táblázata szerint.

`payload_crc32 = CRC-32/ISO-HDLC(file[116:total_length])`; a header 12-es offsetjére kerül. `file_crc32 = CRC-32/ISO-HDLC(file[0:total_length])`; nincs a headerben, a `prepare.crc` előjel nélküli decimális értéke. A HC a header véglegesítése után számít file CRC-t, és a bájtokat többé nem módosítja. Golden bájtszintű vektor: `total_length=236`, `payload_crc32=0x5C182252`, `file_crc32=0xFF821923` (`4286716195` decimális). A vektor bájtjai az eredeti v2.3.0 8.5.1 szakaszának Base64 adatával azonosak; ESP és STM tesztelje bájtra pontosan. A vektor nem teljes geometriai/mission elfogadási példa.

## 4. HTTP API és állapotmenet

Az ESP címe konfiguráció. Kizárólag az alábbi végpontok kanonikusak; `client` nem hitelesítés, hanem egy session tulajdonosazonosítója. A firmware csak megbízható helyi hálón tegye elérhetővé az író API-t. A HC backend a rovernek küldött választ változatlan `code` és `stage` mezővel jelenítse meg, a böngésző ne módosítsa a HCM1 bájtokat.

```text
GET  /api/mission/status
POST /api/mission/prepare?client=...&size=...&crc=...&mission_id=...&revision=...
POST /api/mission/upload?client=...
POST /api/mission/validate?client=...
POST /api/mission/activate?client=...&mission_id=...&revision=...
POST /api/mission/start?client=...
POST /api/mission/pause?client=...
POST /api/mission/resume?client=...
POST /api/mission/stop?client=...
```

`prepare` előtt a HC a kész fájl méretét és két CRC-jét naplózza. A `crc` decimális uint32; UUID canonical lowercase RFC4122; revision uint32. A sikeres `prepare` teljes `size` tárhelyet foglal és új, kiszámíthatatlan `session_id`-t ad. Ugyanaz a `client`, ID, revision, size és CRC prepare kérése csak **PREPARED**, nulla feltöltött bájt állapotban idempotens. Más esetben a HC előbb GET-tel egyeztet; régi sessiont nem írhat felül véletlenül. Egyidejűleg egy session; más tulajdonos `409 MISSION_BUSY`. A `client` és `session_id` minden további mutáló hívásban kötelező (`session_id` query), az ESP ellenőrzi mindkettőt. Timeout vagy ESP reset után a régi token érvénytelen.

Az upload **egyetlen** POST nyers HCM1 bájtsorozattal, `Content-Type: application/octet-stream`, pontos `Content-Length=size` fejléc, chunked transfer nélkül. A HTTP body belül több callbackre bomolhat: az ESP offset alapján másol, nem használ `strlen`-t. A szerver csak `received_bytes == size` és a teljes file CRC egyezése után ad 200 választ. Részleges, túl hosszú vagy bontott upload invalidálja a staginget; a HC soha nem küld automatikus retry-t bizonytalan kimenetelnél.

`validate` ESP oldalon format/hossz/payload CRC ellenőrzéssel kezdődik, majd ugyanazt a bájtsorozatot sorszámozott, ACK-olt UART chunkokban átadja az STM-nek. STM önállóan ellenőrzi a teljes missiont, majd `STAGED` állapotot igazol vissza. A HTTP 200 kizárólag az STM pozitív validációja után adható. ESP RAM-only validáció csak preview capability mellett adhat eredményt, és ezt `preview_validated` mezővel jelzi; `stm_validated:false`, nem `STAGED` teljes értelemben.

`activate` csak STM-validált `STAGED`, egyező session/ID/revision és sértetlen file CRC esetén működik. Az STM atomikusan állítja az ACTIVE slotot, az ESP csak STM visszaigazolás után közöl `ACTIVE_IDLE`-t. Upload/validate/activate soha nem indít motort. Új staging/hibás feltöltés nem cseréli le a korábbi aktív missiont. `start` külön kezelői akció, és minden safety feltételt az STM újra ellenőriz. `pause` hajtást és kést nulláz, megőrzi a műveleti pozíciót. `resume` csak `PAUSED`/`PAUSED_RESTART` állapotból, új kezelői akcióval és minden startfeltétel újbóli ellenőrzésével lehetséges. A globális MQTT `cmd/stop` minden ownershipt és futást megszüntet; régi parancsból nincs automatikus folytatás.

Minden HTTP válasz JSON: `{ "ok":true|false, "stage":"...", "code":"...", "message":"...", "session_id":"..." }`; a `session_id` csak ha releváns. A POST válasz emellett mindig tartalmazza az aktuális `mission_id`, `revision`, `state`, `received_bytes`, `size`, `file_crc32`, `payload_crc32`, `stm_validated` mezőt, ahol ismert; ismeretlen érték hiányzik, nem hamis nulla. A GET ugyanígy közli `contract`, `capabilities`, ESP/STM buildet, `backend`, `staged_valid`, `active_valid`, session-tulajdonost és az utolsó hibát. CRC JSON típusa mindkét mezőnél 8 jegyű nagybetűs hex string; a prepare query marad decimális.

## 5. Hibakódok és felderítés

| HTTP | `code` | Teendő a HC-ban |
|---|---|---|
| 400 | `INVALID_ARGUMENT`, `LENGTH_MISMATCH`, `BAD_FORMAT`, `BAD_OPERATION` | Megmutatja a stage-et és üzenetet, compiler vagy request javítandó. |
| 409 | `MISSION_BUSY`, `SESSION_MISMATCH`, `MISSION_ID_MISMATCH`, `PRECONDITION_FAILED` | GET alapján feloldja az állapotot, nem indít újra automatikusan. |
| 413 | `TOO_LARGE` | Méretlimit fölötti fájl. |
| 422 | `FILE_CRC_MISMATCH`, `PAYLOAD_CRC_MISMATCH`, `STM_REJECTED` | Staging érvénytelen; STM elutasításnál `validation_code` és magyarázat kötelező. |
| 503 | `STM_UNAVAILABLE` | Nincs pozitív STM visszaigazolás. |
| 504 | `STM_TIMEOUT` | Kimenetel bizonytalan, GET egyeztetés; nincs automatikus activate. |
| 507 | `INSUFFICIENT_STORAGE` | Nincs garantált fogadóhely. |

Proxy/HC timeout legyen nagyobb, mint dokumentált ESP→STM műveleti idő; timeout után a HC `UNKNOWN` státuszt mutat, `GET /status` alapján egyeztet, és nem indít/aktivál automatikusan. A `stage` értékei: `PREPARE`, `UPLOAD`, `ESP_VALIDATE`, `STM_TRANSFER`, `STM_VALIDATE`, `ACTIVATE`, `START`, `PAUSE`, `RESUME`, `STOP`. Az ESP belső régi kódjai (`NO_MEMORY`, `UPLOAD_CRC`, `CRC_MISMATCH`, `BAD_OPERATION_*`) csak `legacy_code` alatt láthatók, az elsődleges `code` kanonikus.

## 6. Storage és MQTT

Az STM ACTIVE slotot írás közben nem lehet felülírni: új mission külön staged slotba kerül, payload íródik előbb, valid commit marker utoljára. Reset/tápvesztés után csak érvényes commit marker és CRC alapján lehet `ACTIVE_IDLE`/`PAUSED_RESTART`; `RUNNING` soha nem áll vissza automatikusan. Ha a tényleges backend `ESP_RAM`, ESP vagy STM reset után a staged/active mission elvész, állapot `EMPTY`, `staged_valid:false`, `active_valid:false`; `PAUSED_RESTART` nem használható. `backend` a tényleges storage helyét jelöli (`ESP_RAM`, `STM_FLASH`, `STM_QSPI`, `STM_SD`). Az ESP RAM executor nem állíthatja magáról, hogy STM persistent storage.

`status/mission/storage` minimális mezői: `backend`, `staged_valid`, `active_valid`, `bytes`, `received_bytes`, `file_crc32`, `payload_crc32`, `stm_validated`. A CRC mezők csak valid bájtsorozatnál szerepelnek. `status/mission/validation`: `valid`, `code`, `message`, `checked_operations`, `stm_validated`. `status/mission`: `mission_id`, `revision`, `state`, `operation_index`, `operation_count`, `stop_reason`, és RUNNING alatt az eredeti 8.9-ben felsorolt értelmezhető műveleti mezők. Ismeretlen mérési mező hiányzik, nem nulla. A HC a `received_at` alapján frissességet vizsgál, retained status nem igazolja a current state-et. GET és MQTT eltérésekor a HC blokkolja az író műveleteket, GET-tel egyeztet; MQTT státusz nem váltja ki a HTTP művelet válaszát.

## 7. STM validáció és végrehajtás

Az STM nem bízhat az ESP ellenőrzésében. Kötelező magic, header/hossz/CRC, UUID/revision, táblahatár/overflow, reserved-nullák, ismert op típusok, operation-sorrend, koordináta/geometria ellenőrzés. A teljes boundary és exclusion legyen egyszerű, érvényes polygon; minden DRIVE_LINE és TURN_IN_PLACE teljes mozgási burka a clearance utáni szabad területen. A forgási kör sugara legalább `ceil(sqrt(width²+length²)/2)` plusz kiálló részek; külön boundary clearance. Minden connector explicit, nincs teleport. A mowing mission pontosan `PATH_START, BLADE_ON, ... , BLADE_OFF, STOP`; minden DRIVE_LINE `blade=true`; a startpont és minden target a lokális ENU kvantált koordinátáin validálandó. A v2.3.0 8.7 többi limitje is érvényes.

START: STM ACTIVE + armed + fault/E-stop mentes + RTK FIX + friss korrekció/north/link/VESC + `PATH_START` tolerancia. RUNNING: STM minden ciklusban helyi geofence, exclusions, RTK, cross-track, heading, safety, link és VESC watchdog; tiltáskor hajtás és kés nulla, folytatás csak kezelői akcióval. TURN_IN_PLACE ellentétes kerékirány, nullázott hajtás után DRIVE_LINE; DRIVE_LINE vonalkövetés cross-track/along-track hibából, nem puszta célpont-goto. Az ESP RAM pontkövető csak preview, nem igazolja ezt a fejezetet. Késes éles próba csak a helyi safety és levett késes integrációs próbák után.

## 8. Minimum elfogadási próba

1. Mindkét oldalon ugyanaz a golden 236 bájtos fájl, `236`, `5C182252`, `FF821923`; ez kizárólag format/CRC teszt, a teljes mission validator visszautasíthatja.
2. Külön, valóban geometriában érvényes mowing mission fixture készül; HC, ESP és STM ugyanazokat az operationöket dekódolja, validálja; ellenpéldák: boundary szélén végződő szakasz, exclusion átmetszés, túl kicsi pivot kör, rossz start tolerancia.
3. HC → proxy → ESP prepare/upload/validate/activate integrációs napló: minden lépés `stage`, HTTP status, `code`, `session_id`, `received_bytes`, két CRC és STM validation eredmény. A `mission.v1` csak a teljes lánc sikerénél jelenhet meg.
4. Hiányzó capability: GET elérhető, POST tiltott. Preview capability: upload és diagnosztika elérhető, activate/start tiltott mind HC, mind ESP oldalon.
5. Félbeszakadt body, memóriahiány, hibás CRC, UART ACK timeout, eltérő ID/revision és reset: nincs részleges ACTIVE, nincs automatikus retry/start; korábbi érvényes ACTIVE megmarad, ha a tartós slot létezik.
6. Levett késsel igazolt STM geofence, RTK/correction kiesés, bumper/lift/tilt, link/CAN kiesés, pause/resume/reset; egyetlen régi parancs sem indítja el újra a motort.

## 9. Az aktuális „nem megy át a mission” diagnózis

Elsőként az élő `status/fw`, majd `GET /api/mission/status` `contract`, `capabilities`, `backend`, `max_alloc_heap`/szabad tár, `staged_valid`, `active_valid` mezőit kell rögzíteni. Ha a HC már a POST előtt tilt, capability/contract/stale hiba. Ha prepare hibázik: méret, szabad egybefüggő tár vagy session. Ha upload: raw body, Content-Length, `received_bytes`, file CRC. Ha validate: külön ESP payload CRC, UART transzfer és STM validation code. Ha activate: staged/active állapot és ID/revision. Az élő HTTP/MQTT válasz és firmware napló nélkül nem állítható, hogy ezek közül melyik a konkrét jelenlegi hiba.
