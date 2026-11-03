# HC-26 — Mért, közös HA Growatt-lekérés

2026-11-02, Europe/Budapest. **Ellenőrzött forrásjavítás, nincs élesítve.**
Az aktív kiadás `hc-security-20261102-r18`; a korábbi HC-15/16/20/24 javítások
megmaradtak. Más auditpont implementációja és státusza nem változott.

## Bizonyíték, használat és F10 döntés

Elolvasva HC-26 és forrásbizonyítékai, F0, F10 és annak F2 hibahatár-
előfeltétele. Az eredeti audit változatlan SHA-256 lenyomata:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.
F0 alapja az r18 ellenőrzött HC/Git/router mentése és izolált PG-restore-ja
(`86b8ed71e4104b3a8eb909ae86e8ea91`), a korábbi tesztbizonyítékok megőrzése és
az újrafuttatott regresszió. A poller kizárólag telemetriát olvas, inverter-
parancsot nem ad; más bridge-ek stop-/parancsfolyamát nem módosítottuk.

Az opcionális `ha-growatt` profil **ténylegesen fut**, 27 metrikát/entitást
konfigurál. A HA példány a méréskor 86 állapotobjektumot adott vissza. A futó
poller saját HA-hozzáférésével, csak GET-ekkel, három körben, váltott sorrendben
mértük a két útvonalat, ugyanazzal a perzisztens HTTP sessionnel:

| Útvonal | Kérések/kör | Medián | Első kör válaszmérete |
|---|---:|---:|---:|
| Eredeti, entitásonkénti GET | 27 | 29,755 ms | 11 976 bájt |
| Közös `GET /api/states` | 1 | 2,524 ms | 38 037 bájt |

Mindhárom batch válaszban megvolt a 27 konfigurált entitás. Ez az adott, kis
HA-példányon mért indok a batch használatára: kevesebb kérés és rövidebb olvasás,
kb. 3,2-szeres, de kisméretű választesttel. A normál eredeti kör is gyors volt;
a mérés nem állít éles 60 másodperces hibát vagy általános HA-teljesítménygaranciát.
[Használati bizonyíték](audit-evidence/hc26-20261102/usage.json),
[nyers állapotok nélküli mérések](audit-evidence/hc26-20261102/live-measurement.json).

