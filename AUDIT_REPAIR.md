# HC audit – javítási nyilvántartás

**REPAIR-076 – mentési tárhely élesítve és utóellenőrizve (2026-11-03).**
A helyi root átállás eredménye `ok: true`, `phase: complete`. A mentések a `/var`
partíción érhetők el, kb. 157 GiB szabad hellyel; a `/srv`-n kb. 48 GiB szabad.
16 konténerbaseline, 10 healthy check, öt aktív timer, öt aktív/engedélyezett mount,
736 r18 runtime- és 799 r21 forráshash ellenőrzött. Aktív továbbra is r18.
Az r21 második folytatója rootként még nem indult; a helyi sudo-hitelesítés függő.
46 Ellenőrzött; HC-41/43 Folyamatban; a javítási kör éles átadása még nincs lezárva.
[Utóellenőrzés és következő végrehajtóparancs](docs/backup-storage-live-20261103.md).
Az alábbi korábbi állapotok történetiek; valódi host-rebootot továbbra sem állítunk.

**REPAIR-075 – nagyobb helyi mentési tárhely előkészítve (2026-11-03).**
A nagy mentési adatállomány a kb. 198 GiB szabad hellyel rendelkező `/var` partícióra
kerülhet, változatlan `/srv/docker/homecontrol/backups` eléréssel. Nincs új kvóta;
30 GiB rendszer/Docker tartalék és két nagy archívum helyét ellenőrizzük.
A lezárt release-ek és közös lock-inode-ok a `/srv`-n maradnak. Minden mentés megmarad;
a forrásról csak teljesen ellenőrzött fizikai másolatok takaríthatók meg.
23 sikeres teszt, valódi elkülönített mount/rollback és Docker bind-újranyitás,
valamint a teljes systemd-függőségi gráf ellenőrzése támasztja alá a csomagot.
**Csak előkészítve:** root átállítás és host-reboot nem történt; aktív r18.
Az r21 élesítés külön függő feladat. Először a tárhelycsomag eredményét kell ellenőrizni.
46 Ellenőrzött; HC-41/43 Folyamatban; az audit éles átadása nincs lezárva.
[Indítás, ellenőrzés, visszaállás és bizonyítékok](docs/backup-storage-var-20261103.md).
Az alábbi korábbi állapotok és indítóparancsok történetiek.

**REPAIR-074 – r21 tárhelykapu, kapacitás helyreállítva (2026-11-03).**
A korábbi natív lock-feloldás sikeres, maradó lock nincs. Az éjszakai új helyi mentés
után a látható szabad hely 6,5 GiB volt a kötelező 7,2 GiB helyett. Két azonos,
inaktív r11/r12 image-archívum teljes SHA-256-ellenőrzés utáni összekapcsolásával
1,3 GiB felszabadult; most 7,8 GiB szabad. Mentési archívumot nem töröltünk,
a kapacitásküszöböt nem csökkentettük. 10 új folytatóteszt sikeres.
A külön folytató rootként pontosan az előző tárhelyhibát követeli meg, a sikeres
unlockot nem ismétli, majd az eredeti teljes r21 élesítési kapukat futtatja.
Aktív r18, 736 runtime-hash és az öt timer ellenőrzött; a root végrehajtás még függő.
46 Ellenőrzött, HC-41/43 Folyamatban. A javítási kör éles átadása még nincs lezárva.
[Módosítás, bizonyítékok és aktuális folytatóparancs](docs/audit-r21-capacity-20261103.md).
Az alábbi korábbi indítási és diagnosztikai parancsok történetiek.


**REPAIR-073 – r21 zároláskezelés és ellenőrzött élesítési folytatás kész (2026-11-02).**
A root diagnosztika teljes adatellenőrzése sikeres; egy repository-lock maradt.
A tünetet valódi helyi restic repositoryban reprodukáltuk. A külön folytató csak
azonos géphez tartozó, bizonyítottan nem létező tulajdonosfolyamat lockját oldhatja fel,
kizárólag natív unlockkal, force nélkül. Utána az eredeti r21 összes mentési,
restore-, átállítási és záróellenőrzési kapuját végrehajtja; az előellenőrzést is naplózza.
24 teszt sikeres, köztük valós restic élő/megszakított folyamat- és lockpróba.
Aktív r18; a helyi root-futtatás még hátravan. Az r21 799 forráshashe változatlan.
46 Ellenőrzött; HC-41/43 Folyamatban; a javítási kör éles átadása még függő.
[Folytatóparancs, módosítás és ellenőrzési eredmény](docs/audit-r21-continuation-20261102.md).
Az alábbi régi aktiválási/diagnosztikai parancsok történetiek; az új folytatót használjuk.


**REPAIR-072 – r21 megállt a repository-előellenőrzésnél (2026-11-02).**
Aktív r18, a konténerek és 736 runtime-hash változatlan; alkalmazásátállítás nem indult.
A cache-előkészítés és külön router-probe sikeres, a szabad hely 9,2 GiB.
A teljes éles repository-ellenőrzés RuntimeError hibája még nincs diagnosztizálva.
Az aktiváló előellenőrzése nem használta az új worker-naplózót; a pontos kivétel root-private.
Külön, kilenc teszttel ellenőrzött, csak olvasó diagnosztika készült, helyi sudo-futtatás szükséges.
Az r21 aktiválóját nem ismételjük. A javítási kör éles átadása függő; HC-41/43 folyamatban.
[Részletek és diagnosztikai parancs](docs/audit-r21-precheck-failure-20261102.md).
Az alábbi korábbi előkészítési és élesítési állapotok történetiek.


**REPAIR-071 – r20 visszaállítva, r21 mentési kapuval előkészítve (2026-11-02).**
Aktív r18. Az r20 folytatás átállítás utáni restic-hibája automatikus rollbacket váltott ki.
A későbbi teljes repository-ellenőrzés és diagnosztikai snapshot sikerült; az eredeti hiba oka ismeretlen.
Az r21 az alkalmazások leállítása előtt teljes HC/Git/router és PG-restore próbát követel,
megőrzi a privát hibakimenetet, és azonos inaktív image-cache fájlokkal készít helyet.
105 friss teszt sikeres; az éles root-kapuk még hátravannak. A javítási kör átadása nem lezárt.
46 Ellenőrzött; HC-41 és HC-43 Folyamatban, az AI tiltva marad.
[Részletek, bizonyítékok és helyi indítóparancs](docs/audit-r21-preflight-20261102.md).
Az alábbi korábbi állapotok történetiek; a régi r20 aktiválót és folytatót nem ismételjük.


**REPAIR-070 – r20 mentési időkorlát, ellenőrzött folytatás előkészítve (2026-11-02).**
Aktív r18; az r20 az átállítás előtti mentésnél megállt, konténerváltás nem történt.
A helyi archívum elkészült, a 900 s külső timeout után a futás státusza beragadt.
Az eredeti r20 aktiválót nem ismételjük; külön, állapothoz kötött folytató készült,
23 sikeres izolált teszttel és valódi systemd folyamatfa-leállítási próbával.
A root-only újraellenőrzés és az éles átadás még hátravan.
[Részletek, ellenőrzések és helyi folytatóparancs](docs/audit-r20-continuation-20261102.md).
46 Ellenőrzött; HC-41 és HC-43 Folyamatban, az AI tiltva marad.
Az alábbi korábbi kiadási állapotok történetiek.


**REPAIR-069 – r19 automatikusan visszagörgetve, r20 előkészítve (2026-11-02).**
Aktív továbbra is r18. Az r19 friss Git/router/PG-restore próbája sikeres volt,
majd a történeti F6-nyugtából hibásan számolt időzítők miatt a záróellenőrzés
visszaállította az előző kiadást. Az r20 az aktuális generált ütemezést és a
valódi systemd-állapotot ellenőrzi. Az éles átadás még nem lezárt.
46 Ellenőrzött; HC-41 és HC-43 Folyamatban, változatlanul.
[Javítás, ellenőrzések és helyi r20 parancs](docs/audit-r19-retry-20261102.md).
Az alábbi r19 előkészítési feljegyzések történetiek.


Létrehozva: **2026-10-22**, Europe/Budapest.

Forrás: [HC_REFACTOR_AUDIT.md](HC_REFACTOR_AUDIT.md), a 2026-10-19–22-i audit, az N.5 összesítésével és az N. fejezet pontosításaival együtt.

Az átnézett audit SHA-256 lenyomata:

```text
51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2
```

**Aktív: `hc-security-20261102-r18`, élesítve és szoftveresen átvéve 2026-11-02.**
736 csomag-/runtime-forráshash egyezik; 15 komponens a várt image-en, a 10
healthcheck healthy, HTTP/worker/readiness rendben, 5 timer aktív, systemd-hiba nincs.
A teljes privát HA-előpróba, hitelesített HA API/64 Growatt-entitás és PG16/kolláció
sikeres. Friss HC/Git/router mentés, 6373 checksum, visszaolvasás és külön PG-restore
sikeres. Az AI tiltva, ESP MQTT kivétel változatlan. HC-23/43 korábbi részjavításai élesek;
HC-23 új JSON Compose recovery-javítása külön ellenőrzött, még nem éles (REPAIR-067). HC-43 upstream találatai folyamatban maradnak. A későbbi HC-15/16/20/24/26 kódjavítások
ellenőrzöttek, de még nincsenek ebben az éles kiadásban (REPAIR-062–066).
[Éles átadás](backups/deployments/hc-security-20261102-r18/DEPLOYMENT.md),
[utóellenőrzés](docs/audit-evidence/hc23-43-r18-live-20261102/production-check.json).

A következő bekezdés a korábbi r16 állapot történeti összefoglalója.

**Korábbi aktív: `hc-router-backup-20261101-r16`, élesítve és visszaállítással ellenőrizve.**
A teljes helyi/router/Git mentés, a megőrzés előtti és utáni adatellenőrzés,
5561 fájlchecksum és az izolált PostgreSQL-restore sikeres. A tényleges éles
Gitből és snapshotból friss, üres HC/image-tárú gép teljes helyreállítása,
FTP-kiesési próbája és rebootja is sikeres. Mind a 711 forráshash egyezik;
readiness jó, platform változatlan, az 5 hosttimer aktív és engedélyezett.
Az AI felhasználói döntés alapján letiltva marad; az SSD a jelenlegi mentési
ellenőrzéseknek már nem akadálya.
[Éles r16 átvétel és rollback](backups/deployments/hc-router-backup-20261101-r16/DEPLOYMENT.md).

**Auditösszesítés:** 46 ellenőrzött, 0 nyitott, 2 folyamatban (HC-41/43).
HC-15/16/20/24/26 izoláltan ellenőrzött kódjavítás; éles bevezetésük még nem történt meg.
HC-12 és HC-32 javítása éles; az aktív runtime r18. HC-23 kódja ellenőrzött, az új recovery-javítás még nem éles. HC-43 a felhasználó döntése szerint gyártói javításig, HC-41 az ESP legacy kivétel miatt folyamatban. HC-31 fizikai shutdown/OFF/wake
próba nem futott, csak későbbi AI-újraaktiválás előtt szükséges. A régi AI-Gitea
története nincs ellenőrzöttnek minősítve. A történeti napló megmarad.

## Az áttekintés eredménye

**Legújabb lezárt kiadási munka:** REPAIR-061, aktív r18.
**Legújabb ellenőrzött kódjavítás:** REPAIR-067, HC-23; nem éles.
[Friss és ismételt restore, FTP-kiesés, reboot, tesztek és kiadási függőség](docs/hc23-43-closure-20261102.md). A korábbi HC-15/16/20/24/26 javítások (REPAIR-062–066) megőrzöttek, szintén nem élesek.
A HC-23/43 kontrollált platformfrissítése éles és szoftveresen átvett;
HC-43 a gyártói találatok miatt továbbra is folyamatban. [Korábbi r18 scope és bizonyítékok](docs/hc23-43-platform-release-20261102.md).
Az SSD miatt korábban félretett, jelenlegi mentési láncra vonatkozó ellenőrzések
lezárva; [tételes bizonyítékok](docs/ai-ssd-backup-closure-20261101.md).
HC-41/43 továbbra is folyamatban. HC-23 ellenőrzött; az új recovery-forrás éles kiadása még szükséges. Más feladat
besorolása nem változott; a korábbi naplóbejegyzések történeti állapotot őriznek.

- A dokumentum 48, folytonosan számozott megállapítást tartalmaz: **20 P1, 26 P2, 2 P3**. A tételes besorolás egyezik az N.5 összesítésével. P0 megállapítást nem rögzít.
- A javasolt irány fokozatos javítás a meglévő architektúrán belül. Elsőbbséget kap a leállítás, a friss fizikai visszajelzés, az atomi foglalás és a restart utáni helyreállítás, továbbá a mentés/restore és a hozzáférési határok rendezése.
- A prioritás és a javítás regressziós kockázata külön kezelendő. A fizikai vezérlést érintő P1 tételek több ponton összefüggenek; a végrehajtásnál az F. fejezet előfeltételeit is követni kell.
- A korábbi sikeres tesztek az auditban leírt forrás-/image-állapotokra vonatkoznak. Az N.4 tíz közben megváltozott fájlt és új AI-képkezelést különít el; az új állapot teljes regressziója és függőségvizsgálata nyitott. A korábbi 374/83 és a külön 28/4 teszteredmény nem vonható össze aktuális kiadási bizonyítékká.
- Az About korábbi két timeoutját az N.3 kontrollja pontosítja; ebből nem következik bizonyított éles 60 másodperces hiba. A HC-48 hibás darabszám ettől külön, igazolt megállapítás.
- Ez az áttekintés a jelentés tartalmának feldolgozása. A megállapításokat most nem ellenőriztük újra a forráskódban vagy az élő rendszeren; minden javítás kezdetén az aktuális érintett állapotot kell rögzíteni.

## Nyilvántartási szabályok

Az audit HC-azonosítói és eredeti prioritásai megmaradnak. Egy javítás több tételt is érinthet, egy tétel több javításból is állhat. Részjavítás után a teljes tétel csak akkor zárható le, ha a fennmaradó részek és az audit ellenőrzési feltételei is rendezettek.

Használható státuszok: **Nyitott**, **Folyamatban**, **Javítva – ellenőrzésre vár**, **Ellenőrzött**, **Halasztva – indoklással**. Az ellenőrzött javítás éles bevezetését a naplóban külön kell rögzíteni; a sikeres teszt önmagában nem jelent telepítést.

Minden elvégzett változtatáshoz a lentebbi sablon alapján új, dátumozott naplóbejegyzés készül. A parancsok és eredmények tényleges futását, környezetét és korlátait rögzítjük. A nem futott ellenőrzés nem kap sikeres minősítést. Titokértékek nem kerülnek a nyilvántartásba.

## Tételes javítási lista

A fázisok az audit F. fejezetére hivatkoznak, nem végrehajtott munkát jelölnek. **F0 minden tétel közös előkészítése.** A HC-16 elsődleges besorolása P2; az auth-kompatibilitási takarítás része P3.

| Azonosító | Prioritás | Javítás tárgya | Auditfázis | Státusz |
|---|---|---|---|---|
| HC-01 | P1 | Elavult öntözési telemetria elfogadása fizikai visszaigazolásként | F3 | Ellenőrzött |
| HC-02 | P1 | A leállítási ellenőrzés kimaradása vagy blokkolása | F2 | Ellenőrzött |
| HC-03 | P1 | Félbeszakadt és sikertelen sessionök helyreállítása | F4 | Ellenőrzött |
| HC-04 | P1 | Öntözésindítás atomi lefoglalása | F4 | Ellenőrzött |
| HC-05 | P1 | Sikertelen safety-publikálás utáni hibás sikerállapot | F2 | Ellenőrzött |
| HC-06 | P1 | Safety GET állapotléptetése és a memóriabeli latch | F5 | Ellenőrzött |
| HC-07 | P1 | Üzleti konfigurációt átíró induláskori bootstrap | F7 | Ellenőrzött |
| HC-08 | P1 | Félbemaradó scheduler-auditlánc és rejtett parancsküldés | F4 | Ellenőrzött |
| HC-09 | P1 | Publikálás, befogadás és fizikai teljesülés szétválasztása | F2, F3 | Ellenőrzött |
| HC-10 | P2 | Cache-rétegek és invalidálási versenyhelyzet | F9 | Ellenőrzött |
| HC-11 | P2 | MQTT-feldolgozást blokkoló ingest DB-recovery | F10 | Ellenőrzött |
| HC-12 | P2 | Bridge-parancsfeldolgozás korlátai és sorrendje | F10 | Ellenőrzött |
| HC-13 | P2 | Háttérszálak életciklusa, hosszú kapcsolatok és teljes határidők | F10 | Ellenőrzött |
| HC-14 | P2 | Olvasás közbeni drága összesítésírás és hibás refresh-időzítés | F9 | Ellenőrzött |
| HC-15 | P2 | DB-wrapperlánc és az app összekötési felelősségei | F8 | Ellenőrzött |
| HC-16 | P2 | Rover-modulfüggőségek és kikapcsolt auth-kompatibilitás | F8 | Ellenőrzött |
| HC-17 | P1 | Hitelesítési backup fájl kizárása a Gitea-exportból | F1 | Ellenőrzött |
| HC-18 | P2 | Hiányos konfigurációexport és hatástalan megjelenített útlista | F1 | Ellenőrzött |
| HC-19 | P1 | Kettős backup-végrehajtó, közös névtér és redundáns timerek | F6 | Ellenőrzött |
| HC-20 | P2 | Elérhetetlen legacy öntözéskód és elavult dokumentáció | F8 | Ellenőrzött |
| HC-21 | P2 | Túlzott AI-kontextus és két helyen élő válaszlogika | F9 | Ellenőrzött |
| HC-22 | P2 | Frontend GET-határidő és elavult válaszok kizárása | F9 | Ellenőrzött |
| HC-23 | P2 | Reprodukálható telepítés és alkalmazásszintű állapotellenőrzés | F10 | Ellenőrzött |
| HC-24 | P2 | Végtelen ciklus az mDNS-parserben | F1 | Ellenőrzött |
| HC-25 | P3 | Teljes backup-log olvasása és író lockellenőrzés | F6 | Ellenőrzött |
| HC-26 | P3 | HA-Growatt entitásonként soros HTTP-polling | F10, használattól/méréstől függően | Ellenőrzött |
| HC-27 | P1 | Hibajelzés előtt részlegesen alkalmazott restore | F6a | Ellenőrzött |
| HC-28 | P2 | Fájljogosultságok és típusinformáció elvesztése restore közben | F6a | Ellenőrzött |
| HC-29 | P2 | Mentésdiff útvonalhatár-ellenőrzése | F6a | Ellenőrzött |
| HC-30 | P2 | Beállításfájl sikeres legutóbbi mentésként jelzése | F6 | Ellenőrzött |
| HC-31 | P1 | Késleltetett AI-áramtalanítás mentésvédelme és célazonossága | F6b | Ellenőrzött |
| HC-32 | P2 | Sikertelen Tuya-publikálás elküldöttként könyvelése | F10 | Ellenőrzött |
| HC-33 | P2 | Ingest batch-adatvesztés és elnyelt kapcsolathiba | F10 | Ellenőrzött |
| HC-34 | P2 | Tuya árammetrika hibás globális átnevezése | F10, önállóan F0 után előrevehető | Ellenőrzött |
| HC-35 | P2 | Érvénytelen explicit hozzárendelésből automatikus eszközcsere | F5a | Ellenőrzött |
| HC-36 | P1 | Bindingcsere után túlélő régi késleltetett ventilátor-ON | F5a | Ellenőrzött |
| HC-37 | P2 | Restore-smoke hamis sikere üres találatnál | F6a | Ellenőrzött |
| HC-38 | P2 | Verziózott SQL-ből nem rekonstruálható alapséma | F7 | Ellenőrzött |
| HC-39 | P2 | Runtime DB-superuser és SQL Lab olvasási jogosultsági határa | F7a | Ellenőrzött |
| HC-40 | P2 | Minden értékeléskor tartósan írt szivattyúdiagnosztika | F9 | Ellenőrzött |
| HC-41 | P1 | Névtelen hozzáférést engedő publikált MQTT-vezérlőbusz | F1a | Folyamatban |
| HC-42 | P1 | Git-szinkron hibája miatt kihagyott kötelező heti mentés | F6 | Ellenőrzött |
| HC-43 | P2 | Érintett függőségverziók vizsgálata és kontrollált frissítése | F10 | Folyamatban |
| HC-44 | P1 | Backend közvetlen Docker- és túl széles hostírási joga | F1b | Ellenőrzött |
| HC-45 | P1 | Friss host teljes restore-jából hiányzó időzítőtelepítés | F6a | Ellenőrzött |
| HC-46 | P1 | Másik archívum DB-dumpjának kiválasztása régi stagingből | F6a | Ellenőrzött |
| HC-47 | P1 | Restore-célkönyvtár figyelmen kívül hagyása a secreteknél | F6a | Ellenőrzött |
| HC-48 | P2 | About eszköz-/entitásdarabszám megsokszorozása metrikajoinnal | F9 | Ellenőrzött |

**Kezdő összesítés:** 48 nyitott; 0 folyamatban; 0 javított; 0 ellenőrzött; 0 halasztott. Éles bevezetés nem történt.

**Aktuális összesítés:** 0 nyitott; 2 folyamatban (HC-41/43); 0 javítva – ellenőrzésre vár;
46 ellenőrzött; 0 halasztott. HC-23 REPAIR-067 kódjavítása ellenőrzött, még nem éles. HC-15/16/20/24/26 kódja ellenőrzött, de még nem éles
(REPAIR-062–066).
HC-12/32 és az elkészült HC-23/43 részjavítások
élesek; aktív az r18 (REPAIR-061). Az r10 korábbi HC-35/36 + HC-41/44 javításait
az aktív kiadás megőrzi (REPAIR-049); az ESP legacy kivétel miatt
HC-41 folyamatban. HC-11/33/34 és 062 élesítése REPAIR-039; HC-10 és
HC-13/14/21/22/40 r8 élesítése REPAIR-035. HC-45 KVM REPAIR-046, aktuális r16 teljes hostrestore REPAIR-060. HC-31 fizikai AI-próbáját a szoftveres ellenőrzés nem
helyettesíti. Más auditpont besorolása ebben a javításban nem módosult.


## Végrehajtási támpontok

Az F. fejezet tartalmazza a részletes függőségeket, elfogadási feltételeket és rollbacket. Az alábbi lista csak navigáció a későbbi munkához.

| Fázis | Fő feladat / előfeltétel |
|---|---|
| F0 | Aktuális forrás-/image-állapot, visszaállítható mentés és izolált kiindulási tesztkörnyezet rögzítése |
| F1 | Exporthatár, közös forrásleltár és külön mDNS-parserjavítás |
| F1a | MQTT-kliens-/topicleltár, hitelesítés és ACL, a stopútvonal megőrzésével |
| F1b | Hostműveletek szűkített végrehajtója, a backup/restore/restart működésének megőrzésével |
| F2 → F3 → F4 | Leállítási hibahatár és transporteredmény → friss visszajelzés → atomi foglalás és recovery |
| F5 | Safety állapottulajdonos, tisztán olvasó GET, latch/restart-szemantika; F2 után |
| F5a | Érvényes binding és késleltetett ventilátorszándék összehangolása; F0 után előrevehető |
| F6 | Egy backup-runner/lock, korrekt készre jelentés és célonkénti eredmény; F1 után |
| F6a | Restore-forrás/cél, előellenőrzés, metaadatok és hostunitok; kis határjavítások F6 előtt is végezhetők |
| F6b | AI-leállítás és mentés közös koordinációja; a teljes backup-refaktortól külön előrevehető |
| F7 → F7a | Alapséma és explicit migráció, majd runtime-role szűkítés; a SQL Lab külön olvasókapcsolata előrevehető |
| F8 | Viselkedést megőrző egyszerűsítés, a kritikus működés stabilizálása után |
| F9 | Read model, cache, frontend és AI-konzisztencia, összehasonlítható mérésekkel |
| F10 | Bridge/ingest, worker-életjelek, reprodukálható deploy és függőségek, külön változtatásokban |
| F11 | Dokumentáció és feltételes takarítás; külső használat ellenőrzése után |

## Fennmaradó ellenőrzési határok

Az M.7 és N.5 alapján külön követendő: az élő PostgreSQL teljes fizikai lapintegritása; az aktuális távoli restic/Gitea; a friss host teljes restore-ja; a privilegizált host-/tűzfal-/más felhasználói leltár és PgBouncer-statisztika; a fizikai stop/kiesés/áramkimaradás és online integrációk; a tartós üzemi terhelés és teljes UI-munkafolyamatok; az aktuális kiadás regressziója, függőség- és eredetleltára.

Ezek az audit ismert bizonyítási korlátai, nem új HC-megállapítások és nem automatikusan végrehajtandó éles műveletek. A korábban sikeresen elvégzett izolált vizsgálatok eredménye megmarad a saját forrásállapotukhoz kötve.

## Javítási bejegyzés sablonja

Az alábbi sablon új bejegyzéshez másolható; nem elvégzett javítás.

```markdown
### REPAIR-001 — <rövid megnevezés>

- Dátum és végrehajtó:
- Érintett HC-tételek / auditfázis:
- Státusz:
- Kiindulási forrás-/image-/konfigurációazonosító:
- Aktuális hibabizonyíték és elvárt viselkedés:
- Módosítás és érintett fájlok:
- Ellenőrzés: környezet, tényleges parancs, eredmény:
- Nem futott ellenőrzések / fennmaradó részek:
- Visszaállítás módja, szükséges előállapot:
- Éles bevezetés: nem történt / időpont, verzió és eredmény:
- Lezárási bizonyíték / következő lépés:
```

## Munkanapló

### 2026-10-22 — Dokumentumáttekintés és nyilvántartás létrehozása

A teljes audit A–N. fejezeteinek áttekintése megtörtént, a későbbi pontosításokkal együtt. A HC-01–48 azonosítók folytonosságát és a prioritások összesítését dokumentumszinten ellenőriztük. Elkészült ez a nyilvántartás, mind a 48 tétel nyitott. Implementáció, hibareprodukció, tesztfuttatás és éles beavatkozás ebben a körben nem történt.

### REPAIR-001 — HC-01: friss Nano-mintához kötött öntözési visszaigazolás

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** kizárólag HC-01; áttekintett bizonyítékok: C./HC-01, B.6 időbélyeg-szemantika, H.1, M.4 valódi brokeres esetek; terv: F0, F3 és annak F2 előfeltétele.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. Éles bevezetés nem történt.
- **Előállapot:** a nyolc meglévő érintett fájl másolata és SHA-256 leltára `/tmp/hc01-repair/before/`, illetve `before-sha256.json` alatt; új fájl a monitor regressziós tesztje. Ez a leltár az érintett fájlokra vonatkozik, nem teljes projektmentés. Az eredeti audit fent rögzített lenyomata változatlan.

#### Felhasználó által igazolt firmware-szerződés

A Nano STATUS periódusa 30 s, a TELE periódusa 10 s; az ESP UART-offline határa 40 s, parancs után a Nano TX-csendje 250 ms. Események/parancsok soron kívüli üzenetet is adhatnak. Az ESP MQTT-publikálása eseményvezérelt, ezért új MQTT-üzenet nem feltétlenül jelent új Nano-mintát. A firmware-t ebben a javítási körben nem olvastuk vagy módosítottuk; ezek az üzemeltető által ellenőrzött és megadott adatok.

Az elsődleges online jelzés `nano_status.online`; a `pump_metrics` nem online-forrás, a `diag.nano_online` nem helyettesíti az elsődleges jelzést. A TELE konfigurációfüggően hiányozhat. A forrásminták korát a `last_tele_sec_ago`, illetve `last_status_sec_ago` adja.

#### Megvalósítás és érintett fájlok

- `infra/backend/mqtt_monitor_service.py`: monoton fogadási idő és kapcsolati generáció az MQTT-megfigyelésen, a korábbi mezők megtartásával; az öntözési snapshot kapcsolati állapota és named-topic mintái közös lock alatt készülnek. A reconnect nem fiatalítja és nem címkézi át a régi mintát. A közös monitoron csak additív megfigyelési metaadatok változtak; más domainek vezérlése nem módosult.
- `infra/backend/irrigation_service.py`: a TELE/STATUS kora külön-külön a firmware mintakorából és az MQTT-fogadás óta monoton eltelt időből áll elő. Retained, korábbi kapcsolati generációból származó, offline, hiányzó vagy hibás mintakorú adat nem igazol műveletet. A két topic közül mezőnként a legfrissebb elfogadható Nano-minta nyer. A Nano online állapota külön, lejáró `nano_status.online` megfigyelés; a `tele_fresh` és `status_fresh` ettől külön állapot. A TELE hiánya `null` frissességi állapotot ad, érvényes STATUS továbbra is használható.
- Minden open/close kísérlet saját, a publish indítása előtti monoton időhatárt kap. Csak ennél későbbi Nano-minta igazolhatja. A másodperc felbontású korközlés miatt a bizonyítás konzervatív alsó határa `MQTT-fogadási idő - forráskor - 1 s`; a 250 ms körüli, nulla másodperces kort jelentő üzenet önmagában nem bizonyít új mintát. Az aktuális időhatáron belül érkező későbbi minta igen. A mintakor/kapcsolat/topic és az elutasítás oka bekerül a meglévő confirmation-részletekbe.
- Hiányzó bizonyíték esetén a meglévő sikertelen confirmation-/session-ág fut (`start_failed`, `stop_failed`); a zárási parancs küldését a frissesség vagy online állapot nem tiltja. A `failed_no_watering` átmenethez mindkét szelep friss, a session kezdete utáni mintája kell. Pozícióigazolásnál pontos `OPEN`/`CLOSED` érték szükséges.
- `infra/backend/settings.py`, `infra/backend/app.py`: három külön konfigurálható frissességi határ bekötése. Az eddigi 5/30 s parancsvárakozás és a próbálkozásszám változatlan; új MQTT-parancsot nem vezettünk be.
- `infra/backend/tests/test_irrigation_service.py`: a korábbi live-state fixture frissítése és 26 új regressziós teszt; `infra/backend/tests/test_mqtt_monitor_service.py`: 3 új monitor-metaadat/reconnect teszt.
- `docs/ai/irrigation-domain.md`, `docs/ai/irrigation-scenarios.md`: az új viselkedés, konfiguráció és ellenőrzési esetek leírása. Ez a nyilvántartás a kilencedik érintett projektfájl.

| Konfiguráció | Kezdeti érték | Jelentés |
|---|---:|---|
| `IRRIGATION_VALVE_TELE_MAX_AGE_SECONDS` | 25 s | A TELE-minta megengedett kora, a fogadás óta eltelt idővel együtt |
| `IRRIGATION_VALVE_STATUS_MAX_AGE_SECONDS` | 70 s | A STATUS-minta megengedett kora, a fogadás óta eltelt idővel együtt |
| `IRRIGATION_NANO_ONLINE_MAX_AGE_SECONDS` | 40 s | Az elsődleges online-jelzés MQTT-fogadásának érvényessége, az UART-offline időhöz igazítva |

A határok véges, pozitív számok lehetnek. A 25/70 s a megadott kezdeti küszöb; a 40 s online-jelzés-élettartam a megadott UART-timeoutból választott, szintén konfigurálható kezdeti érték. Valós késleltetések alapján még felülvizsgálandók. Ezek nem a parancs-visszaigazolás timeoutjai.

#### Tényleges ellenőrzések

| Ellenőrzés | Eredmény és korlát |
|---|---|
| Eredeti hiba reprodukciója a mentett, változatlan kódon | A retained CLOSED és az új MQTT-ben ismételt régi Nano-minta két regressziós tesztmetódusa elbukott, összesen 3 hibás assertionnel, futási hiba nélkül. Ugyanezek a javított kódon sikeresek. |
| Kapcsolódó izolált unit-/regressziós kör | **109 teszt, 0 hiba, 0 kihagyás**; ebből a két öntözés/monitor modul együtt 46 teszt. A többi modul: startup, scheduler, combustion, WindowGuard, context, command, PowerWall, schema. Python audit hook tiltja a hálózati kapcsolódást/bindot, külső processzindítást és a `/tmp`-n kívüli fájlírást; fake transport/DB és fake óra. Nem teljes backend-/frontend-kiadási regresszió. |
| Python szintaxis | Mind a 6 módosított/új Python-fájl AST-ellenőrzése sikeres, alkalmazásimport nélkül. |
| Valódi MQTT-broker, elkülönített hálózati névtér | **10/10 eset várt eredménnyel**, mind a 10 parancs eljutott a tesztaktuátorhoz. Nincs hostport, LAN-/eszközelérés, éles `.env`, DB vagy Docker-socket a tesztkliensben; forrás csak olvasható. A teszt rövidített 0,1/2 s várakozást használ; az eredeti 5/30 s időzítést fake órás teszt ellenőrzi. |
| Takarítás | A saját broker és kliens eltávolítva; a `hc.repair=HC-01` konténerlista üres. Éles konténert nem indítottunk újra. |

A tíz brokeres eset: retained CLOSED új minta nélkül; friss parancs utáni CLOSED; cached, nem retained CLOSED új minta nélkül; új MQTT-ben régi Nano-minta; friss parancs utáni OPEN; hibás payload; friss STATUS TELE nélkül; elavult elsődleges és friss másodlagos topic; leválasztott monitor melletti zárásküldés; valódi kliens-reconnect új szelepminta nélkül. Csak a négy friss visszajelzéses pozitív eset igazolt sikeresen. A fizikai végrehajtót MQTT-tesztkliens helyettesítette.

A próbák előkészítésében két harness-hiba volt, ezeket javítás után újrafuttattuk: az első broker a jogeldobás miatt kilépett, majd a Mosquitto saját UID-jével elindult; az első reconnect-próbában a kézzel leállított Paho-hálózati ciklust újra kellett indítani. Ezek nem HC-termékhibák; a 10/10 eredmény a sikeresen befejezett futásé.

Reprodukálható kapcsolódó tesztparancs a projektgyökérből:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=infra/backend python3 -B -m unittest \
  tests.test_irrigation_service tests.test_mqtt_monitor_service \
  tests.test_startup_service tests.test_scheduler_service \
  tests.test_combustion_safety_service tests.test_climate_window_guard \
  tests.test_context_service_contract tests.test_command_service \
  tests.test_power_wall_service tests.test_schema_service
```

A tényleges, audit hookkal védett futás: `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/hc01-repair/check_unit.py`. Eredménye `unit-results.json`; a brokeres harness `check_mqtt.py`, eredménye `mqtt-results.json` és `mqtt-results.log` ugyanitt. Ezek ideiglenes segédanyagok; a tartós regressziós tesztek a fenti projektfájlokban vannak. A broker kizárólag `--network none` konténerben, a tesztkliens annak hálózati névterében futott.

Rögzített teszt-image-ek:

```text
broker: sha256:077fe4ff4c49df1e860c98335c77dda08360629e0e2a718147027e4db3eace9d
kliens: sha256:02eeec7c53042759bd25764ca668594dc25d364e6339f0a1ed2ce73fea2a78ed
```

A kliens a módosított forrásokat read-only mountból importálta; éles image építése/telepítése nem történt. A két fő javított modul lenyomata:

```text
infra/backend/irrigation_service.py
bbf6ddc2168bd1d1adc9087d625ed1d31ac5f7160481354db01344f0e483240f
infra/backend/mqtt_monitor_service.py
b9c78bd49f96ae584a5c9494127bbb404cd83ac9dfccb3ce1aa8480f0985dca5
```

#### Függőségek, fennmaradó ellenőrzés és rollback

- **F2 / HC-02, HC-05, HC-09:** az audit F3 előfeltételeként szerepel; ebben a körben nem készült el. A scheduler stop-hibahatára, a combustion retry és az általános MQTT transporteredmény kezelése változatlan. A HC-01 frissességi védelme önállóan ellenőrzött, de nem jelenti a teljes F2/F3 vagy a klíma/X10 visszaigazolási szerződés lezárását.
- **HC-03/04:** restart-recovery és atomi foglalás továbbra is nyitott. A frissesség hiánya a meglévő sikertelen session-állapothoz vezet; annak további életciklusát ez a javítás nem rendezi.
- **Éles bevezetés előtt:** aktuális visszaállítható mentés/release-azonosság, felügyelt valós szeleppróba és a STATUS/TELE/online késleltetések mérése szükséges. A másodperc felbontású mintakor és az ESP→MQTT út késleltetése miatt nincs parancsazonosítóval igazolt fizikai nyugta; a javítás konzervatív időbeli mintabizonyítékot használ. Egy túl korai válasz után friss későbbi minta hiányában szándékosan sikertelen a visszaigazolás. Üzemi finomhangolás még nem történt.
- **Rollback:** az érintett monitor/service/settings/wiring együtt állítandó vissza a mentett előállapotból vagy előző ismert kiadásból; DB-migráció nincs. A régi kód visszahozza a HC-01 hamis visszaigazolási kockázatát, ezért küszöbproblémánál először a mért konfigurációt és a visszajelzési útvonalat kell ellenőrizni. Bizonytalan állapot utólag nem írható sikerre; indítás tiltása mellett a zárási lehetőség megőrzendő. Függő fizikai művelet esetén állapotegyeztetés előzze meg a kódváltást.

Más auditpont státusza és implementációja nem változott. Az éles bevezetés külön lépés marad.

### REPAIR-002 — HC-02: elkülönített leállításfelügyelet és műveletenkénti hibahatár

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-02. Áttekintve: C./HC-02 és kapcsolódó HC-03/04 bizonyítékok, H.1 scheduler-hibainjektálás, F0 és F2 előfeltételei/ellenőrzései, valamint a már javított HC-01 visszaigazolás. Más auditpont javítása nem indult.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. Ez a HC-02 részét teljesíti az F2-nek; a teljes F2 nem zárható le HC-05 és HC-09 nélkül. Éles bevezetés nem történt.
- **Előállapot:** nyolc meglévő érintett fájl másolata és SHA-256 leltára `/tmp/hc02-repair/before/`, illetve `before-sha256.json` alatt; új fájl a start/stop versenyhelyzetek tesztje. Ez érintettfájl-leltár, nem teljes mentés vagy Git-commit. Az eredeti audit változatlan.

#### Mi változott és miért?

| Fájl | Módosítás |
|---|---|
| `infra/backend/startup_service.py` | Egyetlen `irrigation-safety` szál külön felügyeli a V2 effektív stopot, az általános lejáratot és a fizikai öntözés hiányát; mindhárom önálló, névvel naplózott hibahatárt kapott. A V2 stop megelőzi az általános lejáratot, így megmarad a korábbi stop-policy és indok. Egyetlen soros `scheduler` szál futtatja az auditot, az indításokat és az X10-szinkront, külön hibahatárokkal. Egy lassú OPEN nem foglalja a safety szálat. Első induláskor a stop-ellenőrzések megkísérlése megelőzi a scheduler elengedését. Tickenként nem indul új szál/feladat. |
| `infra/backend/app.py` | A külön V2 stop-tick bekötése; a combustion és WindowGuard hívásai külön hibahatárt kaptak, a service-getterekkel együtt. A combustion belső állapot-/retry-logikája nem változott. |
| `infra/backend/irrigation_service.py` | A V2 stop kikerült az indítási tickből a külön `scheduler_stop_tick()` metódusba, az eredeti domainkapu megtartásával. A fizikai szelep publikálásainak folyamaton belüli sorrendje és a stop által érvénytelenített OPEN-generáció védi az új párhuzamosságot. A kézi/V2 indítás már DB-előkészítés előtt megőrzi ezt a generációt. A session SQL-ek és helyreállítási szűrések nem változtak. |
| `infra/backend/tests/test_startup_service.py` | 7 új teszt: callbackenkénti kivételek/timeoutok, V2 stop elsőbbsége, egyszeri és külön workerindítás, indulási sorrend, ciklusütem és a combustion/WindowGuard hibahatára. A tényleges app-függvény AST-ből izoláltan fut, teljes alkalmazásimport nélkül. |
| `infra/backend/tests/test_irrigation_service.py` | A régi scheduler-teszt a különválasztott viselkedést követi; 2 új teszt ellenőrzi a külön V2 stop-ticket és a domainkaput. |
| `infra/backend/tests/test_irrigation_stop_priority.py` | 9 új, valódi szálakat/Eventeket használó regressziós teszt: lassú OPEN, lejárt session, egyszerre érkező kézi/automatikus stop, folyamatban lévő publish, nyitási tiltás a stop végéig, nyers kézi `valve_stop`, késő OPEN-megfigyelés, kivétel utáni takarítás és DB-előkészítés közbeni stop. |
| `docs/ai/irrigation-domain.md`, `docs/ai/scheduler-domain.md` | Az új worker-/hibahatárok, parancssorrend és késleltetési korlátok leírása. |
| `AUDIT_REPAIR.md` | HC-02 státusza és a jelen javítási/ellenőrzési jegyzőkönyv. |

A kilenc érintett projektfájl változásai kizárólag ezt a javítást és dokumentálását szolgálják.

#### Start/stop-egyeztetés és időzítési szerződés

- A close és a nyers kézi `valve_stop` a belépésekor érvényteleníti a régi OPEN-generációt, még mielőtt egy másik stopra vagy folyamatban lévő publikálásra várna.
- Az OPEN/CLOSE publikálások közös lockot használnak; az 5/30 másodperces reakció-/végállapot-várakozás ezt a lockot nem tartja. A stop így a nyitási várakozás befejezése előtt elküldhető. A már futó publish-hívás viszont nem szakítható meg.
- Stop közben nem küldhető új OPEN, az egyidejű stopok a közös fizikai szelep miatt sorban futnak. A stop alatt felvett, illetve a stop előtt már DB-előkészítésbe lépett kézi/V2 indítás később sem válik újra érvényessé.
- Az érvénytelenített OPEN a következő várakozás/megfigyelés visszatérésekor sikertelenül, `blocked_by=stop_request` jelzéssel zárul; nem ismételhet OPEN-t, és a késői OPEN-megfigyelést sem fogadhatja el sikerként. A már létező session-hibakezelési út kapja az eredményt.
- A HC-01 friss Nano-mintát követelő logikája, a season-profile szabályok, az open/close próbálkozásszám és az 5/30 s konfiguráció változatlan. A fizikai zárás igazolását nem vettük ki.
- Mindkét worker a meglévő `IRRIGATION_SCHEDULER_POLL_SECONDS` alapján alszik a saját köre után: alapérték 5 s, minimum 1 s. Reszponzív függőségeknél az észlelési késés a safety szál saját munkája és pollingja; a scheduler akár 90 s összesített OPEN-várakozása ehhez már nem adódik hozzá.
- **Nincs igazolt kemény fizikai stop-határidő:** a safety callback saját DB-hívása, egy előző stop visszaigazolása vagy a már futó MQTT-publikálás késleltethet. Az esetleges végtelen/blokkoló I/O-t ez a javítás nem preemptálja; egyszerű Python-thread-timeouttal sem állítja le. Az MCU-failsafe és motorzárási idő külön fizikai bizonyítékot igényel.

#### Tényleges ellenőrzések és eredmények

| Ellenőrzés | Eredmény és bizonyítási határ |
|---|---|
| Eredeti scheduler-hiba a mentett forráson | Egyetlen régi `_safety_loop` körben az injektált scheduler-DB-timeout után csak az audit és a hibás öntözési scheduler futott; stop és no-water ellenőrzés nem. Fake I/O, a végtelen ciklus a kör végén megszakítva. |
| Eredeti combustion→WindowGuard hiba | A mentett app-függvény izolált futásában a combustion kivétele után WindowGuard nem futott. Az appot nem importáltuk. |
| Kapcsolódó unit-/regressziós kör | **127 különálló teszt, 0 hiba, 0 kihagyás**, köztük a HC-01 regressziói és 18 új HC-02 tesztmetódus. Egyedi tesztazonosítók ellenőrizve. Audit hook tiltja a külső hálózati connect/bindot, processzindítást és a `/tmp`-n kívüli írást; fake DB/MQTT, fake óra és kontrollált valódi szálak. Nem teljes kiadási suite. |
| Lassú nyitás közbeni felügyelet | A nyitási várakozást Event tartotta függőben; a tényleges `_safety_tick()` közben lefuttatta a lejárt session zárását, a nyitás feloldása nélkül. A fake I/O-s mérés 0,091 ms körüli callback-időt adott; ez tesztharness-adat, nem üzemi teljesítménybecslés. Külön fake-órás ciklusteszt két 5 s pollinglépést ellenőrzött. |
| Valódi broker, automatikus stop | **Sikeres.** 1 s tesztpolling mellett a fake DB-határidő és a CLOSE tesztaktuátorhoz érkezése között **998,97 ms** telt el. Parancssorrend `OPEN → CLOSE`; a nyitás még várakozott, majd megszakított eredménnyel zárult. Friss MQTT-visszajelzés után `auto_stopped` lett a fake session. |
| Valódi broker, egyidejű kézi stop | **Sikeres.** Az automatikus CLOSE érkezésének késése **998,76 ms**; a kézi stop ugyanazon függő nyitás alatt indult. Sorrend `OPEN → CLOSE → CLOSE`, késői OPEN nélkül; a kézi service-hívás sikeres 200-as eredményt adott. Ez nem HTTP-/böngészőteszt. |
| Python szintaxis és hatókör | A 6 módosított/új Python-fájl AST-parse-a sikeres. AST-/SQL-összevetés szerint a HC-01 megfigyelési függvénye, a session-kiválasztási/recovery szűrések és az indítási session SQL-ek változatlanok. |

A brokeres eredmények két egyszeri, erőforráskorlátozott izolált eset mérései. Nem éles p95/p99, és nem az 5 s alapbeállítás mérései. A kliens a tényleges startup-scheduler/safety loopokat, öntözési service-t és MQTT-klienseket futtatta; a DB-t fixture, a fizikai szelepet MQTT-tesztaktuátor helyettesítette. Az audit és a V2 stop callback injektált DB-timeoutja mellett az általános határidőellenőrzés tovább futott. Az OPEN-várakozás 5/30 s, 3 próbálkozás volt; a stop-visszaigazolás csak a tesztben 0,1/2 s-ra rövidült.

A végleges forrás brokeres újraellenőrzésének első próbája még a kezdő állapot feladása előtt feliratkozási versenybe futott a harness-ben: a connect jelzése után, a SUBACK-ek előtt publikált egyszeri kezdő üzenet elveszett. A harness ezután minden feliratkozási nyugtát megvárt; a fenti **2/2 sikeres eredmény** a befejezett végső futásé. Emiatt termékkódot nem változtattunk.

Reprodukálható kapcsolódó tesztparancs a projektgyökérből:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=infra/backend python3 -B -m unittest \
  tests.test_irrigation_service tests.test_mqtt_monitor_service \
  tests.test_startup_service tests.test_scheduler_service \
  tests.test_combustion_safety_service tests.test_climate_window_guard \
  tests.test_context_service_contract tests.test_command_service \
  tests.test_power_wall_service tests.test_schema_service \
  tests.test_irrigation_stop_priority
```

A tényleges védett futás: `PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/hc02-repair/check_unit.py`. A `check_mqtt.py`, `unit-results.json`, `mqtt-results.log` és `mqtt-results.json` ugyanezen ideiglenes könyvtár segédanyagai; a regressziós tesztek tartósan a projektben vannak. A broker `--network none`, a kliens `--network container:hc02-repair-broker` módban futott, hostport, éles `.env`, DB-, Docker-socket- és LAN-/eszközelérés nélkül. A forrás read-only mount volt. Ugyanazt a két rögzített image-et használtuk, mint REPAIR-001-ben; image építése vagy éles szolgáltatás módosítása nem történt.

A fő módosított modulok végső SHA-256 lenyomatai (a korábbi bejegyzés lenyomatai történeti állapotot jelölnek):

```text
infra/backend/startup_service.py
abc9bb531ebbab3c019cb30f86ce116ac799a77eeefc66efa776d917da2ef33d
infra/backend/irrigation_service.py
e747ff2696e690c5df54337f1b09fac403073741f9b647356df53c70d424adc1
infra/backend/app.py
b639088459d52ffa4c99f782cff61d89c285dff5e7164d64519d61dd19a4ea6f
```

#### Nyitott függőségek, bevezetés és rollback

- **HC-04:** az új guard kizárólag folyamaton belüli parancssorrend és megszakítás. Nem hoz létre DB-egyediséget/atomi session-foglalást, nem zárja a két kézi indítás versenyét, és nem többprocesszes tulajdonlás. Az egypéldányos backend megtartandó; a workers számát nem emeltük.
- **HC-03:** restart-recovery, a `starting`/`stop_failed` sorok további felügyelete és a fizikai művelet/DB-commit közötti crash továbbra is külön feladat. A mostani start/stop-generáció memóriabeli; nem tartós helyreállítási mechanizmus.
- **HC-05 és HC-09:** a safety-publish eredmény-/retry-kezelése és az általános MQTT transporteredmény változatlan; ezért a teljes F2 nincs lezárva.
- **HC-08 / HC-13:** a stop nem várhat a korábbi auditlánc sikerére. Az audit DB-láncának folytathatósága és a hiányzó execution-sor egyeztetése, továbbá a worker-életjelek, egységes leállítás és I/O teljes határideje nem készült el ebben a körben. A napelemes pumpa meglévő vegyes start/stop tickje továbbra is a scheduler szálon fut; azt nem bontottuk szét.
- **Éles ellenőrzés:** aktuális visszaállítható mentés/release-azonosság, felügyelt fizikai stop/failsafe próba és DB-/broker-kiesési késésmérés még szükséges. A mostani timeout-injekció nem valóban beragadt éles DB-lekérdezés, és nem motorzárási mérés. Éles bevezetés nem történt.
- **Rollback:** a startup, app-wiring és irrigation service együtt állítandó vissza az előállapotból vagy ismert kiadásból; DB-migráció nincs. Az új scheduler/safety szálakat a régi kód bevezetése előtt ugyanazon processz szabályozott leállításával kell megszüntetni. A már függő OPEN-t nem szabad automatikusan újrajátszani. Kód-revert önmagában nem állítja vissza a fizikai állapotot; előbb állapotegyeztetés szükséges. Visszaállításkor a korábbi blokkolási/kivételkezelési kockázat visszatér.

Csak HC-02 kapott új státuszt; HC-01 korábbi ellenőrzése és a további auditpontok nyitottsága megmaradt. Az eredeti auditdokumentumot nem módosítottuk.


### REPAIR-003 — HC-03: tartós, korlátos session-helyreállítás

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-03. Áttekintve a C./HC-03 bizonyítékai és érintett session-/stop-szűrései, a kapcsolódó HC-04/08, valamint F0, F3 és F4 előfeltételei, ellenőrzései és rollbackje. Más auditpont nem kapott javítást vagy új státuszt.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. Ez az F4 helyreállítási részét teljesíti; a teljes F4 HC-04 és HC-08 nélkül nyitott. Éles bevezetés és fizikai próba nem történt.
- **Előállapot:** 12 meglévő fájl másolata és SHA-256 leltára a `/tmp/hc03-repair/before/`, illetve `before-sha256.json` alatt; 3 új Python-fájl. Ez érintettfájl-leltár, nem teljes mentés vagy Git-commit. Az eredeti audit változatlan.

#### Mi változott és miért?

| Fájl | Módosítás |
|---|---|
| `infra/backend/irrigation_recovery.py` (új) | Induláskori és periodikus, kizárólag záró helyreállítás. A meglévő `stop_payload.recovery` JSON-ban tartós próbálkozáskeret és következő időpont; feltételes DB-foglalás és eredményírás. Külön olvasható lista minden bizonytalan sessionről. |
| `infra/backend/irrigation_service.py` | A `stop_failed` is blokkolja az indítást. Recovery-inicializálás az indítás előtt; bizonytalan OPEN után követhető `stop_failed` marad. A `starting → running` és hibakiírás feltételes, így késői start-eredmény nem éleszti újra a közben lezárt sort. Kézi zárás `starting`/`stop_failed` sorra is elérhető; megőrzi a tartós keretet és frissíti a recovery eredményét. Recovery esetén egyetlen CLOSE-t tartalmazó próbálkozás kérhető. |
| `infra/backend/startup_service.py`, `infra/backend/app.py` | A recovery külön hibahatárral elsőként fut a safety passban. A HC-02 indulási sorrendjével együtt ez megelőzi a scheduler elengedését; az indítási service-útvonalak önálló inicializálási kaput is kaptak. |
| `infra/backend/settings.py` | Három konfigurálható határ: indulási türelmi idő, retry-várakozás és automatikus recovery-keret. |
| `infra/backend/tests/test_irrigation_recovery.py` (új) | 21 unit-/regressziós teszt: állapotok, konfiguráció, DB-/publish-határok, megszakítás, visszatérés, frissesség, tartós keret és párhuzamos tick. |
| `infra/backend/tests/test_irrigation_recovery_postgres.py` (új) | 12 külön, explicit engedélyezett, izolált PostgreSQL-teszt a tényleges SQL-re, tranzakcióhibákra, párhuzamos foglalásra és időkezelésre. Alapfutásban nem csatlakozik DB-hez. |
| `infra/backend/tests/test_irrigation_service.py`, `test_startup_service.py`, `test_irrigation_stop_priority.py` | A fixture-ök, státuszelvárások és callback-sorrend követik az új recovery-szerződést; a korábbi HC-01/02 regressziók megmaradtak. |
| `infra/frontend/src/features/irrigation/Irrigation.jsx` | Minden bizonytalan session látható az állapottal, korral, kerettel, következő próbával és kezelői figyelmeztetéssel, a legutóbbi tíz sessionen túl is. A session-táblázat a hibaszöveget is megjeleníti. |
| `docs/ai/irrigation-domain.md`, `scheduler-domain.md`, `irrigation-scenarios.md` | Állapotátmenetek, indulási/periodikus helyreállítás, időzítés, kézi beavatkozás, korlátok és új konfiguráció dokumentálása. |
| `AUDIT_REPAIR.md` | HC-03 státusza és jelen ellenőrzési jegyzőkönyv. |

Összesen 15 projektfájl érintett. Nincs új státuszérték, táblamódosítás vagy migráció: a napló a meglévő JSON-mezőben él. A teszt-DB sémája kizárólag az izolált, eldobható adatbázisban készült el.

#### Helyreállítási szerződés

- A támogatott egypéldányos backend induláskor a megmaradt, nem `physical_manual` `starting` sorokat bizonytalannak minősíti. A DB-scan sikeréig új HC-OPEN nem engedhető át. A DB-visszatérés után a következő tick újra megkísérli az inicializálást.
- Futás közben a `starting` sor a türelmi idő vagy a kért/biztonsági stop-határidő lejáratakor kerül recoverybe. A türelmi idő alapértéke `IRRIGATION_START_RECOVERY_GRACE_SECONDS=120`; ténylegesen legalább a konfigurált nyitási próbák névleges várakozási ablaka +30 s. Ez nem teljes DB-/transport-határidő.
- A sikertelen új OPEN-visszaigazolás `stop_failed` állapotot és `origin_status=starting` naplót hagy. Csak igazolt zárás után lesz terminális `start_failed`; ez nem sikeresen végrehajtott öntözés. A korábban terminálisra könyvelt történeti `start_failed` sorokat a javítás nem minősíti át vakon.
- `IRRIGATION_RECOVERY_MAX_ATTEMPTS=3` alapból sessionönként három **további automatikus foglalási helyet** jelent; helyenként legfeljebb egy CLOSE küldhető. Egy safety pass legfeljebb egy fizikai recovery-próbát indít. A rendes/kézi stop korábbi saját próbálkozási kerete változatlan.
- A slot és a következő megengedett időpont DB-idővel, még MQTT előtt commitolódik. `IRRIGATION_RECOVERY_RETRY_SECONDS=60` az alap várakozás; processz-újraindítás nem nullázza. Küldés előtti crash is elfogyaszthatja a slotot, ezért a számláló nem bizonyít fizikai teljesülést. Hosszú DB-tranzakció nem marad nyitva a MQTT-várakozás alatt.
- Az azonos recovery-JSON-ra és esedékességre feltételes foglalás megakadályozza ugyanazon slot kétszeri felvételét. Az eredményírás is feltételes; egy közben sikeres kézi stopot vagy újabb recovery-eredményt nem ír felül. Ez kizárólag recovery-foglalás, nem a HC-04 szerinti atomi start-admission.
- Friss CLOSED megfigyelés a recovery saját megfigyelési határa után, a HC-01 forráskor-/online-/retained-/kapcsolatvédelmével fogadható el. Régi retained CLOSED nem siker. Friss CLOSED a várakozás vagy keretkimerülés alatt is rendezheti a sort további küldés nélkül. Sikertelen eredménycommit esetén a bizonytalanság és az elfogyasztott slot megmarad.
- Kimerülés után a sor `stop_failed`, látható és indítást tilt; kézi zárás továbbra is megengedett. A kézi zárás megőrzi a keretet és az eredeti okot; a helyi indítási tiltás konzervatívan a következő sikeres scanig megmaradhat. Bizonytalanság után nincs automatikus OPEN-replay.
- A `physical_manual` sorok nem vesznek részt az automatikus besorolásban, recovery-foglalásban, eredményírásban vagy bizonytalan HC-sessionök listájában. A helyreállítás nem függ a schedule napjától, éjféltől, DST-től vagy a nyitást tiltó szezonprofiltól.

#### Tényleges ellenőrzések és eredmények

| Ellenőrzés | Eredmény és bizonyítási határ |
|---|---|
| Mentett előállapot | Reprodukálva: a `stop_failed` nem tiltott indítást, a lejáratkezelő pedig kihagyta a `starting`/`stop_failed` sorokat. Forrásból, fake DB/MQTT mellett. |
| Kapcsolódó unit-/regressziós kör | **148 különálló teszt, 0 hiba, 0 kihagyás**: a korábbi 127 és 21 új recovery-teszt. Audit hook tiltja a hálózati connect/bindot, processzindítást és a `/tmp`-n kívüli írást. Fake DB/MQTT, kontrollált idő és szálak. Nem teljes kiadási regresszió. |
| Valódi izolált PostgreSQL | **12 teszt, 0 hiba**. Az eredeti session-DDL és a tényleges service-SQL: rollback; commit megtörtént, válasz elveszett; sikeres fizikai eredmény után hibás DB-commit; két valódi kapcsolat versenye; kézi stop és késő start-commit; tartós JSON-keret/backoff; DB-idő; DST-/napváltásból megmaradt sor; szezonkapu; `physical_manual`. A kézi zárás végső recovery-állapotának pontosítása után mind a 12 újra sikeres. |
| Valódi MQTT + PostgreSQL együtt | **Sikeres**: retained CLOSED után az első CLOSE nem kapott friss igazolást; a teszt a küldés után, a végső eredménycommit előtt processzhalált szimulált. Új service-példány ugyanazon DB-n megtartotta a keretet és backoffot. Csak a következő engedélyezett CLOSE-ra érkező későbbi, friss Nano-visszajelzés lett sikeres. Végállapot `start_failed`, 2 foglalt slot, parancsok kizárólag `CLOSE → CLOSE`; OPEN-replay nélkül. |
| Frontend meglévő ellenőrzései | **83 mower + 4 AI teszt sikeres**, és `npm run build` sikeres. Az új megjelenítés buildelve; böngészős funkcionális teszt nem futott. Függőség-/lockfile-módosítás nincs. |
| Szintaxis és leltár | A 10 érintett Python-fájl AST-parse-a sikeres. Az eredeti audit és a HC-01 MQTT-monitor változatlan. A 48 tételes sor közül csak HC-03 státusza változott; a prioritások változatlanok. |

A backend összesen **160 kiválasztott különálló tesztet** jelent (148 unit + 12 PostgreSQL), ezen felül futott a külön MQTT+DB forgatókönyv. A crash-próbák kivételinjektálást, megszakított hívást és új service-példányt használtak; teljes Gunicorn-/host-újraindítás vagy valódi szelepmotor nem szerepelt a tesztben. A combined próba stop-várakozása csak a laborban 0,1/2 s volt; a megmaradó backoff lejáratát ott kizárólag a teszt-DB-ben siettettük. Ezek nem üzemi késleltetési mérések.

A unit-harness első összeállításakor a mentett előállapot fixture-je átírta az importútvonalat, és régi modult töltött be. A harness import-sorrendjének javítása után a fenti végső 148 teszt a jelenlegi forráson futott sikeresen; emiatt termékkód nem változott.

Tartós tesztforrások a projektben vannak. A tényleges védett futás és eredmények:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/hc03-repair/check_unit.py
/tmp/hc03-repair/unit-results.log
/tmp/hc03-repair/unit-results.json
/tmp/hc03-repair/check_postgres.py
/tmp/hc03-repair/postgres-results.log
/tmp/hc03-repair/check_mqtt_postgres.py
/tmp/hc03-repair/mqtt-postgres-results.log
/tmp/hc03-repair/frontend-results.log
```

A PostgreSQL-teszt külön engedélyezése `HC03_TEST_POSTGRES=1`; a teszt URL-je kizárólag `127.0.0.1` és `hc03_recovery_test` adatbázis lehet. Ezt csak izolált tesztkörnyezetben szabad futtatni. A DB/broker `--network none`, a kliensek ugyanazon elzárt konténerhálózati névtérben, hostport és éles `.env`/adat-/Docker-socket mount nélkül futottak; a projektforrás read-only volt. Erőforráskorlátos, eldobható konténereket használtunk. A frontend saját `/tmp` másolatában kapta meg a rögzített függőségeket; a teszt/build hálózat nélkül futott. Éles image építése vagy telepítése nem történt.

#### Nyitott függőségek, bevezetés és rollback

- **HC-04:** továbbra sincs atomi start-foglalás/aktív egyediség, többprocesszes parancstulajdonlás vagy a két új indítás közötti DB-verseny lezárása. Az egypéldányos backend megtartandó. A kétkapcsolatos recovery-teszt ezt nem helyettesíti.
- **HC-08:** hiányzó event/plan/execution nem keletkezik utólag, az auditlánc folytathatósága és a rejtett klímaküldés nem változott. A meglévő pilot-/audit-/történeti eredményeket nem írjuk át. A teljes F4 ezért nincs lezárva; napi egyszeri start és teljes auditlánc-crash-mátrix továbbra is a HC-04/08 feladata.
- **F2/F3, HC-05/09:** a HC-01 frissességi védelmére és HC-02 külön safety szálára építünk. A generikus transporteredmény és a többi safety-domain retry-ja továbbra is nyitott, ezért a teljes F2/F3 lezárását ez nem igazolja.
- **HC-13:** egy blokkoló DB-hívás, folyamatban lévő publikálás vagy zárási várakozás késleltetheti a következő safety callbacket. Teljes I/O-határidő, worker-életjel és garantált fizikai stop-idő nincs újonnan bizonyítva.
- **Éles bevezetés előtt:** aktuális visszaállítható mentés/release-azonosság, az aktív/történeti sorok és esetleges duplikátumok felmérése, felügyelt fizikai zárás/failsafe próba és DB-/broker-kiesésből visszatérési mérés szükséges. Az éles sorok állapotát ebben a munkában nem olvastuk vagy módosítottuk; a határok kezdeti konfigurációs értékek.
- **Rollback:** a recovery-modul, service, startup/app-wiring és settings együtt állítandó vissza, szabályozott processzleállítással. DB-migráció nincs, a tartós JSON megőrzendő. A régi kód ismeri a `stop_failed` státuszt, de nem adja ezt az indítási tiltást/helyreállítást, ezért downgrade előtt a bizonytalan fizikai műveleteket egyeztetni és a függő sessionöket rendezni kell. Nyitott/bizonytalan művelet mellett automatikus kód-visszaváltás vagy OPEN-replay nem megfelelő; adatot törlő rollback nem szükséges.

Csak HC-03 kapott új státuszt. A korábbi bejegyzések megállapításai a bejegyzéskori történeti állapotot rögzítik; az aktuális összesítés és a REPAIR-003 jelzi a most elkészült helyreállítást.


### REPAIR-004 — HC-04: közös, atomi DB-foglalás minden HC-indításra

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-04. Áttekintve a C./HC-04 megállapítás, az élő DB-indexekről szóló kiegészítés, az L.3 valódi kétkapcsolatos reprodukciója, a kapcsolódó HC-02/03/08 és az F4 előfeltételei, ellenőrzései, rollbackje. A HC-01–03 eddigi javításaira építünk. Más auditpont javítása nem indult.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. Az F4 foglalási része elkészült; a teljes F4 HC-08 nélkül továbbra is nyitott. Éles telepítés és fizikai próba nem történt.
- **Előállapot:** 7 meglévő fájl másolata és SHA-256 leltára `/tmp/hc04-repair/before/`, illetve `before-sha256.json` alatt; 3 új Python-fájl. A leltár érintett fájlokra vonatkozik, nem teljes mentés vagy Git-commit. Az eredeti audit változatlan.

#### Mi változott és miért?

| Fájl | Módosítás |
|---|---|
| `infra/backend/irrigation_admission.py` (új) | Egy közös, rövid READ COMMITTED tranzakció kezeli a session-tábla zárolását, az aktív/bizonytalan sorok ismételt ellenőrzését és a `starting` beszúrást. Ütemezett indításnál az esedékesség újraellenőrzése és a napi jelző is ugyanebbe a tranzakcióba tartozik. |
| `infra/backend/irrigation_service.py` | A kézi, V2 és megmaradt legacy HC-indítás egyaránt a közös foglalót használja. A vesztes kérés nem publikál és nem ír sikeres végrehajtást; kézi kérésnél `409` az eredmény. Az API nem használhatja a fizikai megfigyeléseknek fenntartott `physical_manual` eredetet. A legacy ágnál is a DB-előkészítés előtt rögzített stop-generáció érvényesül. |
| `infra/backend/app.py` | A foglaló friss, dictionary-row DB-kapcsolatot nyitó függvényt kap; a service explicit függőségként kapja a tranzakciós foglalást. Hiányzó függőség esetén nincs régi, nem atomi fallback. |
| `infra/backend/tests/test_irrigation_admission.py` (új) | 6 új unit-teszt: vesztes kézi/scheduler, hiányzó függőség, bizonytalan DB-eredmény, fenntartott eredet és normalizált foglalási adatok. |
| `infra/backend/tests/test_irrigation_admission_postgres.py` (új) | 22 explicit engedélyezett, izolált valódi SQL-teszt: versenyek, tranzakcióhatárok, napi egyszeriség, recovery-kapcsolat, fizikai kézi megfigyelés és lock-timeout. |
| `infra/backend/tests/test_irrigation_service.py` | A meglévő service-tesztek külön fake admissiont kapnak; a tényleges tranzakciót a PostgreSQL-kör ellenőrzi. A fixture a futás közben cserélt DB-helyettesítőket is követi. |
| `docs/ai/irrigation-domain.md`, `scheduler-domain.md`, `irrigation-scenarios.md` | Foglalási szerződés, napi jelző, commit/OPEN sorrend, hibák, fizikai kézi kivétel és megmaradt függőségek dokumentálása. |
| `AUDIT_REPAIR.md` | HC-04 státusza és jelen ellenőrzési jegyzőkönyv. |

Összesen **10 projektfájl** érintett. Nincs DB-migráció, egyedi index, trigger, új táblamező vagy runtime DDL. A választott megoldás az auditban javasolt egyetlen tranzakciós lock; nem alkalmazunk csak memóriabeli start-lockot vagy önmagában versenyző `INSERT … WHERE NOT EXISTS` feltételt.

#### Foglalási és fizikai végrehajtási szerződés

1. A service szezon-/recovery-kapui és előzetes SELECT-je megmaradnak, de az üres előzetes SELECT nem ad indítási jogosultságot. A közös foglaló új DB-kapcsolatot használ, és explicit READ COMMITTED tranzakcióban dolgozik.
2. `SHARE ROW EXCLUSIVE` táblazár sorosítja az egymást követő HC-foglalásokat, valamint rövid időre az ingest/stop/recovery session-írásaival is összehangolja az ellenőrzést. A sima olvasók tovább futhatnak. A lock megszerzése UTÁNI külön SELECT friss pillanatképet kap; egy előbb induló, közben commitolt fizikai kézi megfigyelés sem marad láthatatlan.
3. Bármely `starting`, `running` vagy `stop_failed` session elutasítja az új HC-foglalást. Az aktív fizikai kézi megfigyelés is blokkol, de a foglaló nem minősíti át, nem zárja le és nem hozza létre `physical_manual` sorokat. Az ingest később továbbra is rögzítheti a fizikai kézi aktivitást egy HC-session mellett; ez nem második HC-parancstulajdonos.
4. Ütemezett indításnál az aktív flag, hét napja, időablak és az adott DB-helyi napi jelző ismételt feltétele az UPDATE-nak. A `last_started_on` és a session INSERT közös commitja miatt a vesztes kérés nem fogyaszt napot, az insert/commit hibája mindkettőt visszagörgeti. A már előkészített, későn folytatódó kérés az első session lezárása után sem ismétli meg ugyanazt a napi schedule-t.
5. Sikeres commit után tér vissza a session a hívóhoz; csak ezután jöhet OPEN, fizikai visszaigazolás és a meglévő auditírás. MQTT-várakozás alatt nincs foglalási DB-tranzakció/táblazár. Ha a commit megtörtént, de a válasz elveszett, a hívás kivételt ad és nem küld OPEN-t. A DB-ben megmaradt `starting` sort a HC-03 close-only recovery rendezi; automatikus újranyitás nincs.
6. A foglalási tranzakción belül `lock_timeout=2s`, `statement_timeout=5s` érvényes; a beállítások a tranzakcióval megszűnnek. Lock-/DB-hiba kifelé kivétel, nem hamis siker vagy automatikus újraküldés. Ezek SQL-határok, nem igazolt teljes kapcsolódási/transport/fizikai határidők. A stop publikálását nem tesszük a foglalási tranzakció részévé.
7. A HC-02 stop-generáció és a HC-03 feltételes végállapotírás megmaradt: egy foglalás és OPEN közötti kézi stop érvényteleníti a régi indítást. A már lezárt session nem léphet vissza `running` állapotba a kézi/V2 útvonalon.

A meglévő duplikátumokat a javítás **nem törli vagy supersedeli**: aktív/bizonytalan sor esetén további foglalást tilt. Nem egyedi DB-megszorítás készült, ezért minden HC-író köteles ezt a tranzakciós kaput használni. Az összes jelenlegi HC-session INSERT átkerült ide; az ingest fizikai megfigyelésírója változatlan. Kézi SQL-írás vagy régi és új vezérlő párhuzamos futtatása nem kap általános egyediségvédelmet.

#### Tényleges ellenőrzések és eredmények

| Ellenőrzés | Eredmény és bizonyítási határ |
|---|---|
| Mentett HC-04 előállapot, valódi DB | **Reprodukálva: 200/200, két session és két fake OPEN.** A mentett tényleges `start_manual()`/`running_session()` külön PostgreSQL-kapcsolatokon futott; barrier csak az aktív-session olvasások visszaadása előtt. Fizikai visszaigazolás helyettesített. |
| Kapcsolódó unit-/regressziós kör | **154 különálló teszt, 0 hiba, 0 kihagyás**: a korábbi 148 és 6 új HC-04 unit-teszt. A hálózati connect/bind, processzindítás és `/tmp`-n kívüli írás audit hookkal tiltott. Nem teljes kiadási regresszió. |
| Valódi PostgreSQL-kör | **34 különálló teszt, 0 hiba, 0 kihagyás**: 22 HC-04 + a korábbi 12 HC-03 SQL-regresszió. A session és schedule eredeti DDL-je, tényleges foglalási/service/recovery SQL, külön kapcsolatok. |
| Párhuzamos indítások | Ugyanazon service két kézi kérése, két külön service-példány, kézi+V2, V2+V2 azonos és külön schedule-lel, valamint legacy+V2: egyetlen foglalás és fake OPEN; két kézi kérésnél `200/409`. A közös reservation elé tett barrier biztosította, hogy mindkét előkészítés az üres állapotból induljon. |
| Tranzakció-/crash-határok | Schedule UPDATE utáni INSERT-hiba és végső commit-hiba: mindkét változás rollback, OPEN nélkül. Commit után elveszett válasz, illetve foglalás és publish közötti szimulált processzhalál: megmaradt `starting`, új start tiltott, OPEN-replay nélkül. OPEN után hibás running-commit: a foglalás bizonytalanul megmaradt. A HC-03 külön regressziói a zárás előtti/utáni DB-határokat is ellenőrizték. |
| Start+stop és lock-élettartam | Commitolt `starting` és későbbi OPEN közé ékelt kézi stop sikeresen zárt; az előző start `blocked_by=stop_request`, késő OPEN és visszaéledő sor nélkül. A publish/confirmation belépésekor egy másik DB-kapcsolat NOWAIT módban megszerezte ugyanazt a táblazárat és írta a sessiont: a foglalási tranzakció már lezárult. |
| Fizikai kézi megkülönböztetés | Aktív fizikai sor változatlanul tilt; fizikai megfigyelés HC mellett továbbra is beszúrható. Külön próbában befejezetlen fizikai író blokkolta a táblazárat (`pg_stat_activity` Lock-várakozás igazolva), majd commitja után az új SELECT észlelte és elutasította az HC-indítást. |
| Napi jelző és hiba utáni visszatérés | Lezárt első session után ugyanazon napi előkészített schedule nem foglal újra. Előkészítés alatt inaktivált schedule nem indul. Lock-timeout nem enged OPEN-t; a lock megszűnése után új kérés foglalhat. A megmaradt duplikátumok változatlanok és blokkolnak. A korábbi HC-03 nap-/DST-ből megmaradt sorának recovery-tesztje is sikeres; teljes időzóna-/DST-ütemezési tesztmátrix nem futott. |
| Valódi MQTT + PostgreSQL együtt | **2/2 sikeres eset:** kézi+kézi és kézi+V2 verseny, a tényleges foglaló/service/MQTT-monitor/publisher láncon. Mindkét esetben 1 session, `OPEN → CLOSE`, friss Nano-mintával igazolt nyitás/zárás, végállapot `stopped`. Kézi+kézi válaszok `200/409`; a másik esetben a scheduler nyert, a kézi kérés `409`. |
| Szintaxis és változtatási határ | A 6 módosított/új Python-fájl AST-parse-a sikeres. Az eredeti audit, a HC-01 MQTT-monitor, a HC-02 startup-worker és a HC-03 recovery-modul változatlan. A 48 tétel közül csak HC-04 státusza változott, prioritások változatlanok. Frontend nem változott; új frontendteszt/build nem futott. |

A backend összesen **188 kiválasztott különálló teszt** (154 unit + 34 SQL); a két külön MQTT+DB eset ezen felül értendő. A brokeres próbában a Nano/szelepmotor helyett MQTT-tesztaktuátor adott 1,2 s után új állapotmintát. Az OPEN/CLOSE várakozások csak a laborban 0,1/2 s, egy próbálkozással futottak; üzemi teljesítmény-/stop-határidő-mérés, HTTP-/böngészőpróba, teljes worker-/host-restart vagy hardverpróba nem történt. A V2 auditírás és rule-engine helyettesített; a hiányzó auditlánc nem került javításra.

Az új unit-tesztek első összeállításakor egy közvetlenül importált TestCase ismét felderítette a már meglévő teszteket; az egyedi azonosítókat ellenőrző harness ezt futtatás előtt megállította. Modulimporttal javítottuk. A legacy tesztfixture hiányzó `reason` mezőjét is pótoltuk; emiatt termékkód nem változott. A fenti eredmények a végső sikeres körökből származnak.

A tartós tesztek a projektben vannak; a tényleges védett futás és bizonyítékok:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -B /tmp/hc04-repair/check_unit.py
/tmp/hc04-repair/unit-results.log
/tmp/hc04-repair/unit-results.json
/tmp/hc04-repair/check_postgres.py
/tmp/hc04-repair/postgres-results.log
/tmp/hc04-repair/check_mqtt_postgres.py
/tmp/hc04-repair/mqtt-postgres-results.log
/tmp/hc04-repair/before-sha256.json
/tmp/hc04-repair/after-sha256.json
/tmp/hc04-repair/repair.diff
```

A PostgreSQL-modul explicit engedélye `HC04_TEST_POSTGRES=1`, URL-je kizárólag `127.0.0.1` és `hc04_admission_test` lehet; csak eldobható teszt-DB-ben futtatható. A HC-03 regressziók ugyanazon izolált szerver külön `hc03_recovery_test` adatbázisában futottak. A PostgreSQL `postgres:16` (`f992505e18f1`) és Mosquitto (`077fe4ff4c49`) konténere nem kapott külső hálózatot/hostportot, a backend tesztkliensek (`02eeec7c5304`) ugyanazon elzárt névtérben futottak. Források read-only, DB-adatok tmpfs-en; éles `.env`, DB-adatkönyvtár, Docker-socket és LAN-/eszközelérés nélkül. A konténerek erőforráskorlátosak és eldobhatók; éles image/konfiguráció nem módosult. PgBouncer-kiesést vagy teljes alkalmazásindítást ezzel a körrel nem teszteltünk.

#### Nyitott függőségek, bevezetés és rollback

- **HC-08:** event/plan/execution folytathatóság, hiányzó auditlánc és rejtett klímaküldés változatlan. A foglalás elutasítása nem készít vagy javít auditláncot. A pilot skip/audit ág meglévő viselkedése megmaradt. A teljes F4 ezért még nincs lezárva.
- **HC-20:** a megmaradt legacy start közös foglalót kapott, hogy ne kerülhesse meg az HC-04 kaput; elérhetetlenségének megszüntetése, eltávolítása és saját régi eredménykönyvelésének takarítása nem része ennek a javításnak. A tényleges scheduler továbbra is V2-t hív.
- **HC-02/03 és HC-13:** a DB-foglalás külön kapcsolatok között is sorosít, de a parancssorrend, a recovery inicializálása és a worker-tulajdonlás nem többprocesszes szerződés. Továbbra is egy aktív backend tartandó. A rövid táblazár session-írókat is késleltethet; teljes I/O-/fizikai határidő továbbra sincs bizonyítva.
- **HC-05/09:** más safety-domain retry-ja és a generikus MQTT transporteredmény változatlan. Az F2/F3 teljes lezárását ez a módosítás nem jelenti.
- **Éles bevezetés előtt:** aktuális visszaállítható mentés/release-azonosság, aktív és történeti sorok/duplikátumok felmérése, esetleges bizonytalan fizikai műveletek egyeztetése, a tényleges runtime DB-jog és poolbeállítás ellenőrzése, valamint felügyelt valós start/stop és lock-/DB-/broker-kiesésből visszatérési próba szükséges. Ebben a körben az éles sorokat nem olvastuk vagy módosítottuk; nincs automatikus adattisztítás. A teljes F4 éjfél/DST és auditlánc-crash ellenőrzései még külön bevezetési bizonyítékot igényelnek.
- **Rollback:** service, admission-modul és app-wiring együtt állítandó vissza, szabályozott processzleállítással; régi és új vezérlő nem futhat párhuzamosan. DB-migráció/DDL nincs, a sessionök, napi jelzők és recovery-JSON megőrzendők. Függő/bizonytalan fizikai művelet előtt állapotegyeztetés kell; a visszaállítás nem indokol OPEN-replayt vagy napi jelző automatikus nullázását. A régi kód visszahozza az indítási versenyhelyzetet.

Csak HC-04 kapott új státuszt. A korábbi bejegyzések történeti állapotot rögzítenek; a jelenlegi összesítés és REPAIR-004 jelzi az elkészült foglalási javítást. Az eredeti auditdokumentumot nem módosítottuk.


### REPAIR-005 — HC-48: helyes About eszköz-/entitásdarabszám

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-48. Áttekintve a C./HC-48 bizonyítéka, az érintett backend SQL és frontend mezők, valamint az F9 előfeltételei, ellenőrzése és rollbackje. Más auditpontot nem javítottunk.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben; éles telepítés nem történt.
- **Előállapot:** a két meglévő érintett fájl másolata és SHA-256 leltára `/tmp/hc48-repair/before/`, illetve `before-sha256.json` alatt. Ez nem teljes mentés vagy Git-commit.

**Módosítás:** az `infra/backend/system_status_service.py` `about_inventory_stats()` eszköztípus-lekérdezésében `count(distinct d.id)` és `count(distinct e.id)` számol eszközt/entitást. A metrikajoin többé nem sokszorozza meg a két értéket, és az eszközszám szerinti rendezés is a helyes darabszámot használja. A termékkód változása két SQL-sor; új fájl az `infra/backend/tests/test_about_inventory_postgres.py`, továbbá ez a nyilvántartás módosult.

**Megőrzött szerződés:** a típuslista aktív eszközöket és azok összes entitását tartalmazza, az inaktív entitásokat is; ezt most nem változtattuk meg. A külön metrikatípus-lista továbbra is aktív entitások engedélyezett metrikáit számolja. A DISTINCT metrikahalmaz, képességek, példák, helyek, globális kártyák és az API-mezők megmaradtak. A frontend a két mezőt közvetlenül jeleníti meg, módosítása nem szükséges. Séma-/adatmigráció nincs.

**Tényleges ellenőrzés:** ugyanazon szintetikus adatsoron, valódi PostgreSQL-en a mentett SQL 1 eszköz/3 entitás helyett 6/6-ot és hibás sorrendet adott. A javított tényleges `about_inventory_stats()` **3 célzott tesztje sikeres, 0 hiba, 0 kihagyás**:

- Több metrika, több entitás, két azonos típusú eszköz, metrika nélküli entitás és entitás nélküli eszköz helyes számlálása; metrika-/képességhalmaz megőrzése.
- Aktív/inaktív eszközök és entitások, engedélyezett/letiltott metrikák; külön globális és metrikaösszesítések változatlan eredménye.
- Eszközszám szerinti rendezés: két kevés metrikájú eszköz megelőzi az egy sokmetrikás eszközt.

Mindhárom payloadépítés PostgreSQL `READ ONLY` tranzakcióban, változatlanul **4 SELECT-tel** futott. A payload fő kulcsai változatlanok. A két érintett Python-fájl AST-parse-a sikeres; a mentett és új termékkód összevetése kizárólag a két számláló változását mutatja. Az eredeti audit lenyomata változatlan; a 48 tételből csak HC-48 státusza változott.

A tartós teszt explicit engedélye `HC48_TEST_POSTGRES=1`; URL-je csak `127.0.0.1` és `hc48_inventory_test` lehet. A tényleges futás `/tmp/hc48-repair/check_postgres.py`, eredménye `postgres-results.log` és `postgres-results.json`; az előtte/utána leltár és diff ugyanitt található. A próba eldobható PostgreSQL 16 (`f992505e18f1`) és backend-kliens (`02eeec7c5304`) konténerben, elzárt hálózati névtérben, hostport és éles `.env`/adat/Docker-socket mount nélkül futott. A forrás read-only; a DB tmpfs-en, minimális szintetikus leltársémával készült. Ez nem teljes restore-, böngészős vagy kiadási regresszió; frontendbuild és éles teljesítménymérés nem futott.

**Függőségek és korlátok:** az F9 többi pontja (HC-10/14/21/22/40), a teljes történeti aggregáció költsége, cache/frissesség és frontend GET-életciklus változatlan. A négy lekérdezés és read-only payload igazolt; p95/WAL és friss restore/karbantartott DB összehasonlítás nem történt. Ezeket nem állítjuk HC-48 számlálási bizonyítékának, és a teljes F9 nincs lezárva. A meglévő auditbizonyíték a visszatöltött mentésen készült; most éles DB-lekérdezés nem történt. Bevezetés előtt az aktuális release-/mentésazonosság és az About megjelenítés ellenőrzendő.

**Rollback:** a két SQL-kifejezés visszaállítása vagy a korábbi backendkiadás visszatelepítése; adat-/sémaváltoztatás nem szükséges. A régi számlálási hiba ezzel visszatér. Csak HC-48 kapott új státuszt, az eredeti audit változatlan.


### REPAIR-006 — HC-05: hibás sikerjelző helyett korlátos safety-retry

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-05. Áttekintve a C./HC-05 és kapcsolódó HC-06/09 bizonyítékai, az F0/F2 előfeltételei és ellenőrzései, a publisher szerződése, az ingest entity-state időbélyeg-/retained-meta írása és a meglévő 043-as konfiguráció. Más auditpont javítása nem indult.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. A teljes F2 HC-09 nélkül továbbra is nyitott; fizikai bevezetés nem történt.
- **Előállapot:** 6 meglévő érintett fájl másolata és SHA-256 leltára `/tmp/hc05-repair/before/`, illetve `before-sha256.json` alatt. Ez érintettfájl-leltár, nem teljes mentés vagy Git-commit. Egy új tesztfájl készült.

#### Módosítás és viselkedés

| Fájl | Változás |
|---|---|
| `infra/backend/combustion_safety_service.py` | Célonkénti `SafetyCommand`: kísérlet, publisher-visszatérés és későbbi megfigyelés külön állapot. Monoton órás, korlátos retry az extractor OFF-ra és a jelzőlámpára; ki nem igazolt teljesülésnél a sikeres publish sem állítja le idő előtt a retry-t. A flag-ek csak sikeres visszatérés vagy megfelelő lámpamegfigyelés alapján változnak. Az extractor stop a lámpa és az eseményírás előtt fut, külön actuation-hibahatárokkal. |
| `infra/backend/settings.py`, `infra/backend/app.py` | Konfigurálható `COMBUSTION_COMMAND_RETRY_SECONDS=10`, `COMBUSTION_COMMAND_MAX_ATTEMPTS=3`, `COMBUSTION_OBSERVATION_MAX_AGE_SECONDS=60`; pozitív/véges határok és 1..100 egész keret validálása. Wiring a meglévő service-hez. |
| `infra/backend/tests/test_combustion_safety_delivery.py` (új) | 21 célzott regressziós teszt: sikertelen/elfogadott/kivételes publish, várakozás és kimerülés, késő megfigyelés, fan újraindulás, stale/retained/future/hiányzó minta, lámpa ON/OFF/pulzus/preview, külön hibahatárok, target és konfiguráció. |
| `infra/backend/tests/test_combustion_safety_service.py` | A fixture opcionális időbélyeget és retained-metát, szöveg-/JSON-értéket is ad a valódi megfigyelési útvonalhoz; a korábbi tesztek megmaradtak. |
| `docs/ai/climate-domain.md` | Az új küldési/megfigyelési szerződés, lámpapulzus, konfiguráció és megmaradt függőségek. |
| `AUDIT_REPAIR.md` | HC-05 státusza és ez a jegyzőkönyv. |

Összesen 7 projektfájl érintett. DB-séma/-adat migráció és frontendmódosítás nincs. A meglévő entity-state lekérdezés a már létező `meta` oszlopot is olvassa; az ingest és a közös MQTT-publisher változatlan.

- Egy adott cél/parancs epizód alapból legfeljebb **3 kísérlet**, köztük legalább **10 s** monoton várakozás; az első azonnali. Nincs sleep/retry-ciklus a tickben. Az ismétlés csak akkor történik, ha az adott policy továbbra is kéri a parancsot; a tartós latch önmagában nem írja át a meglévő current-danger/auto-shutdown szabályt. Az utolsó küldési hely alapból t=20 s körül válik esedékessé, plusz polling/I/O-késés; ez nem fizikai stop-határidő.
- `shutdown_sent` azt jelenti, hogy az adott epizódban a publisher legalább egyszer sikert jelzett. Sikertelen első küldésnél hamis marad; nem szolgál többé a további próbák tiltására. Az `indicator_on` elfogadott kimeneti állapot vagy megfelelő lámpamegfigyelés, nem önálló fizikai nyugta. Sikertelen OFF nem állítja hamisra.
- Az additív `actuation.shutdown` és `actuation.indicator` payload tartalmazza a célt, kívánt parancsot, próbálkozásszámot, utolsó publish-eredményt, `published`/`observed` mezőket, megfigyelési időt, következő várakozást és a keretkimerülés `requires_attention` jelzését. A tick válaszában az aktuális küldési eredmény szerepel.
- A megfigyelés az első kísérlet UTÁNI, nem jövőbeli, legfeljebb 60 s korú entity-state minta lehet, explicit `meta.retained=false` mellett. Extractornál véges numerikus `power` vagy `power_w <= fan_off_w`; lámpa OFF-nál `switch_state=false`; ON-nál kapcsolóállapot, fényerő és xy szín (0,01 tolerancia) együtt szükséges. Explicit offline lámpa nem igazolhat. Hiányzó meta/időbélyeg nem bizonyít teljesülést.
- A korábban megfigyelt OFF utáni új, friss magas fan-teljesítmény új leállítási epizódot enged. Pusztán a fan-debounce/GET megváltozása nem nullázza a keretet. Kimerülés után nincs néma újrapróbálás; egy későbbi megfelelő OFF-megfigyelés még küldés nélkül rendezheti az állapotot. A cél vagy kívánt parancs változása új epizód. Az inaktív/célját vesztett extractor nem kap régi topicra retry-t.
- A lámpapulzus ON hibája sem enged korlátlanul eltolódó pulzust: a határidő után külön, korlátos OFF-takarítás következik. Új pulzus a megfigyelt OFF-ot várja; hiányzó feedback tehát szüneteltetheti a pulzusokat. A folyamatos piros elsőbbséget élvez. A preview meglévő véges mintája megmaradt, de a flag-jei sem állnak sikerre sikertelen publish után.

#### Tényleges ellenőrzés

| Ellenőrzés | Eredmény / korlát |
|---|---|
| Mentett hiba reprodukciója | Két tényleges régi `_shutdown()` hívás mindig `(False, ...)` publisherrel: egy küldés, mégis `shutdown_sent=True`; a második hívás elmaradt. Fake I/O. |
| Kapcsolódó unit-/regressziós kör | **175 különálló teszt, 0 hiba, 0 kihagyás**: az előző 154 és 21 új HC-05 teszt. Fake óra/DB/MQTT; az audit hook tiltja a külső connect/bindot, processzindítást és a `/tmp`-n kívüli írást. Nem teljes release-suite. |
| Ütemezés és megfigyelés | Fake órával igazolt 10 s-os kapu, 3 kísérlet utáni stop, wall-clock ugrástól független retry; false/exception nem siker. Friss alacsony teljesítmény lezár, késő friss magas érték új stopot indít. Kimerült, sikertelen küldés után késő OFF-megfigyelés `observed=true`, `published=false`: a két bizonyíték nem mosódik össze. |
| Hibahatár és lámpa | Lámpa-DB-hiba mellett az extractor OFF megkísérelve; extractorhiba mellett a lámpa tovább működik. Sikertelen lámpa ON/OFF, preview OFF, pulzusvége/új pulzus, piros szintváltások és offline lámpa ellenőrizve. |
| Izolált valódi broker: elérhetetlen végpont→helyreállás | **Sikeres.** Előbb a névtérben nem figyelő 1884-es porton valós connect-hiba; `published=false`, lámpa nincs sikeresnek jelölve. Visszaváltva a futó 1883-as brokerre, a megengedett újrapróbálás tényleges OFF/ON-t küldött és a tesztaktuátor válasza megfigyeléssé vált. Célonként 2 kísérlet, ténylegesen 1 OFF/1 ON. A labor retry 0,2 s; az első tényleges parancs késése 221,81 ms a hibás tick után. Ez nem valódi broker-újraindítás vagy üzemi p95-mérés. |
| Izolált valódi broker: eszközvisszajelzés nélkül | **Sikeres.** A broker befogadott célonként 3 parancsot; a tesztaktuátor visszajelzése kikapcsolva. A negyedik tick nem publikált: 6 parancs összesen, mindkét célon `published=true`, `observed=false`, `requires_attention=true`. Nem lett belőle fizikai siker. |
| Szintaxis és hatókör | Az 5 érintett Python-fájl AST-parse-a sikeres. Az eredeti audit változatlan; csak HC-05 státusza változott. A HC-06 `state_payload()`, `acknowledge()` és konfigurációírás életciklusa megmaradt; a generikus publisher nem változott. |

A brokeres próbában a tényleges service és `MqttClientService` futott, de a DB/ingest és a fizikai készülék fixture/tesztaktuátor volt. Read-only forrásmount, `--network none` broker és ugyanazon névtérben futó kliens, hostport/éles `.env`/DB-/Docker-socket/LAN-/eszközelérés nélkül. Mosquitto image `077fe4ff4c49`, backend-kliens `02eeec7c5304`; erőforráskorlátos, eldobható konténerek. Új éles image nem épült. Frontend-/SQL-/hardverpróba és teljes folyamat-restart nem futott; a default 10 s-os időzítést fake óra ellenőrizte.

Reprodukálható célzott unit-parancs:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=infra/backend python3 -B -m unittest \
  tests.test_combustion_safety_service tests.test_combustion_safety_delivery \
  tests.test_startup_service
```

A tényleges bővebb, védett futás `python3 -B /tmp/hc05-repair/check_unit.py`; `unit-results.log/json`, `check_mqtt.py`, `mqtt-results.log/json`, előtte/utána SHA-256 leltár és `repair.diff` ugyanebben az ideiglenes könyvtárban. A regressziós tesztek tartósan a projektben vannak.

#### Nyitott függőségek, bevezetés és rollback

- **HC-09 / F3:** a közös publisher `True` értéke továbbra sem bizonyít broker-/bridge-/fizikai teljesülést; a `wait_for_publish` általános timeout-szerződése változatlan. Az új `observed` mező szigorúbb helyi, parancs utáni **ingest/DB-megfigyelést** jelent, nem eszközoldali mintakorral vagy parancsazonosítóval igazolt fizikai nyugtát. Egy nem retained, újrapublikált régi eszközminta forráskora ebből nem állapítható meg. A megfigyelés múltbeli bizonyíték, nem tartós online-garancia. A teljes F2/F3 nincs lezárva.
- **HC-06:** a fan-debounce, GET közbeni evaluate, tartós latch és acknowledge/restart szerződés nincs javítva. A parancsmeta-lock nem általános döntési állapotlock. A retry-keret folyamaton belüli; restartkor a meglévő állapothoz hasonlóan újraindul. Egy aktív backend megtartandó. A tartós retry/latch helyreállítás e külön feladathoz kapcsolódik.
- **HC-13:** a tick nem alszik újrapróbálásra, de DB/publish blokkolhat. Teljes connect/transport/worker határidő és garantált fizikai kikapcsolási idő nincs bizonyítva. A lámpa és az eseménynapló hibája az adott kör első stop-kísérletét már nem előzi meg, de egy beragadt művelet későbbi köröket továbbra is késleltethet.
- **Éles bevezetés előtt:** aktuális mentés/release-azonosság, felügyelt valós extractor-/lámpapróba, a valódi mintakor/retained-meta és feedback-ritmus ellenőrzése, valamint a 10 s/3/60 s kezdeti értékek mért késések szerinti véglegesítése szükséges. A kimerülést az additív API jelzi; külön frontendriasztást nem vezettünk be. A rendszer meglévő fizikai riasztóit ez a kiegészítő service nem helyettesíti.
- **Rollback:** combustion service, app-wiring és settings együtt visszaállítandó az előállapotból vagy ismert kiadásból, szabályozott processzleállítással. DB-migráció nincs. A visszaváltás visszahozza a false-publish utáni hibás sikerflag és elnyomott retry kockázatát; függő fizikai állapot mellett előbb állapotegyeztetés szükséges. Éles rendszerhez és adatokhoz ebben a körben nem nyúltunk.

Csak HC-05 kapott új státuszt. A korábbi bejegyzések történeti állapotát nem írtuk át; az aktuális összesítés a mostani állapotot jelzi.


#### HC-05 ismételt ellenőrzés — 2026-10-22

Az ismételt javítási kérésre újra elolvastuk a HC-05 bizonyítékát és az F2 érintett lépését. A REPAIR-006 végső SHA-256 leltárának minden fájlja egyezett az aktuális állapottal; új kódmódosítás nem volt szükséges. A fent dokumentált célzott unit-parancs újrafuttatása: **38 teszt, 0 hiba, 0 kihagyás**. Az injektált extractor-/lámpa-DB hibák naplózása a sikeres teszt része. A korábbi 175-ös kör és két MQTT-próba történeti eredményét nem számoltuk újra; ezeket most nem futtattuk ismét.

A HC-06/09/13 függőségek és az eszközoldali mintakor/parancsazonosság korlátja megmaradt. Más auditpont státusza, termékkód vagy éles rendszer nem változott; csak ez az ellenőrzési bejegyzés került a nyilvántartásba.


### REPAIR-007 — HC-06: worker-owned döntés, tiszta GET és tartós latch

- **Dátum és végrehajtó:** 2026-10-22, Codex.
- **Hatókör:** HC-06. Áttekintve a C./HC-06 bizonyítékai, az F5 előfeltétele/döntési tábla, ellenőrzése és rollbackje, valamint a HC-05 eredménykezelés, HC-09 mintakor és a klímaablak-fogyasztó kapcsolata. Más auditpont nem kapott javítást vagy új státuszt.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben. Az F5 HC-06 része elkészült; F2/F3 és az eszközoldali bizonyítékok nyitott függőségei megmaradtak. Éles telepítés és migrációalkalmazás nem történt.
- **Előállapot:** 9 meglévő fájl másolata és SHA-256 leltára `/tmp/hc06-repair/before/`, illetve `before-sha256.json` alatt. Négy új projektfájl; összesen 13 érintett fájl. Ez nem teljes mentés vagy Git-commit.

#### Módosítások

| Fájl | Változás |
|---|---|
| `infra/backend/combustion_safety_service.py` | A worker az egyetlen automatikus döntési tulajdonos. Nem átfedő tick, közös döntési/ACK lock és külön rövid snapshot-lock; teljes másolat publikálása, monoton kor. A GET és a kompatibilis `evaluate()` kizárólag olvas. Tartós állapot restore/save, explicit ACK és konzervatív hiba-/frissességi szabályok. |
| `infra/backend/combustion_state_store.py` (új) | Runtime latch/CO-előzmény betöltése és revízióhoz kötött, rövid UPDATE; nincs DDL vagy MQTT. |
| `infra/db/058_combustion_safety_runtime.sql` (új) | Additív singleton runtime-tábla: latch, CO-warning, utolsó CO/mintaidő, revision, update/ACK idő. Első telepítéskor reteszelt; újrafuttatáskor a meglévő sor változatlan. Üzleti konfigurációt nem ír. |
| `infra/backend/settings.py`, `infra/backend/app.py` | Kezdeti, konfigurálható `COMBUSTION_INPUT_MAX_AGE_SECONDS=300`, `COMBUSTION_SNAPSHOT_MAX_AGE_SECONDS=5`, pozitív/véges validálással és wiringgal. |
| `infra/backend/tests/test_combustion_safety_state.py` (új) | 26 új unit-/szálas teszt az olvasási szerződésre, frissességre, debounce-ra, latch/ACK/restore hibákra és versenyekre. |
| `infra/backend/tests/test_combustion_safety_state_postgres.py` (új) | 10 explicit engedélyezett valódi SQL-teszt: migráció, CAS, commit/rollback, külön Python-folyamat újraindítása és history. |
| `infra/backend/tests/test_combustion_safety_service.py`, `test_combustion_safety_delivery.py` | A meglévő tesztek worker-ticket, in-memory runtime store-t és explicit mintametadata-fixture-t használnak; a snapshot nem osztozik a konfiguráció mutable referenciáján. A HC-05 elvárásait megtartottuk. |
| `infra/frontend/src/features/home/HomeDashboard.jsx`, `infra/frontend/src/features/admin/HcAdmin.jsx` | Ismeretlen/elavult értékelés jelzése egészséges fallback helyett, értékelési kor és helyreállítási bizonytalanság; a nyugtázás tiltása ismert veszély/bizonytalanság esetén. A backend minden esetben önállóan validál. |
| `docs/ai/climate-domain.md`, `AUDIT_REPAIR.md` | Aktuális szerződés, döntési tábla, bevezetés, korlátok és jelen jegyzőkönyv. |

#### Döntési és tartóssági szerződés

- A worker lépteti a fan-debounce, CO-trend, warning és automatikus latch állapotát. A GET/`last_snapshot`/`evaluate()` nem olvas DB-t, nem publikál, nem ír, nem értékel újra és nem módosítja az időzítést. Az eseményeket a worker olvassa. A snapshot másolat, nem kívülről módosítható belső referencia.
- A worker a teljes döntést az actuation/log I/O előtt publikálja, majd a küldési eredményekkel frissíti. Lassú DB/publish mellett is olvasható a legutóbbi snapshot; a kor nem nullázódik GET-re vagy ACK-ra. 5 s fölött, illetve első értékelés előtt `stale`; egészséges állapotot nem mutat, a latch megmarad. Ismeretlen/stale fan nem adhat klímaablak-kivételt.
- **Pozitív CO/füst/shutdown-küszöb:** régi pozitív bizonyíték is konzervatívan latch-et eredményez. **Törléshez:** friss, ismert, nem retained CO és minden bekötött füstforrás, megfelelő rádióállapot és hibamentes CO szükséges. Hiányzó/öreg/jövőbeli/retained/hibás vagy fault/unknown adat nem törölhet latch-et. Nem bekötött füstforrás opcionális; CO-igazolás ACK-hoz kötelező. A részletes tábla a domain-dokumentációban van.
- Fan-hiszterézis csak friss, véges numerikus mintával, monoton idővel lép. Ismeretlen minta megszakítja a pending intervallumot; nem bizonyít OFF-ot és nem törli a CO-warningot. Régi/retained/offline nyitott ablak nem bizonyít légutánpótlást. CO-trend csak újabb, friss minta alapján lép; a minta ismételt GET-je/tickje nem új emelkedés.
- A worker előbb betölti a runtime sort, a változó latch/warning/CO history-t revíziós UPDATE-tal commitolja az actuation/event előtt. A biztonságos, commitolt állapot folyamat-restart után helyreáll. A séma/sor hiánya és DB-hiba látható bizonytalanság, nem automatikus clear. Nincs runtime DDL. A rövid DB-kiesés alatt észlelt veszély a memóriában pending marad, visszatéréskor újra menthető.
- Az ACK explicit manuális kivétel az automatikus tulajdonlás alól: a workerrel sorosítva, friss helyreállított snapshot és a jelenlegi binding/küszöb/CO/füst újraolvasása mellett működik. Nem értékel újra, nem léptet debounce-ot vagy CO-trendet, és nem küld parancsot. Csak sikeres revíziós commit után jelent clear-t; a worker timestampje megmarad. Veszély/stale/bindingváltozás/ismeretlen input `409`; bizonytalan DB-eredmény nem siker.
- Elveszett ACK-commitválasznál az API hibát jelez és a helyi latch/restore-bizonytalanság megmarad, miközben a DB-ben az engedélyezett ACK akár már commitolódhatott. A worker később újratölti az állapotot. Nem állítjuk, hogy DB és API-válasz atomi.
- A kezdeti 300 s inputkor és 5 s snapshotkor konfigurációs érték, nem igazolt eszközriport-periódus. A forrás továbbra is ingest/DB-időbélyeg; eszközoldali mintakor/parancsazonosság nincs hozzá kitalálva. A HC-05 kísérleti keret és actuation-vezérlés megmaradt, és továbbra is folyamaton belüli. A guard letiltása nem ACK, a `would_level` és a latch megmarad.

#### Tényleges ellenőrzések

| Ellenőrzés | Eredmény és bizonyítási határ |
|---|---|
| Mentett előállapot | Reprodukálva: két GET fan-debounce-ot léptetett; GET veszélyből latch-et írt; új service a latch-et elveszítette. A tényleges mentett osztály, fake adatforrások. |
| Kapcsolódó unit-/regressziós kör | **201 különálló teszt, 0 hiba, 0 kihagyás**: az előző 175 és 26 új HC-06 teszt. Audit hook tiltja a connect/bindot, processzindítást és `/tmp`-n kívüli írást. Kontrollált szálak/Eventek és fake óra. |
| GET és versenyek | Több száz GET nem lépteti a debounce/CO/latch állapotát és nem ír runtime-ot. GET blokkolt actuation közben is befejeződik. Két átfedő tickből csak egy dönt. Párhuzamos ACK megvárja a danger-ticket és elutasul; stale vagy újonnan beérkező veszély/fault/unknown/retained minta sem enged clear-t. A visszaadott snapshot kívülről nem módosítja a belső állapotot. |
| Óra/frissesség | Monoton fan on/off hiszterézis, wall-clock ugrás, megszakadt pending intervallum, stale ablak/fan, új és ismételt CO-minta, későn beérkező minta. A valós idővel futó SQL-kör egy kezdeti hibát feltárt: az értékelés közben érkező mintát a tick-start időhöz mértük. A read/check időre javítva, külön unit-regresszióval a végső kör sikeres. |
| Valódi PostgreSQL | **10 teszt, 0 hiba, 0 kihagyás.** Tényleges új migráció/store SQL, két külön kapcsolat revízióütközése, valódi rollback, commit utáni elveszett válasz, hiányzó séma→visszatérés, ACK/history round-trip, migráció újrafuttatása és változatlan fixture-konfiguráció. Commitolt rövid alarm után külön **új Python-folyamat** tiszta jelenlegi bemenettel is visszaállította a latch-et. Ez nem teljes host/Gunicorn restart. |
| Valódi MQTT, HC-05 regresszió | **2/2 sikeres:** elérhetetlen 1884-es végpont→futó brokerre visszaváltás után OFF/ON, célonként 2 kísérlet és megfelelő megfigyelés; eszközválasz nélkül célonként 3 kísérlet után kimerülés, 6 parancs, nincs hamis megfigyelés. A labor retry 0,2 s; helyreállás utáni első parancs 226,05 ms a hibás tick után. Fake DB/runtime és tesztaktuátor, tényleges publisher; nem broker-restart vagy fizikai mérés. |
| Frontend | **83 mower + 4 AI teszt sikeres**, `npm run build` sikeres. A módosított két megjelenítés buildelve; böngészős funkcionális teszt nem futott. Package-/lockfile-módosítás nincs. |
| Szintaxis/hatókör | A 8 érintett Python-fájl AST-parse-a sikeres. Az eredeti audit, közös MQTT és startup-worker változatlan. A HC-05 retry/actuation metódusai és a konfigurációírás változatlanok; csak HC-06 kapott új státuszt. |

A kiválasztott backendkör összesen **211 különálló teszt** (201 unit + 10 SQL), a két MQTT-eset ezen felül. Ez nem teljes release-suite. Az első fixture-átállításkor egy HC-05 teszt a korábbi mutable config-referenciát módosította; az új másolt snapshot explicit konfigurációját adtuk a tesztnek. Ez nem termékkód-regresszió. A fenti számok a végleges forráson futott sikeres köröket jelölik.

A tesztek tartósan a projektben vannak. A tényleges futás: `/tmp/hc06-repair/check_unit.py`, `check_postgres.py`, `check_mqtt.py`; eredmények `unit-results.log/json`, `postgres-results.log/json`, `mqtt-results.log/json`, `frontend-results.log`; előtte/utána SHA-256 leltár és `repair.diff` ugyanitt. A SQL-modul explicit engedélye `HC06_TEST_POSTGRES=1`, URL-je csak `127.0.0.1` és `hc06_state_test` lehet. Csak eldobható teszt-DB-ben futtatható.

PostgreSQL 16 (`f992505e18f1`), Mosquitto (`077fe4ff4c49`) és backend-kliens (`02eeec7c5304`) elzárt közös hálózati névtérben, hostport, éles `.env`, DB-adatkönyvtár, Docker-socket és LAN-/eszközelérés nélkül futott; forrás read-only, DB tmpfs-en. Node (`fb4cd12c85ee`) saját `/tmp` forrásmásolatban telepített a lockból, teszt/build hálózat nélkül futott. Erőforráskorlátos eldobható konténerek; új éles image nem épült.

#### Függőségek, bevezetés és rollback

- **058-as migráció:** a backend bevezetése előtt külön alkalmazandó, a runtime DB-jogosultság ellenőrzésével. Első telepítéskor a sor szándékosan `latched=true`, mert nincs hiteles korábbi runtime latch; friss, felügyelt ACK szükséges. A migráció ismételt futtatása sem töröl latch-et/history-t és nem változtat üzleti konfigurációt. Éles DB-n nem futtattuk.
- **HC-09 / F2/F3:** generikus MQTT timeout/transporteredmény és eszközoldali mintakor/fizikai korreláció továbbra is nyitott. A frissesség most DB/ingest szintű; nem teljes fizikai nyugta. Teljes F2/F3/F5 bevezetési bizonyítékot nem helyettesít.
- **HC-13 és tartóssági határ:** az ACK a döntési lock mögött DB/publish végére várhat, de GET nem vár erre a lockra. Teljes I/O-/worker-határidő és igazolt fizikai leállási késés nincs. A DB-n még nem commitolt, csak memóriában pending veszély egyidejű processzvesztésnél elveszhet; ehhez nincs külön helyi journal. Commitolt latch/history tartós. A retry-epizódok külön, memóriabeli HC-05 állapotok maradtak. Egy aktív backend szükséges, többprocesszes worker-tulajdonlás nem készült.
- **HC-07 és HC-35/36:** a meglévő üzleti bootstrapok, binding-választás és klíma-folytatás nem változott. A klímaablak-fogyasztó csak a friss, ismert fan bizonyítékából kaphat kivételt; nem rendeztük át a másik domain tulajdonlását.
- **Éles ellenőrzés:** visszaállítható mentés/release-azonosság, a CO/füst/teljesítmény/kontakt riportolási ritmus és meták mérése, a 300/5 s kezdeti határok véglegesítése, felügyelt alarm→restart→ACK, DB-kiesés és valódi extractor/lámpa próba szükséges. A fizikai riasztók továbbra is függetlenek; az éles környezetet ebben a munkában nem olvastuk vagy módosítottuk.
- **Rollback:** a runtime-tábla és adatai megőrzendők; nincs destruktív visszamigráció. Az előző kód nem olvassa a tartós latch-et, ezért aktív/függő/ismeretlen veszély mellett automatikus downgrade tilos: előbb fizikai egyeztetés és hiteles clear, vagy a restore/clear-védelem kompatibilis visszaportolása szükséges. A service/store/settings/wiring és a UI együtt, szabályozott processzleállítással váltható. A régi GET-mellékhatás és restart-latch-vesztés visszatérne.

Csak HC-06 státusza változott. A korábbi naplóbejegyzések a bejegyzéskori történeti állapotot jelölik; az eredeti audit változatlan.


### 2026-10-22 — A jelenlegi auditjavítások élesítésének előkészítése

**Kérés:** minden szükséges előkészítés az élesítéshez; éles migráció, szolgáltatáscsere és ACK nélkül. Ez nem új auditjavítás és nem éles bevezetési jegyzőkönyv. A HC-01–06/HC-48 ellenőrzött státusza és a további 41 nyitott pont változatlan.

**Kiadás:** `backups/releases/hc-audit-20261022-r1`. A teljes jelenlegi backend/frontend forrásból két külön címkézett image készült; a futó két image külön rollback címkét és helyi archívumot kapott. A befagyasztott forrást hashleltár, az image-eket image-ID és archívum-checksum azonosítja. Az eredeti audit változatlan. Új termékkód- vagy függőségmódosítás nem történt.

**Mentés és konfiguráció:** a teljes éles DB-ről read-only `pg_dump -Fc` készült (~154 MiB), privát szerepkörmentéssel. A dump PostgreSQL 16-ra teljes egészében, izolált laborban visszaállt. Az új és régi image-ek helyi archívuma egyenként ~116 MiB. A kiadási Compose-inputok privát pillanatképek. A futó operátori jelszóhash eltér a sima Compose újrarenderelésétől; a release és rollback override a futó értéket őrzi meg, változatlan éles `.env` mellett. Ezt konfigurációszinten és külön, hálózat nélküli Compose-konténerben hash-egyezéssel igazoltuk, titok kiírása nélkül. A migrációs és runtime DB-role azonosságát és a HC sémajogokat csak olvasva ellenőriztük; a superuser szerep megmaradt (HC-39).

| Tényleges ellenőrzés | Eredmény / határ |
|---|---|
| Backend regresszió | **574 különálló teszt, 0 hiba, 0 kihagyás**, a befagyasztott release forráson és új image könyvtáraival. HC-03/04/06/48 és mower PostgreSQL tesztek explicit opt-innel, külön eldobható DB-kben. `evidence/backend-suite.json/log`. |
| Frontend | **83 mower + 4 AI teszt sikeres**, Vite build sikeres a végleges image buildjében. `evidence/frontend-build.log`. Böngészős fizikai kezelői próba nem futott. |
| Image/forrás azonosság | Az új backend image 66 Python/statikus fájlja SHA-256 szerint egyezik a befagyasztott kontextussal. `evidence/backend-image-source.json`. |
| Teljes restore | A teljes custom dump visszaállt, `pg_restore --exit-on-error` sikeres. No-owner/no-privileges laborrestore; a szerepkörök külön mentve, a tényleges runtime és migrációs role azonos. Nem teljes host-restore. |
| 058-as migráció | A DB másolatán kétszer sikeres, 0,049 s összesen; kezdeti latch=true/revízió=0; idempotens; a vizsgált meglévő üzleti adatok változatlanok. Élesen nem futott. |
| HC-07 függőség vizsgálata | A tényleges bootstrap lefutott a visszaállított DB-n; a 17 megnevezett, részben hiányzó táblában a created_at/updated_at mezőket kizárva nincs üzleti értékdiff. `evidence/database-rehearsal.json`, privát before/after snapshotok. Nem teljes katalógusdiff vagy üres DB-s telepítés, HC-07/F7 nincs lezárva. |
| Teljes indulás / HTTP | Valódi Gunicorn/WSGI, safety/scheduler/monitor workerek, laborbroker és Nginx; backend és frontend health 200, DB/MQTT true; HTML és assetek 200; safety GET 200, runtime restored=true, kezdeti latch megmaradt. Labor Nginxben backend DNS helyett loopback. `evidence/http-smoke.json`. Nincs fizikai aktuátor/nyugta/késésmérés. |
| Elszigetelés | A labor DB `--network none`; a társak annak névterében, hostport, éles env/DB-könyvtár/Docker-socket/aktuátorhálózat nélkül. A teszt-DB-k különállók; a mentésből visszaállított másolatra nem futottak destruktív tesztfixture-ök. A labor erőforrásai az ellenőrzés után eltávolítva. |
| Read-only éles preflight | **Integritási hiba nincs**, de az éles kapuk nyitottak: futó physical_manual öntözési sor és elavult CO/füst clear minták. A script 2-es kóddal megáll; nem zár le sort, nem lazít frissességet, nem nyugtáz. `evidence/latest-preflight.json`. |

A teljes tesztindítás elején a labor mountpontjait, eredménykönyvtár-felhasználóját, namespace-tesztfelfedezését, dokumentáció/fixture csatolását és a subprocess PYTHONPATH-ját kellett rendezni. Az első tényleges 574-es kör egy dokumentációs és egy subprocess-import hibát jelzett; a végleges laborinputokkal a teljes kör megismételve hibátlan. A fenti számok a végső sikeres körök, nem külön futások összeadása. Termékkód-javítás ezek miatt nem történt.

**Éles kapuk és függőségek:** a fizikai öntözést/sessiont egyeztetni kell, a kötött CO- és füstforrásoktól friss, valós, nem retained, hibamentes, rádióállapotában is ismert adatok kellenek. A kezdeti 300 s inputhatár marad. Felügyelt váltás, helyi stop, friss Nano online/STATUS/TELE és a tényleges extractor/lámpa ellenőrzése szükséges. Az első runtime sor latch=true: ACK kizárólag az új rendszer friss, veszélymentes állapotának kezelői ellenőrzése után. HC-09/HC-13 fizikai visszajelzés/határidő, HC-07 bootstrap és HC-43 függőségi sérülékenységek továbbra is nyitottak; csomagfrissítés/advisory-újraellenőrzés nem történt.

**Átadott menet:** [DEPLOYMENT_PREP.md](DEPLOYMENT_PREP.md), részletes privát `README.md`; read-only `preflight.py`, rögzített Compose-wrapper, friss váltási DB-mentés, alapértelmezetten csak tervet mutató `migrate058.py`, read-only rollback gate. Az éles `--apply` ág nem futott. A migrációhoz leállított régi backend és friss sikeres preflight/checksumolt dump kell. A downgrade aktív/függő/ismeretlen latch mellett tiltott; nincs down-migráció vagy automatikus teljes DB-restore. A helyi csomag nem került külső szolgáltatásba. A kiadási szkriptek szintaxisa ellenőrzött; az éles mutációs ágak szándékosan nincsenek végrehajtási sikerrel megjelölve.

Az előkészítés végén az éles backend/frontend/postgres konténerazonosító, image és indulási idő a rögzített előállapottal egyezik; az 058 tábla továbbra sincs jelen az éles DB-ben. Éles szolgáltatáscsere, újraindítás, ACK vagy eszközparancs nem történt.


### 2026-10-22 — Éles bevezetés felhasználói kivételekkel, gyors safety-kompatibilis visszaállással

**Engedély:** a felhasználó megerősítette, hogy téli profil van és nincs fizikai öntözés; új CO-/füstadatot jelenleg nem tud biztosítani. Kifejezetten kérte az élesítést és a könnyű visszaállíthatóságot. Ez a szoftverváltás előfeltételeinek dokumentált kivétele, nem a szenzorok frissnek minősítése vagy ACK-engedély.

**Tényleges váltás:** 2026-10-22 20:53:05 CEST. `homecontrol-backend:hc-audit-20261022-r1` és `homecontrol-frontend:hc-audit-20261022-r1`; a konkrét image-ID-k az `evidence/active-deployment.json` fájlban. Friss custom DB-dump és checksum után szabályozott backendleállítás, 058 commit kezdeti latch=true/revízió=0 értékkel, új backend, readiness, új frontend. Kizárólag a backend/frontend szolgáltatást cseréltük; a PostgreSQL konténer ID/indulási ideje változatlan.

**Kivételek:** az éles DB-ből is igazolt `winter` profil mellett manual/scheduled/solar/maintenance capability=false. A `physical_manual` 125-ös running sor érintetlen maradt. A kizárólag elavult, utoljára clear, nem retained CO-/füstminták hiánya elfogadott a váltáshoz; új pozitív/hibás/ismeretlen érték, más aktív session vagy integritási hiba nem kapott felmentést. A nyers `latest-preflight.json` továbbra is hibátlan integritást, de nyitott live-blockereket mutat; nem hamisítottuk sikeresre. Az ettől különálló `cutover-review.json` friss, konkrét engedélyezett kivételt és a változatlan safety feltételeket rögzíti. A `migrate058.py --apply-with-reviewed-exceptions` csak ehhez illeszkedő friss preflighttal, mentéssel és leállított régi backenddel futott.

**Gyors visszaállás:** külön `homecontrol-backend:fallback-hc-audit-20261022-r1` image készült az előző, ténylegesen futó backendből. Az eredeti appban csak a safety provider konfigurációja változott, és a release változatlan `combustion_safety_service.py` / `combustion_state_store.py` moduljai kerültek rá. A HC-05/06 retry/frissesség/tartós latch/ACK védelem megmarad; a többi alkalmazáskód régi. A frontend a HC-06 állapotjelzés miatt a jelenlegi verzió marad. Ez kompatibilis tartalék, nem állítjuk, hogy minden módosítás nélküli teljes régi verzió. Az eredeti image-ek külön megőrizve, tartós latch-et figyelmen kívül hagyó downgrade-re nem váltunk automatikusan.

**Visszaállás ellenőrzése:** a tartalék image tényleges safety moduljaival **64 különálló unit/SQL teszt, 0 hiba, 0 kihagyás**. A mentésből visszaállított izolált DB-n valódi teljes WSGI **tartalék → új → tartalék** indulási kör: minden lépés health=true, runtime restored=true/revision=0, latched=true, a régi inputok nem váltak frissé. Egyetlen backend futott egyszerre; fizikai eszközkapcsolat nem volt. Eredmények: `fallback-tests.log`, `fallback-roundtrip.json`, külön indulási logok. A labor és saját volume-ja eltávolítva.

**Éles ellenőrzések:** `evidence/deployment-verification.json` és `deployment-business-invariants.json`:

- A backend/frontend image-ID egyezik a rögzített kiadással; DB/MQTT health=true, frontend health/HTML/assetek/API 200.
- A safety worker GET-ek között önállóan frissül, a snapshot nem stale, nincs evaluation/persistence error, a tartós állapot helyreállt. Runtime latched=true, acknowledged_at=null; ACK nem történt. A CO/füst input-health=false, fan=true: az elavult szenzoradat nem lett egészségesnek minősítve. Danger=false a legutóbbi tárolt értékek alapján, friss clear bizonyíték nincs.
- A téli capability-tiltások, safety config, scheduler config, bindingok és aktív sessionek a váltás előtti adatokkal egyeznek. Nincs kézi SQL-es sessionlezárás vagy frissességi határnövelés.
- A piros jelzés MQTT-küldései sikeresek, de a kívánt állapot teljes megfigyelési feltétele nem igazolt: 3/3 próbálkozás, observed=false, requires_attention=true. Ez látható fennmaradó eszköz-visszaigazolási korlát; nem fizikai sikerállítás. Extractor shutdown parancs nem volt szükséges (`shutdown=null`). Kézi alarm/ACK/aktuátorpróbát nem indítottunk; a normál új safety worker jelzőlámpa-parancsokat már küldött.
- A futó hitelesítés megmaradt. Az `infra/docker-compose.override.yml` az aktív, privát release override-ra mutat; a normál Compose renderelt image-jei és operátori hitelesítése egyezik a futó konténerrel. Váltáskor a script ezt az aktív pointert is frissíti.

**Átadás:** `switch_mode.py fallback --apply` vagy `release --apply`; egyik sem ACK-ol, nem állít vissza DB-t és nem töröl runtime-ot. `verify_deployment.py` a read-only utóellenőrzés. A részletes parancsok a [DEPLOYMENT_PREP.md](DEPLOYMENT_PREP.md) és a csomag `DEPLOYMENT.md` fájljában vannak. A régi előkészítési checksum leltár megőrzendő történeti bizonyíték; a bevezetési segédscript/métaadat/dokumentáció szándékos változásai után új teljes checksum leltár készül. Az eredeti HC audit és a 41 nyitott pont változatlan; más auditjavítás nem történt.


### 2026-10-22 21:03:52 CEST — Újabb read-only éles ellenőrzés a védelem kezelői kikapcsolása után

**Kérés:** a felhasználó a szenzorok másnapi tesztjéig kikapcsolva hagyja a védelmet; az eddigi javítások élesítésének és működésének újbóli ellenőrzését kérte. Nem indítottunk ACK-ot, tesztet, kézi eszközparancsot, újraindítást vagy kiadásváltást. A napló helyi frissítésén kívül nem módosítottunk termékkódot vagy éles beállítást.

**Eredmény:** a `hc-audit-20261022-r1` backend/frontend image-ek futnak, a HC-01–06 és HC-48 kiadás aktív, az 058 runtime-tábla és tartós retesz jelen van. A 233 fájlos eredeti forrásleltárban nincs eltérés. A ténylegesen futó backend 66 Python/statikus fájlja egyezik a tesztelt, befagyasztott buildforrással. A korábbi 574 backend- és 83+4 frontendteszt hibátlan eredményét újra ellenőriztük; a forrás változatlan, a teljes suite-ot most nem futtattuk újra. A tartalék image korábbi 64 tesztje és a teljes tartalék→új→tartalék WSGI-próba megőrzött, sikeres bizonyíték.

A most ténylegesen futtatott `verify_deployment.py` ismét sikeres: proxyn át web/asset/API/health 200, DB/MQTT true, GET-ek között előrehaladó worker-snapshot, nincs evaluation/persistence hiba, a runtime helyreállt. Az aktív normál Compose-konfiguráció és az operátori hitelesítés egyezik a futóval; a DB-konténer változatlan. A backend és frontend restart-számlálója 0. Az élesítés óta megvizsgált backendlogban nincs traceback/error/worker-timeout/500/503 találat. Ez az ellenőrzött backendlogra vonatkozik, nem minden eszköz és szolgáltatás hibamentességének állítása.

**Jelenlegi állapot:** config.enabled=false, level=disabled, latched=true, acknowledged_at=null. A téli öntözési tiltások megmaradtak. A CO/smoke input-health továbbra is false, fan=true; a nyugtázáshoz még nincs friss clear bizonyíték. A letiltás miatti jelző OFF parancs állapotát az új rendszer friss telemetria alapján megfigyeltnek jelzi: 1 kísérlet, observed=true, requires_attention=false. Ez az OFF állapot megfigyelése, nem a korábbi piros szín/fényerő visszaigazolásának utólagos igazolása. A parancsot a felhasználó korábbi kikapcsolására reagáló normál worker küldte, az ellenőrzés nem kezdeményezett új kézi parancsot.

Bizonyíték: `evidence/deployment-verification.json`, `evidence/recheck-runtime.json`, privát `recheck-backend.log`. A holnapi szenzorteszt után a HC-ban ténylegesen megjelenő friss, hibamentes és már veszélymentes CO-/füst-/rádióadatokat kell ellenőrizni; a tesztgomb megnyomását önmagában nem tekintjük új MQTT-/DB-minta bizonyítékának. Az ellenőrzés nem igazolja a kikapcsolt védelem aktív veszélykezelését; az továbbra is a kezelő döntése szerint kikapcsolt. Más auditpont státusza nem változott.


### REPAIR-008 — HC-07: explicit migráció és adatátírás nélküli érintett startup

- **Dátum:** 2026-10-22.
- **Elolvasott bizonyíték:** HC-07, az ott hivatkozott pilot upsert-ágak, scheduler mód-/klímaszabály-migráció, `app.py` bootstrap és `wsgi.py`; **F0 és F7**, kapcsolódó F7a/HC-39 és HC-38. A futó éles kiadást a felhasználó kérésére nem cseréltük le.
- **Hatókör:** kizárólag HC-07. A startup során elérhető szezon- és jegyzet-backfill is ugyanebbe a migrációs határba került; más auditpont státusza nem változott.

#### Módosítás

| Fájl | Eredmény |
|---|---|
| `infra/backend/schema_service.py`, `scheduler_service.py` | Pilot/scheduler ensure: lockkal cache-elt read-only kompatibilitásellenőrzés. Nincs inventory-upsert, módátállítás, történeti schedule-másolás/törlés vagy új default-sor startupkor. A külön power-wall DDL helper megmaradt. |
| `infra/backend/season_profile_service.py`, `admin_service.py` | A szezon-/jegyzetséma és legacy backfill kikerült a startup/lazy ensure útból. Csak ellenőrzés maradt; explicit kezelői módosító API-k változatlanok. |
| `infra/backend/app.py` | Read callback átadása a schema service-nek; a szezonkompatibilitás is a workerek előtti bootstrap része. Az ütemező/audit/publish és safety kód más része változatlan. |
| `infra/backend/startup_schema_contract.py`, `startup_schema_manifest.py` (új) | Naplózott verzió/checksum, ismeretlen verzió, 12 érintett tábla szükséges oszlopai/típusai, konfigurációs sorok, aktív szezonkapcsolat és idempotenciaindex olvasási ellenőrzése. Hiba nem állít ready flag-et, nem javít DB-t és megállítja az indulást. |
| `infra/backend/migrate_hc07.py` (új) | Alapértelmezetten read-only terv. Explicit apply allowlisttel, fájl-/journal-checksummal, tranzakciós advisory lockkal, 5 s lock-/60 s statement-timeouttal, atomikus SQL+journal köteggel. Nem importál alkalmazást/workert, nem publikál MQTT-re. |
| `infra/db/059_hc07_startup_schema.sql` (új) | Az érintett, korábban lazy DDL verziózott megfelelője. Nem ír inventoryt, scheduler-módot vagy schedule-adatot. A régi módok DB-szinten megőrizhetők, de az alkalmazás explicit választást követel, automatikus execute-all konverzió nincs. |
| `infra/db/060_hc07_legacy_data.sql` (új) | Egyszeri explicit legacy szezonreprezentáció-váltás meglévő capability-választások/aktív profil megőrzésével; hiányzó/üres jegyzetstátusz pótlása. Az érvényes `done=true,status=open` állapotot sem írja át. |
| `infra/db/seeds/hc07_initial.sql` (új) | Külön kért, egyszer naplózott, insert-only kezdeti inventory/config/seven disabled climate defaults. Meglévő telepítésen az első seed visszautasított; már lefutott seed nem hozza vissza az utóbb törölt defaultokat. |
| `infra/backend/tests/test_schema_service.py`, `test_scheduler_service.py`, `test_startup_schema_postgres.py` (új) | Read-only startup/cache és valódi SQL regressziók, köztük elveszett commitválasz utáni biztonságos journal-alapú újrafuttatás. |
| `docs/hc07-schema-migrations.md`, két `docs/ai` leírás, `AUDIT_REPAIR.md`, `DEPLOYMENT_PREP.md` | Új forrásszerződés, bevezetési/restore sorrend, függőségek, bizonyítási határok és a változatlan éles kiadás megkülönböztetése. |

#### Döntések és invariánsok

- A runtime check nem tekinti az eszköz/metrika kikapcsolását, átnevezését vagy egy default-sor törlését javítandó hibának. A kezdeti inventory nincs minden induláskor újra seedelve. A szükséges singleton/szezonkapcsolat hiánya látható hiba, nem önkényes helyreállítás.
- A scheduler `legacy/v2_shadow/v2_plan_only/unified_shadow` módja megmarad a DB-ben; a backend támogatott V2 módot kér, és addig nem indul. Így nem emeli a végrehajtási jogosultságot. Explicit kezelői konfigurációs API-aliasok nem részei ennek a javításnak.
- A meglévő klímaszabályok identitása/értékei megmaradnak; a korábbi "Climate morning comfort" másolás/törlés és canonical schedule újraseedelés nincs az upgrade/startup útban. A régi sorok esetleges későbbi konszolidációja külön adatdöntés.
- A `hc.startup_schema_migration` a verzió/checksum/időpont/role igazolása. A fájlok önmagukban, kézi psql-futtatással nem pótolják a runner naplóját. Ismeretlen/eltérő bejegyzést nem ír felül. A `001–058` SQL-fájlokat nem futtatja újra; a `042 CONCURRENTLY` kizárt ebből a tranzakciós runnerből.
- Az apply commitolhat kompatibilis sémát úgy is, hogy egy legacy mód/hiányzó konfiguráció miatt `ready=false`, exit 2 marad. Ez külön jelzett állapot. Elveszett commitválasznál az eredmény bizonytalan: a journal ellenőrizendő, nincs hamis "biztos rollback" állítás.

#### Tényleges ellenőrzések

| Ellenőrzés | Eredmény és határ |
|---|---|
| Eredeti SQL reprodukció | A mentett eredeti pilot/scheduler SQL eldobható fixture-DB-n: 2 kikapcsolt device, 2 entity, 9 metric és 9 entity-metric szabály visszaaktiválódott; `v2_shadow` → `v2_execute_all`; 1 történeti klímasor törlődött. `before-reproduction.json`. |
| Teljes backend regresszió | **592 különálló teszt, 0 hiba, 0 kihagyás**, ebből **17 új HC-07 valódi PostgreSQL-eset** és egy új unit-eset. A korábbi 574 teszt is a végleges forráson futott; nem külön futások számainak összege. `suite-results.json/log`. |
| Valódi SQL | Friss domain + explicit seed; read-only terv/check; jogosan törölt/kikapcsolt sorok és időbélyegeik megőrzése; legacy mód/schedule megőrzése; seedtiltás meglévő DB-n; checksum/fájlhiány/ismeretlen verzió; oszloptípus/index drift; megszakítás utáni rollback/resume; két konkurens migrátor egyszeri apply; commitolt, elveszett válasz utáni idempotens replay. Dedikált `hc07_schema_test`. |
| Teljes régi mentés restore/upgrade | A váltás előtti, konzisztens teljes dump izolált PostgreSQL 16-ra visszaállítva. A hiányzó journalnál a bootstrap írás nélkül megállt. 059/060 apply és ismétlés sikeres, a 17 vizsgált üzleti tábla adatai az upgrade előttivel pontosan egyeztek. `restore-results.json`, privát business/catalog snapshotok. |
| Kézzel módosított adat + restart | A teljes DB-másolaton kikapcsolt/átnevezett inventory, egyedi metrikapolicy, választott scheduler-mód, történeti és egyedi klímaszabály, valamint szándékos nyitott jegyzetállapot. Két bootstrap, köztük új Python-folyamat, megőrizte a sorokat és időbélyegeket; teljes startup-katalógus diff nincs az explicit migráció utáni állapothoz képest. |
| Strukturális katalógusdiff | Az aktuális dump upgrade-jének eltérései: 4 journaloszlop, journal-PK/check/index, és a legacy értékeket megőrző scheduler mode-check cseréje. Meglévő oszlop/üzleti adat törlés nincs. A saját függvénydefiníciók és triggerengedélyezések változatlanok, a letiltott presence-triggerek nem aktiválódtak. Nem HC-38 alapséma-rekonstrukció. |
| Teljes WSGI/HTTP próba | Az új forrás explicit Gunicorn `--chdir` útvonallal indult a migrált klónon, saját laborbrokerrel. Health 200, DB/MQTT true; season-profiles, notes, scheduler/state és combustion-safety/state 200. A HC-06 runtime helyreállt, latched=true. A pre-058 dumphoz az 058 előfeltételt külön, csak a klónon pótoltuk. Normál laborworker-parancsok kizárólag az üres laborbrokerre mentek. |
| Éles állapot / izoláció | Az éles backend/frontend/postgres ID, image, indulási idő és restart-számláló a mentett előállapottal egyezik. A HC-07 journal élesen nincs; guard.enabled=false, latched=true, acknowledged_at=null megmaradt. A labor `--network none` DB-névterű, hostport/éles env/DB-volume/Docker-socket/LAN nélkül; a saját konténerek és volume eltávolítva. |
| Frontend / eredeti audit | Frontend- és függőségmódosítás nincs, ezért frontendteszt/build most nem ismétlődött. Az eredeti HC audit SHA-256-ja változatlan. |

A kezdeti restore-próba új Python-folyamata a változatlan alapimage `/app` modulját választotta; a teszt észlelte a régi adatátírást. Az új importútvonalat ezután kifejezetten rögzítettük és ellenőriztük. Egy ismétlés a még futó restore-ral átfedett, ezért csak a restore sikeres befejezése után, tiszta DB-n ismételt próba kapott sikeres minősítést. A staging csak olvasható, privát fájljaihoz a teljes WSGI labor megfelelő uid-del indult. Ezek labor/orkesztrációs hibák voltak, nem termékkód-javítások; az éles rendszer egyikhez sem kapcsolódott. A fenti eredmények a végső sikeres körökre vonatkoznak.

#### Függőségek, bevezetés és rollback

- **Nem élesítettük.** A most futó `r1` és annak tartalék image-e változatlan. A HC-07 forrás csak explicit 059/060 runner és külön verziózott kiadás után indítható. A működő éles stacken most ne fusson `up --build` a módosított munkafából.
- **HC-38 / F7:** a teljes üres core adatbázis történeti sémája/függvényei/triggerállapotai nincsenek pótolva. A runner hiányzó core tábláknál írás nélkül megáll. Friss érintett domainhez kompatibilis core baseline, teljes helyreállításhoz dump és célzott migrációs sorrend szükséges. A teljes új VM/üres DB F7-bizonyítása nem része a lezárt HC-07 résznek.
- **F6 / restore:** a meglévő általános launcher nem lett automatikus migrátorrá átírva; a régi mentés → explicit szükséges migrációk → új backend sorrendet a dokumentáció adja. Nem módosítottuk a kiválasztási, útvonal-, unit-/timer- vagy mentésaudit többi hibáját.
- **HC-39:** a migrációs és runtime role szétválasztása külön nyitott feladat. A checkek read-only SQL-ek, a runner DDL-/journal-jogot igényel; globális role-/SQL Lab-szűkítés nem készült.
- **HC-08/HC-13/HC-21:** audit/publish/worker I/O, határidők és read-model költség nem változott. Más lazy DDL helper és üzemi runtime/összesítő-írás megmaradt; nem állítjuk, hogy a teljes WSGI indulás minden workere írásmentes.
- **Rollback:** nincs down-migráció vagy journal-/adatürítés. Az előző kód a régi startup-átírást is visszahozza, ezért HC-07 utáni későbbi deploy rollbackjét üzleti snapshot/kompatibilis régi bootstrap mellett kell tervezni. A korábbi r1-hez készített HC-05/06 tartalék nem válik ettől HC-07-kompatibilis tartalékká.

Tartós használati leírás: [hc07-schema-migrations.md](docs/hc07-schema-migrations.md). A tényleges ellenőrzési scriptek, mentett előállapot, diffek és eredmények `/tmp/hc07-repair` alatt vannak. A HC-07 kódellenőrzés státusza **Ellenőrzött**; éles bevezetés nincs, a további 40 pont státusza változatlan.

### REPAIR-009 — HC-38: verziózott, üres adatbázisból rekonstruálható HC alapséma

- **Dátum:** 2026-10-22, Europe/Budapest.
- **Elolvasott bizonyíték:** HC-38, K.1–K.2 élő objektumleltár és triggerállapotok, L restore-határa, **F7**, kapcsolódó F0/F6/F7a; `001_irrigation_admin.sql`, a jelenlegi schema-service/HC-07 runner és a restore launcher DB-restore/start lépése. A meglévő HC-07 munkafaváltozásokat megőriztük.
- **Hatókör:** kizárólag HC-38. Új, explicit friss telepítési/tesztút; az éles adatbázis, a futó r1, a restore launcher és más auditpont javítása nem változott.

**Módosítás**

1. `infra/db/baselines/hc_r1_058_v1.sql`: az éles r1/058 HC sémájából ellenőrzött, verziózott snapshot. **52 tábla, 7 nézet, 16 sequence, 2 enum, 171 constraint, 122 HC-index, 5 függvény, 5 saját trigger**. Mind a nyolc hiányzó core tábla teljes definíciója szerepel. A három aktív trigger aktív, a két `trg_touch_presence_*` letiltott marad; függvényviselkedést nem javítottunk át.
2. Nincs üzleti sor, aktuális sequence-számláló, owner/ACL/role vagy titok. Egyetlen telephelyhez kötött DDL-defaultot semlegesítettünk: az új `soil_sensor_topic_base` default üres szöveg. Az élő default és soradat nem változott. Ez a deklarált strukturális eltérés látható marad az összevetésben. A `public` recorder táblák más alkalmazás sémája; nem kerültek a HC baseline-ba.
3. `migrate_hc38.py`: alapértelmezett read-only terv, külön `--verify`, explicit `--apply`; PostgreSQL 16, SQL- és referencia-checksum allowlist. Apply csak friss DB-n, teljes tranzakcióban, az 059/060 runnerével közös advisory lockkal és időkorlátokkal; utólagos katalógusegyezés és `hc.schema_baseline` verzió-/checksum-napló. Meglévő/hiányos/naplózatlan HC sémát nem ír felül és nem fogad örökbe. Saját változatlan baseline ismétlése no-op; checksum/journal/drift hiba nem javítódik automatikusan.
4. `baseline_contract.py` és verziózott `.catalog.json`: strukturális ellenőrzés az oszlopokra, constraint-ekre, indexállapotra, enumokra, függvényekre, triggerengedélyezésekre, nézetekre, relation opciókra és sequence-definíció/tulajdonosi kötésre, OID/soradat/owner/ACL nélkül. Egyetlen pontosan megadott, szemantikailag azonos AND-zárójelezést normalizálunk a történeti mower image-checkben; általános default-/kifejezéseltérést nem fedünk el.
5. `tests/test_baseline_postgres.py`: **19 új valódi PostgreSQL-eset**, explicit opt-in, dedikált localhost DB és a tényleges DB-név ellenőrzése minden törlés előtt. A baseline nem kerül alkalmazásindulásba. A régi `001–058` fájlok és a HC-07 migrátor/manifest checksumjai változatlanok.
6. [HC-38 telepítési leírás](docs/hc38-database-baseline.md), HC-07 függőségi leírás és `DEPLOYMENT_PREP.md` frissítése. Friss telepítés: baseline → külön kijelölt 058 fail-safe runtime inicializálás → 059/060 → csak külön kért, felülvizsgált kezdeti domainseed → kezelői konfiguráció → backend. Meglévő dump: teljes sikeres restore → célzott hiányzó migráció → 059/060, kezdeti seed és baseline apply nélkül.

**Ellenőrzés és eredmény**

A részletes, privát bizonyítékok helye `/tmp/hc38-repair` (0700); a tartós regresszió és használati szerződés a forrásban szerepel.

| Ellenőrzés | Eredmény |
|---|---|
| Teljes backend regresszió | **611 különálló teszt, 0 failure, 0 error, 0 skip** a végleges forráson; ebből 19 új HC-38 SQL-eset. A korábbi 592 teszt is ugyanebben a futásban szerepel. `suite-results.json/log`. |
| Üres PG16 → baseline | A teljes referencia-katalógussal egyező szerkezet; mind az 52 üzleti tábla üres, csak a baseline-napló kap metaadatsort; nincs telepített extra extension. `test_full_catalog_and_no_business_rows_or_extensions`. |
| Élő struktúra összevetése | Read-only élő katalógus és frissen létrehozott baseline: kizárólag a dokumentált soil-topic default semlegesítése érdemi eltérés. A mower CHECK ismert pg_dump/reparse zárójelezése pontosan normalizált. Az összes többi vizsgált kategória egyezik. `live-catalog.json`, `live-baseline-diff.json`, verziózott referencia és a végleges katalógusteszt. |
| Üresből teljes HC alkalmazásséma | Baseline → kijelölt 058 inicializálás → 059/060 és explicit HC-07 seed; readiness=true. Kezelői mód/szezon/jegyzet megmaradt bootstrap és új Python-folyamat után; runtime katalógus nem változott, függvények/triggerek azonosak. `fresh-results.json`, `fresh-migration-diff.json`. |
| Trigger-/mintabeírási szerződés | Valós measurement/state num/bool/text/json elfogadás, hibás típus és tartomány elutasítás, state-update validálás; történeti laza/ismeretlen metrikaág megőrzése. Enum, sequence, PK/unique/FK és outbox default/delete szemantika ellenőrzött. A két presence-touch trigger D maradt tényleges ingest után is. `refresh_presence` és updated-at működik; `tg_touch_presence` csak temp teszttáblán vizsgált, eredeti triggerek aktiválása nélkül. |
| Idempotencia, sérülés és megszakítás | Két párhuzamos telepítő egy baseline-t naplóz. Replay nem ír üzleti adatot/sequence-et. Naplózatlan vagy részleges HC séma, idegen user-objektum, checksum/napló/drift hiba visszautasított. Injektált SQL-hiba és hibás referencia a teljes új sémát rollbackeli; ezután újrapróbálható. |
| Régi teljes dump upgrade | A pre-cutover teljes dump saját PG16 DB-be restore-olva; **pg_restore exit 0 megvárva**, majd csak a hiányzó 058 és 059/060. Baseline apply visszautasított; a restore katalógusa is csak a soil-defaultban tér el a baseline-tól. **17 megnevezett üzleti tábla pontos soradata megmaradt**, egyedi tiltás/átnevezés/mód/jegyzet új folyamat után is megmaradt; újraapply no-op; függvények és triggerek változatlanok. `restore-exit.txt`, `restore-results.json/log`, `restore-baseline-diff.json`. |
| Valódi WSGI/HTTP, friss DB | Az új forrású Gunicorn és saját MQTT az üresből felépített labor-DB-vel: health (DB/MQTT true), season-profiles, notes, scheduler/state, combustion-safety/state mind 200. Kezdeti safety latch=true, persistence.restored=true, evaluation_error nélkül. `wsgi-smoke.json`, `wsgi-results.log`. Nem fizikai szenzor-/aktuátorpróba. |
| Éles változatlanság / izoláció | Backend/frontend/postgres konténer-ID, image, indulási idő és restart-számláló egyezik az előállapottal. Nincs éles HC-07/38 journal; enabled=false, latched=true, acknowledged_at=null és irrigation winter megmaradt. Labor: network none / ugyanannak a DB-nek hálózati névtere, hostport/éles env/volume/socket/LAN nélkül. `live-before/after.json`, `live-state-after.json`, `lab-isolation.json`, `lab-cleanup.json`. |

**Függőségek, határ, rollback**

- A HC-07 korábbi HC-38 core-baseline függőségét ez a javítás a friss DB útjára feloldja. Mindkét helyi javítás továbbra is **nem élesített**. A meglévő éles DB upgrade-jéhez baseline nem kell és nem alkalmazható; explicit 059/060 és külön kiadás kell.
- A baseline nem helyreállított inventory vagy teljes metrikakatalógus. A külön HC-07 kezdeti seed telephelyi inventoryt is tartalmaz; használata tudatos döntés. Az üres soil-topic konfigurálandó, a korábbi runtime fallbackhez nem nyúltunk. Nem tekintjük egy új helyszín szenzorait/bindingjait ettől ellenőrzöttnek.
- **HC-39 / F7a:** role/ACL szűkítés és SQL Lab külön kapcsolat változatlanul nyitott. Nincs automatikus superuser-másolás, role-csere vagy jogosultságcsökkentés. Más lazy DDL-k, HC-08 és minden további auditpont változatlan.
- **F0/F6/F7 operatív határ:** a mentés tényleges DB-visszaállítása és üres HC-DB→alkalmazás próbája megtörtént, teljes új VM/host/HA-telepítés és restore-launcher automatizálás nem. A `public` HA recorder saját sémája nem HC-rekonstrukciós feladat. A történeti `042 CONCURRENTLY` nem került tranzakciós replay-be; a baseline a kész indexdefiníciót tartalmazza. A régi `001–058` készlet tömeges újrajátszása tilos a baseline után.
- Az F7 előfeltételeként szereplő **F6 mentésrefaktor (HC-19/25/30/42) továbbra is nyitott**; most egy kiválasztott meglévő teljes dump DB-restore-ja bizonyított. E pontokhoz, a közös mentési lockhoz vagy időzítőkhöz nem nyúltunk.
- **Rollback:** nincs down-migráció vagy meglévő DB-ürítés. Az új baseline hibája tranzakciósan visszagörgethető, működő rendszerhez a külön dump/restore út és mentett előállapot marad. Az r1 image/override és safety-kompatibilis tartalék változatlan. A korábbi HC-07 kódrollback-korlátok továbbra is érvényesek.

A HC-38 kódellenőrzési státusza **Ellenőrzött**; összesen 9 ellenőrzött, 39 nyitott pont. A korábbi REPAIR-008 HC-38-hiányra vonatkozó történeti állítását ez a bejegyzés és a kapcsolt új leírás váltja fel, a korábbi bizonyítékot nem írtuk át.

### REPAIR-010 — HC-06 kiegészítés: szunnyadó szenzor és rádiós jelenlét

- **Dátum:** 2026-10-23, Europe/Budapest.
- **Kezelői pontosítás:** a CO- és füstérzékelő szunnyadó, eseményvezérelt; új riasztási adat nélkül is lehet igazolt rádiós jelenlét. A CO akár fél évig változatlan maradhat. A rádiós jelenlétet és az utolsó jelzést külön kell kezelni.
- **Kiinduló éles bizonyíték:** az r1-ben 300 s-os, közös safety inputkorhatár fut. 19:09-kor a CO utolsó mentett értéke 10:53:44 (0 ppm, alarm=false, fault=false), a füsté 17:12:33 (alarm=false); rádiós lastSeen 17:55:29 / 18:12:42, mindkettő online. A worker friss, danger=false, de latched=true és input_health.co/smoke=false. ACK nem történt. A rádiós idő és a riasztási mintakor két külön bizonyíték.
- **Feltárt illesztési hiba:** az új HC-06 frissességi szabályt nem hangoltuk össze a szunnyadó szenzorokkal és az ingest állapot-/történetritkításával. A `smoke` változása hiányzott az azonnal írt metrikák közül; numerikus CO-változást deadband/min-interval is kiszűrhetett. A futó ingest forrásának hash-e a vizsgált forrással egyezett. Az előtte próbában 3 új backend-eset, illetve az ingest két tesztjének 17 alesete hibázott; a hiba laborban reprodukált.
- **Hatókör:** a HC-06 követelményének célzott kiegészítése és közvetlen ingest-függősége. Más auditpontot nem zártunk le, HC-07/38 forrásait/migrációit nem írtuk át. Az éles stacket és a reteszt nem módosítottuk.

**Módosítás**

1. `CombustionSafetyService._recorded_event`: a CO-/füstesemény érvényessége nincs 300 s-hoz kötve; ismert érték, véges nem jövőbeli időbélyeg és explicit retained=false továbbra is szükséges. `_clear_inputs` a tartós utolsó jelzést **igazolt rádiós jelenléttel együtt** fogadja el. Hiányzó/invalid/retained/future jelzés, offline/ismeretlen rádió és CO fault továbbra is blokkolja az ACK-ot. A jelenlét nem gyárt clear értéket és nem ír át időbélyeget.
2. Az új numerikus CO-esemény időbélyeg alapján egyszer dolgozható fel, nem ismétlődő tickenként. A pozitív riasztás, tartós latch, worker-owned döntés és tiszta GET megmaradt. Tisztulás és rádiós visszatérés nem automatikus ACK.
3. A folyamatos elszívóteljesítmény-/nyitásadat 300 s-os, a parancsmegfigyelés külön és a worker snapshot 5 s-os frissessége változatlan. A Zigbee jelenlét meglévő `lastSeen` / 6 órás szabályát nem tágítottuk.
4. Ingest `STATE_CHANGE_KEYS`: `carbon_monoxide_value/co/co_ppm`, `smoke/smoke_alarm/fire/alarm` változásai a min-interval/deadband előtt íródnak. Riasztás és tisztulás, illetve kis CO-küszöbátlépés is átjut. A már kezelt CO alarm/fault ág változatlan. Tiltott szabály, más metrika és változatlan érték továbbra is ritkítható; nincs mesterséges frissítés/heartbeatből gyártott mérés.
5. Az admin UI magyarázza az eseményvezérelt működést, megjeleníti a CO-/füst rádiós észlelés idejét és az input miatti ACK-tiltás feltételét. A gomb a szerver állapotát követi; kliensoldali feloldás nincs. A szerződés és az AI domainleírás frissült.

**Ellenőrzés**

| Próba | Eredmény |
|---|---|
| Teljes backend | **617 különálló teszt, 0 failure/error/skip**, a korábbi 611 esettel és 6 új szunnyadó-szenzor esettel egy futásban; a régi PG auditkörök is bekapcsolva. `suite-results.json/log`. |
| Ingest unit + PG | **8 sikeres teszt**: 4 új safety unit, 3 korábbi floodteszt és 1 új PostgreSQL-integráció; 0 hiba/kihagyás. `ingest-integration.log`. |
| Hosszú csend / elérhetőség | Féléves, ismert clear jelzés online rádiónál elfogadott; eredeti időbélyeg nem frissül. Rádió nélkül/ismeretlen rádiónál mindkét szenzor külön blokkol. Hiányzó/retained/future/hibás jelzés és fault nem nyugtázható. Aktív vagy újonnan érkező riasztás reteszel; clear után külön ACK kell. |
| Valós ingest → DB → worker | Üres labor-DB baseline-ból; a tényleges ingest függvények írják az állapotot és a történetet. Régi clear + online → labor-ACK; smoke false→true → tartós latch/ACK-tiltás; true→false → latch megmarad; rádiókiesés → ACK-tiltás; visszatérés → kézi ACK. Numerikus 19,9→20,1 ppm nagyobb deadband/min-interval ellenére mentődik és danger-t okoz. Nem fut broker, nincs tényleges publish. |
| Éles minták offline újrajátszása | A csak olvasva mentett 19:09-es éles pillanatfelvétel régi, clear CO-/füstértékeivel az új input_health mindkettőnél true; a latch magától megmarad, memóriabeli ACK engedett. **Network none, nincs éles DB/ACK/publish.** `offline-snapshot-replay.json`. |
| Frontend | **83 mower + 4 AI = 87 sikeres teszt**, Vite production build sikeres, külön `hc06-sleeping-frontend-check` buildimage. Nem az éles frontend image. A hideg offline npm cache miatt a végső build a változatlan lockfájlhoz tartozó csomagletöltést használta; dependency-verziót nem módosítottunk. `frontend-build.log`. |
| Éles változatlanság | A backend és ingest továbbra is a javítás előtti forráshash-t futtatja; r1 backend/frontend kiadás változatlan, újraindítás/éles ACK/migráció nem történt. `live-source-check.json`, `live-container-state.json`, `live-state-after.json`. A saját labor DB/tesztkonténerek és kötete eltávolítva. |

**Függőségek és bevezetés**

- **Nincs élesítve.** A r1-ben a nyugtázási korlát és a korábbi ingest-szűrés még fennáll. A javítás backend + ingest + frontend kiadás, DB-migráció nélkül. Az r1 fagyasztott forrására célzott külön release kell; a munkafa HC-07/38 refaktorja nem kerülhet bele automatikusan. A jelenlegi stacken ne fusson a munkafából általános `up --build`.
- A worker a rendes tickben olvassa az elfogadott állapotot; nincs új tartós eseménysor vagy garantált végponttól végpontig határidő. HC-08/09/11/13/33, a batch/reconnect hibahatárok és más auditpontok változatlanok. A rádiós jelenlét tényleges időzítését továbbra is a Zigbee bizonyítéka adja, nem a szenzor mintáinak kitalált periodikussága.
- **Rollback:** a kód visszaállítása nem törölheti a tartós reteszt/ACK-ot vagy a DB-adatot. A r1 kódja a korábbi korlátot és szűrést visszahozná; ezt egy későbbi release visszaállási tervében külön jelezni kell. Nem történt automatikus éles küszöbemelés, kikapcsolás vagy nyugtázás.

Tartós szerződés: [hc06-sleeping-sensors.md](docs/hc06-sleeping-sensors.md). Privát bizonyíték: `/tmp/hc06-sleeping-repair` és az előzmény `/tmp/hc-sensor-diagnosis-20261023`. Az eredeti audit változatlan; továbbra is **9 ellenőrzött, 39 nyitott auditpont**.

#### REPAIR-010 bevezetési kiegészítés — 2026-10-23 20:51:59 CEST

A felhasználó kifejezett „élesítsd” kérésére a célzott javítás **élesítve**,
kiadás: **hc-sleeping-20261023-r2**. Ez felváltja a fenti korábbi „nincs élesítve”
állapotot. A forrás az r1 fagyasztott kiadása, egy backendmodul-, egy ingestmodul-
és egy admin UI-forrásmódosítással; a HC-07/38 kódja és migrációja nem került be.

A bevezetési reconnect-próba további szükséges feltételt igazolt: azonos retained
visszajátszás nem írhatja át az ismert állapot metadata-ját retained=true-ra;
retained clear nem törölhet pozitív riasztást. Pozitív retained alarm/emelkedés
viszont konzervatívan kezelendő. A cache az eredeti retained jelölést is visszatölti,
és azonos értékű élő megerősítést átenged a korábbi retained/unknown állapot helyett.
Az éles ingestre induláskor beérkező brokerreplay így nem teszi újra
nyugtázhatatlanná a már ismert, veszélymentes, rádión elérhető szenzort.
Ez nem kiterjesztett batch/reconnect refaktor vagy más auditpont lezárása.

| Ellenőrzés | Bevezetési eredmény |
|---|---|
| Tényleges kiadási backend | **580 különálló teszt**, 0 failure/error/skip az r1 + safety patch forráson. A korábbi 617 a HC-07/38-at is tartalmazó munkafa köre volt; a számok nem összeadandók. |
| Tényleges ingest | **13 teszt**, 0 hiba/kihagyás: 9 safety unit + 3 flood + 1 valós PostgreSQL-integráció, retained replay/positive/clear/live-confirmation esetekkel. |
| Tényleges frontend | **87 teszt és production build** az r1 + admin patchen. A kiszolgált admin chunk hash-e egyezik az ellenőrzött builddel. |
| Friss teljes DB-mentés / restore | Privát `rollback/pre-cutover.dump` + SHA-256; saját PG16-ba `pg_restore` exit 0 megvárva. Régi és új három image külön archívumban, pontos ID-k rögzítve. |
| Valódi r2 → r1 → r2 | Saját broker/ingest/WSGI a visszaállított DB-vel, hálózati izolációban. Első r2 indulás: régi CO-/füstrekord retained replay mellett pontosan megmaradt, mindkét input elfogadott. 16 tábla kezelői értékei és latch minden váltáskor megmaradtak. Kizárólag laborban élő megerősítés + kézi API-ACK, utána új r2 folyamatban is megmaradó oldott latch. |
| Éles átadás | Backend/ingest/frontend pontos r2 image-je fut. Health DB/MQTT true, web/API/assets 200, worker snapshot halad, ingest heartbeat friss. CO/smoke/fan input_health=true, danger=false, latched=true, acknowledged_at=null. **Éles ACK nem történt.** |
| Konfiguráció / infrastruktúra | Kezelői beállítások és hitelesítési környezet változatlan; normalizált UTC-összevetés. Csak created_at/updated_at és a HC-40 ismert latest_decision diagnosztikája kizárt. PostgreSQL és broker nem indult újra. A HC-07/38 modulok hiánya a futó backendben külön igazolt. |

Az első kiadási suite subprocessének hiányzó PYTHONPATH-ja javított labor-
beállítás volt, termékkód-változás nélkül; a végső 580-as kör hibátlan. A
konfigurációdiffben a normál solar latest_decision és azonos időpont UTC/CEST
szövege külön kezelést igényelt. Az előellenőrzés utóbbin még **éles leállítás
előtt** megállt; UTC-normalizálás után minden tényleges kezelői érték egyezett.
HC-40-et vagy sémát nem javítottunk ezen a címen.

A bevezetés röviden leállította/cserélte a három alkalmazási komponenst; nem volt
két párhuzamos ingest/backend, DB-migráció, DB-restore vagy környezeti titokcsere.
Az aktív Compose symlink az r2 privát override-jára mutat. Az r2 buildkontextusok
fagyasztottak, a munkafa későbbi HC-07/38 változásai nem kerülnek véletlenül bele.
A külön kiadás egyparancsos r1 visszaállást és read-only verifikációt tartalmaz;
a régi r1 scriptet az r2-höz nem szabad használni. A rollback megőrzi a DB-t/
reteszt, de az r1 korábbi 300 s-os ACK-korlátját és ingest-szűrését visszahozza;
ismételt r2-re váltáskor új élő szenzormegerősítés kellhet. Ezt nem helyettesítjük
mesterséges metadata-/időbélyeg-átírással vagy éles mintapublikálással.

Tartós kiadás és bizonyíték:
[DEPLOYMENT.md](backups/releases/hc-sleeping-20261023-r2/DEPLOYMENT.md),
`evidence/active-deployment.json`, `deployment-verification.json`,
`live-code-assets.json`, `lab-roundtrip.json`, suite-/ingest-/frontendlogok.
A saját labor és kötete eltávolítva; a friss dump és az image-archívumok megmaradtak.
Az eredeti audit változatlan, továbbra is **9 ellenőrzött, 39 nyitott auditpont**.

### REPAIR-011 — HC-39: korlátozott runtime és külön SQL Lab olvasókapcsolat

- **Dátum:** 2026-10-23, Europe/Budapest.
- **Audit:** a HC-39 teljes megállapítása és hivatkozott `database_service.py`,
  `sql_lab_service.py`, Compose/élő role bizonyíték; az **F7a** lépés és F7 előfeltétele
  áttekintve. A SQL-validátor admin signal SELECT-et átengedő viselkedése ismét
  reprodukált, kizárólag laborban/offline; privilegizált auth-adatot nem olvastunk.
- **Hatókör/státusz:** **Ellenőrzött, nincs élesítve**. Az éles r2 kiadás fut tovább.
  Más auditpontot nem javítottunk vagy zártunk le. A megmaradt lazy DDL leválasztása
  a teljes runtime-role szűkítés közvetlen technikai függősége.

**Módosítás és érintett források**

1. `SqlLabDatabase` saját `SQL_LAB_DATABASE_URL`-t kap az app wiringban; a schema,
   preview és query ugyanazon ellenőrzött readerhatáron megy át. Nincs runtime/admin
   fallback. Hiányzó/hibás/túl jogosult kapcsolat 503-at ad, DSN/jelszó nélkül.
   Minden új kapcsolaton effektív role-, tagság-, tulajdon-, írás/oszlopgrant-,
   privilegizált katalógus- és SECURITY DEFINER ellenőrzés történik. A normál Lab
   read-only tranzakciója, SQL-validálása, timeoutja és eredménylimitje megmaradt;
   a séma/preview HC-ra szűkül. Érintett: `sql_lab_database.py`, `settings.py`,
   `app.py`, `sql_lab_service.py`, `api_route_modules.py`.
2. `hc_app` az alkalmazási DML/sequence role, `hc_lab` a HC-olvasó. NOINHERIT és
   minden admin/DB/role/replication/RLS-bypass attribútum false; nincs role-tagság
   vagy objektumtulajdon. A meglévő admin role a külön migrációs kapcsolathoz
   megmarad. Az alap Compose backend/ingest/PgBouncer wiringja app-role-ra változik;
   a Lab közvetlen PostgreSQL-kapcsolata külön marad. A `DatabaseRuntime` és az
   ingest minden kapcsolódásnál/reconnectkor ellenőriz; admin DSN-t visszautasít.
3. `migrate_hc39.py`: alapértelmezésben read-only plan, külön admin környezet,
   explicit `--apply`, HC-07 előfeltétel, ellenőrzött **061** fájlchecksum,
   tranzakció/advisory lock/timeoutok és `hc.db_privilege_migration` journal.
   Két külön, explicit jelszó szükséges új role-okhoz; meglévő jelszót nem forgat.
   Név/típus szerinti `db_privilege_manifest.py` grantlista; journalokra nincs DML,
   nincs TRUNCATE/TRIGGER/REFERENCES/CREATE vagy sequence UPDATE. Új, ismeretlen
   HC objektumot nem grantel automatikusan. Korábbi dumpnál a baseline-journal
   hiánya megengedett; nem naplózott cluster-role átvétele külön explicit opció.
4. A `PUBLIC` adatbázis CREATE/TEMP, user-séma CREATE, reláció- és érintett
   függvényjogai nem kerülhetnek az új readerhez. A telepítő a már létező loginok
   hozzáférését előbb explicit megőrzi, majd szűkít; a saját új role-jai kimaradnak.
   A HC függvények PUBLIC EXECUTE alapjoga a jelenlegi tulajdonosoknál is megszűnik.
   Biztonságtalan megmaradó direkt/oszlopgrant esetén az apply visszagörget;
   nem próbál ismeretlen jogosultságot csendben elfogadni.
5. `061_hc39_runtime_schema.sql`: a korábbi power-wall, binding, temperature/opening,
   page usage, AI audit, irrigation summary, mower draft/staging/session/operation
   és climate guard lazy DDL egyszeri explicit lépése. A 12 runtime-domain most a
   `runtime_schema_contract.py` SELECT ellenőrzését hívja. Hiányzó objektum nem
   keletkezik a kérésből; újrapróbálás csak sikeres ellenőrzés után kész. A guard
   hiányzó singletonját a migráció tölti, meglévő konfigurációt nem módosít.
   Az 055 constraintcsere itt egyszer történik; a restore katalógusa szerint a
   kész séma definícióját nem változtatta. Az üzleti döntés/publish/ACK nem változott.
   A régi mower konstansok történeti fixture-ként maradtak, runtime végrehajtás nélkül.
6. Új, tartós `tests/test_db_privileges_postgres.py` (21 eset), a korábbi mower PG
   fixture-ök explicit pg_temp sématelepítése, a schema/page usage elvárások átállítása
   olvasóellenőrzésre. A régi regressziók állításai és izolációja megmaradtak.
   Szerződés és bevezetés: [hc39-database-roles.md](docs/hc39-database-roles.md);
   `DEPLOYMENT_PREP.md`, HC-07/38 kapcsolódó függőségszövege is frissült.

**Tényleges ellenőrzések**

| Próba | Eredmény / bizonyíték |
|---|---|
| Teljes végleges backend | **638 különálló teszt, 0 failure/error/skip**, minden korábbi PG opt-in körrel és 21 HC-39 esettel. `suite-results.json`, `run_suite.py.log`. |
| Ingest regresszió | **13 sikeres teszt**, 0 hiba/kihagyás; ezen felül valódi psycopg2 app-kapcsolat elfogadva, admin-kapcsolat elutasítva. `ingest-results.json`, `ingest-tests.log`. |
| Role-mátrix | HC SELECT, sequence és üzleti DML sikeres, validáló trigger elutasítja az invalid mérést. App schema/journal/role-admin tiltott. Lab auth-katalógus, másik app-kapcsolat cancel/terminate, SET ROLE, sequence, temp/schema/role create és read-only kikapcsolása utáni DML tiltott. A signal célkapcsolata életben maradt. |
| Hibainjektálás | Hiányzó/privilegizált DSN mindhárom HTTP-végponton 503, nincs fallback/titok. Membership, nem HC PUBLIC olvasás, direkt oszlopgrant és elérhető SECURITY DEFINER veszély esetén lezár; unsafe apply rollback. Timeout után új lekérdezés sikeres; sémahiány nem javul magától, helyes séma után újrapróbálható. Checksumeltérés megáll. |
| Friss DB | Saját PG16-ban HC-38 baseline, 058, HC-07 seed/059/060, majd 061 + role/ACL; plan, apply, ismételt apply és schema checks sikeres. Csak erre a célra létrehozott adatbázisok és szintetikus jelszavak. |
| Teljes régi dump upgrade | Az r2 `pre-cutover.dump` saját PG16-ba restore-olva, **pg_restore exit 0 megvárva**. 059/060 és 061 után **17 üzleti tábla pontos soradata megmaradt**. A katalógus csak az új privilege-journallal bővült, függvények/triggerek változatlanok. Meglévő cluster-role átvétele explicit; ismételt apply no-op. `restore-exit.txt`, `restore-results.json`, `check_restore.py.log`. A restore `--no-owner --no-acl` tesztúton futott; nem teljes host/owner-ACL restore. |
| Valódi WSGI + MQTT + PgBouncer | Health, szezon, notes, scheduler, safety, Lab schema/preview 200. Lab identity `hc_lab`, auth_read=false. Valós MQTT fixture a `hc_app` ingest útján egy állapot- és történetsort írt. HTTP-ből másik app-role signal elutasítva, kapcsolat él. `wsgi-mqtt-results.json`, `probe_wsgi.py.log`, `lab-source-check.json`. |
| Reconnect és rollback-határ | Saját PgBouncer tényleges újraindítása után app identity, health, HTTP Lab és új MQTT state/history sikeres; reader végig külön role-on. Régi admin kapcsolat megmaradt, új backend admin fallbacket nem enged. `pool-reconnect-results.json`. **Teljes régi-image rollback reader-védelemmel nem volt**; annak konkrét feltétele a külön runbookban szerepel. |
| Compose / éles változatlanság | Az explicit új alap Compose szintetikus envvel validált; app/pool/ingest hc_app, Lab hc_lab közvetlen PG. Az éles backend/ingest/frontend/DB/PgBouncer/broker ID, image, indulás és restart-szám változatlan, safety/ingest r2 forráshash egyezik. `compose-results.json`, `live-before/after.json`, `live-source-check.json`, `live-db-after.json`. Nincs éles role/ACL/DSN/migráció/publish/ACK. |

Az első WSGI-laborindítás az image régi `/app` modulját töltötte be a chdir
ellenére; még a health-próba előtt megállt. Közvetlen új `/app` forrásmounttal,
külön modulút/hash ellenőrzéssel javítottuk a laborbeállítást. A mérőscript parser-
hívása és üres hibasztring-állítása, illetve az ingest fixture relatív projektútja
szintén korrigált laborhibák voltak, termékkód-megkerülés nélkül. A restore első
apply-ja a régi DB jogosan hiányzó baseline-journalján állt meg, tranzakciósan;
a manifest opcionális journal-kezelése után az upgrade sikeres. Csak a végleges,
hibamentes körök kapnak sikeres státuszt. A saját öt laborkonténer és az egyetlen
saját PG-kötet eltávolítva; az éles hat konténer a takarítás után is változatlan
(`lab-isolation.json`, `lab-cleanup.json`). Privát bizonyíték: `/tmp/hc39-repair`.

**Függőségek, bevezetés és visszaállás**

- A HC-07/38 helyi F7 munkája előfeltétel; HC-38 baseline továbbra is csak üres DB-re
  alkalmazható. Meglévő éles DB-re 059/060, majd 061 + role/ACL előkészítés és külön
  kiadás kell. A 061 lazy DDL leválasztása kizárólag a HC-39 szükséges függősége.
- **Nem élesítettünk.** Az r2 továbbra is a korábbi DB-kapcsolatot használja;
  a javítás kódellenőrzési státusza nem állítja, hogy az éles superuser már megszűnt.
  Az alap Compose már új hitelesítést vár, a fagyasztott r2 kiadási út változatlan;
  normál `up --build` most sem használható. Frontend/dependency változás nincs.
- F0/F6 mentésrefaktor és teljes hosthelyreállítás, HC-08 scheduler audit/publish,
  HC-33 ingest batch/retry,
  HC-40/41/43/44 és minden további auditpont nyitott; nem javítottuk őket automatikusan.
- Nincs destruktív down-migráció, régi role-törlés vagy automatikus DB-restore/ACK.
  A readerhatárt rollbackkor is őrizni kell. Régi admin app-kapcsolatot igénylő
  kódhoz reader-wiringet megőrző rollback build vagy mindhárom SQL Lab HTTP-út
  előzetes proxytiltása kell; a régi r2 image önmagában ezt nem tudja. Enélkül a
  korábbi app DSN visszatétele nem elfogadható rollback. A már éles r2 saját
  visszaállási folyamata ettől változatlan, mivel HC-39 még nincs bevezetve.

Az eredeti audit változatlan SHA-256-ú. Aktuális kódellenőrzési összesítés:
**10 ellenőrzött, 38 nyitott auditpont**; HC-07/38/39 továbbra is helyi, nem élesített.

### REPAIR-012 — HC-19/25/30/42: közös backup-runner és igazolt készre jelentés

- **Dátum:** 2026-10-23, Europe/Budapest.
- **Áttekintett bizonyíték:** a négy megállapítás teljes szövege és hivatkozott
  `BackupService`, shell/weekly/Git végrehajtók, systemd unitok; F0/F1/**F6** és M.3.
  A root és `a` user napi backup/log timere egyaránt enabled/active állapotú volt.
  A settings-fájl legutóbbi sikernek választása, a teljes logolvasás és az eltérő
  Python/shell mentési út forrásból ismét ellenőrizve; éles hibainjektálás nélkül.
- **Státusz:** mind a négy pont **Ellenőrzött, helyi javítás; nincs élesítve**.
  Más auditpontot nem javítottunk/zártunk le. A r2 és a host régi végrehajtói megmaradtak.

**Megvalósítás**

1. `scripts/backup_runner.py`: egyetlen új host belépési pont local/weekly/git/check/
   maintenance móddal. Webes create/full/Git commit csak fix JSON-kérést és run_id-t
   hoz létre, **202**-t ad; nincs backend tar/BytesIO/dump-végrehajtás. A timer és
   a queue ugyanazokat a belső workereket használja, közös `homecontrol-backup.lock`
   alatt. A heti mód megtartja a korábbi ai-lockot és eredeti sorrendjét. FD-öröklés,
   SIGTERM/timeout folyamatcsoport-kezelés és systemd control-group kizárja, hogy a
   koordinátor halála közben még dolgozó worker mellé új mentés induljon.
2. `backup_archive_worker.sh` + `backup_job_state.py` + `backup_protocol.py`:
   a host korábbi tartalma a kánon, egyedi timestamp+UUID név, streamelt custom dump,
   staging, belső manifest/SHA-lista, `.partial` tar, streamelt ellenőrzés, atomi
   rename/fsync és receipt. Csak ez a commitpont jelent kész archívumot. Retention
   csak új, ellenőrzött helyi publikálás után és ellenőrzött régi példányokon fut;
   ismeretlen/legacy/árva/félkész fájlt nem töröl. A kiválasztott komponens hiánya hiba.
3. Közös leltár a listához/`latest_info()`-hoz. Settings/lock/request/checksum és
   új, receipt nélküli tar nem siker; közvetlen megnyitáskor is védett. Régi tar
   megmarad, `legacy_unverified` jelöléssel. Explicit `--verify-existing` a közös
   lock alatt, belső checksumegyezés után adhat receiptet; nem hamisítunk régi sikert.
   Az API a receipt/stat egyezését ellenőrzi, nem hash-el minden GET-nél teljes tarokat.
4. HC-25: seek/tail legfeljebb 256 KiB, bounded JSON/receipt és legfeljebb 20 friss
   futás. Lockpróba `rb`/flock, hiányzó fájl vagy könyvtár nem keletkezik;
   EACCES ismeretlen, nem igazoltan szabad lock. A read modelben kérés/futás/kész
   archívum külön marad. A külön HC-31 AiNodeService lockolvasót nem módosítottuk.
5. `backup_weekly_worker.sh`, `backup_config_sync_worker.sh`: origin/offsite/Gitea
   dump/secrets/local/restic/retention célonkénti eredmény, független last_success és
   megmaradó last_failure. Origin hiba után offsite is megkísérelt; Git/Gitea-hiba
   után a kötelező helyi/restic út folytatódik. Heti restic nem kerülhető meg a napi
   restic_enabled=false kapcsolóval. Kötelező cél hibáján összesített exit 1, queue
   drain is hibával zár, miközben a további kész kéréseket feldolgozza. Nincs force-push.
   Az opcionális secrets bundle és a heti halasztott shutdown eredeti szerződése
   megmaradt; a shutdown csak a kötelező mentési kísérletek után kérhető.
6. `scripts/systemd/f6/` 12 új forrásunit; `install_backup_f6.py` csak explicit
   `--apply` esetén telepít, alapértelmezésben tervet ad. User manager előellenőrzés,
   idle/common-lock, aktív régi backup/maintenance és másik apply-helper elutasítása,
   privát telepítettunit/engedélyezési snapshot, régi apply-watcher leállítása,
   két duplikált user timer tiltása, rendszer-scope, ellenőrzött eredmény. Hibás
   átmenetnél mentett unitbájtok/enabled állapot visszaállítása. Kezelői napi/heti
   időpont és tiltás megmarad; havi első vasárnapi restic check és jitter változatlan.
7. `BackupService`, frontend Backup és `backupJobState.mjs`: a saját run_id követése;
   a queued/running kérésből nem lesz hamis „created” eredmény, másik futás sem zárja
   le. Célonkénti kimenet/utolsó siker, legacy jelölés és ellenőrzött archívum külön
   látszik. A generikus runner-állapot nem helyettesíti a külön heti AI shutdown guardot.
   Az új backup frontendteszt a Dockerfile szokásos buildlépésébe is bekerült.

**Tényleges ellenőrzések**

| Ellenőrzés | Eredmény és bizonyíték (`/tmp/hc-f6-repair`, privát) |
|---|---|
| Teljes backend | **667 különálló teszt, 0 failure/error/skip**, minden korábbi opt-in PG körrel; 21 új F6 processz/protokoll + 8 installer eset. A végső apply-helper ütközésellenőrzésre a 8 installer-teszt célzottan újra hibamentes. `suite-results.json`, `run_suite.py.log`, `final-installer-tests.log`. |
| Frontend | **93 teszt** (83 mower + 4 AI + 6 backup) és Vite production build sikeres, hálózat nélküli Node-konténer, meglévő dependency-cache. Verzió/lockfile nem változott. `frontend-check.log`. |
| Konkurencia/kilövés | Valós subprocess/flock: web+timer kizárás; SIGTERM dump és tar közben; SIGKILL parent mellett élő worker tovább tartja a lockot, új runner 75-tel elutasítva. Worker vége után interrupted, nem siker; nincs kész receipt. |
| Hibák/retention/olvasás | Dump-, tar/disk-full-, permission-, origin-, offsite-, Gitea dump-, restic snapshot/retention/check hiba; required restic napi tiltás mellett; késői jó helyi mentés nem mossa el a remote hibát. Belső checksumeltérés elutasított; sérült/részleges fájl és újabb settings/lock nem latest. 64 MiB sparse log és rotáció bounded olvasással; hiányzó lock nem jön létre, olvasási EACCES unknown. Régi jó mentés hibánál megmarad, retention csak új ellenőrzött siker után. |
| Valódi HTTP → queue → worker | Tényleges Flask route-on POST create: **202/queued**, nincs backend dump; host drain után ugyanaz a run_id completed és verified archívum. A külső parancsok szintetikus adapterek. `http-results.json`, `http_probe.py.log`. |
| Valódi új PG-mentés és restore | Az r2 korábbi teljes dumpjának saját PG16 source restore-ja **exit 0 megvárva**. A közös új runner ebből **111 367 498 bájtos dumpot** streamelt; **109 596 668 bájtos tar**, 15 belső fájlchecksum és teljes SHA ellenőrizve. Új, második DB-be `pg_restore` **exit 0 megvárva**. **52 HC-tábla darabszáma, 17 üzleti tábla pontos soradata, teljes HC-katalógus/függvény/trigger egyezik; 6 673 183 mérés**. `real-backup-restore.json`, `restore-comparison.json`, restore-exit/log fájlok. Szintetikus fájlgyökér és kizárólag saját lab-pg_dumpot engedő Docker-wrapper; éles adatforrás nélkül. |
| Streamelés megfigyelése | Konkrét új backup kb. 27,94 s, megfigyelt max gyerek RSS 29 156 KiB; 111 MB dump mellett nincs BytesIO/whole-output gyűjtés. Egy labormérés, nem általános teljesítménygarancia. |
| Valódi helyi Git | Két helyi bare repository: mindkét push sikeres; origin hook elutasításakor offsite ténylegesen frissül; fordítva origin siker, offsite hiba; utóbbi két eset összesített exit 1. Távoli repositoryba nem írtunk. `real-git-results.json`. |
| Valódi helyi restic | Saját titkosított helyi repo, egy sikeres snapshot, tényleges `restic check` és snapshotból visszaolvasott archívum SHA-ja egyezik. SSH-szerver/HDD-próba szintetikus; az éles restic repo nem érintett. `real-restic-results.json`, `real-restic.log`. |
| Legacy készre jelentés | Aktív közös lock mellett explicit verify elutasított, utána ugyanazon valódi mentés régi névvel adott példánya belső checksumokkal elfogadott. Nem minden történeti archívum újraellenőrzése. `legacy-adoption.json`. |
| Unitátadás | 8 fake-manager szerződéspróba: mindkét user timer tiltva, egy root végrehajtó, tiltott/egyedi időpont megmarad, user bus hiba és aktív régi service/apply elutasítva, hibás enable esetén pontos unit-visszaállítás, ismétlés idempotens. Static unitverify exit 0, host manager/bus figyelmeztetésekkel; nem éles systemd-átadás. `install-plan.json`, `unit-verify.log`, `final-installer-tests.log`. |

Az első konténeres F6 körben a teszt-tmpfs `noexec` beállítása blokkolta a
szintetikus command fixture-öket; a hostpróbák már akkor sikeresek voltak.
A konkrét PermissionError diagnózis után kizárólag a hálózat nélküli teszt-tmpfs
kapott exec jogot; a végleges suite hibamentes. A valódi dump mérőscriptben hiányzó
opcionális `/usr/bin/time` helyett Python resource-mérés, a Git-fixture-nél a
kiválasztott BASE továbbadása és a Flask-probe hiányzó route adapterei javítva.
A systemd-analyze hostverziója `--root` verify-t nem támogatott; e sikertelen
laborparancs nem telepítés. Csak a sikeres végső próbák szerepelnek igazolt eredményként.

**Függőségek, éles határ és visszaállás**

- **Nem történt élesítés.** Az eredeti shell scriptek és eredeti systemd source-ok
  változatlanok, mert a futó host timerek és apply-watcher közvetlenül rájuk mutat.
  A root és user timerek tényleges letiltása csak a későbbi explicit hostbevezetéskor
  történhet. A helyi forrás státusza nem állítja, hogy az éles duplikáció megszűnt.
- F1-ből **HC-17/18 exporthatár nyitott**: a meglévő exporter titok-/tartalomhibáját
  nem javítottuk. Éles Git-publikáció előtt rendezendő; a HC-24 mDNS nem technikai
  része ennek. **HC-31/F6b**, HC-27–29/37/45–47 és teljes hostrestore külön munka.
  A késleltetett fizikai power-cut ismert hibája változatlan; a régi heti guard és
  shutdown-sorrend megőrzése nem HC-31-lezárás.
- HC-07/38/39 helyi javításához a F6 végrehajtó most előkészített/ellenőrzött.
  A migrációk/role/DSN/pool és az új backend/frontend/host unit kiadás továbbra is
  külön összehangolt átadás. A backup admin dump a host feladata, nem a hc_app-é.
- Helyi tar és nyers restic-forrás tartalma, full/partial, legacy receipt és retention
  szerződése: [hc-f6-backups.md](docs/hc-f6-backups.md). Új Git exporter nincs;
  restore útvalidátor, fájl-metaadat és launcherscript nem változott automatikusan.
- Installer-hibánál unit-visszaállás próbált; teljes új kiadás → r2 host/backend/UI
  rollback most nem volt. A későbbi kiadáshoz fagyasztott forrás és privát unitbundle,
  külön átadási/visszaállási próba kell. A közös lock és helyes olvasómodell megtartandó;
  a régi webes Python create visszakapcsolása önmagában nem kompatibilis rollback.
  Archívumot, DB-t, safety latch-et/ACK-ot nem törlünk rollback címén.

Az eredeti audit SHA-256-a változatlan. A saját labor takarítása és az éles
konténer/unit/script változatlanságának végső bizonyítéka az alábbi zárókiegészítésben.
Összesítés: **14 ellenőrzött, 34 nyitott auditpont**, a HC-19/25/30/42 és HC-07/38/39
helyi; az éles r2 kiadás változatlan.

#### REPAIR-012 záróellenőrzés

Az éles backend/ingest/frontend/PostgreSQL/PgBouncer/broker konténer-ID, image,
indulás és restart-szám a javítás előtti állapottal egyezik. A futó backend
`backup_service.py` hash-e a fagyasztott r2 forrásával egyezik. **40 eredeti
host script/forrásunit és 14 telepített rendszerunit byte-pontosan változatlan**;
a root és user timer állapotát csak olvastuk, továbbra is a korábbi enabled/active
állapotban van. Ez megerősíti, hogy a négy javítás nincs élesítve.
Bizonyíték: `live-before/after.json`, `live-backup-source-check.json`,
`live-scope-check.json`, `installed-unit-before/after.json`, timerállapot-fájlok.

A saját PG16-labor és kötete eltávolítva; tesztkonténer nem maradt. A privát
bizonyíték, az új valódi archívum és dump megmaradt, az eredeti r2 mentés nem változott.
`lab-isolation.json`, `lab-cleanup.json`, forráshash-ek és diffek a privát
`/tmp/hc-f6-repair` könyvtárban. Az éles rendszeren nem volt mentésindítás,
Git-push, restic-művelet, wake/shutdown, deploy, migráció, szenzorpublish vagy ACK.

### REVIEW-001 — A még nem élesített blokk második ellenőrzése (2026-10-23)

**A blokk még nem élesítésre kész.** A friss 41 célzott backendteszt és 93
frontendteszt/build sikeres, de új, teljes-runner ellenpróbák két archívumhibát
igazoltak: belső `MANIFEST.txt`/`SHA256SUMS.txt` fájlok és megőrzött hardlinkek
mellett checksumeltérés miatt nincs kész mentés. A HC-17/18 exportfüggőség
szintetikus próbában továbbra is fennáll; a közös kiadási/rollback-próba hiányzik.

[Részletes megállapítások, bizonyítékok és bevezetési feltételek](docs/hc-block-double-check.md).
Ez ellenőrzési bejegyzés, nem új javítás: a korábbi teszteredményeket nem írja át,
de a F6 élesítésének feltételeit a fenti két javítással kiegészíti. Termékkód,
eredeti audit és éles rendszer változatlan; auditpont lezárása nem történt.

### REPAIR-013 — A review DC-01/DC-02 archívumhibáinak javítása (2026-10-23)

**Hatókör:** a HC-19/F6 helyi közös mentésprotokoll két ellenpéldája.
Az audit kapcsolódó bizonyítékait és F6 lépését ismét áttekintettük.
Más auditpont javítása és élesítés nem történt.

- A `backup_protocol.seal()` kizárása csak a gyökérszintű saját manifest/checksum
  fájlokra vonatkozik. Belső `MANIFEST.txt` és `SHA256SUMS.txt` tartalma is bekerül
  a checksumhalmazba; a verifier és a tar ugyanazokat a fájlokat ellenőrzi.
- A streamelt verifier az azonos archívumgyökéren belüli, már beolvasott célfájl
  hash-ével ellenőrzi a hardlink útvonalát is. Hiányzó/idegen/önmagára vagy előre
  mutató célt elutasít, nem csomagol ki és nem bufferel teljes fájlt. A link célja
  és a link útvonalához elvárt tartalom eltérése továbbra is checksumhiba.
- Öt tartós regresszió került a `test_backup_runner.py` fájlba: belső fájlnevek
  tartalmi visszaolvasása scripts/HA alól, sérült belső manifestek, tényleges GNU
  tar hardlink visszaolvasása, hibás linkcéltartalom, érvénytelen linkcélok.

**Ellenőrzés:** javítás előtt a két új teljes-runner regresszió 2/2 hibás;
javítás után **46 mentési teszt**, 0 failure/error/skip. Az eredeti kontroll és
három ellenpróba külön is exit 0 / completed / verified archívumot adott.
A korábbi 109 596 668 bájtos, teljes DB-restore-ral igazolt archívum és régi nevű
példánya változatlan SHA-val, 15 belső fájlchecksum-mal ellenőrizhető. Új PG-restore
és frontendteszt ebben a célzott körben nem futott; azok kódja változatlan.

Termékkódból csak `infra/backend/backup_protocol.py` és a tesztfájl változott;
minden más korábban leltározott termékforrás és 14 telepített unit SHA-ja egyezik.
Az eredeti audit változatlan. A fagyasztott éles r2, host timerek és eredeti host
scriptek nem módosultak. Nem futott deploy, migráció, Git-push, távoli restic,
wake/shutdown, szenzorpublish vagy ACK.

**Nyitott függőségek:** HC-17/18 exporthatár (DC-03), valamint a közös fagyasztott
kiadás és átadási/rollback-próba (DC-04). Ezeket a javítás nem zárja le; a blokk
ettől még nem minősül teljesen előkészített éles kiadásnak. Az auditpontok száma
változatlan: ez két reviewhiba javítása a korábbi F6 javításon belül.

Bizonyítékok: `/tmp/hc-dc-repair/` — előállapot/hash/diff, `regressions-before.log`,
`backup-tests.log`, `probes.json`, `existing-archive-verification.json`.
[Frissített review és javítási eredmény](docs/hc-block-double-check.md).

### REPAIR-014 — HC-31: AI-leállítás és mentés közös koordinációja (2026-10-25)

**Hatókör:** kizárólag HC-31/F6b, az audit bizonyítékainak és a locktulajdonosoknak
az újraolvasásával. Más auditpont státusza és megvalósítása nem változott.
**Helyben ellenőrzött, nincs élesítve.**

- Új stdlib `ai_power_coordination.py`: atomi generáció/szándékállapot, rövid
  koordinációs lock, az SSH/OFF alatt megtartott AI/common backup-lockfoglalás.
  A power út nem vár backup lockra a koordináció birtokában, így a weekly
  saját lockját birtokló callback nem okoz önblokkolást.
- Az AiNodeService egyetlen aktuális, lejáró, rögzített entity/topic/platform/device
  szándékot és egy kezelőszálat használ. Wake, új F6 feladat, AI-bindingcsere,
  új shutdownkérés és backendújraindítás visszavonja a korábbit. A végrehajtáskori
  guard, célazonosság és érvényesség ellenőrzése a tényleges foglalás alatt történik.
- A weekly/check worker futásazonosítót visz a saját wake és completion kérésbe.
  Köztes kézi wake vagy új szándék után a régi completion 409; saját lock alatt
  csak 202/deferred. Az SSH csak lockelengedés után indul, a régi requestfájl
  nem játszódik vissza. A `defer_if_backup_running=false` többé nem bypass.
- A ProcessBindingService csak az `ai_node_power_plug` mentését koordinálja;
  az A → B → A is érvénytelenít. HC-35/36 és más bindingpolitikák nem változtak.
- A backup/AI API és UI külön mutatja az ismeretlen guardot, queued shutdownt
  és pending OFF-ot. A countdown szerveroldali szándékhoz kötött; régi böngészőbeli
  határidőből nem származik. Guardhiba blokkolja az AI power utat, más backend
  funkció indulását nem akadályozza. Fizikai OFF nem kap hamis observed minősítést.

**Ellenőrzés:** az eredeti tiszta, helyettesítő publisheres reprodukció a régi
kódon A helyett B-re adott OFF-ot aktív lock alatt; az új kód nem publikált.
26 AI-teszt (21 clock/flock/processz/transport + 5 Flask HTTP), benne minden
F6b eseménysorrend; valódi külön processz lockversenye mindkét sorrenddel,
weekly self-held callback, restic-check callback és ismeretlen lockhiba.
A végső backend alapkör **701 felfedezett: 585 sikeres, 116 PG opt-in kihagyott,
0 failure/error**; ebből 49 mentési eset. **98 frontendteszt**, 0 hiba,
production build sikeres. Python- és shellszintaxis rendben. Külön backup-státuszpróba
igazolta a közös lock, pending szándék, törlés és unknown állapot megjelenését.

Az első futás új fixture-hibája (teljes offline miatt hiányzó restic parancs)
csak az első SSH-probe kiesésére korlátozva javítva; a végső kör hibamentes.
Új DB-migráció/PG-integrációs kör és fizikai shutdown/wake nem futott. Az audit
a felügyelt hardverpróbát külön végrehajtási feladatnak tekinti; az még hátravan.

**Függőség/bevezetés:** a mostani megoldás az új F6 runnerrel, weekly/check
workerekkel, backenddel és UI-val együtt, azonos backupmounttal adandó át.
A legacy-only indítás nem biztosít minden esetben generációs érvénytelenítést.
A teljes munkafakiadáshoz a HC-07/38/39 migrációs/role/DSN feltételei megmaradnak;
HC-17/18 és F6a továbbra is külön, nyitott munka. Az aktuális r3 ingest javítása
megőrzendő. Kiadási és rollback-próba még nem készült; régi pending szándékok és
alvó workerek megszüntetése, valamint a közös védelem megőrzése szükséges.

**Éles határ:** 6 konténer ID/image/indulás/restart-szám változatlan; élő AI-modul
hash-e a fagyasztott r2-é, ingest továbbra is r3. A 14 telepített unit és az eredeti
pre-F6 host scriptek/forrásunitok változatlanok; DB/MQTT health rendben.
Nem futott élesítés, mentésindítás, SSH/WOL/MQTT-eszközművelet, Git-push, távoli
restic, migráció vagy ACK. Az eredeti audit SHA-ja változatlan.

Bizonyíték: `/tmp/hc31-repair/` — előállapot/hash/diff, `unit-tests.log`,
`backend-tests.log`, `backend-results.json`, `frontend-tests.log`,
`audit-reproduction.json`, `backup-status-probe.json`, `live-before/after.json`,
`live-scope.json`. [Részletes működési és rollback-szerződés](docs/hc31-ai-power-coordination.md).

Összesítés: **15 ellenőrzött, 33 nyitott auditpont**; a HC-31 helyi, nincs élesítve.

## REPAIR-015 — HC-17: hitelesítési fájlok exporthatára

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** HC-17 bizonyíték, I/J titokmentes vizsgálati határ, F0/F1.
Új pozitív manifest és tiszta staginges exporter; minden Xiaomi auth-/backupváltozat,
`.env*`, HA-secret és kulcs kizárva, ismert credential-tartalom fail-closed.
A régi checkoutban már követett fájl is eltűnik a következő snapshotból.
Az új weekly ág a tényleges auth-változatokat titkosított manifestbe emeli.
Friss/meglévő checkout, már követett titok, JSON/private-key védelem tesztelve;
valódi szintetikus age encrypt/decrypt és validált `0600` restore sikeres.
Külön inaktív valódi encrypted bundle: 12 fájl, két auth-változat;
hiányzó opcionális forrás: `apps/xiaomi-x10/.env`. Valódi visszafejtés nem történt.
**Függőség/rollback:** F6-tal együtt adandó át; a távoli Git-történet és esetleges
credential-csere külön vizsgálat. Éles régi exporter/secretmanifest változatlan.

## REPAIR-016 — HC-18: végrehajtott és megjelenített exportleltár

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** HC-18 hiányzó Compose-forrásai, F0/F1.
A backend/UI és az exporter ugyanazt a `git_paths` leltárt használja;
a mező nem írható felül hatástalan, tetszőleges listával.
Bekerült db/proxy/MQTT-config/mDNS, megmaradt minden app buildforrás.
Valódi privát helyi export, leltárteszt, izolált backend/frontend/ingest build
és két fagyasztott Compose-terv renderelése sikeres.
**Függőség/rollback:** HC-17-tel és F6-tal együtt; HC-24 mDNS-parserét nem javítja.
A Git-kód/config snapshot nem a teljes gépmentés.

## REPAIR-017 — HC-27: teljes preflight és visszagörgethető részleges restore

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** késői DB-tag után megváltozó fájl reprodukciója, I/J, F6a.
A teljes kijelölés validálása és payload/előképek stagingje megelőzi a célírást.
Fájlonként fsync+atomikus csere; run ID-s napló, már a mkdir előtt rögzített
könyvtárterv. Nem többfájlos tranzakció. Hiba: HTTP 409, applied/remaining és
recovery ID, tartósan újra felderíthető pending műveletek. Külön ROLLBACK endpoint
és UI; későbbi kezelői szerkesztést nem ír felül automatikusan.
Késői tiltás, ENOSPC, permission, valódi processzkilépés új szülőkönyvtárakkal,
recovery/idempotencia, Flask 400/409/200 bizonyítva. A kibővített kill-próba
megtalálta a létrehozott szülők naplózási rését; ez a végső kódban javítva.
**Függőség/rollback:** közös F6 lock; előképek és napló megőrzendők a lezárásig.
A programverzió visszarakása önmagában nem görget vissza alkalmazott fájlokat.

## REPAIR-018 — HC-28: módok, időbélyegek, könyvtárak, linkek

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** 0750/0600→0644 reprodukció, I/J, F6a.
Mode&0777, mtime és üres könyvtár megmarad; directory-metaadat a gyermekek után.
Explicit relatív symlink/hardlink politika, speciális/escape/ki nem jelölt cél
előre elutasítva; idegen ownership és suid/sgid nincs vakon visszatöltve.
0750 script ténylegesen futott a valódi új F6-archívumból visszaállítva;
0600 fájl, 0710 üres directory, mtime és hardlink közös inode is ellenőrzött.
**Függőség/rollback:** HC-27 preimage-jével a korábbi tartalom és metaadat is visszatehető.

## REPAIR-019 — HC-29: compare és restore közös fájlhatára

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** célgyökéren kívüli testvérfájl diff-olvasása, I/J, F6a.
Közös canonical validator fut már bármely fájlolvasás előtt; abszolút/.. út,
ismeretlen komponens és symlink szülő/cél tiltott. Descriptoros, no-follow,
méretkorlátos aktuálisfájl-olvasás; archívumlinket nem hasonlít szövegként.
Traversal- és symlink-fixture az archívum/cél olvasásának meghívása nélkül bukott.
**Függőség/rollback:** a HC-27/28 modullal együtt maradjon; a régi diffhatár nem tehető vissza.

## REPAIR-020 — HC-37: tartalmi restore-smoke

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** üres `find` 0 exitkód, I/J és M távoli bizonyítási határ, F6a.
Homecontrol tagből választott teljes snapshot ID, nemüres tényleges archívum,
streamelt teljes SHA-ellenőrzés és külön filesystem/restic/database eredmény.
A DB nem lesz sikeresnek jelölve pusztán a tar listázhatóságától.
Valódi helyi encrypted restic tár: újabb más tag kihagyva, pontos ID restore,
SHA egyezés; ép helyi fájl mellett a visszahozott sérült archive elutasítva.
Az opcionális DB-próba külön PG16-ban `--exit-on-error`-ral fut. A teljes adat/index
nem fért a kezdeti 2 GB tmpfs-be; ezért a végső ág friss, --rm-mel törlődő anonim
PGDATA kötetet használ, nem a teljes DB-t RAM-ban tartja. Ezzel a külön valódi DB-smoke is sikeres: 52 HC-tábla, owner/ACL nélküli próba, nincs összetévesztve a korábbi owner/ACL-es restore-ral.
**Függőség/rollback:** távoli Gitea/restic nincs ebből igazolva; régi hamis sikert adó
script csak a javított tartalmi ellenőrzés megtartásával állítható vissza.

## REPAIR-021 — HC-45: full restore hostmanifest

**Dátum:** 2026-10-26. **Státusz:** Javítva – ellenőrzésre vár.
**Alap:** M. full launcher/unitmanifest hiány, HC-45, F6a.
Full bootstrap után explicit, ismételhető system-scope installer: 12 F6 + 2
post-boot unit, user-duplikáció ellenőrzése/visszavonása, telepített hash,
active/enable és next-trigger ellenőrzés, mentett installed előállapot.
Hiányzó user account/bus csak ellenőrzött fresh-host esetben fogadható el;
a későbbi apply watcher is ezt a manifestet használja. Startup nem hosttelepítő.
11 manager-contract teszt és két teljes canonical tmpfs bootstrap sikeres;
14 azonos unit, next-trigger, sérült/DB nélküli mentés korai hibája igazolt.
**Nyitott:** valódi üres VM-en működő systemd-managerrel ismételt full restore,
Persistent-trigger/duplikáció/rollback és offline age-kulcs próba. VM-futtató
nem állt rendelkezésre; a szimulált manager eredményét nem nevezzük VM-bizonyítéknak.
**Függőség/rollback:** F6 teljes hostkód/lock; HC-07/39 explicit migrációs híd;
HC-31 fizikai próba külön. Unit-rollback előállapota megmarad; éles install nem futott.

## REPAIR-022 — HC-46: az archívumhoz kötött dump

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** N. újabb→régebbi és DB nélküli archívum reprodukciói, F6a.
Egyedi selected-archive staging; pontosan egy regular postgres dump, belső SHA,
archívum/dump hash és relatív tagnév a selection JSON-ban. Nincs régi stagingben
kereső fallback. Formátum-/tartalomellenőrzés stop/drop előtt, hash-újraellenőrzés
közvetlenül csere előtt; pg_restore --exit-on-error.
Új→régi snapshot közös work-dirrel helyes dumpot adott. DB nélküli és checksumhibás
mentés előtt a teljes bootstrap még Docker-parancsot sem hívott. Valódi F6 runner
új, 109 596 894 bájtos archívuma 17 file-checksummal ellenőrzött; a 111 367 498
bájtos dump PG16 célba 0 exitkóddal visszaállt.
**Függőség/rollback:** F6 archívumszerződés; baseline meglévő DB-re nem alkalmazható,
a korábbi stagingek nem válnak automatikus fallbackké.

## REPAIR-023 — HC-47: canonical full target és secret-határ

**Dátum:** 2026-10-26. **Státusz:** Ellenőrzött, helyi.
**Alap:** N. eltérő target mellett canonical secretírás reprodukciója, F6a.
Bootstrap és launcher full/apply/DB/start esetben kizárólag a canonical targetet
fogadja el, még apt/clone/stop/copy előtt. Staging-only támogat más work/targetet.
A teljes secret-tar elővalidált; project és /etc/homecontrol külön allowlist,
link/special/traversal tiltás, no-follow és atomikus 0600 fájlcsere.
Eltérő full/skip-restic target korán hibázott, canonical sentinel megmaradt;
valódi szintetikus encrypted bundle validált staging restore-ja sikeres.
**Függőség/rollback:** hostrestore külön izolált gép; fájl/DB-apply után nem elég
kódot visszatenni. A működő offline kulcs és HC-45 hostpróba még szükséges.

## REPAIR-024 — közös végellenőrzés és inaktív r4 csomag

**Dátum:** 2026-10-26. **Élesítés:** nem történt.
**Regresszió:** végső teljes backend **731 teszt, 0 failure/error/skip**, minden PG
opt-in körrel; **98 frontendteszt** (83 mower + 9 AI + 6 backup) és production build.
Ebből 25 új export/restore szerződés, 2 Flask HTTP-próba és 11 hostunit-próba.
A regressziós HC-39 fixture trust kapcsolatot feltételez; a kiadási SCRAM-környezet
változtatás nélküli újrahasználata egyszer hitelesítési hibát okozott. A fixture
feltételének helyreállítása után a 731-es kör hibamentes; a valódi jelszavas
kiadási próbát külön SCRAM-mal futtatjuk. Nem termékkód-lazítás történt.

Valódi régi teljes dump owner/ACL restore-ja és az új runner dumpjának külön
restore-ja sikeres. Saját hálózat nélküli DB/PgBouncer/MQTT mellett release →
korlátozott rollback → release, health/frontend/ingest és operator-config ellenőrzés
sikeres; 6 673 183 mérési sor megmaradt. A végleges image/probe eredmények az
inaktív csomag `evidence` könyvtárába kerülnek. A rollback megőrzi az új F6
lockját és az additív sémát; SQL Lab, webes backup-módosítás és AI power ideiglenesen
503. Az r3 ingest visszajelzési javítása megmarad. Nem történt ACK, fizikai
SSH/WOL/power-művelet, Git-push vagy távoli restic művelet.

A csomag külön privát app/reader env-et és új age-bundle-t tartalmaz; az eredeti
éles titkok nem változtak. Az éles régi exporter/backup scriptek és forrásunitok
változatlanok. A HC-45 valódi VM/systemd/kulcs és HC-31 fizikai próba megmaradó
előfeltétel; HC-24/41/44 nincs automatikusan javítva. Ez **nem** feltétel nélküli
„csak élesíteni kell” jóváhagyás.

Részletes szerződés: [docs/hc-f1-f6a-repair.md](docs/hc-f1-f6a-repair.md).
Nyers privát bizonyíték: `/tmp/hc-f1-f6a-repair/`; tartós, titokmentes összesítés:
`backups/releases/hc-refactor-20261026-r4/evidence/`. Forrásaudit SHA változatlan.

Összesítés: **23 ellenőrzött, 24 nyitott, 1 javítva – ellenőrzésre vár (HC-45)**.

## REPAIR-025 — a hátralévő bevezetési ellenőrzések végrehajtása

**Dátum:** 2026-10-26. **Élesítés:** nem történt. A felhasználó kérte a még
szükséges lépések elvégzését. Új auditpont kódját nem módosítottuk.

**Valódi age-bundle és helyi kulcs:** az r4 előkészített titkosított csomagját
a meglévő külön identity sikeresen visszafejtette. Hálózat nélküli, csak olvasható
konténerben, tmpfs-staginggel a teljes archívum validálása és mind a **12 titkos
fájl** tartalmi összehasonlítása sikeres. A 14 validált fájlból kettő metadata;
a titkos fájlok módja 0600. Az előkészített app/reader env került összevetésre,
az éles titkok változatlanok. A kulcs nincs a saját bundle-jében; a plaintext
staging törlődött. Ez a helyi identity működését bizonyítja, külön külső/offline
kulcspéldány meglétét vagy a teljes VM-láncot nem.

**HC-31 fizikai próba — részleges, nem lezárt:** az AI-aljzat kezdetben OFF,
az SSH és az Ollama nem volt elérhető. Az r4 fagyasztott `AiNodeService` kódja
külön koordinációs könyvtárral futott; a próba idejére a valódi legacy AI/common
backup-lockokat foglalta, az éles backend nem cserélődött. A rögzített 121-es
AI-aljzat azonosságát minden kapcsolás előtt ellenőrizte. A publisher callback
az éles Power Wall HTTP→MQTT útját használta; a WOL valódi hálózati művelet volt.
Az ütemezett OFF-ot a candidate wake érvénytelenítette, az ON-parancs elfogadása
után nem retained telemetria igazolta a bekapcsolt aljzatot és fogyasztást mért.

A konfigurált **192.168.1.2:22** 180 másodpercen belül sem vált elérhetővé;
az ARP-bejegyzés FAILED. A fizikailag bekapcsolt aljzat után második WOL is
ment, a lezáró SSH/Ollama próba továbbra is sikertelen. **SSH shutdown vagy OFF
nem történt**, a teljes shutdown→OFF→wake ciklus nincs bizonyítva. A tesztfolyamat
lezárult, saját pending szándékát törölte, mindkét valódi backup-lockot elengedte.
**Az AI-aljzat bekapcsolva maradt**; a gép állapotát és IP-címét helyben kell
egyeztetni a szabályos leállítás folytatásához. A visszakapcsolást nem tekintjük
az operációs rendszer sikeres indulásának.

**HC-45 VM-határ:** KVM-eszköz van, de nincs telepített QEMU/libvirt/nspawn/
VirtualBox/Multipass/cloud-hypervisor és nem találtunk előkészített VM-lemezt.
Az eldobható restore-VM SSH-elérését bekértük. Valódi systemd-manageres full
restore, ismétlés, Persistent-trigger/duplikáció és unit-rollback nem futott;
a korábbi fixture-manager bizonyítékát nem minősítjük át.

**Végellenőrzés:** a hat éles konténer ID/image/indulás/restart-száma változatlan,
DB/MQTT health rendben; az aktív Compose override továbbra is r3. A csomag
SHA/image/Compose ellenőrzése sikeres. Nem volt migráció, hostunit-telepítés,
ACK vagy éles kiadásváltás. A forrásaudit SHA változatlan. **A két bevezetési
kapu nyitva marad**, az auditpontok összesítése változatlan.

Tartós, titokmentes bizonyítékok az r4 `evidence/` könyvtárában:
`real-key-decryption-check.json`, `physical-probe-events-20261026.json`,
`remaining-validation-20261026.json`. Privát végrehajtási nyom:
`/tmp/hc-remaining-validation/`.

### REPAIR-025 folytatás — AI-kapcsolat célzott diagnosztikája

A felhasználó visszajelzése szerint nincs eldobható VM; a fejlesztői PC-ről
az AI-gép pingelhető. A HC-ról és a backend konténerből a 192.168.1.2:22 és
:11434 továbbra is elérhetetlen, miközben a 192.168.1.1:80 mindkettőből működik.
A HC címe 192.168.1.133/24; az AI felé közvetlen eno1 útvonal helyes, a NIC
1 Gbit/s/full duplex kapcsolatot és nulla RX/TX hibát jelez.

Három broadcast és három, a konfigurált 7c:10:c9:87:ad:c9 MAC-re küldött unicast
ARP-kérésre nulla AI-válasz érkezett; a kontroll router három kérésre háromszor
válaszolt. Az AI neighbor állapota FAILED. Nyers ICMP-próba az ismert AI-MAC-re
és a routeren át sem adott AI-választ; a router kontroll echo 3/3 sikeres,
két ICMP redirect érkezett. A próbák nem módosították a host route-/ARP-beállításait.

A listázott nftables készletben nincs ARP/netdev family vagy AI-címet célzó
szabály; a legacy iptables készlet és az eno1 ingress/egress tc-szűrőlistája üres,
XDP nincs. Ez a helyi alkalmazáshibát és több helyi szűrési okot kizár, de
**a két gép közötti hiba gyökérokát még nem bizonyítja**. A fejlesztői PC
`arp -a 192.168.1.2` eredményének MAC-címét bekértük az eszközazonosság
összevetéséhez; switch-/VLAN- vagy AI-oldali hibát egyelőre nem állítunk tényként.

Éles konfiguráció-/tűzfal-/route-módosítás, újabb fizikai kapcsolás vagy
élesítés nem történt. Bizonyíték: az r4 `evidence/ai-network-diagnostic-20261026.json`;
a szűrt nyers diagnosztika és próbascriptek a privát munkakönyvtárban maradnak.

### REPAIR-025 státuszfrissítés — AI-próbák elhalasztva

**2026-10-26, felhasználói döntés:** az AI-szerver SSD-jével probléma van,
ezért az AI-szervert most kihagyjuk a további vizsgálatokból. Ez felhasználói
hardverjelzés; az SSD állapotát külön mérés nem igazolta. A fejlesztői PC-ről
beküldött ARP-eredmény is `<incomplete>` volt; a PC címe 192.168.1.89/24,
sikeres pingválasz kimenete nem érkezett. Az AI-kapcsolat hibáját ezért továbbra
sem minősítjük bizonyított HC-konfigurációs hibának.

A **HC-31 fizikai shutdown/OFF/wake próba elhalasztva, nem lezárt**. A szoftveres
ellenőrzések korábbi eredményei megmaradnak. Az AI-próba folytatása működő
hardver és hálózati/SSH-elérés mellett lehetséges. Eldobható VM a felhasználó
visszajelzése szerint nincs, így a **HC-45 valódi hostrestore-próbája is hátravan**.
A halasztás nem jelent automatikus felmentést a bevezetési kapuk alól.

Ebben a státuszfrissítésben kizárólag dokumentáció módosult. Az AI-géphez nem
indult új kapcsolat-, WOL-, shutdown- vagy tápkapcsolási művelet; élesítés sem
történt. A korábbi próba végén ON állapotban hagyott aljzatot most nem kapcsoltuk.

## REPAIR-026 — korlátozott r6 kiadás előkészítése AI-szerver nélkül

**Dátum:** 2026-10-27. **Kérés:** korlátozott élesítés előkészítése;
**élesítés nem történt**. Külön csomag: `hc-refactor-ai-offline-20261027-r6`.
Az eredeti r4 megmarad. Más auditpontot nem javítottunk vagy zártunk le automatikusan.

**Profil:** image-be és hostmodul mellé fagyasztott, kötelező `ai-offline` policy.
Settings/ENV nem kapcsolhatja ki; sérült/hiányzó kötelező profil mellett az
alkalmazás és a védett poller nem indul. AI-node SSH/WOL/shutdown/késleltetett
kapcsolás, AI gateway/chat/model művelet és az AI-binding módosítása tiltott.
Az AI státusza `disabled`, hálózati próba nélkül. A Power Wall/Tuya API, közös
MQTT publisher és a külön védett Tuya fogyasztó is védi az AI-aljzatot, utóbbi a
fizikai device ID-t is ellenőrzi. Átnevezés vagy közvetlen MQTT ID-alias sem oldja
fel a tiltást. A poller telemetria-/fingerprint kódja változatlan: ez nem HC-32 javítás.

**Mentés:** heti AI, Git/Gitea/offsite és restic/check API, runner, közvetlen worker
és timer szinten letiltva. A tárolt operatorbeállítások megmaradnak, a remote mód
effektíven kikapcsolt. Elavult remote queue-kérés őszinte failed/elutasítást kap.
Helyi archívum/DB-mentés, leltár/összehasonlítás és staging restore marad.
Az éles webes fájlrestore/recovery is tiltott, hogy egy régi script-visszaállítás
ne kerülhesse meg a profilt. A canonical legacy wrapperek csak az inaktív
csomagban cserélődtek: az élő watcher/hostscript most változatlan.

**Csomag és rollback:** külön backend/frontend/Tuya és backend-rollback image,
r4 ingest; rollbackben r3 ingest. A rollback megtartja a kötelező profilt, az F6
lockot, a védett Tuya image-et és az additív DB-sémát/app/reader szerepköröket.
Nincs automatikus dump-restore vagy korlátozás nélküli régi backend/poller fallback.
37 hostfájlra átadási leltár, csak olvasó integritás- és preflight helper készült.

**Ellenőrzés:** teljes backend **756 teszt, 0 failure/error/skip**, minden PG
opt-innal; végleges profilkör **19 teszt, 0 hiba** (átfed, nem összeadandó).
Frontend **98 teszt és production build sikeres**. Valódi owner/ACL-megőrző
izolált dump-restore és saját PG/PgBouncer/MQTT mellett **release → rollback →
release**: health/UI/ingest/reader és operatorbeállítás-hash rendben.
Mindhárom fázisban backend tiltott AI-kérésből 0 MQTT-parancs; a kontroll átjutott.
Nyers MQTT-ből érkező AI név/ID-alias kérésekre a tényleges poller 2 elutasítást
adott, **0 AI-aktuátorhívással**, míg a kontrollon 1 hívás történt. Az aktuátor-
transzport szintetikus, fizikai AI-próba nem történt. A valódi r6 age-bundle
visszafejtése és 12/12 titkos fájl összevetése sikeres, 0600 módokkal, törölt tmpfs-szel.

**Tesztkörnyezeti pontosítások:** a fake parancsokhoz futtatható tmpfs kellett;
a HC-39 fixture a labor dump-restore-jához előre létrehozott szintetikus szerepkörök
explicit adoptálása után futott, termékkód-lazítás nélkül. Külön referencia-DB
igazolta, hogy a kezdeti konfigurációs hash-eltérés csak a származtatott
`irrigation_solar_pump_config.latest_decision` futási állapot frissülése volt;
ezt a teszt az operatorbeállításoktól külön kezeli. A broker megfigyelése a cél/
kontrolltopicokra szűrt a megengedett másaljzat-forgalom miatt. A fake runpy adapter
/app importútja javítva; fogyasztói döntés/aktuátorhívás és MQTT-válaszkézbesítés
külön bizonyíték. Más auditpont javítása ezekből nem következik.

**Megmaradó határ:** HC-31 fizikai próba az SSD javítása után; HC-45 valódi üres
VM/systemd/offline-kulcs full restore/repeat/rollback továbbra is hiányzik. A friss
gépes full restore nem része a minősített, meglévő hostos korlátozott átadásnak.
Nincs feltétel nélküli teljes kiadási jóváhagyás. Friss helyi pre-cutover mentés,
privilegizált hostátadás és külön élesítési utasítás kell a tényleges váltáshoz.

Részletek: [korlátozott r6 kiadás](docs/hc-ai-offline-release.md).
Privát nyom: `/tmp/hc-ai-offline-20261027/`; tartós összesítések az r6 `evidence/`
könyvtárában. Az auditpontok összesítése változatlan.

**Megőrzött éles baseline:** a végellenőrzés a már éles `hc-opening-events-20261027-r4` backendjét azonosította. A nyitásérzékelős safety-fájl futó/kiadási/munkafai SHA-ja egyezik. A végleges r6 és rollback is ezt a pontos fájlt tartalmazza. A korábban lezárt, még inaktív r5 csomag külön `SUPERSEDED.json` jelölést kapott, és nem élesíthető ajánlott csomagként; nem írtuk felül a fagyasztott image-eit. A preflight a live baseline megváltozását is ellenőrzi.

Az r6 végső képellenőrzésében a kiadási és a rollback backend **67/67 célzott safety-tesztje sikeres**, a nyitásérzékelős javítás fájl-SHA-ja a már élessel azonos. Az r6-tal ismételt izolált release/rollback/release kör is sikeres; a rollback sem vonja vissza ezt a már éles javítást.

## REPAIR-027 — korlátozott r6 élesítése a meglévő HC hoston

**Dátum:** 2026-10-27. **Engedély:** a felhasználó kifejezetten kérte a
korlátozott élesítés megkezdését biztonsági intézkedésekkel. Az r6 `ai-offline`
profilban éles. Más auditpont automatikus javítása vagy lezárása nem történt.

**Visszaállási pont:** friss privát DB-dump/globals, config/env/titok és
system/user unit-előállapot, valamint offline kiadási/rollback image-mentés.
A friss dump teljes owner/ACL-megőrző visszatöltése izolált, hálózat nélküli
PG16-ba sikeres: **6 832 809 mérési rekord**. A próbakonténer/kötet eltávolítva.
A helyi privát mentés és SHA-k az átadási könyvtárban megmaradnak.

**Átadás:** régi system/user timerek/watcherek felfüggesztve, régi AI-marker és
queue-előállapot elkülönítve; régi backend/ingest/poller leállítva. 37 fagyasztott
hostfájl, kötelező policy.py/json és előkészített env átadva. Explicit
**059/060/061** és app/reader provision sikeres, baseline/seed/adatdobás nélkül.
PgBouncer/backend/frontend/ingest/védett Tuya rögzített image-ekkel újraindult;
az eredeti PostgreSQL és MQTT konténere megmaradt. Az aktív override csak a
sikeres átvétel és webes helyi mentés után váltott r6-ra.

**Felmerült telepítési hiba:** az első F6 futás a legacy, kizárólag wants-linkként
létező user timerek letiltásánál hibát kapott; az installer visszaállította az
installed unitokat. A két user timer hagyományos, kikapcsolt definícióként
megőrizve, ismételt F6 telepítés sikeres. Unit-hashek, enable/active állapot és
következő trigger egyezik; duplikált user timer nincs. A fagyasztott csomag és
termékkód nem változott. Napi helyi mentés: **02:15 CET**, logkarbantartás:
**03:30 CET**; AI-weekly/restic letiltva, közös helyi webes queue aktív.

**Éles ellenőrzés:** DB/MQTT health, UI, SQL Lab séma, `hc_app`/`hc_lab` login és
reader ACL rendben; ingest heartbeat friss, mérések tovább gyűlnek. Nyolc
operator-konfiguráció hash és a tárolt mentési settings változatlan. Safety ACK
ideje változatlan, snapshot friss; átvételkor idle/latch=false, automatikus ACK
nincs. A már éles nyitásérzékelős safety-javítás pontos SHA-ja megmaradt.
Az új konténerek indulási naplóiban nincs traceback/permission/schema/critical
hiba; újraindulásszámuk az átvételkor 0.

**Mentési próba:** valódi webes HTTP202 → queue → systemd → runner → completed/0,
local_only. Az első archívum **125 536 331 bájt**, **879** belső checksum rendben,
0600 mód, távoli cél nem futott. Az aktív override átállítása után külön végső
helyi checkpoint is sikeres: **125 529 412 bájt**, 879 checksum. Az archívumban
az aktív r6 hivatkozása, a privát env és a kötelező hostprofil pontos tartalma
is ellenőrizve. Eredmény: `local-backup-verified.json` és `deployment.json`.

**Rollback:** kézi, kompatibilis `rollback.py` helper készült; megtartja az AI-
tiltást, védett r6 Tuyát, F6 lockot, app/reader env-et és az additív sémát.
Nem tölt vissza dumpot és nem törli az új méréseket. A kiadás/rollback képekkel
korábban izolált release→rollback→release próba sikeres; az éles rendszeren most
nem indítottunk szükségtelen visszaváltási kört. A helper és a hostátadási
szkriptek szintaktikai ellenőrzése sikeres.

**Nyitva marad:** HC-31 fizikai AI-próba az SSD javítása után, HC-45 teljes
üres VM/systemd/offline-kulcs hostrestore-próba. Fizikai AI-parancs/új kapcsolat
nem indult. AI-vezérlés, távoli mentések és webes in-place restore/recovery
tiltott; helyi mentés és staging restore használható. A mai dump-visszatöltés
nem teljes host/boot minősítés. Az eredeti auditdokumentum változatlan.

Tartós bizonyítékok, privát előállapot és visszaállási leírás:
[éles r6 átadás](backups/deployments/hc-ai-offline-20261027-r6/DEPLOYMENT.md).

## REPAIR-028 — HC-08: atomi scheduler-audit és külön klímavégrehajtás

**Dátum:** 2026-10-27. **Státusz:** helyileg javított, izolált környezetben
ellenőrzött; **nincs élesítve**. Kizárólag HC-08; audit F4 és F0, kapcsolódó
F2/F3 előfeltételek átolvasva. Forrásbizonyíték: az eredeti audit HC-08 és
app/scheduler függvényhivatkozásai, továbbá az M.7 láncleltár korlátja.

**Reprodukció:** a mentett régi klímametódus fake transporttal a publish-t az
execution insert elé tette; régi app callback már létező scheduler_run után
nem folytatta a hiányzó láncot. Az éles READ ONLY leltárban 295 scheduler-run,
292 event/plan/execution, három 2026-07-13-i run-only lánc (X10 start, öntözés
start/stop), 0 duplikált scheduler-plan/execution. A régi audit 0 event→plan
hiánya nem jelentett 0 run→event hiányt. A leltár egy régi `physical_manual`
sessiont is mutatott; ezt nem módosítottuk, és nem tekintjük friss fizikai
öntözés bizonyítékának. Bevezetés előtt külön állapotegyeztetéshez rögzítettük.

**Változás:** új `scheduler_audit.py`, célzott app/scheduler/startup bekötés.
Egy idempotenciakulcshoz tartozó run→event→plan→execution egy rövid, READ
COMMITTED tranzakcióban készül, tranzakciós advisory lockkal és egyetlen
kapcsolattal. Hiba visszagörgeti a teljes új láncot. A már létező run nem állítja
meg a pótlást; a mentett eredeti payload marad mérvadó. A régi hiányokat
perc-/napváltástól független, 50-es recovery-batch pótolja. Duplikált hivatkozást
nem választ ki önkényesen, hanem explicit egyeztetési hibát jelez.

A klímás audit-építő csak tartós szándékot készít; nem publikál és nem kapcsol
Power Wall eszközt. A snapshot olvasása a foglalási tranzakción kívül történik.
Külön, hibahatárral védett startup callback küldi a klímás szándékot. Az aktuális
domain/global flag, rögzített topic és esedékességi perc ellenőrzése után egy
atomi claim `unknown/attempt=1` állapotot commitol **a küldés előtt**. Csak a
biztosan lezárt claim enged I/O-t; elveszett commit-válasz nem. A publish és a
meglévő ventilátorszinkron tranzakción kívül történik. A sikeres publisher-válasz
`sent`, nem fizikai nyugta; hibás/bizonytalan eredmény `unknown`. Ezek nem
automatikusan újraküldhetők. Lejárt vagy tiltott pending szándék `blocked`.

A legacy hiányzó execution kimenete nem állapítható meg biztosan: az új pótlás
`unknown`, replay-tiltással és az eredeti requested_at szerinti created_at-tal.
Ez az X10/öntözés aktuális végrehajtóitól is elkülöníti a régi auditpótlást.
Meglévő teljes láncot/eredményt nem írunk át. Új SQL-migráció nincs.

**Ellenőrzés:** **282 kapcsolódó teszt, 0 failure/error/skip**, ebből 25 új,
valódi PG16-os HC-08 eset korlátozott `hc_app` kapcsolaton. Lefedés: hiba mind
a négy insert után négy domain/action ágon; független kapcsolatok versenye;
audit-/claim-/eredménycommit válaszvesztése; publish előtti/utáni process-crash;
timeout/false reply; eredményírás és másodlagos Power Wall hiba; tiltott domain
és globális flag; lejárat; ismételt tick/restart; napi és ismétlődő DST-perc;
legacy részlánc, duplikáció és hiányzó tábla; külön startup callback/safety-hibahatár.
A kapcsolódó HC-03/04 SQL-, öntözés/stop/recovery-, klímaablak-, safety-, MQTT-
és AI-offline profilregresszió is sikeres. A 282 célzott kör, nem új teljes
backend/frontend minősítés.

A valódi auditadatok konzisztens, izolált másolatán a végleges kód mindhárom
régi hiányt pótolta: +3 event/+3 plan/+3 execution, +0 run; minden eredeti sor
változatlan. Második recovery: 0 hiány; **0 publish, 0 Power Wall hívás**.
A teszteknek nincs éles LAN/Docker-socket/hostport elérésük. A saját tmpfs-es
teszt-DB a munka végén eltávolítva. Szintaktikai ellenőrzés sikeres.

**Függőségek és bevezetés:** HC-09/F3 fizikai visszaigazolás és transporttimeout
továbbra is nyitott; a `sent` kizárólag a meglévő publisher válaszát jelenti.
X10 confirmation, MQTT-kliens, binding/ventilátor HC-35/36 nem lett javítva.
HC-03/04/07/38/39 meglévő szerződéseire építünk; a physical_manual kivétel
megmarad. Új backendhez az app/scheduler/startup/modul együtt telepítendő,
régi scheduler-writerrel párhuzamos átadás nem megfelelő. Nyitott/unknown fizikai
művelet mellett automatikus rollback nincs; előbb állapotegyeztetés. Adatot,
auditot és uncertain állapotot dump-restore/újraküldés nem törölhet.

**Éles állapot:** a futó r6 konténerek és aktív hosthelper/unitforrások változatlanok;
nem futott éles backfill, migráció vagy eszközparancs. Az eredeti audit SHA-ja
változatlan. Részletes működés/rollback és tartós bizonyíték:
[HC-08 javítás](docs/hc-08-repair.md).


## REPAIR-029 — HC-09: transport, befogadás és friss eszközmegfigyelés

**Dátum:** 2026-10-27. **Állapot:** helyileg javítva és ellenőrizve, nincs
élesítve. Kizárólag HC-09 kapott új javítást/státuszt; az eredeti audit megmaradt.
Áttekintve a HC-09 bizonyítéka, az F2 transport-/stop-határ, az F3 friss
forrásminta és az F4/HC-08 tranzakciós függőség.

**Módosítás:** a generikus MQTT-publish a várakozás után `is_published()`
értéket is ellenőriz. Timeout/kivétel bizonytalan eredmény, a cleanup ágak
függetlenek. Új retry nincs; a meglévő safety és stop korlátai megmaradtak.
A klíma tartós küldési foglalásához execution-korreláció és megfigyelési
időhatár társul. A `sent`, `accepted`, `confirmed` és `unknown` külön állapot;
friss fizikai állapot nélkül a transport/bridge sikere nem lesz confirmation.

Az X10 heti szinkron atomi run/event/plan/execution szándékkal, közös lockkal
és egyszeri olvasási kéréssel indul. Friss eltérés és megfelelő engedélyek
után legfeljebb egy programírás következik, commit után. Válaszvesztés vagy
restart nem ad replay-jogot. Csak a roboton tárolt program friss egyezése
igazolható, a takarítás teljesülése nem. A kapcsolt egyedi auditok pontos
illeszkedését és saját időhatárát is ellenőrizzük; nincs tömeges sikerjelzés.

A bridge-ek additív `sampled_at`/`reported_at` mezőket és korrelációt kaptak.
Az X10 új, nem retained `scheduler/observation` topicja minden sikeres,
feldolgozható eszközolvasáskor kimegy; a régi topicok megmaradnak. Hibás
olvasat nem lesz friss minta. A forráskorhoz hozzáadódik az MQTT-fogadás óta
eltelt idő; régi, retained, korábbi kapcsolatból maradt, jövőbeli, hiányos
vagy szándék előtti minta nem igazolhat eredményt. A diagnosztikai fogyasztók
is ezt követik. Kezdeti, konfigurálható korhatár 90 s, külön confirmation
határidő 120 s; a Nano saját korhatárai és parancstimeoutjai változatlanok.

**Ellenőrzés:** 330 kapcsolódó teszt, 0 failure/error/skip. Ebből 48 új HC-09
eset: 23 valódi PG16/hc_app teszt, 6 bridge-függvénypróba, 19 transport és
frissességi teszt. Ellenőrizve a timeout tényleges Paho 2.1.0 példánnyal,
a sikeres transport/eszköz-visszajelzés különválása, retained/reconnect,
forráskor+MQTT-késés, késő válasz, hibás/nulla értékek, két DB-kapcsolat,
négy insert hibahelye, commit-válaszvesztés, MQTT közbeni crash,
eredménymentési hiba, restart, kapcsolt audit és tiltott/aktív domain.
A meglévő HC-01–08, safety/stop és AI-offline regressziók is sikeresek.
A labor network-none PG16 névterében futott, hostport/LAN/Docker socket
nélkül; a saját konténerek és tmpfs DB törölve.

**Éles változatlanság:** 9 konténer ID/image/start/restart, 37 aktív hostfájl,
az éles safety-forrás és az eredeti audit hash-e egyezik. DB/MQTT health jó,
AI-offline profil megmaradt. Nem küldtünk éles eszközparancsot; nem történt
migráció, éles auditpótlás vagy kiadás. A forrás Compose két additív env-je
nem módosítja a fagyasztott r6 konfigurációt.

**Függőség/korlát:** HC-08 helyi javításával és mindkét bridge-del összehangolt
későbbi kiadás szükséges; régi bridge nem szolgáltat elfogadható új nyugtát.
Új migráció nincs. HC-12/13 worker/határidő, HC-35/36 ventilátor/binding külön
nyitott pont marad. A korábbi physical_manual session 125 egyeztetése, a
felügyelt klíma-/robotpróba és a késések mérése kiadási feladat. Az AI/VM
próba nem történt meg. Bizonytalan szándékot és történeti confirmed sort nem
írtunk át; rollback előtt a függő műveleteket egyeztetni kell, az auditadatokat
meg kell őrizni.

Részletes szerződés és rollback: [HC-09](docs/hc-09-repair.md).
[Tartós, titokmentes bizonyítékok](docs/audit-evidence/hc09-20261027/).


## REPAIR-030 — X10 térképfrissítés és kommunikációs beragadás

**Dátum:** 2026-10-27. **Állapot:** helyileg javítva és ellenőrizve, nincs
élesítve. Felhasználói hibaanalízis alapján célzott X10-javítás. Az eredeti
audit változatlan; a HC-12/13 teljes feladata nem kapott lezárt státuszt.
Az összesítés marad 25 ellenőrzött, 22 nyitott, 1 ellenőrzésre váró pont.

**Módosítás:** közös `x10_runtime.py` mögé került a bridge összes MIIO-kérése
és a külön mapfolyamat robotlekérdezése. Szálzár + közös fájlon tartott
folyamatközi `flock`; alapból 30 s teljes zárvárakozás és 20 s híváshatár,
független hibaági zárfelszabadítás. Nincs automatikus MIIO-parancsismétlés.
A python-miio TypeError hibás művelet marad, nem siker; csomagverzió nem
változott. A mapexport 120 s-os határán a gyermekfolyamatcsoport is leáll.
Hibás/hiányzó státuszminta nem frissíti a watchdogot; tokent a transporthiba
nem exportálhat. Az MD5 csak sikeres térképexport után frissül, így a korábbi
sikertelen exportot a következő meglévő térképellenőrzés újrapróbálhatja.

A külön watchdog a főciklust, a sikeres státuszt és csak aktív követéskor a
sikeres élőtérképet külön figyeli. 300 s elmaradás után a következő 5 s-os
ellenőrzés 75-ös bridge-kilépést kezdeményez; robot-/MQTT-I/O és szálra várás
nélkül. A meglevő Docker/systemd restartpolicy végzi az újraindítást.
A limitek konfigurálhatók és ellenőrzöttek. A közös MIIO-zár nem terjed ki
más, azt nem használó alkalmazásra; a cloud/renderelés nem foglalja a zárat.

**Ellenőrzés:** 31 új célzott teszt az éles X10 image függőségeivel, teljes
bridge/map importpróbával; 52 HC-09/MQTT/scheduler regresszió. Összesen
83 sikeres, 0 failure/error/skip. Valódi kétfolyamatos lockpróba, CLI-timeout,
zártulajdonos megölése utáni folytatás, processzcsoport és gyermek leállítása,
watchdog 75-ös tényleges folyamatkilépés, hibás/friss státusz, élőtérkép-ágak,
MD5-hiba utáni újrapróbálás és invalid konfiguráció is ellenőrizve.
A tesztkonténerek hálózat nélkül, root/Docker socket nélkül futottak és törölve.
Nem volt valódi robot-/cloudpróba vagy konténer-restart az éles oldalon.

**Éles változatlanság:** a feladat előtti/utáni X10 konténer ID/image/start/
restart egyezik. A 9 éles konténer és 37 aktív hostfájl a HC-09 checkpointtal
is egyezik; DB/MQTT health jó, AI-offline profil és safety-forrás megmaradt.
Az X10 meglévő `unless-stopped` restartpolicy-ja olvasással ellenőrizve.

**Kiadás/függőség:** runtime-modul, bridge, map helper és config együtt
szükséges; DB-migráció nincs. A helyi bridge HC-09 módosításait is figyelembe
kell venni a későbbi rögzített kiadásnál. Felügyelt státusz-/pozíció-/két
szintes térképátvétel és kompatibilis korábbi image/config megőrzése szükséges.
A watchdog határa éles késésméréssel finomítható; tartós hálózati/cloudhibát
az újraindítás önmagában nem javít meg. A HC-12/13 többi része nyitott marad.

[Szerződés és visszaállás](docs/x10-map-repair.md),
[tartós bizonyítékok](docs/audit-evidence/x10-map-20261027/).


## REPAIR-031 — HC-08/09 és X10: inaktív r7 kiadás előkészítése

**Dátum:** 2026-10-27. **Állapot:** szoftveres csomag előkészítve és laborban
ellenőrizve, **nincs élesítve**. A felhasználó előkészítést kért. A teljes
éles átadás blokkolt a működésre várt Nano telemetriahiánya és a 125-ös fizikai
kézi session egyeztetése miatt. Az éles r6, a 9 ellenőrzött konténer és a 37
aktív hostfájl megmaradt. Más auditpont státusza nem változott.

**Előkészített:** külön `hc-scheduler-x10-20261027-r7` csomag, immutable
backend/Gree/X10 image-ek és minimális offline buildcontext; kötelező AI-offline
profil és pontos éles safety-forrás megőrizve. Release/rollback Compose,
privát env-másolat, alapból olvasó preflight és külön explicit alkalmazási út.
Az átadás csak a három writert cseréli; új migráció vagy host-unit telepítés
nincs. A visszaállás az előző három image-re történik, minden V2 indítási flag
0 mellett, a safety és stop megtartásával. Bizonytalan parancsot nem játszik
újra, adatbázist és auditadatot nem állít vissza/töröl. Backendhiba esetén is
használható a rögzített, korlátozott rollback.

**Javított HC-09 integrációs eltérés:** az X10 olvasóparancs helyes topicja
`command/read_scheduler`. A korábbi `command/scheduler` nevet a bridge nem
kezelte. A hívó, kapcsolódó PG-tesztek és aktuális HC-09 szerződés javítva;
az új valódi brokeres/bridge-próba a két tényleges oldalt kapcsolja össze.
A történeti HC-09 bizonyíték változatlan, az új diff az r7 csomagban szerepel.

**Ellenőrzés:** 330 backend-, 31 X10- és 14 átadási kaputeszt, 0 failure/error/
skip. Valódi release → rollback → release labor, minden fázisban a megfelelő
backend és mindkét megfelelő bridge-image, hálózat nélküli PG16, PgBouncer
és broker, szintetikus eszközök. A scheduler automatikus worker a laborban
ki volt kapcsolva, a protokoll explicit hívással futott. X10 read/diff/
egyetlen írás/friss confirmation, Gree korrelált friss confirmation,
eszközfogyasztó nélkül unknown/no-replay és küldés nélküli történeti pótlás
sikeres. Kezelői konfiguráció, safety ACK, mérési sorok és bizonytalan execution
mindhárom fázison megmaradtak. Nem volt éles hardver- vagy teljes VM-próba.

**Mentések:** friss privát dump és szerepkörleltár valódi owner/ACL-visszatöltése
sikeres, 6 840 083 mérés. Új helyi F6 archívum completed/0, 125 776 325 bájt,
belső checksumok rendben; kizárólag helyi cél. A hat új/előző image 0600 offline
tarban elmentve. Pontos archívumnév/hash és eredmények a csomag `evidence/`
könyvtárában; titkos adat csak a 0700 privát könyvtárban.

**Éles kapu:** a felhasználó szerint a vezérlőnek működnie kellene, ezért a
hiányzó Nano STATUS/TELE nem jóváhagyott téli kivétel. Az utolsó ESP-diag Nano
offline/UART-hibát, UNKNOWN/CONFLICT szelepállapotot, sok timeoutot és eltett
SUPPLY_LOW kódot jelzett; ez utóbbi nem friss feszültségmérés. A 125-ös sort
nem zártuk le, szelepparancs nem ment ki. Helyszíni táp/UART-ellenőrzés és
friss állapotegyeztetés kell. A helper valós, friss adatok alapján enged vagy
tilt, nem a téli profilból következtet zárt szelepre. Későbbi váltáskor új,
legfeljebb 30 perces helyi mentés szükséges. HC-31/45 és HC-12/13/35/36
korlátai változatlanok; 25 ellenőrzött, 22 nyitott, 1 ellenőrzésre váró pont.

[Előkészítés](docs/hc-r7-preparation.md),
[csomag/runbook](backups/releases/hc-scheduler-x10-20261027-r7/DEPLOYMENT.md).


## REPAIR-032 — HC-08/09 és X10 r7: ellenőrzött élesítés

**Dátum:** 2026-10-28. **Állapot:** éles, az aktív override az r7 csomagra mutat.
A felhasználó a Nano újraindítása és a kézi szelep elzárása után kifejezetten
engedélyezte az átadást. Friss online STATUS/TELE igazolta a két CLOSED szelepet;
a 125-ös fizikai kézi sessiont a meglévő ingest lezárta. Nem történt kézi SQL-es
státuszfeloldás vagy szelepparancs. A teljes előellenőrzés akadály nélkül lefutott.

**Mentés és átadás:** új F6 helyi archívum completed/0, 126 200 875 bájt,
belső checksumok és lefedettség ellenőrizve. Az r7 helper kizárólag a backend,
Gree és X10 rögzített image-eit cserélte, majd friss forrásminták, health,
kezelői konfiguráció, safety ACK/latch és mérésmegőrzés ellenőrzése után
aktiválta az override-ot. Új migráció nincs. Hat megőrzendő konténer ID/image/
indulás/restart változatlan; 37 aktív hostfájl és a privát env hash rendben.
A téli és a kötelező AI-offline profil, valamint a safety-forrás megmaradt.

**Éles ellenőrzés:** friss Nano/Gree/X10 adatok, zárt szelepek, üres aktív
sessionlista; a robot töltőn. Mindhárom szint mentett PNG-je elérhető. Három
júliusi shadow auditot az indulási láncpótlás `unknown` állapotban helyreállított,
parancs-replay nélkül; a történeti küldés bizonytalanságát megőriztük.
Új, tényleges függő végrehajtás nem látszott. A külön olvasó ellenőrző
ékezetes URL-kezelését, történeti auditbesorolását és host-Python időbélyeg-
feldolgozását javítottuk; az első eredmény megmaradt, az alkalmazáskód nem változott.

**Korlát:** az X10 Xiaomi-felhős térképletöltése `Failed to get file URL: None`
hibát ad. Az érintett letöltési függvények az előző és az új image-ben azonosak;
a hiba kezdetét ez nem bizonyítja. A helyi robotstátusz működik és a mentett
térképek megmaradtak, új felhős térképátvétel nem igazolt. Ezt külön jeleztük,
nem javítottunk automatikusan más auditpontot. Fizikai takarítás/szintváltás,
öntözési és klímakapcsolási próba nem indult. HC-31/45 és a többi nyitott
auditpont státusza változatlan.

**Visszaállás:** az előző három immutable image és offline mentésük megmaradt.
Az r7 rollback helper állít vissza AI-offline profillal és négy tiltott V2
indítási flaggel, a safety/stop megtartásával. Nincs DB-restore, auditadat-törlés
vagy parancs-replay. [Élesítési dokumentáció, bizonyítékok és pontos parancsok](backups/deployments/hc-scheduler-x10-20261028-r7/DEPLOYMENT.md).


## REPAIR-033 — HC-10: generációvédett cache és összehangolt invalidálás

**Dátum:** 2026-10-28. **Állapot:** ellenőrzött helyi javítás, **nincs élesítve**.
Elolvasva a HC-10, H.1/B.5/B.6 bizonyíték és az F9 teljes lépése. Az eredeti
race öt cache-útvonalon reprodukálva; invalidálás után mindegyik régi értéket
adott vissza és tárolt. A kiindulási kód külön másolatban, az audit változatlan.

**Javítás:** közös ReadModelCache, generációellenőrzés, kulcsonként egy builder,
lockon kívüli adatépítés/másolás és hiba utáni felszabadítás. Invalidált eredményt
nem szolgál ki és nem tárol; három megszakított build után explicit hiba,
Contextben ok=false, cache-elés nélkül. TTL a build végén, védekező másolatok,
force-összevonás. A Context/API/öntözési belső cache ugyanazt a mechanikát használja.
Hat legacy get/build/set payload védett builderhívásra vezetve; az app közös
cache-t injektál. A Context, API-prefix és közvetlen domain-invalidálás mindkét
réteget törli. Pilot/weather együtt atomi; a tartály MQTT-topicja is invalidál.

Az öntözési Context alatt nincs második snapshot-cache; a Context tulajdonos
megőrzi az IRRIGATION_SNAPSHOT_CACHE_TTL alapértelmezett 10 s értékét. Néhány
Context builderből redundáns ApiCache-wrapper kikerült, a drága statisztika
és a pilot/időjárási cache megmaradt. A fizikai vezérlési kapuk változatlanok.

**Ellenőrzés:** 290 különböző teszt, 0 failure/error/skip, ebből 24 új cache-teszt.
Izolált, hálózat nélküli futás az r7 függőségeivel; nincs éles DB/MQTT/socket.
Öt eredeti barrieres race javítva; 12 párhuzamos kéréshez egy builder, force,
lassú build, invalidálás, hiba→helyreállás, prefix/all, viharhatár, másolás,
valós app-invalidátorok és atomi pilot/weather igazolva. Tíz szintetikus payload,
SQL/paraméter-ujjlenyomat és hideg/meleg query-counter előtte/utána azonos.
Hat builder számítási ága és 152 SQL-hívás AST-je változatlan. Azonos, hat kéréses
TTL-workload mindkét verzióban három alapbuild. Ez nem éles p95/WAL-mérés.

**Éles változatlanság:** kilenc konténer ID/image/indulás/restart és 37 hostfájl
megmaradt, aktív r7, DB/MQTT health és AI-offline profil rendben. Új migráció,
függőségfrissítés, hardverparancs vagy telepítés nincs.

**Függőségek:** HC-14/40 összesítés-/diagnosztikaírás, HC-21 AI-payload,
HC-22 frontendválasz-sorrend és HC-13 teljes builder/I/O-határidő nyitott.
F9 nem zárult le, más auditpont státusza nem változott. Bevezetéshez a kilenc
érintett backendmodul együtt, új külön kiadási csomagban szükséges; a lezárt
r7 változatlan. Rollback tiszta kód-/backend-image visszaállás, DB-restore nélkül.

[Részletes szerződés és korlátok](docs/hc-10-repair.md),
[tartós bizonyítékok](docs/audit-evidence/hc10-20261028/summary.json).


## REPAIR-034 — HC-13/14/21/22/40, helyi javítás (2026-10-28)

**Hatókör és bizonyíték:** az öt megállapítás, B.5/B.6, K.3, N.3 és az érintett
F9/F10 lépés átolvasva. Kiindulás a HC-10 helyi cache-javítása; az eredeti audit,
az éles r7 és annak fagyasztott csomagja változatlan.

**Javítás:** explicit háttérszál-tulajdonlás, ciklus/siker/hiba/beragadás státusz,
stop-event és korlátos join; egypéldányos vezérlés, 1/8 Gunicorn, preload tiltása.
Ismert hosszú kérésekhez 2 WS + 1 AI + 1 backup + 1 diagnosztika kapacitás,
túllépéskor 503; néma stream bontása és valódi Docker-/AI-határidő.
Beragadt feladat a helyét és a vezérlőzárat tényleges befejezéséig tartja.
A summary-frissítésnek külön worker a gazdája; siker után indul a TTL,
DB-hiba után nincs 300 s-os kihagyás. Bemeneti időablak és megelőző határminta
az öt régi napi képlet körül, késői adatot is újraszámoló teljes ablak.
Solar-pump értékelés írásmentes; friss döntés a read modelben, változatlan
fizikai start/stop/run-audit. AI-kérés besorolása adatépítés előtt, célzott
szekciók és közös determinisztikus HC-válaszmodul a proxyban/szerverben.
Frontend GET: 15 s teljes timeout, közös path-/generációgazda, read-after,
referenciaszámlált megszakítás, path/unmount/visibility védelem.

**Ellenőrzés:** 377 külön backend- és 109 frontendteszt, 0 failure/error/skip;
23+11 új teszt, sikeres frontendbuild és önálló AI-csomagimport. Valódi izolált
Gunicornban 2 WS + 3 lassú kérés mellett 64/64 vezérlési GET sikeres,
p95 7,72 ms; kapacitástúllépés és néma pump-stream bontása igazolva.
SIGTERM exit 0, saját háttérszál nélkül.

Izolált PG16 restore 6 840 083 mérési sorral: 15 nézet-/ablak- és 30 határ/DST/késői
minta-összehasonlítás azonos; read-only snapshot/statisztika/értékelés sikeres,
a régi értékelés negatív kontrollként íráson elbukott. Azonos 20 GET-workload:
DB-wrapper 381→360, diagnosztikai UPDATE 20→0, GET-summary UPSERT 5→0,
WAL 264352→0 byte. A háttérfrissítés továbbra is elvégzi az összesítést:
200 napos refresh 30,33 s az 1 GiB/2 CPU friss restore-on; ez nem eltűnt DB-munka
vagy éles p95. Nyolc stabil payloadszekció azonos. A döntési képlet és a négy
fizikai/audit metódus AST-je változatlan az eltávolított UPDATE kivételével.

**Éles változatlanság:** 9 konténer ID/image/indulás/restart, 37 hostfájl,
safety-forrás, 64 migráció, npm lock és audit megmaradt. Nincs fizikai parancs,
telepítés vagy függőségfrissítés. A tesztkonténerek és saját DB-kötetük eltávolítva.

**Függőségek/korlátok:** HC-10 helyi forrással együtt csomagolandó. HC-07/38/39
alap változatlan; új migráció nem kell. AI-engedélyezéskor a szerver új közös
moduljai is szükségesek; SSD/HC-31 fizikai próba továbbra is függő.
HC-45 VM/systemd próba és F10 többi auditpontja nem kapott javítást/lezárást.
Nincs teljes böngészőmotoros, online provideres vagy tartós üzemi terhelési próba;
az önkényesen beragadt Python-/DB-művelet nem vált erővel megszakíthatóvá.
F9/F10 teljes fáziszárás nincs. Bevezetés: új fagyasztott csomag, friss mentés,
egyetlen vezérlő, backend/frontend smoke. Rollback: előző image-ek, DB-restore
és fizikai/audit replay nélkül. **Az öt tétel szoftveres státusza Ellenőrzött;
nincs élesítve.** Más auditpont státusza nem változott.

[Részletes javítás, mérés és rollback](docs/hc-13-14-21-22-40-repair.md),
[tartós bizonyítékok](docs/audit-evidence/hc13-14-21-22-40-20261028/summary.json).


## REPAIR-035 — HC-10/13/14/21/22/40 r8 élesítése (2026-10-28)

**Felhatalmazás:** a felhasználó kérte a teljes előkészítést és az élesítést.
A tényleges r7 backend/r6 frontend image-ből, kizárólag a hat pont forrásaival
új, külön csomag készült. A többi hét szolgáltatás és a 37 védett hostfájl megmaradt.
AI-offline/téli profil, safety-forrás, konfiguráció és nyugtázás változatlan.

**Előkészítés:** 377 backend-, 109 frontend- és 9 átadási teszt sikeres;
production build; kész nginx/frontend/backend Chromium 8 nézet/0 JS-hiba;
tényleges r8→r7→r8 laborpróba ugyanazon, owner/ACL-es 6 840 083 méréses restore-on.
F6 local-only mentés completed/0, teljes helyi lefedettség és belső checksumok
ellenőrizve: `homecontrol_2026-10-28_20-14-08_c96b70f2104a4135aee5ffcc64009a40.tar.gz`.
Négy immutable release/rollback image privát offline tarban megőrizve.
A kezdeti kapu hiányzó math-importot fogott a helperben, éles leállítás nélkül;
javítás, új frissességteszt és dokumentált újralezárás után a kapu ready=true.
Az alkalmazás-image-eket ez nem módosította.

**Élesítés: 20:20:59 CET.** A helper közös backup-lock alatt megállította a
régi backendet/frontendet, csak az új két szolgáltatást indította, majd sikeres
health/profil/config/ACK/mérés/image/frontendszolgálás/summary-worker ellenőrzés
után aktiválta az override-ot. Nincs párhuzamos vezérlő, DB-restore vagy replay.
Automatikus rollback nem kellett. Az éles utóellenőrzés és nyolc Chromium-nézet
sikeres: 0 JS-hiba, 38 sikeres tényleges API-olvasás, módosító kérések tiltva.
Minden engedélyezett worker fut és halad; Nano friss, online, szelepek CLOSED,
aktív öntözés/új függő execution nincs. A három júliusi unknown audit változatlan.

**Rollback:** az r8 saját `scripts/switch.py rollback --apply` helperje az előző
pontos backend/frontend image-et állítja vissza, a hét másik szolgáltatás,
DB-adatok, auditok és meglévő r7 V2 flag-ek megtartásával. Az r7 saját régi
helperje r6-ra vinne vissza; ehhez az átadáshoz nem az használandó.
Új migráció és függőségfrissítés nincs. AI-SSD/HC-31, HC-45 VM/systemd és a
Xiaomi-felhő korábbi korlátja megmarad; más auditpont státusza nem változott.

[Éles átadás, ellenőrzés és rollback](backups/deployments/hc-read-models-20261028-r8/DEPLOYMENT.md),
[fagyasztott csomag](backups/releases/hc-read-models-20261028-r8/DEPLOYMENT.md).

Éles olvasási kontroll: négy új snapshot/statisztika GET sikeres, köztük három
force context-build; a szivattyúkonfiguráció UPDATE-számlálója a 147,31 s-os
megfigyelési ablakban 1 167 250 maradt. Új diagnosztikai konfigurációírás nem látszott.
A laborpéldányok és saját DB-kötetük eltávolítva; az utolsó teljes éles ellenőrzés is sikeres.


## REPAIR-036 — HC-11: reszponzív ingest DB-kiesés alatt (2026-10-28)

**Hatókör:** kizárólag HC-11, a kapcsolódó bizonyítékok, HC-33/34 és az audit F10
lépésének elolvasásával. A felhasználó kifejezetten elfogadta a számlált eldobást
DB-kieséskor. **Helyi javítás, nincs élesítés vagy éles restart.**

A Paho callback helyett egyetlen külön DB-worker kezeli a kapcsolatot, cursort,
cache-eket, mentést, contact-flush-t és presence-sweepet. A callback csak egy
FIFO inboxba ad át fogadási idővel és retained jelzéssel ellátott üzenetet.
Alaplimitek: 1000 várakozó üzenet, 8 MiB payload+topic, 5 s sorban töltött idő;
mind konfigurálható. Kiesés, overflow, oversized, expiry és shutdown külön
veszteségszámlálót kap; felismert DB-hibakor atomikus befogadási tiltás és
sorürítés történik. A hibás, esetleg részben végrehajtott üzenetet nem próbáljuk
újra; helyreálláskor friss MQTT-adatokkal folytatjuk.

Kapcsolódási timeout és időzített újrapróbálkozás, HC-39 szerepkör-ellenőrzés
minden kapcsolódáskor, részleges kapcsolódási hiba és csere előtti külön
cursor/connection close. A hálózati életjel független a DB-től; külön JSON- és
naplódiagnosztika jelzi a DB-ready/stalled állapotot, veszteségeket és sorhatárokat,
leálláskor is. A megszűnő DB-session függő kontaktusjelöltjei számláltan kiesnek;
a stabilitási időt a shutdown nem kerüli meg. A workerre várás korlátos;
beragadt SQL/flush esetén hibakódos processzkilépés, nem állított tiszta flush.
Új migráció vagy függőségverzió nincs; a Dockerfile az új runtime modult is másolja.

**Ellenőrzés:** a régi végtelen callback-reconnect reprodukálva.
**37 hálózat nélküli unit-/regressziós teszt és 1 valódi MQTT/PostgreSQL
integrációs teszt sikeres.** A hálózati ciklus DB-indulási késés alatt is halad;
10 000-es burst, darab/byte/kor-limit, FIFO/retained/fogadási idő, kizárólagos
DB-tulajdonos, close-sorrend, role-/warmup-hiba, kapcsolódás és flush alatti
leállás, beragadt flush utáni tényleges processzkilépés ellenőrizve.
A valódi próba saját, hálózatról leválasztott MQTT és PostgreSQL 16 példánnyal,
HC-39 `hc_app` szerepkörrel futott: 100 kiesési üzenetből 99 számlált eldobás és
1 DB-hibás feldolgozás; MQTT és életjel folytatódott. Recovery után nincs kiesési
replay vagy régi kontaktusjelölt, az elfogadott értékek sorrendje helyes,
a kontaktus-bounce kimarad, stabil él késleltetve mentődik, SIGTERM-kori utolsó
batch mentve, kilépési kód 0. A labor és saját kötete eltávolítva.

**Határ és függőség:** HC-33 nyitott; a korai batch-ürítés/hibanyelés,
részleges commit, history-veszteség és idempotencia nincs javítva. A legacy
mérési batch nem az új inbox, veszteségeit az új számlálók nem fedik le.
Tartós offline tárolás/replay vagy veszteségmentes history előtt HC-33 külön
szükséges. HC-34, HC-12/32 és HC-43 változatlan; más auditpont státusza nem módosult.
AST szerint a 47 korábbi függvény/osztályból csak a `main()` változott.
Mind a 9 éles konténer, az aktív r8 override, a 37 védett hostfájl és az eredeti
audit SHA változatlan. Későbbi átadás kizárólag az ingest külön image-cseréje,
előző r4 image-re visszaállással, DB-restore és automatikus replay nélkül.

[Részletes szerződés és rollback](docs/hc-11-repair.md),
[ellenőrzési bizonyítékok](docs/audit-evidence/hc11-20261028/summary.json).


## REPAIR-037 — HC-33: tranzakciós, idempotens mérési batch (2026-10-28)

**Hatókör:** kizárólag HC-33; az audit bizonyítéka, F10 és a kapcsolódó HC-11
helyi változása elolvasva. **Helyi javítás és teszt, nincs élesítés.**
A kiesés alatt érkező új MQTT-adatok számlált eldobási politikája megmarad.

A history-sor csak visszaigazolt COMMIT után ürül. Stabil mintánkénti UUID,
egyetlen tranzakció minden batch-oldal körül, együtt commitoló history és
hozzá tartozó state/session művelet; a végleges deadband-cache követi a sikerpontot.
COMMIT utáni válaszvesztésnél azonos UUID-s újrapróbálás, duplikált history és
újrafuttatott state/session nélkül. Kapcsolathiba eljut a HC-11 recoveryhez;
csak SQL-adathiba indít teljes rollback utáni, savepointos sorizolálást.
Hibás sor, köztük meglévő `(entity_id,ts,key)` ütközés, számláltan kiesik,
a jó sorok és páros state-jeik menthetők. A timestamp az eredeti fogadásé.

A már befogadott history-sor alapkorlátja 1000 minta / 8 MiB / 30 s / 3
próbálkozás, mind env-ben állítható. Új minta túlcsordulásakor state/cache nem
lép tovább. Recovery előbb a régi, azonosított sort rendezi, aztán melegíti
be a cache-t; az új MQTT-inbox nem lesz offline replay-sor. Nincs tartós spool
vagy veszteségmentes crash-ígéret. A státusz a korlátokat, sikert, ismételt
visszaigazolást, hibát, SQLSTATE-et és eldobási okokat mutatja. Unknown commit
utáni limit-/shutdown-lezárás kimenetele bizonytalan lehet.

A `both` minták az MQTT-üzenet végén commitolnak, nem várnak a 2 s history-only
flush-ra. Élő feedback továbbra is frissülhet history-minta nélkül a szabály
szerint; korábbi függő state nem írhatja felül későbbi feedbackjét. Újrainduláskor
a historyt tároló szabály cache-e valódi historyból, a state-only szabályé
state-ből épül, a meglévő entity/key/ts index használatával.

**Ellenőrzés:** eredeti adatvesztés offline AST-próbával reprodukálva.
**44 unit-/regressziós és 15 valódi PostgreSQL/MQTT integrációs teszt sikeres.**
Batch előtti kapcsolatvesztés, többoldalas részleges végrehajtás rollbackje,
valódi COMMIT után elvesztett válasz és azonos UUID-s ismétlés, hibás history
és state-sor, timestamp-konfliktus, korlátok, cache/state/history sikerpont,
migráció újrafuttatása/régi író és hiányzó/hibás index miatti tiltás ellenőrizve.
A tényleges `main()` saját, hálózatról leválasztott Mosquitto/PostgreSQL 16
laborban DB-stop/start alatt haladt: új adat eldobva, korábban befogadott
history-minta recoveryvel mentve, SIGTERM-kor history-only utolsó minta mentve.
Valódi új processzben feldolgozott változatlan élő minta nem dupláz historyt;
friss eltérő érték menthető. CO/füst alvó szenzor → DB → safety worker
regresszió sikeres; nincs eszközparancs. A saját labor és kötete eltávolítva.

**Migráció és függőség:** az új **062_hc33_ingest_sample_identity.sql** nullable
UUID-oszlopot és részleges egyedi indexet ad, történeti backfill nélkül.
A régi íróval kompatibilis, az ingest kapcsolódáskor ellenőrzi, nem futtat DDL-t.
Külön adminmigráció kell a későbbi élesítés előtt, HC-11 és HC-33 közös ingest
image-ével. Friss mentés/karbantartási ablak szükséges: az index végigolvassa
a nagy mérési táblát, a tranzakció alatt olvasás/írás is várhat. 5 s lock-/120 s
statement-timeout; éles indexépítési idő most nem mért. HC-34, HC-12/32, HC-43
és minden más auditpont változatlan. Könyvtárfrissítés nincs.

**Éles érintetlenség/rollback:** 9 konténer, aktív r8 override, 37 védett hostfájl,
safety-forrás és eredeti audit SHA változatlan. Visszaálláskor előző pontos r4
ingest image, függő sor explicit rendezésével; a kompatibilis oszlop/index
maradhat. Nincs DB-restore, automatikus üzenetreplay vagy destruktív séma-visszavonás.

[Részletes szerződés, migráció és rollback](docs/hc-33-repair.md),
[ellenőrzési bizonyítékok](docs/audit-evidence/hc33-20261028/summary.json).


## REPAIR-038 — HC-34 és HC-11/33/34 ingest-kiadás előkészítése (2026-10-28)

**Engedély/hatókör:** a felhasználó a következő élesítéshez szükséges pontokat
kérte. HC-34, a HC-23 ingestet érintő kiadási része, rögzített image,
állapotellenőrzés, éles méretű migrációpróba, mentés és rollback-csomag készült.
**Az éles r8 megmaradt; nem futott éles migráció vagy szolgáltatáscsere.**
Elolvasva HC-34/HC-23, a kapcsolódó bizonyítékok és F10.

A pumpa-/szelep-/vezérlő- és solar-aliasok csak a megfelelő öntözési telemetria-
topicokra vonatkoznak. Tuya `current_a` megmarad; a már normalizált pumpa-,
szelepmotor- és solar-kulcsok változatlanok. A teljes méretű próba a helyiségnév
nélküli Tuya `/m/current_a` út 7 helyett 6 szegmenses parserigényét is igazolta:
a producer és hat éles rövid topic alapján ezt a HC-34 per-metric út részeként
javítottuk. Rövid/hosszú state és per-metric alak ellenőrizve. Nincs történeti
átnevezés/backfill és nincs bridge-módosítás.

**HC-23 részterület:** a ténylegesen futó r4 ingest alaprétegei és összes Python-
csomagja változatlan, paho-mqtt 2.1.0 / psycopg2-binary 2.9.13 rögzítve.
A build hálózat nélkül, pontos image- és forráshash-ellenőrzéssel futott.
Mellékhatásmentes, fájlalapú Docker-liveness és külön DB/MQTT/worker-readiness;
a status a processz indulási azonosságát is rögzíti. A globális HC-23 nyitott,
HC-43 csomagfrissítés nem történt; más auditpont státusza nem változott.

**Ellenőrzés:** 52 unit-/regressziós teszt a kész image moduljaival és fagyasztott
tesztforrással; 15 valódi PostgreSQL/MQTT hiba-/safety-integráció; 14 átadási
teszt, 0 failure/error/skip. Blokkolt kapu/lock alatti változás esetén nincs stop,
migráció vagy startup; migráció/startup-hiba ellenőrzött régi image-visszaállási
útja tesztelt. Rollbackhez új image/forrás vagy friss backup nem szükséges;
a történeti unknown auditok kivétele nem szélesedett.

6 840 083 méréses, ellenőrzött owner/ACL-es másolaton 062 migráció **3,796 s**;
a régi sorok teljes, sorrendfüggetlen tartalmi hash-e változatlan. Blokkolt ALTER
5,086 s után lock-timeout, sémaátírás nélkül; újrafuttatás kompatibilis.
Tényleges **r9 → r4 → r9** image/processz-próba ugyanazon DB-n, valódi
transaction-mode PgBouncerrel és loopback Mosquittóval; köztes DB-restore nélkül.
Új/legacy/új UUID-kezelés, current-state és Tuya state/per-metric adatmentés jó.
A kész image liveness/readiness a tényleges PID 1 processzen is működött.
Élesben csak olvasó metrika/rule-egyeztetés: 6 aktív Tuya current-szabály,
5 helyes numerikus metrika és 4 helyes öntözési/solar-szabály.

**Mentés/kiadás:** friss local-only, completed/0 F6 archívum teljes helyi
lefedettséggel és ellenőrzött belső checksumokkal; receipt az r9 evidence-ben.
Két pontos ingest image privát offline tarban, runtime-env külön 0600 másolatban.
Az r9 Compose csak az ingest image-ét változtatja; runtime-env megegyezik,
a többi nyolc szolgáltatás változatlan. A helper alapértelmezett művelete olvasó
előellenőrzés; `--apply` nélkül nincs átadás. Az engedélyezett átadás majd közös
backup-lock alatt állítja le a régi ingestet, alkalmazza szükség esetén a 062-t,
és kizárólag az ingestet indítja, utóellenőrzés után aktiválva az override-ot.
A kompatibilis séma rollbackkor megmarad, nincs DB-restore vagy replay.
A karbantartási rés QoS0-vesztesége nem számlálható; az index mért laborideje
nem éles időgarancia. Friss mentés és élő állapotkapu élesítéskor is szükséges.

A labor és saját kötetei eltávolítva. 9 éles konténer, 37 védett hostfájl,
aktív r8 override, safety-forrás és eredeti audit SHA változatlan.
AI-offline/téli profil megmarad. HC-12/32, globális HC-23/43, AI-SSD/HC-31 fizikai
próba és HC-45 valódi VM/systemd restore külön marad.

[Előkészített r9 csomag és végrehajtási/rollback-parancsok](backups/releases/hc-ingest-20261028-r9/DEPLOYMENT.md),
[HC-34 leírás](docs/hc-34-repair.md),
[bizonyítékok](docs/audit-evidence/hc34-20261028/summary.json).

Az első r9 olvasó kapu a történeti unknown ellenőrzésben hiányzó datetime-importot
fogott; éles stop/migráció nem történt. Az import javítva, pozitív történeti
unknown-regresszió hozzáadva, csomag újralezárva és a kapu ismét ellenőrizve.

## REPAIR-039 — HC-11/33/34 ingest r9 élesítése (2026-10-28)

**Engedély:** a felhasználó kifejezetten kérte: „ok, akkor élesítsd”.
**Átadva: 22:13:26 CET.** A HC-11/33/34 közös ingest image-e aktív; az új
062-es migráció egy admintranzakcióban lefutott. Kizárólag az ingest cserélődött,
backend/frontend r8 és a másik nyolc konténer változatlan. Globális HC-23/43 és
minden más auditpont státusza megmaradt; HC-23 ingest-liveness/readiness és
image-rögzítés részterülete aktiválva. Nincs könyvtárfrissítés.

Az előkészített csomag/hash-ek, friss ellenőrzött local-only mentés, DB/MQTT,
AI-offline/téli profil, friss Nano és zárt szelepek kapuja sikeres; közös
backup-lock alatt újraellenőrizve. Régi writer szabályosan leállt, az új egyedül
indult, az override csak sikeres utóellenőrzés után váltott. A nullable UUID és
részleges unique index valid/ready; nincs backfill, történeti átírás vagy DB-restore.

**Éles ellenőrzés 22:15:29 CET:** healthy és ready, restart=0, DB/MQTT működik,
nincs beragadt worker. 6 880 210 → 6 880 323 mérés, 113 új UUID-os minta,
köztük 26 `current_a`. Külön 30,25 s megfigyelés: 204 feldolgozott üzenet és
23 megerősített új minta; nincs új DB-/flush-/adathiba vagy eldobásnövekedés.
Mindkét sor üres a végén. Induláskor a DB/cache készenléte előtt 70 MQTT-üzenet
számláltan eldobódott, az elfogadott szerződés szerint; a számláló azóta nem nőtt.
A leállás alatti QoS0-veszteség nem számlálható, automatikus replay nincs.

Konfiguráció, safety ACK/latch és safety-forrás megmaradt; 37 védett hostfájl
és eredeti audit SHA változatlan. Friss Nano online, CLOSED/CLOSED szelepek,
téli profil és AI-offline érvényes. Aktív session/új függő execution nincs,
a három történeti unknown audit érintetlen. Nincs nyugtázás vagy próbaöntözés.

Előkészítési bizonyíték: 52 unit-/regressziós + 15 PostgreSQL/MQTT + 14 átadási
teszt, 6,84 milliós migráció és r9→r4→r9 PgBouncer-próba. Az éles migráció
külön időtartama nem lett mérve. Labor-erőforrás nincs; rövid éles ellenőrzés
történt, tartós terhelést vagy DB-kiesést nem provokáltunk.

Friss mentés és mindkét pontos image privát offline példánya megőrizve.
Automatikus rollbackre nem volt szükség. Szükség esetén az r9 saját helperje
csak az ingestet állítja vissza az előző r4 image-re, a kompatibilis 062-es
sémát megtartva; DB-restore vagy destruktív sémavisszavonás nélkül.
AI SSD/HC-31 fizikai próba, HC-45 VM/systemd teljes restore és más nyitott
auditpontok változatlanul fennmaradnak.

[Éles átadás és rollback](backups/deployments/hc-ingest-20261028-r9/DEPLOYMENT.md),
[éles ellenőrzés](backups/deployments/hc-ingest-20261028-r9/live-verification.json).
Az r9 fagyasztott csomag előkészítéskori metaadatai történeti bizonyítékként
változatlanok; az aktuális élesítést a külön deployment és az applied-release
receipt rögzíti. A javítások leírásainak aktuális fejlécét és a DEPLOYMENT_PREP
aktuális állapotát frissítettük.

## REPAIR-040 — HC-35/36: explicit binding és késleltetett ventilátor-ON (2026-10-29)

**Hatókör:** a felhasználó HC-35/36 javítását kérte; mindkét megállapítás,
kapcsolódó reprodukció és F5a elolvasva. Más auditpontot nem javítottunk.
**Helyben javítva és ellenőrizve; élesítés nincs.** Az aktív r9 ingest és r8
backend/frontend megmaradt.

**HC-35:** külön nem konfigurált/érvényes/érvénytelen konfigurált állapot.
Tárolt sor esetén nincs fallback; a törlés után nullra állított explicit sor
sem kezdeti állapot. Aktív entity/device, megfelelő engedélyezett metrikák és
kapcsolási/jelzőfény-képesség szükséges. A fallback csak tárolt sor nélküli,
ellenőrzött kezdeti kompatibilitás. Az adminfelület egyértelmű hibát és üres
választást mutat, a kezdőlap nem választ másik eszközt név alapján. Az AI-aljzat,
mérők, talajszenzor és automata ventilátor fogyasztói sem kerülhetik meg a null
eredményt saját konfigurációs fallbackkel. Szenzorhiánynál a domain ismeretlen
adatot kap; nincs automatikus eszközcsere vagy kezelői konfigurációátírás.

**HC-36:** appból közösen bekötött helyi lock és PostgreSQL-tranzakciós advisory
lock rendezi a bindingcserét, ON/OFF-ot, policyt, due ticket és kézi PowerWall/Tuya
kapcsolást. A binding/policy/régi szándék módosítása egy tranzakció; a tick csak
az aktuális érvényes cél engedélyezett, lejárt és sikeresen lefoglalt szándékát
publikálja, a lockot a publikálás végéig tartva. A→B→A nem éleszti újra a régi ON-t;
változatlan érvényes cél saját késleltetése megmarad. Más kézi/ütemezett feladat
tábláját nem üríti. A nem kiválasztott/letiltott cél régi climate-késleltetése
visszavont. Lock-timeout 2 s, koordinációs SQL statement-timeout 5 s; hiba esetén
nincs másik célra küldés. Nincs új migráció vagy függőségverzió.

**Ellenőrzés:** eredeti forrásból újra reprodukálva az explicit 11→fallback 22
helyettesítés és A pending→binding B→OFF→tick után B OFF, majd A ON. A javításon
**386 backend unit-/regressziós + 19 valódi PostgreSQL-integrációs + 4 frontend
viselkedési teszt**, valamint teljes frontend build sikeres; 0 failure/error/skip.
Inaktív/törölt entity/device, letiltott képesség, kezdeti fallback, A→B→A,
OFF előtte/utána, új cél saját késleltetése, policytiltás, új service-példánnyal
restart-szimuláció, tranzakció-rollback, külön DB-kapcsolatok közti verseny,
lejárat közbeni csere és lock-timeout ellenőrizve. Tuya fül kézi OFF-ja sem
hagy régi climate-indítást. A publisher helyettesítő; nincs fizikai kapcsolás.

A tesztkörnyezet mount-/tmp-végrehajthatósági és Node-cache hibáit a laborban
rendeztük; a végső teljes suite sikeres. Emiatt alkalmazás-/backupjavítás vagy
könyvtárfrissítés nem történt. A csak olvasva leltározott **11 jelenlegi binding
mind érvényes** az új ellenőrzéssel, nincs aktuális fallbackes szerepkör.

**Éles érintetlenség:** mind a 15 rögzített éles konténer azonosítója, image-e,
indulása és restartszáma változatlan; 37 védett hostfájl, binding API-leltár,
aktív r9 override, safety-forrás, frontend lock és eredeti audit SHA megmaradt.
A saját PostgreSQL-labor/belső hálózat eltávolítva. A tesztek nem az éles DB-n
futottak; nincs eszközparancs, migráció, backendrestart vagy riasztásnyugtázás.

**Függőség/átadás:** backend, új koordinátor, app-bekötés és frontend együtt
kiadandó, külön fagyasztott csomaggal és friss mentéssel. Régi és új backend
nem futhat párhuzamosan; a régi nem ismeri az új lockot. Indulás/rollback előtt
a függő ventilátorszándékok aktuális állapottal egyeztetendők. Visszavont ON-t
rollback sem tervezhet újra; korábbi binding/policy előállapot megőrizendő.
Éles fizikai/integrált container-/PgBouncer-átadás és tartós terhelés most nem
futott. HC-31 fizikai AI-próba, HC-45 VM/systemd restore, HC-12/32, globális
HC-23/43 és minden más auditpont változatlan.

[Részletes szerződés és rollback](docs/hc-35-36-repair.md),
[bizonyítékok](docs/audit-evidence/hc35-36-20261029/summary.json).

## REPAIR-041 — HC-41/44: elhalasztott MQTT-auth, szűkített hostvégrehajtás (2026-10-29)

**Hatókör:** HC-41/44, kapcsolódó bizonyítékok és F1a/F1b elolvasva.
**HC-44 helyben javítva és ellenőrizve, nincs élesítve. HC-41 nyitott.**
Más auditpontot nem javítottunk. A korábbi HC-35/36 helyi javítás megmaradt.

**Felhasználói döntés / HC-41:** van hitelesítést nem támogató MQTT-eszköz;
a felhasználó egyelőre nem kér MQTT-jelszót. Nincs jelszógenerálás, broker-,
kliens-, ACL- vagy tűzfalmódosítás. Csak olvasó port-/kliensazonosító-leltár és
alkalmazási mód nélküli hálózatiterv-készítő készült. A terv nem alkalmazható
jóváhagyott eszköz-/IP- és teljes hostcímleltár nélkül. A névtelen vezérlőbusz
kitettsége megmarad; IP-szűrés sem helyettesítene hitelesítést/topic-ACL-t.
Izolált auth/ACL-átállási próbát nem állítunk elvégzettnek.

**HC-44 változás:** a munkafabeli backend UID/GID10001, read-only rootfs,
cap-drop ALL és no-new-privileges; nincs Docker-socket. Kód, archívumok és
staging csak olvashatók; írható az elkülönített AI-állapot, a két meglévő közös
lock és a Rover JSON-adatkönyvtár. A normál API csak meghatározott Unix IPC-
műveleteket kérhet; nincs általános Docker/exec/CLI-fallback. Külön hostszolgáltatás
ellenőrzi a peer UID-t, a 14 meglévő konténercélt és a projektet. Határidő,
méret, szálak és restartkapacitás korlátozott. Idegen cél/parancs/útvonal tiltott.

Hostprivát feladatnapló, tartalmi idempotencia és a restart befogadásakor rögzített
konténerazonosító; HTTP202 és lekérdezhető job, nem hamis készültség. Megszakadt
feladat újraindulás után uncertain, automatikus replay nélkül. A backup a meglévő
F6 sort/lockot használja; hostútvonal/credential/cél nem írható át az API-val,
in-place restore csak ellenőrzött hostarchívumból, completed receipt/checksum
alapján. Az eredeti backup/restore modulok és éles runnerek változatlanok.

Külön AI-koordinációs adapter, F6 adapter, öt systemd drop-in és a kanonikus
runner fagyasztott kiadásra renderelendő launchersablon készült. Ezek biztosítják
a közös állapotot anélkül, hogy a jelenlegi éles F6-fogyasztókat átírtuk volna.
A két mentésvédelmi lock útvonala/inode-ja változatlanul megtartandó.

**Ellenőrzés:** 408 backend unit-/regressziós teszt, 0 failure/error/skip;
ebből 22 új HC-44 teszt. Valódi Unix IPC, UID-határ, timeout, idempotencia,
megszakadt és lecserélt restartcél, 202/job, útvonal-/parancs-/settings-tiltás,
F6-launcher, szintetikus ellenőrzött mentés/restore és lockvédelem igazolva.
Compose valid, a négy írható cél ellenőrizve. Pontos r8 alapú, függőségfrissítés
nélküli tesztimage-ben UID10001, RO-forrás/archívum, daemon hiánya és elutasítások
igazolva. Státusz/stats/log, szintetikus hostrestore, F6-sor és saját eldobható
konténer tényleges restartja sikeres; UID10002 elutasított. Labor eltávolítva.

**Korlát:** a Docker-socketet kapó laborkonténer tervét az automatikus jóváhagyási
ellenőrzés hostszintű vezérlés kockázata miatt elutasította. A megvalósult biztonságos
alternatívában egyetlen konténer sem kapott socketet: host UID1000 tesztvezérlő,
0666 laborsocket, aktív peer-UID-ellenőrzés. Az éles root:10001/0660 socket és
valódi systemd-telepítés nincs igazolva; nincs jelszómentes sudo, ezt nem kerültük
meg. Fizikai AI/offsite, új backend teljes éles indulás és VM/systemd full restore
nem futott. A szintetikus restore policyfeloldása csak a tesztfolyamatban élt.

**Éles érintetlenség:** mind a 15 konténer ID/image/indulás/restartszáma, 37
védett hostfájl, broker/bridge-források, r9 override, safety és eredeti audit SHA
változatlan. Az éles backend korábbi root/mountjai megmaradtak; a javítás nincs
aktiválva. Nincs migráció, éles restart, eszközparancs vagy riasztásnyugtázás.

**Függőség / következő átadás:** backend, hostunit, öt F6 drop-in és kanonikus
runner-adapter együtt, fagyasztott kiadásból. Régi backend/F6-fogyasztók leállítva,
lockok üresek, inode-ok megőrizve; az AI-állapot ellenőrzött átadása és függő
szándékok egyeztetése szükséges. **HC-45 restore-manifest/telepítési lánc az új
egységekkel kiegészítendő a bevezetés előtt**, külön feladatként; státusza nem
változott. Root/systemd jogosultságpróba és integrált backendindulás hátravan.
HC-31 fizikai AI-próba/SSD, valamint globális HC-23/43 továbbra is függőség/korlát.

Rollback: futó műveletek és uncertain jobok egyeztetése, majd image, adapter,
unitok és eredeti jogok együtt. Aktuális AI-állapotot egyeztetni kell a régi
útvonallal; korábbi generation/szándék nem állítható vissza vakon. Archívum,
staging és jobnapló megőrzendő; nincs automatikus újrafuttatás.

[Részletek és bevezetési terv](docs/hc-41-44-repair.md),
[ellenőrzési eredmények és forrásdiff](docs/audit-evidence/hc41-44-20261029/summary.json).

## REPAIR-042 — HC-41: fokozatos MQTT-auth, ESP-kivétel és külön dashboard-jog (2026-10-30)

**Felhasználói döntés:** a korábbi általános jelszóhalasztás helyett a HC-n futó
alkalmazások hitelesítése előkészítendő, az öntöző ESP átmeneti kivételével;
az ESP-t a firmware-frissítésekor állítjuk át. A közben azonosított fejlesztői
dashboardhoz a felhasználó külön jelszavas hozzáférést kért. **HC-41 folyamatban,
nincs élesítve.** HC-41 bizonyítékai/F1a elolvasva, más auditpont nem javítva.

**Módosítás:** a backend valamennyi MQTT-kapcsolata, ingest, Tuya, X10 bridge és
legacy API, Gree, HA–Growatt egységes jelszófájl-kezelést kapott. Előírt authnál
hiányos/olvashatatlan/hibás titok nem vezet névtelen kapcsolódáshoz; titokérték
nem szerepel hibában. A még át nem állított konfiguráció kompatibilis marad.
Ingest Dockerfile kiegészítve; Zigbee2MQTT külön környezeti felülírás előkészítve.

Új, alkalmazási mód nélküli jelöltcsomag-készítő: szerepkörönként külön jelszó,
ACL, brokerkonfig és Compose override. Belső/loopback jelszavas 1884; az ESP
változatlan 1883-on csak saját tele/stat írás és cmd olvasás. Az inaktív Grott
profilhoz opcionális, nem aktivált sablon készült. Privát credentialcsomag nem
kerülhet exportált forrás/configfa alá. Az adatbázis hash-elése, éles ownership
és titkosított mentési lefedés külön kiadási lépés.

A post-boot script névtelen broker-CLI-jét az új adapterben hitelesített,
határidős, csak olvasó backendprobe váltja fel. Az éles script/unit változatlan.
Az új, csak olvasó hálózatiterv-készítő a publikált és közvetlen Docker-, host-
és IPv6-utakra is kitér; nem telepítő, szabályt nem alkalmazott.

**Leltári függőség:** a felhasználó által feltételesen megadott 192.168.1.179-ről
valóban van broker-TCP-kapcsolat, de ESP-azonosság/fix DHCP nincs bizonyítva.
192.168.1.89-ről irrigation-dashboard-lite is kapcsolódik: külső kliens, tehát
az ESP nem az egyetlen szerveren kívüli MQTT-fogyasztó. A jóváhagyott hc_dashboard
csak saját öntözési állapotokat olvashat és saját öntözési parancsot küldhet.
Külön privát klienssablon, terv szerint SSH-alagút a loopback jelszavas portra;
a PC nem kap névtelen IP-kivételt. A PC konfigurációját nem módosítottuk.

**Ellenőrzés:** 422 backend unit-/regresszió, 0 failure/error/skip, ebből 14 új
hitelesítési/csomag-/hálózatiterv-teszt. Továbbá 14 sikeres valódi brokerforgatókönyv
a jelenlegi pontos Mosquitto image-en, network=none, publikált port nélkül:
10 külön identitás, névtelen/hibás jelszó tiltás, legacy telemetria, szintetikus
STOP/ack, retained, LWT és reconnect; domain-/parancshatár, ingest írástilalom,
Tuya/X10/klíma szintetikus parancsátadás, dashboard-ACL, valódi backend monitor,
publisher és post-boot probe. Nem történt fizikai vagy éles MQTT-publikálás.
Compose parser a hat Python-klienssel és Zigbee2MQTT-vel sikeres; Python/Bash
szintaxis ellenőrizve. Hashsegéd labor-/tmp problémája a laborban rendezve.

**Éles állapot:** mind a 15 rögzített konténer ID/image-e megmaradt. A tegnapi
leltárhoz képest csak az X10 önálló indulás/restartszáma változott, a mostani
előkészítés kezdete óta az is változatlan. Aktív r9 override, MQTT-konfig,
37 védett hostfájl, eredeti audit és safety-forrás megmaradt. A labor eltávolítva.
Nincs broker-/kliensrestart, tűzfalalkalmazás, migráció vagy új éles credential.

**Hátravan:** ESP-azonosság/fix cím, a valódi hoston a kizárólagos legacy-IP-határ
igazolása és tartós/idempotens telepítése, broker-UID/secretjogok, dashboard-
konfiguráció/SSH-alagút, pontos fagyasztott image-ek, titkosított secret-restore
és post-boot adapter átadás, friss mentés és felügyelt telemetria/STOP/ack.
A munkafában lévő HC-35/36/44 nem kerülhet automatikusan ebbe a kiadásba.
HC-45/F6 restore-/unit-lefedés külön függőség, státusza változatlan. HC-41 teljes
lezárása az ESP későbbi jelszavas átállása és a névtelen listener eltávolítása után.

Rollback: korábbi broker/kliens image és konfig, post-boot adapter együtt,
az ESP-re szűkített hálózati határ megtartásával. Credentialek/receipt/állapot
megőrzendők; általános névtelen parancsbusz nem állítható vissza észrevétlenül.

[Részletes terv és korlátok](docs/hc41-staged-mqtt-auth.md),
[teszteredmények és forrásdiff](docs/audit-evidence/hc41-stage-20261030/summary.json).

## REPAIR-043 — HC-41: külön megfigyelői MQTT Explorer-profil (2026-10-30)

**Hatókör:** a felhasználó kérésére az Explorer jelszavas hozzáférésének
előkészítése, a HC-41 fokozatos átállási tervén belül. **Nincs élesítés**, a
HC-41 státusza továbbra is folyamatban; más auditpont státusza nem változott.

Új `hc_explorer` identitás és saját jelszó, a dashboardétól függetlenül. Kizárólag
`homecontrol/#`, `zigbee/#` és `$SYS/broker/#` olvasás, parancs-/telemetria-/retained
írás nélkül. A csomagkészítő privát, 0600 kapcsolatimező-referenciát is előállít;
nem állítunk ellenőrzött alkalmazásimportot. Host 127.0.0.1, port 21884, a meglévő
terv szerinti SSH-alagúton a HC loopback 1884-es portjához. A dashboard és Explorer
használhatja ugyanazt az alagutat, külön MQTT-identitással.

Privát jelöltcsomag készült `backups/mqtt-access/hc41-20261030-explorer` alatt,
0700 könyvtárral és hash-elt broker-jelszóadatbázissal. Éles Compose/brokerhez
nincs bekötve. A jelszó csak a privát profilban szerepel; a nyilvános eredmények,
dokumentumok és chat nem tartalmazzák. A kiadás véglegesítésekor a választott
credentialt meg kell őrizni vagy az új profilt külön átadni; másik jelölt készítése
nem változtat automatikusan aktív jelszót.

**Ellenőrzés:** 15 célzott hitelesítési/profil/csomagvédelmi unit teszt és
15 valódi, network=none brokerforgatókönyv sikeres. Utóbbi megismétli az előző
14 forgatókönyvet és kiegészül a valódi MQTT5 Explorer-klienssel: retained állapot
olvasása sikeres, öt parancs-/telemetria-topicra QoS1 retained írás `Not authorized`
PUBACK 135-tel elutasítva, a backend nem kapott tiltott üzenetet. Mind a 11 szerepkör
hitelesítése sikeres. Nincs éles vagy fizikai MQTT-üzenet; labor eltávolítva.

A HC 192.168.1.133 címét és az SSH-alagút `ssh -G` szerinti helyi konfigurációját
ellenőriztük; tényleges PC→HC SSH és grafikus Explorer-próba nem történt.
Az éles broker ID/image/indulás/restartszáma, MQTT-konfiguráció és 37 védett
hostfájl változatlan; r9 override megmaradt. A korábbi teljes 422-es suite külön
történeti eredmény, most a célzott tesztek futottak.

A HC-41 élesítési előfeltételei változatlanok: ESP fix azonosság/IP, hostoldali
legacy-szűrés, privát jogok/secret-restore, pontos kiadási image-ek, kliensátadás és
felügyelt STOP/ack. Az Explorer jelenlegi profilját addig nem kell átírni.

[Kapcsolódási útmutató](docs/mqtt-explorer-access.md),
[tesztek, profilmezők jelszó nélkül és diff](docs/audit-evidence/hc41-explorer-20261030/summary.json).

## REPAIR-044 — HC-41: az öntöző ESP aktuális IP-jének olvasó ellenőrzése (2026-10-30)

A felhasználó a 192.168.1.179 címet adta meg újra ellenőrzésre. ARP-szomszéd:
eno1, REACHABLE, MAC ec:e3:34:db:ea:9c. A broker /proc/net/tcp leltárában aktív
ESTABLISHED kapcsolat erről a címről, forrásport 59913, brokerport 1883.
A friss broker-debugnapló szerint a saját nano_status/solar/pump_metrics topicok
publikálója esp-irrigation-1-db34e3ec. A suffix a MAC első négy bájtjának fordított
sorrendjével egyezik; ez erősen alátámasztja, hogy ez az öntöző ESP jelenlegi címe.

Friss CONNECT rekord nem volt a korlátos naplókivonatban, így a forrás-IP és
publikáló kliens összerendelése a MAC/suffix egyezésből következtetés. A négy
másodperces, csak feliratkozó diagnosztikai ablakban nem jött diag üzenet; a
kezdőoldalra küldött egyszeri HTTP GET nem adott elérhető azonosítást. Ez nem
állítja hibásnak az MQTT-adatküldést, amelynek publikálása a naplóban látható.

Az átmeneti kivételhez a 192.168.1.179 címet vesszük alapul. A tartós DHCP-foglalás/
fix beállítás továbbra sem igazolt; a kiadási kaput nem állítottuk teljesültre.
Csak a privát jelölt manifestjének megfigyelési metaadata és a dokumentáció
frissült. Nincs vezérlőpublikálás, élő konfiguráció-/tűzfalváltozás vagy restart.
HC-41 folyamatban marad, más auditpont státusza változatlan.

[Olvasó vizsgálat bizonyítéka](docs/audit-evidence/hc41-esp-ip-20261030/verification.json).

## REPAIR-045 — HC-41/44: célzott r10 kiadási előkészítés (2026-10-30)

A felhasználó teljes élesítési előkészítést kért; az ESP azonosságát és fix címét
holnap erősíti meg. Az audit HC-41/44 bizonyítékai, F1a/F1b és a szükséges
HC-45/F6a restore-kapcsolat alapján elkészült a `hc-access-20261030-r10` csomag.
**Nincs élesítve.** Más auditpontot nem aktiváltunk; HC-35/36 szándékosan kimarad.

Hat kész image a jelenlegi pontos alapimage-ekből; rögzített Compose, külön
MQTT-identitások/ACL-ek, loopback 1884, ESP-only 1883 nft-szűrés. A guard saját
táblákat használ, atomi, nem változtat globális sysctl-t; Docker ExecStartPre
biztosítja a reboot előtti védelmet. Backend UID10001/read-only/socket nélkül,
külön root host-végrehajtó, öt F6 drop-in, közös lock-inode megőrzése, AI-state
átadás korábbi szándék visszajátszása nélkül. Root állapotírás után az API-jogok
megmaradnak; symlink/FIFO/hardlink tiltás, helyi Docker-context kikényszerítve.

Restore-függőségként a fagyasztott bootstrap/runner/hostinstaller, secretmanifest
és titokbundle átadása is elkészült. A teljes mentés felveszi az offline image-cache-t
és az `uncertain` állapotú megszakadt hostfeladatokat. Azonos journal ismétlése
engedett, újabb helyi job felülírása tiltott. Kanonikus fájl-/unit-/jogosultság-
snapshot és rollback kész; a rollback hálózati engedélylistája külön dokumentált.
Éles védett hostkódot most nem írtunk át.

**Ellenőrzés:** 427 kiadási unit/regressziós teszt, 0 failure/error/skip. Valódi
izolált PostgreSQL/PgBouncer/authenticated MQTT + kész backend/ingest ready;
root:10001 0660 IPC, idegen UID és önkényes parancs elutasítása, védett írások
tiltása sikeres. Broker UID1883/0600 konfiguráció ellenőrzött. A host Docker CLI
ebben a laborban fixture, daemon-socket nincs. Natív namespace nft-próba pozitív/
negatív forrásokra, IPv6-ra, ismétlésre és rollbackre sikeres. Hat image forráshash,
Compose, 16 unit + 9 drop-in + Docker alapunit szintaktikai ellenőrzése sikeres;
utóbbi hostfüggőségi/sandbox figyelmeztetésekkel, éles systemd-alkalmazás nélkül.

Friss r9 teljes mentés: `homecontrol_2026-10-30_19-01-45_2ca584d8dd584af5977fb9cc84c4fc40.tar.gz`,
969/969 belső checksum. Külön 20 image-es linux/amd64 offline cache, 233 blob SHA256
és platformhoz tartozó tartalomlánc ellenőrzött. 50 titokfájl age-roundtripje sikeres,
13 jelenlegi fájl frissítve a privát csomagban; éles titok nem változott.

Mind a 16 éles konténer ID/image/indulás/restartszáma és 37 védett hostfájl
változatlan, az eredeti audit/safety/MQTT-config és r9 override megmaradt.

**Hátravan:** ESP azonosság és fix IP/DHCP megerősítése; erre épülő előkészített
policy/bundle-véglegesítés és új seal; root hostjogú, felügyelt átállás fizikai
telemetria/STOP/ack és PC-s dashboard/Explorer próbával. A teljes HC-41 az ESP
későbbi jelszavas átállásáig folyamatban; HC-45 valódi friss VM/PID1 restore-próba
hiányában ellenőrzésre vár. Az auditösszesítés változatlan: **37 ellenőrzött,
9 nyitott, 1 folyamatban, 1 javítva – ellenőrzésre vár**.

[Kiadási eljárás és korlátok](docs/hc41-44-release-preparation.md),
[gépi összesítés](docs/audit-evidence/hc41-44-release-20261030/summary.json).


## REPAIR-046 — HC-45/F6a: valódi friss KVM-restore és szükséges r10-korrekciók (2026-10-30)

**Kérés/alap:** a felhasználó kérte a hiányzó VM-visszaállítási próba elvégzését.
Átnézve HC-45 bizonyítéka/ellenőrzése/rollbackje, F6a, M.2/M.3, valamint az r10
HC-41/44 restore-manifestjének kapcsolódása. Más auditpontot nem javítottunk vagy
aktiváltunk. Az ESP-cím megerősítése továbbra is hiányzik; élesítés nem történt.

**Környezet:** helyben létrehozott eldobható KVM, 2 vCPU, 6 GiB RAM, 32 GiB lemez,
Ubuntu 22.04, valódi systemd PID1, saját Docker 29.1.5 és Compose 5.0.2.
Hivatalos OS-image GPG/SHA256 ellenőrzött. Nincs host Docker-socket vagy LAN;
HC/ESP/AI/internet/QEMU-host kapcsolatok blokkoltak. A guest saját Git és valós
SSH/SFTP/restic tára szolgálta a próbát. A kezdeti r10 fixture változatlan valós
r9 DB-dumpot használt; ezt külön valódi VM-mentés→restore kör egészítette ki.
A fizikai AI/offsite és eszközműködés nem lett igazoltnak feltüntetve.

**Feltárt/javított hibák, kizárólag az előkészített csomagban:**

- Ellenőrzött image-cache/journal/settings kiemelése a kiválasztott archívumból;
  pinned PG-image a DB-formátum ellenőrzése előtt, új `restore_assets.py`.
- Fagyasztott wrapper importút, támogatott Compose run kapcsolók, hiányzó friss
  host-unit explicit kezelése, telepítéskor/ismétléskor is jövőbeli post-boot trigger.
- A mentési beállítás is bekerül a valódi archívumba és előre validáltan áll vissza.
- A host-végrehajtó újraindításkor megőrzi a socketkönyvtár inode-ját, a fix socketet
  stop után eltávolítja. Valódi restart/SIGKILL után a backend újraindítása nélkül működik.
- Az első rebootkor dinamikus peer kapta a broker rögzített IP-jét. A runtime és
  rollback mind a 11 meglévő HC bridge-címet rögzíti, a telepítő az endpointleltárat
  ellenőrzi. Ez az eredeti nyolc helyett **13 szolgáltatás** újralétrehozását igényli:
  az öt további a PostgreSQL, PgBouncer, frontend, proxy és HC AI API-konténer.
  Az image-ek/környezetük megmarad, DB-migráció nincs; rövid DB/API-kiesés és QoS0
  mérési adatvesztés lehet a későbbi felügyelt átadáskor. Fizikai AI-ébresztés nincs.

A 37 aktív hostfájl eredetije megmaradt; a szükséges régi scriptkorrekciók a
kiadás fagyasztott példányaiban/renderelőjében készültek, nem az éles végrehajtóban.

**Ellenőrzés:** 430 kiadási unit/regressziós teszt és külön 52 célzott restore-/
unittelepítési teszt, 0 failure/error/skip; a suite-ok átfednek. Friss teljes
bootstrap és ismétlés sikeres, egyetlen system scope, unit-/drop-in bájtegyezés,
valós enabled/next-trigger ellenőrzés. A kiinduló DB 7 006 285 mérési sora,
66 entityje és 61 táblája elérhető. A VM valódi non-root API → root IPC → systemd
útvonalon új teljes mentést készített; 1 480 checksum ellenőrzött. Ennek teljes
visszaállítása a külön eltávolított beállításfájl nélkül is visszaadta a **04:27**
ütemezést. A végső kóddal ismét sikeres teljes bootstrap és valós reboot történt.
DB/MQTT-health, UID10001/read-only/socket nélküli backend, valódi Docker-inventory,
írási határok, nft guard és megszakadt `uncertain` feladat megőrzése igazolt.
Szándékos unitengedélyezési hiba után 16 korábbi unitfájl és enabled állapot
visszaállt; valódi vendégkonténer-restart is sikeres. Elérhetetlen SFTP-tárnál a
bootstrap őszintén hibával megállt, a kanonikus állapot és DB nem változott.
Újabb helyi journal felülírását megtagadta; a labor naplója külön megőrizve lett.

A hibás labor restic-kizárás miatti disk-full kört hibának rögzítettük, a helyes
kizárásokkal ismételtük. Az összes sikertelen köztes próbát a végső eredménytől
elkülönítve dokumentáltuk. A külső magic-letöltő és a teljes r9→r10→r9 cutover-
tranzakció nem futott ebben a VM-ben; a unit-rollback ténylegesen lefutott.

**Éles változatlanság/státusz:** 16 konténer ID/image/start/restart, 37 védett
hostfájl, eredeti audit, safety-forrás, MQTT-konfiguráció és r9 override változatlan.
A termelési bundle nem módosult, `esp_confirmed=false`; az új root unit/runtime
nincs a hoston telepítve. HC-45 **Ellenőrzött, helyben; nincs élesítve**.
Összesítés: **38 ellenőrzött, 9 nyitott, 1 folyamatban, 0 ellenőrzésre váró**.
HC-41 folyamatban marad, HC-35/36 kimarad, a fizikai AI-próba külön függőség.

[Részletes jegyzőkönyv](docs/hc45-vm-restore-20261030.md),
[gépi eredmények](docs/audit-evidence/hc45-vm-20261030/summary.json),
[frissített átadási terv](docs/hc41-44-release-preparation.md).


## REPAIR-047 — Igazolt ESP-cím és HC-35/36 a közös r10 kiadásban (2026-10-31)

**Kérés/alap:** a felhasználó megerősítette a 192.168.1.179 irrigation ESP-címet és
külön a routeres DHCP-foglalást, kérte a HC-35/36 közös csomagba építését.
Elolvasva HC-35/36 bizonyítéka, F5a, korábbi javítási/PG-tesztbizonyítékok és az
r10 F1a/F1b/F6a kapcsolódása. Más auditpontot nem javítottunk automatikusan,
élesítés nem történt. A korábbi r10 kit teljes másolata külön megőrizve.

**Módosítás:** az r8 függőség-/appalapra a HC-35/36 binding, power-wall, új koordinátor,
fogyasztói modulok és frontend együtt került, a HC-44 scoped AI/root IPC/non-root
működésének megőrzésével. A factory már nem távolítja el a klímakoordinátort;
a frontend építése és az összetartozó backend/frontend image-pár ellenőrzése is
része a csomagnak. Hét kiadási image, 21 régi/új/infrastruktúra-image offline;
DB-migráció és függőségfrissítés nincs. Az ESP megerősítése a privát jóváhagyásban,
policyban és újratitkosított bundle-ben rögzítve; valós age-roundtrip sikeres.

**Szükséges átadási/restore-függőség:** az új helper a régi backend leállítása után
advisory lockos tranzakcióban naplózza az előállapotot és visszavonja a függő
klímaventilátor-ON-időpontokat. Binding/policyflag, más ütemezett munka és fizikai
állapot megmarad. Futó backendnél megtagadja a műveletet. Rollbackkor az új backend
áll le először, szükség esetén a DB elindul, majd az új függő ON-ok visszavonódnak;
régi időpontot nem játszunk vissza. Full restore-nál DB-visszatöltés után,
szolgáltatás/appindítás előtt ugyanígy egyeztetünk, hibánál nincs továbblépés.
A privát receiptek megmaradnak; a restore-futások külön azonosítót használnak.
Az átadáskor az aktuális cél érvényes függő késleltetése is visszavonódik;
a normál automatika az aktuális állapotból hozhat létre új szándékot.

**Ellenőrzés:** 441 backend unit-/regressziós, 113 frontendteszt és Vite build,
19 valódi PostgreSQL-teszt transaction PgBounceren át, 54 célzott restore-/unitteszt,
0 failure/error/skip (a suite-ok átfednek). Öt valós átadási/restore-eset ellenőrzött:
futó backend tiltása, deploy- és rollbackkori törlés, SQL-hibánál valódi rollback
hamis siker nélkül, valamint pg_dump→üres DB→pg_restore után a régi ON törlése.
A kiválasztott binding és más ütemezett munka megmaradt; a kész új image moduljai
nem publikáltak régi ON-t. A teljes non-root backend/ingest + hitelesített MQTT +
PG/PgBouncer + root IPC integráció sikeres; e labor Docker CLI-je fixture.
A kész backend közös koordinátor-objektuma és scoped AI-koordinációja igazolt;
hat Python-image fájlegyezése, a frontend tényleges HTTP-indexe/admin-assetje rendben.
21 image/241 blob hash és linux/amd64 lánc ellenőrzött, a bundle-ben is a megerősített
ESP-policy van. A mai éles READ ONLY leltár: 11 érvényes szerepkör, 0 fallback,
0 függő klímaindítás; nem történt DB-/eszközmódosítás.

**Korlát:** a 2026-10-30-i teljes KVM-próba a HC-35/36 nélküli előző jelöltre
vonatkozik. A változatlan hostlánc bizonyítéka megmarad; a közös revízió teljes
VM-bootstrap/reboot és teljes r9→r10→r9 cutover nem ismétlődött. A mai restore
elkülönített klímaállapot-fixture, nem teljes éles host/DB. Fizikai ventilátor/ESP,
böngészős átadás, PC-kliens reconnect és AI-SSD/offsite próba nem futott.
A teszt-harness köztes hibái javítva, csak a végső sikeres futások kaptak minősítést.

**Éles változatlanság/státusz:** 16 konténer ID/image/start/restart, 37 védett
hostfájl, safety-forrás, MQTT-konfiguráció, eredeti audit és r9 override változatlan.
A korábbi image/környezet és 11 hálózati cím egyezik az előkészített rollbackkel.
Az új runtime/root unit nincs telepítve. HC-35/36 a közös r10-ben előkészítve,
HC-41 folyamatban marad; **38 ellenőrzött, 9 nyitott, 1 folyamatban**. Az élesítés
külön utasításra, friss mentés/baseline és root hostjog mellett történhet; továbbra
is 13 szolgáltatás érintett, köztük PostgreSQL, rövid DB/API-kieséssel.

[Részletes közös csomag](docs/hc3536-access-combined-20261031.md),
[gépi bizonyítékok](docs/audit-evidence/hc3536-access-combined-20261031/summary.json).


## REPAIR-048 — Engedélyezett r10 élesítés előellenőrzése; rootjogra vár (2026-10-31)

A felhasználó engedélyezte a közös HC-35/36 + HC-41/44 élesítést.
A lezárt csomag integritása, a korábbi image/környezet és 11 endpoint egyezése
újra ellenőrzött. 16 éles konténer és 37 védett hostfájl változatlan;
HTTP200 health, DB/MQTT rendben. Új auditpontot nem javítottunk.

Friss helyi teljes mentés készült: `homecontrol_2026-10-31_15-04-42_75a83052bbed4203ba4afee69bcdd15f.tar.gz`,
134 787 588 byte, SHA256 `eb20a8b808cd0944230358adc70e84a47d201ecdce316978461a049f560555ec`.
A root worker publikációja 975 belső checksumot ellenőrzött; completed/exit0,
hiányzó kötelező cél nincs. A külön UID1000 ellenőrző a root/0600 archívumot
nem tudta újraolvasni; az eredmény forrása a működő root mentési worker receiptje.
AI/offsite mentés a korábbi korlátozott üzem miatt kimarad.

**Blokkoló feltétel:** az éles hoston `sudo -n -l` → `a password is required`;
a telepítő UID0-t igényel a systemd/nft/jogosultságok átadásához.
Nem engedélyhiány: az élesítés jóváhagyott, a végrehajtási rootjog hiányzik.
A telepítés nem indult, transition könyvtár nincs, szolgáltatáscsere és rollback
nem történt. A lezárt csomag nem módosult, `deployed=false`.
Aktív továbbra is r9 ingest/r8 backend/frontend; HC-41 folyamatban,
az auditösszesítés változatlan. A root terminálparancs és átadási feltételek
[PENDING](backups/deployments/hc-access-20261030-r10/PENDING.md),
[gépi előellenőrzés](backups/deployments/hc-access-20261030-r10/preflight.json).


## REPAIR-049 — Közös HC-35/36 + HC-41/44 r10 élesítve (2026-10-31)

A rootjog-blokkot a felhasználó terminálos sudo-telepítése feloldotta;
telepítő: deploy/success=true, konténerindulás 15:12:43–15:13:05 CET.
13 szolgáltatás az új kanonikus runtime szerint cserélődött, 14 pinned szolgáltatás
fut, 0 restart. Backend/frontend együtt, DB-migráció nincs. Más auditpontot nem
javítottunk automatikusan. A korábbi kit/mentések megmaradtak.

**Utóellenőrzés:** HTTP200 DB/MQTT, egészséges PG/PgBouncer/ingest;
UID10001/read-only/socket nélküli backend szerződés 0 probléma,
engedélyezett root inventory működik. Guard/hostops active/success,
12 generált unit/drop-in pontos egyezés, timerek/watcherek aktívak.
11 endpoint és 11 valid/fallback nélküli binding egyezik az előkészítéssel.
HC-kliensek saját MQTT-identitáson, ESP .179 legacy kivételen reconnect;
1884 anonymous CONNACK5, hostról a legacy MQTT-kapcsolat tiltása megfigyelt,
hitelesített Zigbee online. Nft-táblák közvetlen rootkiolvasása nem történt.
ESP/Nano STATUS/TELE friss (18s/0s), pumpa0/szelepek CLOSED, téli profil,
AI-offline megmaradt. Safety idle/latch=false, nincs értékelési hiba.
Fizikai parancs/ACK nem volt. Frontend/proxy és proxyn át API HTTP200.
Ingest új mérésmentés igazolt; induláskor 71 db_unavailable üzenet eldobva,
a számláló utána stabil, db_failure0. Ez a jóváhagyott kiesési politika.
Eredeti audit/safety-forrás és 3 nem érintett konténer változatlan.

**Új runtime mentési próba:** non-root API → root IPC → kanonikus worker,
`b51307f4cb2145c69c489bb40e3fabd4`, completed/exit0;
786731706 byte, 1678 checksum, SHA256
`3e47f0d5900d33d8a37b723b9a519e1793312aa900345ca4e12314774f7ea4dd`.
Az archívumok root-worker publikációs receipt alapján ellenőrzöttek;
UID1000 a 0600/root archívumot és transition/handover receiptet közvetlenül
nem olvasta újra. Új teljes restore/reboot/éles rollback nem futott.

**Nyitott átadási tétel:** X10 map-refresh Xiaomi file-URL hiba/exit1;
robot/MQTT állapot friss, hibaeredet nem igazolt, automatikus javítás nem történt.
PC dashboard/Explorer reconnect, fizikai STOP/ventilátor próba és AI SSD/offsite
próba marad. A közös revízió korábbi KVM-bizonyítási korlátja változatlan.
HC-35/36 és HC-44 éles, a HC-45 szükséges runtime-integrációja aktív;
HC-41 az anonim ESP legacy kivétel miatt folyamatban marad.
Összesítés változatlan: **38 ellenőrzött, 9 nyitott, 1 folyamatban**.

[Éles átadás/rollback](backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md),
[gépi ellenőrzés](backups/deployments/hc-access-20261030-r10/verification.json).


## REPAIR-050 — X10 felhősession diagnózis és átadási kiegészítés (2026-10-31)

A felhasználó az X10 térképhibájának és a fennmaradó átadási tételek vizsgálatát
kérte. Igazolt Xiaomi HTTP426 / SERVICETOKEN_EXPIRED; az augusztus21-i sessiont
használja a térképletöltő. A felhasználó csak a helyi robottokent frissítette.
A connector nem-200 ága None-t ad, ez magyarázza a korábbi általános URL-hibát.
MQTT és robotállapot-frissülés működik; új fiókbelépés nélkül a térkép nem javítható.

Elkészült `scripts/refresh_x10_cloud_auth.py`: terminálos jelszó/2FA a meglévő
X10 konténerben; fiókegyezés és felhővalidálás előtt nem cserél hitelesítést,
0600 atomikus csere és privát korábbi példány, nincs automatikus bridge-restart.
Négy teszt sikeres (hibás session, más fiók, sikeres csere/módok, replace-hiba).
Nem interaktív futtatás tiltása ellenőrzött. Éles hitelesítés még nem változott;
a térképhiba azonosított, nem minősült javítottnak. Új image/kit nem készült.

Éles Explorer és dashboard saját jelszava MQTT5/loopback1884-en sikeresen
csatlakozott és saját megengedett topicról adatot olvasott. Nincs éles publish,
eszközvezérlés vagy védelmi ACK. Ez nem bizonyítja a PC SSH-alagútját/GUI-ját;
fizikai STOP/ventilátor és AI SSD/offsite próba továbbra is külön függőség.
Más auditpontot nem javítottunk; az auditösszesítés változatlan.
[X10 eljárás](docs/x10-cloud-session-20261031.md),
[fennmaradó tételek](backups/deployments/hc-access-20261030-r10/FOLLOWUPS.md).


## REPAIR-051 — X10 belépési segéd a működő natív tokenkinyerővel (2026-10-31)

A felhasználó az első segédnél elakadt, a régi tokenkinyerővel eszközlistát kapott.
A pontos elakadási üzenet nem áll rendelkezésre. A régi helyi, repo és aktív
image tokenkinyerője SHA256-egyező. A korábbi segéd kizárólag a Password
connectort indította és túl általános hibát jelzett; ezt korrigáltuk.
Az éles session továbbra is augusztus21-i, HTTP426/SERVICETOKEN_EXPIRED.
A listázott helyi robottoken nem teljes felhősession; aktív robot-IP már .158.
A felhasználó által bemásolt tokeneket nem másoltuk dokumentumba/kódba.

A `refresh_x10_cloud_auth.py` most a működő helyi program eredeti p/q loginját
használja, a bejelentkezett connectorból felhővalidálás után veszi át a sessiont,
az eszköztokenek listázása előtt megállítja az eredeti főfolyamatot. A session
csak stdin-en jut az X10 konténer mentési részébe; ott újból fiók/régió ellenőrzés,
0600 atomikus csere és korábbi privát példány. Nem módosítja a régi tokenkinyerőt,
image-et, lezárt r10-et, robotparancsot vagy bridge-restartot nem hajt végre.
A helyi belépési és céloldali mentési hibák külön, titokmentesen jelezhetők.

8 célzott teszt sikeres, ezen belül mindkét natív menüág fixture-es session-
átadása és az eszköztoken-listázás kihagyása. A tényleges helyi tokenkinyerő
p/q menüjével külön két szintetikus belépési illesztési próba is sikeres,
hálózati kérés és hitelesítéscsere nélkül. Éles új belépés még szükséges;
a térképhibát nem minősítettük javítottnak. Más auditpont/státusz nem módosult.
[Részletes eljárás](docs/x10-cloud-session-20261031.md),
[gépi ellenőrzés](backups/deployments/hc-access-20261030-r10/x10-login-helper-check.json).


## REPAIR-052 — X10 CAPTCHA/QR-kép SSH-alagutas előnézete (2026-10-31)

A felhasználó a CAPTCHA-képet nem tudta megnyitni. A segéd saját, ideiglenes,
kizárólag 127.0.0.1:31415-re kötött képszervert kapott; a fejlesztői PC31416
SSH-alagútján nézhető meg az aktuális kép. A natív extractor CAPTCHA/QR callbackjét
csak a belépés idejére cseréli, végül visszaállítja és leállítja a képszervert.
A megoldást továbbra is a felhasználó írja be. Nincs új konténer/éles port,
broker- vagy image-módosítás, robotparancs, bridge-restart, hitelesítéscsere.

12 célzott teszt sikeres (a korábbi 8-cal együtt), valódi helyi HTTP/PNG/JPEG
szintetikus képadatokkal: legfrissebb kép, cache tiltása, loopback kötés,
leállítás, ismeretlen útvonal tiltása, portfoglaltság és callback-cleanup.
Éles PC/alagút/böngésző, felhasználói belépés és sikeres térképletöltés még hiányzik.
Más auditpont/státusz nem módosult.
[Kapcsolódási lépések](docs/x10-cloud-session-20261031.md),
[gépi ellenőrzés](backups/deployments/hc-access-20261030-r10/x10-captcha-preview-check.json).


## REPAIR-053 — Működő X10 belépő megőrizve, későbbi webes beépítés rögzítve (2026-10-31)

A felhasználó sikeresnek jelezte a CAPTCHA/alagutas folyamatot, kérte a kód
megőrzését és későbbi HC-webes beépítését. Új, titokmentes forráscsomag:
`backups/releases/hc-x10-cloud-login-20261031-v1`, 8 fájl SHA256-leltárral,
az aktív helper/teszt/natív extractor pontos másolata. A korábbi 12 sikeres
célzott teszt ehhez a változatlan kódhoz tartozik; fájlhash-egyezés újra ellenőrzött.
A csomagban nincs auth/session/token/jelszó vagy CAPTCHA-kép.

Éles új session mentése igazolt (16:04:25 CET), privát korábbi másolat megmaradt.
Xiaomi HTTP200/code0, 3 mentett térkép újrarenderelve (16:05:13 CET),
DB/MQTT health rendben. Nincs restart/robotmozgatás; aktív takarítás közbeni
live-map próba még külön kell, korábbi retained hiba önmagában nem friss próba.
A webes folyamat és a HC-44/admin/session/titokmentési függőségek feljegyezve;
webes kód/endpoint, új image vagy más auditjavítás most nem készült.
[Webes feladat](docs/x10-cloud-web-integration.md),
[megőrzött csomag](backups/releases/hc-x10-cloud-login-20261031-v1/README.md).


## REPAIR-054 — HC-12 korlátos bridge-sor és egy parancsgazda (2026-10-31)

**Alap/előfeltétel:** HC-12, I. reprodukciós táblázat, J. AST/barrier bizonyíték,
F10 és F0/F2 átnézve. Az aktuális 9 forrásfile hash és 16 konténer baseline rögzítve.
A korábbi Tuya két eredeti fogyasztójából fixture-rel ismét OFF→ON sorrend
reprodukálva; az aktuátor valódi eszközhívást nem végez.

**Javítás:** bridge-enként egy CommandDispatcher/worker és korlátos memóriasor;
Tuya polling nem fogyasztja a sort, Gree/X10 nem indít üzenetenként szálat.
32 várakozó (egy hely STOP/OFF számára), 4096 byte payload, Tuya/Gree 30s,
X10 180s konfigurálható kor, monotón deadline. Normál FIFO, mozgási parancsok
általános összevonása nélkül. STOP/OFF érvényes, saját célra vonatkozó barrier:
a korábbi várakozó szándékokat visszavonja, a már futó I/O-t nem szakítja meg,
későbbi őrzött lépéseit tiltja. Új, STOP utáni ON/start végrehajtható.
Retained replay, telítettség, lejárat, offline/reset és shutdown külön kódot ad;
reconnect/restartkor nincs régi sorvisszajátszás.

**Szükséges belső függőségek:** Tuya name/id alias feloldva, eszközrebuild is
ugyanazzal a lockkal; a guard a poll-lock után is ellenőriz. Gree validált OFF,
kezdeti olvasás után és push/persist előtt újraellenőrzés, queue-replyben eredeti
hc_execution_id. X10 guard a MIIO-flockon belül; belső watch/direct-start is
ugyanazon workerre került, nem halmozódik és MQTT-ről nem hívható. STOP a HC
helyi delayed-start intentet akkor is törli, ha a fizikai küldés hibázik;
a robotban már tárolt jövőbeli/heti ütemezést nem törli automatikusan.
Tuya új callback/sorelutasítása közvetlen QoS0, nem retained, nem kezdeményez
szinkron reconnectet; offline csak lokális queue-számláló marad. A kanonikus
standalone modult három azonos contextmásolat és csomagolási hash-teszt kíséri;
Tuya/Gree Dockerfile a meglévő MQTT-auth helpert is másolja az új modullal.

**Ellenőrzés:** 33 queue/tényleges bridge-függvényes, 32 X10 runtime/watchdog/map,
25 scheduler/feedback teszt, összesen 90, 0 failure/error/skip. Külön 9 valódi
izolált brokeres eset sikeres (3 bridge × retained, full+STOP, reconnect),
helyettesített aktuátorral, publikált hostport nélkül. Callbackkapcsolat a labor
adaptere, a valódi on_message/handler/queue futott. 13 queue_full és 3 visszavont
várakozó intent/bridge; aktuátorhívás ON→OFF/start→stop, reconnectkor nincs replay.
2000-es burst, élettartam a poll-lock mögött, foglalt transportzár utáni guard,
hibás kevert OFF és visszautasított STOP atomikussága is ellenőrzött.
A köztes harness-útvonal feltételezéseket javítottuk; csak a végső futás minősített.

**Határ:** hardveres/full-process karbantartási próba és külön pinned image-
átadás még szükséges. HC-32 általános publisher/fingerprint hibája, HC-23/43
health/build/feldolgozott függőségfrissítés külön nyitott; nem kaptak automatikus
javítást. Tuya mqtt_publish/mqtt_publish_changed/parse_partial/mqtt_publish_device
AST-egyező a korábbival, HC-09/34 szerződés-regresszió sikeres.
Nincs új külső dependency vagy DB-migráció, backend/frontend változatlan.

**Éles állapot/rollback:** nincs élesítés vagy fizikai parancs. Mind a 16 éles
konténer ID/image/start/restart/status és a r10 646 lezárt forrásfájlja változatlan;
az eredeti audit hash megmaradt. A lokális korábbi források F0 SHA-val igazolt
másolatai az evidence/original alatt megvannak; később régi image visszatehető,
RAM-sor vagy régi X10 delayed-start intent visszajátszása nélkül.
HC-12 **Ellenőrzött helyben, nincs élesítve**. Új összesítés:
**39 ellenőrzött, 8 nyitott, 1 folyamatban (HC-41)**.
Az elavult nyilvántartás-fejléc az egyébként már naplózott r10 éles állapotra
frissítve; más auditpont státusza nem változott.

[Részletes változás/korlát/átadás](docs/hc12-bridge-commands.md),
[gépi összesítés](docs/audit-evidence/hc12-20261031/summary.json).

### REPAIR-055 — HC-32 és a HC-23/43 kapcsolódó helyi részjavításai

- **Dátum / végrehajtó:** 2026-10-31, Codex, Europe/Budapest.
- **Felhatalmazás és határ:** a felhasználó a HC-12 függőségeire adott „ezeket is csináld meg” kéréssel engedélyezte HC-32/23/43 munkáját. Élesítési utasítás nem érkezett. Más auditpontot nem zártunk le; HC-24/26 nem módosult. Az AI SSD miatti tiltás megmaradt.
- **Elolvasva:** HC-23, HC-32, HC-43; HC-32 I./J. reprodukció; HC-43 L.6/M.6 leltár/feltételek; F10 előfeltételek, regresszió, rollback. Kiindulás: `docs/audit-evidence/hc32-23-43-20261031/before.json`, 16 konténer és tényleges Python-leltár; eredeti források ugyanott az `original/` alatt.
- **HC-32 — Ellenőrzött, nincs élesítve:** `mqtt_publish()` explicit helyi paho-befogadási bool; sikertelen rc/kivétel/offline nem frissít fingerprintet. A network loop birtokolja a reconnectet. Kapcsolatgeneráció-váltás törli a cache-t, küldés közbeni disconnect megakadályozza a téves könyvelést. Nincs payload-replay: a következő poll aktuális értéke küldhető. 100/s, burst100 konfigurálható korlát; 8192 cache-topic, paho queue256/in-flight20; körönként forgó eszközsorrend. A siker QoS0 és QoS1 esetén is **helyi kliensbefogadás, nem PUBACK vagy fizikai állapot**. A heartbeat és a `current_a` payload megmarad.
- **HC-23 — Folyamatban:** új, mellékhatásmentes backend live/worker/ready végpontok, leállítható retry-bootstrap; a Docker-healthcheck figyeli a vezérlési worker haladását is. Tuya/Gree/X10/Growatt önálló, processzazonossághoz kötött worker-health, külön siker/haladás/kapcsolat; async MQTT-indulás. Gree reconnect a meglévő pollt ébreszti. AI-gateway külön live/ready; a live nem hív providert. Teljes Python-lockok, digestes/explicit alapok, hash-elt biztonsági wheelek, közös célzott unit/integritásparancsok, külön candidate-image-ek készültek. Globális tesztprofil/HA/AI és pozitív kiadási startup/restore/rollback még szükséges; teljes HC-23 nem lezárt.
- **HC-43 — Folyamatban:** friss teljes nyilvános PyPI OSV-katalógus helyi összevetése, privát leltár feltöltése nélkül. Célzott Flask 3.1.3, Pillow 13.0.0, urllib3 2.8.0, Requests 2.34.2, certifi 2026.10.18, Werkzeug 3.1.9, pip 26.2.2, setuptools 84.2.1, ahol telepítve vannak. Gree 3.2.0/python-miio 0.5.12 protokollverzió és Click 8.1.8 megmaradt. Öt frontend-tranzitív csomag explicit javított override/lock. 15 futó konténer friss OS-leltára rögzítve. A hét Python-candidate értékelhető OSV-verziótartományaiban 0 találat; 53 Git-tartományt is tartalmazó rekord `unknown`. Teljes friss npm-katalógus/OS-scan és kompatibilis alapimage-/HA-frissítés nincs kész; HA 2026.7.2 változatlan. Ez nem sérülékenységmentességi tanúsítvány.
- **Candidate-ek:** backend, ingest, Tuya, Gree, X10, Growatt, helyi AI-gateway és frontend, mind külön image-ID-val a `backups/releases/hc-f10-20261031-candidate` könyvtárban. Alapjuk az r10 rögzített image-e; a frontendből a régi statikus bundle-ök is eltávolítva. Nem kész telepítőcsomag, nincs automatikus deploy. Nincs DB-migráció.
- **Sikeres ellenőrzés:** 339 célzott backend + 54 bridge/publisher/health + 33 X10/Pillow + 52 ingest + 113 frontend = **591 célzott teszt**, nincs kihagyás ezekben a suite-okban; frontend build, `miiocli --help`, 9 queue/STOP/retained/reconnect brokeres eset + 6 új Tuya publisher brokeres eset; hét teljes Python-processz DB/MQTT/provider nélkül él és helyesen nem ready. Frontend külön statikus HTTP-próba sikeres, szintetikus backend DNS-sel. Image-források, wheel-hash, teljes csomagzár, `pip check`, frontend-assetkészlet és AI-tiltás ellenőrzött. Laborok elkülönítve, hardverparancs nem ment ki.
- **Korlát:** a széles backend discovery nem zöld: régi és új csomagokkal egyaránt 998 teszt, ugyanaz a 29 failure + 7 error, 183 skip; új hibás tesztazonosító nincs. Profil/root/sealed-runner/firmware-fixture és PostgreSQL-környezet eltérései külön dokumentálva. Nem nevezzük teljes sikeres regressziónak; a végső worker-health és audit-tool kiegészítése a célzott 339-es suite-ban ellenőrzött.
- **Függőségek / kiadási kapuk:** globális HC-23/43, HA saját támogatott kiadásával végzett DB-/integrációpróba, OS/advisory triage, új pozitív DB/MQTT startup/restore/rollback, külön immutable kiadás/hostops-integráció, friss mentés és felügyelt bridge-hardverpróbák. X10 felhő-/élőtérkép smoke és új certifi bizalmi lánc ellenőrzése szükséges. Ezek nem jogosítanak más auditpont automatikus javítására. A HC-32 külön szoftveres hibajavítása lezárt, a teljes globális HC-23/43 nem.
- **Éles változatlanság:** 16 konténer ID/image/start/restart/status egyezik az előállapottal; 646 lezárt r10 forrás, az aktív Compose és az eredeti audit hash-e változatlan. A tesztkonténerek és -hálózatok eltávolítva.
- **Visszaállítás:** most helyi forrás-/candidate-visszaállítás lehetséges az `original/` és az image-lockok alapján. Későbbi éles rollback komponensenként az előző image-re, régi RAM-parancssor és vezérlési szándék visszajátszása nélkül. Az r10 lezárt csomagjához nem nyúltunk.
- **Részletek / bizonyíték:** [kapcsolódó javítások](docs/hc32-23-43-followups.md), [gépi összegzés](docs/audit-evidence/hc32-23-43-20261031/summary.json), [teszteredmények](docs/audit-evidence/hc32-23-43-20261031/unit-results.json), [éles változatlanság](docs/audit-evidence/hc32-23-43-20261031/after.json).


## REPAIR-056 — HC-12/32 és HC-23/43 részjavítás r11 élesítési csomagja (2026-10-31)

**Felhatalmazás:** „mehet az élesítés”. Az eredeti audit HC-12/23/32/43 pontjai,
HC-12/32 I./J. bizonyítékai és F10 feltételei ismét áttekintve. Auditstátusz és
más auditpont kódja nem változott; ez a REPAIR-054/055 kiadási integrációja.

**Elkészült:** `scripts/f10_release/` előkészítő, telepítő, ellenőrző és seal
eszközök, illetve `backups/releases/hc-f10-20261031-r11`. Nyolc alkalmazás
immutable image-e, külön r11 runtime és privát környezet, a meglévő identitások
megőrzésével. A DB/MQTT/HA/Zigbee/proxy/mDNS nem cserélődik. Új SQL nincs.
Az AI SSD-tiltása, a téli profil, a védelmi konfiguráció és az ESP 192.168.1.179
legacy kivétele megmarad. A root telepítő ellenőrzi a változatlan éles előállapotot,
aktív öntözés és takarító robot mellett leáll, friss mentést és ellenőrzött age
bundle-t készít. A leállítás után a korábbi függő ventilátor-ON szándékot törli;
bindingot és policy flag-et nem töröl. Nyolc alkalmazásra szűkített `--no-deps`
váltás, health/readiness/hostops/UID/mount-ellenőrzés, hibakor rollback. Időzítők
állapota és régi konfiguráció/metadata snapshotban; későbbi release-re nem fut
rá a régi rollback. Előkészítési hiba előtt nincs alkalmazás-leállítás.
Az új backup worker minden release privát image-cache-ét kizárja az infra
rsyncből, és csak az aktív, ellenőrzött recovery-archívumot teszi a mentésbe.

**Új ellenőrzés:** 10 telepítőteszt sikeres: részleges stop/install/start/readiness
hiba, megszakítás, időzítő-visszaállítás, későbbi release elleni rollback-tiltás,
scope, útvonalak és tesztkulcsos age titkosítás/visszafejtés tényleges roundtripje.
Eldobható, külső hálózat és hostport nélküli, generált hitelesítési adatú valódi
PostgreSQL/PgBouncer/MQTT lab: régi → új → régi → DB-dumpból visszatöltött új
backend; readiness, perzisztens próbaadat, UID10001 és root hostops név szerinti
capability sikeres. A root executor Docker CLI-ja helyettesítő; sem éles adatot,
sem Docker-daemon socketet nem kapott. Az új ingest DB/MQTT-ready. A ventilátor
handover valódi SQL-je leállított lab backend mellett sikeres. Ez nem új teljes
KVM/systemd-próba és nem fizikai eszközkapcsolás.

A 24 régi és új image-es offline recovery-archívum (1 411 092 197 bájt) minden
OCI-blob-hashét, aktuális platformrétegét és image-készletét ellenőriztük;
a tényleges Docker-load sikeres, konténercsere nélkül. SHA-256:
`b179836e78ce8f3fa359673e954de9eb07a32ed03a3e8e8ce6a7e18eef9cdd20`.
A nyolc candidate image forrás-/wheelfájljai, hét teljes Python-csomagzár,
`pip check`, frontend assetek és AI-korlátozás újra ellenőrizve. A korábbi
591 célzott teszt, 15 brokeres eset és 7 processzpróba bizonyítéka megőrizve;
nem állítunk új teljes suite-sikert. A széles discovery 29 failure/7 error/
183 skip eredménye változatlan diagnosztikai korlát.

**Éles előállapot / mentés:** 16/16 konténer ID/image változatlan, 15 fut;
DB/MQTT jó, X10 tölt, aktív öntözés nincs. API-n indított helyi teljes mentés
`57f4aba7444843fda20c512d848264f4`: completed, 1737 ellenőrzött fájl,
787 723 971 bájt; SHA-256
`033ffabfa122ab6dbdfd82a4a569c04d41d08e0696ea7daa78744ceeec914032`.
A telepítő a tényleges váltáskor új mentést követel. Az r10 646 lezárt
forráshash-e és az eredeti audit SHA-256-ja változatlan.

**Még nincs élesítve:** az automatikus jóváhagyási ellenőrzés a mentett Xiaomi-
munkamenet külső Xiaomi-felhőnél történő használatát külön konkrét jóváhagyás
hiányában elutasította. Az async kérdés elküldve, munkamenetes próba nem futott.
Az új certifi 2026.10.18 névtelen TLS-próbája sikeres (403 hitelesítés nélkül),
de ez nem igazol teljes térképletöltést. A release-ready flag false marad.
A valódi hoston `sudo -n true` jelszót kér, ezért a privát root-staging, friss
telepítéskori mentés, systemd/Compose-váltás és éles utóellenőrzés még nem futott.
A [kiadási leírás](backups/releases/hc-f10-20261031-r11/README.md) tartalmazza
az előkészített pontos deploy/rollback-parancsot és az átvételi ellenőrzést;
[a függő állapot](backups/deployments/hc-f10-20261031-r11/PENDING.md) naprakész.
A globális HC-23/43, HA/OS/advisory triage és a fizikai AI-SSD-próba külön marad.


**REPAIR-056 folytatás — Xiaomi-jóváhagyás megérkezett:** „Igen, mehet a Xiaomi-
felhőpróba”. Az első kísérlet `PermissionError` miatt, a root:root 0600 fájl
olvasásánál állt meg; külső hitelesítés nem történt. A védett fájlhoz nem adtunk
szélesebb jogosultságot, Docker-root olvasással nem kerültük meg. Az előkészített
helyi sudo `activate.py` védett ideiglenes másolattal, UID1000 tesztkonténerrel
ellenőrzi a munkamenetet/térképet, majd csak sikeres eredménnyel frissíti a
lezárt elfogadási nyugtát és indítja a guarded deployt. Sikertelen eredmény
nem oldja fel a kaput; timeout a tesztkonténert és a másolatot is takarítja.
Új két regresszióval 12 telepítőteszt sikeres. Jóváhagyás és első hibás kísérlet
sanitizált nyugtája a kiadási evidence-ben. A felhőpróba sikeres végrehajtása és
az éles váltás továbbra is helyi sudo-ra vár; a [pontos parancs](backups/deployments/hc-f10-20261031-r11/PENDING.md)
rögzítve. Auditstátusz nem változott.


**REPAIR-056 incidens és javítás:** a felhasználó sudo-val indított aktiválása
sikeresen letöltötte és JSON-ként dekódolta a Xiaomi térképet (6062 bájt,
certifi 2026.10.18, robotparancs nélkül). A friss mentés/snapshot után a váltás
leállította az alkalmazásokat, majd `platform().locked` hívásnál megállt:
a függvény az access_release/install.py modulban van, a common modulban nincs.
Ugyanaz a hiba a rollbacket is megállította. Ez a telepítő hibája; a korábbi
hibabefecskendezéses fixture nem futtatta ezt az adapterhívást.

A javítás explicit `install.locked` adaptert használ, és a preflight importtal
még leállítás előtt ellenőrzi elérhetőségét. Két új regresszió a tényleges
Cutover.install és rollback metódust futtatja valódi flockokkal, ellenőrzi a
két lock foglaltságát és az inode-ok megőrzését; a közös modulnak továbbra sincs
locked attribútuma. Összesen 14 teszt sikeres.

A diagnózis idején nyolc alkalmazás és hostops áll, DB/MQTT/Zigbee/HA/proxy
fut; r11 runtime/private nincs, canonical marker/Compose r10. A javított
recover.py kizárólag az ismert AttributeError, eredeti image/ID/Compose,
ellenőrzött forrás és root snapshot mellett állítja vissza az r10-et; nem
végez új élesítést. A javított deploy forrását és a recoveryt a meglévő kitbe
tettük, az eredeti manifestet bizonyítékként változatlanul hagytuk. Emiatt a
normál deploy szándékosan integritáshibával leállna; most csak recover futtatható.
A sudo -n helyreállítási kísérlet jelszót kért, így a tényleges helyreállítás
még nem történt meg. A felhasználónak helyi sudo-parancsot adtunk át.
Bizonyíték: `evidence/lock-repair.json` és `lock-repair-tests.txt`. Az auditpontok
státusza és az eredeti audit változatlan. A helyreállítás sikerét nem állítjuk
addig, amíg a parancs eredménye és az élő ellenőrzés nem igazolja.


**REPAIR-056 helyreállítás ellenőrzése és javított r12:** a felhasználó
`recover_r10 success:true, r11_deployed:false` eredményt adott. Az ezt követő
élő ellenőrzés szerint minden korábbi image változatlan, 15 konténer fut,
Adminer szándékosan áll. DB/MQTT és hostops jó, MQTT guard aktív, X10 online és
tölt, telemetriája elérhető, öntözési és CO/füst API sikeres. A korábban aktív
helyi backup/log/restore és postboot időzítők futnak; AI heti/restic inaktív.
Bizonyíték: r11 `evidence/recovery-live.json`, r12 `evidence/production-before.json`.
A leállási incidens rendezett; r11 nem települt.

A változatlan alkalmazásimage-ekből külön `hc-f10-20261031-r12` készült,
önálló runtime/private/transition célokkal, az r11 root-staging megőrzésével.
Az explicit install.locked mellett a preflight minden használt adaptert és
még a szolgáltatások leállítása előtt a valódi közös lockokat is ellenőrzi.
A 14 regresszió mellé a tényleges teljes install_files/snapshot-rollback
ideiglenes fájlrendszerben végzett próbája és a titokmentes fázisnyugta
ellenőrzése került: **16 sikeres telepítőteszt**. A fixture root chown és
systemd/Docker hívásai helyettesítettek, nem új teljes VM-/hardverpróba.
A sikeres r10-helyreállítás a javított rollback valódi hostos működését is
bizonyítja. A runtime/image-ek és a korábbi 591 célzott teszt/15 brokeres eset/
7 processzpróba változatlan; a munkamenetes Xiaomi-próba ugyanazzal az image-dzsel
sikeres volt. A 24 image-es archívum hash-e és betölthetősége megmaradt.

Az r12 új mentést és age-roundtripet követel, majd csak nyolc alkalmazást cserél;
hiba esetén snapshot-rollback, korábbi ON szándék visszajátszása nélkül. A root
aktiválás és az éles utóellenőrzés még nem futott, helyi sudo-ra vár. A meglévő
felhasználói élesítési és Xiaomi-engedély érvényes. Más auditpont nem változott,
az eredeti audit hash-e változatlan. [Parancsok és korlátok](backups/releases/hc-f10-20261031-r12/README.md).


**REPAIR-056 r12 éles utóellenőrzés:** felhasználói activate success:true,
Xiaomi-munkamenetes térképletöltés 6062 bájt, robotparancs nélkül. Mind a nyolc
új image fut, healthy, restart0; mind a többi konténer ID/image változatlan.
Backend live/workers/ready és DB/MQTT sikeres, nincs hiányzó/stalled/unready
worker, frontend HTTP200. Tuya/Gree/X10/Growatt helyi worker ready/MQTT-connected,
friss sikerrel. 690 telepített forráshash egyezik. Hostops és MQTT guard aktív,
a korábbi időzítők helyreálltak. Öntözés winter: vezérlések tiltva, mérésnaplózás
engedélyezett. CO/füst API idle, latched=false, danger=false, kiértékelési hiba nincs;
konfiguráció nem változott. Külső AI restricted/valid=true.

Az első r12 helyi mentés completed, returncode0, run
7595700918fe4e579fcba0cd16149fe3, 2494 ellenőrzött fájl,
1 550 379 633 bájt, SHA-256
`dee40275ab23f000f4c08ea48e386284307bd1f7f0abf90ba27b3aec8ccada2d`.
A tényleges új backup/aktív offline cache integráció sikeres; ez nem új VM-restore.
[Átadás](backups/deployments/hc-f10-20261031-r12/DEPLOYMENT.md).

**REPAIR-056 X10 indulási regresszió és r13 előkészítés:** az async MQTT-indulás
miatt a CONNACK előtti sikertelen online=1 publikáció cache-elve maradhatott,
így a callback nem írta felül a régi retained LWT 0-t. A robot ténylegesen
online/ready volt és friss adatot küldött; a scheduler offline-ként blokkolhatta.
Az online jelzést a szolgáltatás saját MQTT-szerepével, a megfigyelt ready állapot
után QoS1 nyugtával egyszer helyreigazítottuk; robotparancs nem történt.
A tartós, szűk javítás az on_connect három életjelét force=True módon küldi.
Más publisher/adatpayload/protokoll és auditpont nem változott.

Az azonos r12 alapú új X10 image változatlan teljes csomagleltára és baked
forráshash-e ellenőrzött. Három AST-regresszió a tényleges publisher/callbackkel:
a régi image kettőn hibázik, az új mindhármon sikeres. R13 16 telepítőteszt és
25 image-es offline cache OCI-blobonkénti vizsgálata/Docker-load sikeres.
Az r13 külön runtime/private/snapshot, csak X10 image-csere és backend-újraindítás;
más konténer futva marad. Friss mentés, age-roundtrip, korábbi közös lock-
és rollback-védelem megmarad. Még nincs élesítve, helyi sudo-ra vár.
[Pontos r13 parancs](backups/deployments/hc-f10-20261031-r13/PENDING.md).
A fizikai hardveres elfogadás és globális HC-23/43 továbbra is külön korlát;
az auditstátusz nem változott, az eredeti audit érintetlen.


**REPAIR-056 r13 éles utóellenőrzés:** a felhasználó activate success:true,
az új image-ből felhőhitelesítés/térképletöltés sikeres, 6062 bájt, robotparancs
nélkül. Aktív marker r13. Csak backend és X10 cserélődött, a másik 14 konténer
ID/image változatlan. Mind a nyolc alkalmazás a lezárt image-et futtatja,
running/healthy, restart0; mind a négy backend health-végpont sikeres,
DB/MQTT és összes worker ready. A telepített 690 forráshash ellenőrzött.
X10 bridge/online=1, status=online, connected és telemetria elérhető,
robot charging; az r13 indítása után kézi online-publikáció nem kellett.
A callback tartós korrekciója éles, a korábbi r12 egyszeri helyreigazítás
nem kellett megismétlődjön.

Öntözés winter profil: vezérlések tiltva, naplózás engedélyezett. CO/füst
idle/latched=false/danger=false, kiértékelési hiba nincs, védelem enabled=true;
konfigurációt nem változtattunk. Külső AI policy restricted/valid=true.
Hostops/guard és a korábbi időzítők rendben. Első r13 helyi mentés indítva,
run 4a933d9b7583435bbfe3e14e4b554d71; eredményét külön nyugta rögzíti.
[Éles átadás és visszaállítás](backups/deployments/hc-f10-20261031-r13/DEPLOYMENT.md),
bizonyíték `evidence/live-acceptance.json`. Fizikai STOP/OFF/élőtérképpróba
és globális HC-23/43/HA/OS/AI-SSD korlátok megmaradnak. Auditpont státusza
nem változott, eredeti audit hash-e változatlan.


**REPAIR-056 végső mentési nyugta:** Az első éles r13 helyi teljes mentés **completed, returncode0**: run `4a933d9b7583435bbfe3e14e4b554d71`,
3239 ellenőrzött fájl, 1552026123 bájt. Archívum:
`homecontrol_2026-10-31_21-41-40_4a933d9b7583435bbfe3e14e4b554d71.tar.gz`. SHA-256:
`5ab8c7e900ac2b53e2d286ba11752b9e30d9c70465b204947475a199ca27ec95`.
Ez az aktív r13 runtime és a 25 image-es cache integrált helyi mentését igazolja;
nem új teljes VM-/fizikai visszaállítási próba. A mentés utáni readiness, X10 online,
nyolc healthy/restart0 alkalmazás és frontend HTTP200 ismét sikeres. Nano online,
friss STATUS/TELE-mintákkal. Bizonyíték: `evidence/post-backup.json` és
`evidence/live-acceptance.json`. Fizikai STOP/OFF/takarítás alatti élőtérkép még felügyelt feladat.

## REPAIR-057 — AI-tól független routeres mentés, éles r15 (2026-11-01)

**Felhasználói irány:** a meghibásodott AI SSD helyett a router 2 TB-os USB-lemeze
a mentési cél; a külső Git-feltöltés megmarad. Az AI letiltva marad. Az FTP
LAN-on elért cél, a mentést HC-oldalon restic titkosítja. A root által védett
hitelesítést a felhasználó a helyi terminálon adta meg.

Az r14 élesítése után a párhuzamos FTP-listázás hamis hiányzó-pack hibát adott.
A három külön listázás minden packot megtalált; a közvetlen visszaolvasás is jó
volt. A sorosított listázással teljes repository-adatellenőrzés, archívum- és
PostgreSQL-restore sikerült. Az r15 ezt élesíti, a megőrzés előtt és után teljes
adatellenőrzéssel és a korábban felfüggesztett mentési időzítők visszakapcsolásával.

**Éles bizonyíték:** `b105be08ce6943fdb3b10cdf835547ee` heti futás completed,
returncode0; local_archive/restic/secrets_bundle/git_offsite/restic_retention
succeeded. Snapshot `b381d1287149a95a1277d4724969677bd53c11736d7eb4365f307336463b49d6`.
Az archívum 4788 checksumja és a külön PostgreSQL-visszaállítás ellenőrzött.
Napi 02:15, heti Sun 03:30 és havi ellenőrzési timer aktív/engedélyezett.
706 fagyasztott forráshash egyezik; readiness sikeres; az alkalmazások healthy.
Az AI-Gitea cél kifejezetten skipped, nem sikeres AI-mentésnek jelzett.

[Éles átvétel](backups/releases/hc-router-backup-20261101-r15/evidence/router-live-acceptance.json),
[utóellenőrzés](backups/releases/hc-router-backup-20261101-r15/evidence/post-live-check.json),
[incidens és javítás](docs/router-ftp-backup-incident-20261101.md),
[átadás/rollback](backups/deployments/hc-router-backup-20261101-r15/DEPLOYMENT.md).
A friss host teljes routeres bootstrapje ebből nem következik; külön REPAIR-058.
Az auditpontok darabszáma/státusza nem változik.

## REPAIR-058 — az SSD miatti mentési korlátok felülvizsgálata (2026-11-01, folyamatban)

**Felhasználói megerősítés:** „Igen, az AI maradjon letiltva; a mentési pontokat
zárjuk le.” A korábbi SSD/Gitea/restic/VM hivatkozások tételes átnézése elkészült.
A HC-31 szoftveres javítása ellenőrzött marad; a fizikai shutdown/OFF/wake
alpróba a letiltott gép későbbi újraaktiválásához kötött, nem végrehajtott próba.
A régi AI-Gitea történetét nem minősítjük ellenőrzöttnek.

Az aktuális routeres repository, Git push, megőrzés, archívum- és DB-restore
korlátját REPAIR-057 tényleges éles bizonyítéka feloldja. Az aktuális külső Git
független visszaklónozása/történetellenőrzése és az r15 teljes friss hostos,
ismételt és reboot utáni próbája még hátravan. Az új, elkülönített KVM-gép OS-e
elkészült: valódi systemd PID1, Docker29.1.5, Compose5.0.2, üres HC és image-tár.
HC-kulcsot/adatot még nem kapott, az OS-próba után leállt.

A konkrét, három teszttel ellenőrzött `scripts/router_release/prepare_audit_restore.py`
csak olvasó exportot készít a routerről/Gitből, és az operátornak külön privát
laborpéldányt ad. A védett age-kulcs miatt a felhasználó helyi sudo-futtatása
szükséges; az ügynök nem olvassa ki Dockerrel a védett hostkulcsot. Sikeres
előkészítési nyugta még nincs, a teljes VM-restore nem indult el.

Külön feltárt ellenőrzési hiány: az r15 cache az image ID-ket tartalmazza,
RepoTags nélkül; a HA Compose `stable` taget kér. A korábbi VM előre betöltött
HA-image-et használt. Az üres image-tárból történő offline HA-indítás ezért
külön vizsgálandó, jelenleg nem igazolt. A fagyasztott csomagok változatlanok.

[Tételes állapot és folytatás](docs/ai-ssd-backup-closure-20261101.md),
[OS-próba](docs/audit-evidence/ai-ssd-closure-20261101/os-ready.json).
Ez előkészítés és részleges korlátfeloldás, **nem teljes lezárás**. Más nyitott
auditpontot ez a munka nem változtat meg.

**REPAIR-058 folytatás — tényleges külső bemenet és feltárt restore-hibák:**
A felhasználó 19:45-kor sudo-val lefuttatta az előkészítőt. A router másolatának
teljes adatellenőrzése, a külső Git mirror és fsck sikeres. Commit:
`d612e6e3db13e3bc836bacf7338ef879d9c50532`. A kulcsexport tulajdonosellenőrzése
root futásnál tévesen elutasította az operátor 0600-as age-kulcsát. A javított
ellenőrzés root vagy a megnevezett operátor tulajdonát fogadja el; 6 célzott
teszt sikeres. Az ellenőrzött privát bemenet átadása újabb sudo nélkül befejeződött.

A független Git-vizsgálat 33 commitot és 1442 történeti blobot vizsgált; a
publikus exporter privátkulcs-/kitöltött JSON-hitelesítési mintáira 0 találat.
A fejben az ellenőrzött fájltartalmak hash-ei egyeznek, de a jegyzék 111 runtime
térképfájlt felsorol, amelyeket a Git ignore kihagyott. Ez nem adatvesztésnek
minősített routerhiba: a térképek a titkosított fájlmentésben vannak; a Git
nyilvántartási/exporthatárát javítani kell.

A valódi friss VM-próba a fájl-/DB-csere előtt megállt, mert a bootstrap a
Git gyökerének régi kiadási segédjét választotta. A javítás után előjött a HA
offline tag hiánya, majd a 077-es caller umask okozta nem olvasható SQL-forrás.
Az utóbbi megfelelő publikus forrásjogokkal a valós séma-/ACL-migrációt sikerre
engedte. A hibás körök nem kapnak sikeres minősítést. Új, tiszta OS-alap és
ellenőrzötten üres HC/image-tár készült a teljes javított próba megismétléséhez.

## REPAIR-059 — friss routeres hostrestore és Git-leltár javítása, r16 előkészítés (2026-11-01)

**Nincs élesítve; aktív marad az r15.** A REPAIR-058-ban feltárt konkrét hibák
javítása kész: a bootstrap fagyasztott kiadási segédet használ; a HA-image tagje
az ellenőrzött archívum és cache-ID alapján helyreáll, Docker29 metaadattal is;
HA-indítás `--pull never`; a Git-klónozás 022-es umaskot kap a 0700-as privát
work-rooton belül. A kulcsok és privát beállítások 0600-asak maradnak.

A publikus Git-export a runtime Xiaomi-térképcache-t kizárja; az továbbra is a
titkosított archívum/restic része. A validált exportot külön staging-lépés adja
a Gitnek, és a tényleges indexútvonalakat egyezteti a jegyzékkel. A távoli push
nem force push. A teljes valós helyi export és Git-index egyezett; privát auth
fájl nem került bele. A heti folyamat tesztje valódi Git-történetet és két
egymást követő commitot használ, az AI-t nem éri el.

Sikeres suite-ok: 16 tranzakció, 11 routeraktiválás, 21 recovery-asset/jogosultság,
27 restore/export szerződés, 29 hálózat nélküli routerteszt (3 opt-in kihagyva),
6 előkészítő és 1 valódi Git/age első+ismételt umask-teszt. Átfedő suite-ok,
nem összeadott tesztdarabszám. A cache ténylegesen betöltött; hat beépített modul
hash-e egyezik a csomag forrásával. A korai tesztkörnyezet `noexec`/capability és
régi fixture eltérései javítva; azok a futások nem sikeres bizonyítékok.

Az r16 a backend/frontend és a host mentő/bootstrap javításának új, külön
csomagja. A fagyasztott r15 kód és az eredeti audit változatlan. Az éles DB-t
ez a csomag nem tölti újra; az elkülönített VM saját DB-jét állítja vissza.
Az eredeti külső Git és a célzott javítások laborcommitja külön szerepel.
A teljes tiszta hostos, elérhetetlen FTP-s, ismételt és reboot utáni próba
folyamatban van; készre jelentés és élesítés még nem történt.

[Csomag és átállítás](backups/releases/hc-router-backup-20261101-r16/README.md),
[tételes bizonyítékhatár](docs/ai-ssd-backup-closure-20261101.md).
Az auditpontok darabszáma/besorolása változatlan; más nyitott feladat nincs lezárva.

**REPAIR-059 helyi átvétel lezárva, 21:00 körül:** a tiszta OS-ről és ugyanazon
work-dirből ismételt teljes bootstrap, az elérhetetlen FTP-s negatív kör és a
teljes vendégreboot sikeres. A hibátlan kör már automatikusan javította a modell
tényleges régebbi MQTT-mountjának tulajdonosát is. Ez az ötödik javítás; a csak
új PRIVATE könyvtárra alkalmazott permissions lépés önmagában nem volt elég.
Nem hivatkozott privát könyvtárhoz nem nyúl, és a normál élesítés ezt a cold
restore-lépést nem futtatja. A séma/asset/jogosultsági suite így 23 sikeres teszt.

7 139 946 mérés, 66 entitás és 61 HC-tábla visszaállt. Az 5 timernek van jövőbeli
triggere; a 14 alapunit és a kiadási adapterfájlok egyeznek ismétlés és reboot
után. Valódi UID10001 → root IPC → vendég-Docker leltár, tiltott forrás-/archívumírás,
read-only backend Docker-socket nélkül, és offline HA-image ellenőrzött. A negatív
FTP-kör nem módosította a kanonikus fájlokat/unitokat vagy a DB-konténert.
A kijelölt archívum egyezik az éles nyugtával; dump SHA-256:
`ccbf9799f8dfe6d13967be3fe1f9a20bbb50628efbf8cca814b20155218c8f47`.

Eredeti külső Git: `d612e6e3db13e3bc836bacf7338ef879d9c50532`; külön javítási
laborcommit: `014e1c2d663a746e9df6b632bc7d158d0584552a`. A funkcionális javítások
az r16 csomaggal a kiadásnév normalizálása után egyeznek. A friss tényleges r16
éles snapshotot ez nem előlegezi meg. A privát guest HC-lemez, a külön age-kulcs,
Git és repository másolata törölt; a HC-adat nélküli OS-alap maradt az utópróbához.

Az r16 711 forrásfájllal lezárt és élesítésre kész, a csomagpreflight sikeres.
12 aktiválási teszt igazolja többek között, hogy a külön laborbemenet hibája nem
vonja vissza a már ellenőrzött éles mentést. Az éles r15 readiness jó, 16 konténer
és a 706 fagyasztott forráshash változatlan, systemd failed-lista üres. Az eredeti
audit SHA-256 egyezik. **Az r16 nincs élesítve; ehhez a helyi sudo-futtatás kell.**
Az új éles mentés/Git/snapshot átvétele az aktiválás után következik.

[Teljes VM-nyugta](docs/audit-evidence/ai-ssd-closure-20261101/vm-acceptance.json),
[r16 előellenőrzés](backups/releases/hc-router-backup-20261101-r16/preactivation-check.json),
[helyreállítási útmutató](docs/router-disaster-restore.md).

## REPAIR-060 — éles r16 és az SSD miatti mentési korlátok lezárása (2026-11-01)

A felhasználó sudo-val sikeresen élesítette az r16-ot. Új heti futás:
`744b9d23cb54408698d80e50afd30585`; snapshot:
`354c6ca19a7cbbd2a4a30a8ead54a6011f2a93763384022533ec1d917b97db1f`;
külső Git: `5740329aeaa0a90c914185b816c702c069603d2d`.
Minden kötelező cél és a megőrzés sikeres; 5561 checksum és valódi izolált
PostgreSQL-restore ellenőrzött. Az éles utóellenőrzésben 711 kit/runtime hash
és a lezárt acceptance-evidence egyezik, a korábbi r15 és az eredeti audit
változatlan. Readiness jó; platform változatlan, systemd failed nincs.

A független Git-mirror vizsgálat 34 commitot, 1533 történeti blobot és 5345
manifestfájlt ellenőrzött. Hiányzó útvonal/hash-eltérés nincs, a 111 runtime
cache-fájl eltérése megszűnt. A meghatározott privátkulcs-/JSON-hitelesítési
mintákra nincs találat. A külső Git megmaradt, az AI letiltva maradt.

A tényleges éles r16 Git és snapshot változatlan kóddal, külön laborcommit
nélkül állt vissza az üres HC/image-tárú KVM-gépre. DB/MQTT, offline HA,
14 alapunit, kiadási adapterek, 5 timer, root IPC, non-root/read-only backend,
írástilalmak és no-replay sikeres. Az FTP-kiesés nem módosította a kanonikus
fájlokat/unitokat vagy DB-konténert. Reboot után az állapot és unitbájtok
ellenőrzése ismét sikeres. Az élesítés előtti kör az ismételt teljes restore-t
külön igazolta. A privát laborbemenet és HC-s vendéglemez törölve.

A jelenlegi mentési lánc SSD miatti ellenőrzési korlátai lezárva. HC-31 fizikai
shutdown/OFF/wake nem futott; csak későbbi AI-újraaktiválás előtt szükséges.
A régi AI-Gitea története nem kapott ellenőrzött minősítést. Auditbesorolás
változatlan: 40 ellenőrzött, 5 nyitott, 3 folyamatban; más feladatot nem zártunk le.

[Tételes lezárás](docs/ai-ssd-backup-closure-20261101.md),
[aktuális VM-nyugta](docs/audit-evidence/router-r16-live-20261101/vm-acceptance.json),
[éles átadás](backups/deployments/hc-router-backup-20261101-r16/DEPLOYMENT.md).

## REPAIR-061 — HC-23/43 r18 platformfrissítés és éles átvétel (2026-11-02)

**Állapot: éles és szoftveresen átvett r18.**
Az alábbi előkészítési feljegyzés a még r16-on futó állapotot rögzíti;
a tényleges éles átvétel eredménye a bejegyzés végén szerepel. HC-23/43 folyamatban marad;
az auditösszesítés és más pontok besorolása változatlan.

**Változás:** 14 fő platformszolgáltatás és a külön HA pontos image-ID-val,
megőrzött offline recovery-cache-sel. Támogatott HA 2026.10.4 és PgBouncer-alap,
elérhető stabil OS-frissítések, rögzített Node 24/Vite 6.4.5 frontend. A saját
Python-függőségverziók változatlanok. Konzisztens HA SQLite-backup és pontos
HA image-ID-t elfogadó, ellenőrzött full-hostrestore. Az AI letiltva marad;
az ESP MQTT legacy kivétel megmarad, Git/router backup és időzítés megőrzött.

**Bizonyíték:** 795 általános + 190 PostgreSQL + 2 tulajdonosi backendteszt,
19 külön éles-policy teszt, 54 bridge + 52 ingest + 33 X10 + 114 frontendteszt
és build, 16 telepítő + 12 router + 16 HA-tranzakció + 8 platform-tranzakció + 2 SQLite-backup teszt,
hibák és kihagyások nélkül. Valódi izolált PG/PgBouncer/hitelesített MQTT
indulás → rollback → dump-restore; hét alkalmazás függőségkiesési próbája.
A HA adatbázismásolat az új és régi image-en is megőrizte a sorokat, schema53.
Öt védett HA auth/config fájl teljes másolata az operátori próbából hiányzott;
az élesítő ezért teljes helyi root-előpróbát követel még szolgáltatásleállítás
előtt. A végleges 46 image-es offline csomag blob/réteg/készletellenőrzése és
Docker-load próbája sikeres. Nyilvános OS/npm buildanyagok megőrizve.
Külön régi → új → régi PostgreSQL image-próba azonos laboradatköteten,
megőrzött adatokkal. SQL-handover előtt a DB nem állhat le; rollbackkor előbb
az előző DB-ownernek kell működnie. A valódi telepítőútvonalat is teszteltük.
Az előzetes r17 aktiválási kapuja visszavonva, nem került élesbe; lezárt
forrása és bizonyítékai megmaradtak. Az átadott kiadás r18.

**HC-43 korlát:** teljes, friss PyPI/npm OSV-katalógus helyi összevetése és
15 image OS-vizsgálata. Saját hét Python-komponens 0 értékelhető találat,
frontend npm 0 találat/0 ismeretlen; elérhető disztribúciós javítás nem maradt.
A HA-ban 98 nyers advisory / 67 aliascsoport, a Python-értékelésben 122
ismeretlen rekord maradt. Debianban javítatlan találatok maradtak, köztük
3 kritikus azonosító; tételes upstream/útvonal-triage dokumentálva. Ez nem
sérülékenységmentességi tanúsítvány, HC-43 nem lezárt. Host kernel/frissítés,
fizikai hardver- és felhőpróbák nem részei az offline elfogadásnak.

**Éles kapuk:** r16 baseline és forráshash-ek, teljes védett HA-másolat offline
próbája; titkosított router-próba és teljes régi repository-ellenőrzés, friss
helyi mentés; naplózott átállítás és eredeti HA-adatállapotot visszaállító
rollback; live readiness, PostgreSQL16/kolláció, hitelesített HA API és a
korábban elérhető Growatt-entitások; friss HC/Git/router mentés, visszaolvasás,
SHA-256 és külön PG-restore. Csak sikeres bizonyítás után indulhatnak a timerek.

[Tételes átadás és visszagörgetés](docs/hc23-43-platform-release-20261102.md),
[csomag](backups/releases/hc-security-20261102-r18/README.md),
[helyi átadás](backups/deployments/hc-security-20261102-r18/PENDING.md).


**REPAIR-061 éles átvétel — 2026-11-02.** A felhasználó helyi sudo-val
sikeresen élesítette az r18-at. Teljes védett HA-konfiguráció és konzisztens
DB-másolat offline előpróbája sikeres, a sorok megmaradtak. Éles hitelesített
HA API HTTP200, 64 korábban elérhető Growatt-entitás megmaradt; PostgreSQL16,
kolláció 2.41/2.41. A heti futás `86b8ed71e4104b3a8eb909ae86e8ea91` completed/0;
6373 checksum, Git push, routeres visszaolvasás és külön PG-restore sikeres.
Snapshot `16cce464df928667d89eb16065c72eebd6c9e02a25867a0aff2037f7660488cb`,
Git `09c74d093a4276e8d5cb90b4fe454055b09010fb`.

Független, csak olvasó utóellenőrzés: 736 csomag-/runtime-forráshash és a
lezárt bizonyítékok egyeznek; 15 komponens a várt image-en, 10 healthcheck
healthy, restart0; backend live/ready/workers és frontend/proxy HTTP200 jó.
Mind az 5 hosttimer aktív/engedélyezett, hostops/MQTT guard aktív, systemd-hiba
nincs. Az AI letiltva, ESP-kivétel megmaradt. A lezárt csomagot és az eredeti
auditot nem módosítottuk. A teljes friss r18 vendéggépes restore/reboot és a
fizikai bridge-/X10-próba ebben a körben nem futott; a korábbi r16 VM-próba
nem újraminősített r18 bizonyíték. HC-23/43 folyamatban marad, az upstream
függőségi találatok és más pontok besorolása változatlan.

[Éles átadás és rollback](backups/deployments/hc-security-20261102-r18/DEPLOYMENT.md),
[utóellenőrzés](docs/audit-evidence/hc23-43-r18-live-20261102/production-check.json).

## REPAIR-062 — HC-15: mért DB-hozzáférés és app-wiring egyszerűsítése (2026-11-02)

- **Hatókör / fázis:** kizárólag HC-15, F0 és F8. Elolvasva HC-15, D.1
  hivatkozási bizonyítékai és F8 elfogadási/rollback feltételei. Az eredeti
  audit SHA-256 változatlan. Kiindulás az éles r18-cal egyező backendforrás;
  ellenőrzött r18 mentési nyugta rendelkezésre állt.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben; **nem élesített**.
  Aktív továbbra is `hc-security-20261102-r18`.
- **Bizonyíték / javítás:** az egyetlen shared repositoryt tartó
  `RepositoryRegistry` és a változtatás nélkül delegáló `SqlRepository`
  kivezetve; `DatabaseRuntime` közvetlenül a változatlan `DatabaseService`-t
  hívja. A használatlan registry-getter és a puszta forwardingteszt törölve.
  Requestenkénti helper-számlálás, nyers connection/context manager,
  kivétel-/rollback-határ és a szűkített `hc_app` role megmaradt.
- **App/domain:** a klímaütemezés SQL/profilvalidálása a meglévő ClimateService-be,
  a V2 öntözési session lookup a meglévő IrrigationService-be került. Az app
  1406 → 1339 sor; explicit, késleltetett wiring maradt. A korábbi HC-08
  scheduler-audit leválasztását megőriztük. Nincs új DI-framework vagy migráció.
  Az összes korábbi öntözési metódus AST-je változatlan; HC-20-at nem javítottuk.
- **Ellenőrzés:** kiinduló 795 unit; végső 806 unit és 197 PostgreSQL-teszt,
  utóbbi 15 külön eldobható klaszterben/modulban. **1003 egyedi végső teszt,
  0 failure/error/skip.** A külön 24 célzott/startup teszt átfedő, nem hozzáadott.
  Valódi rollback, close, savepoint, role-elutasítás; korábbi/új SQL-payload
  ugyanazon DB-tranzakcióban. Query-counter hibás/sikeres/párhuzamos requestnél
  azonos. Őrzött app-import és valódi lazy factoryk nem nyitnak kapcsolatot,
  nem indítanak szálat/folyamatot, nem írnak fájlt; 163 route változatlan.
- **Tesztkörnyezet:** hálózat nélküli konténerek, csak saját PG namespace,
  hostport és éles DB/eszköz nélkül. A staging a törölt modulokat is eltávolítja.
  Az első célzott kísérlet image-munkakönyvtár miatti téves importját külön
  naplóztuk; a végső futtatások explicit forrásimporttal sikeresek.
- **Függőségek:** meglévő HC-08 tranzakciós adapter, HC-07/38 sémaellenőrzés és
  HC-39 DB-role/SQL Lab határ megőrzött. HC-16 és HC-20 továbbra is külön
  feladat; más HC státusza/implementációja nem változott. Éles bevezetéshez
  új backendkiadás kell, a törölt modul tényleges kihagyásával.
- **Éles változatlanság:** a 736 telepített runtime-hash és mind a 16 konténer
  ID/image/állapota az r18 korábbi átvételével egyezik; deploy/restart és éles
  DB-lekérdezés nem történt. Rollbackhez a mentett eredeti fájlok megvannak;
  nincs DB-down-migráció vagy adattörlés.

[Tételes leírás](docs/hc-15-repair.md),
[összesítés és tényleges parancsok](docs/audit-evidence/hc15-20261102/summary.json),
[scope](docs/audit-evidence/hc15-20261102/scope-check.json),
[éles változatlanság](docs/audit-evidence/hc15-20261102/production-unchanged.json),
[patch](docs/audit-evidence/hc15-20261102/source.diff).


## REPAIR-063 — HC-16: egyirányú rover-protokoll és használatlan settings kivezetése (2026-11-02)

- **Hatókör / fázis:** kizárólag HC-16, F0/F8. Elolvasva a megállapítás,
  D.1 bizonyítékai/kivezetési feltételei, F8 teljes kapcsolódó suite-ra,
  viselkedésmegőrzésre és rollbackre vonatkozó feltételei, G.3–4 és az aktuális
  egykezelős átadás. Az eredeti audit SHA-256 változatlan. F0 alapja az r18
  visszaállítással ellenőrzött mentése és a mostani 806 tesztes baseline.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben; **nem élesített**.
  Aktív továbbra is `hc-security-20261102-r18`. A korábbi HC-15 javítás mind
  a 15 fájlujjlenyomata változatlan; más auditpont státusza nem módosult.
- **Javítás:** a 14 közös, tiszta rover-definíció a `mower_v3_protocol.py`
  levélmodulba került. A service/commands/manual/motor-test/parameters
  ötmodulos kölcsönös függősége megszűnt, a késleltetett importokat is számítva.
  A korábbi nyilvános importok aliasok, azonos hibatípusokkal/függvényekkel.
  Az áthelyezett definíciók és az öt üzleti modultörzs AST-je importokat
  leszámítva azonos; protokollkonstans, payload és időzítés változatlan.
- **Auth:** két használatlan operator-env settings-mező kivezetve, három
  érintett guide javítva. Az app fix superuser módja, a same-origin ellenőrzés,
  a natív Bearer/tokenfájl és a tesztelt opcionális session-adapter megmaradt.
  A teljes auth-modult D.1 alapján nem töröltük; privát env nem módosult.
- **Ellenőrzés:** végső 810 unit (249 roverhez kapcsolódó), 197 valódi
  PostgreSQL-teszt 15 külön eldobható klaszterben és 114 frontendteszt,
  továbbá offline frontend-build. **1121 végső teszt, 0 failure/error/skip.**
  A 4 célzott teszt átfedő: 120 importálási sorrend, alias-/exceptionazonosság,
  importgráf és őrzött tényleges app-wiring; 28 idegen/hiányzó originű POST
  elutasítva külső I/O előtt, natív teszttoken nem látható repr/API válaszban.
  Normál v3/MOTOR_TEST/HC_BRINGUP, lease/deadman/UNKNOWN és firmware/store
  szerződések ellenőrizve. Nincs fizikai roverpróba vagy éles DB/eszközkapcsolat.
- **Korábbi kísérletek:** a teszt téves parameter-URL-jét javítottuk; az első
  teljes kör 11 hibáját okozó hiányzó `re` importot visszaállítottuk. A végső
  backend/PG-körök már a javított forráson sikeresek. A sikertelen logok
  megőrzöttek és nem részei a sikeres elfogadásnak.
- **Függőségek / bevezetés:** a következő backendkiadás a megőrzött HC-15 és
  az új HC-16 forrásállapotát együtt tartalmazza; az új protokollmodult az öt
  importálóval/settings-szel együtt kell szállítani. HC-20 külön feladat,
  nem előfeltétel. HC-23/43 globális nyitott részei és HC-41 ESP kivétele
  nem változtak. Nincs DB-migráció, új parancs vagy új worker-szemantika.
- **Éles változatlanság / rollback:** 736 runtime-hash és 16 konténer
  ID/image/futás állapota változatlan. Deploy/restart nem történt. Az eredeti
  fájlok és patch alapján tiszta kód-revert lehetséges a HC-15 megőrzésével;
  adat-/DB-visszaállítás nem szükséges.

[Tételes leírás](docs/hc-16-repair.md),
[összesítés](docs/audit-evidence/hc16-20261102/summary.json),
[scope](docs/audit-evidence/hc16-20261102/scope-check.json),
[éles változatlanság](docs/audit-evidence/hc16-20261102/production-unchanged.json).


## REPAIR-064 — HC-20: elérhetetlen legacy öntözési végrehajtó kivezetése (2026-11-02)

- **Hatókör / fázis:** kizárólag HC-20, F0/F8. Elolvasva HC-20, D.1 bizonyítékai,
  F8 viselkedésmegőrzési/teszt-/rollback feltételei, F0 és G.5. Az eredeti audit
  SHA-256 változatlan. Az r18 visszaállítással ellenőrzött mentése rendelkezésre
  állt; a most lefagyasztott HC-15/16 állapot 810 baseline unit tesztje sikeres.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben; **nem élesített**.
  Aktív továbbra is `hc-security-20261102-r18`. Más auditpont státusza nem módosult.
- **Bizonyíték / javítás:** a három zárt legacy metódus (`start_scheduled_session`,
  `run_due_schedules`, `stop_due_schedules`) kivezetve, 185 definíciós sor törölve.
  Mind a 86 megmaradó service-metódus és a teljes modul AST-je a törléseket
  leszámítva változatlan. A 491 kezelt aktív forrás-/unit-/config fájlban nincs
  hivatkozás a régi nevekre; az öntözési domain-guide a tényleges V2 utat írja le.
- **Tesztigazítás:** az audit óta készült HC-04 legacy-indítási teszthivatkozások
  a megmaradó manual/V2 kapukat követik; a tranzakciós hiba-/versenytesztek
  megmaradtak. A régi legacy–V2 teszt helyett tényleges V2 service-hívás védi a
  napi egyszeri startot lezárt session és service-újrapéldányosítás után.
  Hat új unit és egy további PG-teszt fedi a navigator/pilot, skip/hibás start,
  kéziszelep-guard, stopnaplózás és valódi SQL-alapú effektív stop szerződését.
- **Ellenőrzés:** **816 unit + 198 PostgreSQL = 1014 egyedi végső backendteszt,
  0 failure/error/skip**. A PG 15 külön eldobható klaszteren/modulban futott.
  A külön 57 célzott teszt átfedő, nem hozzáadott. Tizenkét előtte/utána V2
  forgatókönyvben pontos reservation/MQTT payload/SQL/eredmény/recovery egyezés.
  Az app 163 route-ját ellenőrző és a HC-15/16 regressziós tesztek is sikeresek.
- **Megőrzött határok:** 62 SQL-migráció, történeti sessionök és publikus API-k
  változatlanok. HC-01–04/08, szezonprofil, stop-authority és egyworkeres
  tulajdonlás megmaradt. Nincs új eszközparancs, ütemezési szemantikaváltozás,
  runtime DDL vagy DB-migráció. Frontend és AI letiltás változatlan.
- **Függőségek / bevezetés:** a következő backendkiadás a korábbi HC-15/16 és
  HC-20 forrását együtt tartalmazza. A HC-15 service-fájlja csak a HC-20 három
  törlésével változott; a korábbi javítás működése megmaradt. HC-24/26 és
  HC-23/41/43 külön munka marad. Fizikai öntözési próba nem történt.
- **Éles változatlanság / rollback:** 736 runtime-hash és 16 konténer
  ID/image/futás állapota változatlan; deploy/restart és éles DB/eszközművelet
  nem történt. Az eredeti fájlok és patch alapján tiszta kód-revert lehetséges
  a HC-15/16 megtartásával, adat- vagy DB-visszaállítás nélkül.

[Tételes leírás](docs/hc-20-repair.md),
[összesítés](docs/audit-evidence/hc20-20261102/summary.json),
[scope](docs/audit-evidence/hc20-20261102/scope-check.json),
[payload-egyezés](docs/audit-evidence/hc20-20261102/payload-parity.json),
[éles változatlanság](docs/audit-evidence/hc20-20261102/production-unchanged.json).


## REPAIR-065 — HC-24: korlátos mDNS-pointer- és kérdésfeldolgozás (2026-11-02)

- **Hatókör / fázis:** kizárólag HC-24, F0/F1. Elolvasva a megállapítás,
  a H.1 pointerciklus-bizonyítéka, F0 és az érintett F1 lépés. Az export-/secret-
  kezelés HC-17/18 része nem módosult. Az eredeti audit SHA-256 változatlan;
  az r18 visszaállítással ellenőrzött mentése és a korábbi HC-20 alap rendelkezésre állt.
- **Státusz:** Ellenőrzött, izolált szoftveres környezetben; **nem élesített**.
  Aktív továbbra is `hc-security-20261102-r18`. Más auditpont státusza nem módosult.
- **Reprodukció / javítás:** az eredeti önhivatkozó és kétpointeres ciklus
  100 ms időkorlátba futott hálózat nélkül. A `read_name()` meglátogatott
  offseteket, pointer-/címkehatárt és kibontott névhosszt ellenőriz. A helyi
  pointerugrás-korlát 128; ez külön erőforráskorlát, nem RFC-hosszlimit.
  A `parse_questions()` a hibás/csonka kérdésszekciót teljesen eldobja, részleges
  válasz nélkül. A következő jó csomag feldolgozható marad.
- **Ellenőrzés:** **19 mDNS + 816 backend unit = 835 egyedi végső teszt,
  0 failure/error/skip**. Az mDNS-profil a tényleges mDNS-image Pythonjával,
  hálózat nélkül, tiltott valódi socketkonstruktorral futott. Ciklusok,
  csonka/határon túli név, érvényes tömörítés/folytatási offset, ugráskorlát,
  hibás későbbi kérdés és fake fogadóciklus ellenőrizve. 3000 véletlen bájtfixture
  és 200 generált név a 19 teszt része. Az egyszerű A/ANY válasz és announcement
  bájtpontosan egyezik az eredetivel. PG-/frontendteszt nem futott újra.
- **Tesztbekötés:** az új `mdns` profil és `infra/mdns` staging szükséges ahhoz,
  hogy a teszt a módosított parsert futtassa. A korábbi profilok viselkedése
  megmaradt; a változtatás nem zárja le a HC-23 globális kiadási feladatait.
- **Megőrzött határok:** kizárólag a két parserfüggvény és két korlátkonstans
  változott a responderben. Main/socket/válaszépítő/announcement AST változatlan;
  185 backend-Python-fájl és 62 SQL-migráció változatlan. HC-15/16/20 működése
  és korábbi bizonyítékai megmaradtak. Nincs új csomagfüggőség vagy szolgáltatáscsere.
- **Külön megfigyelés, nem javítva:** többkérdéses querynél a meglévő builder
  minden kérdés bájtját másolja, de QDCOUNT=1-et ír. Külön szintetikus bizonyíték
  készült; ez válaszformátum-felülvizsgálat, nem a pointerciklus-javítás előfeltétele.
- **Függőségek / bevezetés:** új mDNS-image és kontrollált mDNS-kiadás kell;
  runtime-szinten nem függ a még nem éles HC-15/16/20 backendjavításoktól.
  Közös platformkiadásban azok scope-ja külön feltüntetendő. HC-26 és a
  HC-23/41/43 nyitott részei változatlanok; AI letiltva marad.
- **Éles változatlanság / rollback:** 736 runtime-hash és 16 konténer
  ID/image/futás állapota változatlan; deploy/restart, DB/eszközművelet és
  LAN-csomagküldés nem történt. Az eredeti parser/harnessfájlok és patch alapján
  tiszta kód-revert lehetséges a korábbi javítások megtartásával; DB-/adatrestore nem kell.

[Tételes leírás](docs/hc-24-repair.md),
[összesítés](docs/audit-evidence/hc24-20261102/summary.json),
[scope](docs/audit-evidence/hc24-20261102/scope-check.json),
[külön megfigyelés](docs/audit-evidence/hc24-20261102/separate-observation.json),
[éles változatlanság](docs/audit-evidence/hc24-20261102/production-unchanged.json).


## REPAIR-066 — HC-26: mért HA Growatt-batch és külön HA-állapotkor (2026-11-02)

- **Hatókör / fázis:** kizárólag HC-26, F0/F10 és kapcsolódó F2 hibahatárok.
  Elolvasva a megállapítás és bizonyítékai, az F10 mért HA-batch feltétele.
  Az eredeti audit SHA-256 változatlan; r18 ellenőrzött mentés/restore és az
  aktuális forrás-/korábbi javítási bizonyítékok rendelkezésre álltak.
- **Státusz:** Ellenőrzött, izolált szoftveres és csak olvasó HA-ellenőrzéssel;
  **nem élesített**. Aktív `hc-security-20261102-r18`. Más auditpont státusza nem módosult.
- **Használati előfeltétel / mérés:** az opcionális `ha-growatt` poller valóban
  fut, 27 konfigurált entitással; a HA 86 állapotot ad. Három váltott sorrendű,
  csak GET-es körben a 27 egyedi kérés mediánja 29,755 ms / 11 976 bájt,
  az egy batch GET mediánja 2,524 ms / 38 037 bájt. A kis HA-példányon ez indokolja
  az egy lekérést és helyi szűrést; nem állít éles 60 s hibát vagy általános sebességgaranciát.
- **Javítás:** egy `GET /api/states` ciklusonként, utána a változatlan entity map
  szerinti szűrés. Hiányzó/ismeretlen állapot kimarad; teljes HTTP/JSON/body-hiba
  üres ciklust ad, nincs N kéréses fallback vagy régi snapshot-replay. Válasz és
  session lezárva. A ciklusvárakozás monoton órát használ; health-allowance egy
  kérésre számol, nem entitásszámra.
- **Payload:** eredeti metrikanevek, konverzió, topic/QoS/retain és négy metaadatmező
  megmaradt. `sample_time` a lekérés utáni UTC megfigyelés; additív `observed_at`
  és `ha_state_age_seconds` metrikánként. A HA `last_updated` megmaradt; kora nem
  bizonyít fizikai inverter-mintaidőt. Hibás/naiv/jövőbeli timestampnél kor=null.
  Nincs új stale-küszöb vagy automatikus értéktörlés. A meglévő JSON-meta ingest/SQL
  útvonal használható, migráció/ingestváltoztatás nélkül. A solar-guide frissítve.
- **Ellenőrzés:** **18 Growatt + 816 backend unit + 19 mDNS + 52 ingest = 905
  különböző végső teszt, 0 failure/error/skip**. A Growatt-profil a tényleges
  poller-image-ben, hálózat és valódi HA/MQTT nélkül futott. Hiányzó/ismeretlen,
  timeout/JSON/részleges body-hiba, következő körös recovery, forráskor, alias,
  monoton sleep, health/shutdown és ingest szerződés ellenőrizve. Négy külön
  régi main-loop AST-s összevetésben az eredeti MQTT mezők pontosan egyeznek.
- **Csak olvasó jelöltpróba:** a jelölt függvények külön folyamatban egy HA GET-ből
  26 használható metrikát építettek a 27 konfiguráltból, 26 kor-/timestampmezővel.
  Ez nem pollerátállítás és nem MQTT-küldés. Token/nyers állapot nem került ki,
  HA-módosítás vagy inverterparancs nem történt. Az első tesztkör datetime-mock
  hibáját a fixture-ben javítottuk; a hibás log megmaradt, nem elfogadási bizonyíték.
- **Korlát / függőségek:** a Requests connect/read timeout nem kemény teljes
  wall-clock ciklushatáridő. Ezt nem állítjuk kijavítottnak; a soros N-szorzó szűnt
  meg. Kemény transporthatáridő, fizikai forrásfrissességi szabály és frontend-
  korjelzés külön döntés; MQTT siker/readiness szemantika változatlan. Nincs új
  függőségfrissítés vagy más auditpont javítása. HC-23/41/43 folyamatban marad.
- **Élesítés / rollback:** új, önálló Growatt-poller image/kiadás kell; runtime-
  szinten nem függ a még nem éles HC-15/16/20 backend- és HC-24 mDNS-javításoktól.
  A 185 backend-Python-fájl, 62 migráció, dependency lock/Dockerfile és MQTT-/health
  segédek változatlanok. 736 runtime-hash és 16 konténer ID/image/futás egyezik;
  deploy/restart, DB-lekérdezés vagy éles MQTT publish nem történt. Az eredeti
  poller/harness/guide és patch visszatehető a korábbi javítások megtartásával;
  DB-/adatrestore nem kell. AI letiltva marad.

[Tételes leírás](docs/hc-26-repair.md),
[mérés](docs/audit-evidence/hc26-20261102/live-measurement.json),
[összesítés](docs/audit-evidence/hc26-20261102/summary.json),
[scope](docs/audit-evidence/hc26-20261102/scope-check.json),
[éles változatlanság](docs/audit-evidence/hc26-20261102/production-unchanged.json).

## REPAIR-067 — HC-23/43 lezárási felülvizsgálat és HA JSON Compose recovery-javítás (2026-11-02)

**Kérés és scope:** HC-23/43 lezárhatósága, HC-41 változatlanul hagyásával.
HC-23/43 bizonyítékai és az F0/F2/F10 lépés áttekintve; más auditpont javítása,
ESP-jelszóváltás, AI-indítás vagy éles telepítés nem történt.

**HC-23 státusz: Ellenőrzött kódjavítás, nem éles.** A friss és ismételt helyreállítás, az FTP-kiesési próba és a valódi guest-reboot sikeres; 14 system-scope unit, 5 timer, 12 hozzáférési unit/drop-in, DB-dump/checksum és root IPC ellenőrzött.

**HC-23 módosítás:** a letiltott AI-node három mozgó image-hivatkozása ellenőrzött
OCI-digestet kapott, a README és az új image-pins.json rögzíti az inaktív scope-ot.
Ez metadata-/Compose-ellenőrzés; a három image futtatása és hardverminősítése nem
történt meg. A valódi r18 Gitből és router-snapshotból induló friss KVM-restore
az előellenőrzésben HA JSON Compose-formátumhibát jelzett. A munkapéldány
restore_assets.py fájlja ezt kezeli, egyetlen explicit, offline cache-ben létező
HA-image követelményével és duplikált kulcs/több szolgáltatás/hibás image elutasításával.
Az eredeti r18 runtime és mentés változatlan. A külön labor-Git-jelölt kizárólag
az egy recovery-forrás javítását tartalmazza két megfelelő helyen.

**Ellenőrzés:** az összes tesztprofil és a frontend build sikeres. A recovery-javítás
után 818 backend unit teszt sikeres; a profilok összesen 1194 külön Python- és
114 frontendtesztet, azaz 1308 külön esetet fednek le, hiba és kihagyás nélkül.
A friss, megismételt, FTP-kiesési és rebootos restore-átvétel végső eredménye a
részletes dokumentum ellenőrzési záradékában és a bounded-lab bizonyítékaiban szerepel.

**Laborincidens:** az első javított jelölt próbájának eldobható lemeze megtöltötte
a rootpartíciót. A labor méretét nem korlátoztuk megfelelően. Kizárólag a védett
labor-VM leállítása és saját overlayének törlése helyreállította a tárhelyet.
Az utóellenőrzésben minden éles konténer-ID/image és 736 runtime-hash változatlan,
15 komponens fut, 10 healthcheck healthy, restart0, systemd failed unit nincs.
A korábbi 41 függő kódfingerprint és 215 bizonyítékfájl megőrzött. Az új labor
külön 18 GiB staging-lemezt, 40 GiB kemény root-VM-fájlkorlátot és automatikus
tárhelyőrt használ. A megszakított próbát nem számítjuk sikeresnek.

**HC-43:** az éles inventory ismételt teljes helyi Python-OSV ellenőrzése 98 rekordot,
67 aliascsoportot és 122 nem eldöntött rekordot adott; a hét saját Python-komponensben
nincs ismert verziótalálat. Az érintett HA képfeltöltési út ténylegesen használja a
Pillow-t. A SQL Lab éles forrással egyező tiszta validátora ártalmatlan XMLPARSE SELECT-et
elfogad; DB-kapcsolat/SQL-futtatás/exploit nem történt. A támogatott HA/Debian javítások
hiánya és a teljes maradványlista dokumentált. A felhasználó kifejezetten azt kérte:
**„Maradjon folyamatban a gyártói javításig.”** HC-43 ezért Folyamatban marad;
maradványkockázat-elfogadás és halasztott lezárás nem történt.

**Élesítés és függőség:** a recovery-forrás és az inaktív sablon javítása nem éles.
Új, hitelesített recovery-/kiadáscsomag kell; a lezárt r18 nem írható át helyben.
A még nem éles HC-15/16/20/24/26 javítások megőrzöttek, külön számon tartva.
HC-41 és az AI-tiltás változatlan.

[Részletes módosítás, gyártói kockázatok és ellenőrzési záradék](docs/hc23-43-closure-20261102.md),
[bizonyítékok](docs/audit-evidence/hc23-43-closure-20261102/).

## REPAIR-068 — az elkészült javítások r19 élesítésének előkészítése (2026-11-02)

A felhasználó engedélyezte az utolsó elkészült javítások élesítését és az audit
jelenlegi javítási körének lezárását. Az aktív csomag r18; a HC-15/16/20/23/24/26
kódjavítások új `hc-audit-20261102-r19` csomagba kerültek. Három image és a root
recovery/runtime változik, HA/PG/MQTT és a többi konténer megőrzött. Az 50 fájlos
review-listán kívüli munkakönyvtári drift nem kerül be, a friss host F6-javítása
megmarad. A három image pontos régi alapot és változatlan csomagkészletet használ.

1308 regressziós + 41 telepítő/aktiváló/utóellenőrzési eset és frontend build
sikeres; a baked kód/csomaglista, dependency nélküli processzstartup és a 19 image-es
offline Docker-load ellenőrzött. A három hiányzó teszt-fixture miatt nulla teszttel
leállt profilt külön sikeresen újrafuttattuk, a sikertelen történet megmaradt.
A hét meglévő health-route tesztet is megőriztük; a teljes 818 unit teszt újra sikeres.
Új pontos r19 bare-metal VM-próbát nem állítunk: az r18+recovery-javítás teljes
bizonyítéka változatlanul megőrzött. A friss éles Git/router és PG-restore a helyi
root-aktiválás kötelező kapuja.

**Élesítés eddig nem történt.** A host `sudo -n` jelszót kér; ez nem új engedélykérés,
hanem a helyi root-hitelesítés határa. A védett titkokat nem kerüljük meg Dockerrel.
A helyi parancs siker után automatikus runtime/timer/komponens-ellenőrzést és élő
auditzáró bejegyzést készít. HC-41 és HC-43 a korábbi döntés szerint folyamatban;
46 Ellenőrzött, 0 Nyitott, 0 Halasztva. Az AI tiltva marad.

[Átadási terv és indítóparancs](docs/audit-final-release-20261102.md),
[r19 csomag](backups/releases/hc-audit-20261102-r19/README.md).
