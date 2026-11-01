# HC AI átadás – feltölthető MOTOR_TEST, hárommotoros kézi próba

2026-10-12. Ezzel kezdj: ez a külön, felügyelt MOTOR_TEST kiadás szerződése.
A korábbi HC_BRINGUP csak olvasható; a normál VG/QSPI éles telepítés külön feladat.
Nem változtattuk meg a HC-projektet vagy a VESC firmware-t/beállításokat.
Kés nélküli, helyileg felügyelt motorpróba; nem autonóm vagy minősített kaszálás.
Firmware készítése nem hardveres próba és nem igazolja a tényleges megállást.

## Pontosan melyik firmware?

- ESP: `esp-motor-test-20261012`, STM: `stm-motor-test-20261012`.
- `identity.mode="MOTOR_TEST"`, `contract="3.1.0"`, kompatibilis peer szükséges.
- `profile_crc="4D545331"`: elkülönített szerviz-boardazonosság. NEM runtime
  paraméter-CRC és NEM RFU2/RFI2/OTA minősített telepítési snapshot.
- `commissioned=false`, `profile_verified=false`, `conformant=false`,
  `motion_permitted=false` marad. Ezek az éles üzem minősítésének mezői.
- **Csak ebben az explicit módban** a külön `test_manual_control=true` és
  `manual_erpm=true` képesség ad belépést a felügyelt kézi vezérlési folyamatba.
  Ez még nem ARM és nem garantált motorelérhetőség; az STM végső kapuja dönt.
- `stm_flash_layout="H743_1M_STANDALONE"`, `stm_remote_update=false`,
  `stm_image_max_bytes=0`, `esp_ota_enabled=false`, `esp_ota_max_bytes=0`,
  `autonomous_enabled=false`. Ne indíts firmware sessiont vagy START/RESUME-t.

Ne alakítsd át a normál kiadás admissionjét: a MOTOR_TEST legyen külön
fejlesztői üzemmód, jól látható felügyelt tesztjelzéssel. Ismeretlen firmware,
bootváltás, elavult adat, UNKNOWN vagy hiányzó capability mellett nincs vezérlés.
Az updater valódi ERROR/locked állapota a még nem telepített szolgáltatást is
mutathatja. Ezt a teszt-FW nem törli és nem hamisítja unlocked IDLE-ra.
Csak ténylegesen üres, vagy ép unlocked IDLE history mellett indul a MOTOR_TEST;
lezárt/sérült/TRIAL history és függő ESP OTA blokkol. Nincs force vagy NVS-törlés.

## LAN, autentikáció

A rover a már mentett helyi WiFi-hálózatra csatlakozik, nem indít saját AP-t.
A korábban provisionált rover origin/token marad a HC backend privát
konfigurációjában (`MOWER_V3_REMOTE_URL`, `ROVER_API_TOKEN`). A csomag nem
tartalmaz titkot. HTTP Bearer-auth és WebSocket
`homecontrol.mower.manual.v3` protokoll változatlan, backendből használandó.
MOTOR_TEST-ben nincs MQTT/NTRIP/GNSS küldetésútvonal; kézi próbához nem kell RTK.
Egyszerre egy szokásos HTTP job van, plusz külön fenntartott STOP slot.
Szerializáld a GET/POST lekéréseket; túlterhelés nem enged automatikus írásretryt.

## Első konfiguráció – a HC feladata

`config/rover_motor_test.initial.json` **teljes, valid RCP2 ERPM kezdőjavaslat**,
CRC32 `27384620`. Nem compiled default és nem kerül be automatikusan az ESP NVS-be.
A HC importálja saját szerkeszthető draftjába, és explicit kezelői Apply-ból küldi.

Adatforrás: kerékkerület 650/650 mm, nyomtáv 290 mm, test sugár 375 mm,
antenna [0,0,150] mm. A VESC-be a felhasználó 207 mm átmérőt állított.
Az áttétel/pólusszám nem igazolt, ezért mind nulla és a vezérlés nyers eRPM.
VESC ID1 már invertált; roveroldali irányok +1, nincs automatikus dupla invertálás.
IMU [1000000,0,0,0] a megadott x-előre/y-balra **és feltételezett z-felfelé**
szereléshez. Helyileg ellenőrizendő! Kezdő tesztlimitek: 1000 eRPM mindhárom
motoron, rámpák 1000/1000/500 eRPM/s, dőléslimit 25°. Ezek tesztjavaslatok,
nem mért telepítési határok. A fékáram mindháromnál 0 mA, tehát kifutás lehet;
STOP nem fizikai vészleállítás. A gyári 1000 ms / 0 A VESC timeout változatlan.

1. Friss GET identity/STATE/parameters. `runtime_parameters=true`,
   `source_valid=true`, `can_apply=true`, nem busy, aktuális bootok/epoch/revision.
