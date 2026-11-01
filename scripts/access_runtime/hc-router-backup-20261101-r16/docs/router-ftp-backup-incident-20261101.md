# Routeres mentés: integritási incidens, 2026-11-01

Az r14 aktiválás első teljes mentése és az abból végzett archívum-/PostgreSQL-
visszaállítás sikeres volt. Az időzítők indulásakor bepótolt második heti mentés
feltöltése után a retention hibázott. A későbbi teljes check sok `pack ...:
does not exist` hibát jelzett. Ez nem bizonyít önmagában HDD-hibát, és a hiba
okát még nem azonosítottuk; a routeres tároló jelenleg nem tekinthető megbízhatónak.

## Elvégzett védelem

A felhasználó által indított karbantartási ellenőrző 16:06:45–16:09:55 CET között
már az első checken megállt; retentiont nem végzett. A hibás tárolót azóta nem
inicializáltuk újra, nem futott indexjavítás, snapshot-törlés vagy újabb prune.

A támogatott `PUT /api/backup/settings` művelettel 16:13:49 CET-kor:

- `restic_enabled=false`, `restic_required=false`;
- `ai_weekly_backup_enabled=false`;
- napi helyi mentés engedélyezve, időpont 02:15;
- `git_enabled=true`, `git_offsite_enabled=true`, a Git-cél változatlan.

A systemd állapota külön ellenőrzött: a napi timer aktív, a heti és havi
routeres timer inaktív. A Git automatikus heti futása átmenetileg szünetel,
a Git-hozzáférés és beállításai megmaradtak. A HC alkalmazások és az AI-offline
policy megmaradtak. A lezárt r14 forrásfájlokat nem módosítottuk.

[Védelmi beállítások gépi jegyzőkönyve](../backups/releases/hc-router-backup-20261101-r14/evidence/router-incident-containment.json).
[Hibás check eredménye](../backups/releases/hc-router-backup-20261101-r14/evidence/router-maintenance-20261101T150645Z-e56db030.json).

## Elvégzett csak olvasó diagnosztika

```bash
sudo python3 /srv/docker/homecontrol/scripts/router_release/diagnose.py
```

A helyi sudo a privát beállításokhoz és a tárolt FTP-jelszóhoz szükséges.
A script ellenőrzi az aktív r14 kiadást és a használt fagyasztott modul hashét,
majd a közös mentési zárat használja. A routeren végzett műveletek:

1. Snapshotok és indexek olvasása `restic --no-lock` kapcsolóval; privát helyi
   metaadatpéldány készítése. Az indexek által leváltott régi indexeket kiszűri.
2. A packok rekurzív listázása rclone-nal, majd MLSD nélkül is, egyetlen
   listázó workerrel.
3. Külön natív FTP `NLST` listázás, az rclone listafeldolgozása nélkül.
4. Legfeljebb három hiányzónak jelzett pack közvetlen FTP-visszaolvasása.
   A teljes titkosított fájl SHA-256 értékét a pack azonosítójával veti össze.

Jelszó nem kerül parancssorba vagy nyilvános kimenetbe. A privát metaadatok
0700-as könyvtárba, a jelszómentes eredmény új JSON-ként az r14 `evidence`
könyvtárába kerül. A script nem javítja és nem minősíti egészségesnek a tárolót;
a sikeres kilépés csak a diagnosztika befejezését jelenti.

Hét diagnosztikai teszt és egy valódi localhost FTP/restic integráció sikeres:
a három inventory egyezett, a közvetlen pack-visszaolvasások SHA-256 értéke
helyes volt, és a diagnosztika utáni teljes repository-check is sikerült.

**Éles eredmény, 16:18:15–16:18:25 CET:** az aktív indexek 1408 packja mind
szerepelt a két rclone-listában és a natív FTP-listában. Három korábban
hiányzónak jelzett pack közvetlen visszaolvasása és teljes SHA-256 értéke
helyes. Tehát a vizsgált fájlok ténylegesen léteznek; az eredmény a restic/rclone
listázási útvonalának vagy párhuzamosságának hibájára utal, de nem igazolja
még az összes adat épségét.
[Éles diagnosztikai eredmény](../backups/releases/hc-router-backup-20261101-r14/evidence/router-diagnosis-20261101T151815Z-6356d084.json).

## Sikeres teljes próba korlátozott párhuzamossággal

```bash
sudo python3 /srv/docker/homecontrol/scripts/router_release/verify_transport.py
```

Ez összehasonlítja az eredeti restic-listázást a `--checkers 1 --transfers 1`
rclone-opciókkal és `rclone.connections=2` restic-opcióval futó változattal.
Az eredeti módban metaadat-check, a korlátozott változatban teljes
`check --read-data` fut. Egyező inventory és sikeres teljes check után az
aktuális snapshotból archívumot állít vissza, összeveti az eredeti helyi
publikációs receipttel, ellenőrzi a belső fájlchecksumokat, és a dumpot friss,
izolált PostgreSQL-konténerben is kipróbálja. A PostgreSQL-image a már futó
adatbázis image-digestjéhez kötött; éles adatbázishoz nem kapcsolódik.

A próba végig a közös mentési zár alatt fut, és minden restic-művelete
`--no-lock` kapcsolós, így a routeren még lockfájlokat sem hoz létre. Nincs
retention, törlés vagy automatikus visszakapcsolás. A részletes napló privát,
az eredmény külön nyilvános JSON. Hat célzott teszt és valódi localhost FTP-s
listázási/teljes-check próba sikeres.

**Éles eredmény, 17:55:41–18:01:16 CET:** a korlátozott kapcsolatkezeléssel
mind az 1408 pack teljes adatolvasása sikeres. A snapshotból visszaállított
archívum SHA-256 értéke az eredeti helyi receiptjével egyezik, mind a 4007
belső fájlchecksum helyes. Az izolált PostgreSQL-visszaállítás is sikeres.
Az eredeti kapcsolatkezelés ebben az összehasonlításban már a listázásnál
`RuntimeError` hibával megállt. A próba távoli írást nem végzett, az automatikus
routeres mentés továbbra is kikapcsolt.

## Előkészített javítás: r15

Az r15 a ténylegesen igazolt kapcsolatszámot használja, és a retention előtt
és után teljes adatellenőrzést végez. Sikertelen első check után nem indul
törlés. A heti ütemezés csak az incidens előtti receipt szerint, az új kiadás
saját teljes mentési/visszaállítási próbái után kapcsolódik vissza.

[r15 csomag, indítás és bizonyítékok](../backups/releases/hc-router-backup-20261101-r15/README.md).
Az r14 jelenlegi tárolójának adatai a teljes próbán ellenőrzöttek; az incidens
feloldása az r15 élesítésének és új mentésének igazolásával zárható le.

Vak indexjavítás, a produkciós repository újrainicializálása vagy javítás célú
snapshot-törlés nem történt. A teljes éles adatolvasás és visszaállítás szerint
ezekre nincs szükség; az új mentő a működő kapcsolatkezelési útvonalat használja.

Referenciák: [restic hibakeresés](https://restic.readthedocs.io/en/stable/077_troubleshooting.html),
[rclone FTP opciók](https://rclone.org/ftp/),
[rclone 1.75.2 helyi jelszódekódolás formátuma](https://github.com/rclone/rclone/blob/v1.75.2/fs/config/obscure/obscure.go).
