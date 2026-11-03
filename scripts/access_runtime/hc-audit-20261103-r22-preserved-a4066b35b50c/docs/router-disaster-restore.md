# HC teljes helyreállítása a routeres mentésből

Az r16 javított bootstrapjének útvonala: **külső Git → age-bundle → routeres
FTP/restic → ellenőrzött archívum → PostgreSQL → systemd és Docker**.
Az AI-szerver nem része az útvonalnak, és letiltva marad.

Ez a teljes parancs a célhost `/srv/docker/homecontrol` fájljait és HC-adatbázisát
állítja vissza, a DB-t lecseréli. A staging-only változatból az apply/DB/start
kapcsolót el kell hagyni. A cél nem áthelyezhető tetszőleges projektkönyvtárba.

## Bemenetek és előfeltételek

- A külső Git olvasási joga és a külön megőrzött **age identity privát kulcs**.
  A Gitben a bundle titkosított; az identity nem kerül bele a mentési bundle-be.
- A kiválasztott mentéssel egyező Git-commit és teljes restic snapshot-ID.
  A kiadási nyugták rögzítik a snapshotot és az archívum hash-ét; a Git commitot
  külön rögzíteni kell. A különböző kiadási kódot és snapshotot nem keverjük.
- Hozzáférés a router LAN FTP-céljához. A nyilvános router-settings JSON a Git
  `docs/router-backup-settings.json` fájlja; a jelszavak a visszafejtett bundle-ből
  kerülnek privát stagingbe, nem a parancssorba.
- Előkészített OS, működő Docker/Compose, age, git, rsync, restic, nftables és
  python3. Az izolált próba Ubuntu22.04, Docker29.1.5 és Compose5.0.2 környezetet
  használ. A bootstrap saját `--install-packages` útvonala ebben a próbában nem fut.
- Ellenőrzött rclone1.75.2. Új hoston a Gitből elérhető telepítő terve és apply-ja:

```bash
python3 scripts/install_router_backup_prereqs.py
sudo python3 scripts/install_router_backup_prereqs.py --apply
```

A telepítő a rögzített kiadás checksumját ellenőrzi, és kizárólag a hiányzó
`/usr/local/bin/rclone` fájlt telepíti. Meglevő binárist nem ír felül.
Offline helyreállításkor az előre megőrzött, hash-ellenőrzött rclone bináris
használható. A Docker-image-eket a kiválasztott ellenőrzött HC-archívum adja.

## Konkrét bootstrap

A helyi Git mirror és az abból kivett `project` checkout egy előkészített,
privát recovery-könyvtárban legyen. Az alábbi helyőrzőket a kiválasztott
mentés azonosítóira kell cserélni:

```bash
sudo bash /root/hc-recovery/project/scripts/bootstrap_restore_v0_1.sh \
  --age-key /root/hc-recovery/age-identity.txt \
  --repo-url /root/hc-recovery/git.git \
  --repo-ref GIT_COMMIT \
  --router-settings /root/hc-recovery/project/docs/router-backup-settings.json \
  --snapshot RESTIC_SNAPSHOT_ID \
  --work-dir /root/hc-recovery/work \
  --apply --apply-restic-files --restore-db --confirm-db-replace --start
```

Friss, üres work-dirből induljunk. A privát work-root 0700-as; a titkok 0600-asak.
A Git-checkout publikus forrásai a nem root alkalmazás számára is olvashatók.
A bootstrap előbb a bundle-t, a repositoryt, az archívumot, az egyértelmű dumpot
és a recovery-image-eket ellenőrzi, majd állítja le/cseréli a célállapotot.
Az elérhetetlen FTP nem minősül sikeres helyreállításnak.

## Átvétel

```bash
curl --fail http://127.0.0.1:5000/health
curl --fail http://127.0.0.1:5000/health/ready
systemctl list-timers 'homecontrol-*'
```

A napi 02:15 és heti Sun03:30 beállítást a kiválasztott archívum őrzi; a havi
adatellenőrzési timer is visszatér. A backend UID10001, read-only és Docker-socket
nélküli; a szükséges hostműveleteket szűk root IPC végzi. A broker korábbi kiadási
mountjának szükséges tulajdonosát is a tényleges Compose-modell alapján állítjuk be.
A helyreállított, félbeszakadt hostfeladatok nem játszódnak vissza automatikusan.

Az izolált próba nem igazol fizikai Zigbee/ESP/AI/Growatt működést. A friss host
fizikai hálózati azonossága és az eredetileg megerősített ESP-kivétel az átadás
külön része. A régi `homecontrol_restore_magic.sh` automatikus csomagtelepítése
és letöltése nem része ennek a tesztelt routeres útvonalnak; a fenti közvetlen
bootstrap hívást használjuk.

[Aktuális próba és bizonyítékhatár](ai-ssd-backup-closure-20261101.md).
