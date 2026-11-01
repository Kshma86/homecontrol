# HC átadás — simplify11, 2026-10-13

A roveroldali ESP/STM páros egyszerűsítése elkészült és **mindkét firmware
feltöltve, visszaolvasva, normál indulás ellenőrizve**. Az ACTIVE rev2/CRC27384620
változatlanul APPLIED, a rover DISARMED/hibamentes, UART/IMU/STM POSE friss.
Új Apply, ARM vagy motorpróba nem történt. A telepítés tényleges
eredménye: `artifacts/rover-simplify11-20261013/RELEASE_STATUS.md`.
A HC ezen a gépen nem módosult: az alábbi változásokat a HC fejlesztője kösse be.
HTTP/WS 3.1.0, CFG ABI2 és RCP2 marad; ezek MOTOR_TEST-specifikus bővítések,
nem éles/autonóm engedélyek. Korábbi részletek: `HC_AI_PARAM_UART_ATADAS_20261013.md`.

## Egyetlen „Kézi mód” művelet

GET identity új jelzői:
`manual_claim_from_disarmed=true`, `minimal_erpm_parameters=true`,
`first_configuration_requires_motor_feedback=false`.
A meglévő `test_manual_control=true` képességet és friss kompatibilis natív
állapotot használd. A commissioned/motion_permitted=false és a nem telepített
updater állapota nem általános tiltása ennek a külön MOTOR_TEST útvonalnak.

A már működő, hitelesített `homecontrol.mower.manual.v3` WebSocketen közvetlenül
DISARMED állapotból küldhető a meglévő claim; nem kell külön ARM gomb/lépés:

```json
{"type":"claim","request_id":"<új-egyedi-id>","esp_boot":"<friss-16-hex>","stm_boot":"<friss-16-hex>","control_epoch":123}
```

A `claimed` válasz tényleges lease_id/control_epoch értékével, növekvő seq-val
küldd az ERPM parancsokat. Ne használd tovább a claim előtti epochot.

```json
{"type":"drive_erpm","lease_id":1,"control_epoch":124,"seq":1,"left_erpm":0,"right_erpm":0,"third_erpm":0,"deadman":false}
```

A példák azonosítói/epochjai helyőrzők, nem élő parancsok. Wheel-only menetben
third_erpm=0. Nemnulla célhoz deadman=true kell. Rendszeres, például 50 ms
küldési ütem; az ESP 100 ms-nál régebbi drive-ot eldob, az STM 350 ms kézi
input timeouttal megszünteti a hajtást. Socket- vagy peer-vesztés után új,
explicit kezelői claim kell; korábbi lease/parancs nem állhat vissza.
A korábbi ARM→claim út megmaradt a régi HC-val való együttműködéshez.

Natív claim-kapu: alkalmazott profil, hibamentes és kompatibilis friss peer,
IMU/dőlés és **mindkét kerék** friss feedbackje/300 ms megállásigazolása.
Nem szükséges a használaton kívüli harmadik motor feedbackje vagy megállása.
A STATE összesített stopped=false értéke ezért ne legyen önálló HC kézi tiltás:
a natív STM dönt a wheel-only megállási feltételről. Az első nemnulla harmadik
cél saját friss feedbacket és megállásigazolást igényel; a harmadik motor későbbi
folyamatos frissítése közben nem követelünk újra álló tengelyt.
Harmadik=0 és blade_enabled=false mellett a harmadik motor offline lehet.

## Csak szükséges ERPM paraméterek

GET `/api/v3/parameters` megtartja a korábbi teljes `parameters` objektumot, és friss,
alkalmazott ERPM profilnál hozzáadja a `necessary_parameters` objektumot.
A meglévő Apply végpont/envelope/revízió/CRC/állapotegyeztetés nem változik.
POST-ra továbbra is egyszeri küldés, utána GET-egyeztetés; 202 nem APPLIED.

Kompakt, harmadik motor nélküli konfiguráció pontosan 10 mező:

| Mező | Típus / jelentés |
| --- | --- |
| parameters_version | 2 |
| robot_id | meglévő robotazonosító |
| drive_mode | "ERPM" |
| blade_enabled | false |
| wheel_direction | két irány, a meglévő szerződés szerint ±1 |
| wheel_erpm_limit | két pozitív ERPM-limit |
| wheel_brake_ma | két nemnegatív fékáram, mA |
| motor_accel_erpm_s | két pozitív gyorsulási korlát |
| imu_mount_q_ppm | négyelemű, érvényes mount quaternion |
| tilt_limit_mdeg | érvényes dőlési limit, millifok |

blade_enabled=true esetén 13 mező: a fentiekhez `blade_direction`,
`blade_erpm_limit`, `blade_brake_ma` tartozik, motor_accel_erpm_s **háromelemű**.
A VESC iránybeállítását ne fordítsd meg még egyszer automatikusan a HC-ban.
A teljes régi 31 mezős RCP2 és korábbi RCP1 bemenet továbbra is elfogadott.