2. Az első konfigurációhoz mindhárom VESC legyen ténylegesen táp alatt és
   sugározzon friss STATUS-t: ID1/2 pontosan 0 eRPM 300 ms, ID3 0 eRPM 1000 ms.
   Native megfigyelési rés >20 ms újrakezdi az ablakot. A kimenet szoftveresen
   tiltott, DISARMED és nincs lease. Kikapcsolt VESC mellett diagnosztika van,
   de nincs config Apply. Ne hamisíts visszajelzést és ne kényszerítsd a kaput.
3. Egyszeri kompakt JSON POST `/api/v3/parameters`: a korábbi hét gyökérkulcs
   (`v,request_id,esp_boot,stm_boot,control_epoch,expected_revision,parameters`),
   benne a teljes 31-mezős RCP2 objektum. Első revision 0. Max 2048 byte;
   duplikált/ismeretlen mező, float, chunked feltöltés elutasított.
4. Csak GET-egyeztetés: friss ACTIVE+applied, pontos request ID/revision/CRC.
   202 csak sorba állítás, NVS ACTIVE önmagában nem STM APPLIED.
5. Konfigurációváltás töröl lease-t, headinget/runtime-ot és új epochot ad.
   Új STATE alapján új explicit ARM/claim kell; nincs auto ARM vagy replay.
6. Újraindítás után a tartós ACTIVE ugyanazon boardhoz helyreállítható, de csak
   ugyanilyen natív stopped/inhibited bizonyítékkal, mindig mozgás nélkül.
   PENDING/FAULT nem törölhető online; szervizes egyeztetés kell.

CFG UART ABI **2**, RCP1/RCP2 formátumleírás és `drive_erpm` részletek:
`HC_AI_HAROM_MOTOR_ATADAS_20261012.md`, `docs/HC_RUNTIME_PARAMETERS_API.md`.
MOTOR_TEST csak RCP2/ERPM konfigurációt fogad. A codec általános CALIBRATED
támogatása nem jelenti, hogy ebben a buildben az alkalmazható.
Tesztbuild plafon: 6000/6000/25000 eRPM; fékáram legfeljebb 5580/5380/2000 mA
a megadott motor-exportok alapján. A kezdőjavaslat jóval kisebb; módosítása HC-adat.

## Kézi vezérlés – operátori műveletként

Friss applied profil és `test_manual_control=true` után:

1. Explicit POST command `arm`, a korábbi hétmezős parancsobjektum, `value:null`.
   Várd meg a korrelált APPLIED-t és a friss IDLE-t. Mindhárom motor álljon,
   az IMU legyen friss és ne legyen aktív/latched fault.
2. Authenticated WebSocket `/api/v3/manual`, majd a változatlan `claim` objektum:
   `type,request_id,esp_boot,stm_boot,control_epoch`. Csak APPLIED/claimed után
   használd a visszaadott `lease_id`, `control_epoch`, `motor_erpm_limits` értékeit.
3. A motorok kezdetben mind 0 célon vannak. Teljes `drive_erpm` snapshot:

```json
{"type":"drive_erpm","lease_id":123,"control_epoch":7,"seq":1,"left_erpm":100,"right_erpm":100,"third_erpm":0,"deadman":true}
```

Ez formátumpélda, nem beküldhető session és nem automatikus próbaindítás.
Küldés csak nyomva tartott deadman alatt, például 50 ms időközzel; lease 350 ms.
Elengedéskor mindhárom cél nulla és `deadman=false`/`stop`, majd explicit release.
Harmadik motor külön kezelői kapcsoló és ugyanaz a deadman/lease, nincs automatikus
felpörgés ARM vagy claim után. A `blade_enabled=true` itt a kés nélküli ID3-motor.
`drive` mm/s/mechanikai-RPM formátumot ERPM módban ne használd.

STOP/DISARM, sessionvesztés, elavult IMU, dőlés, CAN/motorfeedback hiba nullázza
a célokat. A nulla cél rámpa nélkül érvényes, a megállási/kifutási idő fizikailag
nincs igazolva. Reconnect nem reclaim és nem újraküldés. Fault után friss,
tényleges megállási bizonyíték és explicit reset_fault kell; nincs auto-reset.
START, küldetésfeltöltés, heading-set, maintenance/update műveletek zárva.

## Csak olvasó ellenőrzés feltöltés után

```sh
python3 tools/rover_hc_bringup_probe.py --motor-test --url http://ROVER_LAN_IP --access PRIVATE_ACCESS_JSON
```

Kizárólag GET-ek, nincs config Apply, ARM, motorparancs vagy titok a kimenetben.
Két friss, előrehaladó STATE ugyanazon bootpárral, egyező FW-k és nem armed
DISARMED/FAULT az elvárt eredmény. A script sikere nem IMU/CAN/megállásminősítés.
HC oldali teszt: readonly HC_BRINGUP továbbra zárt; új MOTOR_TEST külön út;
üres/stale CFG zárt; explicit Apply/ARM/claim; lost ACK csak GET; deadman/STOP
mindhárom célra; linkvesztés nincs replay; updater zárása ne legyen „javítva”.
