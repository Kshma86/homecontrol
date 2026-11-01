# HomeControl – aktuális éles kiadás

**Aktív: `hc-router-backup-20261101-r14`, élesítve 2026-11-01.**
A teljes helyi + titkosított routeres mentés, a külső Git-feltöltés, az archívum
visszaolvasása és az izolált PostgreSQL-visszaállítás sikeres. Backend ready,
AI továbbra is letiltott. **Routeres mentési incidens:** a 16:06–16:09 CET között
lefutott teljes check sok hiányzó packot jelez. A routeres tároló jelenleg nem
tekinthető megbízható mentésnek. A támogatott API-val a restic és a heti router/Git
ütemezés felfüggesztve; az időzítők ténylegesen inaktívak. A napi helyi mentés
02:15-kor továbbra is aktív, a Git-cél és a Git engedélyezése megmaradt.
Az éles, korlátozott párhuzamosságú teljes próba 2026-11-01 17:55–18:01 CET
között sikeres: 1408 pack teljes visszaolvasása, 4007 archívumfájl ellenőrzése
és izolált PostgreSQL-visszaállítás igazolt. Az eredeti kapcsolatkezelés ugyanebben
a próbában hibázott. **Az r15 javítás külön csomagban előkészítve, még nem éles:**
azonos, igazolt kapcsolatszám; teljes check a retention előtt és után; sikeres
új mentés/restore után az incidens miatt felfüggesztett ütemezés visszakapcsolása.
[r15 indítás és bizonyítékok](backups/releases/hc-router-backup-20261101-r15/README.md).
Az incidens során retention,
újrainicializálás vagy repositoryjavítás nem történt a hibás check után.
[Incidens és következő lépés](docs/router-ftp-backup-incident-20261101.md).
[r14 éles állapot, nyitott teendő és rollback](backups/deployments/hc-router-backup-20261101-r14/DEPLOYMENT.md).

A következő bekezdés az előző r13 kiadás feljegyzése.

**Korábbi aktív kiadás: `hc-f10-20261031-r13`.**
Az r12 HC-12/32 és HC-23/43 részjavításai, valamint az X10 indulási online-jelzés
korrekciója éles. Nyolc alkalmazás a várt image-en healthy, restart0; DB/MQTT
és minden backend health/worker/readiness sikeres. X10 online=1 és friss
telemetriát küld, tölt. Az r13 csak X10+backend újraindítás volt, a másik
14 konténer ID/image változatlan. 690 telepített forráshash egyezik.
Öntözés winter, védelmi API idle, a védelem enabled=true, AI SSD-korlátozás megmaradt.
[Éles r13 átvétel és rollback](backups/deployments/hc-f10-20261031-r13/DEPLOYMENT.md).
Az első r13 helyi mentés sikeres, 3239 checksum ellenőrizve; fizikai
eszköz-/élőtérképpróba még felügyelt feladat.

A következő feljegyzések korábbi kiadási állapotokat őriznek.

**Aktív: `hc-f10-20261031-r12`, élesítve és szoftveresen ellenőrizve.**
Nyolc pinned alkalmazásimage healthy, restart0; DB/MQTT és worker-readiness jó,
platformkonténer-ID-k változatlanok, frontend HTTP200. Telepített 690 forráshash
rendben. Öntözés winter profil, AI SSD-korlátozás megmaradt. Első éles r12 helyi
mentés completed, 2494 fájl ellenőrzött checksumával.

**Utóellenőrzési javítás előkészítve: r13.** X10 friss adatot küldött, de a régi
retained offline jelzés cache-elődött. A valós online jelzést egyszer helyreállítottuk;
a tartós callback-javítás külön új image, változatlan függőségekkel. Három baked
regresszió, 16 telepítőteszt és 25 image-es offline load sikeres. X10+backend
újraindítás szükséges, a többi szolgáltatás futva marad; helyi sudo-ra vár.
[Éles r12 ellenőrzés](backups/deployments/hc-f10-20261031-r12/DEPLOYMENT.md),
[r13 javítás átadása](backups/deployments/hc-f10-20261031-r13/PENDING.md).

## Korábbi előkészítési és incidensfeljegyzések

**r10 HELYREÁLLÍTVA, élőben ellenőrizve.** A felhasználó helyreállítója
`success: true` eredményt adott. 15 elvárt konténer fut, minden image r10;
DB/MQTT rendben, X10 online és tölt, öntözési/védelmi API jó, hostops és a korábban
aktív időzítők működnek. Az alábbi leállási feljegyzés történeti incidens.
A javított kiadás külön **r12** csomag; 16 telepítőteszt sikeres, helyi sudo-ra vár.
[Friss telepítési állapot](backups/deployments/hc-f10-20261031-r12/PENDING.md).


