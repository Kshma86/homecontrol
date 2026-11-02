# HC-20 — Elérhetetlen öntözési végrehajtó kivezetése

2026-11-02, Europe/Budapest. **Ellenőrzött forrásjavítás, nincs élesítve.**
Aktív továbbra is a `hc-security-20261102-r18`. A korábbi HC-15/16 javítás
megmaradt; más auditpont implementációja és státusza nem változott.

## Kiinduló bizonyíték és hatókör

Elolvasva az eredeti HC-20 megállapítás és hivatkozási bizonyítéka, D.1
kivezetési feltétele, F0/F8 előfeltételei, ellenőrzése és rollbackje, valamint
G.5 megőrzendő szezon-/kéziszelep-/stop-authority szabálya. Az eredeti audit
változatlan SHA-256 lenyomata:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.

A jelenlegi forrásban a `start_scheduled_session()`, `run_due_schedules()` és
`stop_due_schedules()` zárt, üzemi hívó nélküli csoportot alkotott. A régi run
hívta a régi startot; az aktív tick már V2-t használt. Az audit óta készült
HC-04 admission-tesztek közvetlenül is hívták a régi startot: ezeket a mostani
állapot alapján kellett igazítani, nem egyszerűen a korábbi audit leltárát követni.

F0: a korábban teljes visszaolvasással és izolált PostgreSQL-visszaállítással
ellenőrzött r18 mentés rendelkezésre állt
(`86b8ed71e4104b3a8eb909ae86e8ea91`). A most lefagyasztott HC-15/16 állapot
**810 kiinduló unit tesztje sikeres**, hiba és kihagyás nélkül. Az eredeti
fájlok, hivatkozások, 185 backend-Python-fájl és 62 SQL-fájl ujjlenyomata a
[HC-20 bizonyítékok](audit-evidence/hc20-20261102/) között szerepel.

## Módosítás

- Az `IrrigationService` három legacy metódusa, összesen 185 definíciós sor
  kikerült. A teljes modul AST-je a három törlést leszámítva azonos; mind a
  **86 megmaradó metódus változatlan**, beleértve a HC-15 session-lookupját,
  a V2 végrehajtót, a manual/safety/recovery és a solar-pump útvonalakat.
- Az elavult tesztbeli legacy run/stop helyettesítések megszűntek. Az admission
  hiba-/timeout-tesztek továbbra is a manual és V2 indításokat védik. A korábbi
  legacy–V2 versenyteszt helyett a tényleges V2 service-hívással ellenőrizzük,
  hogy lezárt session és új service-példány után sincs második napi OPEN.
  A két V2 indító közötti konkurenciatesztek megmaradtak.
- Hat új unit teszt ellenőrzi a navigator eredeti időtartamát, a pilot eltérő
  effektív időtartamát, a pilot miatti kihagyást, a sikertelen start bizonytalan
  állapotát, a fizikai kéziszelep guardot és a stopnaplózás feltételeit.
  Egy további PostgreSQL-teszt a valódi V2 stopkiválasztó SQL-lel bizonyítja,
  hogy a session lejárata a későbbi eredeti ütemezett stop előtt is érvényesül.
- Az öntözési domain-guide az aktív V2 start/stop, tranzakciós foglalás,
  navigator/pilot és effektív stop folyamatát írja le. Nem állítja, hogy a
  törölt végrehajtó fut, vagy hogy V2 navigator-start `navigator_only` naplót ír.

Nincs új eszközparancs, ütemezési szemantikaváltás, DB-migráció vagy történeti
adattörlés. A publikus API-k, history/read felületek, korábbi `scheduler`/`pilot`
sessionök kezelése, stop-authority és a HC-01–04/08 védelmei megmaradtak.

## Ellenőrzés és eredmény

