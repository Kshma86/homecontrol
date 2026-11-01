# Közös HC-35/36 + HC-41/44 kiadás – 2026-10-31

**Aktuális állapot, 2026-10-31: a közös r10 élesítve.** A runtime és pinned
image-ek ellenőrzöttek, új teljes helyi mentés kész. X10 térképletöltési hiba
és fizikai/PC-átadás nyitott. [Éles jegyzőkönyv](../backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md).
Az alábbi csomag-előkészítési állapot történeti bizonyíték.

**Előkészítve és ellenőrizve, nincs élesítve.** Az aktív rendszer továbbra is
r9 ingest + r8 backend/frontend. A felhasználó kérésére a korábbi r10 csomagba
bekerült a HC-35/36; más auditpontot nem javítottunk automatikusan.

## ESP és csomagazonosság

A felhasználó 2026-10-31-én megerősítette az irrigation ESP **192.168.1.179** címét
és a **routeres DHCP-foglalást**. A két megerősítés rögzítve; a policy
`esp_confirmed=true`. A titkosított bundle újrakészült, valós age-dekódolás és
fájlhash-egyezés ellenőrzött. A dekódolt bundle-ben is ez a megerősített policy van.
Jelszóérték nem került a dokumentációba, az éles broker változatlan.

A jelenlegi kiadási könyvtár `backups/releases/hc-access-20261030-r10`, revíziója
`20261031-hc3536-combined`. Az előző előkészítés változatlan példánya:
`backups/releases/hc-access-20261030-r10-before-hc3536-20261031`.
Ez ellenőrzési referencia; az éles rollback célja a tényleges r9/r8 rendszer.
Az új runtime útvonala továbbra is `scripts/access_runtime/hc-access-20261030-r10`;
a hoston még nincs telepítve. A lezárás hash-leltára a `release.json`.

## Együtt átadott változások

A kiadás a közös ClimateFanCoordinatort, a binding/power-wall szolgáltatásokat,
a bindinget fogyasztó AI-/klíma-/energia-/öntözéskódot, az app bekötését és a két
frontendmódosítást együtt tartalmazza. Az explicit érvénytelen választás nem válthat
másik eszközre; a régi ventilátor késleltetett ON-ja nem élheti túl a bindingcserét.
A HC-44 scoped AI-koordináció, UID10001, read-only backend és root IPC megmarad.

Hét kiadási image szerepel: hat Python-szolgáltatás és a frontend. A hét image újraépült a jelenlegi pontos alapokra. A korábbi r10 jelölthöz képest
az alkalmazáskódban a backend/frontend változott; a többi öt Python-szolgáltatás
alkalmazásforrása változatlan. Nincs új DB-migráció, npm-/Python-függőségfrissítés vagy MQTT-jelszócsere.
A frontend az r8 forrásból és a két HC-35 módosításból, meglévő lock/cache alapján
épült; nginx-alapja a jelenlegi pontos frontendimage.

Az offline csomag **21 régi/új/infrastruktúra-image**, 650 291 715 byte, 241
ellenőrzött blob. SHA256:
`cc05451dd8757d75cd755c739ac6a182f4ffc63dff419bf4c3797a4c67f7fabd`.
Mind a 21 image linux/amd64 lánca teljes. Más upstream architektúrák/attestationok
nem részei a csomagnak. A bundle 50 titokfájlt tartalmaz, 13 aktuális fájl
frissítésével, az image-cache külön marad.

## Ventilátorindítások az átállásban és restore-ban

A telepítő a régi backend leállítása után, a közös backup lockok mellett rögzíti
a binding/policy előállapotot, majd egy rövid, advisory lockkal védett tranzakcióban
visszavonja a még függő `auto_climate_on_at` időpontokat. A helper maga is ellenőrzi,
hogy a backend leállt vagy még nem létezik; futó backendnél megtagadja a módosítást.
Csak a klímához tartozó ON-időpontokat törli: binding, policyflag, más kézi vagy
ütemezett munka és fizikai kapcsolóállapot nem változik. Az átadáskor érvényes
függő késleltetés is visszavonódik; a normál automatika később az aktuális állapotból
hozhat létre új szándékot.

Rollback előtt az új backend leáll, szükség esetén csak a PostgreSQL indul el,
majd a közben keletkezett késleltetett ON-ok ugyanígy visszavonódnak. Ezután térhet
vissza a korábbi backend/frontend. A mentett időpontokat a rollback nem játssza
vissza. A már megtörtént fizikai kapcsolást kód-visszaállítás nem vonja vissza.

