# HomeControl backup and restore runbook

Ez a runbook a HC szerver helyi archívumait, az AI szerver HDD-n lévő restic repositoryt és a Gitea konfigurációs repositoryt kezeli együtt.

## Gyors állapotellenőrzés

```bash
tail -n 80 /srv/docker/homecontrol/backups/backup.log
systemctl list-timers 'homecontrol*backup*' 'homecontrol-restic-check*'
```

Elvárt rétegek:

- napi helyi `homecontrol_*.tar.gz` archívum a HC szerveren
- heti kötelező restic snapshot az AI szerver HDD-jére
- Gitea `homecontrol/config` repository a kézzel szerkesztett konfigurációknak
- havi `restic check`

## Nem romboló restore próba

```bash
cd /srv/docker/homecontrol
sudo scripts/restore_smoke_test.sh
```

A script ideiglenes könyvtárban dolgozik. Ellenőrzi, hogy a legfrissebb tar archívum listázható, van benne manifest és checksum fájl, a Gitea repo elérhető, és ha a restic engedélyezett, a legfrissebb snapshotból vissza tud hozni legalább egy HC archívumot.

## Restic repository ellenőrzés

```bash
cd /srv/docker/homecontrol
sudo scripts/restic_check_ai_backup.sh
```

Automatikusan havi timer is futtatja:

```bash
systemctl status homecontrol-restic-check.timer
journalctl -u homecontrol-restic-check.service -n 80 --no-pager
```

## Konfiguráció visszaállítása Gitea-ból

```bash
GIT_SSH_COMMAND='ssh -i /srv/docker/homecontrol/infra/ssh/ai_node_key -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
git clone ssh://git@192.168.1.2:2222/homecontrol/config.git /tmp/hc-config-restore
```

Innen kézzel érdemes összehasonlítani és átmásolni a szükséges fájlokat. A repository szándékosan nem tartalmaz titkokat, adatbázisokat, logokat és runtime cache-eket.

## Gitea kézi workflow

A `/srv/docker/homecontrol` könyvtár jelenleg nem normál Git working tree-ként működik. Emiatt a Gitea workflow külön, biztonságos snapshot scriptekkel dolgozik: előállít egy szűrt konfigurációs képet, összeveti a Gitea repo aktuális állapotával, majd csak ezt commitolja/pusholja.

### Mit tartalmaz a Gitea snapshot

A Gitea repo célja a kézzel szerkesztett, szöveges HC állapot verziókövetése. Ez nem váltja ki a resticet és nem teljes gépmentés, hanem gyorsan böngészhető, commit historyval rendelkező konfigurációs/projekt snapshot.

Jelenlegi mentett területek:

- `homeassistant/config`
- `homeassistant/docker-compose.yml`
- `infra/docker-compose.yml`
- `infra/backend`
- `infra/frontend`
- `apps`
- `scripts`
- `docs/ai/backup-domain.md`
- `docs/backup-restore-runbook.md`

Szándékosan kizárt területek:

- `.env` fájlok
- `secrets.yaml`
- `infra/ssh`
- adatbázisok és SQLite fájlok
- logok
- cache/runtime könyvtárak
- Home Assistant `.storage`, `deps`, `tts`
- PostgreSQL/MQTT/Zigbee runtime data/log
- frontend `node_modules`, `dist`, `build`
- lokális capture/export jellegű adatok

Ez azért fontos, mert a repo legyen olvasható és visszakereshető, de ne kerüljön bele jelszó, kulcs, token, adatbázis vagy nagy futásidejű szemét.

### Hárompéldányos Git modell

A tervezett biztonsági modell így néz ki:

1. HC szerver: itt él a futó HomeControl projekt.
2. AI szerver Gitea: ide kerül a szűrt, verziózott HC snapshot.
3. Külső Git fiók, például GitHub: ide kerül opcionális offsite mirror.

Ez azért erős, mert nem csak egy másik lemezen van mentés, hanem a szöveges konfiguráció/projekt állapot egy külső Git szolgáltatóban is megvan. A külső Git repo nem adatbázis- és volume-backup, hanem verziózott projekt/config másolat.

Az offsite Git mirror beállításai a Backup tab `Backup Settings / Gitea / Git` részében vannak:

