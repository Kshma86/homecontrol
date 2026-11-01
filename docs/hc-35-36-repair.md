# HC-35/36 — Érvényes hozzárendelés és ventilátorindítás

**Aktuális állapot, 2026-10-31: HC-35/36 éles a közös r10-ben.**
11 érvényes binding változatlan, backend/frontend együtt átadva; a fizikai
ventilátorpróba hátravan. [Éles átadás](../backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md).
Az alábbi előkészítési bejegyzések történeti állapotok.

**Frissítés, 2026-10-31:** a HC-35/36 bekerült a közös HC-41/44 r10 backend/frontend
kiadásba, újraellenőrizve, nincs élesítve. Az átadás/rollback/restore előtti
ventilátorindítás-egyeztetés elkészült. [Közös csomag és bizonyítékok](hc3536-access-combined-20261031.md).
Az alábbi 2026-10-29-i javítási leírás és teszteredmények történeti állapot.

2026-10-29. **Helyben javítva és ellenőrizve; nincs élesítve.**
Elolvasva az eredeti audit két megállapítása, reprodukciós bizonyítéka és F5a.
Az aktív r9 ingest és r8 backend/frontend változatlan.

## HC-35: a tárolt kezelői választás megőrzése

A binding API külön `configuration_state` értéket ad:

| Állapot | Jelentés és kiválasztás |
|---|---|
| `not_configured` | Nincs tárolt sor. A korábbi, ellenőrzött legacy fallback használható. |
| `valid` | Az explicit eszköz és a szerepkörhöz szükséges képesség érvényes. |
| `invalid` | Van explicit sor, de célja hiányzik, inaktív vagy alkalmatlan. Nincs helyettesítő cél. |

Az FK `ON DELETE SET NULL` után megmaradó sor explicit, érvénytelen választás.
Az érvényességhez aktív entity/device, engedélyezett megfelelő metrika és a
szerepkör kizáró feltételei szükségesek. Kapcsolóhoz kapcsolási metrika és
támogatott Zigbee/Tuya platform is kell; elszívóhoz teljesítménymérés is,
a jelzőfényhez Zigbee switch/brightness/color képesség. A kiválasztható jelöltekre
és az induló fallbackre ugyanez az ellenőrzés vonatkozik.

Érvénytelen állapotban a `selected_entity_id` és `selected_entity` null,
`uses_fallback=false`; a `stored_entity_id` és diagnosztikai ok megmarad.
A korábbi implicit pótlást a fogyasztóknál is lezártuk: AI-aljzat, klíma-/HC-
teljesítménymérő, öntözési talajszenzor, klíma-ventilátor és a kezdőlap név alapján
választó helperje. A domain ismeretlen/hiányzó állapotot kap. A kötést nem használó,
régi önálló konstruktorok kezdeti konfigurációs kompatibilitása megmarad.

Az adminfelület jelzi az érvénytelen eszközt, és üres, letiltott placeholdert mutat:
nem jeleníti meg kiválasztottnak a lista első másik eszközét. A kezelő érvényes
jelölt kiválasztásával javíthatja a hozzárendelést. Automatikus eszközcserét,
konfiguráció-átírást vagy riasztásnyugtázást nem végeztünk.

## HC-36: egy sorrend a binding, policy és késleltetés számára

Az app ugyanazt a `ClimateFanCoordinator` példányt adja a binding és PowerWall
service-nek. Sorrend: helyi RLock → külön READ COMMITTED tranzakció →
`pg_advisory_xact_lock(350036, 1)`. A tranzakciós lock külön service-/DB-kapcsolatok
között is véd, transaction-mode PgBouncer mellett is használható; nincs session lock.
A koordinációs SQL lock-timeoutja 2 s, statement-timeoutja 5 s. Lockhiba esetén
a művelet hibával visszatér; nem küld parancsot másik célra.

Bindingcserekor ugyanazon rövid DB-tranzakció újraellenőrzi a jelöltet, visszavonja
a régi cél `auto_climate_on_at` szándékát és auto-climate flagjét, átírja a bindinget,
és engedélyezi az új cél policyjét. A valóban másik célra váltás az új sor esetleges
régi indítását is törli: A→B→A nem támasztja fel az A régi szándékát. Az érvényes,
változatlan cél újbóli mentése megőrzi saját késleltetését.

