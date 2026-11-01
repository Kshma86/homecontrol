# HC-39 — külön adatbázis-szerepkörök és SQL Lab

Állapot: **helyben ellenőrzött, nincs élesítve**, 2026-10-23.
Audit: HC-39 bizonyítékok, F7a; közvetlen előfeltétel a HC-07/HC-38 F7 útja.
Az éles `hc-sleeping-20261023-r2` kiadás és privát override változatlan.

## Kapcsolatok és jogok

| Feladat | Role / út | Engedély |
|---|---|---|
| Explicit migráció, mentés/admin | Meglévő admin, külön `HC39_ADMIN_DATABASE_URL`, közvetlen PostgreSQL | Sémamódosítás és role/ACL-kezelés; nem kerül a backend/ingest környezetébe |
| Backend + ingest | `hc_app`, PgBouncer | A név szerint felsorolt HC üzleti táblák SELECT/INSERT/UPDATE/DELETE, nézetek SELECT, sequence-ek USAGE; journalok csak SELECT |
| SQL Lab lekérdezés, séma, preview | `hc_lab`, külön `SQL_LAB_DATABASE_URL`, közvetlen PostgreSQL | A felsorolt HC táblák/nézetek SELECT; nincs sequence-használat, írás, objektumtulajdon, CREATE/TEMP vagy role-tagság |

Mindkét új role LOGIN, NOINHERIT, NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
NOREPLICATION, NOBYPASSRLS. Nincs admin/signal/file-access tagság vagy runtime
objektumtulajdon. A régi admin role megmarad, jogosultságát nem másoljuk.
Az objektumlista a `db_privilege_manifest.py` explicit manifestje; ismeretlen
HC reláció vagy hiányzó üzleti objektum esetén az apply visszagörget.
Régi dumpnál a friss telepítés `schema_baseline` journalja jogszerűen hiányozhat.

A backend és ingest kapcsolódáskor, reconnectkor is ellenőrzi a `hc_app`
azonosságát és a lényeges jogosultsági feltételeket. A SQL Lab minden saját
kapcsolatán külön ellenőrzi a reader szerepkört és effektív jogait: tagság,
tulajdon, rendszerkatalógus-jog, írás/oszlopgrant, HC-n kívüli adatolvasás és
elérhető felhasználói SECURITY DEFINER függvény sem maradhat rejtett jogforrás.
Üres vagy veszélyes reader DSN: **503**, titokmentes hiba, admin/app fallback nélkül.
A Lab sémalistája és preview-ja a `hc` sémára szorítkozik.

Megmarad a SQL-validálás, read-only tranzakció, 7 s-os lekérdezési timeout,
500 soros eredménylimit és 100 soros preview-limit. A reader alapértelmezett
tranzakciója is read-only; idle tranzakciós timeoutja 10 s. A DB-ACL akkor is tiltja
az írást, ha valaki kikapcsolná a tranzakció read-only kapcsolóját.

A PostgreSQL `PUBLIC` jogai minden új role-ra is vonatkoznak. Ezért a telepítő
az érintett adatbázis CREATE/TEMP, felhasználói séma CREATE és reláció PUBLIC
jogait, továbbá a HC/felhasználói SECURITY DEFINER függvények PUBLIC EXECUTE
jogát szűkíti. Előbb explicit megőrzi a már létező loginok hozzáférését;
az új app/reader role kimarad ebből. Meglévő oszlopszintű vagy direkt reader-grant
miatti eltérésnél nem állít biztonságos működést: az apply visszagörget, kézi
jogosultsági felülvizsgálat kell. Új szerepkörnek vagy új sémaobjektumnak később
explicit grant kell. A HC függvények jövőbeli PUBLIC EXECUTE alapjoga is megszűnik
a jelenlegi függvénytulajdonosoknál. A szükséges triggerek változatlanul működnek.

