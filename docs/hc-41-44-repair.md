# HC-41/44 – MQTT-döntés és a backend hostjogainak szűkítése

**2026-10-30, újabb kiadási állapot:** a HC-41/44 célzott r10 csomag elkészült,
nincs élesítve. A hostjog-/hálózati/restore-adapter és image-függőségek előkészítve;
az ESP fix címének megerősítése és a felügyelt éles átadás hátravan.
[Kiadási csomag, ellenőrzések, korlátok](hc41-44-release-preparation.md).

**Aktualizálás, 2026-10-30:** a HC-41 általános jelszóhalasztását felváltotta a
fokozatos előkészítés HC-kliensekkel és ESP-kivétellel.
[Új aktuális terv és eredmények](hc41-staged-mqtt-auth.md). Az alábbiak a
2026-10-29-i javítás történeti állapotát rögzítik.

2026-10-29. **HC-44 helyben javítva és ellenőrizve, nincs élesítve. HC-41
nyitott: a felhasználó egyelőre nem kér MQTT-jelszót.** Aktív kiadás továbbra is
r9 ingest / r8 backend és frontend. A korábbi HC-35/36 helyi javítás megmaradt.

Elolvasva az eredeti audit HC-41/44 megállapítása, port-/UID-/mountbizonyítéka,
kapcsolódó M. vizsgálata és F1a/F1b lépése. Az eredeti audit nem módosult.
[Javítási napló](../AUDIT_REPAIR.md),
[gépi eredmények](audit-evidence/hc41-44-20261029/summary.json).

## HC-41: elhalasztott átállás