**INCIDENS – r11 aktiválás megszakadt, alkalmazások állnak.** A Xiaomi-próba
sikeres volt (6062 bájt, új certifi), de a telepítő tévesen a `common.locked`
függvényt hívta az `install.locked` helyett. Ez a rollbacket is megállította.
Az adatbázis/MQTT/Zigbee/HA/proxy fut; az érintett nyolc alkalmazás és hostops áll.
Az r11 runtime/privát könyvtár még nem települt, a Compose/marker továbbra is r10.
A javított, szűk helyreállító és a 14 teszt kész; a tényleges visszaállítás
helyi sudo-jelszóra vár. **Az activate/deploy parancsot most ne ismételd meg.**

```bash
cd /srv/docker/homecontrol/backups/releases/hc-f10-20261031-r11
sudo python3 source/scripts/f10_release/recover.py
```

Ez csak a snapshot szerinti r10-et állítja helyre, megőrzi az adatokat,
a zárolások alatt egyezteti a függő ventilátor-ON szándékot, majd health/hostops
ellenőrzés után visszaindítja a korábban aktív időzítőket. Új r11 váltás nincs.
A root-védett hibanaplót a helyreállító maga ellenőrzi: csak a diagnosztizált
AttributeError és változatlan r10 kép/konfiguráció mellett fut.


**Engedélyezett r11 élesítés előkészítve, 2026-10-31; NINCS ÉLESÍTVE.**
HC-12/32 és HC-23/43 helyi részjavítás: nyolc alkalmazásra korlátozott, pinned
kiadás, mentéssel és automatikus/kézi rollbackkel. 591 célzott alkalmazásteszt,
15 brokeres eset és 7 dependency nélküli processzpróba mellett most 10 telepítőteszt,
valódi DB/pool/auth-MQTT startup/rollback/restore és a 24 image-es offline archívum
Docker-betöltése is sikeres. Előzetes helyi mentés: 1737 ellenőrzött fájl.
A teljes backend-discovery nem zöld; globális HC-23/43 és HA/OS/AI külön marad.

**Még szükséges:** helyi sudo. A Xiaomi-munkamenetes próbát a felhasználó
jóváhagyta, de az első kísérlet a root:root 0600 fájl olvasásánál, hitelesítés
előtt megállt. A jogosultságokat nem változtattuk meg. Az előkészített
`sudo python3 source/scripts/f10_release/activate.py` előbb védett ideiglenes
másolatból próbálja a felhőt, majd kizárólag siker esetén engedi és futtatja
az éles váltást. 12 telepítőteszt sikeres. A ready flag addig false.
[Állapot és parancs](backups/deployments/hc-f10-20261031-r11/PENDING.md),
[telepítés és rollback](backups/releases/hc-f10-20261031-r11/README.md).

**Aktív: `hc-access-20261030-r10`, élesítve 2026-10-31 15:12–15:13 CET.**
HC-35/36 + HC-41/44 közös runtime, a szükséges mentési/restore-integrációval.
13 szolgáltatás cserélődött, pinned image-ek, DB/MQTT/hostops rendben;
11 binding változatlan és valid. ESP/Nano friss, téli profil és AI-tiltás megmaradt.
Élesítés előtti és utáni helyi mentés kész (975 és 1678 ellenőrzött checksum).
**X10 utókövetés:** új felhőbelépés után HTTP200, három mentett térkép frissült;
aktív takarítás közbeni élőtérkép-próba még kell. A működő belépőkód megőrizve,
a későbbi webes beépítés [feljegyezve](docs/x10-cloud-web-integration.md).
PC Explorer/dashboard reconnect és fizikai STOP/ventilátor próba még nincs elvégezve.
HC-41 az ESP legacy kivétel miatt folyamatban marad. A rootjog-blokkot a felhasználó
terminálos telepítése feloldotta; a régi deploy/váltó parancsokat ne futtassuk újra.
[Aktuális átadás, bizonyíték és rollback](backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md).

## Korábbi dátumozott előkészítések és kiadások – történeti feljegyzések

**Élesítési utasítás érkezett, 2026-10-31; rootjogra vár, NINCS ÉLESÍTVE.**
A csomag- és éles előállapot ellenőrzése sikeres; friss helyi teljes mentés kész,
a root worker szerint 975 checksum rendben. A host `sudo` jelszót kér, ezért
a systemd/nft átállás nem indult el; az r9 ingest és r8 backend/frontend fut.
[Pontos folytatás és mentés](backups/deployments/hc-access-20261030-r10/PENDING.md).

