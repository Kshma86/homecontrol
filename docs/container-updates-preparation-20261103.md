# Konténerfrissítések – lezárt előkészítés, 2026-11-03

Állapot: **előkészítve, élesítés előtt**. Aktív kiadás továbbra is
`hc-audit-20261103-r22`. Jelölt: `hc-containers-20261103-r23`.
A felhasználó kérte a frissítések elvégzését; konzolos hozzáférés rendelkezésre áll.
A helyi sudo jelszót a kezelő adja meg az alábbi indításhoz.

| Frissítés | Előző | Jelölt |
| --- | --- | --- |
| Zigbee2MQTT | 2.8.0 | 2.14.3 |
| Mosquitto | 2.0.22 | 2.1.2-alpine |
| Frontend és proxy libexpat | 2.9.0-r0 | 2.10.0-r0 |
| Gree és X10 linux-libc-dev | 6.12.113-1 | 6.12.115-2 |
| Nyolc saját Python-image pip | 26.2.2; mDNS: 25.0.1 | 26.3 |

Összesen 12 szolgáltatás image-e változik: AI-szerver, backend, frontend, ingest,
Gree, Growatt, Tuya, X10, mDNS, MQTT, proxy, Zigbee2MQTT. Az AI alkalmazásszintű
tiltása megmarad. A Python-verzió és az összes többi telepített Python-disztribúció
verziója változatlan, a pip dependency-check sikeres. A négy OS-réteg pontos
csomageltérése és az indítási konfiguráció megőrzése ellenőrzött.

PostgreSQL 16.15, PgBouncer 1.26.1, nginx 1.30.6 és Home Assistant 2026.10.4
esetében a jelenleg támogatott stabil ágon nincs újabb alkalmazásverzió.
A PostgreSQL, PgBouncer, HA és a leállított Adminer konténerazonosítója megőrzendő.
A konténernevek, hálózati címek és tartós adatbindok rögzítettek; az MQTT
konfigurációja új, védett kiadási könyvtárba kerül.

## Ellenőrzések

- A végleges image-ekkel **1327 regressziós teszt** sikeres: unit 818,
  jogosultság 2, éles policy 19, PostgreSQL 198, frontend 114, bridge 54,
  ingest 52, X10 33, mDNS 19, Growatt 18. Nincs kihagyott vagy hibás teszt.
- Az r23-ra átvezetett forrás korábbi unit 818 / policy 19 próbája sikeres;
  a tranzakció és fájlkezelés 16 tesztje, valamint az új frissítő 26 tesztje
  sikeres. Az audit-adapterek 80, a mountváltási cache-másolás 10 és a
  health timer lezárásának 11 további tesztje is sikeres. A frissítő a részleges leállás, fizikai kapu, tűzfal, visszaállítási
  sorrend és MQTT/Zigbee adatvisszaállítás hibáit is ellenőrzi.
- A régi és új Zigbee konfigurációvalidáció schema 5, Ember adapter,
  57 konfigurált eszköz és 58 adatbázis-bejegyzés mellett sikeres.
  A jelölt kód EZSP 13–19 támogatása ellenőrzött. A tényleges rádiókapcsolatot
  az éles kapu külön ellenőrzi; firmware-frissítést ez az eljárás nem végez.
- Az izolált MQTT-próba régi adatbázist beolvasó új brokert, jogosult és tiltott
  műveleteket, retained adatot és a régi adatbázismásolatból történő rollbacket
  ellenőrizte. A 2.0 korábbi MQTT-csomagméretét explicit konfiguráció megőrzi.
  Az éles broker védett konfigurációjának és backend-hitelesítésének izolált
  próbája helyi sudo után, bármely szolgáltatás leállítása előtt kötelező.
- Nginx konfiguráció/start mindkét image-ben és frontend HTTP 200 sikeres.
- Az offline Docker-archívum 31 image-et tartalmaz, beleértve minden r22
  baseline-image-et. 414 tartalomcímzett blob hash-ellenőrzése sikeres;
  az archívum a helyi Docker image-tárba visszatölthető, mind a 31 ID egyezik.
  Ez nem új, tiszta bare-metal/VM-visszaállítási próba.

