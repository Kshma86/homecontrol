# A még nem élesített blokk második ellenőrzése

Dátum: 2026-10-23. Hatókör: HC-19/25/30/42 (F6), valamint a vele együtt
bevezetendő HC-07/38/39. Kizárólag ellenőrzés: termékkód-javítás, migráció,
host unit-telepítés és élesítés nem történt.

**Eredeti ellenőrzési eredmény: még nem állítható, hogy csak élesíteni kell.**
Az alábbi két archívumhibát az ellenőrzés után helyben javítottuk
(DC-01/DC-02, AUDIT_REPAIR REPAIR-013). A HC-17/18 exportfüggőség továbbra is
fennáll, és a teljes közös kiadás átadási/visszaállási próbája még hiányzik.
A javítás nincs élesítve; az eredeti reprodukciók lent történeti bizonyítékok.

## Megállapítások

### DC-01 — P2: a belső manifesttel azonos nevű forrásfájl miatt elbukik a mentés

Hely: [backup_protocol.py](../infra/backend/backup_protocol.py), `seal()`
142–143. sor és `verify_archive()` 164–183. sor.

A `seal()` a fájl puszta neve alapján minden könyvtárban kihagyja a
`MANIFEST.txt` és `SHA256SUMS.txt` fájlokat az ellenőrzőösszeg-listából.
A tar ezeket a forrásfájlokat is elteszi, az ellenőrző pedig csak az archívum
gyökerében levő saját `SHA256SUMS.txt`-t kezeli külön. A két fájllista ezért eltér.

Reprodukció a valódi új runnerrel, szintetikus forrásokon: egy
`scripts/MANIFEST.txt`, illetve `scripts/SHA256SUMS.txt` elhelyezése után
exit 1, `local_archive=failed`, nulla kész archívum és
`Incomplete archive or internal checksum mismatch`. Ugyanennek a fixture-nek
a kontrollfutása exit 0 és egy ellenőrzött kész archívum.

Javítási feltétel: csak a saját, gyökérszintű metaadatfájlok maradjanak ki;
a belső könyvtárak azonos nevű, mentendő fájljainak tartalma is legyen ellenőrizve.
Mindkét fájlnévvel tartós regressziópróba szükséges.
**Utóállapot:** a kizárás csak a saját gyökérszintű metaadatokra vonatkozik;
mindkét fájlnév scripts/HA tartalma visszaolvasható, sérülésük elutasított.

### DC-02 — P2: a megőrzött hardlink miatt szintén elbukik a mentés

Hely: [backup_protocol.py](../infra/backend/backup_protocol.py), `seal()`
142. sor és `verify_archive()` 162. sor;
[backup_archive_worker.sh](../scripts/backup_archive_worker.sh), a scripts és
Home Assistant könyvtár `cp -a` másolása, majd a tar létrehozása.

A checksumkészítő mindkét hardlinkútvonalhoz felveszi a tartalom hash-ét.
A `cp -a` megőrzi a közös inode-ot, a GNU tar pedig az egyik útvonalat
hardlink-bejegyzésként tárolja. Az ellenőrző a `member.isfile()` feltétellel
kihagyja ezt a bejegyzést, így hiányzik a várt ellenőrzött fájlhalmazból.

Reprodukció: a szintetikus `scripts/link-a.txt` és annak `os.link()`-kel
létrehozott `link-b.txt` párja mellett a teljes local runner exit 1,
`local_archive=failed`, nulla kész archívum, ugyanazzal a checksumhibával.

Javítási feltétel: a tar készítője és ellenőrzője következetesen kezelje a
hardlinkeket, és a visszaolvasható tartalmat is ellenőrizzük. Tartós
regressziópróba szükséges.
**Utóállapot:** az ellenőrző a már beolvasott, azonos archívumgyökéren belüli
céltartalom hash-ét veszi át a hardlink útvonalához. Hiányzó, idegen gyökerű,
önmagára vagy még nem beolvasott célra mutató linket elutasít; nincs kicsomagolás
vagy visszakeresés a tömörített adatban. A link útvonalának checksumja is kötelező.

E két eset szintetikus ellenpélda; nem állítás arról, hogy a jelenlegi éles
fájlállomány már tartalmaz ilyen fájlokat. A hibák helyesen sikertelenséget
jeleznek, de érvényes forrásállomány mellett megakadályozzák az új mentés
elkészítését. A korábbi sikeres tesztek ezeket az eseteket nem fedték le.

### DC-03 — P1 függőség: HC-17/18 továbbra is rendezendő az éles Git-publikálás előtt

Hely: [export_gitea_config_snapshot.sh](../scripts/export_gitea_config_snapshot.sh),
`copy_path()` és a források listája. Az eredeti audit F6 lépésének előfeltétele F1;
a szükséges rész itt HC-17/18, a HC-24 nem technikai függőség.

Új, kizárólag szintetikus exportpróbában az
`apps/xiaomi-x10/x10_maps/xiaomi_cloud_auth.json.bak` tesztjelölője bekerült
a snapshotba, miközben az `infra/db`, `infra/proxy`, `infra/mqtt/config` és
`infra/mdns` tesztfájljai kimaradtak. Ez a meglévő auditmegállapítás megerősítése;
valódi hitelesítési adatot nem olvastunk ki, Git-push nem történt.

A jelenlegi backupbeállításban `git_enabled=true` és
`git_offsite_enabled=true`, tehát ez a tervezett működésnél releváns függőség.
Külön javítandó, nem lett automatikusan a jelen review részeként megoldva.

### DC-04 — P1 bevezetési hiány: nincs a teljes blokkra próbált kiadás és rollback

