# RCP2 / hárommotoros kiegészítés – 2026-10-12

Az új forrás a CFG UART ABI2 alatt RCP1-et és RCP2-t is támogat. Az alábbi
korábbi 27-mezős leírás az RCP1-szerződés; nem értelmezzük át automatikusan.
RCP2 / `drive_erpm` / mért összesített áttétel és telepítési korlátok:
[hárommotoros HC átadás](../HC_AI_HAROM_MOTOR_ATADAS_20261012.md).
A kiadás nem telepített és nem jelent mozgási engedélyt.

# HC runtime paraméter API — CFG ABI1, 2026-10-09

Roveroldalon implementált, natív célokra fordított, hoston ellenőrzött. Valós
boardtelepítés és fizikai minősítés még nem történt. A HC integráció elkezdhető;
ne mutasson telepített vagy mozgásra minősített állapotot a csomag alapján.
Adatok/mértékegységek/range/CRC: `HC_PARAMETERS_RCP1.md`, `rover_parameters.py`.

## HC alkalmazási folyamat

1. Bearer-authenticated GET `/api/v3/identity`: `runtime_parameters=true` szükséges.
2. GET `/api/v3/parameters`: friss `source_valid=true`, `can_apply=true`,
   `busy=false`, aktuális boots/epoch/revision. A capability önmagában nem safety.
3. Explicit kezelői műveletből egyszeri POST `/api/v3/parameters`.
4. Csak GET-egyeztetés; nincs automatikus POST retry, ARM, START, manual claim,
   mission resume, firmware rebuild vagy OTA a paraméterek miatt.

POST Content-Type pontosan `application/json`, nem chunked, maximum 2048 byte.
Kompakt, whitespace nélküli JSON; duplikált/extra kulcs, lebegőpontos szám tiltott.
Pontosan hét gyökérkulcs:

```json
{"v":3,"request_id":"operator-unique-id","esp_boot":"<16 uppercase hex>","stm_boot":"<16 uppercase hex>","control_epoch":123,"expected_revision":0,"parameters":{}}
```

Ez szerkezeti példa, nem beküldhető adat: a boots/epoch/revision friss GET-ből,
`parameters` teljes validált 27-mezős objektum a HC draftból. ID: 1..64
request-karakter, műveletenként egyedi. expected_revision: 0..4294967294;
0 az első konfiguráció. Python `json.dumps(..., separators=(",", ":"),
ensure_ascii=True, allow_nan=False)` vagy validált JS `JSON.stringify`.

202: `{"v":3,"result":"PENDING","code":"QUEUED","request_id":"…"}` csak
queue-fogadás, nem alkalmazás. 400 INVALID_PAYLOAD; 409 CONFIG_NOT_READY vagy
CONFIG_BUSY; karbantartáskor 423 UPDATE_MODE. A worker újra ellenőrzi az élő
boots/epoch/safety/revision értékeket. A HC szerializálja az alkalmazási kéréseket.

GET mezők: `v=3`, `parameters_version=1`, `esp_boot`, `stm_boot`, `control_epoch`,
`request_id` (ismeretlen:null), `revision`, `parameters_crc` (8 uppercase hex,
hiányzó:null), `storage=EMPTY|ACTIVE|PENDING|FAULT`, `busy`, `available`,
`source_valid`, `source_age_ms`, `can_apply`, `applied`, `code`, `parameters`,
`commissioned=false`, `motion_permitted=false`. A kezdeti boots lehetnek üresek,
epoch/revision 0; unavailable forrásból ezek nem használhatók íráshoz.

A forrás eredeti UART-kora megmarad; 1500 ms felett nincs friss applied/can_apply
vagy paraméterobjektum. A GET 200 nem konfigurációs siker. Siker csak friss
`source_valid=true`, `applied=true`, `storage=ACTIVE`, azonos request ID, várt
revision és a HC által RCP1-ből kiszámolt CRC mellett. `code=APPLIED` önmagában
nem elég. Timeout/elveszett 202: UNKNOWN és GET-egyeztetés, nem új POST.
Eltérő ID/revision/draft konfliktus. Új boot restore megőrzi az eredeti job ID-t.