- `Offsite Git mirror enabled`
- `Offsite remote`
- `Offsite branch`
- `Offsite token file`
- `Offsite SSH key`

HTTPS tokenes GitHub remote példa:

```text
https://github.com/FELHASZNALO/homecontrol.git
```

A token ne kerüljön a remote URL-be és ne kerüljön a webes beállításba. A javasolt hely:

```text
/srv/docker/homecontrol/infra/ssh/git-offsite-token
```

Ez a fájl nincs Gitea snapshotba exportálva, mert az `infra/ssh` kizárt terület. A sync script GitHub push közben ideiglenes `GIT_ASKPASS` helperrel olvassa a tokent, így a token nem jelenik meg a logban és nem lesz commitolva.

SSH-s külső remote is használható, ha az `Offsite SSH key` egy olyan privát kulcsra mutat, amelynek publikus párja fel van véve a külső Git fiókba.

Fontos: a külső Git repo törlése külön, kézi megerősítést igénylő művelet. Üres repo-k törlése előtt mindig nézd meg a pontos repo nevet, owner nevet és hogy tényleg nincs-e benne értékes commit.

### Webes Gitea Control panel

A Backup tabon a `Gitea Control` panel ugyanazokat a scripteket futtatja, mint a CLI workflow, csak kényelmes gombokkal.

`Status / Diff`:

1. A backend meghívja a `scripts/gitea_config_status.sh` scriptet.
2. A script ideiglenes könyvtárba klónozza a Gitea repo `main` branchét.
3. Lefuttatja a `scripts/export_gitea_config_snapshot.sh` exportert.
4. Git stagingbe teszi az exportált állapotot.
5. Ha nincs változás, ezt írja: `Nincs változás a Gitea snapshothoz képest.`
6. Ha van változás, megmutatja a `git status --short` listát és a diff statot.

`Commit & Push`:

1. A webes commit message mező értékét küldi a backendnek.
2. A backend meghívja a `scripts/gitea_config_commit.sh` scriptet.
3. A script friss snapshotot exportál.
4. Ha nincs változás, nem készít üres commitot, hanem `Nincs változás, push kihagyva` üzenettel kilép.
5. Ha van változás, commitolja és pusholja a `ssh://git@192.168.1.2:2222/homecontrol/config.git` repositoryba.
6. Ha az offsite mirror engedélyezve van, ugyanazt a snapshot branch-et a külső Git remote-ra is pusholja.
7. A Backup Activity panelben a Gitea sor frissül.

`Restore to Staging`:

1. A `Restore ref` mezőben megadható branch, tag vagy commit hash. Alapértelmezett: `main`.
2. A backend meghívja a `scripts/gitea_config_restore.sh` scriptet.
3. A script a kiválasztott refet staging mappába klónozza.
4. Éles HC fájlokat nem ír felül.
5. A staging mappából kézzel lehet diffelni és csak a szükséges fájlokat visszahozni.

`Open Gitea`:

Megnyitja a Gitea webes repository oldalt:

```text
http://192.168.1.2:3002/homecontrol/config
```

Privát repo esetén belépés nélkül 404 vagy üres oldal normális lehet. Ilyenkor előbb be kell jelentkezni Gitea-ba.

### CLI alternatívák

Státusz és diff stat:

```bash
cd /srv/docker/homecontrol
scripts/gitea_config_status.sh
```

Kézi commit és push:

```bash
cd /srv/docker/homecontrol
scripts/gitea_config_commit.sh "Leíró commit üzenet"
```

Külön branch használata:

```bash
cd /srv/docker/homecontrol
GITEA_BRANCH=teszt-valtozas scripts/gitea_config_commit.sh "Teszt konfiguráció snapshot"
```

Nem romboló restore stagingbe:

```bash
cd /srv/docker/homecontrol
scripts/gitea_config_restore.sh main
```

Konkrét commit vagy branch stagingbe:

```bash
scripts/gitea_config_restore.sh 0770d86
scripts/gitea_config_restore.sh teszt-valtozas
```

Alapértelmezett restore cél:

```text
/srv/docker/homecontrol/restore_staging/gitea-config-YYYY-MM-DD_HH-MM-SS
```

