# Routeres HDD-mentés: próba és HC-átállítási terv

Készült: 2026-10-31. Eszköz: TP-Link Archer BE550, 2 TB-os HDD.
2026-11-01: a routeres mentés fejlesztői kódja elkészült; a bevezetés és az első
titkosított routerpróba lépései a [megvalósítási leírásban](router-ftp-backup-implementation.md).
A következő alkalomra előkészített próba önálló eszköz. A jelenlegi mentést,
ütemezőket, Git-célokat és az AI-offline korlátozást nem módosítja.

## 1. Router előkészítése

1. Csatlakoztasd a HDD-t; saját tápos háznál a tápot is.
2. Az USB / USB Storage Device menüben ellenőrizd, hogy a router látja a lemezt.
   Ha a lemezen már vannak adatok, a próba miatt ne formázd.
3. Kapcsold be a Local FTP-t, az Internet FTP maradjon kikapcsolva.
4. Állíts be jelszavas hozzáférést, lehetőleg külön mentési felhasználóval,
   a router adminjelszavától eltérő jelszóval. Ha a firmware engedi,
   korlátozd egy `hc-backup` nevű megosztásra. A próbához olvasás, írás,
   könyvtárlétrehozás és a saját tesztfájl törlése kell.
5. Jegyezd fel a LAN IP-t, az FTP-portot és az FTP-n látható megosztási útvonalat.
   Ez nem feltétlenül ugyanaz, mint a lemez neve a router felületén.

A „Secure Sharing” jelszavas hozzáférés; nem igazolja az FTPS támogatását.
A titkosított mentést a HC fogja előállítani. A próba csak véletlen adatot küld,
nem valódi mentést, kulcsot vagy konfigurációt. Sima FTP-n a bejelentkezés
titkosítatlan; ezt a próbát a megbízható belső hálózaton végezzük.

## 2. Feltöltési próba a HC gépen

Csak a már rendelkezésre álló Python 3 kell. Nem szükséges sudo vagy csomagtelepítés.
A példákban az IP-t és a felhasználót cseréld a tényleges értékekre.
A jelszót a program rejtetten kéri be; ne írd parancssorba vagy chatbe.

Először nézd meg a router által mutatott megosztásokat:

```bash
cd /srv/docker/homecontrol
python3 scripts/test_router_ftp.py --host 192.168.1.1 --user hcbackup --list
```

Ez csak listáz. A 2026-11-01-i próbán a lemez FTP-útvonala `/G` volt.
A célmappának már léteznie kell; a `/` csak a megosztások gyökere,
ott a router a könyvtárlétrehozást `550 Permission denied` hibával elutasította:

```bash
python3 scripts/test_router_ftp.py --host 192.168.1.1 --user hcbackup --directory /G
```

A program egyedi `hc-ftp-test-<UTC-idő>-<véletlen-azonosító>` könyvtárat hoz létre,
16 MiB véletlen adatot tölt fel, ugyanazt visszaolvassa, és összeveti a méretet
és a SHA-256 ellenőrzőösszeget. Kiírja az átlagos fel- és letöltési sebességet.
Alapértelmezésben a saját tesztfájlját és az üres tesztkönyvtárát törli;
más fájlhoz nem nyúl. A helyi ideiglenes fájlt is eltakarítja.

Siker esetén nagyobb próba:

```bash
python3 scripts/test_router_ftp.py --host 192.168.1.1 --user hcbackup --directory /G --size-mib 256
```

A későbbi, újracsatlakozás utáni kézi ellenőrzéshez `--keep-remote` kapcsolóval
megtartható a tesztadat. A program kiírja az útvonalat és a SHA-256 értéket.
Ez a program nem végez több munkameneten át tartó tartóssági vizsgálatot.
FTPS-próba csak igazolt támogatás esetén: `--tls`; nincs visszaesés sima FTP-re
és nincs tanúsítvány-ellenőrzést kikapcsoló opció.

Elvárt végeredmény: `SHA-256 EGYEZIK`, majd `SIKERES PRÓBA`, kilépési kód 0.
Sikertelen takarításnál is hibás a kilépési kód, még ha az adatellenőrzés sikerült.
Megszakadt kapcsolatnál maradhat saját tesztkönyvtár; az útvonal alapján kézzel
ellenőrizhető. Ne használj rekurzív törlést a megosztás gyökerén.

