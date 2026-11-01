# HC-10 — Cache-versenyhelyzet és invalidálás

**Élesítési frissítés:** 2026-10-28 20:20:59 CET, az r8 kiadásban aktiválva.
[Éles ellenőrzés és r7 rollback](../backups/deployments/hc-read-models-20261028-r8/DEPLOYMENT.md).
Az alábbi leírás a korábbi helyi javítás és izolált ellenőrzés történeti állapota.


**2026-10-28. Állapot: helyileg javítva és izoláltan ellenőrizve; nincs élesítve.**
Az éles rendszer továbbra is az r7. Más auditpont státusza nem változott.

## Kiindulás és bizonyíték

Elolvasva az eredeti audit HC-10 megállapítása, a H.1 barrieres reprodukciója,
a B.5/B.6 cache- és időbélyeg-korlátai, valamint az **F9** teljes lépése.
A kiindulási forrás külön másolata `/tmp/hc10-20261028/before/`; az eredeti
audit SHA-256 változatlan: `51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.
A korábbi r7-átadás friss, ellenőrzött helyi mentése és rollbackcsomagja megmaradt;
ehhez a kódjavításhoz DB-/konfigurációmódosítás vagy új telepítés nem kellett.

Az eredeti cache a lock elengedése után építette a payloadot, majd ellenőrzés
nélkül visszaírta. Ugyanazzal az eseményekkel szinkronizált próbával **öt úton**
reprodukáltuk: ContextService, ApiCache, öntözési snapshot, pilot és időjárási
összegzés. Invalidálás után a régi eredmény maradt a következő olvasásra is.
Az MQTT és egyes parancsok csak az egyik cache-réteget törölték.

## Változtatás

- Új, közös `ReadModelCache`: kulcsonként egy adatépítő; a többi kérés csatlakozik.
  Generációellenőrzés védi az invalidálást akkor is, amikor még nincs tárolt érték,
  csak folyamatban lévő első build. A builder és a payloadmásolás a cache-lockon
  kívül fut; külön kulcsok egymástól függetlenül frissülhetnek.
- Érvénytelenített buildet nem adunk vissza és nem tárolunk. Újraépítés után
  friss eredmény szolgálható ki. Három megszakított build után explicit
  `read_model_changed_during_build` hiba zárja a kérést; nincs végtelen újraépítés.
  A Context API ezt `ok=false` payloadként jelzi, nem gyorsítótárazza. A builder
  kivétele felszabadítja a tulajdonost; új kérés helyreállhat. Ez nem általános
  I/O-határidő vagy megszakítható workerkezelés.
- A TTL a sikeres build végén indul. A cache másolatokat tárol és ad vissza;
  a válasz módosítása nem változtatja meg a következő kliens adatát. `None`
  eredményt továbbra sem tárolunk. A force-kérés csatlakozhat egy már futó
  frissítéshez, külön második builder nélkül.
- A ContextService, ApiCache és a három belső öntözési cache ugyanazt a mechanikát
  használja. A korábbi osztott API get/build/set olvasók hat payloadépítőjét
  egyetlen védett builderhívásra vezettük át: admin statisztika, Tuya, Power Wall,
  nyestmozgás, fogyasztási történet, öntözési statisztika. A konstruktorok új,
  opcionális `cached_api_payload` függőséget kapnak; az app minden érintett
  szolgáltatásnak a közös ApiCache-t adja. Enélkül a szolgáltatás cache nélkül
  épít, így régi, kézzel injektált get/set callbackpárból nem keletkezik új race.
- A ContextService invalidátorai a hozzájuk tartozó belső cache-t is törlik,
  rövid memóriaműveletekkel, builder/DB/MQTT-hívás nélkül. A pilot és időjárási
  bemenete egyetlen belső lock alatt invalidálódik. Az API-prefix és a közvetlen
  pilot/snapshot/weather parancs-invalidálás a külső contextet is törli.
  A tartály MQTT-topicja megkapta a meglévő öntözési invalidálási hozzárendelést.
- Az öntözési Context builder közvetlenül `build_snapshot()`-ot használ: nincs
  alatta újabb snapshot-TTL. Az egyetlen olvasási tulajdonos az addigi
  `IRRIGATION_SNAPSHOT_CACHE_TTL` értéket használja, alapból **10 s**. Ez az
  `_context.ttl_sec` tényleges értéke is; korábban a külső 5 s eltakarta a belső
  10 s-t. A klímatörténet, Solar és server-power Context builderből is kikerült
  a külön ApiCache-wrapper. A drága statisztikák cache-e, a pilot/időjárás TTL-je
  és a közvetlen történeti API-k cache-e megmaradt.

A hat payloadépítő teljes számítási ága AST szerint azonos, ha a cache-wrapper
kiemelését leválasztjuk. A négy szolgáltatás **152 SQL-hívásának AST-je változatlan**.
A friss fizikai visszajelzés, nyitás/zárás és scheduler vezérlési metódusai nem
változtak; a vezérlés továbbra is közvetlen MQTT-megfigyelésből dönt.

## Ellenőrzés

**290 különböző teszt sikeres, 0 failure/error/skip**, ebből **24 új cache-teszt**.
Hálózat nélküli, csak olvasható projektmountos konténer, az éles r7 Python-
függőségeivel, külön ideiglenes fájlokkal. A tesztbeli backup/policy folyamatok
szintetikus parancsokat használtak; éles Docker socket, DB vagy broker nem állt
a teszt rendelkezésére. A teljes futtató és moduljegyzék a bizonyítékok között.

- Az öt eredeti versenyben előtte `0 → 0`, javítás után `0 → 1` eredmény;
  a javítás után a következő olvasás is `1`.
- Tizenkét egyidejű kérésből egy builder és tizenegy várakozó; force összevonás,
  lassú/független szekció, hiba és várakozó helyreállása, prefix/all invalidálás,
  explicit set és régi builder versenye, válaszmásolatok, véges invalidálási vihar.
- Valós app-wiringből kiemelt invalidátorokkal MQTT utáni külső/belső frissítés,
  közvetlen parancs-invalidálás, atomi pilot/weather törlés és egyetlen öntözési
  cache-tulajdonos. Context/command/API/scheduler/öntözés/safety/policy regresszió.
- **Tíz szintetikus payloadeset**: a válasz, hideg/meleg SQL-hívásszám, SQL és
  paraméterek ujjlenyomata előtte/utána azonos. Ez korlátos, főként üres adatos
  szerződéspróba; a hat builder számítási ágának AST-egyezése külön bizonyíték.
- Azonos, mesterséges órás TTL-workload: hat kérés a 0/5/9/10/15/20 másodpercben,
  invalidálás nélkül; mindkét verzió három alapbuildet végez a 0/10/20 időpontban.
  Ez nem éles p95-/WAL-mérés vagy általános gyorsulási állítás.
- **Éles változatlanság:** 9 konténer ID/image/indulás/restart és 37 védett hostfájl
  egyezik a kiindulással. Aktív r7, működő DB/MQTT, érvényes AI-offline policy.
  Az eredeti audit, az éles kiadási csomag és az aktív override nem változott.

## Függőségek és bevezetés

Az **F9 nincs teljesen lezárva**. HC-14 marad a GET-ek alatti összesítésírás és
refresh-tulajdonos; HC-40 a szivattyúdiagnosztika tartós írása; HC-21 az AI-
payload és HC-22 a frontend késő válaszainak kezelése. HC-13 alatt marad a
háttérszálak és a lassú builder/I/O teljes határideje. Ezeket nem javítottuk és
nem gyengítettük a fizikai frissességi kapukat. A cache csak egy backendprocesszen
belül koordinál; több Gunicorn worker támogatását ez önmagában nem bizonyítja.

HC-10 ellenőrzéséhez a meglévő stabil domainkód és az izolált payload-/query-
leltár elegendő volt. F9 teljes lezárásához azonos éles jellegű workloadon
p95/query/UPDATE/WAL-mérés, valamint a többi felsorolt pont és frontendpróbák
szükségesek. Most nem volt éles hardver-/böngészőpróba vagy új DB-restore.

Későbbi csomagban együtt szükséges: `read_model_cache.py`, `runtime_utils.py`,
`context_service.py`, `irrigation_service.py`, `command_service.py`, `app.py`,
`admin_service.py`, `power_wall_service.py`, `energy_device_service.py`.
Új függőség vagy migráció nincs. A meglévő r7 csomagot nem módosítottuk;
az új kódot csak új, külön ellenőrzött kiadási csomagban szabad bevezetni.
Rollback: e kódfájlok együtt visszaállítása, vagy későbbi telepítésnél a korábbi
immutable backend-image. Adatbázis-visszatöltés és mérési/auditadat-törlés nem kell.

[Összesített eredmény](audit-evidence/hc10-20261028/summary.json),
[tesztjegyzőkönyv](audit-evidence/hc10-20261028/related-tests.log),
[eredeti reprodukció](audit-evidence/hc10-20261028/baseline-reproduction.json),
[javított reprodukció](audit-evidence/hc10-20261028/fixed-reproduction.json),
[payload/query összevetés](audit-evidence/hc10-20261028/payload-comparison.json),
[számítási ágak](audit-evidence/hc10-20261028/payload-builder-contract.json),
[SQL/vezérlési szerződés](audit-evidence/hc10-20261028/query-and-control-contract.json),
[éles változatlanság](audit-evidence/hc10-20261028/production-unchanged.json),
[forrásdiff](audit-evidence/hc10-20261028/source.diff).