A felhasználó szerint van hitelesítést nem támogató MQTT-eszköz, majd kifejezetten
kérte: „sztem egyenlőre ne állítsunk be mqtt jelszót”. Nem generáltunk jelszót,
nem módosítottunk brokert, klienst, ACL-t vagy tűzfalat. A broker névtelen
hozzáférése és publikált 1883-as portja változatlan. A teljes HC-41 nem lezárt.
A Mosquitto [listener-/hozzáférési beállításai](https://mosquitto.org/man/mosquitto-conf-5.html)
alapján külön szükséges a klienshitelesítés és a topicjogosultságok megtervezése;
az IP-szűrés önmagában nem jelent ilyen védelmet.

A `scripts/plan_mqtt_access.py` csak olvasó tervkészítő, nincs alkalmazási módja.
Docker-portleltárból és megadott IP-kből felülvizsgálandó IPv4/IPv6
DOCKER-USER-szabályokat állít össze. Nem kész, idempotens tűzfaltelepítő.
A jelenlegi terv blokkolt: nincs jóváhagyott távoli kliens-/IP-leltár és teljes
hostcímleltár. A közelmúlt brokeres kliensazonosítói nem tekinthetők igazolt
eszközazonosságnak. Folytatáshoz eszköz/IP/portmódosítási képesség és
publish/subscribe/retained/LWT/STOP igények leltára kell; utána izolált pozitív és
negatív brokerpróba, majd felügyelt átállás. Ezeket most nem minősítettük sikeresnek.

## HC-44: helyi működési szerződés

A backend `10001:10001` felhasználóval, csak olvasható root fájlrendszerrel,
eldobott capabilitykkel és `no-new-privileges` mellett fut majd. A Docker-socket
kikerült a munkafabeli Compose-ból. A kód, archívumok, beállítások és restore
staging csak olvashatók. Négy cél marad írható: az elkülönített `backups/ai-control`,
a két meglévő közös lockfájl és a Rover JSON-adatokat tartalmazó `infra/private`.
A `/tmp` külön tmpfs. A Docker daemonhoz való hozzáférés
[hostszintű bizalmi határ](https://docs.docker.com/engine/security/);
a socket csak olvasható mountja ezt nem szűkíti olvasó API-ra.

Az új `host_operations_client.py` kizárólag Unix IPC-n kérhet meghatározott
státusz-, statisztika-, log-, restart-, mentés- és feladatállapot-műveletet.
Nincs közvetlen Docker HTTP-/CLI-fallback, általános exec vagy tetszőleges
konténerindítás. Az app mentési hívásai `HostBackupService` adapteren át mennek;
a normál API nem írhat archívumot, receiptet, forrást vagy mentési beállításfájlt.
A hívás teljes határideje és az üzenetméret korlátozott.

A `scripts/hostops/server.py` külön, megbízható hostszolgáltatás. A kliens
UID-jét `SO_PEERCRED` ellenőrzi; éles socketterv: root:10001, 0660. A végrehajtó
csak a meglévő 14 engedélyezett HC-konténernevet, a `homecontrol` projektet és
az aktuálisan feloldott konténerazonosítót fogadja el. Egy lecserélt célra nem
követi tovább a korábbi restartkérést. A hostparancsok argv-listák, shell nélkül,
teljes idő- és kimeneti korláttal. AI-offline mellett az AI restart tiltott.

A restart tartós feladatazonosítót és HTTP 202 választ ad; ez befogadás, nem
alkalmazáskészültség. Állapot: `GET /api/admin/host-jobs/<job_id>`.
A legfeljebb két restartworker és nyolc IPC-kiszolgáló szál korlátozott.
A host privát naplója az azonos kérés újrajátszását kivédi; eltérő tartalomhoz
nem használható ugyanaz az azonosító. Újrainduláskor a félbemaradt queued/running
feladat `uncertain`, automatikus ismétlés nélkül. A napló 1000 bejegyzés után
hostoldali karbantartást igényel; nem törli automatikusan a bizonyítékot.

A backup/restore a meglévő F6 sorát, checksumját, receiptjét, restore-journalját
és lockjait használja. Hostútvonal, credential és mentési cél nem írható át az
API-n. In-place restore csak hostoldalon ellenőrzött, completed receiptű,
egyező SHA-256 archívumból engedett; továbbra is érvényesek a korábbi cél- és
útvonalellenőrzések. A normál backend nem írhatja ezt a bemenetet.

A `ScopedAiPowerCoordinator` csak a közös AI-állapotot és rövid állapotlockot
helyezi az elkülönített írható könyvtárba. A két mentésvédelmi lock útvonala és
inode-ja megmarad. Az új F6 adapter, öt systemd drop-in és a kanonikus runnerhez
adott, fagyasztott kiadásra renderelendő launcher együtt biztosítja, hogy a CLI,
timer és API ugyanazt az állapotot lássa. A jelenlegi éles runnert és egységeket
nem írtuk át; ezek új sablonok és külön adapterek.

## Elvégzett ellenőrzés és korlátai

- **408 backend unit-/regressziós teszt**, 0 hiba, 0 kihagyás. Ebben 22 HC-44
  teszt: valódi Unix IPC, UID-tiltás, protokoll/határidő, cél-/parancs-/útvonalkorlát,
  idempotencia, megszakadt és lecserélt célú restart, API 202/job, F6 launcher és
  ellenőrzött szintetikus mentés/restore, közös mentéslock.
- A teljes munkafabeli Compose parserellenőrzése sikeres; a backendnek nincs
  Docker-socketje, a négy írható cél tételesen ellenőrizve.
- Az r8 pontos alapimage-ére, függőségfrissítés nélkül készült külön tesztimage
  UID10001. Elkülönített, csak olvasható, capability nélküli konténerben a forrás
  és archívum írása, általános Docker-parancs és idegen cél tiltott; a státusz,
  statisztika, log, szintetikus ellenőrzött hostrestore és F6-sorba állítás sikeres.
  Egy saját eldobható célkonténer tényleges restartját az indulásidő változása
  igazolta. A UID10002 kliens elutasítva. Minden laborkonténer eltávolítva.
- Az automatikus jóváhagyási ellenőrzés elutasította a Docker-socketet és binárist
  kapó laborkonténer tervét, mert ezzel hostszintű vezérlés kerülne a konténerbe.
  A megvalósult alternatívában egyik konténer sem kapott Docker-socketet:
  a host UID1000 tesztvezérlője csak saját célkonténert kezelt. A labor socketje
  0666 volt, az UID-vizsgálat aktív maradt. **A root tulajdonú 0660 socket és a
  valódi systemd-telepítés jogosultságai nem lettek igazolva**; a hoston nincs
  jelszómentes sudo, és ezt nem kerültük meg Dockerrel.
- A fizikai AI-gép, offsite célok, teljes VM/systemd restore és az új backend
  teljes éles indulása nem volt része ennek a próbának. A labor restore-hoz
  kizárólag a tesztfolyamatban engedélyeztünk szintetikus AI-policyt; az éles
  AI-offline policy változatlan. A 408 teszt nem helyettesít új PgBouncer- vagy
  fizikai eszközpróbát; a korábbi HC-35/36 PostgreSQL-tesztek külön bizonyítékok.
- Mind a **15 éles konténer** ID/image/indulás/restartszáma, **37 védett hostfájl**,
  a broker és bridge-források, r9 override, safety-forrás és az eredeti audit
  változatlan. Nincs éles eszközparancs, szolgáltatástelepítés vagy migráció.

## Bevezetési függőségek és visszaállás

Ez még nem önállóan élesíthető backendimage. A csak tervező
`scripts/hostops/installation_plan.py` rögzíti az összehangolt átadást:

1. Fagyasztott, felülvizsgált kiadás, friss ellenőrzött mentés, korábbi image-ek,
   unitok és eredeti ownership/módok mentése. A sablonok ExecStart/launcher útját
   az immutábilis kiadásra kell renderelni, nem a változó munkafára.
2. Régi backend és F6-fogyasztók leállítása, futó műveletek és közös lockok
   egyeztetése. Meglévő lock inode nem cserélhető. A régi AI-koordinációs állapot
   megőrzendő és ellenőrizve átadandó az új helyre; függő szándékot nem szabad
   üres állapottal elveszíteni vagy korábbi állapotból újraéleszteni.
3. Védett szülőkönyvtárak, tulajdonosok, új adatkönyvtárak, socket és négy írható
   bind cél ellenőrzése; symlink és API által írható védett szülő nem fogadható el.
   Új backend + hostszolgáltatás + öt F6 drop-in + kanonikus launcher együtt.
4. **HC-45-függőség:** a restore unitmanifestjét/telepítési láncát ki kell
   egészíteni az új hostszolgáltatással és drop-inekkel a bevezetés előtt.
   Ezt a külön auditpontot most nem javítottuk; a VM/systemd próba továbbra is
   hiányzik. A régi backend nem futhat párhuzamosan az új állapotot használóval.
5. Felügyelt root/systemd-jogosultságpróba, új backend indulás/DB-kapcsolat,
   engedélyezett és tiltott műveletek, státuszfrissülés, mentés és tél/AI-offline
   invariánsok. HC-31 fizikai AI-próba az SSD helyreállása után; az SSH-kulcs
   minimális UID10001-olvasási jogát külön ellenőrizni kell. A globális HC-23/43
   és más auditpontok változatlanok; sem csomagfrissítés, sem általános healthcheck
   refaktor nem történt. HC-41 elhalasztása nem akadályozza a HC-44 helyi javítását.

Rollback: először az új backend és végrehajtó leállítása, futó backup/restore és
`uncertain` feladatok egyeztetése. Ezután korábbi pontos image, adapter/kanonikus
runner, unitok és eredeti jogosultságok együtt állíthatók vissza. Az aktuális
AI-állapotot a régi helyével egyeztetni kell; régi generation/ON/leállítási szándék
nem másolható vissza vakon. Archívum, staging és feladatnapló megőrzendő,
félbemaradt művelet nem indítható automatikusan újra. A korábbi backendjogok
visszaállítása a HC-44 eredeti kitettségét is visszahozza.
