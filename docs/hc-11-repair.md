# HC-11 — Az ingest DB-helyreállításának leválasztása

2026-10-28. **Élesítve az r9 ingesttel, 22:13:26 CET.**
HC-11/33/34 együtt aktiválva, a 062-es migráció alkalmazva; backend/frontend r8.
[Éles ellenőrzés és visszaállítás](../backups/deployments/hc-ingest-20261028-r9/DEPLOYMENT.md).
Az alábbi leírás és teszteredmények az önálló HC-11 javításkori állapotot rögzítik;
a végén szereplő akkori függőségeket és bevezetési tervet az r9 átadási napló pontosítja.

Forrás: az eredeti audit HC-11 megállapítása, bizonyítéka és F10 lépése;
kapcsolódó HC-33/34 elolvasva. A felhasználó jóváhagyta a
**számlált eldobást kieséskor**, tartós offline tárolás helyett.

## Működés

A Paho callback csak a topic/payload/retained jelzést és a fogadás falióra-,
valamint monoton időpontját adja át egy korlátos memóriasornak. Nem futtat SQL-t,
reconnectet vagy várakozást. Egyetlen DB-worker birtokolja a kapcsolatot,
cursort, cache-eket, DB-feldolgozást, kontaktus-flush-t és presence-sweepet.
A hálózati ciklus és életjel DB-hiba vagy lassú DB-hívás alatt is tovább fut.

A DB-kapcsolódás próbálkozásonként történik, a következő kísérlet időzített;
a hálózati szál nem várja meg. Minden kapcsolódáskor megmarad a HC-39 korlátozott
szerepkörének ellenőrzése és az állapot-cache bemelegítése. Hibás részleges
kapcsolódás után és kapcsolatcsere előtt a cursor és connection külön lezáródik.
A reconnect nem indítja újra az éppen hibázott üzenetet: autocommit mellett
annak korábbi SQL-jei már végrehajtódhattak.

Az inbox FIFO, nincs metrikánkénti összevonás vagy sorrendcsere:

| Beállítás | Alapérték | Jelentés |
| --- | --- | --- |
| `INGEST_INBOX_MAX_MESSAGES` | 1000 | Várakozó üzenetek darabkorlátja |
| `INGEST_INBOX_MAX_BYTES` | 8388608 | Várakozó payloadok és UTF-8 topicok összmérete |
| `INGEST_INBOX_MAX_AGE_SECONDS` | 5 | Feldolgozás elkezdése előtti maximális sorban töltött idő |
| `INGEST_DB_CONNECT_TIMEOUT_SECONDS` | 3 | libpq kapcsolódási timeout; nem minden SQL abszolút határideje |
| `INGEST_DB_RETRY_SECONDS` | 5 | Sikertelen próbálkozás utáni várakozás |
| `INGEST_SHUTDOWN_TIMEOUT_SECONDS` | 5 | Worker leállására várás felső határa |

A limitek env változóként állíthatók; új Compose- vagy éles beállítás nem készült.
A bytekorlát nem teljes Python RSS-korlát; a darabkorlát az objektumok számát is
határolja. A kivett, feldolgozás alatt álló egy üzenet már nincs a várakozó sorban.
A későbbi SQL-végrehajtás időtartamát az 5 s-os sorlimit nem korlátozza.

## Adatvesztési szerződés

- Nincs elérhető DB: az új MQTT-üzenet azonnal kiesik, `db_unavailable` számlálóval.
- Túl nagy üzenet: `oversize`; megtelt sor: az új üzenet esik ki, `overflow`.
- Sorban elöregedett üzenet: `expired`, feldolgozás nélkül.
- Felismert DB-hiba: a még várakozó sor atomikusan lezáródik a befogadás előtt és
  kiürül, `db_failure` számlálóval. A sikertelen feldolgozás külön
  `db_failed_messages`; ez részleges végrehajtást is jelenthet.
- Újracsatlakozás után új üzeneteket fogadunk; a régi sor és hibás üzenet nem
  játszódik vissza. A megmaradó MQTT QoS0 miatt broker/hálózati veszteséget nem
  tudunk számlálni vagy visszajátszani. A számlálók a processz élettartamára szólnak.
- A sor megőrzi az eredeti `recv_ts` és retained értékét. A parser, szabályok,
  safety/feedback megkülönböztetés és a meglévő DB-időbélyegzés változatlan.
- Kontaktusonként megmarad a trailing-edge pergésmentesítés. DB-session
  elvesztésekor a függő jelöltek kiesnek; külön `contact_candidates_dropped`
  számláló jelzi őket. Leállás nem kényszerít még nem stabil kontaktusélt.

