# Rover-paraméterek: rover a forrás, HC a szerkesztő

## Aktuális, boardon ellenőrzött állapot — hw15

Az ESP hw15 javítása **feltöltve és visszaolvasással ellenőrizve**; az STM
változatlan simplify11. A persistence12 GET-kiegészítés is ebben az ESP-ben van.
Sikeres, külön engedélyezett, változatlan értékű mentés: rev2 → rev3,
CRC27384620, `storage=ACTIVE`, `applied=true`, `code=APPLIED`, `busy=false`.
Mindkét írás utáni soros egyeztetés lefutott, nincs UART-hiba vagy flash-zárolás.
Utána normál ESP-restart: **HC-Apply nélkül** ugyanaz a rev3/CRC és ugyanazok az
értékek automatikusan visszaálltak. Induláskor nulla konfigurációs flashírás.
`stored_parameters_valid=true`; a mentett objektum megegyezik az alkalmazottal.
Az IMU friss, a rover DISARMED. ARM vagy motorparancs nem történt.

Bizonyíték: `artifacts/rover-config-flash-hw15-20261013/RELEASE_STATUS.md`,
`INSTALL_READBACK.json`, `APPROVED_SINGLE_APPLY.log`, `BOOT_RESTORE_VERIFIED.json`.
A korábbi félbemaradt kérések lent történeti előzmények, nem aktuális PENDING.
A HC induláskor/editor megnyitásakor csak lekérdez; csak valódi kezelői
változtatáskor ment. Az alábbi API/HC-működési leírás változatlanul érvényes.
Ez felügyelt MOTOR_TEST firmware, nem autonóm/OTA/VG minősítés.

## Korábbi helyreállítási előzmény

2026-10-13-i helyreállítás: a felhasználó engedélyezte a lent tárgyalt függő
kérés elvetését. Az utolsó igazolt rev2/CRC27384620 visszaállt ACTIVE/APPLIED
állapotba normál boot-restore-ral, HC-Apply nélkül. A művelet mentett,
paraméterérték/revízió változás és firmware-feltöltés nem történt.
Jegyzőkönyv: `artifacts/rover-rev2-recovery-20261013/RECOVERY_STATUS.md`.
Az írás utáni flash/UART-barrier egy hibája a helyreállításkor is jelentkezett;
az ACTIVE eredmény rögzítése után normál ESP-indulással állt helyre az alkalmazás.
Ezért a boot-restore sikere nem jelenti, hogy új Apply-ciklus már hibamentes.

## Mi működik már a feltöltött simplify11-ben?

Az ESP saját NVS flashében a `rover-config` névtér `params0`/`params1`
rekordjaiban tárolja a paramétereket. Sikeres Mentés/Apply tartósan commitolja
őket, majd az STM alkalmazza. Nem a HC adatbázisa az egyetlen példány.

Normál induláskor az ESP önállóan beolvassa az utolsó igazolt ACTIVE rekordot,
és az STM-re visszaállítja. Ehhez **nem kell működő HC, POST, új revízió vagy
kezelői aktiválás**. Az STM futó konfigurációja RAM-ban van; a rover tartós
tárolója az ESP flash. Az automatikus helyi restore nem új mentés: nem növeli
a revíziót, nem írja újra az NVS-t és nem engedélyezi a mozgást.

A simplify11 telepítése utáni élő ellenőrzés ezt igazolta: rev2/CRC27384620
új páros booton magától APPLIED lett, HC-Apply nélkül.

## Miért látszott korábban úgy, hogy nincs tárolva?

Korábbi, 2026-10-13-i csak olvasó ellenőrzés: ugyanazon ESP/STM boot mellett egy új HC
kérés (`hc3-mv6x9iv7-j9tn8zjxegq`) félbemaradt. `storage=PENDING`,
`code=CONFIG_RECOVERY_REQUIRED`, `busy=false`, `applied=false`, rev2 és
CRC27384620 továbbra is a korábban commitolt rekordra utal.
Ez nem a normál indulási folyamat és nem bizonyít hiányzó tárolást.
Az új kérés megszakadásának pontos oka ebből a GET-válaszból nem állapítható meg.

A régi GET API csak frissen STM-en alkalmazott konfiguráció esetén ad
`parameters` objektumot; egyébként null. A mentett revízió megmarad, de a
paraméterértékek láthatatlanná válnak. Ez megtévesztő az editor számára.
PENDING esetén a firmware nem emeli aktívvá a bizonytalan módosítást és nem
törli automatikusan. Ezt a korábbi kérést külön engedélyezett roveroldali
szervizműveletben már elvetettük; a HC ne törölje automatikusan a hasonló kéréseket.

## Új, additív GET-kiegészítés — persistence12

