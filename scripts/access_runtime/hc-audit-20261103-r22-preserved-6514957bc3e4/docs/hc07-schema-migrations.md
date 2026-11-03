# HC-07: explicit migráció, induláskori ellenőrzés

Ez a helyi HC-07 forrásjavítás szerződése. **Még nincs élesítve**; a jelenlegi
`hc-sleeping-20261023-r2` az r1-re épülő, kizárólag HC-06 kiegészítésű kiadás;
a HC-07 ebbe sem került bele. Az új forrás telepítése
külön migrációs és szolgáltatásváltási művelet.

## Mi változott?

A pilot, scheduler, szezonprofil és jegyzet bootstrapje csak olvasva ellenőrzi
a naplózott séma verzióját/checksumját, a szükséges oszlopokat és típusokat,
a konfigurációs sorokat, illetve a scheduler idempotenciaindexét.
Hiba esetén nem javít, nem seedel és nem vált működési módot. A teljes indulási
bootstrap a workerek indítása előtt fut; inkompatibilis DB-n az indulás megáll.

- `059_hc07_startup_schema.sql`: a korábbi, érintett lazy DDL verziózott
  változata. Nem aktivál inventoryt, nem ír át scheduler-módot és nem másol vagy
  töröl történeti klímaszabályokat. A régi módértékeket a DB megőrzi; az új
  alkalmazás az öt támogatott V2 mód valamelyikét követeli meg. Régi/shadow módnál
  explicit kezelői döntés kell, automatikus `v2_execute_all` váltás nincs.
- `060_hc07_legacy_data.sql`: egyszeri, explicit reprezentációváltás. A régi
  szezonális `control_enabled` értékből csak a hiányzó capability értékeket
  tölti ki, a meglevő egyedi választásokat és aktív profilt megőrzi. A teljes
  capability-modelllel rendelkező profilokat nem frissíti. Csak a hiányzó/üres
  jegyzetstátuszt pótolja; a szándékos `done=true,status=open` állapotot megőrzi.
- `seeds/hc07_initial.sql`: külön kérhető, egyszer naplózott kezdeti adatok.
  Inventoryn csak `ON CONFLICT DO NOTHING`; létező entitásazonosságot nem cserél.
  A meglévő telepítéseken a runner visszautasítja az első seedet. Egy már
  naplózott seed újbóli kérése sem támaszt fel később törölt alapértelmezéseket.

A `hc.startup_schema_migration` táblában verzió, SHA-256, időpont és DB-role
szerepel. A runner allowlistet használ, kizárólag az 059/060 és az opcionális
kezdeti seed fájlokat ismeri. Nem futtatja végig a régi `001–058` fájlokat.
A `042` `CONCURRENTLY` művelete külön operatív feladat marad; ez a runner nem
támogat nem tranzakciós migrációt. Az összes kiválasztott SQL és naplóbejegyzés
egy tranzakció, tranzakciós advisory lockkal, 5 s lock- és 60 s statement-timeouttal.
Megszakításkor a teljes köteg visszagörgethető, újrafuttatáskor az elkészült
verziók kimaradnak. Eltérő checksum vagy ismeretlen naplózott verzió megállítja
a futást; a journal kézi átírása nem megoldás.

Az 059/060 SQL-fájlok puszta, kézi `psql` futtatása nem elegendő: a kompatibilitási
ellenőrzéshez a runner által rögzített checksum-napló is szükséges.

## Meglévő DB upgrade-je

A migrátor nem importálja az `app`/`wsgi` modulokat, nem indít workert és nem
publikál MQTT-re. A parancsok új forrást és psycopg 3-at tartalmazó, elkülönített
migrációs folyamatot feltételeznek. Konténerben csak a backendforrás, az SQL-
könyvtár és a szükséges DB-kapcsolat kell; Docker-socket, aktuátorhálózat és
backend worker nem szükséges. A hitelesítést privát környezeti változóban kell
átadni, nem parancssori URL-ben vagy naplóban.

```bash
python3 infra/backend/migrate_hc07.py --plan
python3 infra/backend/migrate_hc07.py --apply
```

Alapértelmezésben a `--plan` működik: read-only tranzakció, nincs journal- vagy
sémalétrehozás. A `DATABASE_URL` a megfelelő migrációs szerepkör kapcsolata.
Konténerben a csatolt SQL-út megadható `--sql-dir /migrations` argumentummal.
Sikeres migráció után az új backend deploy következhet; ezt a javítási munka
nem hajtja végre. Az új és a régi író/workerek ne fussanak párhuzamosan.

