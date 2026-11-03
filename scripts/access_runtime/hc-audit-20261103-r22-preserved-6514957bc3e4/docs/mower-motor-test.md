# HC MOTOR_TEST integráció – 2026-10-12

Forrás: `hc-motor-test-20261012-v2.zip`, elsődleges szerződés:
[roveroldali átadás](rover-motor-test-20261012/HC_AI_MOTOR_TEST_ATADAS_20261012.md).
A ZIP HC-integrációs forrásokat tartalmaz; a felsorolt STM/ESP binárisok nincsenek benne.

## Használat

A **Mower** oldal közvetlenül a MOTOR_TEST hárommotoros próbát nyitja meg.
A régi Bringup, HC-draft, LAN2 és normál üzemi alfüleket eltávolítottuk;
a tesztkonfiguráció szerkesztése és mentése ezen az oldalon maradt. A HC kezdeti, szerkeszthető
`rover-motor-test` draftja revision 1, RCP2/ERPM, CRC **27384620**.
A HC-draft revisionje külön számláló a rover konfigurációs revisionjétől.
A draft mentése nem konfigurálja és nem élesíti a rovert.
A teljes JSON szerkeszthető; a referencia validátor ellenőrzi a 31 mezőt.

1. Helyi, kés nélküli, mozgásbiztos felügyelet. IMU irányát ellenőrizni kell.
2. Mindkét boardon a pontos `esp-motor-test-20261012` / `stm-motor-test-20261012`
   firmware kell. Feltöltés külön roveroldali művelet, a HC ezt nem végzi el.
3. Kezelői bejelentkezés. Mindhárom VESC táp alatt, friss megállási visszajelzés;
   DISARMED, lease nélkül, friss CFG `can_apply=true`.
4. Explicit **Apply**, majd **Apply egyeztetése · csak GET**. A sikerhez friss
   ACTIVE és STM APPLIED, pontos request ID, boots, új revision és CRC szükséges.
5. Új STATE/epoch alapján explicit **Élesítés**, korrelált STM APPLIED és IDLE.
6. Explicit **Kézi kapcsolat kérése**. A három cél alaphelyzetben nulla.
   Bal/jobb eRPM csúszkák; a harmadik motorhoz külön engedélyező kapcsoló kell.
   Mozgás csak nyomva tartott deadman alatt, teljes 50 ms-os snapshotokkal.
7. Elengedés/fókuszvesztés mindhárom célt nullázza és törli a harmadik engedélyét.
   Lezárás release-t küld. Újracsatlakozás nem reclaim és nem mozgás-replay.

Kezdő határok: 1000/1000/1000 eRPM; rámpák 1000/1000/500 eRPM/s;
fékáramok 0 mA, dőléslimit 25°. A kifutás/megállási idő nincs fizikailag
minősítve. A STOP nem fizikai vészleállító. Az eRPM nem mechanikai RPM vagy mm/s.

## Elkülönítés és állapot

`MOWER_V3_READ_ONLY=1` megmarad. `MOWER_V3_MOTOR_TEST_ENABLED=1` csak a pontos,
kompatibilis MOTOR_TEST buildpárhoz, külön tesztképességekhez és friss RCP2/ERPM
konfigurációhoz nyitja meg a szükséges műveleteket. A HC_BRINGUP és a normál
kiadás korábbi csak olvasó beállítása megmarad. START/RESUME/heading/mission és
firmware-módosítás nem nyílik meg ebben a tesztágban.

Az identity `update_locked` és a commissioning/conformance bitek változatlanul
az eredeti értékkel láthatók. Hiányzó updater szolgáltatás diagnosztikai ERROR/lock
állapotát nem írjuk át. Az explicit MOTOR_TEST natív `can_apply`, majd
`test_manual_control`/`manual_erpm` kapuja bizonyítja a tesztbelépést; valódi
locked/sérült/TRIAL history vagy függő OTA esetén a firmware ezeket zárja.
A HC tartós firmware-session zárolása továbbra is blokkol.