## Natív adatút és kizárások

Dedicated ESP konfigurációs task kezeli az NVS-t. HTTP és sole UART bridge csak
fixméretű másolt mailboxokkal kapcsolódik; nincs NVS-írás az UART RX-taskban.
STM CFG ABI1: BEGIN → hat DATA (maximum 96 byte) → SEAL → APPLY. Teljes 512-byte
canonical RCF1, board/UID/CRC/boots/epoch/revision validálás. Tranzakció 15 s;
válasz 1500 ms; mutáció nincs automatikusan újraküldve.

STM saját DISARMED, lease/update/upload-mentes állapot és minősített natív
kimenettiltási bizonyíték szükséges. CAN-os telepítésnél a szoftveres kapu
zárt, a CAN működőképes és a friss motor-STATUS újra igazolja a megállási
ablakokat; nincs VESC-tápmegszakítás. GPIO-s telepítésnél az actual inhibit és
független feedback után újra kivárt coast-idő szükséges. Ismeretlen bizonyíték
zár; 20 ms feletti natív megfigyelési rés újrakezdi a megállási/coast ablakot.
Részletek: `ROVER_UPDATE_MAINTENANCE.md`.
Első konfiguráció/ACTIVE boot-restore előtt a megállás igazolása a minősített
installation kalibrációt használhatja; ez nem működési profil-fallback és
hiányzó runtime konfigurációval a mozgási kapu zárva marad.
SEAL/APPLY törli a küldetést/headinget/szenzorsessiont/kézi lease-t,
nullázza a kimenetet és új control epochot ad: STATE reason CONFIG_CHANGED.

SEAL után csak friss natív PREPARED-proofra commitol/visszaolvas az ESP;
az APPLY ennek pontos committed CRC-jét kéri. NVS ACTIVE nem STM APPLIED.
Hiányzó konfigurációból nincs compiled működési fallback. Minden alkalmazás
visszavonja a commissioninget; ez a szolgáltatás nem jogosít mozgásra.

## Boot, frissítés és mission CRC

RFU2/RFI2/OTA/journal/HELLO `profile_crc` = változatlan immutable installation
snapshot CRC. Nem runtime CRC; ne cseréld le update headerben. A snapshot régi
paramétermezői legacy telepítési azonosság, nem aktív controllerbeállítások.
GET `/api/v3/profile` csak ezt olvassa, nem setter és nem aktív konfiguráció.

M3 mission header +64 `profile_crc` = friss runtime `parameters_crc`. Készíts
új küldetést alkalmazás után; a mission/geometria/IMU/kézi útvonal runtime-ból
dolgozik. Paraméterváltozás nem igényel új installation headert/firmware-t.

OTA/rollback nem írja a `rover-config/params0|params1` kulcsokat. Csak már
tartós ACTIVE rekord restore-ja mehet új normál STM/ESP bootra, friss natív
safety-prooffal és ugyanazzal a boardazonossággal. PREPARED nem folytatódik,
nem kap új bootot/deadline-t. A sikertelen restore ugyanazon bootpáron nem retry.

PENDING + CONFIG_RECOVERY_REQUIRED vagy FAULT + CONFIG_STORAGE_ERROR szervizes
helyreállítás; nincs online force/erase/abort vagy néma régi-paraméter fallback.
A megőrzött előző ACTIVE nem mozgási engedély. Elveszett végső APPLY ACK pontos
STATUS-readbackkel egyeztethető; csak már commitolt és natívan APPLIED adat jó.

## Ellenőrzések

Repository: `make -C tests configuration-live configuration-foundations`.
Kilenc lost-ACK pont, ACTIVE restore új boots mellett, safety/lease/update/upload
kizárás, strict JSON és minden 512 staging/commit byte-megszakítás hoston tesztelt.
Ez nem fizikai power-cut, watchdog/stop/időzítés minősítés. A HC szintetikus
adatokból csak tesztet készíthet, telepítési bizonyítékot nem.
