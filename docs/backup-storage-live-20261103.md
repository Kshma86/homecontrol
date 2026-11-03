# Mentési tárhely – sikeres éles átállás, 2026-11-03

REPAIR-076. Aktív alkalmazáskiadás: `hc-security-20261102-r18`.
Az r21 élesítése és a javítási kör átadása még függő.

A felhasználó a helyi terminálban lefuttatta a REPAIR-075 tárhelycsomag `apply`
parancsát. A megosztott eredmény minden szakaszon végigment, végül `ok: true`,
`phase: complete`, `free_bytes: 168643108864`, `reserve_bytes: 32212254720`
értékeket adott. A root végrehajtás részletes nyugtái továbbra is a privát
`/var/lib/homecontrol-backup-storage/state/` könyvtárban vannak; ezeket az ügynök
nem olvasta. A következő ellenőrzések ettől független, tényleges utóellenőrzések.

## Ellenőrzött éles állapot

* A `backups` mount forrása a `/var` fájlrendszerének
  `/lib/homecontrol-backup-storage/data` könyvtára. A logikai elérés változatlan.
* A natív hoston mind az öt mount-unit aktív és engedélyezett. A `releases`,
  `ai-control` és a két közös lock a korábbi `/srv`-beli példánnyal azonos inode.
* Mind a 16 konténer ID-ja és image-e egyezik a tárhelycsomag baseline-jával.
  A 15 elvárt futó komponens működik, a 10 healthcheck healthy; az Adminer
  korábbi leállított állapota megmaradt. A backend `/health` válaszában `ok: true`.
* Mind az öt timer, a hostops és mindkét kérésfigyelő path-unit aktív.
* A deployment API szerint `ai_enabled: false`, `router_backup_enabled: true`.
* Az r18 mind a 736 runtime-forráshashe egyezik. Az r21 mind a 799 lezárt
  forráshashe és a folytatóban rögzített release-manifest hash egyezik.
* A tárhelycsomag 32, az első folytató 9 és a második folytató 10 elfogadási
  hashbejegyzése egyezik. A lezárt csomagok nem változtak.

A kapacitás utóellenőrzésekor a `/srv` szabad helye 51 586 408 448 bájt,
a mentési tárhelyé 168 648 151 040 bájt volt. A 36 befejezett archívumnyugta
közül a legnagyobb archívum 2 814 297 607 bájt. A változatlan r21 kapu
7 776 078 862 bájtot követel a `/srv`-n; a tárhelyellenőrző két ilyen archívumot
és 30 GiB tartalékot, összesen 37 840 849 934 bájtot követel a mentési
fájlrendszeren. Mindkettő teljesül; a root indítás frissen újraellenőrzi őket.

Az ellenőrzések `docker inspect`, a két olvasó HTTP-végpont, `systemctl is-active`
és `is-enabled`, `findmnt`, `disk_usage`, inode-összehasonlítás és SHA-256
számítás útján történtek. Éles szolgáltatást nem indítottunk újra.
Új tesztfuttatás vagy tényleges host-reboot nem történt ebben az utóellenőrzésben.

## Az r21 folytatása

A második folytató `activation-attempt.json` állománya szerint az előző
ügynöki indítás a sudo-hitelesítésnél állt meg: `root_execution_started: false`.
Nincs r21 `deployment-status.json`, telepített r21 runtime vagy végső átadási
dokumentum. A root-only korábbi hibát és egyszeri indítási nyugtát maga a
lezárt folytató ellenőrzi; a privát állapotot ebből az utóellenőrzésből nem
minősítjük ellenőrzöttnek.

A natív `sudo -n` most is helyi jelszót kér, ezért a következő parancsot a
felhasználó helyi termináljában kell indítani. Az első parancs csak ellenőriz;
kizárólag siker esetén indul az élesítést végző második parancs.

```bash
sudo python3 /usr/local/lib/homecontrol-backup-storage/migrate.py check &&
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r21-continuation-2/source/resume_r21_capacity.py
```

A folytató nem ismétli a korábbi sikeres unlockot, és új repository-lock esetén
megáll. Az eredeti teljes repository-check, r18 HC/Git/router előmentés,
izolált PG-restore, háromkomponenses átállítás, új mentés/restore és végső
runtime-/health-/timer-ellenőrzés kötelező marad. A root futás hosszabb ideig
tarthat; sikeres lezárás: `deployed_and_audit_handover_complete`.
Hiba után a folytatót nem szabad vakon újraindítani.

46 Ellenőrzött; HC-41 és HC-43 Folyamatban. Az AI tiltva marad.
Az éles tárhelyváltás nem jelenti az alkalmazásjavítások élesítését vagy az audit
átadásának lezárását. A teljes host-reboot és az új elhelyezés friss bare-metal
recovery-próbája továbbra sem bizonyított.
