# HC rovertiltások auditja – 2026-10-13

A jelenlegi MOTOR_TEST ág forráskódjának áttekintése. Ez nem pillanatnyi
hardverállapot-mérés és nem védelemkikapcsolás. Kódot vagy konfigurációt az audit
során nem változtattunk. A natív STM elutasításait külön kell kezelni a HC
saját adminisztratív és felületi zárolásaitól.

## Műveletenkénti kapuk

| Kapu | Mit blokkolhat? | Hol / feltétel |
|---|---|---|
| Rover hozzáférés | Natív lekérések és írások | MOWER_V3_REMOTE_URL / ROVER_API_TOKEN hiánya, hibás formátum, kapcsolat/auth/redirect/HTTP hiba |
| Kezelői hozzáférés | HC-draft mentés, Apply, parancsok, kézi WebSocket, STOP | Jelszóhash + session secret, bejelentkezett cookie, 1 órás session; backend újraindításkor a memóriában lévő sessionek elvesznek |
| Origin és login rate limit | Bejelentkezés és írás | Az Origin és a Host egyezése; 5 próbálkozás/60 s; legfeljebb 32 megőrzött session |
| Üzemmódkapcsolók | Rover írások | Read-only tiltás; külön MOTOR_TEST engedély szükséges a kivételhez |
| Pontos buildazonosság | MOTOR_TEST integráció | Fix ESP/STM firmware-nevek, 3.1.0, 4D545331 profilazonosság, flash-kiosztás, protokoll, [1,2] codecverziók, tesztüzemi capability/commissioning bitek |
| STATE frissesség | Új vezérlés és meglévő kézi session | Érvényes, előrehaladó STM-forrás; legfeljebb 1500 ms; megfelelő boot/epoch; ismételt sorszám nem újít frissességet |
| CFG frissesség | Apply és ARM/claim képessége | runtime_parameters=true, available/source_valid; legfeljebb 1500 ms; STATE-tel egyező boots/epoch |
| Konfiguráció állapota | ARM és kézi vezérlés | RCP2/ERPM, ACTIVE + applied=true, nem busy, teljes valid paraméterobjektum és helyes CRC; manual_erpm és test_manual_control |
| Apply állapotkapu | Konfiguráció alkalmazása | DISARMED, armed=false, stopped=true, nincs lease, can_apply=true, EMPTY/ACTIVE, nem busy, nem feltöltés közben; bezárt kézi kapcsolat |
| Paramétervalidáció | Mentés és/vagy Apply | 31 teljes RCP2 mező, egész számok, irányok/kvaternió/limitek, inaktív metric mezők nullák; Apply legfeljebb 2048 byte és motoronkénti fékáramplafon |
| Draftverzió/CAS | HC-draft mentés | PostgreSQL elérhetőség, rover_key, request_id, expected_revision; verzióütközés vagy UNKNOWN mentés esetén GET-egyeztetés |
| Függő HC Apply | Új Apply, ARM/claim; UI-ben további gombok | Tartós pending ledger; siker pontos GET bizonyítékkal; bootváltás utáni megszűnés csak friss, nyugodt natív helyreállási bizonyítékkal |
| Apply ledger tárolhatósága | Új Apply | Privát ledger írása/fsync/atomikus cseréje; hibás ledger induláskor is megakaszthatja a szolgáltatást |
| 128 eltárolt Apply-kérés | Minden további új Apply | Az összes eltárolt kérés számít, a lezártak is; jelenleg nincs archiválás/ürítés |
| Ismeretlen parancseredmény | UI-ben ARM/reset_fault és új claim | Böngészőben tárolt PENDING/UNKNOWN parancsok, unresolved=true; automatikus GET csak az első 10 s-ban, utána kézi egyeztetés |
| Parancsledger telítődése | Backendben új normál parancsok | 128 rekord és nincs archiválható terminal rekord; STOP kivételt kap |
| Firmware-session | Üzemi állapotlekérés és normál vezérlés | Tartós aktív frissítési session; a frissítési tároló ellenőrzési hibája is tilt, MOTOR_TEST-ben is |
| Böngésző régi firmware-intentje | MOTOR_TEST STATE/fresh és vezérlés is | Az updater hook MOTOR_TEST-ben sem hagyja figyelmen kívül a sessionStorage pending/actionPending maradványát |
| HC helyi szerkesztő állapota | Kézi session és parancsgombok | configurationBlocked = busy vagy pending Apply vagy pending HC-mentés; a busy az egyszerű draftmentésre is igaz |
| HTTP / műveleti foglaltság | Rövid időre egyes lekérések, Apply/claim/parancsok | Közös ordinary activity_lock, HTTP lock, konfigurációs lock, egyetlen kézi relay tulajdonos; STOP külön natív küldési út |
| Claim belépés | Kézi kapcsolat | Friss IDLE + stopped, megfelelő boots/epoch, nincs feltöltés, manual capability, bejelentkezés, nincs UI parancs-UNKNOWN |
| Lease / deadman / seq | Kézi motorparancsok | 350 ms lease, monoton seq, pontos lease_id/epoch, csak teljes korlátozott eRPM snapshot; deadman=false esetén minden cél nulla |
| Böngésző környezete | Kézi mozgás vagy teljes session | Fókuszvesztés nulláz; rejtett oldal lezár; logout/állapot/boot/epoch váltás lezár; nincs automatikus reconnect-claim/replay |
| WS pufferek | Kézi session | Már bufferedAmount>0 lezárást okoz; backend max 4 várakozó frame, 40 frame/s, 512 byte/frame, 100 ms bemeneti frissesség |
| MOTOR_TEST funkciók kizárása | START/RESUME/heading/mission/update | A tesztágban szándékosan nem elérhető normál autonóm/telepítési út |

