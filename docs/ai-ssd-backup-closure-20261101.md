# Az AI SSD-hiba miatt félretett mentési ellenőrzések — lezárva

2026-11-01. Felhasználói döntés: **az AI maradjon letiltva; a mentési pontokat
a routeres rendszerrel zárjuk le**. Az r16 élesítése és a tényleges éles mentésből
végzett friss gépes utópróba sikeres. A jelenlegi mentési lánc ellenőrzését
már nem blokkolja az AI-szerver SSD-je.

| Régi korlát | Igazolt eredmény | Állapot |
| --- | --- | --- |
| Távoli restic az AI nélkül | Routeres titkosított repository teljes adatellenőrzése | Lezárva |
| Heti mentés, Git és megőrzés | Új éles futás minden kötelező célja sikeres; teljes ellenőrzés a megőrzés előtt és után | Lezárva |
| Archívum és PostgreSQL | 5561 fájlchecksum, külön PG-restore és teljes vendéggépes DB-restore | Lezárva |
| HC-45 friss host/systemd/host IPC | Üres HC/image-tárból teljes restore, 14 alapunit, adapterek, 5 timer, root IPC, offline HA és reboot sikeres | Lezárva |
| Aktuális külső Git tartalma/története | 34 commit, 1533 történeti blob, 5345 manifestfájl; hiány és hash-eltérés nélkül | Lezárva a jelenlegi célra |
| HC-31 fizikai shutdown/OFF/wake | Az AI letiltva; fizikai próba nem futott | Csak későbbi újraaktiválás előtt; nincs sikeresnek minősítve |
| Régi AI-Gitea története | A jelenlegi lánc nem használja | A régi lemez története nincs ellenőrzöttnek nyilvánítva |

## Tényleges éles r16 bizonyíték

Kiadás: `hc-router-backup-20261101-r16`.
Mentés: `744b9d23cb54408698d80e50afd30585`.
Snapshot: `354c6ca19a7cbbd2a4a30a8ead54a6011f2a93763384022533ec1d917b97db1f`.
Git-commit: `5740329aeaa0a90c914185b816c702c069603d2d`.
Archívum SHA-256: `d644e9c1ef0f64d243665fb5475191e817998d0b4743f67f0894151e1c2c7519`.

Az éles aktiválás a routeres próba után teljes ellenőrzést, helyi előmentést,
backend/frontend átállítást, teljes helyi/router/Git mentést, archívum- és izolált
PostgreSQL-próbát végzett. A 711 csomag- és runtime-forráshash egyezik;
readiness jó, platform változatlan, systemd failed nincs. Az 5 hosttimer aktív
és engedélyezett. Napi mentés 02:15, heti teljes router/Git Sun03:30.

[Éles nyugta](../backups/releases/hc-router-backup-20261101-r16/deployment-status.json),
[önálló éles utóellenőrzés](audit-evidence/router-r16-live-20261101/production-check.json),
[csak olvasó laborbemenet-előkészítés](audit-evidence/router-r16-live-20261101/input-preparation.json).

A Git független vizsgálata a teljes mirroron futott: a jegyzék mind az 5345
fájlja megvan és helyes hash-ű. A korábbi 111 runtime térképfájl eltérése megszűnt;
a térképcache a titkosított mentésben marad. A vizsgált privátkulcsfejlécekre és
kitöltött érzékeny JSON-mezőkre nincs találat a 1533 történeti blobban. Ez a
publikus exporterrel azonos, meghatározott mintavizsgálat, nem minden lehetséges
titok általános kizárásának állítása.
[Git-vizsgálat](audit-evidence/router-r16-live-20261101/git-verification.json).

## Teljes helyreállítás és ellenőrzési határ

A friss KVM-gép előkészített Ubuntu22.04-et, valódi systemd PID1-et, Docker29.1.5-öt
és Compose5.0.2-t használt. A HC könyvtár és az image-tár induláskor üres volt.
A tényleges új Git-commit és snapshot változtatás nélkül állt vissza; nincs
külön javítási laborcommit (`candidate_fixes_applied:false`). A dump SHA-256:
`b3b863888f9458d2a596647d07b6ef866bb1ffe705194d6f76b31f4c7a18effc`.
A visszaállított DB: `7148703` mérés, `66` entitás, `61` HC-tábla.

Sikeres a DB/MQTT-health, a checksumhoz kötött offline Home Assistant-indítás,
a 14 alapunit és kiadási adapterek telepítése, az 5 timer jövőbeli triggerrel,
a non-root/read-only backend Docker-socket nélkül és a valódi UID10001 → root
IPC → vendég-Docker útvonal. Tiltott forrás-/archívumírás ellenőrzött;
félbeszakadt hostfeladatok nem játszódtak újra. Elérhetetlen FTP esetén a
restore hibával megállt, a kanonikus fájlok/unitok és a DB-konténer változatlanok.
Teljes vendégreboot után a probe és a unitbájtok egyezése ismét sikeres.

[Friss restore és reboot](audit-evidence/router-r16-live-20261101/vm-acceptance.json),
[friss állapot](audit-evidence/router-r16-live-20261101/fresh-probe.json),
[reboot utáni állapot](audit-evidence/router-r16-live-20261101/post-reboot-probe.json),
[FTP-kiesés](audit-evidence/router-r16-live-20261101/unavailable-repository.json).

A Docker network=none és QEMU restrict=on izolálta a vendéget; a router másolatát
vendégen belüli FTP szolgálta ki, csak olvasható adatokkal és ideiglenes lockokkal.
A termelési repository nem kapott író parancsot az ellenőrzéstől. Fizikai
Zigbee/ESP/AI/Growatt-integrációt és OS-csomagtelepítést ez a próba nem igazol.
A privát bemenetmásolatok és a HC-adatot tartalmazó guest lemez törölve;
az eredeti kulcsok és mentések érintetlenek.
[Takarítás](audit-evidence/router-r16-live-20261101/lab-cleanup.json).

## Előzmények és külön maradó feladatok

Az élesítés előtti, valódi r15 adatokkal és külön javítási laborcommittal futó
próba a tiszta és azonos work-dirből ismételt restore-t, FTP-kiesést és rebootot
is ellenőrizte. Ez az r16 utópróbájától külön bizonyíték:
[korábbi VM-átvétel](audit-evidence/ai-ssd-closure-20261101/vm-acceptance.json).
A feltárt öt hiba javítása az r16-ban éles: fagyasztott recovery helper választása,
ellenőrzött HA-tag helyreállítása, Git-checkout umask, pontos export/Git-index,
a tényleges régebbi MQTT-mount cold restore jogosultságai. A sikertelen korai
próbák történeti diagnózisként megmaradtak, nem kapnak sikeres minősítést.

Az eredeti audit változatlan. HC-15/16/20/24/26, a globális HC-23/43 és az ESP
legacy MQTT-kivétel külön feladat. A besorolás továbbra is 40 ellenőrzött,
5 nyitott, 3 folyamatban; ez a munka a mentési bizonyítékok korlátját zárja le.
[Éles átadás és rollback](../backups/deployments/hc-router-backup-20261101-r16/DEPLOYMENT.md),
[helyreállítási útmutató](router-disaster-restore.md), [javítási napló](../AUDIT_REPAIR.md).
