# Audit záró kiadás – r19, 2026-11-02

**Kiadás: `hc-audit-20261102-r19`. Élesítés előtti csomag; aktív továbbra is r18.**
A felhasználó engedélyezte az összes elkészült javítás élesítését és a jelenlegi
javítási kör lezárását. A host `sudo -n` ellenőrzése jelszót kér; a jelszót csak
helyi terminálban kell megadni. Nem használunk Docker-konténert host root-jog
vagy védett titkok elérésének megkerülésére.

A csomag a lezárt r18-ból és az ellenőrzött javítások 50 fájlos listájából épül.
34 kód-/tesztfájl, továbbá az érintett dokumentumok és inaktív AI-node image-pinek
kerülnek át. A munkakönyvtár más eltéréseit nem szállítjuk; különösen a kanonikus
backup-runner és a friss hosthoz már javított F6-telepítő r18 változata megmarad.

| Terület | Az r19 változtatása |
|---|---|
| HC-15/16/20 | Egy backend-image: közvetlen DB service, egyirányú rover-protokoll, a három elérhetetlen legacy öntözési metódus eltávolítása. Új DB-migráció nincs. |
| HC-24 | Új mDNS-image a korlátos DNS-parserrel. |
| HC-26 | Új Growatt-poller image, egy batch HA GET, külön állapotkor és megfigyelési idő. |
| HC-23 | JSON Compose recovery-kompatibilitás a lezárt runtime-ban és Git-exportban, új verziózott host/recovery-források. A letiltott AI-node három immutable pinje csak inaktív konfiguráció. |
| Platform | A PostgreSQL, HA, MQTT, proxy, frontend, ingest, Tuya/Gree/X10 és a többi image megmarad. A 13 egyéb konténerazonosítót megőrizzük; ebben a korábban leállított Adminer is szerepel. |

A három új image a jelenlegi, pontos image-ID-jű alapokra épül. Telepített
Python-csomag és runtime-konfiguráció nem változik; nincs apt/pip frissítés.
Az actual baked kód, a csomaglista, a mandatory AI-policy és a Docker indítási
szerződés ellenőrzött. A 19 image-es offline készlet az aktuális platformot és
a három előző image-et tartalmazza az r18 rollbackhez; tényleges Docker-load sikeres.

**Ellenőrzések:** 1308 külön regressziós eset és frontend build sikeres; további
16 alaptelepítő-, 12 router-tranzakciós és 13 audit-aktiváló/utóellenőrzési és tesztfuttató eset
sikeres (41 eset). A régi csomagból hiányzó bridge/ingest/X10 teszt-fixture-ök miatt
az első futás három profilja nulla teszttel megállt; ezek megmaradtak történeti
kísérletként, majd a teszttámogatás pótlása után mindhárom profil sikeres volt. A hét meglévő health-route tesztet is a csomaghoz adtuk, majd a teljes unit-profilt újrafuttattuk.
A szállított alkalmazáskód e javítás során nem változott. A közös tesztsegédek
bájtra egyeznek a már vendored futó kóddal.

A backend és Growatt tényleges, beépített processze network=none mellett elindul;
liveness jó, hiányzó DB/MQTT/HA mellett readiness hibás, a processz életben marad.
Éles DB/HA/eszközmódosítás, MQTT-publish és konténer-átállítás eddig nem történt.
Az új pontos r19 snapshotból teljes bare-metal VM-restore még nem futott; az r18
és ugyanazon recovery-javítás friss/ismételt/FTP-kiesési/reboot bizonyítékát
változatlan néven őrizzük, nem címkézzük át r19-próbává.

## Élesítési kapuk és helyi parancs

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r19/source/scripts/audit_release/activate.py
```

A parancs a teljes seal/source/image/hash ellenőrzés, a változatlan baseline,
nyugalmi robot/öntözés és a meglévő lockok vizsgálata után indul. Hitelesített HA
API/Growatt-entitás és PG16/kolláció előpróba, titkosított router-probe és teljes
repository-check, új ellenőrzött helyi mentés előzi meg a váltást. A backend,
mDNS és Growatt, valamint a hostops/root runtime átállítása történik; HA és PG
leállítás/adatmigráció nincs. A hibás átadás visszagörgethető r18-ra.

Az éles váltás után friss HC/Git/router mentés, SHA-256 visszaolvasás és izolált
PostgreSQL-restore kötelező. Az öt timer csak a sikeres mentési átvétel után
áll vissza. Runtime-hashek, komponensek, AI/router-policy és timerek záróellenőrzése
után a program létrehozza a `docs/audit-final-20261102.md` élő átadási nyugtát,
és bejegyzést tesz az audit- és kiadási nyilvántartás elejére. Egy sikeres
aktiválást nem futtatunk újra.

Hiba esetén a `deployment-status.json`, `private/progress.json` és
`private/audit-error.json` alapján kell meghatározni az állapotot. Privát napló
nem megosztható; a jelszó nem kerül a chatbe. Szükség esetén ugyanaz a parancs
`rollback` argumentummal használható; későbbi kiadásról a guard elutasítja.

## Az audit lezárásának pontos jelentése

**46 Ellenőrzött, HC-41 és HC-43 továbbra is Folyamatban.** A jelenlegi javítási
kör sikeres éles átadása lezárható; nem állítjuk, hogy mind a 48 megállapítás
javított. HC-41 az ESP MQTT-jelszó migrációja miatt marad meg. HC-43 a felhasználó
kifejezett döntése szerint támogatott gyártói javításig marad folyamatban:
98 HA Python-találati rekord/67 aliascsoport és 122 nem eldöntött rekord, továbbá
a korábban dokumentált Debian SSH/XML maradványtalálatok. A csomagverziók nem
változtak; ez nem új tiszta sérülékenységi scan. Az AI letiltva marad.

A korábbi labor tárhelyincidense és a sikeres méretkorlátos próba változatlanul
megőrzött. Az éles kiadás elkészítése során új KVM-labort nem indítottunk.
A lezárt r18 csomagot, runtime-ot, eredeti auditot és korábbi bizonyítékokat
nem írjuk át. Bizonyíték: `backups/releases/hc-audit-20261102-r19/evidence/`.

Az átadás előtt két, még nem publikált seal visszavonása és eredeti nyugtája
megőrzött. A tesztfuttató a shellnek is továbbadja a profil kilépési kódját;
két új próba ellenőrzi. Egy túl széles dokumentációs szövegcsere után az eredeti
auditnyilvántartást visszaállítottuk, és csak az új tesztdarabszámot frissítettük.
A runtime image-ek és az alkalmazáskód egyik esetben sem változott.