A natív MOTOR_TEST STATE hex hibamaszkját és külön SAFE-frissességét önálló
validátor kezeli; a normál motion-admission STATE sémája változatlan.
GET/POST HTTP kérések sorosak. STOP külön út, nem vár az ordinary slotra.
Apply egyszeri küldés; timeout/lost ACK UNKNOWN, csak GET-egyeztetés. A böngésző
előre megőrzi a korrelációt; backend- vagy oldalújraindítás sem küld automatikusan
Apply-t, ARM-ot vagy claimet. Nem egyeztethető bootváltás/PENDING/FAULT szervizes
ellenőrzést igényel, nincs force/erase/online reset vagy néma fallback.

## Ellenőrzés és kihelyezés

Backend: 244 rover teszt, 15 alapból kihagyott környezeti teszt.
A négy PostgreSQL-draft teszt külön, pg_temp/rollback módban szintén átment.
Frontend: 63 teszt és sikeres Vite build; szintetikus WebSocket hooktesztek
ellenőrzik a hárommotoros deadmant, fókuszvesztést, elakadást és replay hiányát.
A draftimport `scripts/import_motor_test_draft.py` kizárólag a HC adatbázisát
érinti, meglévő draftot megőriz, a roverhez nem kapcsolódik.

Az integráció készítésekor az élő rover még az október 10-i HC_BRINGUP párost
jelentette. Nem történt firmware-feltöltés, natív Apply, ARM, claim vagy motorindítás.
A szoftvertesztek nem igazolnak IMU/CAN/hardveres megállási minősítést.
Módosítás előtti forrásmentés: `backups/hc-motor-test-integration-20261012/`.

Kihelyezés után HC health: `ok=true`, `db_ok=true`, `mqtt_ok=true`; az új draft
HTTP-visszaolvasása revision 1 / CRC 27384620 / nem applied. A rover az utolsó
kihelyezés utáni ellenőrzésnél nem volt elérhető; utolsó korábbi élő azonosítása
HC_BRINGUP volt.

## Felületfrissítés javítása – 2026-10-12

A letiltott vezérlőgombok tiltott kurzort kapnak; várakozó kurzor csak a
ténylegesen futó explicit Frissítés gombján jelenik meg. A háttérlekérdezés
nem üríti az előző bizonyítékot átmeneti BUSY válaszra és nem újítja meg annak
idejét: a 1500 ms-os helyi elévülés változatlanul letiltja a vezérlést.
Kérések egymás után: LIVE után 500 ms, STALE/BUSY után 1000 ms, kiesés után
5000 ms; 5000 ms-os HTTP timeout, rejtett oldalon nincs polling.
Ellenőrzés: 66 frontendteszt, sikeres build; BUSY, timeout és láthatóság
viselkedését külön hooktesztek ellenőrzik.

## Dinamikus CFG-képesség és állapot – 2026-10-12

Élő mérésben az identity `runtime_parameters` időnként hamis, miközben a
bootpár változatlan, a STATE sorszáma előrehalad, és friss DISARMED érkezik.
Ezt a HC korábban tévesen INVALID_RESPONSE firmware-azonossági hibának
minősítette, el sem olvasta a STATE-et, majd a frontend 5 s-ra visszavette
a pollingot. A statikus build-azonosság most külön van a dinamikus CFG
képességtől; a STATE önálló frissessége szabályozza az állapotkijelzést.
Apply és manual/ARM továbbra is explicit `runtime_parameters=true` mellett,
a korábbi friss CFG és APPLIED bizonyítékokkal engedélyezett.
Ellenőrzés: 245 backendteszt (15 környezeti skip), 66 frontendteszt; külön
regressziós teszt a friss STATE + hamis runtime-képesség és a zárt Apply/ARM esetére.

A mérés ritka GET HTTP 503-at is mutatott. A rover olvasási slotjának
foglaltságánál legfeljebb egy, 50 ms késleltetésű soros GET retry történik.
Második 503 BUSY diagnosztika; a böngésző a korábbi adat eredeti idejét
megőrizve, a 1500 ms-os határig használja a mintát. Nem történik POST retry,
frissességhosszabbítás vagy hamis állapot. Végső backendteszt: 247 (15 skip).