Implementálva, tesztelve és a hw15 ESP-ben feltöltve; aktuális állapot:
`artifacts/rover-config-flash-hw15-20261013/RELEASE_STATUS.md`.
A külön persistence12 csomag jegyzőkönyve korábbi, fordításkori állapotot ír le.
Ez a kiegészítés **csak az ESP firmware-t változtatja**, nem a tárolási formátumot
vagy az STM-et. HTTP/CFG szerződés 3.1.0/ABI2 marad. Korábbi mezők jelentése
változatlan, két új mező a hitelesített GET `/api/v3/parameters` válaszban:

- `stored_parameters_valid`: az ESP ellenőrzött, korábban commitolt rekordot
  olvasott ki. Nem STM-freshness, nem APPLIED és nem mozgási engedély.
- `stored_parameters`: az utolsó igazolt, teljes RCP1/RCP2 objektum; az értékekhez
  a meglévő `revision` és `parameters_crc` tartozik. Nem az új PENDING jelölt.

STM-szakadás/újraindulás alatt is olvasható a mentett objektum. PENDING mellett
is olvasható az előző ACTIVE, ha a tár konzisztens és volt ilyen rekord.
EMPTY, hibás/bizonytalan tár vagy első, még nem commitolt konfiguráció esetén
valid=false, objektum=null. Nem gyártunk alapértékeket és nem írunk a GET miatt.
MOTOR_TEST kapcsolat-helyreállítás alatt ez a GET engedélyezett, POST és WS nem;
valódi update-karbantartásban és production izolációban nincs új kivétel.

A régi `parameters` és `necessary_parameters` továbbra is csak friss APPLIED
konfigurációt jelent; `source_valid`, `applied`, `can_apply` továbbra is natív,
élő visszaigazoláshoz kötött. Az olvasható `stored_parameters` nem lazítja ezeket.

## A HC kívánt működése

1. HC indulás, rover újracsatlakozás vagy editor megnyitás: **csak GET**.
   Új firmware-nél stored_parameters_valid=true esetén az editor forrása
   stored_parameters. simplify11 fallback: friss, alkalmazott `parameters`.
   Ha az adat átmenetileg null/stale, ne nullázd a HC korábbi megjelenített
   értékeit, és ne küldj automatikus Apply-t az „aktiválásukra”.
2. A rover commitolt konfigurációja az igazodási alap. A HC saját mentése draft
   vagy gyorsítótár, nem automatikusan erősebb a rover revíziójánál.
   Helyi, még nem mentett szerkesztést ne írj felül pollból; mutass különbséget.
3. Ha nincs valódi értékváltozás, nincs POST és nincs revíziónövelés. A form
   elküldött mezőit a kanonikus RCP-adatokkal hasonlítsd össze, ne JSON-kulcssorrenddel.
   Referencia: `tools/rover_parameters.py` `encode()`/`checksum()`.
4. Csak a kezelő **Mentés roverre** művelete indítja a meglévő POST
   `/api/v3/parameters` műveletet. Ez ment és alkalmaz: nem kell külön későbbi
   „aktiválás” gomb vagy minden újraindulás utáni Apply. Előtte friss GET-ből
   származó boots/control_epoch/expected_revision és can_apply szükséges.
5. A 202/QUEUED még nem siker. GET-tel várd meg az ACTIVE/APPLIED, várt
   request/revision/CRC állapotot. Elveszett válaszra nincs automatikus POST retry.
   Konfliktusra új GET és különbségkijelzés, nem automatikus HC→rover felülírás.
6. Normál rover-újrainduláskor csak várd meg a helyi restore végét. Változatlan
   revízió a helyes eredmény; a korábbi request ID megmaradhat. Új boot nem
   jelenti azt, hogy a paramétereket ismét el kell menteni.

A rövid 10/13 mezős objektum továbbra is teljes csere, nem PATCH: inaktív,
elhagyott adatok nullázódnak. Ha a szerkesztő csak néhány mezőt módosít és meg
akarja őrizni a többi hosszútávú adatot, a GET-ből klónozott teljes 31 mezős
RCP2 objektumon végezze a módosítást. Ne keverje a HC draftot automatikusan
a rover újabb revíziójára. Részletek: `HC_AI_EGYSZERUSITES_ATADAS_20261013.md`.

## Minimum HC tesztek

- HC restart/editor megnyitása: GET-ek, nulla POST.
- Rover reboot: változatlan revízió, HC nélküli automatikus helyi restore.
- STM átmenetileg offline: mentett adatok láthatók, applied/can_apply=false.
- Egy valódi módosítás: egy POST, tartós commit, GET-ben igazolt új revízió.
- Nem változott semmi: nulla POST és revíziónövelés.
- PENDING: előző mentett értékek megjeleníthetők, de nem látszanak élő APPLIED-nak;
  nincs újraküldés vagy automatikus függőkérés-törlés.

PENDING helyreállítása továbbra is külön, állapotot módosító szervizművelet.
Ez a dokumentum nem engedélyez automatikus elvetést vagy újraküldést a HC-nak.
