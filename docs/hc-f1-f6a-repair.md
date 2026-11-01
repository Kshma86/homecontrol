# HC-17/18 és F6a: export és visszaállítás

**Frissítés, 2026-10-30:** HC-45 valódi friss KVM/systemd/Docker teljes restore,
ismétlés, mentés→restore, unit-rollback és reboot sikeres; helyben ellenőrzött,
nincs élesítve. [Bizonyítékok, szükséges r10-korrekciók és korlátok](hc45-vm-restore-20261030.md).
Az alábbi 2026-10-26-i bejegyzés történeti állapot.

2026-10-26. Helyi javítás, **nincs élesítve**. Az eredeti audit változatlan.
Érintett: HC-17, HC-18, HC-27, HC-28, HC-29, HC-37, HC-45, HC-46, HC-47.
Elolvasott alap: a kilenc megállapítás helye/bizonyítéka/ellenőrzése,
F0, F1 és F6a, valamint I/J/M/N érintett reprodukciói. A HC-24 mDNS-parser,
HC-41 MQTT-hozzáférés és HC-44 hostjogosultság nem része ennek a javításnak.

## HC-17 és HC-18 — egy exportleltár

A `backup_export_manifest.py` pozitív forrásleltárát használja az új
`export_config_snapshot.py`, a backend `settings.git_paths` és a UI mentési terve.
A `git_paths` ellenőrzött, olvasható leltár; eltérő lista mentését a backend
elutasítja. A hiányzó `infra/db`, `infra/proxy`, `infra/mqtt/config` és
`infra/mdns` bekerült, a Compose buildforrásai az `apps` alatt is megmaradnak.

Az export kizárja a Xiaomi auth minden névváltozatát, a Tuya privát configot,
`.env*`, `secrets.yaml*`, kulcs-, adatbázis-, log- és runtime-fájlokat.
Nem követ symlinket. Ismert hitelesítési JSON-mező vagy privátkulcs-fejléc esetén
a teljes új snapshotot elutasítja, érték kiírása nélkül. Ez célzott védelem,
nem általános titokfelismerési garancia. Először külön staginget készít;
csak ennek ellenőrzése után cseréli a checkout tartalmát, a `.git` megőrzésével.
Így a már követett titok a következő `git add -A`-ból is eltűnik.
A korábbi Git-commitok ettől még nem tisztulnak meg. A renderelt Compose mind a kilenc build-contextje, az opcionális profilokkal együtt, és minden Dockerfile COPY-bemenete megtalálható az exportban; a szükséges nyilvános configmountok is. Három kiadási image épült újra, a többi app image-ét nem cseréltük.

Az új F6 Git-worker és az új `gitea_config_status_f1.sh` ezt az exportert hívja.
A heti worker külön, privát manifestet generál a tényleges Xiaomi auth- és
backupfájlokkal, és ezt adja az age-bundle készítőjének. Az eredeti, éles
`export_gitea_config_snapshot.sh` és `secrets/manifest.txt` változatlan, mert
az éles régi timer közvetlenül használja őket. A canonical exporter csak az
**inaktív kiadási forrásban** lett az új CLI-re mutató wrapper.

Bizonyítás: friss/meglévő checkout, már követett titok eltávolítása,
auth `.json/.bak` változatok, ismeretlen credential miatti fail-closed;
valódi age encrypt/decrypt szintetikus titkokon, validált restore, `0600` módok.
Az inaktív kiadáshoz külön valódi, titkosított csomag is készült: 12 fájl,
köztük két Xiaomi auth-változat és az előkészített app/reader környezet.
Az éles secretfájlok és a régi bundle nem változtak. Ezt a valódi csomagot nem
fejtettük vissza; az offline visszafejtő kulcs ellenőrzése a hostpróba része.

## HC-27 — előellenőrzés, csere, napló és recovery