**Aktuális előkészítés, 2026-10-31: közös HC-35/36 + HC-41/44 r10, NINCS ÉLESÍTVE.**
A `hc-access-20261030-r10` csomag közös backend/frontend revíziója elkészült.
Az ESP 192.168.1.179 címét és a routeres DHCP-foglalást a felhasználó megerősítette;
a policy és az újratitkosított bundle véglegesítve. Hét kiadási image, 21 image-es
ellenőrzött offline csomag; nincs DB-migráció vagy függőségfrissítés.
441 backend- és 113 frontendteszt/build, 19 valódi PostgreSQL/PgBouncer teszt,
5 átadási/restore-forgatókönyv és 54 célzott restore-/unitteszt sikeres (átfedő suite-ok).
A telepítés, rollback és full restore az alkalmazás indulása előtt naplózottan
visszavonja a korábbi függő klímaventilátor-ON-okat; binding/policy és más munka megmarad.
A 2026-10-30-i teljes KVM-bizonyíték az előző, HC-35/36 nélküli jelölthöz tartozik;
a közös revízió teljes VM-bootstrap/reboot és r9→r10→r9 cutover-próbája nem ismétlődött.
A mai új restore-lépés és az alkalmazásállapot valós DB/Docker-laborban ellenőrzött.
A következő lépés külön utasításra a felügyelt élesítés, friss mentés/baseline és
root hostjog mellett, majd fizikai és PC-klienspróba. Továbbra is 13 szolgáltatás
érintett, köztük a DB; rövid DB/API-kieséssel számolni kell. Az aktív kiadás változatlan.
[Közös revízió és bizonyítékok](docs/hc3536-access-combined-20261031.md),
[átadási/rollback eljárás](docs/hc41-44-release-preparation.md).
Az alábbi korábbi dátumozott előkészítések történeti állapotot rögzítenek.

**Aktív: `hc-ingest-20261028-r9`, élesítve 2026-10-28 22:13:26 CET.**
HC-11/33/34 aktiválva, a 062-es additív migráció alkalmazva. Kizárólag az ingest
cserélődött; a backend/frontend az r8-on, a többi nyolc konténer változatlanul fut.
Az új ingest healthy/ready, új mérés mentése igazolt. Kezelői konfiguráció,
safety ACK/latch, AI-offline és téli profil megmaradt. Friss ellenőrzött helyi
mentés és az előző pontos ingest image offline másolata is rendelkezésre áll.
[Aktuális éles átadás és ingest-only visszaállítás](backups/deployments/hc-ingest-20261028-r9/DEPLOYMENT.md).

A kész image-en 52 unit-/regressziós + 15 PostgreSQL/MQTT + 14 átadási teszt
sikeres; r9→r4→r9 PgBouncer-próba és 6,84 milliós migrációpróba is történt.
A HC-23 ingest-liveness/readiness és image-rögzítési része aktiválva; a globális
HC-23 és HC-43 nyitott marad, csomagfrissítés nincs. A fagyasztott kiadási
csomag előkészítési feljegyzése történeti, az aktuális állapotot a deployment rögzíti.
Az r8 backend/frontend korábbi átadása: [r8](backups/deployments/hc-read-models-20261028-r8/DEPLOYMENT.md).

**Helyi következő javítás, 2026-10-29:** HC-35/36 ellenőrizve, nincs élesítve.
Érvénytelen explicit binding nem válthat fallback eszközre; a ventilátor
binding/policy/késleltetés közös koordinációt használ. 386 backend-, 19 valódi
PostgreSQL- és 4 frontendteszt, valamint a frontend build sikeres. Backend,
új koordinátor-modul és frontend együtt adandó át; új migráció nincs.
Külön kiadás és a függő ventilátorszándékok egyeztetése szükséges, a régi
backend leállításával. [Javítás, függőségek és rollback](docs/hc-35-36-repair.md).

**További helyi javítás, 2026-10-29:** HC-44 ellenőrizve, nincs élesítve.
Nem root, csak olvasható backend, közvetlen Docker-socket nélkül; külön,
engedélylistás hostvégrehajtó kezeli a diagnosztikát/backupot/restore-t/restartot.
408 backendteszt és elkülönített UID-/írási-/restartpróba sikeres. Ez még nem
önállóan élesíthető backendimage: a hostszolgáltatás, öt F6 drop-in, kanonikus
runner-adapter, jogosultságok és AI-állapotátadás összehangolt telepítése kell.
A HC-45 restore-manifestet ehhez ki kell egészíteni; a valódi root/systemd-
jogosultságpróba még hátravan. **HC-41 nyitott**, a felhasználó kérésére
MQTT-jelszót nem állítunk be; broker- és tűzfalmódosítás nem történt.
[Javítás, ellenőrzési korlátok és bevezetési függőségek](docs/hc-41-44-repair.md).

