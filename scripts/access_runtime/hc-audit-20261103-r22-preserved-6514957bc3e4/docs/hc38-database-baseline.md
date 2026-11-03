# HC-38: verziózott HC alapséma

A `hc-r1-058-v1` baseline új, üres **PostgreSQL 16** adatbázis HC sémáját
építi fel. A `hc-audit-20261022-r1` HC-objektumait tartalmazza az 058 DDL-jével
együtt, még az 059/060 előtt. **A baseline az éles DB-re nem került rá.** Azóta a célzott HC-06
kiegészítés r2 néven éles, HC-07/38 bevonása nélkül; lásd DEPLOYMENT_PREP.md.

## Tartalom és határ

- `infra/db/baselines/hc_r1_058_v1.sql`: 52 HC-tábla, 7 nézet, 16 sequence,
  2 enum, 171 constraint, 122 index, 5 függvény és 5 saját trigger.
- A hiányzó nyolc core tábla teljes definíciója is szerepel. A validátorok,
  `refresh_presence`, `tg_set_updated_at` és `tg_touch_presence` meglévő
  viselkedését megőrizzük; nem módosítjuk az ingest szerződését.
- A két `trg_touch_presence_*` **D / letiltott**. A két validátor és a
  device updated-at trigger **O / engedélyezett**. A telepítés nem kapcsolja be
  a presence-touch triggereket.
- Nincs táblasor, sequence aktuális számláló, owner, ACL, szerepkör vagy titok.
  Egy telephelyi cím szerepelt a korábbi DDL-ben: az
  `irrigation_pilot_config.soil_sensor_topic_base` új telepítési alapértéke üres
  szöveg. Ez az egyetlen szándékos eltérés az éles HC-katalógushoz képest.
  A régi migráció, élő default és konfigurációs sor nem változott.
- A `public` séma Home Assistant recorder táblái és extensionjei külön
  alkalmazáshoz tartoznak, nincsenek a HC baseline-ban. Teljes helyreállításhoz
  továbbra is teljes dump és az alkalmazások saját migrációja kell.
- A PostgreSQL 16 beépített `gen_random_uuid()` függvénye elegendő; a tiszta
  telepítést csak a szokásos `plpgsql` extensionnel is ellenőriztük.

## Explicit telepítő

Az `infra/backend/migrate_hc38.py` nem importál alkalmazást, nem indít workert
és nem publikál MQTT-re. A `DATABASE_URL` privát környezeti változóban a
kiválasztott migrációs kapcsolat legyen. Ne kerüljön jelszó parancssorba vagy
naplóba. Psycopg 3 és az azonos forrásverziójú SQL-könyvtár szükséges;
konténerben `--sql-dir /migrations` adható meg.

```bash
python3 infra/backend/migrate_hc38.py --plan
python3 infra/backend/migrate_hc38.py --apply
python3 infra/backend/migrate_hc38.py --verify
```

A kapcsoló nélküli működés `--plan`. A terv és a verify read-only,
repeatable-read tranzakciót használ. A fájlokat SHA-256 allowlist védi; a
referencia-katalógus checksumja is rögzített. Az apply egy tranzakcióban,
az 059/060 runnerével közös advisory lockkal, 5 s lock- és 60 s statement-
timeouttal futtatja az SQL-t, ellenőrzi az eredményét és létrehozza a
`hc.schema_baseline` naplót. Ez az egy metaadatsor nem üzleti seed.
A napló verziót, SQL-checksumot, időpontot és végrehajtó DB-role-t tartalmaz.

Üres adatbázist követel: nincs meglévő HC namespace, idegen felhasználói
tábla/nézet/sequence, függvény vagy egyedi típus; extension-objektum megengedett.
Egy üres, de már létrehozott HC séma is visszautasított, mert nincs bizonyított
eredete. Meglévő, naplózatlan sémát **nem fogad örökbe és nem ír felül**, még
azonos szerkezet esetén sem. A saját, változatlan, már naplózott baseline
ismételt apply-ja nem csinál semmit és nem állít sequence-et.

SQL-hiba vagy eltérő létrejött katalógus esetén az egész telepítés rollbackel;
újrapróbálható. Kapcsolatszakadáskor a commit eredménye bizonytalan lehet:
előbb a sémát/naplót ellenőrizni kell. Ismeretlen verzió, checksumeltérés vagy
drift esetén nincs automatikus javítás vagy naplóátírás.

Exitkód: 0 = érvényes üres telepítési terv vagy egyező katalógus; 2 = nem
egyező/hiányzó baseline a read-only ellenőrzésnél; 1 = checksum-, kapcsolati,
telepítési vagy felülírásvédelmi hiba. A `matched` kizárólag a szerkezet
egyezése, nem konfigurációs vagy eszközegészség. A `fresh_install_allowed`
mezőt külön kell nézni: egy meglévő, egyező séma sem engedély friss telepítésre.

## Új telepítés sorrendje

1. Új, dedikált PostgreSQL 16 DB, megfelelő migrációs kapcsolat; backend és
   aktuátorelérés nélkül `--plan`, majd `--apply` és `--verify` a fenti módon.
2. A baseline nem seedel. Az 058 már verziózott, additív inicializálóját
   külön kell alkalmazni, hogy a safety runtime kezdetben `latched=true`,
   `acknowledged_at=null` legyen. Ez az egy kijelölt, idempotens fájl engedett,
   nem az összes korábbi migráció újrajátszása:

   ```bash
   python3 - <<'PY'
   import os
   from pathlib import Path
   import psycopg
   with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as conn:
       conn.execute(Path('infra/db/058_combustion_safety_runtime.sql').read_text(), prepare=False)
   PY
   ```