A kimeneti `ready` csak sémakompatibilitás, nem eszköz-/telemetria-egészség.
0: kompatibilis; 2: tervben még van migráció vagy hiányzik/inkompatibilis a
konfiguráció; 1: migrációs/kapcsolati/checksum hiba. Az `--apply` mellett kapott
`ready=false` jelentheti azt, hogy a séma commitolt, de például egy legacy mód
vagy hiányzó konfiguráció miatt az alkalmazás még nem indítható. Ezt a kimenet
külön felsorolja. A puszta exitkód nem bizonyítja, hogy semmi sem commitolt.

A megtartott `legacy`, `v2_shadow`, `v2_plan_only`, `unified_shadow` módoknál
előbb át kell nézni a kívánt parancstulajdonlást és feature flag-eket, majd
explicit módot választani. A jelenlegi támogatott választások:
`v2_execute_irrigation`, `v2_execute_x10`, `v2_execute_climate`,
`v2_execute_x10_climate`, `v2_execute_all`. A migráció egyiket sem választja
ki helyetted. Az aktív szezon, egyedi ütemezések és a történeti szabályok
változatlanok maradnak; a régi klímaszabályok konszolidálása külön adatdöntés.

## Friss érintett domain / restore

Friss, **már létező kompatibilis core sémán**, üres HC-07 domainkonfigurációval:

```bash
python3 infra/backend/migrate_hc07.py --apply --seed-initial
```

Ez hozza létre a korábbi kezdeti pilot/scheduler/szezonadatokat és hét tiltott
klímaszabályt. A kezdeti scheduler-mód a korábbi default `v2_execute_all`;
éles engedélyezés előtt a feature flag-eket és szezonprofilt kezelőileg ellenőrizni
kell. Meglévő telepítéshez **nem** szabad `--seed-initial` kapcsolót használni;
hiányzó konfigurációt a kiválasztott mentésből vagy külön felülvizsgált művelettel
kell helyreállítani. A startup nem tölti vissza önkényesen a hiányzó sorokat.

Régi teljes DB-mentés helyreállításakor sorrend: sikeres teljes restore →
szükséges korábbi, célzott migrációk (például a HC-06 058-a, ha hiányzik) →
HC-07 `--plan`/`--apply` → konfiguráció áttekintése → új backend indítása.
Egy folyamatban lévő vagy hibás restore-ra nem szabad migrációt indítani.
A meglévő általános restore launcher nem futtatja automatikusan ezt a parancsot:
az új backenddel történő restore-átadásba ezt az explicit lépést be kell venni.

**HC-38 / F7 frissítés:** azóta elkészült a külön
[HC-38 alapséma és üres-DB telepítési út](hc38-database-baseline.md).
Új DB-n előbb annak baseline-ja és explicit 058 runtime inicializálása kell,
utána ez az 059/060 runner és a külön kérhető kezdeti domainseed. Meglévő DB-n
továbbra is dump/upgrade út van, baseline apply nélkül. A HC-07 runner maga
hiányzó `hc.device/entity/metric/entity_metric` esetén írás nélkül megáll;
nem hoz létre core sémát. A teljes új VM telepítése külön operatív feladat marad.

## Hatókör és rollback

Az érintett indulási adatátírások megszűntek. Más lazy, kizárólag DDL-t futtató
bootstrapok (például power-wall, binding, összesítőtáblák) ebben a javításban
megmaradtak a HC-07-ben. A későbbi [HC-39](hc39-database-roles.md) ezeket is
explicit 061 migrációba tette, külön app/reader role-lal és runtime sémaellenőrzéssel.
Ez is csak helyben ellenőrzött. A scheduler audit/publish út (HC-08) és egyéb
auditpontok változatlanok.

Nincs destruktív down-migráció; a journal és adatok megőrzendők. A korábbi
`r1` backend visszaindítása a régi bootstrapet is visszahozná, ami a kézzel
módosított inventoryt/schedule-t újra átírhatja. HC-07 utáni kiadás rollbackjéhez
is megőrzött üzleti snapshot és a kompatibilitás felülvizsgálata szükséges;
egy teljes DB-visszaállítás nem automatikus kódrollback. A HC-07 továbbra sincs élesítve. Időközben az r1-re épülő célzott HC-06
kiegészítés r2 néven éles lett; annak külön visszaállását a DEPLOYMENT_PREP.md
írja le. Ez nem oldja fel a HC-07 utáni kódrollback korlátait.

## Ellenőrzés

A tartós regressziók: `tests/test_schema_service.py`,
`tests/test_scheduler_service.py`, `tests/test_startup_schema_postgres.py`.
A SQL-kör explicit opt-in: `HC07_TEST_POSTGRES=1`,
`HC07_TEST_DATABASE_URL=postgresql://...@127.0.0.1/hc07_schema_test`.
Kizárólag ezt a dedikált, eldobható DB-t fogadja el, a saját `hc` sémáját törli.
Éles vagy restore-DB-re nem futtatható. A tényleges futások eredményeit és
bizonyítási határait az `AUDIT_REPAIR.md` HC-07 bejegyzése tartalmazza.
