# HC-24 — Korlátos mDNS-kérdésfeldolgozás

2026-11-02, Europe/Budapest. **Ellenőrzött forrásjavítás, nincs élesítve.**
Az aktív kiadás változatlanul `hc-security-20261102-r18`. A korábbi HC-15/16/20
javítások megmaradtak; más auditpont implementációja és státusza nem változott.

## Bizonyíték és hatókör

Elolvasva az eredeti HC-24 megállapítás, a H.1-ben rögzített pointerciklus-
reprodukció, F0 és az érintett F1 lépés. Az eredeti audit változatlan SHA-256:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.
F1-ből itt kizárólag a DNS-parser javítása és szintetikus fixture-ellenőrzése
érintett; a HC-17/18 export-/secret-kezelését nem módosítottuk.

Az eredeti `read_name()` mind a `c000` önhivatkozásnál, mind a `c002c000`
kétpointeres ciklusnál 100 ms után is futott; a most megismételt, hálózatmentes
próbát időzítő szakította meg. A parser importja és az érvényes kiinduló A/ANY
válasz-/announcement fixture-ök előállítása sem hozott létre socketet.
[Kiinduló reprodukció](audit-evidence/hc24-20261102/baseline-parser.json).

F0 alapja a korábban teljes visszaolvasással és izolált PG-restore-ral ellenőrzött
r18 mentés (`86b8ed71e4104b3a8eb909ae86e8ea91`), az aktuális források rögzítése, a korábbi
HC-20 816 unit + 198 PG eredménye és az ebben a körben újrafuttatott teljes unit
suite. Az eredeti fájlok és előállapot a [bizonyítékkönyvtárban](audit-evidence/hc24-20261102/) vannak.

## Módosítás

- A `read_name()` meglátogatott offseteket tart nyilván, ezért az ön-, kétpontos
  és címkén át visszatérő ciklust is elutasítja. Csomagon kívüli offset/pointer,
  csonka pointer/címke, hiányzó névlezárás és fenntartott címketípus `ValueError`.