Az új `backup_restore.py` előbb ellenőrzi **a teljes kijelölést**: mód,
megerősítés, létező kiválasztások, egy archívumgyökér, duplikátumok,
komponensek, útvonalak, típusok, linkek és az in-place DB-tiltás.
Minden payload saját privát stagingbe kerül; meglévő SHA-manifest esetén
a teljes belső checksumkészletet ellenőrzi, készrejelentő receipt esetén az
archívum hash-ét is. Manifest nélküli régi webes archívum állapota
`legacy_unverified`, nem lesz belőle igazolt mentés.

Minden előállapotot ment a célírás előtt. A run ID-s `journal.json` tartalmazza
a tervet, előképeket, módokat/időket, alkalmazott/hátralévő tételeket és a
létrehozandó szülőkönyvtárakat is, még a `mkdir` előtt. Egy fájl cseréje
azonos szülőben készült ideiglenes fájllal, fsync-kel és `os.replace`-szel történik.
A bejárás directory descriptorokat és `O_NOFOLLOW`-t használ.
**Több fájl együtt nem tranzakció.** Hiba esetén HTTP 409 és `partial`, run ID,
alkalmazott/hátralévő lista, `recovery_required` érkezik; a frontend megtartja
a strukturált hibát. A tároló hibája a végső naplóíráskor sem jelenthet sikert.

Az aktív/félbemaradt naplók a backup payload `restore_recoveries` listájában
újra megjelennek böngésző- vagy processzújraindítás után. Visszagörgetés:
`POST /api/backup/restore/recover`, JSON: `run_id` és `confirm: "ROLLBACK"`.
A UI külön megjeleníti a részleges műveletet; a megerősítés mezőbe `ROLLBACK`
írható. Az endpoint ellenőrzi az aktuális célleltárt és az előképek útját,
és későbbi kezelői fájlmódosítás esetén megáll, megőrzi azt. A visszagörgetés
ismételhető. Tároló-/jogosultsághiba után előbb az okot kell rendezni;
a privát run könyvtárat addig nem szabad törölni.

Restore/recovery a F6 közös backup-lockját használja; futó backup mellett
nem kezd írni. Ez nem zárja ki egy másik hostfolyamat kézi fájlmódosítását.
Az élő szolgáltatásokkal összefüggő fájl-visszaállítás továbbra is karbantartási
művelet: a fájlcsere nem jelenti a szolgáltatások vagy a DB automatikus átállítását.

Bizonyítás: késői tiltott DB/hiányzó komponens előtt változatlan cél;
ENOSPC és permission-hiba; valódi külön processz `os._exit` a csere után,
új szülőkönyvtárakkal; naplófelderítés és recovery; későbbi kezelői szerkesztés
megőrzése; valódi Flask 400/409/recovery-200 válaszok.

## HC-28 — metaadat- és linkpolitika

A restore megtartja a fájlok és könyvtárak alsó kilenc módbitjét, mtime-ját,
az üres könyvtárakat és a script futtathatóságát. A directory-metaadat a gyermekek
létrehozása után kerül vissza. Setuid/setgid/sticky archívumbit és idegen
UID/GID nem kerül vakon a célra; meglévő fájl tulajdonosa lehetőség szerint
megmarad, új fájl a végrehajtó tulajdona. Az előképhez a régi mód/mtime is tartozik.

Támogatott: relatív symlink `..` és abszolút cél nélkül, saját komponensen belül;
hardlink, ha a hivatkozott rendes fájl is ki van jelölve. Speciális fájl,
link alatti másik archívumtag, fel nem oldható/ki nem jelölt hardlinkcél,
meglévő céloldali symlink vagy fájl/könyvtár típusütközés előre hibát ad.
A szigorú linkpolitika szándékos: szükség esetén külön jóváhagyott kézi
helyreállítás kell, nem csendes típusvesztés.

Bizonyítás: `0750`, `0600`, mtime, üres `0710` könyvtár, suid levétele,
symlink, valódi közös inode-os hardlink, special/escape elutasítása;
a valódi új F6-archívumból visszaállított script ténylegesen futott.

## HC-29 — közös fájlhatár a diffhez is