**MQTT-előkészítés, 2026-10-30:** HC-41 folyamatban, nincs élesítve.
A HC Python-kliensek, Zigbee2MQTT, post-boot probe és a jóváhagyott külön
fejlesztői dashboard hozzáférése előkészítve. Jelszavas belső/loopback 1884,
ideiglenes ESP-only legacy 1883, csak saját öntözési topicokkal. A megadott
192.168.1.179 cím aktív MQTT-forrás, az ESP-azonosság/fix DHCP még igazolandó.
Hálózati szűrés, broker-jogosultságok, privát titokmentés, dashboard SSH-alagút,
kiadási image-ek és felügyelt átadás szükséges. A teljes munkafát nem szabad
közvetlenül élesíteni a benne lévő más, még helyi javítások miatt.
[Részletes fokozatos átállítás](docs/hc41-staged-mqtt-auth.md).

Az alábbi korábbi átadások időrendben megőrzött feljegyzések.


**Korábbi r4 átadás — történeti feljegyzés:** `hc-opening-events-20261027-r4`, 2026-10-27 17:04 CET.

A backend célzott javítása az eseményvezérelt nyitásérzékelőket kezeli:
a legutóbbi érvényes, élő nyitásjelzés igazolt rádiós jelenlét mellett
öt perc után is légutánpótlásnak számít. Zárás, offline/ismeretlen rádió,
hibás vagy retained esemény nem igazol nyitást. A kontakt eseményidőbélyegét
nem frissítjük mesterségesen. A fogyasztás 300 s-os és a parancsvisszajelzés
60 s-os korhatára megmaradt.

A backend az r2 rögzített image-jére épül, egyetlen szolgáltatásfájl célzott
módosításával. Az r3 ingest és a konnektor 60 s-os reportingja megmaradt;
a frontend, ingest, DB és broker nem indult újra. A kezelői konfiguráció,
a nyitás-/CO-/füstesemények és a riasztásretesz megmaradtak. Nincs új migráció
vagy automatikus ACK. A munkafa további refaktorjai nem kerültek az image-be.

[Részletes kiadás és bizonyíték](backups/releases/hc-opening-events-20261027-r4/DEPLOYMENT.md).
[Előző r3 ingest-/reportingjavítás](backups/releases/hc-combustion-feedback-20261025-r3/DEPLOYMENT.md).
[CO-/füstérzékelők szerződése és a kontaktok kiegészítése](docs/hc06-sleeping-sensors.md).

## Visszaállás

Csak a backend visszaállítása az előző r2 image-re; az r3 ingest megmarad:

```bash
python3 /srv/docker/homecontrol/backups/releases/hc-opening-events-20261027-r4/scripts/switch_mode.py rollback --apply
```

Vissza az r4-re ugyanitt `release --apply`. `--apply` nélkül csak olvasó
előellenőrzés és terv. A script rögzített image-et indít,
`--no-deps --no-build --pull never` mellett; kizárólag a backendet cseréli.
Ellenőrzi a konfiguráció megmaradását és a worker állapotát, majd az aktív
Compose symlinket állítja át. Visszaálláskor a nyitásjelzés ötperces
lejárata és a téves sárga jelzés is visszatérhet.

Az aktív `infra/docker-compose.override.yml` az r4 override-jára mutat.
A kiadás az r2 privát környezetére/fagyasztott Compose-ára és az r3 ingestjére
is támaszkodik; mindhárom kiadáskönyvtárat meg kell őrizni. A régi váltóscriptek
nem ismerik az újabb kiadásokat. A munkafából általános build helyett a
rögzített kiadási eljárást kell használni.

## Folytatható helyi refaktor

A [HC-07](docs/hc07-schema-migrations.md), [HC-38](docs/hc38-database-baseline.md)
és [HC-39](docs/hc39-database-roles.md) a munkafában ellenőrzött, nincs élesítve.
A HC-39 további 061 migrációt, külön app/reader hitelesítést és összehangolt
PgBouncer/backend/ingest kiadást igényel; az alap Compose már ezt várja. HC-07 bevezetéséhez explicit
059/060 migráció és külön kiadás kell; a HC-38 baseline csak új üres DB-re
való. Ezeket nem szabad az aktuális éles kiadásba keverni. A munkafából
általános `up --build` helyett a fagyasztott kiadási folyamatot használd.


## Helyi F6 mentésrefaktor — nincs élesítve

A [HC-19/25/30/42 javítása](docs/hc-f6-backups.md) közös host végrehajtót,
receiptalapú leltárt és 202-es webes kérést ad. **Az eredeti host scriptek,
telepített unitok és a még aktív root/user timerek változatlanok**; nem történt
rejtett bevezetés a közvetlen script-/watcher-hivatkozásokon keresztül.
Az új források `backup_runner.py`, a belső `backup_*_worker.sh` fájlok és
`scripts/systemd/f6/`; a `install_backup_f6.py` alapértelmezésben csak tervet ad.