**A kompakt objektum teljes csere, nem PATCH:** elhagyott inaktív metrikus,
áttétel-, geometria- és kalibrációs mezők nullára/ismeretlenre bővülnek. Nem
találgatunk motoradatot. A HC hosszútávú draftban őrizze a későbbi adatokat,
vagy küldje a régi teljes 31 mezős objektumot azok megőrzéséhez. ERPM-hez nem
kell RTK/heading/áttétel. A 207 mm átmérő önmagában nem áttételkalibráció.
Letiltott harmadik motor belső inaktív mezői nullák lehetnek: **új konfiguráció
után régi firmware-re downgrade nem garantált**, mentés és külön egyeztetés kell.

MOTOR_TEST-ben a konfiguráció mentése/boot-visszaállítása nem követeli a motorok
tápját vagy megállási feedbackjét. Továbbra sem engedünk konfigurációváltást
hajtás közben: nincs armed állapot, motorintent, lease, update/küldetésfeltöltés.
FAULT lehet nem-hajtó állapot, de a mentés nem törli a hibát. A tartós ACTIVE/
PENDING/CRC/board/peer kötés és valódi flashhibák ellenőrzése megmarad.
Mentés előtti szoftveres kapuelutasítás nem minősít ép tárat hamisan STORAGE_ERROR-nak;
CONFIG_WRITE_BLOCKED külön eredmény. PENDING/UNKNOWN automatikus törlés nincs.

## Visszatérő CAN és UART

CAN_BUS csak akkor törlődik automatikusan, ha a natív CAN/TX egészséges,
az utolsó busz-helyreállítás után friss motor-STATUS érkezett, és ez 300 ms
folyamatosan igazolt, nem hajtó állapotban. Nem ARM-olunk újra, nem tartjuk meg
a régi célt/lease-t. Más hibát (MOTOR_FEEDBACK, TILT, deadline, internal stb.)
nem töröl ez az út. Vegyes hiba esetén a megmaradt okot javítani/resetelni kell.

UART hiba/szakadás után automatikus flush→kerethatár→HELLO→friss kötött STATE,
szükség esetén **csak DISARM**, majd új állapotigazolás történik. Nincs ARM,
motorparancs vagy korábbi parancs replay. Update alatt ez az út nem indul.
Bizonytalan flash/PENDING tranzakciót a link helyreállása nem old fel.

HEALTH mezők: `uart_recovering`, `uart_recovery_attempts`,
`uart_recovery_completed`. A hibatörténet/számlálók kumulatívak: korábbi
uart_faults/native_error önmagában ne legyen örök UI tiltás, ha a helyreállítás
befejeződött, a port nyitott és a natív források ténylegesen frissek.
Helyreállítás alatt nincs kézi engedély; új boot/epoch esetén régi lease-t dobj el.

## HC-tesztek és még nyitott gyakorlati kérdések

Teszteld: közvetlen claim DISARMED-ből; wheel-only harmadik offline mellett;
letiltott harmadik elutasítja a nemnulla célt; IMU stale/tilt, deadman/socket
timeout megállít; kompakt 10/13 és régi 31 mező dekódolás; nincs automatikus
Apply/ARM/retry, CAN/UART helyreállás után nincs régi cél visszatöltése.

A jelenlegi alkalmazott profil limitei 1000 ERPM; az átadott VESC XML-ekben
s_pid_min_erpm=900. Ha ezek futnak a VESC-eken, kis joystickcél nem indíthatja
a motort. Ezt nem HC safety checkbox oldja meg: VESC-minimum/joystickskála/
roverlimit összehangolás kell, nem vak maximumemelés. VESC firmware/beállítás
ebben a munkában nem módosult. Fékáram 0 mA esetén kifutás lehetséges.

IMU/dőlés, friss szükséges feedback, határértékek, timeout/watchdog megmaradt.
Kés nincs felszerelve; ez nem késsel végzett vagy éles/autonóm minősítés.
Standalone MOTOR_TEST: autonóm START, ESP OTA és STM távoli updater nincs
engedélyezve. A későbbi production/VG integráció külön feladat.

## Páros binárisok

`artifacts/rover-simplify11-20261013.zip`

- ZIP SHA256: `7a92294196f47c97e1e079f7a69b96670fa5deccaba8531ea31572348b10380a`
- ESP SHA256: `e7465229556b814750d0d503c3c23217d24515e8ac8d3f3455a6926435349dad`
- STM SHA256: `f0731a7374b4eb386cc1c714bc9509505a333f13c66e7a902ae873dc3a499271`

A firmware dátumos stringjei változatlanok; a simplify11 párt hash/telepítési
jegyzőkönyv azonosítja. A ZIP régi általános motor-test átadása mellett ez a fájl
a frissebb, kiegészítő HC-szerződés. Titok/token/SSID-jelszó nincs ebben a fájlban.
