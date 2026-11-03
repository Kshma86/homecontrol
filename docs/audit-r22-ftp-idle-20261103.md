# r22 – reprodukált FTP-kapcsolatlejárat javítása és élesítési folytatás

**Lezárás (REPAIR-084): az r22 éles átadása sikeres; a korábbi indítók nem ismétlendők.**
[Aktuális végső állapot és bizonyítékok](audit-r22-live-handover-20261103.md).
Az alábbi előkészítési/hibaállapot történeti.

**REPAIR-080 frissítés:** a felhasználó az r22-t már elindította. A teljes
előmentés/retention és PG-restore sikeres; a telepítési hiba után az r18 rollback
sikeresen lefutott. Az alábbi eredeti indítóparancs nem ismételhető.
[Aktuális állapot és külön telepítési folytató](audit-r22-install-continuation-20261103.md).
Az alábbi előkészítési/indítási állapotok történetiek.

REPAIR-079, 2026-11-03. **Előkészítve és lezárva, még nincs élesítve.**
Aktív: `hc-security-20261102-r18`. Új csomag: `hc-audit-20261103-r22`.
Az r21, a korábbi folytatók és az eredeti hibabizonyítékok megmaradtak.

## A konkrét hiba és javítása

A felhasználó második root naplóösszesítése 10:34:25 CET-kor kimutatta:
a `37e3acdd8a374fc4a2a48422ab830ed5` előmentési futásnál az FTP 21-es
vezérlőportjára írás időtúllépett. Ez a feltöltés szülőkönyvtár-kezelésénél
és a repository-lock eltávolításánál is megtörtént. A restic-híd HTTP 500-at
adott; tényleges FTP 500 válasz nem látszik. A stdout csonkolt, ezért a nulla
megtartott forráshibát nem kezeljük teljes forráshiba-leltárként.
Átállítási tranzakció és új runtime nem jött létre.

A rögzített rclone 1.75.2 FTP-kód a poolból kivett kapcsolaton nem frissíti
új művelet előtt a socket határidejét. A használt TCP-timeout 30 s, a pool
alapértelmezett leürítése 60 s. A lejárt kapcsolat újrahasználható; a TCP
időzítő frissítése a sikeres I/O után már nem segít az első elutasított íráson.

Ezt a hibautat **tényleges, kizárólag localhostos FTP/rclone próbával**
reprodukáltuk. A rögzített binárissal, 35 s szünet után az eredeti beállítás
TCP write timeouttal és HTTP 500-zal hibázott. `--ftp-idle-timeout 10s`
esetén a feltöltés HTTP 200, a visszaolvasott tartalom egyezik, a locktörlés
HTTP 200. A teszt szintetikus adatokat és helyi FTP-szervert használt;
a routert nem érte el. A naplóval egyező mechanizmus reprodukált, az éles
routeres siker bizonyítása továbbra is a root élesítési kapu része.

A szűk transportjavítás ezt az egy opciót adja a meglévő parancshoz.
A 30 s timeout, 10 s connect timeout, egyszeri retryk, egy checker, egy transfer
és `rclone.connections=2` változatlan. Nem kapcsoljuk ki a feltöltés- vagy
adatellenőrzést; a titkosítás, célhely, hitelesítés és megőrzési szabály megmarad.

## Az új csomag és a megőrzött bizonyítékok

Az r22 az r21 799 változatlanul megőrzött forrásából készül. A kiadás saját
működési útvonalait új névtérbe rendereltük. Az alkalmazáskönyvtárakban egyetlen
fájl változott az r21-hez képest: `infra/backend/router_backup.py`.
A backend új image-et kapott az r21 pontos image-ére építve, hálózat és
függőségtelepítés nélkül. Minden beépített Python-forrás egyezik a csomaggal,
a telepített csomaglista és az indítási szerződés változatlan. Az mDNS és
Growatt jelölt image-e az r21-ből megőrzött; a többi 13 konténer baseline-ja
változatlan marad az átállítás során.

