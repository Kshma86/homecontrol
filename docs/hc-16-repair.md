# HC-16 — Egyirányú rover-protokollfüggőségek

2026-11-02, Europe/Budapest. **Ellenőrzött forrásjavítás, nincs élesítve.**
Az aktív kiadás változatlanul `hc-security-20261102-r18`. A korábbi, még nem
élesített HC-15 javítás minden fájlujjlenyomata megmaradt.

## Bizonyíték és hatókör

Elolvasva az eredeti audit HC-16 megállapítása és hivatkozási bizonyítékai,
D.1 kivezetési feltétele, F0/F8 előfeltételei, elfogadása és rollbackje,
valamint G.3–4 megőrzendő rover-/store-szabályai. Az aktuális működéshez a
[2026-10-13-i egykezelős átadás](rover-single-user-control-20261013.md) az irányadó.
Az eredeti audit változatlan SHA-256 lenyomata:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.

Az előállapot teljes backend-importgráfja valóban egy ötmodulos kölcsönös
függőségi csoportot mutatott. Ez szerkezeti csatolás, nem igazolt indulási hiba.
A settings két operator-jelszó/session mezőjét az app nem használta: az app
és a frontend már rögzített egykezelős módot követett. F0 alapja a korábban
visszaállítással ellenőrzött r18 HC/Git/router mentés és izolált PG-restore
(`86b8ed71e4104b3a8eb909ae86e8ea91`), továbbá a most újrafuttatott, sikeres
806 tesztes kiinduló unit-kör.

Csak HC-16 módosult. A közös F8 fázisban szereplő HC-20 legacy öntözéskód,
valamint a többi auditpont implementációja és státusza változatlan maradt.

## Módosítás

- Az új `mower_v3_protocol.py` tartalmazza a 14 közös, tiszta definíciót:
  hibatípusok, JSON-/típus-/azonosító-, identity/state és MOTOR_TEST validáció.
  Egyetlen helyi függősége a változatlan, tiszta `rover_parameters` codec;
  nincs benne hálózat, tárolás, tulajdonlás, időzítés vagy parancsvégrehajtás.
- A service, commands, manual, motor-test és parameters modulok közvetlenül
  ezt használják. Az ötmodulos importkör megszűnt, a függvényen belüli importok
  figyelembevételével is. Az egyirányú transport→manual/commands késleltetett
  importok megmaradtak.
- A régi nyilvános validátor-importútvonalak közvetlen aliasok. A függvények
  és kivételosztályok objektumazonossága megmarad a hívók között; nincs wrapper
  vagy második validációs megvalósítás. A protokollkonstansok változatlanok.
- A `BackendSettings` két használatlan operator-mezője kikerült. A jelenlegi
  app továbbra is `MowerOperatorAuth(superuser=True)` módot használ. A teljes
  auth-modult és az explicit példányosítással használt, tesztelt opcionális
  session-adaptert a D.1 feltételének megfelelően megőriztük. A két korábbi env
  változó nem aktivál külön login-kaput. Privát env-fájlt nem módosítottunk.
- A három érintett rover-guide a tényleges egykezelős wiringot írja le; nem
  kér külön operator-env provisioninget vagy új bejelentkezést. Az origin-
  ellenőrzés, a natív Bearer és a privát tokenfájl betöltése változatlan.

Nincs új eszközparancs, payload-, időzítési vagy ütemezési szemantikaváltás,
DB-migráció vagy firmware-változtatás. A lease/deadman, boot/epoch, sequence,
forráséletkor, single-send/UNKNOWN és tartós firmware/store szabályai megmaradtak.

## Ellenőrzés

| Végső ellenőrzés | Eredmény |
|---|---|
| Teljes backend unit suite | 810 sikeres, ebből 249 roverhez kapcsolódó |
| Valódi PostgreSQL, 15 külön eldobható klaszter/modul | 197 sikeres |
| Frontend szerződéstesztek | 114 sikeres |
| Frontend production build | sikeres, offline cache-ből |
| Importálási sorrendek | mind a 120 permutáció sikeres |
| Aktuális app-origin próbák | 28 idegen/hiányzó originű POST elutasítva, I/O előtt |
| Protokoll- és service-törzsek AST-egyezése | 14 áthelyezett definíció és 5 modultörzs egyezik, importokat leszámítva |
| HC-15 megőrzése | mind a 15 rögzített fájlujjlenyomat változatlan |
| Éles változatlanság | 736 runtime-hash és 16 konténer ID/image/futás állapota egyezik |