## Biztosan javítandó HC összekapcsolások

1. **HC-draft mentése megakaszthatja a mozgást.**
   MowerMotorTestConfig minden busy/savePending állapotot configurationBlocked-ként
   ad át. MowerV3 ezt a kézi hook authenticated értékébe kötötte. A hook ilyen
   változásra nulláz és release-szel lezár. Egy adatbázis-draft mentése nem változtatja
   a rover aktív konfigurációját; itt a mentési és mozgási állapotot szét kell választani.

2. **128 lezárt Apply után sincs új Apply.**
   MotorTestService.apply a teljes tartós requests dictionary hosszát ellenőrzi.
   A terminal APPLIED/REJECTED/CANCELLED sorok nem kerülnek ki belőle. Ez nem
   fizikai biztonsági kapu, hanem ledger-életciklus hiány. Archiválás és külön
   idempotencia-megőrzés szükséges, nem az egész ledger törlése.

3. **Régi firmware UI-maradvány lezárja a MOTOR_TEST nézetet.**
   Az updater hook ugyan disabled autentikációval/pollinggal fut a tesztágban,
   de a helyi korábbi intenteket továbbra is betölti és blocked=true-t adhat.
   A különböző üzemmódok helyi felületi állapotait szét kell választani; egy valódi
   aktív rover/HC firmware-session ellenőrzése ettől még megmarad.

4. **Korábbi, már nem aktuális UNKNOWN parancs túl szélesen blokkol.**
   A UI unresolved minden megőrzött, nem terminal parancsra igaz, időkorlát nélkül.
   Az ARM és reset_fault gomb, valamint a claim emiatt tiltott maradhat. A request
   bootjához, aktuális műveletéhez és egyeztetett kimenetéhez kell kötni a blokkolást.
   Egy bizonytalan írásról nem szabad pusztán timeout miatt sikert vagy törlést kitalálni.

5. **STOP UI-je túl sok normál admissiont örököl.**
   A backend STOP útja elkülönített, nem kér friss STATE-et. A felület azonban
   controlOperator/configured értékeit a normál controlsEnabled alapján képezi,
   ezért egy hibás/hiányos snapshot az azonosított teszt-rover STOP gombját is
   letilthatja. A STOP-nak külön jogosultság- és hozzáférési feltétel kell.

## Felülvizsgálandó szigorítások

- **Bármennyi WS bufferedAmount azonnali bontás.** A minimális átmeneti küldési
  várakozás nem feltétlenül kapcsolatvesztés. Idő- és méretkorlát, latest-only
  küldés és a natív lease-deadman megtartásával lehet toleranciát vizsgálni.
- **Fix firmware-dátum és minden identity-bit kötelező egyezése.** Egy új,
  kompatibilis MOTOR_TEST build is lezárható. Explicit támogatott release-lista
  vagy verziózott capability-szerződés jobb, mint pusztán a stringellenőrzés elhagyása.
- **STATE-kijelzés függ a CFG-válasz validációjától is.** A CFG lekérés hibája
  jelenleg a snapshot egészének frissességét is elronthatja. A STATE saját
  bizonyítékát külön kell megtartani, az Apply/ARM CFG-kapuit külön zárni.
- **Frissítési adatbázis hibája az állapotkijelzést is megállítja.** Diagnosztikai
  GET és mozgási/frissítési engedély különválasztása indokolt; a valódi, bizonytalan
  firmware-session zárolását nem szabad automatikusan figyelmen kívül hagyni.
- **Elakadt normál parancs-fetch busy-t tarthat fenn.** A useMowerCommands.submit
  HTTP-kérésén nincs saját AbortController timeout. Az eredményt UNKNOWN-ként
  megtartó, korlátos kérés szükséges, automatikus POST retry nélkül.

## Megtartandó védelmek

Hitelesített motorvezérlés; új boot/epoch után új explicit ARM/claim; valid
aktív konfiguráció; eRPM plafon; deadman és 350 ms lease; elavult parancsok és
replay kizárása; Apply mozgás és lease nélkül; egyetlen kézi tulajdonos;
valódi firmwarefrissítés és normál mozgás kizárása.

Az IMU_STALE, TILT, motorfeedback/CAN, stopped bizonyíték és a natív kimenettiltás
STM/roveroldali kapuk. A HC az elutasítást közvetíti. Az IMU_STALE kapu a kapott
firmwareforrásban legfeljebb 250 ms-os IMU-mintát kér; ez nem HC-adminisztratív
beragadás. Ezekhez fizikai/firmware adatút-ellenőrzés kell, nem felületi feloldás.

## Korábban javított hibák

A hiányzó kezelői hozzáférés; a runtime_parameters hamis értékének hibás firmware
azonosságként kezelése; a BUSY állapotra történő kijelzésürítés; a régi boothoz
kötött Apply HC-zárolásának GET-egyeztetése. Ezeket nem soroljuk aktív kódhibaként
az auditban. Azonos booton nem egyeztethető Apply továbbra is UNKNOWN maradhat.

Források: infra/backend/mower_motor_test.py, mower_v3_service.py,
mower_v3_commands.py, mower_manual_service.py, mower_operator_auth.py,
mower_firmware_updates.py; infra/frontend/src/features/mower/MowerV3.jsx,
MowerMotorTestConfig.jsx, MowerV3Controls.jsx, useMowerCommands.js,
useMowerManual.js, useMowerUpdateSession.js, mowerV3Model.mjs.
