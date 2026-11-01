# HC-06 kiegészítés: szunnyadó CO- és füstérzékelők

## Nyitásérzékelő-kiegészítés – 2026-10-27

Az `hc-opening-events-20261027-r4` az eseményvezérelt kontaktokra is különválasztja
az utolsó állapotot és a rádiós jelenlétet. A korábbi 300 s-os kontaktkorhatár
téves sárga jelzést okozott öt percnél tovább nyitott konyhaablaknál. A tárolt,
ismert, nem retained nyitásjelzés online rádió mellett továbbra is nyitást
igazol; a zárás azonnal megszünteti ezt. Offline/ismeretlen rádió, hiányzó,
hibás, jövőbeli vagy retained jelzés nem igazol nyitást. A rádiós jelenlét
meglévő határa 6 óra; az értékelés nem ír át eseményt vagy időbélyeget.
Az alábbi 2026-10-23-as leírás 300 s-os kontaktkorhatárát ez a kiegészítés
felülírja; a teljesítmény és a parancsvisszajelzés korhatára megmaradt.

[Kiadás, tesztek és visszaállás](../backups/releases/hc-opening-events-20261027-r4/DEPLOYMENT.md).

## A 2026-10-23-as CO-/füstkiegészítés

2026-10-23: a kezelő pontosítása szerint a két bekötött érzékelő eseményvezérelt.
Hónapokig nem feltétlenül küldenek új riasztási értéket, miközben a Zigbee
rádiós jelenlétük látható. Ezért a korábbi, közös 300 s méréskorhatár nem
megfelelő a CO-/füstállapot minősítésére. A kiegészítés **élesítve: 2026-10-23 20:51:59 CEST**,
kiadás: `hc-sleeping-20261023-r2`, az r1 célzott kiegészítéseként.
HC-07/38 nem került az éles kiadásba.

## Állapot és elérhetőség

- A legutóbbi érvényes CO-/füstjelzés és az elérhetőség külön bizonyíték.
  A változatlan jelzés nem jár le pusztán az idő múlása miatt. Rádiós ellenőrzés,
  GET, restart vagy ACK nem módosítja és nem teszi frissebbé a jelzési időbélyeget.
- Normál/nyugtázható állapothoz ismert, érvényes utolsó jelzés **és igazolt
  rádiós jelenlét** szükséges. A jelenlegi `AdminService.zigbee_radio_status`
  a Zigbee2MQTT `lastSeen` mezőjét olvassa, meglévő határa 6 óra. Ezen most
  nem változtattunk. Ez külön határ, nem CO-/füstmérés-periódus.
- A rádiós jelenlét nem jelent önmagában „nincs riasztás” állapotot: hiányzó,
  ismeretlen, hibás, jövőbeli, retained vagy ismeretlen-retain jelzés nem ad
  nyugtázási engedélyt. A CO fault=true/ismeretlen fault szintén blokkol.
- Offline/ismeretlen rádiónál az utolsó érték megmarad, de nem igazol ismert,
  működő védelmi bemenetet. A kézi ACK tiltott. Pozitív riasztást az offline
  állapot és az idő múlása sem töröl.
- Új pozitív CO-/füstjelzés, illetve veszélyszintű CO esetén a worker reteszel.
  A későbbi tiszta jelzés nem oldja fel automatikusan: külön, kezelői ACK kell.
  A rádiós visszatérés sem nyugtáz automatikusan.

A CO-/füstesemény továbbra is véges, nem jövőbeli DB-időbélyeget, ismert
értéket és explicit `meta.retained=false` jelölést igényel az ACK-hoz. A CO
numerikus eseményét időbélyeg alapján csak egyszer dolgozzuk fel trendként;
egy ismételt worker-tick nem új CO-emelkedés.

Az elszívó teljesítményére és a levegő-utánpótlás nyitásérzékelőire megmaradt
a `COMBUSTION_INPUT_MAX_AGE_SECONDS` (jelenleg 300 s). A parancs-visszaigazolás
külön korhatára és a worker snapshot 5 s-os frissessége is változatlan.
A szunnyadó szenzorok kezelése nem teszi korlátlanná ezeket a visszajelzéseket.

## Ingest és kezelőfelület

Az ingest ugyanazzal a `should_write` döntéssel ritkította az aktuális állapotot
és a történetet. A `smoke` nem szerepelt az azonnal mentett változások között;
így a korábbi szabály még false→true változást is kiszűrhetett. A numerikus CO
deadband/min-interval pedig kis küszöbátlépést nyomhatott el.

