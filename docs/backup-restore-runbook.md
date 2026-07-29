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
