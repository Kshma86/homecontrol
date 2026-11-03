# HC-41 – fokozatos MQTT-hitelesítés, átmeneti öntöző ESP-kivétellel

**Frissítés, 2026-10-31:** az ESP 192.168.1.179 címe és routeres DHCP-foglalása
felhasználó által megerősítve; a közös HC-35/36 + HC-41/44 r10 policy/bundle
véglegesítve, nincs élesítve. Az ESP egyelőre legacy kivétel marad.
[Aktuális csomag és átadási feltételek](hc3536-access-combined-20261031.md).
Az alábbi korábbi bejegyzések dátumuk szerinti állapotot írnak le.


2026-10-30. **Helyi előkészítés, nincs élesítve. HC-41: folyamatban.**
**Újabb állapot:** elkészült a célzott r10 image-/unit-/hálózati/mentési kiadási csomag.
Az ESP megerősítése és a felügyelt átadás marad hátra;
[aktuális eredmények és eljárás](hc41-44-release-preparation.md).
A további szakaszok az ezt megelőző klienselőkészítés bizonyítékait őrzik.
A felhasználó engedélyezte a HC-n futó MQTT-alkalmazások jelszavas átállításának
előkészítését; az öntöző ESP hitelesítését a későbbi firmware-frissítésre hagyjuk.
Ez felülírja a 2026-10-29-i általános jelszóhalasztást. Az eredeti audit HC-41,
kapcsolódó bizonyítékai és F1a elolvasva. Más auditpontot nem javítottunk.

**Kiegészítés:** az MQTT Explorerhez külön `hc_explorer`, csak olvasó identitás,
privát profil és SSH-alagút-leírás is elkészült; nincs aktiválva.
[Explorer-beállítások és új ellenőrzés](mqtt-explorer-access.md).

## Kétlépcsős működés

1. A HC-kliensek külön felhasználónévvel/jelszóval, domainenkénti topic-ACL-lel
   kapcsolódnak az **1884-es** listenerre. A Docker-hálózaton belül elérhető;
   a hoston csak `127.0.0.1:1884` publikált, a hosthálózatos klíma/Growatt számára.
2. A jelenlegi **1883** cím/port megmarad az ESP-nek, változatlan payloadokkal.
   A névtelen ACL csak a `homecontrol/tele/irrigation/esp-irrigation-1/#` és
   `homecontrol/stat/irrigation/esp-irrigation-1/#` írását, illetve a saját
   `homecontrol/cmd/irrigation/esp-irrigation-1/#` olvasását engedi.
   Más eszköz, Zigbee, klíma, robot és parancspublikálás tiltott.
3. Az ESP firmware-frissítésekor saját jelszavas identitást kell kapnia; annak
   tételes ACL-je a mostani három irány. Felügyelt telemetria/STOP/ack/reconnect
   próba után a névtelen listener, portpublikálás és ideiglenes hálózati kivétel
   eltávolítandó. A teljes HC-41 ezután zárható.