Teljes restore esetén a dump visszatöltése után, a hostszolgáltatások és az
alkalmazás indítása előtt ugyanez az egyeztetés fut. A fagyasztott
`binding-release.json` jelzi a közös kiadást és a backend/frontend image-párt.
Hibánál nem indul tovább a rendszer. Minden fázis privát előállapot-/eredménynaplót
kap; a restore-futások külön azonosítót használnak.

A csak olvasásos éles leltárban mind a 11 jelenlegi hozzárendelés érvényes,
legacy fallback és függő klímaindítás nem volt. Ez időponti leltár, ezért az
átadáskor a telepítő ismét rögzíti az előállapotot és egyezteti az indítási szándékokat.

## Ellenőrzés és korlátok

[Gépi összesítés](audit-evidence/hc3536-access-combined-20261031/summary.json).

- 441 backend unit-/regressziós teszt: 0 failure/error/skip.
- 113 frontendteszt és Vite build: sikeres; a 4 bindingviselkedési eset is benne van.
- 19 valódi PostgreSQL-teszt transaction PgBounceren át: sikeres, külön belső hálózaton.
- 5 valós átadási/restore-forgatókönyv: futó backend tiltása, deploykori törlés,
  rollbackkori törlés, SQL-hibánál tranzakció-visszagörgetés és hamis siker tiltása,
  valamint valós pg_dump → üres DB → pg_restore utáni egyeztetés. A kiválasztott
  binding megmaradt, az új image moduljaival a régi ON nem publikálódott.
- 54 célzott restore-/unittelepítési teszt: sikeres; ez átfed a 441-es suite-tal.
- Kész non-root backend + ingest + valódi hitelesített MQTT/PostgreSQL/PgBouncer
  együtt ready; root IPC, 0660 socket, idegen UID tiltása, írási határok és közös
  AI-state ellenőrzött. E labor Docker CLI-je szigorú fixture, nem host-daemon.
- Mind a hat Python-image módosított fájljai egyeznek a fagyasztott forrással.
  A kész backendben a két szolgáltatás valóban ugyanazt a klímakoordinátort kapja,
  a scoped AI-koordináció megmaradt. A frontend valódi HTTP indexe és HC-admin
  JS-assetje bájtpontosan egyezik a builddel.
- A függőséglock, 16 éles konténer ID/image/start/restart, 37 aktív hostfájl,
  safety-forrás, broker-konfiguráció, eredeti audit és aktív r9 override változatlan.

A [2026-10-30-i teljes KVM-próba](hc45-vm-restore-20261030.md) a HC-35/36 nélküli
előző jelölthöz tartozik. A változatlan systemd/nft/root IPC lánc bizonyítéka
megmarad; a mai új átadási/restore-lépés valós DB/Docker-állapotokkal és wiring
tesztekkel ellenőrzött. **A teljes friss VM-bootstrap/reboot és a teljes
r9→r10→r9 élesítési tranzakció e közös revízióval nem lett megismételve.**
A mai dump/restore egy elkülönített klímaállapot-fixture, nem teljes éles DB/host.
Fizikai ventilátor/ESP/STOP, böngészős átadás és a meghibásodott AI-host próbája
nem futott. A tesztlaborok eltávolítva, éles eszközparancs nem ment ki.

Az első tesztfuttatásoknál a Node-cache mounthelye, két új teszt modulhivatkozása,
az ismételt labor readonly configfájljai és az nginx loopback backend-aliasa
környezeti/teszt-harness korrekciót igényeltek; a fentiek a végső sikeres futások.

## Következő lépés

A csomag előkészítése kész. A tényleges felügyelt élesítés külön utasításra,
friss baseline/mentés és root hostjog mellett történhet. Az érintett szolgáltatások
száma továbbra is **13**, PostgreSQL/PgBouncer/backend/frontend is újralétrejön,
ezért rövid DB/API-kieséssel és QoS0 mérési adatvesztéssel számolni kell.
Az ESP egyelőre 1883-as, forrás-IP-re és saját topicokra szűkített kivétel marad;
HC-41 csak a későbbi ESP-hitelesítéssel/legacy listener megszüntetésével zárható.
A fejlesztői dashboard/Explorer jelszavas reconnect és a fizikai átadási ellenőrzés
is az élesítés része. Az AI-offline/téli profil megmarad.