Az `/tmp/hc_ingest_status.json` és a periodikus, illetve leálláskori
`[INGEST_STATUS]` naplósor mutatja a DB/MQTT állapotot, reconnectszámot,
veszteségeket, sorhosszakat és a beragadt worker jelzését. A `processing_attempts`
fogadott feldolgozási kísérleteket számol, nem igazolt tartós mentéseket.
A statusfájl írási hibája naplózódik, nem állítja le az ingestet.
Az életjel a hálózati ciklus haladását mutatja, nem bizonyít sikeres SQL-mentést.

A 10 s-nál tovább aktív DB-hívás `stalled` állapotot jelez és felfüggeszti az
új befogadást. A folyamatban lévő SQL-t nem szakítjuk meg másik szálból.
Szabályos leálláskor a worker stabil kontaktusokat és a meglévő batch-et próbálja
menteni, majd lezár. Ha nem áll le határidőn belül, a processz hibakóddal kilép;
ilyenkor tiszta flush nem állítható. A megmaradó socketeket a processz kilépése
zárja le. A Docker újraindítási politikája változatlan.

## Ellenőrzés

- A régi `connect_db()` DB-hiba után a callbackben maradt: a kontroll reprodukálta.
- **37 hálózat nélküli teszt sikeres:** sor darab/byte/kor-limit, 10 000-es burst,
  FIFO/retained/fogadási idő, kizárólagos DB-tulajdonos, kapcsolódási időzítés,
  kiesés/befogadás versenyhelyzete, friss helyreállás, régi erőforrás lezárása,
  role-/warmup-hiba utáni takarítás, kapcsolódás és flush alatti leállás,
  valóban kilépő processz beragadt flush esetén. A meglévő feedback-,
  alvó safety-szenzor- és MQTT flood-regressziók is ebben a körben futottak.
- **1 valódi MQTT/PostgreSQL integrációs teszt sikeres:** az új `main()` önálló
  processzként, saját Mosquitto és PostgreSQL 16 példányon, kizárólag loopbacken,
  HC-39 `hc_app` jogokkal. A labornak nincs eszköz-/éles hálózati hozzáférése.
  A PostgreSQL tényleges leállítása alatt 100 üzenet érkezett: 99 azonnali
  eldobás, 1 DB-hibás feldolgozás; az MQTT és heartbeat folyamatosan haladt.
  Újraindítás után nem jelentek meg a kiesési értékek vagy a félbehagyott
  kontaktusjelölt. Az elfogadott értékek sorrendje megmaradt, kontaktus-bounce
  nem lett mentve, stabil kontaktus késleltetve mentődött. A SIGTERM a végső
  függő mintát is mentette, kilépési kód 0.
- AST-kontroll: a 47 korábbi függvény/osztály közül csak a `main()` változott;
  a másik 46, így HC-33 `flush_measurements()` és HC-34 `map_key()` változatlan.
- Mind a 9 éles konténer azonosítója/image-e/indulási ideje/restartszáma, az
  aktív override és a 37 védett hostfájl változatlan; a labor eltávolítva.

Bizonyítékok: [összesítés](audit-evidence/hc11-20261028/summary.json),
[tesztnapló](audit-evidence/hc11-20261028/tests.log),
[valódi kieséspróba](audit-evidence/hc11-20261028/postgres-integration.json),
[éles érintetlenség](audit-evidence/hc11-20261028/production-unchanged.json).
Az opt-in integrációs teszt: `apps/hc_ingest/test_ingest_recovery_postgres.py`;
a saját konténerek teljes életciklusát kezelő futtató az evidence könyvtárban.

## Függőségek és későbbi élesítés

**HC-33 nyitott marad.** A régi `pending_measurements` batch külön sor;
a jelen javítás nem teszi atomivá/idempotenssé, nem változtatja meg korai
ürítését és hibanyelését. Emiatt részleges/történeti mérésvesztés, bizonytalan
kimenetelű batch és egy korábban sorba tett mérés későbbi flush-a továbbra is
lehetséges. Az új inbox számlálói ezeket nem fedik le. Tartós offline gyűjtés,
automatikus replay vagy garantált veszteségmentes history ígérete előtt HC-33
külön javítása szükséges. A HC-34 metrikanevek, HC-12/32 bridge-sorok és HC-43
függőségfrissítés külön munka; egyik státusza sem változott.

Új migráció vagy könyvtárverzió nincs. Az ingest új image-ének a módosított
Dockerfile szerint az `ingest_runtime.py` fájlt is tartalmaznia kell. Későbbi,
külön engedélyezett bevezetésnél csak az ingestet kell cserélni; a régi példányt
előbb le kell állítani, két párhuzamos DB-writer nem futhat. Friss helyi mentés,
az előző pontos r4 image megőrzése, MQTT/DB státusz, új minták és kontaktusok
ellenőrzése szükséges. Visszaállás ugyanennek az egy ingest image-nek a cseréje,
DB-restore és régi üzenetek replaye nélkül. A QoS0 kiesési veszteséget a rollback
nem hozza vissza. Jelen feladatban kiadásváltás és éles restart nem történt.
