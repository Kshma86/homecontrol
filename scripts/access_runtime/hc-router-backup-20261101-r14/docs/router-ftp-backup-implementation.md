# Routeres FTP-mentés – elkészült forrás és bevezetési lépések

Állapot: fejlesztői forrás, 2026-11-01. Az éles r13 kiadás, annak fagyasztott
runtime-ja, a kanonikus `scripts/backup_runner.py`, az élő mentési beállítások
és a telepített timerek nem lettek átállítva. Routerjelszó nem került a kódba.

## Működés

A tároló kiválasztása `backup_target=router_ftp`. Alapcél:
`rclone:routerbackup:/G/hc-backup/restic/homecontrol`. A HC-n futó restic
titkosít; a HC-n futó rclone az FTP-kapcsolatot biztosítja. A routeren nem kell
programot telepíteni. Ellenőrzött kombináció: restic 0.12.1 és rclone 1.75.2.
Az Ubuntu 22.04 rclone 1.53 csomagját a kód elutasítja: a helyi FTP-próbánál
nem kezelte megfelelően a nem létező repositorykönyvtárat. A támogatott
minimum ezért a ténylegesen kipróbált rclone 1.75.2.

- A közös host runner meglévő zárolása fogja össze a helyi és távoli munkát.
- A kész helyi archívum receiptje és teljes checksumja feltöltés előtt ellenőrzött.
- A heti routeres futás kihagyja az AI SSH/WOL/leállítás és Gitea-dump lépéseket.
- A külső Git önálló cél. Ugyanabból a külső repóból klónoz, ahová feltölt,
  megőrzi az előzményt, és nem használ force push-t. Egy Git-hiba után is
  megkísérli a helyi és kötelező routeres mentést.
- A heti routeres futásban a helyreállítási titkok csomagjának frissítése is
  kötelező cél. Hibája után a többi mentés még lefut, de a teljes futás hibás,
  így az új FTP-hozzáférés hiányzó mentése nem marad észrevétlen.
- A restic-hiba nem törli a kész helyi mentést vagy az előző távoli siker idejét.
- Normál mentés nem inicializál repositoryt. Az `init` explicit külön parancs.
- A lemez csatolási pontját előbb ellenőrzi; hiányzó `/G` esetén nem készít
  helyette új könyvtárat.
- A retention csak sikeres snapshot után fut, külön eredménnyel. `host,tags`
  szerinti csoportosítással az egyedi helyi archívumnevek nem hoznak létre
  minden alkalommal külön megőrzési csoportot.
- Az integritásvizsgálat `restic check --read-data`: tényleges tartalomolvasás.
- A visszaállítás teljes snapshot-azonosítóhoz kötött, üres stagingbe történik.
- Az új rclone-config és restic-jelszó bekerül a titkosított secrets manifestbe;
  az rclone-konfiguráció nyersen nem exportálható a publikus Git-snapshotba.

Az AI-offline policy alapértelmezése továbbra is `local-only`. A bevezetendő
kiadás policyjába külön `"backup_profile": "router-ftp"` engedély kell.
Ez a routeres mentést és a külső Git-feltöltést engedélyezi, az AI-műveleteket,
az AI-s Gitea olvasó/visszaállító műveleteit és az éles fájlrestore-t nem.
A jelenlegi policy fájl nem lett módosítva.

## Belépési pontok

| Fájl | Feladat |
| --- | --- |
| `infra/backend/router_backup.py` | Validált FTP-transport, titkosított snapshot, retention, check, staging restore |
| `scripts/backup_runner_impl.py` | Fejlesztői közös runner; a fagyasztott éles wrapper helyett az új csomag adaptere ezt használja |
| `scripts/router_restic.py` | Zárolt init, elkülönített smoke, worker és staging restore |
| `scripts/configure_router_backup.py` | Rejtett jelszóbekérés; új 0600-as credentialfájlok és külön jelölt beállítások |
| `scripts/install_router_backup_prereqs.py` | Terv alapértelmezésben; explicit telepítéskor hivatalos rclone és SHA-256 ellenőrzés |
| `scripts/backup_offsite_worker.sh` | AI Giteától független Git-export és feltöltés |
| `scripts/restore_smoke.py` | Valódi routeres snapshotból archívum-visszaolvasás és belső ellenőrzés |
| `scripts/bootstrap_restore_v0_1.sh` | `--router-settings` kapcsolóval a secrets stagingben levő FTP-hozzáférést használja |

A meglévő archive/weekly/check/config-sync workerek routeres ágakat kaptak.
A Backup felület forrásában választható a routeres cél, beállíthatók a nyilvános
elérési adatok, és külön állapotban marad a külső Git. FTP-jelszó nem adható meg
a webes felületen; az a hoston, privát fájlban marad.

## Első valódi restic-próba a routerrel

Ezek operátori lépések, még nem futottak le a BE550-en. A meglévő FTP-próbák
16 és 256 MiB-bal sikeresek voltak; az [eredeti terv](router-ftp-backup-plan.md)
tartalmazza a mért sebességeket.

1. Függőség telepítése. A helper először tervet mutat; a második parancs
   kizárólag az rclone binárist telepíti `/usr/local/bin/rclone` helyre.
   Létező binárist nem ír felül. A restic a HC-n már telepítve van.