Ez nem ír felül éles fájlokat. Először diffeld, utána csak a szükséges fájlokat mozgasd vissza.

### Javasolt használati rend

Napi munka után:

1. Backup tabon `Status / Diff`.
2. Ha van értelmes változás, adj rövid commit message-et.
3. `Commit & Push`.
4. Nyisd meg Gitea-ban a commit historyt, ha ellenőrizni akarod.

Nagyobb módosítás előtt:

1. `Status / Diff`, hogy tiszta-e a kiinduló állapot.
2. Ha van régi, nem mentett változás, előbb commitold.
3. Módosítás után újra `Status / Diff`.
4. `Commit & Push` leíró üzenettel.

Visszakeresés vagy hibás módosítás esetén:

1. Gitea weben keresd meg a jó commitot.
2. A Backup tabon a `Restore ref` mezőbe írd be a commit hash-t vagy branch nevet.
3. `Restore to Staging`.
4. Stagingből diffeld az érintett fájlokat az éles állapottal.
5. Csak a szükséges fájlokat hozd vissza, majd indíts célzott szolgáltatás restartot.

## Helyi tar archívum visszaállítása stagingbe

A webes Backup oldalon válassz archívumot, nyisd meg, majd `staging preview` módban állítsd vissza a kiválasztott komponenseket. A fájlok a `restore_staging` könyvtárba kerülnek, innen összehasonlíthatók az éles fájlokkal.

CLI alternatíva:

```bash
mkdir -p /tmp/hc-restore
tar -xzf /srv/docker/homecontrol/backups/homecontrol_YYYY-MM-DD_HH-MM-SS.tar.gz -C /tmp/hc-restore
```

## PostgreSQL dump visszaállítási irány

A mentésekben a PostgreSQL adatbázis dump formában van, nem a futó adatkönyvtár vak másolataként. Éles visszaállítás előtt először külön teszt adatbázisba érdemes betölteni:

```bash
docker exec homecontrol-postgres createdb -U homecontrol homecontrol_restore_test
docker cp /tmp/hc-restore/homecontrol_*/postgres/homecontrol_*.dump homecontrol-postgres:/tmp/homecontrol_restore_test.dump
docker exec homecontrol-postgres pg_restore -U homecontrol -d homecontrol_restore_test /tmp/homecontrol_restore_test.dump
```

Éles restore előtt állítsd le az érintett szolgáltatásokat, készíts friss mentést, majd csak a teszt restore sikeressége után cseréld az adatbázist.

## Gitea saját mentése az AI szerveren

Az AI szerveren:

```bash
cd ~/homecontrol-ai-node
./backup_gitea.sh
```

A dumpok alapértelmezett helye:

```text
/mnt/hc-backup/gitea-dumps
```

Ez ugyanazon a HDD-n van, ezért nem offsite mentés. Arra jó, hogy Gitea sérülésnél legyen gyors visszaállítási pont.

## Offsite kiegészítés

A 250 GB-os AI HDD jó másodlagos helyi cél. Igazi katasztrófa ellen még egy titkosított külső cél kellene később, például USB lemez vagy felhős restic repository. A restic jelszófájl és az SSH kulcs külön mentése kritikus.

## Teljes folyamatkép

A HC backup rendszer négy rétegből áll.

1. Helyi archívum a HC szerveren.
2. Gitea verziókövetés az AI szerveren.
3. Restic snapshot az AI szerver HDD-jén.
4. Rendszeres ellenőrzés és nem romboló restore próba.

A helyi archívum gyors visszanézésre és staging restore-ra való. A Gitea akkor hasznos, ha konfigurációs változást kell visszakeresni. A restic akkor fontos, ha a HC szerveren megsérül vagy elveszik a helyi backup könyvtár, vagy hosszabb távú snapshotból kell visszaállni.

## Napi backup részletesen

A napi mentést a `homecontrol-backup.timer` indítja. Alapértelmezett időpont: `02:15`.

Folyamat:

