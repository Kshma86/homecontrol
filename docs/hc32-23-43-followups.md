# HC-12 kapcsolódó javításai – 2026-10-31

**2026-11-02-i kiegészítés:** az aktuális éles runtime r16. A HC-23/43 új
platformfrissítése külön [r18 csomagban](hc23-43-platform-release-20261102.md)
áll helyi élesítésre készen. A következő bekezdések történeti r13/r12 állapotot
rögzítenek; nem a jelenlegi aktív kiadást írják le.

**Aktív: `hc-f10-20261031-r13`, élesítve, szoftveresen ellenőrizve.**
Az r12 HC-12/32 és HC-23/43 részjavításai, valamint az X10 indulási online-jelzés
korrekciója éles. Nyolc alkalmazás a várt image-en healthy, restart0; DB/MQTT
és minden backend health/worker/readiness sikeres. X10 online=1 és friss
telemetriát küld, tölt. Az r13 csak X10+backend újraindítás volt, a másik
14 konténer ID/image változatlan. 690 telepített forráshash egyezik.
Öntözés winter, védelmi API idle, a védelem enabled=true, AI SSD-korlátozás megmaradt.
[Éles r13 átvétel és rollback](../backups/deployments/hc-f10-20261031-r13/DEPLOYMENT.md).
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
[Éles r12 ellenőrzés](../backups/deployments/hc-f10-20261031-r12/DEPLOYMENT.md),
[r13 javítás átadása](../backups/deployments/hc-f10-20261031-r13/PENDING.md).

A további bejegyzések korábbi helyi/kiadási állapotokat dokumentálnak.

**Helyi munka, nincs élesítve.** HC-32 javítva és ellenőrizve. HC-23 és HC-43
részben javítva, a teljes auditpontok folyamatban maradnak. Az aktív r10 kiadás
és annak lezárt runtime-ja változatlan.

Elolvasva: az eredeti audit HC-23/32/43 megállapításai, HC-32 I./J. reprodukciója,
HC-43 L.6/M.6 leltára és feltételvizsgálata, valamint F10 előfeltételei,
ellenőrzése és rollbackje. HC-09, HC-12, HC-13 és HC-41 szerződése megőrzendő;
HC-24/26 vagy más nyitott auditpont nem kapott javítást.

## HC-32: Tuya küldési eredmény és reconnect

Az eredeti `mqtt_publish()` sikertelen reconnect után eredmény nélkül tért vissza,
miközben a hívó elküldöttként jegyezte fel az értéket. Most a paho hálózati szála
birtokolja a reconnectet; a publisher nem végez szinkron újracsatlakozást, és nem
állítja saját maga online-ra a klienst. A CONNACK/disconnect callbackek vezetik
a kapcsolatállapotot és a fingerprint-cache generációját.

**A sikerhatár helyi kliensbefogadás:** `publish().rc == MQTT_ERR_SUCCESS`.
Ez QoS0 és QoS1 esetén sem broker-PUBACK, tartós kézbesítés vagy fizikai állapot.
A fingerprint csak ilyen eredmény és változatlan, online kapcsolatgeneráció
mellett frissül. Hibás rc/kivétel/közben megszakadt kapcsolat esetén az érték
publikálandó marad. Nincs PUBACK-várakozás a callbackben.

Reconnectkor a cache ürül. Nincs régi payloadsor: a következő poll legújabb
állapotát próbáljuk küldeni. Az újraküldés alapból 100 üzenet/s, legfeljebb
100 kezdeti tokennel; reconnect nem tölti újra a tokeneket. Konfiguráció:
`TUYA_MQTT_PUBLISH_RATE`, `TUYA_MQTT_PUBLISH_BURST`, pozitív véges értékekkel.
A poll körönként másik eszközzel kezd, ezért a sor végén lévő eszközök is sorra
kerülnek. A változatlan értékek heartbeatje megmarad. A cache legfeljebb
8192 topicot tárol; nincs benne payload. A paho kimenő sora 256 üzenetre,
in-flight készlete 20-ra korlátozott. A parancseredmény nem lép a telemetria
token-bucketjébe; az ilyen best-effort eredmény továbbra sem fizikai nyugta.