A következő kiadásba a backend/frontend és az explicit host unit-átadás együtt
készítendő elő, a két redundáns felhasználói timer tiltásával. A telepítő kezeli
az előállapotot és sikertelen átmenetnél visszaállítja a korábbi unitokat;
most csak izolált fake-manager próbában futott. F1-ből a HC-17/18 exporthatár
az éles Git-publikáció előtt továbbra is szükséges. HC-31 és a restoreaudit
pontjai változatlanul nyitottak. A HC-07/38/39 bevezetése külön migrációs és
role/DSN lépésekkel, fagyasztott kiadási és rollback-próbával történhet.

## Helyi HC-31 AI-leállítási koordináció — nincs élesítve

A [HC-31/F6b javítása](docs/hc31-ai-power-coordination.md) generációhoz és
rögzített aljzatidentitáshoz köti a kikapcsolási szándékot, közös koordinációval
védi az SSH-leállítást és az OFF-publikálást a mentésindítással szemben.
Wake, új F6 feladat, AI-bindingcsere és backendújraindítás törli a korábbi szándékot.
A lockot birtokló weekly/check callback csak sorba állít, köztes kézi wake után
a régi futás nem kérhet automatikus leállítást. A UI ugyanazt az aktuális szándékot mutatja.

Backend/host runner/workerek/UI együtt adandók át, közös backupmounttal.
Az éles r3 ingest, r2 backend/frontend és a legacy host scriptek változatlanok.
585 backendteszt sikeresen futott, 116 PG opt-in kihagyott; 98 frontendteszt és
build sikeres. Fizikai shutdown/wake és teljes kiadási rollback-próba nem történt.
HC-17/18, F6a és a korábbi migrációs/role/DSN feltételek megmaradnak.
Átadás/rollback előtt a korábbi alvó worker processzét is le kell állítani;
az új koordinációs fájl nem tud egy régi image-ben élő threadet visszavonni.


## 2026-10-26 — F1/F6a és inaktív r4 csomag

**Az éles rendszer továbbra is r2 backend/frontend + r3 ingest. Most nem történt élesítés.**

A HC-17/18/27/28/29/37/46/47 helyileg javított és ellenőrzött. A HC-45 kódja kész,
de valódi üres VM/systemd és offline age-kulcs ellenőrzés még kell; a HC-31
felügyelt fizikai próbája is külön függőség. HC-24/41/44 nem lett automatikusan
javítva. Részletes működés és korlátok: [F1/F6a](docs/hc-f1-f6a-repair.md),
[nyilvántartás](AUDIT_REPAIR.md).

Előkészített csomag: [hc-refactor-20261026-r4](backups/releases/hc-refactor-20261026-r4/DEPLOYMENT.md).
Külön image-ek, privát app/reader környezet, új age-bundle, release/rollback
Compose-terv, image ID és SHA-leltár. A 731-es teljes backendkör, 98 frontendteszt
és build, a valódi backup/DB/age/restic próbák, valamint az izolált
release → korlátozott rollback → release sikeresek. A hostmanifest próbája
fixture-managerrel futott; ez nem a hiányzó valódi VM/systemd ellenőrzés.

Csak olvasó csomagellenőrzés:

```bash
python3 /srv/docker/homecontrol/scripts/check_audit_release.py
```

A rollback külön kompatibilitási image, megtartott additív DB-sémával és F6 lockkal;
SQL Lab, webes backup-módosítás és AI power-kérés ideiglenesen 503. Az r3 ingest
feedbackje megmarad. A régi r2/r3 váltóscriptek nem kezelik ezt az új csomagot.
Feltétel nélküli „csak élesíteni kell” minősítés még nincs; a két felügyelt
ellenőrzési határt előbb rendezni kell. Az aktív Compose symlinket nem módosítottuk.

## 2026-10-26 — tényleges kulcsellenőrzés és részleges hardverpróba

A valódi r4 age-bundle visszafejtése a meglévő helyi identityvel sikeres:
12/12 titkos fájl egyezik, 0600 móddal, törölt tmpfs-staginggel. Külső offline
kulcspéldány és valódi VM/systemd full restore továbbra sem igazolt; az eldobható
VM elérését bekértük.

A candidate HC-31 wake törölte a függő OFF-ot, az AI-aljzat bekapcsolását
nem retained telemetria igazolta. A gép azonban a konfigurált 192.168.1.2 címen
180 másodperc alatt sem jelentkezett SSH-n; a második WOL után is elérhetetlen.
Shutdown/OFF nem történt, **az AI-aljzat ON állapotban maradt**. A próba lezárult,
a mentési lockok szabadok. A gép helyi állapotának/IP-jének tisztázása szükséges
a teljes fizikai ciklushoz. Részletek: [REPAIR-025](AUDIT_REPAIR.md).