Az új backend image:
`sha256:e3e4b121fce197f3447cb656b1fdb7015099218a26365439d0f73d764a8dc291`.
A 19 image-es, külön offline archívum 2 006 099 033 bájt, tényleges Docker-load
ellenőrzéssel. Tartalmazza az r18 pontos rollback-image-eit is.

A megváltozott image-készletet nem próbáljuk az eltérő tartalmú történeti
r19/r20 cache-ekkel összekapcsolni. A root új staging-cache-t másol és hashel;
a régi cache-ek megmaradnak. A kapacitáskapu az eredeti két új archívum és 2 GiB
tartalék mellé az új staging-image-archívum teljes méretét is beleszámítja.
A `/var` mentési tárhely 30 GiB tartalékot ellenőrző kapuja külön megmarad.

Az r18 teljes előmentése külön shadow-runnerből történik. A meglévő privát
naplózási overlay mellett csak a javított transportmodult kapja meg a shadow;
az élő r18 forrása, image-e és recovery-névtere változatlan. A mentés tényleges
r18 állapotot tartalmaz. Nem használjuk fel sikeresként a korábbi hibás futást,
és nem helyettesítjük a kötelező friss előmentést annak helyi archívumával.

## Ellenőrzések

165 friss sikeres célzott teszt, hiba és kihagyás nélkül:

| Csoport | Eset |
|---|---:|
| Audit-aktiválás, előmentés/PG-kapuk, felügyelet, ütemezés, indítási guardok, naplóösszesítés és transport | 80 |
| Tényleges installer-/rollback-szerződések izolált fixture-ben | 16 |
| Router-aktiváló és visszagörgetés | 12 |
| Megőrzött lock-helyreállító adapter, valódi helyi restic-lock próbával | 24 |
| Routeres szerződések, workerek és valódi localhost FTP/restic próbák | 33 |

A 33 esethez a közvetlen eszközkimenetben megfigyelt eredményt rögzítettük;
annak teljes terminálnaplója nem került külön fájlba. Az új receipt ezt a
korlátot és az újrafuttatás pontos parancsát feltünteti. A többi csoport
végső naplója a csomagban van. Az első három új transportteszt-fixture-ből
hiányzott a szintetikus `restic_password_file`; ezt pótoltuk, az eredeti
sikertelen napló megmaradt, a runtime-ellenőrzést nem lazítottuk.

A 35 s idle-labor és a két tényleges processzpróba külön bizonyíték, nem további
unit-tesztszám. A backend és Growatt hálózat nélküli, jogosultságcsökkentett
konténerben elindult; a liveness sikeres, a hiányzó külső komponensek mellett
a readiness helyesen hibás. A saját laborkonténerek eltávolítva.

A korábbi 1308 alkalmazásregresszió bizonyítéka verzióhoz kötve megőrzött;
nem számítjuk újrafuttatottnak. Az egyetlen megváltozott alkalmazásmodul célzott
és valódi FTP-tesztet kapott. Új r22 bare-metal VM-recovery/reboot próba nem volt.

A lezárt csomag 805 forráshashét, a tesztbizonyítékokat, a 19 recovery-image-et,
a 736 élő r18 runtime-hasht, a 16 konténerbaseline-t, a healthcheckeket és az öt
aktív timert ellenőriztük. A csomag saját tényleges `core.verify()` ellenőrzése
is sikeres. Éles konténert az előkészítés nem állított át.