A klíma ON/OFF, due tick, policyváltás és kézi PowerWall/Tuya kapcsolás ugyanazt
a koordinációt használja, a publikálás végéig. A tick csak az aktuálisan érvényes
cél, engedélyezett policy és sikeresen lefoglalt, lejárt szándék esetén küld ON-t.
Érvénytelen bindingnál nincs policy-alapú másik cél. OFF és kézi kapcsolás törli
az adott cél késleltetését; a Tuya fül kézi útja is. A tick/sync a nem kiválasztott
vagy letiltott célok régi climate-késleltetését visszavonja. Más kézi/ütemezett
feladat tábláját nem üríti, a kiválasztott új cél érvényes saját késleltetése megmarad.

Ha a tick már publikál, a bindingcsere megvárja. Ha a bindingcsere volt előbb,
a tick az új állapotból dönt. Egy befejezett bindingcsere és utána kezelt OFF
után ezért nem jelenhet meg a régi cél ON-ja. A publikálás továbbra is a meglévő
transporteredményt jelenti; nem új fizikai visszaigazolási protokoll.

## Ellenőrzés és bizonyítási határ

- Az eredeti forrás reprodukálta a 11→22 automatikus helyettesítést és az
  A pending → binding B → OFF → tick sorozat B OFF, majd A ON hibáját.
- **386 backend unit-/regressziós teszt sikeres**, 0 hiba/skip. Safety, CO/füst,
  AI/HC-31, öntözés, scheduler és az új binding/fogyasztói esetek is szerepeltek.
- **19 valódi PostgreSQL-integrációs teszt sikeres**, külön belső hálózatú,
  eldobható DB-n. Inaktív/törölt cél, letiltott metrika, fallback, A→B→A, OFF
  előtte/utána, új cél saját késleltetése, policytiltás, új service-példánnyal
  restart-szimuláció, rollback, külön kapcsolatok közti verseny és 2 s lock-timeout.
  A publisher helyettesítő; fizikai kapcsolás nem történt.
- **4 frontend viselkedési teszt és a teljes Vite build sikeres.** A teszt a
  tényleges eszközválasztó helpert bundle-öli, és ellenőrzi a UI-fallback tiltását.
- A csak olvasva leltározott **11 jelenlegi kiválasztott eszköz mind érvényes**
  marad az új ellenőrzéssel; jelenleg egyik szerepkör sem legacy fallbackes.
- **15 rögzített éles konténer, 37 védett hostfájl, aktív r9 override, binding API-
  leltár, safety-forrás és eredeti audit változatlan.** A labor eltávolítva.

Az első tesztindításoknál a konténer-mount mélysége és az ideiglenes fake-parancsok
végrehajthatósága, illetve a hiányos helyi Node-cache környezeti hibát okozott.
A végső eredmények megfelelő könyvtárstruktúrával, végrehajtható teszt-/tmp-vel
és a meglévő teljes frontend tesztcsomagokkal születtek. Alkalmazás-/backupjavítás
nem történt emiatt, csomagfrissítés sem. A hoston nincs npm; a build helyi Node
image-ben, hálózat nélkül futott. A dependency lock változatlan.

Az integráció új service-példányt és külön DB-kapcsolatokat használ; teljes
backend-container/pooler átadás, éles eszközkapcsolás és tartós terhelés most nem
futott. Az éles rendszerhez nem küldtünk parancsot és nem futtattunk migrációt.

## Függőségek, későbbi élesítés és rollback

HC-35/36 együtt adandó át: backend, új koordinátor-modul, app-bekötés és frontend.
Új migráció, env-változó vagy csomagverzió nem kell. A meglévő binding/policy séma
és HC-39 runtime-role marad. HC-31 AI-koordinációja és AI-offline korlátozása
megmaradt; a fizikai AI-próba továbbra is külön hiány. HC-12/32, globális HC-23/43,
HC-41/44 és HC-45 státuszát nem változtattuk.

Későbbi élesítéshez külön fagyasztott backend/frontend kiadás, friss mentés,
binding/policy/pending leltár és a korábbi kép megőrzése szükséges. A régi
backendet le kell állítani az új indítása előtt: régi kód nem vesz részt az új
advisory-lock protokollban. Az induló függő szándékokat aktuális kezelői/klíma-
állapottal egyeztetni kell, nem szabad egy régi ON-t automatikusan újratervezni.

Rollbackkor a korábbi backend/frontend együtt visszatehető, a jelenlegi explicit
azonosítók és policyk mentett állapotának megőrzésével. Előtte a függő indításokat
egyeztetni kell; visszavont ON-t a rollback sem hozhat vissza. A régi kód ismét
elfogadná az érvénytelen binding fallbackjét, ezért azt külön ellenőrizni kell.
Már megtörtént fizikai kapcsolást kód-visszaállítás nem von vissza.

[Bizonyítékok és összesítés](audit-evidence/hc35-36-20261029/summary.json).
