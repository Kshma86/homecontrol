# HC-23/43 — r18 élesítési csomag, 2026-11-02

**Aktív: hc-security-20261102-r18, élesítve és szoftveresen ellenőrizve 2026-11-02.**
A teljes privát HA-előpróba és az élesítés sikeres. Független utóellenőrzés:
736 egyező forráshash, 15 várt image, 10 healthy healthcheck, 5 aktív timer,
HTTP200; a HA hitelesített API-ja és 64 Growatt-entitás megmaradt, PG16/kolláció jó.
Friss Git/router mentés, 6373 checksum és külön PG-restore sikeres.
[Éles átadás és rollback](../backups/deployments/hc-security-20261102-r18/DEPLOYMENT.md),
[utóellenőrzés](audit-evidence/hc23-43-r18-live-20261102/production-check.json).
Az AI tiltása, az ESP MQTT legacy kivétele, a Git-feltöltés és a routeres mentési
beállítások megmaradnak. Az audit összesítése változatlan: HC-23/43 folyamatban.

## Változás és hatókör

A fő Compose-projekt 14 szolgáltatása és a külön Home Assistant új, pontos
image-ID-val rögzített image-et kap. PostgreSQL 16 marad, az alkalmazások Python-
függőségverziói változatlanok. A Home Assistant hivatalos 2026.10.4 kiadásra,
a PgBouncer támogatott Alpine-alapra kerül; a disztribúciós csomagok elérhető
frissítéseit alkalmaztuk. Frontend: rögzített Node 24 buildalap, Vite 6.4.5,
offline npm-lock/cache és saját HTTP-healthcheck. A leállított Adminer változatlan.

A HA SQLite-mentése ezentúl online backup API-val készül, a WAL-t is figyelembe
véve; az archívumba ellenőrzött, önálló adatbázis kerül. A teljes hostrestore
kezeli a HA pontos, offline cache-ben ellenőrzött image-ID-ját is.

## Ellenőrzések

A [bizonyítékok](audit-evidence/hc23-43-20261102/) és a csomag
`evidence/acceptance.json` fájlja rögzítik a tényleges eredményeket:

- Backend: 795 általános, 190 PostgreSQL és 2 tulajdonosi teszt; hibák és kihagyások nélkül.
- A kötelező deployment policy külön 19 tesztje az éles policy tesztváltozatán futott.
  A régi backup-szerződések általános tesztjei kizárólag eldobható másolatban
  használnak policy nélküli profilt; az éles policy nem változott.
- Bridge 54, ingest 52, X10 33, frontend 114 teszt és frontend build.
- Telepítő 16, router-tranzakció 12, HA-tranzakció 16, platform-tranzakció 8,
  SQLite-backup 2 teszt. A valódi telepítő stop/install és rollback útvonalának
  tesztje is kikényszeríti, hogy a SQL-átadáskor működjön a PostgreSQL.
- Valódi, izolált PostgreSQL/PgBouncer és hitelesített MQTT: előző → jelölt →
  rollback → dumpból visszaállított jelölt; megőrzött adatokkal és működő IPC-vel.
- Külön PostgreSQL image-próba ugyanazon eldobható adatkönyvtárral:
  régi → új → régi; az eredeti és az új image alatt beírt sorok is megmaradtak.
- Hét alkalmazás külön dependency-kiesési próbája: a processz él, a readiness
  helyesen hibát jelez. Ezek nem pozitív hardver-/felhőpróbák.
- A HA olvasható konfigurációjának és konzisztens éles DB-másolatának izolált
  indulása az új és a régi image-en: schema 53, a meglevő sorok megmaradtak.
  Ez nem hitelesített integrációpróba: öt védett auth/config fájlt az operátor
  nem tudott olvasni. Ezek teljes másolatának próbája a helyi sudo előfeltétele.
- 46 image-es offline recovery-archívum: blob-/réteg-/készletellenőrzés és
  tényleges Docker-load. A végleges image-ek ID-jai külön lockban szerepelnek.

## Függőségi eredmény és nyitott rész

A 2026-11-02-i teljes nyilvános PyPI/npm OSV-katalógusokat helyben vetettük össze
a leltárral. Privát leltárt nem töltöttünk fel. A hét saját Python-komponensben
0 értékelhető találat, a végleges npm-lockban 0 találat és 0 ismeretlen rekord.
Az OS-scan mind a 15 image-en lefutott, elérhető disztribúciós javítást jelző
rekord nélkül. **Ez nem sérülékenységmentesség.**

A támogatott HA-csomagkészletben 98 nyers Python-advisory találat, 67 aliascsoport
maradt, továbbá a teljes Python-értékelésben 122 ismeretlen rekord. Debianban
javítatlan találatok maradtak; a három kritikus azonosító értékelését és a
verziókat a [tételes triage](audit-evidence/hc23-43-20261102/dependency-triage.json)
és a teljes scannereredmény őrzi. A HA támogatott pinjeit nem írjuk felül
kézzel. A további upstream frissítés és bemeneti útvonalak vizsgálata nyitott;
**HC-43 nem zárható le ezzel a csomaggal**. A konténeres OS-scan a host kernelt
nem ellenőrzi.