A kiadási könyvtárban jelenleg az r1 és r2 csomag van. A helyi F6 telepítő
unit-visszaállításának fake-manager tesztje és az egyes DB-migrációk laborpróbája
rendelkezésre áll, de nem helyettesíti a közös kiadás átadását és rollbackjét.

Bevezetés előtt szükséges a pontos image-ekkel, privát env/override-dal és host
forrásokkal fagyasztott közös csomag, majd elkülönített átadási/visszaállási próba:

- Meglévő DB-n a szükséges 059/060/061, app/reader role és ACL, majd a
  PgBouncer/backend/ingest összehangolt átadása. A HC-38 baseline csak új,
  üres DB-re való; az éles meglévő DB-re nem alkalmazandó.
- A backend/frontend és a host runner/request path együttes átadása,
  a két redundáns user timer letiltásával és az eredmény ellenőrzésével.
- Rollback alatt is megőrzött SQL Lab reader-határ vagy mindhárom Lab API-út
  lezárása, továbbá közös mentési lock és következetes archívumolvasás.
  A régi r2 önmagában visszahozná a közös admin Lab-kapcsolatot és a külön
  webes mentésvégrehajtót; a régi bootstrap konfigurációt is átírhat.
- Konfiguráció, safety latch/ACK és adatok megmaradásának ellenőrzése;
  automatikus ACK vagy destruktív down-migráció nélkül.

Ezek ismert, már dokumentált bevezetési feltételek, nem új működési hibák.
A részletek a [HC-39](hc39-database-roles.md),
[HC-07](hc07-schema-migrations.md) és [F6](hc-f6-backups.md) leírásban vannak.

## Ellenőrzési eredmények és határok

| Ellenőrzés | Eredmény |
|---|---|
| Korábbi F6 lezáráshoz rögzített 207 forrásfájl SHA-256 összevetése | 207 egyezik, eltérés nincs |
| HC-07, HC-38 és HC-39 SQL/seed/katalógus manifestjei | Mind a 6 fájl checksumja egyezik |
| Friss célzott backend backup-tesztek | 41 sikeres, 0 hiba |
| Friss frontendtesztek | 83 mower + 4 AI + 6 backup = 93 sikeres, 0 hiba |
| Friss frontend production build | Sikeres, elkülönített ideiglenes könyvtárban |
| 5 új shell worker `bash -n` | Sikeres |
| F6 installer alapértelmezett terv | Sikeres, `applied=false`; tényleges telepítés nem futott |
| Új teljes-runner ellenpróbák | Kontroll sikeres; a két fájlnév és a hardlink esete reprodukált hiba |
| Új szintetikus exportpróba | A HC-17/18 függőség megerősítve |
| 14 telepített host unit SHA-256 összevetése | Eltérés nincs |
| Éles konténerek, image-ek és health | Mind a 6 konténer azonos ID-val/indulással/restart-számmal; a három app image pontosan r2; DB/MQTT health rendben |
| Éles root/user backup és logtimerek | A korábbi állapot megmaradt; a duplikáció éles megszüntetése még nem történt meg |
| Eredeti audit SHA-256 | Változatlan |

A korábbi 667 backendteszt, 13 ingest/PG teszt, a teljes DB-visszaállítás,
52 táblaszámláló/17 üzleti tábla pontos egyezése és a helyi Git/restic próbák
bizonyítékait áttekintettük; a teljes PG-integrációs kört most nem futtattuk újra.
A friss célzott próbák az ezekből kimaradt archívumeseteket mutatták ki.
A frontend első próbája minimál Node-image-ben hiányzó `esbuild` miatt nem volt
teljes értékű; a meglévő build-image függőségeivel az összes teszt és build sikeres.

Privát bizonyítékok: `/tmp/hc-block-double-check/` — `probe.py`, `probes.json`,
`fingerprint-and-seal.json`, `backup-tests.log`, `frontend-tests.log`,
`frontend-first-attempt.log`, `install-plan.json`, `installed-units.json`,
`live-readonly.json`. A tesztkonténer automatikusan törlődött; éles művelet
nem történt. Más auditpont javítása sem történt.

## DC-01/DC-02 javításának ellenőrzése

2026-10-23, helyi javítás, élesítés nélkül:

- A két új teljes-runner regresszió a régi kódon egyaránt hibázott (2/2).
- Javítás után **46 mentési teszt sikeres**, 0 hiba/kihagyás. Az 5 új teszt a
  belső manifestnevek megőrzését és sérülését, valódi GNU tar hardlinkbejegyzés
  visszaolvasását, hibás céltartalom checksumját és érvénytelen linkcélokat fedi le.
- Az eredeti kontroll, belső manifest, belső checksum és hardlink ellenpróbák
  mind exit 0 / completed / egy ellenőrzött archívum eredménnyel futnak.
- A korábbi, DB-restore-ral igazolt **109 596 668 bájtos** archívum és régi nevű
  példánya is ellenőrzött: 15 fájl, az eredeti receipttel azonos teljes SHA-256.
  Új DB-restore ebben a kis javításban nem futott.
- A 14 telepített unit és minden más korábban leltározott termékforrás változatlan;
  termékkódból csak a protokollmodul és annak tesztfájlja változott. A frontend és
  DB-kód változatlan, az előző review 93 frontendteszt/build eredménye előzmény.

Javítási bizonyíték: `/tmp/hc-dc-repair/` — `regressions-before.log`,
`backup-tests.log`, `probes.json`, `existing-archive-verification.json`,
előállapot és diffek. DC-03/DC-04 továbbra is nyitott bevezetési feltétel.