A [HA REST API](https://contributors.home-assistant.io/core/internals/rest-api/#get-apistates)
közös listás állapotvégpontját használjuk; nem új szolgáltatást vagy
függőséget vezettünk be. A hozzáférési tokent, nyers állapotokat vagy más
entitások adatait nem exportáltuk. MQTT publish/HA-módosítás nem történt.

## Módosítás és megőrzött szerződés

- Ciklusonként egy batch GET, utána helyi szűrés a változatlan entity map szerint.
  Nincs entitásonkénti hálózati ciklus vagy hibánál N kéréses fallback. A HTTP-
  válasz context managerben lezárul, hibás JSON/body esetén is.
- Hiányzó vagy `unknown`/`unavailable` entitás kimarad; a válasz többi használható
  entitása megmarad. Teljes HTTP/JSON/body-hiba üres ciklust ad (`entity_count=0`,
  `meta={}`), régi értékek visszajátszása nélkül. A következő kör friss GET-et indít.
- A metrikanevek, értékkonverzió, topic, QoS/retain és a meglévő `source`,
  `entity_count`, `meta` mezők kompatibilisek. A négy régi metaadatmező megmaradt:
  `entity_id`, `unit`, `friendly_name`, `last_updated`.
- `sample_time` a batch kiolvasása **utáni** UTC megfigyelési idő. Két additív
  mező: `meta[key].observed_at` és `meta[key].ha_state_age_seconds`. Utóbbi a HA
  `last_updated` kora; hibás/hiányzó/naiv/jövőbeli timestampnél null. Nem állítja
  az inverter fizikai mintájának korát. Változatlan állapot kora nőhet egészséges
  forrásnál is; nem vezettünk be új stale-küszöböt vagy automatikus értéktörlést.
- A meglévő SQL 019 `meta` JSON-state metrika és a változatlan ingest generikus
  útvonala tárolja az új metaadatot. Nem kell DB-migráció vagy új ingestkód.
  Kimaradó metrika nem törli a korábbi DB-értéket, csak nem ad új mintát.
- A ciklusidő/sleep monoton órát használ, az alapértelmezett időköz 60 másodperc.
  Túlcsordulás után az eddigi legalább egy másodperces várakozás megmarad.
  Worker-health allowance már egy kérésből számol; nem az entitásszám szorzójából.
  A health reporter, MQTT-auth és availability/reconnect viselkedése megmaradt.

A HTTP connect/read timeout nem kemény teljes ciklushatáridő: ezt a
[Requests dokumentációja](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts)
is különválasztja. A javítás az entitásszámnyi soros várakozás szorzóját szünteti
meg; nem ígér szigorú 15/60 másodperces wall-clock korlátot lassan csorgó válasz,
DNS vagy több connect-próba esetére. A health-státusz észleli az elakadást, nem
szakítja meg a socketet. Kemény transporthatáridő külön döntés, ebben a javításban
nem rendeztünk további életciklus-/transport-auditfeladatot.

## Ellenőrzés

| Végső profil | Eredmény |
|---|---|
| Growatt, a tényleges poller-image Python-környezetében | 18 sikeres |
| Teljes backend unit suite | 816 sikeres |
| Korábbi HC-24 mDNS-profil | 19 sikeres |
| Ingest regresszió | 52 sikeres |

**905 különböző végső teszt, 0 failure/error/skip.** A tesztazonosítókat a
profilok között is egyeztettük; az ingest ID-k a unittest-logból ellenőrizhetők.
A tesztkonténerek hálózat nélkül futottak, tiltott valódi HA/MQTT klienssel a
Growatt-próbákban. Egyetlen request/27 metrika, hiányzó/ismeretlen állapot,
HTTP-/JSON-/részleges body-timeout, következő körös helyreállás, aliasok,
forráskor, hibás/jövőbeli timestamp, monoton sleep, health és shutdown ellenőrizve.

Négy további szintetikus forgatókönyvben az eredeti main-loop AST-jével
összevetve a régi MQTT mezők pontosan egyeznek, az új két metaadatmezőt
leszámítva. A tényleges ingest-mapper és a meglévő JSON-meta útvonal is ellenőrzött.
Az első Growatt-tesztkör egy hiányos datetime-mock miatt hibázott; a fixture-ben
pótolt `fromisoformat` után mind a 18 teszt sikeres. A korábbi log megmaradt,
nem része a sikeres elfogadásnak.

A jelölt függvényeinek külön, **csak olvasó éles HA-próbája** egyetlen GET-ből
26 használható metrikát épített a 27 konfiguráltból, 26 kor-/timestampmezővel.
Ez nem élesítés és nem MQTT-küldés: a jelölt függvény külön rövid életű
folyamatban futott, a futó poller folyamata/kódja változatlan maradt.
[Csak olvasó candidate-próba](audit-evidence/hc26-20261102/live-candidate-smoke.json).

Tényleges végső parancsok:

```bash
python3 -B docs/audit-evidence/hc26-20261102/check_scope.py
python3 -B scripts/check_hc_tests.py --profile growatt --output docs/audit-evidence/hc26-20261102/growatt-final
python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc26-20261102/unit
python3 -B scripts/check_hc_tests.py --profile mdns --output docs/audit-evidence/hc26-20261102/mdns
python3 -B scripts/check_hc_tests.py --profile ingest --output docs/audit-evidence/hc26-20261102/ingest
```

A Growatt/mDNS-profil deployed policy-val, a generic backend unit a korábban
igazolt, csak eldobható standard policy-val futott. A korábbi PG-/frontendteszteket
nem futtattuk újra és nem számoltuk hozzá. Inverterparancs, éles DB-lekérdezés,
MQTT publish, HA-állapotmódosítás, deploy vagy restart nem történt.

[Összesítés](audit-evidence/hc26-20261102/summary.json),
[Growatt](audit-evidence/hc26-20261102/growatt-final/test-summary.json),
[scope](audit-evidence/hc26-20261102/scope-check.json),
[payload-egyezés](audit-evidence/hc26-20261102/payload-compatibility.json),
[patch](audit-evidence/hc26-20261102/source.diff),
[éles változatlanság](audit-evidence/hc26-20261102/production-unchanged.json).

## Függőségek, élesítés és rollback

**Élesítés nem történt.** Új Growatt-poller image és kontrollált kiadás kell.
A Dockerfile már másolja a módosított scriptet; a dependency lock, HA-verzió,
MQTT credential-/worker-health fájl, Compose-profile és entity map változatlan.
A HC-26 önállóan szállítható a még nem éles HC-15/16/20 backend- és HC-24 mDNS-
javításoktól. Közös platformkiadásnál azok scope-ját külön fel kell tüntetni.

A tesztharness csak az új `growatt` profil bekötéséhez módosult; a staging ezt
a forráskönyvtárat már korábban kezelte. A HC-23/41/43 folyamatban marad; nincs
új függőségfrissítés vagy más auditpont automatikus javítása. Az AI letiltva marad.
A nyers MQTT/DB `meta` információt a fogyasztó értelmezheti; frontend-forráskor-
megjelenítést vagy fizikai frissességi garanciát ez a pollerjavítás nem vezet be.

A 185 backend-Python-fájl és 62 migráció változatlan; korábbi bizonyítékok
sértetlenek. A végső csak olvasó ellenőrzés 736 változatlan runtime-hasht és
mind a 16 konténer változatlan ID/image/futás állapotát igazolta.
Rollbackhez az eredeti poller/harness/guide fájlok és patch rendelkezésre állnak,
a korábbi javításokat megtartva; DB- vagy adatvisszaállítás nem szükséges.