3. A [HC-07 explicit migrátorával](hc07-schema-migrations.md) `--plan`, majd
   `--apply --seed-initial`, amennyiben a kezdeti domainadatok kifejezetten
   kívánatosak. Az opcionális HC-07 seed korábbi CO-/esőszenzor-címeket is
   tartalmaz: új helyszínhez ez külön felülvizsgálandó inventory, **nem általános
   eszközfelderítés**. A baseline maga nem tartalmaz ilyen címet vagy sort.
4. Konfiguráció, metrikakatalógus, bindingok és tényleges inventory áttekintése,
   kívánt szezon/mód/feature flag-ek kiválasztása, utána külön backendindítás.
   A kezdeti soil topic üres: explicit helyi binding/config kell hozzá;
   a korábbi runtime fallback viselkedését ebben a pontban nem változtattuk.
   A kezdeti safety latch nyugtázásához továbbra is a HC-06 friss, veszélymentes
   inputjai és kezelői ACK szükségesek; a telepítő nem nyugtáz.

Az 059/060 egyszeri DML-je külön naplózott migráció, az opcionális HC-07 seed
insert-only. **A `001–058` teljes készlete nem replayelendő a baseline után**:
üzleti upsertek, backfillek és módváltások vannak benne. A `042 CONCURRENTLY`
nem tranzakciós történeti művelet; indexének baseline-definíciója már szerepel
a snapshotban. Nem futtatjuk bele a tranzakciós runnerbe. Későbbi ilyen művelet
külön, dokumentált operatív lépés marad.

## Meglévő adatbázis és restore

**Meglévő DB-n nincs baseline apply.** Az éles r1 és a régi dump naplózatlan,
meglévő telepítésként felismerhető; a telepítő apply-t visszautasítja. A
`--verify` csak összevet, nem ír naplót. Az éles r1 és a tesztelt régi dump
esetében a szándékosan semlegesített soil default az egyetlen érdemi eltérés.

Dump út: teljes restore **sikeresen befejeződik** → korábbi célzott hiányok,
például 058 → HC-07 `--plan`/`--apply`, **kezdeti seed nélkül** → konfiguráció
áttekintése → külön új backendindítás. A régi restore launcher és a teljes
dumpok változatlanok. Az új backend indítása előtt az explicit migrációt
be kell tenni az operatív átadásba; a launcher ezt nem végzi el helyetted.

A baseline verify kizárólag az r1/058 határra vonatkozik. Az 059/060 új
naplót és mód-constraintet hoz; ettől kezdve a baseline verify szándékosan
eltérést jelez, és apply-val sem szabad „helyrehozni”. A startup kompatibilitási
ellenőrzése ekkor a HC-07 szerződését használja. Későbbi sémaváltozáshoz új,
egyirányú, naplózott migráció kell; a kiadott baseline nem szerkesztendő.

## Strukturális összevetés és ellenőrzés

A `baseline_contract.py` az oszlopok sorrendjét/típusát/nullability/defaultját,
constraint definíciót/validáltságot, indexdefiníciót/valid-ready-unique állapotot,
enumokat, függvénydefiníciókat, triggerdefiníciót/engedélyezést, nézeteket,
relation opciókat és sequence definíciót/táblához kötést hasonlítja össze.
OID, owner/ACL, soradat és aktuális sequence-számláló nem része az összevetésnek.
A baseline saját naplótáblája kimarad. Egyetlen ismert deparse-eltérést
normalizálunk: a mower image-size CHECK két, pontosan megadott, azonos AND
kifejezésének zárójelezését. Általános zárójelezést/defaultot nem hagyunk figyelmen
kívül, így a soil default különbsége látható marad.

Tartós SQL-regresszió: `infra/backend/tests/test_baseline_postgres.py`, 19 eset.
Opt-in: `HC38_TEST_POSTGRES=1`,
`HC38_TEST_DATABASE_URL=postgresql://...@127.0.0.1/hc38_schema_test`.
A kapcsolaton ellenőrzött DB-név is pontosan `hc38_schema_test` kell legyen.
**A teszt a saját HC sémáját törli; kizárólag eldobható laborban futtatható.**

A javításkor 611 backendteszt futott hiba/kihagyás nélkül, továbbá teljes régi
dump restore/upgrade, két új folyamatban végzett bootstrap és az üresből
felépített DB valódi WSGI/HTTP próbája is sikerült. Az utóbbi laboros health,
szezon, notes, scheduler és safety végpontokat ellenőrzött; nem valós szenzor-,
aktuátor- vagy új VM-es telepítési próba. Részletek: `AUDIT_REPAIR.md`, REPAIR-009.

## Függőségek és visszaállás

[HC-39 role/ACL/SQL Lab leválasztása](hc39-database-roles.md) azóta külön helyi
javításban ellenőrzött, a megmaradt lazy DDL explicit 061 migrációba került.
A baseline továbbra sem tartalmaz role-t, éles superuser-jogot vagy ACL-t.
HC-08, egyéb auditpontok és a teljes host/VM-restore automatizálás változatlanok. A HC-07 a munkafában kész,
de nincs élesítve; későbbi forrásváltáshoz külön 059/060 és verziózott kiadás kell.
Az F7-ben hivatkozott F6 mentési runner/lock/időzítés egyesítése továbbra is
nyitott; most a kiválasztott meglévő mentés DB-visszaállíthatóságát bizonyítottuk.

Nincs down-migráció, adatürítés vagy automatikus élő visszaállás. Sikertelen
friss baseline tranzakciója visszagörgethető; eldobható labor eldobható.
Meglévő rendszer helyreállítása a változatlan dump út, mentett előállapot és
felülvizsgált kódkompatibilitás alapján történik. A most futó r1 kiadás és
annak előkészített tartaléka változatlan maradt.