A compare ugyanazzal a canonical útvalidátorral választ célt, mint a restore,
még az archívum vagy célfájl olvasása előtt. Abszolút út, `..`, backslash,
ismeretlen komponens, symlink szülő/cél elutasított. Aktuális fájlt descriptorral,
`O_NOFOLLOW` és méretkorlát mellett olvas. Archívumból csak rendes UTF-8 fájl
hasonlítható össze; linkből nem olvas be másik archívumtagot.

## HC-37 — tartalmi smoke, rögzített snapshot

A shell belépő az új `restore_smoke.py`-t hívja. A JSON snapshotlistából csak
`homecontrol` tagű elemet választ, majd a **teljes snapshot ID-t** továbbítja.
A visszaállított canonical backupkönyvtárban tényleges, nem symlink archívum
kell. Üres találat vagy hibás teljes checksumkészlet hiba; nincs `find` exitkódra
épített hamis siker. A legújabb, más tagű snapshot nem írja felül a kiválasztást.

`backups/restore-smoke-result.json` külön jelzi a fájl-/restic-/DB-bizonyítást.
Alapmódban a DB `not_run`. `--db-check` külön, hálózat és hostport nélküli PG16
konténerbe valódi `pg_restore --exit-on-error` próbát futtat; ez owner/ACL nélküli
DB-tartalmi próba, nem teljes hostrestore. A végső valódi DB-smoke is sikeres, 52 HC-táblával; a teljes adat/index készlet friss, --rm-mel törlődő anonim PGDATA kötetre kerül, nem korlátos tmpfs-be. A valódi régi dump owner/ACL-es
restore-ját külön labor igazolta. Távoli restic/Gitea állapotát nem állítjuk
ellenőrzöttnek a helyi próbákból.

Bizonyítás: üres snapshotlista/találat, más tagű újabb snapshot, sérült archívum;
valódi helyi, titkosított restic repository backup/restore és SHA-ellenőrzés.

## HC-45 — explicit hosttelepítés; végső VM-próba nyitott

A full bootstrap a stack indítása után az `install_restore_host.py --apply`
belépőt hívja. Ennek 14 unitos manifestje a 12 F6 unit és a post-boot health
service/timer. Egyetlen system scope marad. Meglévő user manager esetén
visszavonja a két régi user timert; hiányzó account/bus csak explicit fresh-host
módban fogadható el, és előtte a user unitforrásokat is ellenőrzi.
Halott busz önmagában nem bizonyítja a duplikáció hiányát.

A telepítő közös lockokkal várja/kizárja a futó mentést, menti a korábbi
installed unitokat és enabled állapotokat, alkalmazza a mentési ütemezést,
ellenőrzi a telepített bájtokat, active állapotot és minden engedélyezett timer
következő triggerét. Hibás átálláskor megkísérli a mentett installed állapot
visszaállítását. A fresh-host apply watcher későbbi beállításmentéskor is ezt
a hostmanifestet tartja meg. Normál backend-startup továbbra sem telepít hostunitot.
`Persistent=true` miatt azonnali lejárt trigger is lehet; az installer alatt
a közös backup-lock megakadályozza a mentési átfedést.

11 manager-contract teszt, kétszeri teljes bootstrap canonical tmpfs-en,
14 unit és next-trigger ellenőrzése sikeres. Ebben a systemctl/Docker/Git/age/
restic külső műveleteit kontrollált fixture helyettesítette. **Ez nem valódi
üres VM-en futó systemd manager bizonyítéka.** A gépen nincs elérhető VM-futtató;
az audit által előírt üres hostos, ismételt systemd-próba és az offline age-kulcs
helyreállítási lánca még elvégzendő. Ezért HC-45 státusza:
**Javítva – ellenőrzésre vár**, nem teljesen lezárt auditpont.

## HC-46 — a dump az aktuális archívumhoz kötött

A bootstrap `restore_archive.py` segítségével a kiválasztott snapshot pontos
archívumát ellenőrzi. Abban pontosan egy rendes, nem üres `postgres/*.dump`
kell; nincs teljes stagingfán kereső fallback. Egyedi, privát
`selected-archive-*` könyvtárba kerül, a selection JSON rögzíti az archívum és
a dump SHA-ját és a relatív tagnevet. A teljes checksum és `pg_restore --list`
ellenőrzés a stackek leállítása és DB-eldobás **előtt** fut; a dump hash-ét
közvetlenül a csere előtt újra ellenőrzi. A DB-restore `--exit-on-error`-ral fut.