Archívum: 2 122 100 191 bájt;
SHA-256: `47f23787847c2ae99b34530a306ed79e9e6ce5e5ce489e99d3bd8b8b5f23dee1`.
A régebbi archívumok és kiadások megőrizve.

## HC-43

A friss Trivy 0.76.0 adatbázissal a 12 jelölt image helyi, offline vizsgálata
elkészült; leltár nem került külső szolgáltatáshoz. A frontend/proxy/MQTT/Zigbee
négy jelöltjében nincs scanner-találat. A pip-frissítés megszüntette a korábbi
vendored msgpack/urllib3 találatokat. A pip SBOM-ja továbbra is setuptools
70.3.0-t deklarál: a három hozzá társított advisory érintett forrásfájljai
egyik jelölt vendor-fájában sem találhatók. A közvetlen setuptools vagy nincs
telepítve, vagy 84.2.1; a platform Linux. A nyers scanner-bejegyzéseket ez a
triage nem törli és nem minősíti át telepített gyártói javításnak.

A Debian stabil ágon továbbra is javításra váró OS-találatok és a külön
nyilvántartott HA-maradványok miatt **HC-43 Folyamatban marad**. A backendben
például az OpenSSH CVE-2026-60002 kritikus jelzése megmaradt; a friss scanner
nem ad hozzá támogatott stabil javítóverziót. A frissítés nem teljes audit-lezárás.
Az eredeti audit SHA-256-ja változatlan:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.

Források: [Zigbee2MQTT kiadás](https://github.com/Koenkk/zigbee2mqtt/releases/tag/2.14.3),
[Mosquitto hírek](https://mosquitto.org/blog/),
[hivatalos Mosquitto image](https://github.com/docker-library/official-images/blob/master/library/eclipse-mosquitto),
[pip változásnapló](https://pip.pypa.io/en/stable/news/),
[Debian OpenSSH tracker](https://security-tracker.debian.org/tracker/CVE-2026-60002),
[host utáni HC-43 felülvizsgálat](hc43-after-host-update-20261103.md).

## Éles indítás

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23/source/scripts/container_update/activate.py
```

Egyszeri, systemd által felügyelt futás. Először a lezárt csomagot, az r22
teljes éles állapotát, tárhelyet, lockokat és a fizikai eszközök nyugalmi
állapotát ellenőrzi. A robot legyen dokkolva/töltésen, öntözés ne fusson.
Teljes repository-adatellenőrzés, friss HC/Git/router előmentés és izolált
PostgreSQL-restore kötelező. Az MQTT/Zigbee visszaállítási adatmásolata csak
a két szolgáltatás leállítása után készül. Ezt követi a sorrendezett átállítás.
Hibánál az automatikus rollback a megőrzött r22 konfigurációt és a leállított
MQTT/Zigbee adatmásolatot állítja vissza; későbbi kiadást nem írhat felül.

Sikernek csak friss r23 HC/Git/router utómentés, visszaolvasás és külön
PostgreSQL-restore, valamint a runtime-hashek, 16 konténer, fizikai kapcsolatok,
tűzfal és timerek ellenőrzése után minősül. A végállapot:
`container_updates_backup_restore_verified`. Hostreboot nem része az eljárásnak.
A szolgáltatások az átállítás idején röviden kiesnek; a mentések ennél tovább
tarthatnak. A terminál végső kimenetét kell visszaadni az átadáshoz.

Hiba esetén az indítást ne ismételd; csak állapotlekérdezés:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23/source/scripts/container_update/activate.py status
```

Privát naplót és hitelesítőadatot nem kell bemásolni. A régi kiadások általános
aktiváló/rollback indítói nem helyettesítik ezt a konténeradatokat kezelő eljárást.
Bizonyítékok: `backups/releases/hc-containers-20261103-r23/evidence/`.
