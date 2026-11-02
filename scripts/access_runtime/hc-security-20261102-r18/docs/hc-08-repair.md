# HC-08 — scheduler-audit és explicit klímaküldés

2026-10-27. A javítás helyi, nincs élesítve. Az éles korlátozott r6 változatlan.
Audit: `HC_REFACTOR_AUDIT.md` HC-08, F0/F4, az F2/F3 előfeltételekkel és az M.7
event→plan leltár bizonyítási határával. Napló: AUDIT_REPAIR.md REPAIR-028.

## Eredmény

Az audit-előkészítés és a klíma publikálása külön lépés. Egy run, event, plan
és execution rövid, READ COMMITTED tranzakcióban készül, kulcsonkénti
tranzakciós advisory lockkal. Az app friss, dict-row hc_app kapcsolatra köti
az adaptert; a megosztott service callbackjei nem változnak tranzakció közben.
Locktimeout 5 s, statementtimeout 10 s. Az új út nem módosítja az általános
DB-wrapperláncot. Kapcsolat-/teljes callback-határidő HC-13 külön feladat.

Új hiba esetén a teljes lánc rollbackel; ismételt tick az eredeti mentett
payloadot használja. A recovery 50-es batchben, esedékességi időtől függetlenül
pótol hiányzó láncrészeket. Duplikált plan/execution explicit hibát jelent;
nem töröljük és nem választjuk ki valamelyiket találomra.

A régi, hiányzó executiont az előző kód küldés előtt nem rögzítette, ezért a
régi kimenet nem bizonyítható. A pótlás `unknown`, replay-tiltott, eredeti
requested_at szerinti created_at időponttal. Nem válik mai végrehajtható feladattá,
és a jelenlegi X10-eredménymarker nem írja sikerre. A már meglévő sorok megmaradnak.

## Klímás szándék állapotai

| Állapot | Jelentés | Automatikus küldés |
|---|---|---|
| shadow_ready | Előkészítéskor a klíma végrehajtása tiltott | nincs |
| pending | Új protokoll szerint commitolt, még le nem foglalt szándék | csak az eredeti run percében, újraellenőrzött engedélyekkel |
| unknown, attempt=1 | Claim commitolt; küldés kimenete még vagy végleg bizonytalan | újraküldés nincs |
| sent | A meglévő publisher sikert jelzett | újraküldés nincs; ez nem fizikai confirmation |
| blocked | Lejárt perc, tiltott domain/global flag vagy eltérő topic | nincs |
| unknown, audit_recovered | Hiányos legacy lánc auditpótlása, nem bizonyított régi kimenet | nincs |

A claim sikeres commitja után, DB-tranzakción kívül történik a publish és a
meglévő automatikus ventilátorszinkron. Elveszett claim-commit válasz esetén
nem indul I/O. Küldés, ventilátorművelet vagy eredménymentés közbeni hiba után
a durable unknown megakadályozza a vak ismétlést. A fizikai állapot egyeztetése
operátori feladat, nincs automatikus uncertain→pending átírás.

A scheduler sorrendje: tisztán naplózó audit → külön klímás dispatch → meglévő
öntözési start → meglévő X10 szinkron. Mindegyik callback hibahatára külön.
A független stop/recovery worker és a safety prioritása megmarad.

## Bizonyíték és ellenőrzés

- A mentett régi kód fake reprodukciója: publish az execution insert előtt;
  meglévő run esetén nincs folytatás a hiányzó láncon.
- READ ONLY éles leltár: 295 run, 292 event/plan/execution; 3 július 13-i run-only
  lánc (X10 start, öntözés start/stop), 0 scheduler-plan/execution duplikáció.
  Egy régi physical_manual sessiont külön rögzítettünk, nem módosítottunk.
  Ez a leltár nem friss fizikai öntözési állapotvizsgálat.
- 282 kapcsolódó teszt, 0 hiba/kihagyás; ebből 25 új valódi PG16-os HC-08 teszt
  hc_app szerepkörrel. A négy insert megszakításait négy domain/action ágon,
  a kétkapcsolatos foglalást/küldést, commit-/publish-válaszvesztést, restartot,
  tiltást, lejáratot és DST/napi deduplikációt is ellenőrzik.
- Valódi auditmásolat izolált recovery: +3 event/plan/execution, +0 run,
  minden eredeti sor változatlan; második recovery 0, publish/Power Wall hívás 0.
- Az érintett régi öntözési SQL-, startup/safety-, klímaablak-, MQTT- és
  AI-offline profiltesztek is részei a 282-nek. Frontend nem módosult.

Tartós, titokmentes eredmények: [bizonyítékok](audit-evidence/hc08-20261027/).
A nyers auditmásolat és tesztnaplók `/tmp/hc08-20261027/` alatt vannak;
a nyers másolat a 0700/0600 `private/` könyvtárban marad, nem része az exportnak.
A tesztkonténerek a saját, network-none PG16 hálózati névterét használják,
nincs hostport, LAN vagy Docker socket. A saját tmpfs DB a végén törölve.

A célzott PG-próba kizárólag eldobható helyi `hc08_audit_test` adatbázissal:

```bash
HC08_TEST_POSTGRES=1 \
HC08_TEST_DATABASE_URL=postgresql://homecontrol@127.0.0.1/hc08_audit_test \
PYTHONPATH=infra/backend \
python3 -m unittest tests.test_scheduler_audit_postgres tests.test_scheduler_service tests.test_startup_service
```

A név/host ellenőrzése védi a fixture-t, de a futtató felelőssége, hogy ez a
DB valóban eldobható és elkülönített legyen. A fixture törli a saját auditadatait.

## Függőségek, későbbi átadás és rollback

HC-09/F3 marad nyitott: Paho timeout pontosítása, friss klíma-visszajelzés,
X10 confirmation. A `sent` állapot csak a jelenlegi publisher válasza, fizikai
pontosan-egyszer végrehajtást nem garantálunk. HC-35/36 binding és régi ventilátor-
szándék nem módosult. HC-03/04/07/38/39 meglévő szerződéseire építünk; új migráció
nincs. A physical_manual kivétel változatlan.

A következő kiadásnak együtt kell tartalmaznia a scheduler_audit.py, app.py,
scheduler_service.py és startup_service.py fájlokat. A bevezetés előtt friss
előállapotmentés, lánc-/duplikáció-/nyitott művelet-leltár és a régi scheduler
leállítása szükséges. Vegyes régi/új writer nem megfelelő, mert a régi kód nem
ismeri a kulcsonkénti lockot és az új küldési protokollt. A korlátozott AI-profilt
és a már éles opening-events safety-javítást meg kell tartani.

Programrollback nem tölthet vissza régi dumpot, nem törölhet uncertain állapotot
és nem adhat újra replay-jogot egy claimelt szándéknak. Pending/unknown fizikai
művelet mellett előbb állapotegyeztetés kell; a régi scheduler nem tudja
folytatni az új pending szándékot. A most éles r6 rollback helperje a jelenlegi
r6-hoz tartozik; a későbbi HC-08 kiadás saját kompatibilis átadást igényel.