1. Lock fájlt fog, hogy ne fusson párhuzamosan két backup.
2. Beolvassa a `backups/backup_settings.json` beállításait.
3. Ellenőrzi a fő könyvtárakat és a `homecontrol-postgres` konténert.
4. `pg_dump` formátumban adatbázis mentést készít.
5. Átmásolja a kiválasztott komponenseket ideiglenes munkakönyvtárba.
6. Docker és host metaadatokat ír.
7. Manifestet és SHA256 checksum listát készít.
8. `homecontrol_YYYY-MM-DD_HH-MM-SS.tar.gz` archívumot hoz létre.
9. Ellenőrzi, hogy az archívum listázható.
10. Törli a retentionnél régebbi helyi archívumokat.
11. Ha a restic engedélyezett, megpróbál snapshotot küldeni az AI HDD-re.

Napi módban az AI szerver nem kötelező. Ha alszik vagy nem elérhető, a helyi archívum ettől még sikeres marad.

## Webes full AI backup indítás

A Backup tabon a `Run Full AI Backup` gomb a teljes AI HDD-s folyamatot kéri:

1. Gitea config snapshot sync.
2. Gitea dump az AI szerveren.
3. Kötelező restic backup az AI HDD-re.
4. Opcionális AI szerver leállítás.

A gomb nem közvetlenül a konténerből indít host `systemctl` parancsot. A backend a `backups/full-ai-backup.request` fájlt frissíti, a hoston futó `homecontrol-full-ai-backup-request.path` systemd helper pedig erre elindítja a `weekly_ai_backup.sh` full mentési folyamatot.

Shutdown védelem:

1. A full AI backup a `backups/ai-backup.lock` lock alatt fut.
2. Ha backup közben a webes AI oldalon shutdown kérést küldesz, a backend nem állítja le azonnal az AI szervert.
3. Ilyenkor létrejön a `backups/ai-shutdown-after-backup.request` kérés.
4. Sikeres backup végén a `weekly_ai_backup.sh` teljesíti a halasztott shutdown kérést, majd törli a request fájlt.
5. Ha a backup hibával áll le, a gép bekapcsolva marad, hogy a hibát meg lehessen nézni.

A Backup oldali `AI Shutdown Guard` csempe mutatja, hogy fut-e full AI backup vagy van-e sorban álló leállítás. Az AI oldalon a shutdown gomb backup közben `Shutdown After Backup` névre vált.

Telepítés/frissítés:

```bash
cd /srv/docker/homecontrol
sudo scripts/apply_backup_timer.sh
```

Ellenőrzés:

```bash
systemctl status homecontrol-full-ai-backup-request.path
journalctl -u homecontrol-full-ai-backup-request.service -n 120 --no-pager
```

## Heti AI HDD backup részletesen

A heti mentést a `homecontrol-ai-weekly-backup.timer` indítja. Alapértelmezett időpont: vasárnap 03:30, kis random késleltetéssel.

Folyamat:

1. Wake kérést küld az AI szerver felé.
2. SSH-n várja, hogy a szerver elérhető legyen.
3. Lefuttatja a Gitea config snapshot szinkront.
4. Az AI szerveren lefuttatja a Gitea dump scriptet, ha elérhető.
5. `RESTIC_REQUIRED=true` módban indítja a HC backup scriptet.
6. Ha a restic repo vagy AI HDD nem elérhető, a heti mentés hibára fut.
7. Siker után alapértelmezetten leállítást kér az AI szerverre.

Ez a kötelező heti mentés az a pont, ami biztosítja, hogy akkor is legyen AI HDD-s snapshot, ha a napi mentések idején az AI szerver általában ki van kapcsolva.

## Havi restic check részletesen

A havi ellenőrzést a `homecontrol-restic-check.timer` futtatja. Alapértelmezés szerint a hónap első vasárnapján, 04:30 körül indul.

Folyamat:

1. Ellenőrzi, hogy a restic engedélyezve van-e.
2. Ellenőrzi a restic binárist, SSH klienst és jelszófájlt.
3. Megnézi, hogy az AI szerver elérhető-e SSH-n.
4. Ha nem elérhető, wake kérést küld és várja az SSH-t.
5. Ellenőrzi, hogy létezik az AI HDD restic repo könyvtára.
6. Lefuttatja a `restic snapshots --tag homecontrol` parancsot.
7. Lefuttatja a `restic check` parancsot.
8. Ha ő ébresztette fel az AI szervert, a végén leállítást kérhet.