Tipikus hibák:

| Jelenség | Ellenőrizendő |
| --- | --- |
| Kapcsolat elutasítva / időtúllépés | LAN IP, port, Local FTP, HC és router közti elérés |
| `530` | Felhasználó/jelszó és a megosztás hitelesítése |
| `550` könyvtárváltáskor | FTP-n látható útvonal; indulj `--list` móddal |
| `550` létrehozáskor/törléskor | Írási jogosultság, lemez csak olvasható állapota, szabad hely |
| Listázás vagy adatátvitel megakad | Passzív FTP adatkapcsolata, tűzfal, USB-tápellátás |
| Méret/SHA eltérés | A cél nem vehető át; USB, lemez és kapcsolat vizsgálata szükséges |

A kis FTP-próba a feltöltést/visszaolvasást igazolja. Nem igazol teljes
restic-kompatibilitást, 2 TB szabad helyet vagy teljes HC-helyreállíthatóságot.

Előkészítési ellenőrzés (2026-10-31): Python szintaxis és CLI-súgó rendben;
6 helyi ellenőrzés sikeres. Ideiglenes, kizárólag localhoston futó FTP-szerveren
1 MiB feltöltés/visszaolvasás, sérült adat felismerése, tesztadat megtartása,
törlési hiba jelzése és meglévő fájl megőrzése ellenőrzött; külön próba igazolta
a jelszó elrejtését a hibakimenetből és a vezérlőkarakterek elutasítását.
Az előkészítéskor a BE550-nel még nem történt tényleges próba; FTPS-t nem vizsgáltunk.

### Valódi routerpróbák, 2026-11-01

A felhasználó HC-terminálon futtatott próbáinak bemásolt kimenete alapján:
`192.168.1.1:21`, passzív Local FTP, felhasználó `kshma`, cél `/G`.
A router felületén a lemez `Chia_2TB_USB(G:)`, a felhasználó jogosultsága
`Read&Write`. A példákban szereplő `hcbackup` csak helyettesítő felhasználónév.

| Méret | Feltöltés | Visszaolvasás | Adatellenőrzés / takarítás |
| --- | --- | --- | --- |
| 16 MiB | 0,15 s; 104,62 MiB/s | 0,14 s; 110,36 MiB/s | SHA-256 egyezik; saját könyvtár törölve |
| 256 MiB | 2,32 s; 110,48 MiB/s | 3,29 s; 77,81 MiB/s | SHA-256 egyezik; saját könyvtár törölve |

A 256 MiB-os visszaolvasott adat SHA-256 értéke:
`5343973dfc171cf73aadecb58cdc6573340ac1095b3ab4cac527d50fc01e0b22`.
Ezek rövid FTP-próbák, nem tartós lemezsebesség-mérések vagy restic-restore próbák.
A helyi környezet ellenőrzésekor a restic elérhető `/usr/bin/restic` alatt,
rclone nem található a PATH-ban. Következő lépés: rclone elérhetővé tétele,
FTP-remote beállítása, majd elkülönített restic snapshot/check/restore próba.

## 3. A tervezett végleges felépítés

- Helyi, ellenőrzött HC-archívum és PostgreSQL-dump megmarad.
- Router HDD: verziózott, HC-n titkosított restic snapshotok,
  várhatóan a HC-n futó rclone FTP-kapcsolatán keresztül.
- Git: közvetlen feltöltés a kijelölt külső privát repóba, az AI gép Giteája nélkül.
- A régi, ép AI-backup HDD megmarad tartaléknak; az új próba nem migrálja/törli.
- A helyreállításhoz szükséges restic-jelszó és age privát kulcs külön,
  a HC géptől és a router HDD-től független helyen is megőrzendő.

Az FTP-tároló nem futtat Giteát. A külső Git cél tényleges URL-jét, ágát,
hozzáférését és a korábbi feltöltések állapotát külön, titkok kiírása nélkül
kell ellenőrizni. A Git export szűrését is vizsgálni kell éles feltöltés előtt.