A `state` és `/m/current_a` payloadszerződés változatlan. `pump_current` átnevezés
nem került vissza. A számlálók a poller stats `mqtt_publish` mezőjében látszanak.

## HC-23: elkészült részek és fennmaradó határ

- Backend: tisztán olvasó `/health/live`, `/health/workers`, `/health/ready`.
  Egyik sem indít workert, SQL-t, MQTT-kapcsolatot vagy teljesítménynaplózást.
  A Docker-healthcheck a worker-végpontot használja: a meghalt/beragadt,
  elvárt vezérlési worker hibát ad; egy dependency-kiesés külön readiness-hiba.
  Bootstrap előtt a HTTP élhet, de nem üzemkész. A régi `/health` kompatibilis
  dependency-próba marad; az új healthcheck nem azt hívja.
- Egyetlen, leállítható és újrapróbálkozó bootstrap-szál indul. A DB elérhetetlensége
  már nem akadályozza a HTTP-liveness indulását. Az egy Gunicorn-worker és a
  vezérlési tulajdonos lockja megmarad.
- Tuya/Gree/X10/Growatt: helyi, korlátos JSON-életjel; processzazonosság, valódi
  poll-haladás, parancsgazda-haladás és külön legutóbbi siker. Az olvasó probe nem
  importálja a bridge-et és nem kommunikál eszközzel/brokerrel. Friss riportáló
  szál nem rejtheti el a beragadt pollt vagy parancsgazdát.
- A bridge-ek `connect_async()` útvonalon indulnak MQTT nélkül is. A Gree
  reconnect a meglévő pollert ébreszti fel, nem hoz létre új lekérdezőszálat.
  Growatt polling nem kapott batch-átalakítást (HC-26).
- AI-gateway a HC-hoston: tiszta `/health/live`; külön `/health/ready`.
  A provider ellenőrzése nem fut livenesskor. A külső, SSD-hibás AI-gép nem változik.
- Hét teljes Python-verziózár, hash-elt biztonsági wheelek, ellenőrzött helyi
  alapimage-ek, nyolc külön candidate-image. A generikus Python 3.12 és frontend
  Dockerfile is digestet használ. A Python 3.11 Dockerfile-okhoz explicit
  `PYTHON_BASE_IMAGE`, ingestnél `INGEST_BASE_IMAGE` kell; nincs mozgó alapértelmezés.
- Közös célzott ellenőrzőparancs: `scripts/check_f10_units.py` a candidate backend
  image-ben, a nyilvános forrás/teszt fixture-rel. Integritás és teljes csomagzár:
  `python3 scripts/check_f10_candidates.py`. Ezek nem telepítenek.

**HC-23 nincs teljesen lezárva:** a globális, profilokra bontott teljes tesztfuttatás,
a külső HA/AI telepítési út lezárása hátravan. A pozitív DB/MQTT startup/restore/
rollback az r11 izolált labjában már sikeres (REPAIR-056). A worker-health az r11
csomagba beépítve, de még nincs élesítve.
Az AI SSD miatti kivétel érvényben marad.

## HC-43: célzott csomagjavítások

A teljes nyilvános PyPI OSV-katalógust letöltöttük; a privát leltár helyben maradt.
A leltár buildeszközöket is tartalmaz, azok találata nem automatikusan futó HTTP-hiba.
Az aliasokat összevonó előállapot és a nyers rekordok külön bizonyítékban vannak.

