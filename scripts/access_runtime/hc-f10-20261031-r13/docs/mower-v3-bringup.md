# Új rover-FW élesztése a HC-val

**2026-10-11: a most futó firmware HC_BRINGUP / natív HTTP 3.1.0.**
A Mower tab alapértelmezett, csak olvasó nézete ezt kezeli:
[`mower-hc-bringup-read.md`](mower-hc-bringup-read.md). A checker alapértelmezése
szintén bringup; az alábbi későbbi üzemi/VG ellenőrzéshez `--operational` kell.
`MOWER_V3_READ_ONLY=1` mellett nincs natív vezérlés vagy frissítés.

**Történeti: FIRST_INSTALL_SERVICE / ABI1 LAN2.** Külön választható nézet:
`mower-service-read.md`. Ellenőrzés: `python3 -B scripts/check_mower_v3.py --url
http://127.0.0.1 --service`. Az alábbi üzemi/VG folyamat ettől különbözik;
a szervizprogram nem szolgálja ki az identity/state/update üzemi API-kat.

A ZIP v3.1/VG ABI2 szerződéséhez készült. A HC-tesztek nem hardveres minősítések;
első ellenőrzés mozgásra képtelen, roveroldalon biztonságosan tiltott berendezéssel.
HC nem állít be CAN-módot, nem helyettesíti a fizikai tiltást, nem indít ARM/START-ot.

## Kapcsolat és állapot

1. Az új ESP/STM ugyanazt az operatív 3.1 szerződést és telepített profilt használja.
   Első telepítés/provisioning roveroldali feladat: HC nem bootstrapel távolról
   `stm_remote_update=false` vagy 501-es telepítést.
2. A backend privát konfigurációjába kerüljön a pontos `MOWER_V3_REMOTE_URL`
   origin és a provisionált `ROVER_API_TOKEN`. Nincs legacy URL/token fallback.
3. A külön HC kezelői kapuhoz `MOWER_OPERATOR_PASSWORD_HASH` és
   `MOWER_OPERATOR_SESSION_SECRET` kell. Titkot ne másolj chatbe, böngészőtárba
   vagy parancssori argumentumba. Részletek: `mower-v3-foundation.md`.
4. Konfigurációváltás után backend-újraindítás és új kezelői bejelentkezés kell.
   Maradjon egy backend worker; távoli hozzáféréshez védett hálózat/TLS szükséges.

A repó gyökeréből futtatható, jelszó nélküli, csak olvasó ellenőrzés:

```sh
python3 scripts/check_mower_v3.py --url http://127.0.0.1 --operational
```

Másik gépről a `--url` a HC címe, nem a roveré. Csak HC snapshot, operator-status
és kiadáskatalógus GET történik: nincs login, token, frissítés vagy mozgás. A
configured, STM-frissesség, kompatibilitás és updater-képesség külön eredmény.
Az üres katalógus nem akadályozza az állapot ellenőrzését, a firmware-mentést igen.
A script sikere csak az ellenőrzés lefutását jelenti.

A tabon először a boot/profile, frissesség, állapot és hibák megjelenítését nézd.
Ismeretlen/elavult adat nem megállási igazolás. VG maintenance alatt a STOP
NOT_READY nem APPLIED. Legacy csak inaktív mezőnézet, RTK változatlan. RVM3
küldetésfeltöltés és live paraméterapply nincs bekötve; az editor HC-draftot kezel.

## STM-frissítés a HC-ból

1. A valódi RFU2 `.bin` és hozzá tartozó valódi `.elf` kapjon független szerveroldali
   kiadásjóváhagyást (`mower-firmware-preflight.md`). Kiválasztás/hash önmagában
   nem kiadói jóváhagyás; nincs előre jóváhagyott teszt-FW.
2. Explicit előellenőrzés, kezelői login és mentés a HC-ba. HC_STAGED nem natív frissítés.
3. Válaszd a mentett feladatot: **Session létrehozása — runtime törléssel**.
   Ez eldobja a rover futó küldetését/checkpointját/headingjét/kézi lease-ét.
4. Várd meg a kötött, friss loader READY-t: **RFU2-kép feltöltése — egyszer**.
   A backend újraellenőrzi a katalógust/bytes/ELF-et/profilt, csak a pontos képet
   küldi a roverre, az ELF-et nem. A képfejléc layoutja H743_1M_QSPI_REC2, slot APP.
5. RECEIVING/ERASING/WRITING/VERIFYING/TRIAL/COMPLETE külön fázisok. 202/100%
   bájt vagy TRIAL/APP ACK nem végleges commit. Nincs külön ACTIVATE.
6. Szükség esetén explicit **ABORT**: a zárolás megmarad, megerősített telepítést
   nem von vissza. Terminális COMPLETE/ABORTED/ERROR és friss natív
   `can_finish=true` engedi az explicit **FINISH**-t.
7. FINISH után külön **Normál visszatérés ellenőrzése**. Ez HC-only ellenőrzés,
   nem új FINISH: unlocked IDLE + kompatibilis új STM boot/epoch + friss EMPTY/
   inaktív runtime kell. Fizikai bemeneti FAULT elfogadható visszatérés, nem ARM.
   A HC ekkor zárja tartósan a sessiont és eldobja a régi parancsobjektumokat.

HTTP STATE nem közöl motortargeteket. A nullázás bizonyítéka a rover natív §17.8
restart-barrierje, amely nélkül nem jelenthet unlocked IDLE-t; HC ehhez új bootból
friss EMPTY állapotot is kér. Nincs kitalált target mező/checkbox mint bizonyíték.
Az új FW-nek ezt ténylegesen teljesítenie kell; eltérő sémához új handoff/teszt kell.

## Elveszett válasz / megszakadás

Ne indíts újra feltöltést: tartós küldési szándék + csak GET-egyeztetés van.
Egy native session/action legfeljebb egyszer küldhető, más request ID sem enged
rejtett újrapróbálást. Negatív GET/eltűnt session nem törli a zárolást. Elveszett
create ID esetén tetszőleges roverjob nem vehető át HC-sként.

Friss kötött állapottal támogatott ABORT/FINISH kérhető külön. Boot/profil/endpoint
változásnál nincs automatikus folytatás. Bind nélküli/UNKNOWN esetben explicit
roveroldali/admin egyeztetés kell, nem DB-sor törlés vagy legacy reset.
FINISH utáni elveszett HC-igazolás a művelet GET-jével állítható helyre.
Részletes API/persistence: `mower-firmware-sessions.md`.