| Ellenőrzés | Eredmény |
|---|---|
| Teljes backend unit suite | 816 sikeres |
| Valódi PostgreSQL, 15 külön eldobható klaszter/modul | 198 sikeres |
| Külön célzott irrigation/admission unit kör | 57 sikeres, átfed a teljes körrel |
| Előtte/utána V2 payload-/SQL-/eredmény-összevetés | 12 forgatókönyvben pontos egyezés |
| Aktív forrás- és kezelt unit/config hivatkozáskeresés | 491 fájl; nincs hivatkozás a törölt metódusokra |
| Öntözési service AST-egyezés | kizárólag a három metódus törlése |
| SQL-migrációk | mind a 62 változatlan |
| Éles változatlanság | 736 runtime-hash és 16 konténer ID/image/futás állapota egyezik |

**1014 különböző végső backendteszt, 0 failure/error/skip.** A 57 célzott teszt
átfedő, nem hozzáadott darabszám. A 12 külön payloadpróba szintetikus I/O-val
az eredeti és új service-példányok reservation inputját, MQTT payloadját,
SQL-jét/paramétereit, végrehajtási és döntési eredményeit, valamint recovery
állapotát hasonlította össze. Külső kapcsolatot, szál-/folyamatindítást és
fájlírást a probe tiltott. Nem állít fizikai eszközminősítést.

A PostgreSQL-kör ellenőrizte az admission versenyeket, napi egyszeri V2
indítást, commit-/rollback-határokat, kiesési/recovery és scheduler-audit
szerződéseket. A teljes unit-kör megtartotta a HC-15 query-counter és app-wiring,
valamint a HC-16 rover/import/auth regresszióit. A korábbi 163 app-route
szerződését ellenőrző teszt is sikeres.

Tényleges végső parancsok:

```bash
python3 -B docs/audit-evidence/hc20-20261102/check_scope.py
python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc20-20261102/unit
python3 -B scripts/check_hc_tests.py --profile postgres --output docs/audit-evidence/hc20-20261102/postgres
```

A tesztek hálózat nélküli konténerekben futottak; a PG-kliensek csak a saját
eldobható adatbázisuk hálózati névterét osztották. Nincs hostport vagy éles
DB/eszközkapcsolat. A standard tesztprofil korábbi backup-fixture-jeihez a
meglévő harness csak az eldobható deployment policy-t teszi opcionálissá;
az éles kötelező policy változatlan. Frontendkód nem módosult; a korábbi HC-16
114 frontendtesztjét és buildjét nem számoltuk mostani tesztként. Fizikai
öntözési próba és éles deploy/restart nem történt.

[Összesítés](audit-evidence/hc20-20261102/summary.json),
[unit](audit-evidence/hc20-20261102/unit/test-summary.json),
[PostgreSQL](audit-evidence/hc20-20261102/postgres/test-summary.json),
[scope és hivatkozások](audit-evidence/hc20-20261102/scope-check.json),
[payload-egyezés](audit-evidence/hc20-20261102/payload-parity.json),
[patch](audit-evidence/hc20-20261102/source.diff),
[éles változatlanság](audit-evidence/hc20-20261102/production-unchanged.json).

## Függőségek, élesítés és rollback

A már meglévő HC-01 friss fizikai visszaigazolás, HC-02 stop-sorrend, HC-03
recovery, HC-04 tranzakciós foglalás, HC-08 V2 auditlánc és szezonprofil-kapuk
megőrzött függőségek; ezekhez nem készült új javítás. A pilot skip meglévő,
a reservation tranzakción kívüli könyvelését sem alakítottuk át.

A következő backendkiadásnak a korábbi, még nem élesített **HC-15, HC-16 és
HC-20** forrásállapotát együtt kell tartalmaznia. A HC-15 `irrigation_service.py`
fájlja szándékosan változott a három régi metódus törlésével; a többi része
AST-azonos. A HC-16 protokollmodulja és kompatibilis importjai megmaradnak.
HC-24/26 és a HC-23/41/43 nyitott részei külön munkák, nem kerültek javításra.
AI-újraaktiválás nem előfeltétel; az AI letiltva marad.

**Élesítés nem történt.** A lezárt r18 csomag/runtime/image változatlan.
Rollbackhez az `original/` és `source.diff` alapján a HC-20 változtatásai
visszavonhatók, a korábbi HC-15/16 megtartásával. Az eredeti service-másolat
már tartalmazza a HC-15 session-lookupját. DB-down-migráció vagy történeti
adat visszaállítása nem szükséges.