```bash
cd /srv/docker/homecontrol
python3 scripts/install_router_backup_prereqs.py
sudo python3 scripts/install_router_backup_prereqs.py --apply
```

2. Külön tesztcél konfigurálása, jelszó a helyi terminálon:

```bash
sudo python3 scripts/configure_router_backup.py \
  --host 192.168.1.1 --user kshma --mount /G \
  --repository-path /G/hc-backup/probes/router-first \
  --settings-out /srv/docker/homecontrol/backups/router-probe-settings.json
```

Új fájlok: `/etc/homecontrol/router-rclone.conf`,
`/etc/homecontrol/router-restic-password`, valamint a külön tesztbeállítás.
Mindhárom 0600-as. Létező configot/beállítást nem ír felül, létező privát
restic-jelszót újra felhasználhat. A Git a tesztbeállításban kikapcsolt;
a működő éles Git-beállításokat ez nem írja át. Az rclone jelszó-obscure
visszafordítható, ezért a config fájljogosultsága fontos.

3. A külön tesztrepository létrehozása és tartalomellenőrzéses restore:

```bash
sudo python3 scripts/router_restic.py init \
  --settings /srv/docker/homecontrol/backups/router-probe-settings.json
sudo python3 scripts/router_restic.py smoke \
  --settings /srv/docker/homecontrol/backups/router-probe-settings.json
```

A smoke egy 1 MiB-os véletlen fájlt titkosítva elment, a teljes repositoryt
visszaolvassa, a rögzített snapshotból stagingbe visszaállít, és összeveti a
SHA-256 értéket. Az `ok: true` és teljes `snapshot_id` a siker jele.
A titkosított próbasnapshot a külön tesztcélon marad, nincs automatikus távoli
törlés. Hálózati/jelszóhiba esetén ne indíts újabb initet ugyanarra a repositoryra.

## Éles átállítás a sikeres routeres smoke után

1. A jelenlegi mentési beállításokból készülő jelöltben meg kell tartani a
   kiválasztott tartalmakat, időzítést és a tényleges külső Git URL/ág/token/key
   beállításokat. Csak a router célmezőit és privát fájlhivatkozásait kell átvenni
   a tesztbeállításból. `git_origin_enabled=false`, `include_gitea=false`,
   `ai_weekly_shutdown_after=false`; a külső Git engedélyezése megmarad.
   A produkciós repository külön út: `/G/hc-backup/restic/homecontrol`.
2. A produkciós repository explicit inicializálása az új jelöltből. A régi HDD
   tartalmát és a próbarepositoryt nem kell módosítani.
3. Új, fagyasztott backend/frontend/host csomag készítése az itt módosított
   forrásokból; a routeres backup-policy képességgel. A kanonikus wrapper és
   a host adapter ugyanahhoz az új csomaghoz tartozzon. A régi runtime-ot nem
   szabad helyben átírni vagy a régi mellé második ütemezőt telepíteni.
4. Az új kiadásban egy valódi HC-mentés és annak staging restore-ja,
   majd külön PostgreSQL-restore próba. A helyi és távoli sikert külön igazoljuk.
5. Az új FTP-hozzáférést tartalmazó secrets bundle frissítése és visszafejtési
   próbája. A restic-jelszó és az age privát kulcs külön külső másolata kell.
6. Ezután kerülhet át a meglévő ütemezés az új végrehajtóra. A régi, ép backup
   HDD a visszaállítási próbák lezárásáig változatlan tartalék.

Új gépes helyreállításnál a nyilvános routerbeállítások JSON-ja külön elérhető
legyen a Gitből vagy a helyreállítási csomagból; az FTP-jelszó a titkosított
bundle-ben van. A bootstrap `--router-settings FILE` kapcsolója a visszafejtett
bundle gyökeréhez igazítja a privát fájlutakat. A rclone-t az új hoston is a
fenti, ellenőrzött módon kell telepíteni; a disztribúció régi csomagja nem elég.

## Ellenőrzés

A `scripts/tests/test_router_backup.py` tesztjei a közös runnerrel, valódi
helyi Git repókkal és archívumokkal ellenőrzik a hibakezelést; a hálózati
integráció opt-in, csak localhostot használ. A hálózati teszthez `pyftpdlib`
szükséges, a policy HTTP-teszthez Flask.

2026-11-01-i eredmény: **27 routeres teszt, 19 meglévő policy-teszt,
50 meglévő backup/restore/unit teszt és 7 frontend-állapotteszt sikeres**;
a teljes frontend production build is sikeres. Külön valódi FTP-próba igazolta
a visszafejtett secrets stagingből indított, rögzített snapshothoz kötött
visszaállítást. A teszthez letöltött programok és függőségek `/tmp` alatt
maradtak; rendszertelepítés nem történt.
[Ellenőrzési jegyzőkönyv és forrás SHA-256 értékek](audit-evidence/router-ftp-20261101/verification.json).

```bash
python3 -m unittest discover -s scripts/tests -p test_router_backup.py -v
HC_ROUTER_FTP_TEST=1 python3 -m unittest discover -s scripts/tests -p test_router_backup.py -v
```

Kapcsolódó dokumentáció: [restic rclone backend](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#other-services-via-rclone),
[rclone FTP](https://rclone.org/ftp/), [hivatalos rclone kiadások](https://github.com/rclone/rclone/releases).