Az éles konténerek és r3 override változatlanok, DB/MQTT health rendben,
az r4 csomagellenőrzés sikeres. Élesítés nem történt; a két kapu továbbra is nyitott.

## 2026-10-26 — AI-hardverpróba elhalasztása

A felhasználó az AI-szerver SSD-problémája miatt kérte az AI-szerver kihagyását
a további próbákból. **HC-31 fizikai ellenőrzése elhalasztva, nem lezárt**;
működő hardver és SSH-elérés után folytatható. Új AI-kapcsolási vagy ébresztési
művelet nem történt. A korábbi próba végén az aljzat ON maradt.

A felhasználó megerősítette, hogy nincs eldobható VM, ezért a HC-45 valódi
VM/systemd hostrestore-próbája is hátravan. A két hiányzó bizonyíték nyitva marad;
ez a döntés önmagában nem engedélyez élesítést. Részletek: [REPAIR-025](AUDIT_REPAIR.md).

## 2026-10-27 — külön korlátozott r6 csomag

Előkészítve: `backups/releases/hc-refactor-ai-offline-20261027-r6/`.
Kötelező AI-offline profil, védett backend és Tuya-fogyasztó, letiltott távoli
mentési módok/timerek, megtartott helyi mentés és staging restore. Az éles webes
fájlrestore/recovery is tiltott. Az eredeti r4 csomag és az éles opening-events backend/r2 frontend/r3 ingest
megmarad; élesítés nem történt.

756 teljes backendteszt, 19 végleges célzott profilteszt, 98 frontendteszt és build;
valódi izolált release/rollback/release és broker/poller-fogyasztói próba sikeres.
A profilt a rollback is megtartja. A teljes üres VM-es restore és a fizikai
AI-próba külön nyitott, nem minősítjük át őket teljesítettnek.

Olvasási ellenőrzés: `python3 scripts/check_restricted_release.py`.
Éles hostot olvasó preflight: `python3 scripts/preflight_restricted_release.py`.
Az előkészítés nem helyettesíti a friss helyi pre-cutover mentést és a privilegizált,
összehangolt átadást. Részletes hatókör és sorrend:
[docs/hc-ai-offline-release.md](docs/hc-ai-offline-release.md), REPAIR-026.

A végleges r6 a már éles nyitásérzékelős safety-javítást is megőrzi, rollbackben is. A korábbi inaktív r5 előkészítés leváltott, nem telepítendő (`SUPERSEDED.json`).

## 2026-10-27 — korlátozott r6 élesítve

A felhasználó külön engedélye után az r6 a meglévő HC hoston `ai-offline`
profilban éles. Friss privát előállapotmentés és a friss dump valódi, izolált
owner/ACL-megőrző visszatöltése sikeres (6 832 809 mérés). Explicit 059/060/061,
hc_app/hc_lab, védett Tuya és F6 rendszeridőzítők átadva; user duplikációk
kivezetve. DB/MQTT/UI/ingest/reader és operator/safety megőrzés ellenőrizve.
Valódi webes helyi mentés sikeres, minden belső checksum rendben. Az aktív
override az r6 release-re mutat. AI és távoli mentés tiltott; HC-31 fizikai és
HC-45 teljes VM-es hostrestore-próba külön nyitott marad.

A fagyasztott csomag történeti előkészítési leírása változatlan; az aktuális
éles állapot és a kompatibilis rollback eljárás:
[átadási napló](backups/deployments/hc-ai-offline-20261027-r6/DEPLOYMENT.md),
AUDIT_REPAIR.md REPAIR-027. A régi korlátozás nélküli switch helper nem használható.

## 2026-10-27 — HC-08 helyileg ellenőrzött, nincs élesítve

Atomi scheduler run→event→plan→execution, történeti hiányok küldés nélküli
recoveryje és külön, commitolt claimhez kötött klímás dispatch készült.
282 kapcsolódó regresszió hiba/kihagyás nélkül, valódi auditmásolat recoveryje
sikeres. A már éles r6, a 37 aktív hostfájl és az eredeti audit változatlan.
Új image, migráció vagy aktív override-váltás ebben a munkában nincs.

HC-09/F3 és HC-35/36 külön nyitott; az éles leltárban talált régi physical_manual
session nem lett módosítva. Következő bevezetéshez saját csomag/rollback, friss
lánc- és nyitottművelet-leltár, a régi scheduler leállítása és az uncertain/pending
állapotok egyeztetése kell. A r6 helper nem általános jövőbeli rollback.
Részletek: [HC-08 javítás](docs/hc-08-repair.md), REPAIR-028.


## HC-09 — helyi javítás, nincs élesítve (2026-10-27)