A Mosquitto támogatja a listenerenkénti hitelesítést/ACL-t; a használt 2.x image-en
a konfigurációt tényleges brokerpróba ellenőrizte. A `per_listener_settings`
újabb verzióknál elavuló opció, ezért ez a jelölt az ellenőrzött jelenlegi image-hez
tartozik, nem hallgatólagos brokerfrissítés.
[Mosquitto dokumentáció](https://mosquitto.org/documentation/listeners/per-listener-settings/).

## Elkészült helyi módosítások

- Közös tartalmú `mqtt_credentials.py` a hat önálló Python buildkontextusban.
  Felhasználónév és privát jelszófájl támogatott, az X10 saját prefixével is.
  Az új csomag `MQTT_AUTH_REQUIRED=1` beállítása mellett hiányos, olvashatatlan,
  túl nagy vagy ellentmondó hitelesítésnél nincs névtelen visszaesés.
  Az értékek nem kerülnek hibaüzenetbe. Hitelesítési konfiguráció nélkül a még
  át nem állított éles verzió korábbi viselkedése megmarad.
- Backend: valamennyi monitor, healthkapcsolat és egyszeri parancspublisher;
  ingest: a kapcsolat/reconnect tulajdonosának klienspéldánya.
- Tuya: meglévő konfigurációs hitelesítés megmarad kompatibilitásként, explicit
  környezeti hitelesítés elsőbbséget kap. Broker/port környezetből is átadható.
- X10 bridge és a külön, jelenleg nem konténerként futó legacy X10 API;
  Gree bridge és HA–Growatt poller. Az ingest Dockerfile az új modult is másolja.
- `scripts/prepare_mqtt_access.py`: új, privát jelöltcsomagot készít, meglévőt
  nem ír felül; nincs éles alkalmazási mód. Szerepkörönként véletlen jelszó,
  jelszófájl, ACL, brokerkonfiguráció és külön Compose override. Forrás-/config-
  exportfák alá nem engedi írni a credentialcsomagot. A jelszóadatbázist külön
  `mosquitto_passwd -U` lépéssel kell hashelni; a manifest ezt nyitott előfeltételként
  rögzíti. A labor kizárólag saját, eldobható jelszavakat használt.
- Zigbee2MQTT külön környezeti konfigurációt kap, a meglévő eszközadatbázis és
  Zigbee hálózati kulcs módosítása nélkül. A környezeti felülírást a
  [Zigbee2MQTT konfigurációja](https://www.zigbee2mqtt.io/guide/configuration/) támogatja.
- Az inaktív Grott profilhoz opcionális hitelesítési env-sablon és ACL készült;
  a profilt nem kapcsoltuk be. Verbose kikapcsolva, mert az upstream környezeti
  értékeket is naplózhat. Tényleges Grott indulás/DNS/payload külön ellenőrizendő
  aktiválás előtt. [Grott 2.8.3 konfigurációs forrás](https://github.com/johanmeijer/grott/blob/master/grottconf.py).
- `mqtt_read_probe.py` és `scripts/mqtt_access/post_boot_health.sh`: a host
  indulás utáni ellenőrzés a backend hitelesített, csak feliratkozó probe-ját
  használja a névtelen broker-CLI helyett. A jelenlegi éles script és unit
  változatlan; az új adapter csak a későbbi fagyasztott kiadással telepítendő.

A backend a szükséges HC/Zigbee állapotokat olvashatja és a meglévő vezérlési
topicokra írhat. Az ingest csak olvasó. A bridge-ek saját domainjükre korlátozottak;
az X10 bridge és Zigbee2MQTT saját domainen belül tágabb írást igényel. A legacy
X10 API külön `hc_x10_api` identitást igényel, ha újra használatba kerül; a bridge
identitásával nem kell megkerülni a parancspublikálási határt. Az ACL a jelenlegi
topicnevekre készült; egyedi base-topic módosításakor újra kell generálni/ellenőrizni.

## Hálózati kivétel és friss leltári függőség

**Friss ellenőrzés, 2026-10-30:** a **192.168.1.179** cím REACHABLE szomszéd,
MAC-je `ec:e3:34:db:ea:9c`, és aktív broker-TCP-kapcsolata van. Az öntözési
nano_status/solar/pump_metrics topicokat az `esp-irrigation-1-db34e3ec` kliens
publikálja; végződése egyezik a MAC első négy bájtjának fordított sorrendjével.
Ez erős üzemi egyezés, ezért az átmeneti kivételhez ezt a jelenlegi címet vesszük
alapul. Friss CONNECT rekordot nem találtunk, HTTP-azonosítás nem volt elérhető;
a forrás-IP és kliensazonosító összerendelése a fenti egyezésből következtetés.
**A tartós DHCP-foglalás/fix cím megléte továbbra sincs igazolva.** A kliensazonosító
vagy IP önmagában nem kriptográfiai hitelesítés.
[Csak olvasó vizsgálat bizonyítéka](audit-evidence/hc41-esp-ip-20261030/verification.json).

Új függőség: a **192.168.1.89 fejlesztői PC** `irrigation-dashboard-lite-local-web`
kliensként közvetlen MQTT-kapcsolatot is használ. Nem minden kliens fut a HC-n.
A felhasználó külön jelszavas dashboardhozzáférést kért. Az előkészített
`hc_dashboard` szerepkör csak az ESP saját
öntözési ágait olvashatja és a saját öntözési parancsokra írhat. A PC-t nem vesszük
fel a névtelen IP-kivételek közé. A dashboard a terv szerint a loopback jelszavas
portra SSH-alagúttal kapcsolódik; közvetlen LAN-eléréshez külön felülvizsgálat kell;
a PC-n is konfigurálni kell. A privát `dashboard-client.env` általános beállítási
sablon a `127.0.0.1:21884` alagútvéghez; mezőneveit a tényleges dashboard
konfigurációs sémájához kell igazítani. Csak a dashboard saját hozzáférése adható
át a PC-nek, a teljes broker-jelszóadatbázis nem. Távoli PC-konfiguráció nem módosult.

A `scripts/plan_mqtt_legacy.py` csak felülvizsgálandó hálózati parancstervet ad.
A régi, hostpublikálásra szűrt terv önmagában kevés: a közvetlen Docker-peer →
broker és host → broker útvonalakat is kezelni kell. Az új terv a DNAT utáni
broker-célra, az OUTPUT-ra és az IPv6/proxy utakra is kitér. Nem futtat parancsot,
nem idempotens telepítő, nem állítja késznek a tűzfalat.

**Nem szabad a névtelen kivételt általánosan elérhetőként élesíteni.** Az adott
host iptables/nft, bridge-netfilter, NAT és IPv6/proxy viselkedését igazolni kell,
majd tartós, idempotens és pontosan visszavonható szabályt telepíteni. A broker
konténercímének változása esetén a szabályt is frissíteni kell. Ismeretlen vagy
proxy mögé rejtett forráscím nem kaphat automatikus engedményt. A hitelesített
kliensek sem kerülhetik meg az ACL-jüket azzal, hogy a régi névtelen portra mennek.
Ezek a hostoldali hálózati próbák most nem futottak le.

## Ellenőrzés

A gépi összesítés és reprodukció:
[bizonyítékok](audit-evidence/hc41-stage-20261030/summary.json).

- **422 sikeres backend unit-/regressziós teszt**, 0 failure/error/skip,
  ebből 14 új hitelesítési/csomag-/hálózatiterv-teszt, hálózat nélküli konténerben.
- **14 sikeres valódi brokerforgatókönyv**, a jelenlegi pontos Mosquitto image-en,
  `network=none`, közös laborhálózati namespace-ben, publikált port nélkül.
  Mind a 10 előkészített identitás kapcsolódott; névtelen/hibás jelszó az 1884-en
  elutasítva. Legacy telemetria, szintetikus STOP/ack, retained, LWT és reconnect
  sikeres. Legacy idegen eszköz/domain és parancspublikálás tiltott; ingestírás
  tiltott. Tuya/X10/klíma szintetikus parancsátadás, bridge-domainhatár, opcionális
  dashboard-ACL, valódi backend monitor/publisher és hitelesített post-boot probe
  sikeres. Egyetlen fizikai eszköz sem vett részt a laborban.
- A Compose parserben mind a hat futó Python szolgáltatás és Zigbee2MQTT
  átállításának szerkezete ellenőrizve, a Growatt profil csak parserellenőrzéshez
  bekapcsolva. Az 1884 hostpublikálás kizárólag loopback. Python-szintaxis és az új
  post-boot adapter Bash-szintaxisa ellenőrizve. Teljes új bridge-image-ek és
  hardveres kommunikáció nem kaptak sikeres minősítést.
- A hashsegéd első laborfutása írásvédett ideiglenes könyvtár miatt elakadt;
  eldobható `/tmp`-vel javítva a laborban. Éles konfigurációt nem módosítottunk.
  A broker laborban host UID1000-ként olvasta a privát csomagot; az éles broker
  UID-jének tulajdonosi/olvasási jogait a telepítésnél külön igazolni kell.
- Az aktív r9 override, éles MQTT-konfiguráció, 37 védett hostfájl, eredeti audit
  és safety-forrás változatlan. A tegnapi leltárhoz képest az X10 önálló indulási/
  restartszáma változott; az MQTT-javítás nem indított éles konténert újra.

## Hátralevő átadás és rollback

Az ESP azonosságának és fix címének, a dashboard használatának, a host hálózati
szűrésének és a privát credentialjogoknak a rendezése után fagyasztott, ellenőrzött
kiadási csomag kell. A jelszavak privát release/runtime könyvtárban maradjanak,
konfig-Git exportba ne kerüljenek. Az új titkok titkosított mentési/restore
lefedését és a post-boot adapter telepítését is át kell vezetni a kiadásban.
Ez HC-45/F6 átadási függőség; nem zártuk le automatikusan a külön auditpontot.

A munkafa HC-35/36 és HC-44 helyi javításokat is tartalmaz. **A teljes munkafa
egyszerű Compose-upja nem kiadási eljárás.** Vagy külön, célzott MQTT-image-eket
kell készíteni a jelenlegi pontos image-ekből, vagy a többi javítással együtt
felülvizsgált csomagot. A hostszolgáltatásos HC-44 nem válhat véletlen függőséggé.

Friss mentés és korábbi pontos image-/broker-/kliens-/unit-/tűzfalszabály-állapot
szükséges. Felügyelt átálláskor a broker és minden függő kliens összehangolt
újracsatlakozását, valamint a tényleges telemetria/STOP/ack útvonalat ellenőrizni
kell; QoS0 miatt rövid üzenetvesztés lehetséges. Nincs automatikus riasztásnyugtázás
vagy fizikai indításpróba.

Rollback: a korábbi broker és klienskonfiguráció/image-ek együtt, a korábbi
post-boot adapterrel. Az ESP-re szűkített hálózati határ megőrzendő; általános
névtelen parancsbusz nem lehet észrevétlen visszaállítási lépés. Hozzáférési
korlátozás miatti fizikai stopkiesésnél a helyi leállítás elsőbbséget kap.
Jelszófájlok, receipt és feladatállapot nem törlendők automatikusan; élesítés
csak a fennmaradó ellenőrzések után történhet.