Forrás: [PostgreSQL 16 jogosultságok](https://www.postgresql.org/docs/16/ddl-priv.html),
[előre definiált szerepkörök](https://www.postgresql.org/docs/16/predefined-roles.html),
[GRANT](https://www.postgresql.org/docs/16/sql-grant.html).

## Explicit telepítési sorrend

Ez nem élesítési script. Saját Python/Psycopg 3 migrációs környezetben vagy külön
one-shot konténerben fusson; normál backend/ingest ne kapjon admin DSN-t.
A titkok 0600 fájlban/környezeti változóban legyenek, ne parancsargumentumban/logban.

1. Friss teljes mentés, visszaállítási próba és role/ACL előállapot; backend és ingest
   leállítva az éles migráció/átadás idejére. A laborban ez saját, izolált DB volt.
2. Új DB: HC-38 baseline → külön 058 runtime inicializálás → HC-07 059/060 és
   tudatos kezdeti seed. Meglévő DB: dump/upgrade → hiányzó 058 → HC-07 059/060;
   baseline apply és az összes történeti SQL tömeges replay-e tilos.
3. Külön admin DSN és két eltérő, véletlen, 32–128 karakteres URL-biztos jelszó:
   `HC39_ADMIN_DATABASE_URL`, `HC_APP_DB_PASSWORD`, `HC_LAB_DB_PASSWORD`.
   A telepítő nem generál alapjelszót és ismételt futtatáskor nem forgat jelszót.
4. Előellenőrzés, majd explicit alkalmazás az azonos verziójú SQL-könyvtárral:

   ```bash
   python infra/backend/migrate_hc39.py --plan --sql-dir infra/db
   python infra/backend/migrate_hc39.py --apply --sql-dir infra/db
   ```

   Alapértelmezésben is csak plan. A runner ellenőrzi a HC-07 journalt és a 061
   SHA-256-át; azonos tranzakcióba teszi a DDL-t, role/ACL-változást és a
   `hc.db_privilege_migration` 061/checksum/policy bejegyzését. Advisory lock,
   5 s lock- és 60 s statement-timeout védi. Nincs app/worker import.
   Meglévő, nem naplózott HC-role esetén megáll; másik DB-be restore-olt,
   felülvizsgált cluster-role-okhoz külön `--adopt-existing-roles` kell.
5. A runtime környezetbe csak az app jelszó és a reader DSN kerüljön:
   `SQL_LAB_DATABASE_URL=postgresql://hc_lab:<URL-biztos-jelszó>@postgres:5432/<DB>`.
   Az alap Compose már `hc_app`-ot használ a backendben, ingestben és PgBouncerben;
   az app jelszó kötelező. A Lab közvetlen DB-útja elkerüli az app-pool admin/auth
   összekeverését. A jelenlegi PgBouncer image saját userlistből hitelesíti az appot;
   nem kell neki superuseres auth-katalógus-olvasás.
6. Külön, fagyasztott kiadás, pontos image-ek és privát env/override; PgBouncer,
   backend és ingest összehangolt cseréje. Health, ingest state/history, olvasórole,
   tiltott katalógus/signal, config és safety állapot ellenőrzése. Nincs automatikus ACK.

A 061 a megmaradt lazy DDL-t viszi explicit lépésbe: power-wall, opening/temperature,
binding, AI audit, page usage, öntözési összesítők, mower draft/staging/session/operation,
climate window guard. A meglévő definíciókat őrzi, a guard singletonját egyszer
hiánypótolja; meglévő kezelői sort nem ír át. Az 055 korábbi constraintcsere is csak
itt, egyszer, a migrációban fut. A runtime helyettük SELECT-tel ellenőrzi a szükséges
oszlopokat; hiány esetén migrációt kér, nem javít sémát a kérésből. A korábbi mower
SQL-konstansok kizárólag történeti fixture-ként maradtak, a store nem hajtja végre őket.

## Ellenőrzési bizonyíték és határok

`/tmp/hc39-repair` (privát): **638 backendteszt**, **13 ingest/PG teszt**,
0 failure/error/skip; ezen felül valódi ingest role-ellenőrzés app/admin kapcsolattal.
A backendből 21 eset a HC-39 új role/HTTP/hibainjektálási köre.
Friss DB baseline-ból, és az r2 teljes dumpjának saját PG16 restore-ja (`pg_restore`
exit 0 megvárva). Utóbbin 17 üzleti tábla soradata pontosan egyezett; a katalógusban
csak a privilege-journal új, a függvények és triggerek változatlanok.

Valódi WSGI/HTTP + saját MQTT + PgBouncer + ingest: normál olvasások, reader identity,
élő fixture-telemetria állapot- és történetírása, másik role elleni signal tiltása.
A célkapcsolat életben maradt. Saját pool újraindítása után app/reader identity és
health helyreállt. A régi admin kapcsolat megmaradt, az új backend visszautasította
admin fallbackként. Nincs éles signal, auth-adatolvasás, publish, ACK, migráció vagy
újraindítás. A labor nem fizikai szenzor-/aktuátor- vagy teljes host-telepítési próba.

Közvetlen függőség: HC-07/38 és a 061, új role-jelszavak, külön Lab DSN, PgBouncer
átadás. A F6/F0 mentési/host-helyreállítási korlátok, HC-08/33, HC-40/41/43/44 és
minden más auditpont nyitott marad. Az ingest batch/retry működését nem refaktoráltuk.
A frontend és függőségverziók nem változtak; új frontend build nem szükséges.

## Visszaállás

Nincs down-migráció, role-törlés, latch-törlés vagy automatikus teljes DB-restore.
Az additív role-ok/journalok és a régi admin kapcsolat megmaradnak. Sikertelen apply
minden változása együtt visszagörget. Kiadási rollbackhez pontos korábbi image/env
és mentett role/ACL állapot kell; a reader határa közben is megőrzendő.

Az új backend/ingest szándékosan visszautasítja az admin runtime DSN-t. Ha régi
kóddal ideiglenesen admin app-kapcsolat kell, a Lab külön reader wiringját meg kell
őrizni a rollback buildben, vagy **mindhárom `/api/sql-lab/*` HTTP-útvonalat** az
átadás előtt le kell zárni a proxyn. A UI elrejtése nem elegendő. A régi r2 backend
önmagában nem reader-kompatibilis rollback, mert még közös admin Lab-kapcsolata van.
Teljes régi-image rollbacket új reader-védelemmel most nem telepítettünk/próbáltunk;
a labor a kapcsolat megőrzését és az új kód fallback-tiltását igazolta.

A jelenlegi éles r2 fagyasztott kiadási/visszaállási folyamata változatlan:
[DEPLOYMENT_PREP.md](../DEPLOYMENT_PREP.md). A munkafából általános `up --build`
ne fusson: HC-07/38/39 nincs bevezetve.