A HC-08 után a HC-09 is elkészült helyileg. **Az aktív kiadás továbbra is a
korlátozott `hc-refactor-ai-offline-20261027-r6`.** Nem készült új élesítési
csomag, a 9 ellenőrzött éles konténer és a 37 aktív hostfájl változatlan.
DB/MQTT health és AI-offline profil ellenőrizve. A munkafa alap Compose-ja
két új konfigurálható limittel bővült; a fagyasztott r6 nem ezt olvassa.

A transport timeout most pontos; klíma és X10 esetén a publikálás csak
`sent`, korrelált bridge-nyugta `accepted`, friss parancs utáni eszközminta
`confirmed`. Az X10 confirmation a tárolt heti programot igazolja, nem
elvégzett takarítást. Visszajelzés nélkül nincs vak program-újraírás.

Későbbi kiadáskor a HC-08 és HC-09 backendmoduljait/app-bekötését, a Gree
`sampled_at`/korrelációt és az X10 `scheduler/observation`/korrelációt együtt
kell átadni, rögzített és kompatibilis rollback image-ekkel. Új migráció nincs.
A korábbi bridge-ekkel az új backend nem állít friss confirmationt; X10
friss olvasat nélkül nem ír programot. Függő fizikai szándékokat és a régi
physical_manual session 125 állapotát átadás előtt egyeztetni kell.

Kezdeti env: `HC_SCHEDULER_FEEDBACK_MAX_AGE_SECONDS=90`,
`HC_SCHEDULER_CONFIRMATION_TIMEOUT_SECONDS=120`. A véglegesítéshez felügyelt
klíma-/robotpróba és késésmérés szükséges. A HC-12/13 és HC-35/36 további
nyitott munka; itt nem változott. AI-offline és helyi mentési korlátok,
valamint az éles nyitásérzékelős safety-javítás megőrzendők. Az AI SSD-hiba
és a HC-45 teljes VM-restore hiánya továbbra is fennáll.

330 kapcsolódó teszt sikeres, hiba/kihagyás nélkül; 48 új HC-09 eset,
köztük 23 valódi PG16 tranzakciós teszt. A szoftveres ellenőrzés nem éles
eszközátvétel. Részletek és bizonyítékok: [HC-09](docs/hc-09-repair.md),
AUDIT_REPAIR.md REPAIR-029.


## X10 térképjavítás — helyi, nincs élesítve (2026-10-27)

A robotkommunikáció közös szál-/folyamatzárat és időhatárt kapott; a watchdog
külön figyeli a státuszt és az aktív élőtérképet. Sikertelen térképexport után
az MD5 nem lép előre, így a következő ellenőrzés újrapróbálhatja. 31 új és
52 kapcsolódó teszt sikeres; éles robotpróba/bridge-restart nem történt.
Az aktív r6 és az éles X10 változatlan.

Későbbi kiadásban együtt szükséges az új `x10_runtime.py`, `config.py`,
`xiaomi_x10_bridge.py` és `xiaomi_x10_map.py`. A bridge a helyi HC-09-et is
hordozza, ezt a kiadási csomagban össze kell hangolni. DB-migráció nincs.
Közös lockfájl szükséges a bridge és a mapfolyamat között; a Docker meglévő
`unless-stopped` szabálya biztosítja a watchdog utáni újraindítást.
Külön rögzített image/rollback és felügyelt térkép-/pozícióátvétel kell;
most nem készült új élesítési csomag. A HC-12/13 átfogó javítása továbbra is
nyitott. [Részletek és limitek](docs/x10-map-repair.md), REPAIR-030.


## HC-08/09 + X10 r7 — előkészített, élesítés blokkolt (2026-10-27)

Külön csomag: `backups/releases/hc-scheduler-x10-20261027-r7/`. Három immutable
image, release/rollback, privát mentések és végrehajtható ellenőrző/átadó helper.
330 backend + 31 X10 + 14 kaputeszt sikeres; tényleges háromszolgáltatásos
release/rollback/release és valós brokeres, szintetikus eszközös próba sikeres.
Friss dump owner/ACL-visszatöltése, F6 helyi archívum checksumja és hat image
offline mentése ellenőrizve. A HC-09 X10-read topiceltérése is javítva.

**Nem éles. Az aktív továbbra is r6.** A működésre várt Nano nem ad friss
STATUS/TELE adatot, a 125-ös fizikai kézi session nincs egyeztetve. Ezt a
felhasználó nem szándékos téli kikapcsolásnak jelezte. A helper a teljes
élesítést addig tiltja. Szelepparancs és adatbázis-sor lezárása nem történt.
A Nano táp/UART és a fizikai állapot helyszíni rendezése után újra kell futtatni
az ellenőrzőt; a 30 percnél régebbi helyi mentést váltás előtt frissíteni kell.