## 4. Szükséges HC-oldali munka a sikeres FTP-próba után

1. **A ténylegesen telepített kiadás felmérése.** A forrásokban van régi és új
   runner, fagyasztott kiadás és host adapter is. Ellenőrizni kell a tényleges
   systemd ExecStart és Compose mount útvonalakat; nem elég egy forrásfájlt átírni.
2. **Korlátozások szétválasztása.** Az `infra/backend/deployment_policy.py`
   jelenleg az AI-offline profilban a `weekly`, `git`, `check` módot, valamint
   a Git/restic beállításokat is tiltja. A jóváhagyott új viselkedésben a routeres
   mentés és a külső Git működjön, miközben az AI wake/shutdown és a hibás gép
   elérése továbbra is tiltva marad. A policy fájl puszta törlése nem megoldás.
3. **rclone beállítása a HC hoston.** A futtató felhasználó saját, 0600-as
   konfigurációjában `routerbackup` FTP-remote; passzív mód és a kipróbált
   célútvonal. A jelszó nem kerül Gitbe, parancssorba vagy logba. Az rclone
   „obscure” jelszótárolása nem erős titkosítás: fájljogosultsággal kell védeni.
4. **Külön kis restic-próba.** Először új, elkülönített repositoryban init,
   snapshot, teljes `check --read-data` és staging restore, SHA-256 összevetéssel.
   A kipróbált lemezre tervezett repository: `rclone:routerbackup:/G/hc-backup/restic/homecontrol`.
   A relatív célútvonalat a tényleges FTP-gyökérhez kell igazítani. Ismeretlen
   hozzáférési hiba esetén nem szabad automatikusan új repositoryt inicializálni.
5. **Mentő és ellenőrző módosítása.** A `scripts/backup_archive_worker.sh`
   és `scripts/backup_check_worker.sh` jelenleg SSH/SFTP-t és AI-gépet feltételez.
   Külön tárolótípus kell az új célhoz, eltérő elérhetőségi ellenőrzéssel.
   A heti út (`scripts/backup_weekly_worker.sh`) routeres módban ne indítson
   AI wake/shutdown vagy Gitea-dump parancsot.
6. **Git független futtatása.** A `scripts/backup_config_sync_worker.sh`
   útját és az exportot a külső célhoz kell illeszteni. Az AI-s Gitea
   elérhetetlensége ne előfeltétele legyen a külső feltöltésnek.
   Sikertelen Git ne akadályozza a helyi/routeres mentést; mindhárom eredmény
   külön jelenjen meg, a hibák ne látszódjanak sikernek.
7. **Visszaállítás és titkok.** A `scripts/bootstrap_restore_v0_1.sh` még
   SFTP-célból olvassa ki a hostot. A tényleges staging restore/smoke útvonalakat
   is át kell állítani, és az új FTP/rclone hozzáférést a titkosított
   secrets-bundle manifestjébe fel kell venni. Legyen hálózat nélküli, külső
   kulcsmásolat is az új gépről induló helyreállításhoz.
8. **Felület és ütemezés.** A backend/backup UI külön kezelje a routert,
   külső Gitet és AI-gépet. Egyetlen közös backup runner/lock maradjon;
   ne jöjjön létre vele párhuzamos második mentési ütemező.
9. **Átadás és megőrzés.** Első valódi mentés, külön helyreállított
   archívum és PostgreSQL-próba után kapcsolható rendszeresre. A megtartási
   darabszám a mért méret/növekedés alapján állítható be. Régi mentést csak
   igazolt új mentés után takarítunk; az első átállás nem törli a régi HDD-t.

## 5. Források

- [Python ftplib: passzív FTP és FTP_TLS](https://docs.python.org/3/library/ftplib.html)
- [Restic rclone backend](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#other-services-via-rclone)
- [rclone FTP korlátok: távoli checksum és szabadhely-lekérdezés hiánya](https://rclone.org/ftp/#limitations)
- [HC korábbi backup/restore runbook](backup-restore-runbook.md)

A sikeres feltöltés nem helyettesíti a visszaolvasást; az FTP backend
nem ad távoli tartalomhash-t. A rendszeres integritásvizsgálatnak tényleges
adatolvasást is tartalmaznia kell.