**1121 végső teszt, 0 failure/error/skip.** Az import/origin/AST ellenőrzések
és a külön 4 célzott teszt a fenti unit-körrel átfednek, nem hozzáadott darabszámok.
A suite lefedi a normál v3, MOTOR_TEST és HC_BRINGUP olvasást, parancs-/ACK-
szerződést, STOP-elsőbbséget, UNKNOWN utáni GET-only egyeztetést, valódi izolált
WebSocket lease/deadman működést, origin-elutasítást, tokenredakciót, parameter-
és firmware/store tranzakciókat. Az őrzött friss interpreteres app-próba tiltja
az eszköz-/DB-kapcsolatot, szál-/folyamatindítást és fájlírást. A natív teszttoken
nem jelenik meg a settings repr-ben vagy az operator API válaszában.

Tényleges végső parancsok:

```bash
python3 -B docs/audit-evidence/hc16-20261102/check_scope.py
python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc16-20261102/unit-final
python3 -B scripts/check_hc_tests.py --profile postgres --output docs/audit-evidence/hc16-20261102/postgres-final
python3 -B scripts/check_hc_tests.py --profile frontend --output docs/audit-evidence/hc16-20261102/frontend --npm-cache /tmp/hc23-43-20261102/npm-cache
```

A konténerek hálózat nélkül futottak; a PG-kliensek csak a saját eldobható
klaszterük hálózati névterét osztották. Éles hostport, DB vagy rover nem szerepelt
a próbákban. A standard tesztprofil korábbi backup-fixture-jeihez az eddigi
harness csak az eldobható másolat deployment policy-ját teszi opcionálissá;
az éles kötelező policy megmaradt. Fizikai roverpróba nem történt.

Az első célzott próbában a teszt téves parameter-URL-je 404-et adott; a tesztet
a tényleges `/parameters/drafts/<key>` API-ra javítottuk. Az első teljes
unit-kör 11 hibát jelzett a commands modul túl korán törölt `re` importja miatt;
az import visszaállítása után a végső 810 teszt sikeres. Mindkét korábbi log
megmaradt; egyik sem elfogadási bizonyíték. A PG-kört is újrafuttattuk a végső
backendforrással. A frontend forrása a két backend-futás között változatlan volt.

[Összesítés](audit-evidence/hc16-20261102/summary.json),
[unit](audit-evidence/hc16-20261102/unit-final/test-summary.json),
[PostgreSQL](audit-evidence/hc16-20261102/postgres-final/test-summary.json),
[frontend](audit-evidence/hc16-20261102/frontend/test-summary.json),
[scope és importgráf](audit-evidence/hc16-20261102/scope-check.json),
[patch](audit-evidence/hc16-20261102/source.diff),
[éles változatlanság](audit-evidence/hc16-20261102/production-unchanged.json).

## Függőségek, bevezetés és rollback

A korábbi HC-15 munkapéldány-javítás megőrzött függőség a következő kiadás
összeállításakor: a backendforrásban már jelen van, ezért a kiadási scope-nak
mindkét javítást fel kell tüntetnie. Az új protokollmodult az öt importáló
modullal és a settings-szel együtt kell szállítani. Az app, a frontend auth-hook,
a natív tokenbetöltés, a firmware/store modulok és a 052–055 migrációk nem
változtak. Az egyworkeres tulajdonlási korlát megmarad.

HC-20 nem előfeltétele a javításnak, külön munka marad. A HC-23/43 globális
kiadási/függőségi nyitott részeit és a HC-41 ESP MQTT kivételét ez a javítás
nem rendezi. AI-újraaktiválás és fizikai AI-próba nem szükséges hozzá.

**Élesítés nem történt.** Új, ellenőrzött backendkiadás szükséges; a lezárt
r18 csomag-, runtime- és image-állományokat nem módosítottuk. Nincs éles
újraindítás vagy eszközparancs. Forrásoldali rollbackhez az `original/` fájlokat
és a `source.diff` változtatásait együtt kell visszavonni, az új protokollmodult
és teszteket is eltávolítva. A korábbi HC-15 munkát meg kell tartani.
DB-down-migráció vagy történeti adat törlése nem szükséges.