- A kibontott wire név legfeljebb 255 bájt lehet, a címke felső két bitje rendes
  címkénél nulla, így legfeljebb 63 bájtos. Ezek a
  [DNS-formátum korlátai, RFC 1035 §2.3.4/§3.1/§4.1.4](https://www.rfc-editor.org/rfc/rfc1035.html).
  A külön **128 pointerugrás** helyi erőforráskorlát, nem RFC-hosszkorlát;
  ennél hosszabb, egyébként körmentes láncot is eldob a responder.
- Érvényes tömörített névnél a visszaadott folytatási offset továbbra is az
  eredeti név első pointere utáni pozíció, nem a pointer célja utáni offset.
- A `parse_questions()` ellenőrzi a kérdésszám minimális helyigényét és a név
  utáni type/class négy bájtját. Bármely hibás kérdésnél az egész kérdésszekciót
  eldobja (`[]`), így egy korábbi érvényes kérdésből sem lesz részleges válasz.
  A `should_answer()` emiatt hamis, a fogadóciklus a következő csomaggal folytatja.
- Az új `infra/mdns/tests/test_mdns_responder.py` külön `mdns` tesztprofilban fut,
  a jelenlegi mDNS-image Python-környezetével. A staging már a munkapéldány
  mDNS-forrását és tesztjeit is átveszi; nem marad bent a régi r18 parser.
  A meglévő profilokhoz csak az új profil bekötése és image-azonosító rögzítése
  került hozzá, azok kiválasztási szabályai megmaradtak.

A responderben csak a két parserfüggvény és két korlátkonstans változott.
A válaszépítés, announcement, socketbeállítások, multicast cím/port, TTL,
HC_MDNS konfiguráció és a main ciklus törzse változatlan. Nincs új függőség,
névfeloldó-szolgáltatáscsere, DB-migráció vagy LAN-próba.

## Ellenőrzés és eredmény

| Ellenőrzés | Eredmény |
|---|---|
| Új mDNS-profil a jelenlegi mDNS-image-ben | 19 sikeres teszt |
| Teljes backend unit suite, HC-15/16/20 regressziókkal | 816 sikeres teszt |
| Eredeti pointerciklus-reprodukció | mindkét hibát igazolta, 100 ms időkorláttal |
| Érvényes egyszerű A/ANY válasz és announcement | bájtpontos egyezés a korábbi fixture-rel |
| Fogadóciklus hibás csomagok után | következő jó kérdés megválaszolva, fake sockettel |
| Véletlen és generált parserfixture-ök | 3000 véletlen bájtsorozat + 200 érvényes generált név |
| Scope | 185 backend-Python-fájl és 62 SQL-migráció változatlan |
| Éles változatlanság | 736 runtime-hash és 16 konténer ID/image/futás állapota egyezik |

**835 különböző végső teszt, 0 failure/error/skip.** A random/generált esetek
és a fogadóciklus próbája a 19 parser-teszt részei, nem hozzáadott darabszámok.
A fixture-ök időkorlátot használnak, hogy a pointerciklus regressziója se
akassza meg a tesztfolyamatot. A tesztekben a valódi socketkonstruktor tiltott;
a main próbája kizárólag hamis recv/send műveleteket használ.

Tényleges végső parancsok:

```bash
python3 -B docs/audit-evidence/hc24-20261102/check_scope.py
python3 -B scripts/check_hc_tests.py --profile mdns --output docs/audit-evidence/hc24-20261102/mdns
python3 -B scripts/check_hc_tests.py --profile unit --output docs/audit-evidence/hc24-20261102/unit
```

A konténerek `--network none`, csak olvasó forrásmount és nem root felhasználó
mellett futottak. Az mDNS-profil a deployed policy-t változtatás nélkül használta;
a generic unit-profil csak az eldobható másolatban tartja meg a korábban
dokumentált opcionális backup policy-t. Éles DB/eszközkapcsolat, LAN-csomagküldés,
image- vagy szolgáltatáscsere nem történt. PostgreSQL- és frontendtesztet most
nem futtattunk újra, azok korábbi eredménye nem része a 835-nek.

[Összesítés](audit-evidence/hc24-20261102/summary.json),
[mDNS-tesztek](audit-evidence/hc24-20261102/mdns/test-summary.json),
[unit](audit-evidence/hc24-20261102/unit/test-summary.json),
[scope](audit-evidence/hc24-20261102/scope-check.json),
[patch](audit-evidence/hc24-20261102/source.diff),
[éles változatlanság](audit-evidence/hc24-20261102/production-unchanged.json).

## Függőségek, külön megfigyelés és bevezetés

A HC-24 javításához nem kellett más auditpontot módosítani. A HC-17/18 F1
exportmunkája külön feladat volt, a meglévő exportlista már tartalmazza az
`infra/mdns` könyvtárat. A tesztharness változása kizárólag az új parserprofil
futtatásához szükséges; nem zárja le a HC-23 globális kiadási feladatait.
HC-26 és a HC-23/41/43 nyitott részei változatlanok. Az AI letiltva marad.

Külön megfigyelés, **nem javítva ebben a körben**: az eddigi `build_response()`
többkérdéses csomagnál az összes kérdés bájtját másolja, de a fejlécben
`QDCOUNT=1` marad. Ezt szintetikus, kétkérdéses fixture igazolja; a builder
AST-je megmaradt. Ez külön válaszformátum-felülvizsgálat, nem a HC-24 ciklusfix
előfeltétele. Az érvényes egyszerű kérdés válaszegyezését igazoltuk, általános
DNS/mDNS-megfelelőséget nem állítunk.
[Külön bizonyíték](audit-evidence/hc24-20261102/separate-observation.json).

**Élesítés nem történt.** Új mDNS-image és kontrollált mDNS-kiadás szükséges;
a módosított fájl már a Dockerfile meglévő COPY célja. A HC-24 önállóan
szállítható, nincs runtime-függése a még nem éles HC-15/16/20 backendjavításoktól.
Közös platformkiadásnál ezeket külön a backend scope-jában kell feltüntetni.
A r18 csomag-/runtime-/image-állományokat nem módosítottuk.

Forrásoldali rollback: a parser és három harnessfájl eredeti példánya megvan;
az új teszt és a HC-24 dokumentáció/napló módosításai a patch alapján vonhatók
vissza, a HC-15/16/20 megőrzésével. DB- vagy adatvisszaállítás nem szükséges.