Sikeres kimenetnél ezt kell látni:

```text
repository ... opened successfully, password is correct
check snapshots, trees and blobs
no errors were found
== Restic check kész ==
```

## Mit NE csinálj restore közben

- Ne állíts vissza közvetlenül éles könyvtárba első próbára.
- Ne másold vissza vakon a PostgreSQL futó adatkönyvtárát.
- Ne írd felül a teljes `/srv/docker/homecontrol` könyvtárat addig, amíg nem tudod pontosan, melyik réteg sérült.
- Ne töröld a restic repositoryt vagy a Gitea adatkönyvtárat hibakeresés közben.
- Ne használd ugyanazt a restore parancsot DB-re és konfigurációs fájlokra.

## Hibaelhárítási térkép

`Permission denied` az AI HDD-n:

```bash
ssh a@192.168.1.2
ls -ld /mnt/hc-backup
touch /mnt/hc-backup/iras-teszt
rm /mnt/hc-backup/iras-teszt
```

Elvárt tulajdonos: `a:a`.

Restic jelszófájl hiányzik:

```bash
sudo ls -l /etc/homecontrol/restic-password
sudo scripts/install_restic_backup_prereqs.sh
```

Gitea privát repo 404:

Ez belépés nélkül normális. Lépj be a Gitea weben, vagy ellenőrizd SSH-n:

```bash
GIT_SSH_COMMAND='ssh -i /srv/docker/homecontrol/infra/ssh/ai_node_key -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
git ls-remote ssh://git@192.168.1.2:2222/homecontrol/config.git refs/heads/main
```

AI szerver nem elérhető:

```bash
ping 192.168.1.2
ssh -i /srv/docker/homecontrol/infra/ssh/ai_node_key a@192.168.1.2 true
```

Systemd timer ellenőrzés:

```bash
systemctl list-timers 'homecontrol*backup*' 'homecontrol-restic-check*'
systemctl status homecontrol-backup.timer
systemctl status homecontrol-ai-weekly-backup.timer
systemctl status homecontrol-restic-check.timer
```

Naplók:

```bash
tail -n 120 /srv/docker/homecontrol/backups/backup.log
journalctl -u homecontrol-backup.service -n 120 --no-pager
journalctl -u homecontrol-ai-weekly-backup.service -n 120 --no-pager
journalctl -u homecontrol-restic-check.service -n 120 --no-pager
```

## Restore döntési fa

Konfigurációs hiba:

1. Nézd meg Gitea-ban a commit historyt.
2. Ha egy fájl változott rosszul, Gitea-ból vagy staging archívumból hozd vissza azt az egy fájlt.
3. Indítsd újra csak az érintett szolgáltatást.

Eltűnt vagy sérült fájl:

1. Backup tabon válaszd ki a legfrissebb jó archívumot.
2. Staging preview módban bontsd ki.
3. Compare-rel ellenőrizd, mi változik.
4. Csak a szükséges fájlt másold vissza éles helyre.

Adatbázis hiba:

1. Állítsd meg az érintett appokat, ha írnak a DB-be.
2. Bontsd ki a dumpot stagingbe vagy /tmp alá.
3. Töltsd be külön teszt DB-be.
4. Ellenőrizd a táblákat/adatokat.
5. Csak ezután tervezz éles DB cserét.

HC szerver helyi backup könyvtár elveszett:

1. AI szervert indítsd el.
2. Resticből restore-olj külön `/tmp/hc-restic-restore` célba.
3. Onnan válaszd ki a szükséges archívumot vagy fájlokat.
4. Ne restore-olj közvetlenül éles könyvtárra.

Teljes HC szerver újraépítés:

1. Telepítsd az alap OS/Docker környezetet.
2. Szerezd vissza az SSH kulcsot és restic jelszófájlt.
3. Clone-old a Gitea `homecontrol/config` repositoryt.
4. Resticből hozd vissza a legfrissebb teljes snapshotot külön könyvtárba.
5. Compose/config fájlokat ellenőrizd.
6. PostgreSQL-t dumpból állítsd vissza.
7. Indítsd a konténereket fokozatosan.
8. Futtasd a smoke testeket és nézd a dashboardokat.