A `carbon_monoxide_value/co/co_ppm` és `smoke/smoke_alarm/fire/alarm` változásai
most a már meglévő CO alarm/fault változásokhoz hasonlóan a min-interval és
deadband előtt átjutnak. Riasztás és tisztulás is mentendő. A tiltott szabály
továbbra is tiltott; változatlan érték és más metrikák ritkítása megmaradt.
Nem gyártunk mesterségesen új eseményt a rádiós heartbeatből.
Újraindításkor az azonos retained visszajátszás megőrzi a már tárolt esemény
értékét és provenance-át, lejárt max-interval mellett is. A retained clear/decrease
nem törölhet riasztási bizonyítékot. Pozitív retained alarm/numerikus emelkedés
konzervatívan feldolgozható, de retainedként nem enged ACK-ot. Első retained
állapot után az azonos értékű, ténylegesen élő üzenet is azonnal megerősítheti
az állapotot; a forrásjelölés cache-ből visszaáll újraindításkor is.

A worker a rendes tick során olvassa az elfogadott állapotot. Nem vezettünk be
új tartós eseménysort vagy garantált végponttól végpontig határidőt. A korábbi
batch/reconnect és worker-I/O auditpontok változatlanok.

Az admin safety panel külön magyarázza az eseményvezérelt működést, mutatja a
CO-/füst rádiós észlelésének idejét, és jelzi az ismeretlen/hibás bemenet miatti
ACK-tiltást. A meglévő ACK-gomb ugyanazt a szerveroldali `input_health` döntést
használja. Nem kerül a klienshez új állapotdöntési vagy feloldási jog.

## Ellenőrzés

- 617 különálló backendteszt, 0 failure/error/skip, a PostgreSQL-es korábbi
  auditregressziókkal együtt. Hat új unit-eset lefedi a féléves csendet, az
  offline/ismeretlen rádiót, hibás/retained/hiányzó adatot, új riasztást és
  tisztulást, CO-trendet és a folyamatos visszajelzések változatlan korhatárát.
- Az ingest 9 safety unit-esete, 3 meglévő floodtesztje és 1 valódi PG-integráció
  együtt 13 sikeres teszt. Az integráció a tényleges ingest-függvényeket és safety
  szolgáltatást használja: régi adat → rádiós jelenlét → kézi labor-ACK →
  füstjelzés → tiltott ACK → tisztulás → rádiós kiesés → tiltott ACK → visszatérés
  → ACK; továbbá 19,9→20,1 ppm küszöbátlépés nagyobb deadband/min-interval mellett.
  Az aktuális állapot, mérési történet és tartós latch is ellenőrzött.
- A korábbi éles diagnosztika csak olvasva mentett mintáinak offline,
  memóriabeli újrajátszásában a régi CO-/füstérték és igazolt rádió együtt
  nyugtázható lett. Valós ACK, DB-írás vagy MQTT-publikálás nem történt.
- 87 frontendteszt és Vite production build sikeres. Az eredeti audit és a
  HC-07/38 migrációs fájlok változatlanok.

Bizonyíték: `/tmp/hc06-sleeping-repair`, részletes napló: `AUDIT_REPAIR.md`,
REPAIR-010. A PG-integráció csak explicit `HC06_SLEEP_TEST_POSTGRES=1` mellett,
a `HC06_SLEEP_TEST_DATABASE_URL` által megadott `127.0.0.1/hc06_sleeping_test`
eldobható DB-n fut. A tényleges kapcsolati DB-nevet is ellenőrzi, mielőtt
**a saját HC sémáját törli**. Más DB-re vagy éles rendszerre nem futtatható.

## Éles bevezetés és visszaállás

Az r1 fagyasztott forrására célzott backend + ingest + frontend módosítás
élesítve, új DB-migráció nélkül. A tényleges r2 forráson **580 backend-,
13 ingest/PG- és 87 frontendteszt**, frontend build, teljes friss dump restore
és valódi MQTT/ingest/WSGI r2 → r1 → r2 próba sikeres. A korábbi 617-es backendkör
a HC-07/38-at is tartalmazó munkafára vonatkozott; a két kör nem összeadandó.

Az éles ellenőrzéskor a CO-/füst/fan bemenet elfogadott, danger=false;
latched=true, acknowledged_at=null. **Éles ACK nem történt.** A DB és broker
nem indult újra, a kezelői konfiguráció megmaradt. A HC-07/38 munkafaváltozások
nem kerültek bele a kiadásba.

A jelenlegi kiadás, egyparancsos visszaállás és read-only ellenőrzés:
[DEPLOYMENT_PREP.md](../DEPLOYMENT_PREP.md),
[részletes kiadási napló](../backups/releases/hc-sleeping-20261023-r2/DEPLOYMENT.md).
Az r1-re visszaállás a korábbi 300 s-os ACK-korlátot és ingest-szűrést is
visszahozná; egy későbbi r2-re visszatérés új élő szenzormegerősítést igényelhet.
DB-visszatöltés, metadata-átírás vagy a tartós retesz törlése nem része a rollbacknek.
