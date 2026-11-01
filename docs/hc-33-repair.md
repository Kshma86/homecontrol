# HC-33 — Biztonságos ingest batch-kezelés

2026-10-28. **Élesítve az r9 ingesttel, 22:13:26 CET; 062 migráció alkalmazva.**
[Éles ellenőrzés és visszaállítás](../backups/deployments/hc-ingest-20261028-r9/DEPLOYMENT.md).
A HC-33 bizonyítéka, az audit F10 lépése és a HC-11 helyi javítása alapján.
Az alábbi leírás a HC-33 önálló javításkori állapotát és ellenőrzéseit rögzíti;
a későbbi HC-34 javítást és közös élesítést az r9 átadási napló tartalmazza.

## A mentés szerződése

A mérési sor nem ürül ki az SQL előtt. Minden befogadott mintának stabil UUID-ja
van; többoldalas mentése egyetlen explicit PostgreSQL-tranzakcióban történik.
A sor és a végleges `last_saved` deadband-cache csak pozitívan visszaigazolt
COMMIT után lép tovább. A mintához kötött current-state írás és a fizikai kézi
szelep meglévő session-követése ugyanehhez a tranzakcióhoz tartozik.

A `both` mintákat a teljes MQTT-üzenet feldolgozásának végén mentjük; a DB-worker
kontaktus-flush-a ugyanígy menti a stabil éleket. A state nem vár a history-only
batch 2 másodperces időzítőjére. A kizárólag történeti szabályok megtartják a
méret-/időalapú batchinget. A függő minták külön, átmeneti döntési alapot adnak
az intervallum-/deadband-szűrésnek; nem minősülnek tartósan elmentett mintának.

A szándékos, historynál sűrűbb élő feedback-frissítés megmarad: új current-state
érték létezhet ritkábban mintavételezett history mellett. Ez a szabály szerinti
szűrés; egy elfogadott `both` minta history/state párja viszont együtt commitol.
Ugyanazon kulcs korábbi függő history/state mintája előbb mentődik, mint egy
későbbi state-only feedback-frissítés, így nem írhatja felül az újabb állapotot.

A kapcsolathibát (`OperationalError`, `InterfaceError`) nem alakítjuk soronkénti
fallbackké. Eljut a HC-11 recoveryhez, a már befogadott minták azonosítóikkal
megmaradnak a korlátos history-sorban. A következő kapcsolat előbb ezt rendezi,
majd bemelegíti a cache-t, és csak utána fogad új MQTT-adatot. Ez nem az eredeti
MQTT-üzenet újrafuttatása, és nem a kiesés alatt eldobott üzenetek replaye.

Ha a COMMIT megtörtént, de a válasza elveszett, a következő próbálkozás azonos
UUID-val `ON CONFLICT DO NOTHING`-ot használ. A history nem duplázódik, a már
commitolt state/session művelet nem fut le újra. A minták history- és párosított
state-időbélyege az eredeti fogadás időpontja, nem a helyreállításkori `now()`.

Kizárólag SQL-adathiba (`DataError`, `IntegrityError`) indít izolálást: előbb a
teljes korábbi batch visszagördül, majd soronkénti savepoint választja le a hibás
mintát és a hozzá tartozó state-műveletet. A többi sor együtt commitolhat. A hibás
adat számláltan kiesik; a legutóbbi SQLSTATE megfigyelhető. A meglévő
`PRIMARY KEY(entity_id,ts,key)` megmarad: azonos entitás/kulcs/fogadási időpont
ütközése is ilyen adathiba. Nem írjuk át önkényesen az időpontot és nem módosítjuk
visszamenőleg a történeti adatszerződést.

## Korlátok és megfigyelhetőség

| Környezeti változó | Alapérték |
| --- | --- |
| `INGEST_MEASUREMENT_MAX_MESSAGES` | 1000 |
| `INGEST_MEASUREMENT_MAX_BYTES` | 8388608 |
| `INGEST_MEASUREMENT_MAX_AGE_SECONDS` | 30 |
| `INGEST_MEASUREMENT_MAX_ATTEMPTS` | 3 |

Megtelt sor esetén az új minta kiesik, és nem frissít state-et vagy végleges
cache-t. Túl nagy minta, elöregedés, próbálkozási limit, hibás adat és tiszta
leálláskor megmaradó sor külön számlálódik. A 30 s az új flush indítása előtti
korhatár; nem szakítja meg a folyamatban lévő SQL-t. A bytekorlát a szerializált
adatra vonatkozik, nem teljes processz-RSS-re. Egy DB-worker kezeli ezt a sort.

A HC-11 inbox ettől különálló: DB-kieséskor az új MQTT-üzenetek továbbra is
azonnal, számláltan kiesnek a felhasználó által elfogadott politika szerint.
A már korábban elfogadott history-sor újrapróbálása korlátos; nincs tartós spool.
Hirtelen processz-/hostkiesés elveszítheti a még nem commitolt RAM-tartalmat.
Normál shutdown flush-t próbál, majd a leállt worker maradékát számláltan lezárja.
Beragadt worker esetén nem ürítjük ki másik szálból a sorát: a HC-11 hibakódos,
korlátos kilépése marad, a sor kimenetele bizonytalan lehet.

