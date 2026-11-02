# r20 – az átállítás előtti mentés folytatása, 2026-11-02

**Aktív kiadás továbbra is r18. Az r20 alkalmazásváltása még nem kezdődött el.**
A nyilvános r20 állapot `fresh_backup`; a konténerazonosítók és image-ek egyeznek
az r20 előkészítésekor rögzített r18 baseline-nal. Az öt timer és a hostops aktív.
Nem indítjuk újra az eredeti aktiválást, és nem írjuk át a lezárt r20 csomagot.

## Hiba és bizonyíték

Az átállítás előtt hívott F6 runner külső határideje 900 másodperc volt. A
routeres `local` mód helyi archívumot, routeres snapshotot és teljes adatellenőrzést
is végző megőrzési lépést futtat. A runner belső határideje 10800 másodperc,
a service-eké négy óra; a 15 perces külső határidő ezzel nem volt összhangban.

A helyi archívum 21:21-kor elkészült, a routeres snapshot 21:23-kor sikeres lett;
a megőrzési lépés eredménye 21:34-kor került az állapotba. Az aktiváló azonban
21:33-kor már `TimeoutExpired` hibával megállt. A `subprocess.run` a hívott runner
folyamatát megszüntette, miközben a külön sessionben futó worker tovább futott.
Emiatt a futás végső státusza `running` maradt. Csak olvasó host-ellenőrzés szerint
a runner PID már nem létezik, és a két közös mentési lock nincs fogva. Ezt a root
folytató a tényleges helyreállítás előtt ismét ellenőrzi.

Érintett run: `1931f52994584f34b178e8e7a192bb2d`.
Archívum: `homecontrol_2026-11-02_21-18-26_1931f52994584f34b178e8e7a192bb2d.tar.gz`.
Nyugta: 2811581768 bájt, 7239 ellenőrzött fájl;
SHA-256: `c0a445b33b02e993798a7037a7030d3136b2ee5a90ca6190861fb8f1a2eff00d`.
A teljes mentési futást nem minősítjük sikeresnek a résznyugták alapján.

## Ellenőrzött folytatás

A kiegészítő csomag: `hc-audit-20261102-r20-continuation-1`. Ugyanazt a lezárt
r20-at folytatja; a runtime, alkalmazás-image-ek és a 789 forráshash változatlan.
A kiegészítő az r20 manifestjének pontos SHA-256-ához kötött, saját forrásai és
tesztbizonyítékai is hash-nyugtával védettek.

A folytatás kizárólag az adott `fresh_backup` + 900 s `TimeoutExpired` esetben
indulhat. Nem lehet már átállítási snapshot, új runtime/private cél vagy végleges
auditátadás. A normál baseline-, HA-, PG-, ütemezési és routeres előellenőrzések
megmaradnak. A meglévő privát staginget a jelenlegi r18 bemenetekből előállított
elvárt tartalommal és a titkosított age-csomag új visszafejtésével ellenőrzi; az
offline image-cache hashének is egyeznie kell.

A beragadt futást mindkét valódi közös lock birtokában, halott PID és változatlan
run/állapot/archívumnyugta mellett **megszakadt, sikertelen** futásként rögzíti.
Az eredeti privát nyugtát megőrzi, az archívumot nem törli. Élő runner, foglalt
lock vagy közben elindult új mentés esetén nem módosítja a futást.

Az eredeti aktiválásban publikált helyi mentés teljes belső ellenőrzőösszeg-készletét
és külső SHA-256-át újraellenőrzi. Csak a konkrét, legfeljebb négyórás, teljes
lefedettségű archívumot fogadja el az átállítás előtti mentési kapuként. Nem készít
feleslegesen újabb több GB-os példányt. Ha túl régi vagy módosult, nincs átállítás.

A normál r20 tranzakció ezután készít snapshotot, és váltja át a három komponenst.
A friss, átállítás utáni HC/Git/router mentés **nem marad el**. Ezt egy átmeneti
systemd service futtatja: a runner belső határideje 10800 s, a service-é 11400 s,
a leállítási türelmi idő 90 s. `KillMode=mixed` először a runnernek enged szabályos
worker-leállítást, szükség esetén pedig a teljes cgroup megszűnik. A várakozó kliens
határideje ezeknél hosszabb. Hibánál a felügyeletet leállítja a rollback előtt;
egy már létező felügyeleti unitot nem használ fel és nem állít le vakon.

SHA-256/PG-restore, runtime-, health-, policy- és öt timeres záróellenőrzés után
továbbra is az eredeti r20 kód írja a végleges auditátadást. A normál automatikus
rollback megmarad. A folytató egyszer próbálható; hiba után az állapotot meg kell
vizsgálni, a parancs nem ismételhető vakon.

## Ellenőrzések és függőségek

**23 friss izolált teszt sikeres**, köztük a foglalt valódi fájl-lock, élő PID,
megváltozott job/nyugta/archívum, hibás vagy régi mentés, eltérő privát staging,
eltérő titkosított csomag és a felügyeleti hibakezelés próbái.

Valódi felhasználói systemd-cgroup próbában a szintetikus szülő figyelmen kívül
hagyta a SIGTERM-et, a gyermeke külön sessionbe lépett. A 2 s határidő és 1 s
leállítási türelem után **egyik sem futott tovább**. Ez a helyi systemd-mechanizmust
ellenőrzi; éles root mentést ezzel a próbával nem indítottunk.

Az eredeti r20 teljes forrás-/bizonyíték-/image-/offlinearchívum-ellenőrzése újra
lefut; az alkalmazáskód változatlan, a korábbi regressziót nem nevezzük új futásnak.
A root-only privát staging és az archívum tényleges újraellenőrzése a sudo parancs
része, ezt nem állítjuk előzetesen elvégzettnek. A szükséges tárhelyet a folytató
egy új runtime image-cache, egy új heti archívum és 2 GiB tartalék alapján vizsgálja.

Függőségek: helyi sudo, változatlan r18 baseline, legfeljebb négyórás eredeti
mentés, szabad közös lockok, elegendő tárhely és elérhető router/Git. Az általános
jövőbeli kiadásépítőkben is ezt az összehangolt felügyeletet kell használni a
mentés körül; az eredeti lezárt r20 aktiválót nem javítjuk át helyben.

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r20-continuation-1/source/resume_r20.py
```

Siker csak a végső `deployed_and_audit_handover_complete` nyugtával igazolt.
**Az auditátadás még nyitott; 46 Ellenőrzött, HC-41 és HC-43 Folyamatban.**
Az AI tiltva marad. Más auditpontot nem változtattunk meg.

Bizonyítékok: `backups/releases/hc-audit-20261102-r20-continuation-1/evidence/`.
A privát nyugták, visszafejtett adatok és kulcsok nem megoszthatók.