A rollback az előző backend/Gree/X10 image-eket használja, AI-offline mellett,
V2 automatikus indításokat tiltó flag-ekkel, safety/stop megőrzésével.
Nincs DB-restore, replay vagy mérés-/auditadat-törlés. Új migráció nincs;
frontend/ingest/Tuya/F6 nem változik. A r6 saját rollback helperje r7-hez nem jó.
[Teljes leírás](docs/hc-r7-preparation.md), [parancsok és rollback](backups/releases/hc-scheduler-x10-20261027-r7/DEPLOYMENT.md), REPAIR-031.

## HC-08/09 + X10 r7 — éles (2026-10-28)

A felhasználó rendezte a Nano és a kézi szelep állapotát, majd engedélyezte
az élesítést. Friss zárt szelepek, lezárt 125-ös fizikai session, új ellenőrzött
helyi F6 mentés és akadály nélküli preflight után a backend/Gree/X10 r7-re váltott.
Az aktív override r7; hat további konténer, a safety-forrás, a téli és az
AI-offline profil megmaradt. Új migráció nincs. REPAIR-032.

Friss Nano/Gree/X10 állapot és mindhárom mentett térképkép ellenőrizve.
Három júliusi shadow audit láncpótlása `unknown`, parancs-replay nélkül megmaradt.
Külön korlát: a Xiaomi-felhő jelenleg nem ad térképletöltési URL-t; a mentett
térképek és a helyi státusz működnek. Friss felhős térképátvétel nem igazolt.
Más auditpont lezárása vagy fizikai működtetési próba nem történt.

[Aktuális telepítés, mentési bizonyíték, ellenőrzés és r7 rollback](backups/deployments/hc-scheduler-x10-20261028-r7/DEPLOYMENT.md).


## HC-10 — helyileg ellenőrzött, nincs élesítve (2026-10-28)

Generációvédett, kulcsonként egy buildert használó cache; Context/API/domain
invalidálás összekötve, redundáns öntözési cache-réteg megszüntetve, a konfigurált
10 s TTL megtartásával. 290 sikeres teszt, tíz változatlan szintetikus payload és
query-counter, öt eredeti race javítva. Új migráció vagy függőség nincs.

Az éles r7, kilenc konténer és 37 hostfájl változatlan. A kilenc érintett
backendmodult új, külön kiadásban kell együtt csomagolni; a lezárt r7-be nem
másoltunk. HC-14/40/21/22/13 nyitott függőségek, F9 nincs lezárva. REPAIR-033.
[Részletek, ellenőrzés és rollback](docs/hc-10-repair.md).


## HC-13/14/21/22/40 — helyileg ellenőrzött, nincs élesítve (2026-10-28)

Az éles rendszer továbbra is `hc-scheduler-x10-20261027-r7`; a mai javítás és
a HC-10 helyi forrása nem került bele. Nincs új migráció vagy függőségfrissítés.
377 backend-/109 frontendteszt, frontendbuild, önálló AI-package import,
6,84 milliós izolált restore és read-only/SQL-azonosság, valamint Gunicorn
WS+AI+vezérlés/SIGTERM próba sikeres. A 9 éles konténer és 37 védett hostfájl változatlan.

Új kiadáshoz a HC-10 és az öt pont összetartozó backend-/frontendforrását kell
fagyasztani; a backend `gunicorn_conf.py`-t is tartalmazza. Egyetlen, nem preloaded
vezérlő fusson. Az AI-server későbbi újraépítéséhez projektgyökér build context és
a két közös Python-modul kell; az AI-offline policy most is érvényes.
Friss mentés/rollback, kiadási baseline-ellenőrzés és bevezetés utáni smoke szükséges;
élesítés ebben a munkában nem történt. Az SSD/HC-31 fizikai próba és a HC-45
VM/systemd full restore-korlát nem változott. Más auditpontot nem javítottunk.

[Részletes hatókör, kapacitáskorlátok, mérési határok és rollback](docs/hc-13-14-21-22-40-repair.md).


## HC-10/13/14/21/22/40 r8 — éles (2026-10-28)

Átadva 20:20:59 CET. Csak backend/frontend cserélődött, mindkettő immutable ID-re
rögzítve. 377 backend-/109 frontend-/9 kaputeszt, r8→r7→r8 izolált próba és az éles
nyolcnézetes Chromium-ellenőrzés sikeres. Az AI-offline/téli profil és a többi hét
szolgáltatás megmaradt. A friss F6 mentés és négy image offline másolata megőrizve.
A nyitott böngészőlap frissítendő; visszaálláshoz az r8 saját helperje használandó.

[Teljes átadás és parancsok](backups/deployments/hc-read-models-20261028-r8/DEPLOYMENT.md), REPAIR-035.