Bizonyítás: újabb→régebbi archívum közös work-dirrel, DB nélküli új archívum
régi staging mellett, hibás checksum; a full bootstrap fixture-ben a hiányos
és sérült mentés előtt egyetlen Docker-művelet sem történt. Valódi új
F6-archívum: kb. 110 MB, 17 ellenőrzött fájl, 111 367 498 bájtos dump;
visszaállítás a külön PG16 célba 0 exitkóddal.

## HC-47 — canonical full target, validált secret tar

A full/apply/DB/start út csak `/srv/docker/homecontrol` targetet támogat.
A bootstrap és a magic launcher eltérő cél esetén még apt/clone/stop/copy/secret
művelet előtt leáll. Staging-only esetén más target/work-dir megadható, de ez
nem fizikai futtatási sandbox. A full `--start` a kiválasztott, ellenőrzött
DB-restore ágat is megköveteli; fájl-apply önmagában nem teljes rendszerindítás.

A visszafejtett tar teljes leltára validált az írás előtt: csak rendes fájl/
könyvtár, duplikátum és path escape nélkül. HC-titkok csak a canonical project
alá, hosttitkok külön `/etc/homecontrol/` prefixre kerülhetnek; a két
bundle-metaadat a stagingben marad. Nincs nyers `age | tar -C /` alkalmazás.
A fájlok atomi csere útján, `0600` móddal, symlink szülők követése nélkül
kerülnek a célra. A plaintext archívum és secret staging privát munkakönyvtárban
marad; a staging-only művelet után a kezelőnek kell biztonságosan eltávolítania.

## Közös kiadás, visszaállás és megmaradó függőségek

Az inaktív csomag: `backups/releases/hc-refactor-20261026-r4/`.
Külön backend/frontend/ingest és korlátozott rollback-backend image készült;
az r3 ingest élő visszajelzési javításai megmaradnak. Privát app/reader env,
release/rollback Compose-terv, image ID-k és forrás-SHA-k tartoznak hozzá.
A régi r2 backend nyersen nem HC-39/F6/HC-31 kompatibilis: a rollback image
read-only sémacheckeket használ, a SQL Lab mindhárom útját, a webes backup
módosításokat és az AI power-kéréseket ideiglenesen 503-mal zárja.
Az új F6 hostrunner/lock a programrollback alatt is megmarad; DB-downgrade
vagy mérési adatvesztéssel járó automatikus dump-visszaállítás nincs.

Valódi külön PG16/PgBouncer/MQTT mellett a release → rollback → release
fázis health, frontend, ingest heartbeat és szerepkörvédelme sikeres.
6 673 183 mérési sor megmaradt; a konfigurációs mezők hash-e nem változott.
Az explicit HC-07/39 migráció ismételt futtatása is sikeres. A private namespace
hálózat nélküli PG konténeréhez csatlakozott; nem volt hostport, host Docker
socket vagy éles eszközkapcsolat. A teljes backend regresszió és a frontend
build pontos, végső eredménye az AUDIT_REPAIR naplóban és a csomag evidence
könyvtárában található.

Még szükséges: HC-45 valódi üres VM/systemd és offline kulcs próba;
HC-31 külön felügyelt fizikai AI-próba; a távoli Gitea/restic aktuális
elérhetőségének és történetének külön ellenőrzése. Ebből nem következik, hogy
titok jutott a távoli Gitbe; ilyet most nem vizsgáltunk és nem írtunk át.
Éles átadáskor a régi backup workerek/pending AI-szándékok leállítása,
dupla user timer visszavonása, közös lock, új hostkód, app/reader role és
PgBouncer/backend/ingest összehangolt cseréje szükséges. HC-38 baseline meglévő
DB-re tilos; csak 059/060/061 explicit migráció kell. A HC-24/41/44 nyitott
pontokat nem javítottuk és nem zártuk le automatikusan.