Elsődleges források: [HA kiadás](https://www.home-assistant.io/blog/2026/10/07/release-202610/),
[Node támogatás](https://nodejs.org/en/about/previous-releases),
[OSV adatforrás](https://google.github.io/osv.dev/data/),
[Debian SSH](https://security-tracker.debian.org/tracker/CVE-2026-60002),
[Debian libxml2](https://security-tracker.debian.org/tracker/CVE-2026-6653),
[Debian kernel-fejlécek](https://security-tracker.debian.org/tracker/CVE-2026-99083).

## Megtörtént élesítés és rollback

Az élesítés a platform és a HA rövid kiesésével járt. Aktív öntözés vagy nem
nyugalmi/töltő robot esetén a parancs még az átállítás előtt megáll.
A már sikeresen lefuttatott helyi parancs; nem ismétlendő:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-security-20261102-r18/source/scripts/security_release/activate.py
```

A következő leírás a már sikeresen lefutott élesítési folyamatot rögzíti;
az aktiválást nem ismételjük. A helyi sudo a védett HA auth/config, a rendszerkonfiguráció és a systemd
módosítása miatt szükséges. A parancs hash-eket és r16 baseline-t ellenőriz,
hitelesített HA/Growatt állapotot rögzít, majd **minden éles szolgáltatás futása
mellett** teljes privát HA-másolatot készít és próbál ki hálózat nélkül.
A titkosított router-próba és a teljes meglévő repository-ellenőrzés után friss
helyi mentés készül. A leállított HA teljes eredeti állapota külön privát
rollback-másolatba kerül, mielőtt az új image használhatná az adatokat.

Az átállítás utáni kapuk: alkalmazás-health/readiness, PostgreSQL major/kolláció,
hitelesített HA API és a korábban elérhető Growatt-entitások, teljes HC/Git/router
mentés, visszaolvasás, SHA-256 és külön PostgreSQL-restore. Az automatikus
routermentés timerei csak a sikeres próbák után indulnak újra. A laborbemenet
exportjának külön hibája nem görget vissza már bizonyított mentési láncot.

A régi backend és a többi alkalmazás leállítása után a PostgreSQL még fut a
függő fan-ON szándékok SQL-átadásához. Csak a sikeres SQL-commit után áll le
az adatbázis. Rollbackkor az előző PostgreSQL-image külön, explicit image-ID-val
indul, és sikeres SQL-kapcsolat szükséges az átadáshoz, mielőtt a backend
újraindulhatna. Hibás DB-helyreállításkor a régi backend sem indulhat el.

Az r17 előzetes csomag élesítési jelzőjét e sorrendi javítás miatt visszavontuk;
nem került élesbe. Az eredeti lezárt forrás/bizonyítékok megmaradtak, kizárólag
az r18 wrapper használható.

Hiba esetén az átállítás visszaállítja az eredeti HA-adatbázist/configot és az
előző image-eket. Félbeszakadt műveletet nem szabad újraaktiválással felülírni;
ellenőrzés után az explicit helyreállító parancs:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-security-20261102-r18/source/scripts/security_release/activate.py rollback
```

Későbbi kiadás vagy aktív mentés/restore esetén a rollback megáll. Sikeres
élesítés után a `deployment-status.json`, `evidence/router-live-acceptance.json`,
`evidence/ha-live-acceptance.json` és `evidence/postgres-live-acceptance.json`
eredményeit kell átvenni. A fizikai bridge-/élőtérképpróba továbbra is felügyelt
utóellenőrzés; az izolált labor ezt nem helyettesíti.

## Megőrzött buildanyagok

A csomag `build-inputs/` könyvtára a nyilvános, ellenőrzött OS-csomagokat,
Dockerfile-okat, szülő-image ID-kat/digesteket és az npm cache-t is tartalmazza.
A `source/` és az evidence hash-eit a kiadás ellenőrzi. Opcionális újraépítés
előtt a csomagban levő `verify_build_inputs.py <kiadáskönyvtár>` ellenőrzi a
buildanyagokat. Az újraépítés nem élesítés; az új image külön tesztelést igényel.

A régi szülő-image-eket a context `manifest.json` azonosítja. A helyi FROM-tag
csak akkor használható, ha pontosan erre az ID-ra mutat; hiányzó upstream szülő
csak a rögzített digesttel tölthető le. OS build: a megfelelő megőrzött contexttel
`docker build --network=none --pull=false`, külön teszt-taggal. Frontend:
`source/infra/frontend` másolata és a megőrzött cache `.npm-cache` néven,
`NGINX_BASE_IMAGE` buildargumentumként a lockban rögzített proxy image-ID.
A Node alapimage digestje a Dockerfile-ban rögzített. A függőségek letöltése és
a build időbélyegei miatt bitazonos újrabuildet nem állítunk; az offline recovery
az archivált, pontosan ellenőrzött image-eket használja.
