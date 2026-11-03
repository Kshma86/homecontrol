# F6 — HC-19, HC-25, HC-30, HC-42 javítása

Állapot: **helyben ellenőrzött, nincs élesítve**, 2026-10-23.
Az éles r2 backend/frontend és a telepített host timerek változatlanok.
Az audit HC-19/25/30/42 bizonyítékait, F0/F1/F6 és M.3 részét áttekintettük.

## Közös végrehajtó és eredmény

A `scripts/backup_runner.py` az egyetlen új host végrehajtó. A web csak fix
`local`, `weekly` vagy `git` kérést ír a `backups/requests/` könyvtárba és **202**
választ ad futásazonosítóval. A rendszerütemező ugyanazt a végrehajtót hívja;
`check` és `maintenance` módja a restic ellenőrzést és logkarbantartást is
ugyanazzal a kizárással futtatja. A kérés nem archívum és nem sikerjelzés.

A közös `homecontrol-backup.lock` minden új módot sorosít. A heti mód előtte a
korábbi `ai-backup.lock`-ot is felveszi, az eredeti heti AI-guard és a régi
shell lock-sorrend kompatibilitásához. A későbbi, helyi HC-31 kiegészítésben
minden F6 mód új generációval törli a korábbi AI-kikapcsolási szándékot;
a végrehajtáskori SSH/OFF mindkét backup lockot foglalja. A lock FD-jét a worker is örökli;
a koordinátor kilövése nem nyithat párhuzamos mentési ablakot, amíg a worker él.
Az örökölt FD a Linux flock szerint ugyanahhoz a zároláshoz tartozik;
forrás: [flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html),
[Python subprocess pass_fds](https://docs.python.org/3/library/subprocess.html).
SIGTERM/timeout a worker folyamatcsoportját állítja le. Az egyes systemd unitok
`KillMode=control-group` beállítást kapnak. Busy közvetlen timer/CLI hívás 75-tel
kilép, a webes sorba állított kérés kivárja a lockot. A futásállapotok:
`queued`, `running`, `completed`, `failed`; félbeszakadt worker az olvasási modellben
`interrupted`. A később induló másik futás nem teszi újra aktívvá az elárvult régi futást.

A `backup-state.json`, `runs/<id>.json` és `backup-targets.json` kis, atomikusan
cserélt állapotfájlok. Célonként külön `last_attempt`, `last_status`, `last_success`
és `last_failure` szerepel. Indulás/kihagyás nem gyárt új sikerdátumot; másik cél
sikere nem törli az előző restic/Git hibát. A queue csak kész JSON-kérést kap;
a félkész fájl a figyelt könyvtáron kívül marad. Ismeretlen parancs/mód/mező
karanténba kerül, nem fut host shellként. A figyelt könyvtárban nem maradhat
ideiglenes/hibás kérés, mert a [systemd.path](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html)
azonnal újraellenőrzi a `DirectoryNotEmpty` feltételét a service végeztével. A drain hibás futás után is feldolgozza
a többi kész kérést, de végül hibás exitkódot ad, ha bármelyik kötelező feladat hibázott.

## Archívum tartalma és készre jelentése

A korábbi **host shell tartalma** lett az egységes helyi szerződés, így a UI többé
nem használ eltérő, memóriában dumpot gyűjtő Python-mentést. A kiválasztott elem
hiánya hiba, nem csendes sikeres kihagyás.

| Tartalom | Korábbi webes Python | Korábbi host shell → új közös út |
|---|---|---|
| PostgreSQL custom dump | Teljes bytes/BytesIO memóriában | `pg_dump` stdout közvetlenül fájlba streamelve |
| Apps, infra, külön Zigbee data, HA, scripts | Saját tar-lista és kizárások | A host korábbi kapcsolói és rsync/cp szerződése |
| Docker/host meta | Eltérő JSON-részhalmaz | Host meta és a bekapcsolt Docker-leltár |
| Belső ellenőrzőösszeg | Csak manifest | Manifest + minden normál fájl SHA-256-a |
| Docker volume, media, helyi Gitea gyökér | A Python create nem használta | Restic opcionális extra forrásai, **nem a helyi tar részei** |
| Retention | Külön, véglegesnek látszó tarokon | Csak ellenőrzött kész helyi mentés publikálása után |

A helyi `coverage` a hét `include_postgres/apps/infra/zigbee2mqtt/homeassistant/
scripts/docker_meta` kapcsolót rögzíti. Ezek bármelyike kikapcsolható: a mentés
ilyenkor tudatosan részleges. A `weekly` a kért munkafolyamatot jelöli, nem azt,
hogy a helyi tar önmagában a távoli AI-gép teljes tartalma.

A restic a helyi kész archívumon túl a korábbi host viselkedését őrzi: meglévő
apps/infra/HA/scripts gyökereket is ment, illetve külön kapcsolóval Docker
volume-okat, mediát, helyi Giteát. A helyi `include_*` kapcsolók nem változtatják meg
visszamenőleg e nyers restic-források korábbi jelentését. A nyers, futó volume/mappa
nem helyettesíti a PostgreSQL dumpot; a teljes host/alkalmazáshelyreállítás más
ellenőrzési szint marad.

Új név: `homecontrol_<másodperc>_<32 karakteres futásazonosító>.tar.gz`.
Folyamat: staging → belső SHA/manifest → `.partial` tar → gzip/tar és streamelt
belső checksum-ellenőrzés → atomi átnevezés → fsync + `.tar.gz.complete.json`.
A receipt a teljes archívum SHA-256-át, méretét, mtime-ját és ellenőrzött
fájlszámát is rögzíti. **A receipt a készre jelentési pont.** Enélkül az új nevű
archívum a listában, legutóbbi sikerben és közvetlen megnyitáskor sem elérhető.
Az API nem hash-eli újra az egész archívumot minden GET-nél: az utolsó ellenőrzött
receipt és a jelenlegi fájlstat egyezését használja. Új integritásvizsgálat explicit művelet.

A második ellenőrzés DC-01/DC-02 hibái helyben javítva: csak a gyökérszintű
saját `MANIFEST.txt`/`SHA256SUMS.txt` marad ki a forráschecksum-listából;
a belső könyvtárak azonos nevű fájljai is ellenőrzött tartalom. A tar hardlinkje
a már beolvasott, azonos gyökérben levő céltartalom hash-ét kapja, majd a saját
útvonalához tartozó checksumhoz is összevetjük. Hiányzó/idegen/előre mutató
linkcél elutasított, kicsomagolás nincs. **46 célzott mentési teszt sikeres**,
köztük 5 új regresszió; a korábbi nagy archívum teljes SHA-ja is egyezik.
[Javítási részletek és megmaradt bevezetési feltételek](hc-block-double-check.md).

A régi tarok megmaradnak, listázhatók és inspect/restore forrásként elérhetők,
de `legacy_unverified` jelölést kapnak; puszta mtime alapján nem sikeres mentések.
Egy régi, belső SHA256SUMS-szal rendelkező archívum explicit vizsgálata:

```bash
python3 scripts/backup_runner.py --verify-existing homecontrol_<korábbi-név>.tar.gz
```

Ez is a közös lock alatt fut; aktív mentés mellett elutasított. Csak sikeres
streamelt belső ellenőrzés után készít receiptet (`verified_existing`). A korábbi
Python-archívum, amelynek nincs belső checksumlistája, nem fog ettől ellenőrzöttnek
látszani: külön restore-/integritáspróba szükséges. Nem írunk automatikusan
sikertörténetet a régi fájlokra. A retention a még ellenőrizetlen régi tarokat,
árva/hibás/félkész fájlokat nem törli; meglévő ellenőrzött mentést is csak új,
ellenőrzött helyi mentés után és a beállított korhatárral törölhet.

## Heti mentés és független célok

Heti sorrend: a korábbi AI wake/SSH várakozás → opcionális titkosított secretbundle
frissítés → Git origin/offsite → AI Gitea dump → **mindig megkísérelt helyi és kötelező
restic mentés**. A Git/export vagy Gitea dump hibája nem szakítja el az utóbbi utat.
SSH-várakozás lejártakor is folytatódik a helyi mentési kísérlet; a kötelező restic
hibát jelez, ha távolra nem tud menteni. A heti restic a napi `restic_enabled=false`
mellett is kötelezően megkísérelt; a heti kapcsoló a timer engedélyezése.

Bekapcsolt Gitnél az origin és a bekapcsolt offsite külön cél, külön push és
külön eredmény. Origin hiba után az offsite push is lefut; nincs force-push vagy
előzményátírás. Nem fast-forward elutasítás is valódi célhiba marad. A kézi webes
Git commit szintén a közös `git` módba kerül, a megadott üzenettel; a régi
`gitea_config_status/restore` olvasó/staging funkciókhoz nem nyúltunk.

Kötelező heti cél a helyi archívum, restic és Gitea dump, továbbá az engedélyezett
Git célok. Secretbundle-frissítés a korábbi szerződés szerint opcionális, de
hibája külön látszik. Restic snapshot és restic retention külön eredmény: sikertelen
prune nem tünteti el a sikerült snapshot idejét, de a futás hibás. Napi best-effort
restic-hiba mellett lehet kész helyi archívum; a remote hiba ettől látszik.
A HC-31 helyi kiegészítésben a heti/check worker futásazonosítóval állítja sorba
a befejező shutdownkérést, miközben a lock még él. Az SSH csak a lock felengedése
után indulhat; köztes kézi wake vagy új szándék visszavonja a régi callback jogát.
Régi requestfájlból nincs automatikus visszajátszás. Az új runner valamennyi módja
és az AI-leállítás közös koordinációt használ; az éles legacy scriptek változatlanok.
[HC-31 működés, ellenőrzés és bevezetési határ](hc31-ai-power-coordination.md).

## Korlátos, tiszta olvasási modell

A logolvasás legfeljebb 256 KiB-ot és legfeljebb 2000 sort olvas seekkel, nagy
sor/rotáció/hiány esetén is. A JSON státuszolvasás legfeljebb 128 KiB, a receipt
8 KiB, a friss futásokból legfeljebb 20 kerül vissza. Hiányzó lockot az olvasás
nem hoz létre, meglévőt `rb` megnyitással/flockkal vizsgál. Jogosultsági hiba
`None`/ismeretlen, nem igazoltan szabad lock. A HC-31 kiegészítés AiNodeService
és BackupService guardja ugyanezt az olvasási szerződést és mindkét backup lockot használja.

`latest_info()` és `archives()` közös, receiptet értelmező leltárt használ.
Settings/request/lock/checksum, az új félkész vagy commitálatlan tar nem lehet
sikeres utolsó mentés. A legutóbbi jó helyi mentés akkor is látszik, ha a legutóbbi
futás távoli cél miatt hibás; a futás és a célok hibája külön marad. A UI a saját
`run_id`-ját követi: egy másik futás vagy régi archívum nem zárja sikerrel a kérését.

## Külön, explicit hostbevezetés

A régi `scripts/backup_hc.sh`, `weekly_ai_backup.sh`, `sync_config_to_gitea.sh`,
`maintenance_logs.sh`, apply/install scriptek és `scripts/systemd/` eredeti unitjai
**byte-pontosan megmaradtak**. Ezekre az éles timerek és a régi automatikus apply-path
közvetlenül hivatkoznak; helyi kódjavítás közben nem vezethettük be az új munkafolyamatot.
Az új workerfájlok belső adapterek, a publikus belépési pont a `backup_runner.py`.

A `scripts/systemd/f6/` 12 külön templatesource-t tartalmaz. A
`install_backup_f6.py` alapértelmezésben **csak tervet** ír:

```bash
python3 scripts/install_backup_f6.py
```

Későbbi, összehangolt kiadáskor az explicit admin lépés:

```bash
sudo python3 scripts/install_backup_f6.py --apply --wait-idle
```

Ez **most nem futott**. A telepítő az `a` user managerét előellenőrzi; nem elérhető
buszt nem tekint sikeres tiltásnak. Idle állapotban menti a telepített unitok bájtjait
és enabled állapotait privát `backups/f6-unit-rollback/<id>/` csomagba, leállítja a
régi apply-watchert, tiltja a két redundáns felhasználói backup/log timert, majd
rendszerscope-ba telepíti az új végrehajtókat. Az új apply-watcher kerül vissza utoljára.
A napi/heti kezelői időpont és tiltás megmarad; restic check továbbra is **az első
vasárnap 04:30, legfeljebb 45 perc jitterrel**, a logkarbantartás napi 03:30.
Aktív régi service esetén a telepítő elutasít/újrapróbálást kér, nem öl futó mentést.
A sikerhez ellenőrzött rendszerunit-állapot és letiltott user timerek kellenek.

A webes sorhoz az új `.path` kell, ezért a backend/frontend és host unitok kiadása
együtt készítendő elő. A telepítés előtt beállított kérés megmarad queued állapotban;
az új helper később feldolgozhatja. Bevezetéskor ne induljon két backend/runnercsalád.
A jelenlegi r2 fagyasztott Compose-kiadását nem módosítjuk általános `up --build`-del.

## Ellenőrzés, függőségek, rollback

Az eredeti F6 körben **667 backendteszt**, köztük 21 új processz/archívum/protokoll és 8 új installer-eset,
0 hiba/kihagyás; **93 frontendteszt** (83 mower + 4 AI + 6 backup) és production build.
A valódi Flask út 202 → queued → host drain → verified completed eredményt adott.
Saját PG16-ba visszaállított r2 teljes dumpból az új közös runner **111 367 498 bájtos**
custom dumpot streamelt; az új archívum 15 belső fájlchecksumja és teljes SHA-ja
ellenőrzött. Külön DB-be `pg_restore` exit 0; 52 HC-tábla számlálói,
17 üzleti tábla pontos soradata és teljes HC-katalógus egyezik,
**6 673 183 mérési sorral**. A mért gyerekfolyamat max RSS 29 156 KiB volt;
ez konkrét laborfutás megfigyelése, nem általános terhelési garancia.

Valódi Git-próba két saját helyi bare repositoryval: mindkettő sikeres; origin
push hookkal elutasítva, offsite ténylegesen frissül; fordítva az origin sikeres,
offsite hibás, összesített exit 1. Tényleges, helyi titkosított restic repositoryban snapshot, `restic check` és
az archívum visszaolvasása is sikeres; a visszaolvasott SHA-256 egyezik. Távoli
Gitbe írás nem történt. A távoli
Gitea/restic/wake/shutdown többi hibapróbája szintetikus parancsadapterrel futott;
éles AI-gépet nem ébresztettünk/állítottunk le, távoli restic-integritást nem igazoltunk.
A systemd manager átállása fake-manager szerződéspróba volt, nem éles telepítés;
a statikus unitverify exit 0 mellett a host manager/bus elérési figyelmeztetései
megmaradtak. Privát bizonyíték: `/tmp/hc-f6-repair`.

Függőségek: az **F1 mentési exporthatára (HC-17/18) nyitott**, a régi exporter
bizonyított titok-/tartalomhibáját nem javítottuk; új éles Git-publikálás előtt ezt
rendezni kell. A HC-24 mDNS nem ennek a javításnak technikai része.
A HC-31/F6b azóta helyben javított és ellenőrzött, nincs élesítve;
a HC-27–29/37/45–47 restorehibák és a teljes hosthelyreállítás továbbra is
külön munka. A HC-07/38/39 helyi javítás bevezetése továbbra is explicit 059/060/061,
role/ACL, DSN/pool és külön kiadás; az admin dump a hoston marad, nem a runtime app-role feladata.

Sikertelen installer-átmenetnél a mentett telepített bájtok és enabled állapotok
visszaállítása hibainjektálással ellenőrzött. Ez visszahozza a korábbi konfigurációt,
nem állítja, hogy annak régi hibái megszűntek. Archívumot, journalokat vagy adatbázist
nem törlünk rollbackként. Későbbi teljes kiadási rollbackhez előre fagyasztott
backend/frontend/host forrás, a privát unitbundle és külön próba kell; **r2-re teljes
éles átadás/visszaállás most nem történt**. A közös lock, az egyetlen kijelölt
ütemező és a helyes archive-read modell rollbackkor is megtartandó. A régi webes
Python create visszakapcsolása a kettős végrehajtót visszahozná, ezért önmagában nem
kompatibilis rollback; szükség esetén a backup-író webes műveletek lezárása kell,
amíg a közös végrehajtót/olvasómodellt megőrző rollback build elkészül.
