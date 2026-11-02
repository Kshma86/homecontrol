# HC-15 — DB-hozzáférés és app-wiring egyszerűsítése

2026-11-02, F0/F8. **Ellenőrzött kódjavítás, még nem élesített.** Az aktív
rendszer továbbra is az előzőleg átvett `hc-security-20261102-r18`.
Más auditpont implementációja és státusza nem változott.

## Kiindulás és kapcsolódó bizonyíték

Elolvasva az eredeti audit HC-15 megállapítása, D.1 hivatkozási bizonyítéka,
F0 előfeltételei és F8 végrehajtási lépése. Az audit eredeti SHA-256 lenyomata
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`, változatlan.

A mostani app, DB- és domainmodulok megegyeztek az éles r18 forrásával.
A registry egyetlen `shared` repositoryt tartott, a repository változtatás
nélkül delegált; a használatlan app-getternek nem volt aktív hívója.
A scheduler-audit domainlogikája a korábbi HC-08 javítással már a meglévő
`SchedulerService`/`SchedulerAudit` osztályokba került. Ezt megőriztük.

F0: a visszaállítással ellenőrzött r18 mentési nyugta rendelkezésre állt
(`86b8ed71e4104b3a8eb909ae86e8ea91`, completed/0). A kiinduló 795 unit teszt
sikeres. Az előállapot, az eredeti fájlok és a hivatkozási/scope bizonyítékok
a [HC-15 bizonyítékkönyvtárban](audit-evidence/hc15-20261102/) szerepelnek.

## Módosítás

- A `DatabaseRuntime` közvetlenül a `DatabaseService` metódusait használja;
  a `RepositoryRegistry`, `SqlRepository`, az ezeket tartalmazó modul és az
  egyetlen puszta forwardingteszt kikerült. A használatlan
  `app.get_repository_registry()` is megszűnt. Aktív hivatkozás nem maradt rájuk.
- A query-counter a `DatabaseRuntime` felelőssége maradt. A connection,
  szerepkör-ellenőrzés és tranzakciókezelés a változatlan `DatabaseService`-ben
  maradt. A nyers connection és healthcheck továbbra sem növeli a request
  helper-számlálót; nem állítunk új, SQL-utasításonkénti mérési szemantikát.
- A klímaütemezések lekérdezése és profilvalidálása a meglévő
  `ClimateService.fetch_schedule_rules()` metódusba került. A szezon-/scheduler
  sémaellenőrző callbackek explicit bekötést kaptak; sorrendjük változatlan.
  Az app kompatibilis helperfüggvénye csak delegál.
- A V2 öntözési session SQL-lookup a meglévő
  `IrrigationService.fetch_v2_session()` metódusba került. A scheduler ugyanazon
  callback-interfészen, késleltetett service-hívással kapja az eredményt.
  A forrásazonosító konverziója, nap-/forrásszűrés és a legújabb sor kiválasztása
  megmaradt. Az összes korábbi öntözési metódus AST-je változatlan.
- Az app 1406 sorról 1339 sorra csökkent. Nincs új DI-framework, sémamigráció,
  eszközparancs vagy ütemezési szemantikaváltozás.
- A tesztforrás-staging a törölt Python-fájlokat is eltávolítja az éles
  forrásmásolatra tett overlayből; a törölt modul/teszt nem maradhatott benne
  észrevétlenül. A meglévő PostgreSQL-harness külön HC-15 tesztmodult kapott.

## Ellenőrzés és eredmény

**1003 különböző végső backendteszt sikeres, 0 hiba, 0 kihagyás:** 806 unit és
197 PostgreSQL-teszt, utóbbi 15 külön eldobható klaszterben/modulban.
A külön 24 célzott, startupot is tartalmazó teszt átfed ezzel, nem számoltuk hozzá.
19 új szerződésteszt váltotta fel az egyetlen puszta forwardingtesztet.

A valódi PostgreSQL-próbák ellenőrizték a helper-eredményeket/commitot, az
SQL-hiba utáni teljes rollbacket, connection close-t, a beágyazott savepointot,
az eredeti `hc_app` szerepkörhatárt, valamint a korábbi SQL és az új domainhívás
azonos eredményét ugyanazon tranzakcióban. A klímateszt az összes státuszt és
a profilválasztást is ellenőrizte. A request-számláló sikeres/hibás hívásnál
egyszer nő, és két párhuzamos request között külön marad.

A friss interpreterben végzett app-importpróba tiltja a socketkapcsolatot,
thread-/folyamatindítást és fájlírást. Import után a domain/service-worker
inicializálás továbbra is késleltetett; a valódi app-factoryk is külső munka
nélkül bekötik a két új domainhívást. A kiinduló és új **163 route**
útvonala, HTTP-metódusai és endpoint-azonosítói megegyeznek.

Tényleges végső parancsok:

```bash
python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc15-20261102/unit
python3 -B scripts/check_hc_tests.py --profile postgres --output docs/audit-evidence/hc15-20261102/postgres
```

A tesztkonténerek hálózat nélkül futottak; a PG-kliensek kizárólag a saját,
eldobható DB hálózati névterét osztották. Nem volt hostport vagy éles eszköz/DB.
A generic standard-profil régi backup-szerződései az eddigi harness szerint
kizárólag eldobható másolatban használnak opcionális deployment policy-t;
az éles kötelező policy és a szerepkörök nem változtak.

Az első külön célzott `python -m unittest` futtatás az image munkakönyvtára
miatt régi, beégetett modulokat importált; ennek hibás eredménye külön logban
megmaradt. A javított célzott futtatás explicit forrás-munkakönyvtárral, a
végső profilok pedig explicit forrás-importúttal futottak. Az első kísérlet
nem része a sikeres elfogadásnak.

[Összesítés](audit-evidence/hc15-20261102/summary.json),
[unit-eredmény](audit-evidence/hc15-20261102/unit/test-summary.json),
[PG-eredmény](audit-evidence/hc15-20261102/postgres/test-summary.json),
[hatókör](audit-evidence/hc15-20261102/scope-check.json),
[patch](audit-evidence/hc15-20261102/source.diff).

## Függőségek, élesítés és rollback

Megőrzött, már meglévő függőség a HC-08 tranzakciós scheduler-audit adapter,
a HC-07/38 sémaellenőrzés és a HC-39 alkalmazási/SQL Lab jogosultsághatár.
Ezekhez nem készült új javítás vagy migráció. HC-16 rover/auth és HC-20
legacy executor továbbra is külön feladat, annak ellenére, hogy ugyanaz az F8
fázis és részben ugyanaz az öntözési fájl érinti őket.

Az élesítés külön, felülvizsgált backendkiadást igényel. A törölt fájlokat az
új source/image összeállításánál is ténylegesen el kell hagyni; egy régi
kiadásra tett egyszerű fájloverlay nem bizonyítja ezt. Az r18 lezárt forrásait,
runtime-ját és image-eit nem módosítottuk. A külön végső ellenőrzés 736 változatlan
runtime-hasht és mind a 16 korábbi konténer változatlan ID/image/állapotát igazolta.
[Éles változatlanság](audit-evidence/hc15-20261102/production-unchanged.json).

Forrásoldali rollback: a `before.json` és `original/` alapján az érintett app,
DB-runtime, domain-, teszt- és harnessfájlok együtt visszaállíthatók; a törölt
repositorymodul és régi teszt is megőrzött. Az új tesztfájlokat ilyenkor szintén
vissza kell vonni. DB-visszaállítás/down-migráció nem szükséges. Az éles
rendszeren ebben a körben nincs visszagörgetendő beavatkozás.