A status JSON és napló `measurements` része tartalmazza a sorhatárokat,
`confirmed`, `duplicate_confirmations`, `failed_flushes`, `last_data_error` és
`dropped` mezőket. A visszaigazolás nélküli limit-/shutdown-lezárás nem bizonyítja,
hogy a DB nem commitolt; csak a lokális megerősítés hiányát. A számlálók a processz
élettartamára szólnak; SIGKILL előtti teljes elszámolás és hálózati QoS0-veszteség
mérése nincs garantálva.

Újrainduláskor a historyt tároló szabályok deadband-cache-e a legutóbbi valódi
history-sorból épül, az `(entity_id,key,ts DESC)` meglévő indexével. A state-only
szabályok továbbra is a current-state-et használják. Egy frissebb, szűrés miatt
history nélküli feedback-frissítés nem tolja ki újra a history max-intervallumát.

## Migráció és későbbi bevezetés

Új, **külön alkalmazandó 062-es migráció**:
[062_hc33_ingest_sample_identity.sql](../infra/db/062_hc33_ingest_sample_identity.sql).
Az `ingest_sample_id uuid` nullable oszlop és a részleges egyedi index additív;
a régi sorokhoz nincs visszatöltés. A régi írók továbbra is írhatnak az oszlop
megadása nélkül. A kapcsolódáskori ellenőrzés hiányzó/hibás index esetén nem
engedi DB-ready állapotba az új ingestet. Runtime DDL nincs.

A migrációt adminszereppel, friss mentés után, ellenőrzött karbantartási ablakban,
`psql --set ON_ERROR_STOP=1 --single-transaction --file ...062...sql` módon kell
futtatni. A script 5 s lock- és 120 s statement-timeoutot állít. Az indexépítés
végigolvassa a mérési táblát; a tranzakció idején olvasás/írás is várakozhat.
A 6,8 milliós éles táblán ennek időigényét ebben a feladatban nem mértük meg.
A meglévő HC-07 startup-journalhoz nem adunk ismeretlen verziót; ez az ingest
külön, explicit sémabővítése. Új könyvtárverzió vagy más auditjavítás nincs.

**Függőség:** a helyi HC-11 és HC-33 együtt szükséges az új ingest image-hez;
az image-nek az `ingest_runtime.py` és `measurement_batch.py` modulokat is
másolnia kell. A HC-34 névjavítás, HC-12/32 bridge-sorok és HC-43 frissítések
külön nyitottak, nem részei ennek a javításnak. Élesítés nem történt.

Későbbi rollbackkor az előző pontos r4 ingest image állítható vissza, két
párhuzamos writer nélkül. Előbb a függő sor és végső diagnosztika rendezendő;
a már elveszett RAM-adatot rollback nem állítja helyre. A nullable oszlop/index
maradjon meg, a régi image kompatibilitása ellenőrizve. DB-restore, automatikus
régiüzenet-replay és destruktív oszlop-/indextörlés nem szükséges.

## Ellenőrzés

- Eredeti AST-függvényekkel reprodukálva: 2 függő minta → 0 mentés, üres sor,
  kifelé nem jelzett kapcsolathiba.
- **44 hálózat nélküli unit-/regressziós teszt sikeres:** méret-/kor-/retry-határok,
  commit előtti sor/cache-megőrzés, commit-válasz elvesztése, kizárólagos DB-gazda,
  HC-11 életciklus, meglévő feedback, safety és flood-szabályok.
- **15 valódi PostgreSQL/MQTT integrációs teszt sikeres**, külön, hálózatról
  leválasztott PostgreSQL 16/Mosquitto laborban: kapcsolatvesztés batch előtt,
  többoldalas részleges végrehajtás visszagörgetése, valóban megtörtént COMMIT
  utáni válaszvesztés és azonos UUID-s ismétlés, későbbi state megőrzése,
  hibás history/state sor és timestamp-kulcs ütközés izolálása, queue-overflow,
  cache-bemelegítés, migráció újrafuttatása/régi író, hiányzó/hibás index tiltása.
- A tényleges `main()` DB-leállítás/újraindítás alatt tovább fogad MQTT-t és ír
  életjelet; kiesés alatt új adatot eldob, egy korábban befogadott history-mintát
  viszont azonosítóval helyreállít. Valódi SIGTERM flush-olja a history-only
  utolsó mintát; új processzben a cache visszaépül és egy ténylegesen feldolgozott változatlan élő minta
  nem készít új history-sort. A labor a gyorsított 0,2 s retryhoz 30 próbálkozást
  enged; az alapértelmezett 3-as korlát külön tesztelt.
- A CO/füst alvó szenzor → PostgreSQL → combustion worker integráció is sikeres.
  Nincs rádiós/eszközparancs vagy éles broker-/DB-kapcsolat.

[Összesítés](audit-evidence/hc33-20261028/summary.json),
[unit-/regressziós napló](audit-evidence/hc33-20261028/tests.log),
[valódi integrációs napló](audit-evidence/hc33-20261028/postgres-integration.log),
[éles érintetlenség](audit-evidence/hc33-20261028/production-unchanged.json).
Az éles 9 konténer, az aktív r8 override, a 37 védett hostfájl és az eredeti audit
változatlan. A saját laborkonténerek és kötetük eltávolítva.