| Csomag | Candidate-verzió, ahol telepítve van | Vizsgált határ |
|---|---|---|
| Flask | 3.1.3 | Session/cache/Vary feltétel; az általános HC-kihasználhatóság nincs igazolva |
| Pillow | 13.0.0 | Backend/AI képfeltöltés és X10 térképrender: valódi dekódolási felület |
| urllib3 | 2.8.0 | Streaming/deflate feltételek; nincs általános HC-exploit állítva |
| requests | 2.34.2 | Growatt régi 2.32.4 verziója is javítva |
| certifi | 2026.10.18 | CA-készlet javítása; Xiaomi-felhő bizalmi láncának éles smoke-ja még kell |
| Werkzeug | 3.1.9 | X10 régi 3.1.8 frissítve; platformfeltétel külön kezelve |
| pip / setuptools | 26.2.2 / 84.2.1 | Build/telepítés; nem igazolt futó HC-HTTP hiba |

Elsődleges források: [Flask](https://github.com/pallets/flask/security/advisories/GHSA-68rp-wp8r-4726),
[urllib3](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g),
[Requests](https://github.com/psf/requests/security/advisories/GHSA-gc5v-m9x4-r6x2),
[certifi](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2),
[Pillow 13 változások](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html).

A Gree 3.2.0 és python-miio 0.5.12 protokollkönyvtárak verziója megmarad;
nem történt indokolatlan főverzióváltás. Az X10 Click 8.1.8 korlátja is megmarad.
`miiocli --help`, PNG/JPEG/WebP feltöltés és tényleges mentetttérkép-render sikeres.

A frontend öt érintett csomagja explicit override + új lock:
baseline-browser-mapping 2.11.0, browserslist 4.28.7, nanoid 3.3.18,
postcss 8.5.23, source-map-js 1.2.2. A nyolc eredeti advisory javított
tartományait a [nyilvános GitHub-válaszok](audit-evidence/hc32-23-43-20261031/npm-advisories.json)
rögzítik. Teljes friss npm-advisory-katalógusvizsgálat nem történt.

**Nem teljes HC-43 lezárás:** a hét tényleges Python-candidate 2026-10-31-i
szemantikus/explicit OSV-verzió-összevetése 0 találatot adott. 53 Git-tartományt
is tartalmazó, kiadási verzióra nem teljesen leképezhető rekord `unknown` maradt.
Ez nem teljes sérülékenységmentességi igazolás. A Home Assistant 2026.7.2
változatlan; az új leltárban továbbra is érintett. A HA saját támogatott
kiadásával, másolatból végzett DB-/integrációpróbával frissítendő, közvetlen pip
beavatkozás nélkül. Mind a 15 futó konténer OS-leltára rögzítve; OS scanner,
javított alapimage-ek és az elavult PgBouncer/Node/Nginx rétegek kontrollált
cseréje még hátravan. A candidate-ek ezekben megtartják a kompatibilitási alapot.

## Tényleges ellenőrzés

| Vizsgálat | Eredmény |
|---|---|
| Backend célzott vezérlési/payload/health/audit-tool mátrix | 339 sikeres, nincs skip |
| Bridge queue + Tuya publisher + worker-health | 54 sikeres |
| X10 MIIO/watchdog és valódi Pillow-render | 33 sikeres |
| Ingest recovery/batch/forrás/safety/health | 52 sikeres |
| Frontend teljes Node-suite és statikus build | 113 sikeres; build sikeres |
| Frontend-image statikus HTTP és régi assetek kizárása | Sikeres, szintetikus backend DNS-sel |
| MQTT bridge retained/burst/STOP/reconnect, tesztaktuátorok | 9 sikeres |
| Új Tuya publisher valódi broker/paho mellett | 6 sikeres |
| Teljes Python-processzek külső dependency nélkül | 7/7 él, readiness helyesen hibás |
| Python-image forrás/wheel/lock + pip check + AI-tiltás | 7/7 rendben |

Összesen 591 célzott unit/frontendteszt, ezen felül a felsorolt broker- és
processzpróbák. A processzpróba rövid indulási smoke, nem tartós üzemi mérés.
A Tuya broker-próba tokenórája kontrollált, hálózati kommunikációja valódi.
A másik 9 brokeres eset kapcsolati callbackje laboradapter, aktuátorai fixture-ök.
A frontend külön HTTP-próbája a változatlan nginx upstreamhez loopback
`backend` DNS-aliast kapott; API-t és valódi backendet nem hívott.

A széles backend discovery **nem zöld**: mind a régi, mind az új csomagokkal
998 teszt, ugyanaz a 29 failure + 7 error, 183 skip; új hibás tesztazonosító nincs.
Eltérő profilhoz készült backuppróbák, rootjogot váró ownership-próba, hiányzó
sealed-runner/firmware fixture és nem konfigurált PostgreSQL okozzák a korlátot.
Ezt nem kezeltük sikeres teljes suite-ként, nem javítottunk hozzá más auditpontot.
Az összehasonlítás a worker-endpoint utolsó kiegészítése előtti discovery-n készült;
a végső health és audit-tool változat a 339-es célzott suite-ban szerepel.

## Következő kiadás és visszaállítás

A candidate-könyvtár `backups/releases/hc-f10-20261031-candidate`; ez **nem kész
éles telepítőcsomag**. A nyolc image külön rögzítve, az összes jelenlegi éles
image baseline-ja külön lockban. A r10 lezárt csomagját nem írjuk felül.

Élesítés előtt külön kell a döntött kiadási terjedelem, friss mentés, immutable
release/rollback integráció, az új revízió pozitív DB/MQTT startup/restore-próbája,
bridge-enként felügyelt hardveres STOP/OFF/sorrendpróba, X10 felhő-/térképsmoke
és a tényleges késések ellenőrzése. A korábban függő parancsot nem szabad
visszajátszani. A safety és az AI-tiltás szabályai megmaradnak.

Nincs DB-migráció. Helyi rollbackhez az eredeti források és image-azonosítók
megőrizve; későbbi éles rollback komponensenként az előző image-et tegye vissza,
a RAM-sort és régi vezérlési szándékot soha. Csomagfrissítés és health/queue
külön is kiadható, a választott források saját ellenőrzése után.

[Bizonyítékok és gépi összegzés](audit-evidence/hc32-23-43-20261031/summary.json).


## r11 kiadási integráció

REPAIR-056: elkészült a nyolc alkalmazásra korlátozott telepítő, a 24 image-es
loadolt offline recovery-cache és a 10 telepítőteszt. Valódi izolált DB/pool/
hitelesített MQTT mellett az indulás, régi image-re visszaállás és DB-dumpból
újraindulás sikeres. Root hostops-IPC szigorú Docker CLI fixture-rel ellenőrizve.
A r10 és az eredeti audit változatlan, új SQL-migráció nincs.

Az élesítés engedélyezett, de nem futott: az automatikus jóváhagyási ellenőrzés
külön engedélyt kér a mentett Xiaomi-munkamenettel végzett felhőpróbához;
a host pedig sudo-jelszót kér a root váltáshoz. Névtelen TLS-próba sikeres.
A [kiadási állapot](../backups/deployments/hc-f10-20261031-r11/PENDING.md) és
[a telepítés/visszaállítás leírása](../backups/releases/hc-f10-20261031-r11/README.md)
tartalmazza a végrehajtás pontos kapuit. A globális HC-23/43 státusza nem változott.


A Xiaomi-próba jóváhagyása megérkezett. Az első kísérlet a root:root 0600 authfájl
olvasásánál, külső hitelesítés előtt megállt. Most az egyetlen helyi sudo-s
`activate.py` parancs előbb cloud smoke-ot végez, és csak siker esetén vált élesre.
12 telepítőteszt sikeres; engedélyre már nem várunk. Az éles r10 változatlan.