## Egyetlen helyi root-parancs

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261103-r22/source/scripts/audit_release/start_r22.py
```

Ez végrehajtó indító, nem újabb önálló diagnosztika. A felhasználó korábban
engedélyezett javításainak élesítését folytatja az új r22 csomaggal.

**Aktuális indítási korlát:** a felhasználó kifejezetten engedélyezte az r22
élesítését, a három komponens újraindításával és a host mentő átállításával.
Az ezutáni ügynöki indítást az automatikus ellenőrzés már nem utasította el;
a natív `sudo -n` viszont `sudo: a password is required` hibával, a Python-indító
végrehajtása előtt megállt. A fenti jóváhagyott parancsot a helyi terminálban,
jelszóval hitelesített sudo-val kell elindítani. Az r22 root végrehajtása még
nem kezdődött meg; a lezárt csomag változatlan.

Történeti előzmény: az első ügynöki root-indítást az automatikus jóváhagyási
ellenőrzés az új kiadás engedélyének egyértelműsége miatt elutasította.
Ez vezetett a konkrét felhasználói jóváhagyáshoz. Az eredeti elutasítás és a
jóváhagyás utáni sudo-eredmény külön nyugtában megőrzött; megkerülés nem történt.

1. Ellenőrzi a lezárt r22-t, az eredeti r21-et, a konkrét hibás futást,
   a privát eredeti kivételt és a két konkrét FTP-vezérlőkapcsolati timeoutot.
   Nem fogad el más hibaállapotot, újabb futást, megkezdett átállítást vagy
   már létező átadást. Valódi helyi root és egyszeri indítási nyugta kötelező.
2. A tárhelyellenőrző után mindkét közös hostlock alatt újraellenőrzi az állapotot
   és a diagnosztikát. A repository-lockok friss metaadatait a megőrzött,
   hash-ellenőrzött adapter vizsgálja: csak ugyanazon host igazoltan megszűnt
   folyamatának lockja oldható fel natív unlockkal. Nincs force, remove-all,
   adatjavítás, újrainicializálás vagy lockhiba miatti snapshot-törlés.
3. Új normál teljes repository-check, teljes r18 HC/Git/router előmentés és
   az archívumhoz kötött izolált PG-restore előzi meg az alkalmazásátállítást.
4. A backend, mDNS, Growatt és host runtime átállítása után új teljes r22
   HC/Git/router mentés, SHA-visszaolvasás és izolált PG-restore kötelező.
   A meglévő automatikus r18 rollback megmarad. A timerek visszaállítása,
   runtime-hashek, komponensek és policy záróellenőrzése után készülhet átadás.

Végső siker: **`deployed_and_audit_handover_complete`** és az r22
`evidence/post-live-check.json` nyugtája. A korábbi r21 folytatót ne ismételd.
Hiba után ezt az új indítót se ismételd vakon. A privát napló az r22 `private/`
könyvtárában marad; a root végrehajtás és az éles mentési/restore-átadás még függő.

46 Ellenőrzött; HC-41 az ESP MQTT-jelszó migrációja miatt, HC-43 a felhasználó
döntése szerint gyártói javításig Folyamatban. Az AI tiltva marad.
A jelenlegi javítási kör auditátadása a sikeres root-eredményig nincs lezárva.

Bizonyítékok: `backups/releases/hc-audit-20261103-r22/evidence/`, különösen
`ftp-idle-pool-lab.json`, `process-lab.json`, `baked-code-and-packages.json`,
`offline-load.json`, `application-delta.json`, `fresh-test-summary.json`
és `acceptance.json`. A készítési/ellenőrzési scriptek és a helyi indítási
próba további nyugtái: `docs/audit-evidence/r22-transport-20261103/`.

Elsődleges források a reprodukált mechanizmushoz:
[rclone 1.75.2 poolból történő kapcsolatkiadás](https://github.com/rclone/rclone/blob/v1.75.2/backend/ftp/ftp.go#L535),
[rclone 1.75.2 socket-deadline frissítése](https://github.com/rclone/rclone/blob/v1.75.2/fs/fshttp/dialer.go#L93),
[FTP pool-idle beállítás dokumentációja](https://rclone.org/ftp/#ftp-idle-timeout).
