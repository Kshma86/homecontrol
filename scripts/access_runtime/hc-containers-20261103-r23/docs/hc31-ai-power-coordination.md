# HC-31 — AI-kikapcsolás és mentés közös koordinációja

Állapot: **helyben ellenőrzött, nincs élesítve**, 2026-10-25.
Audit: HC-31 bizonyítékok és F6b; F0 részeként az aktuális r3 kiadás,
a locktulajdonosok és az eredeti host scriptek leltára ellenőrizve.

## Működési szerződés

- Egy backend workerben egy szándékkezelő szál és legfeljebb egy aktuális
  leállítási szándék van. Új kérés lecseréli a korábbit.
- A szándék rögzíti az aljzat entity-, topic-, platform- és device-azonosságát,
  a generációját és érvényességét. Végrehajtás előtt mindet ellenőrizzük.
- Ébresztés, új F6 feladat, AI-aljzat-hozzárendelés módosítása és backend
  újraindítás érvényteleníti a korábbi szándékot. Az A → B → A hozzárendeléscsere
  sem támaszt fel régi OFF-ot. Más folyamatok bindingkezelése változatlan.
- Új mentés miatt a korábbi késleltetett OFF **törlődik**; nem indul újra
  automatikusan a mentés után. A már futó mentés közben kért shutdown külön
  sorba állítható: annak SSH-kérése csak a lockok felengedése után fut.
- Lock-/állapotolvasási hiba ismeretlen állapot, nem szabad mentési ablak.
  Guardhiba esetén nincs SSH-leállítás vagy automatikus OFF, és nincs vak retry.
  Az AI-guard indulási hibája nem állítja le a többi backendfunkció indulását.
- A késleltetett OFF sikeres MQTT-kérése `requested` állapot, nem fizikai
  kikapcsolási bizonyíték. A publikálási/visszaigazolási szerződést nem módosítottuk.

A backup/check mögött váró kérés érvényessége 24 óra. A már időzített OFF a
kiválasztott határidő után legfeljebb 60 másodpercig érvényes; késői felébredéskor
törlődik. Az ütemezés monotón órát használ, a UI számára külön wall-clock
határidő szerepel. A tárolt szándék backendújraindítás után nem játszódik vissza.

## Közös állapot és lockok

Az új `ai_power_coordination.py` stdlib modul a backend és a host F6 runner
közös, atomi `backups/ai-power-state.json` állapotát és rövid
`ai-power-coordination.lock` zárolását kezeli. Nem használ új DB-táblát.
A backend és a host ugyanazt a backupkönyvtárat/inode-okat kell lássa.

| Tulajdonos | Sorrend és időtartam |
|---|---|
| F6 weekly runner | `ai-backup.lock` → `homecontrol-backup.lock` a teljes munkára; utána rövid koordináció az új generáció rögzítéséhez |
| Többi F6 mód | `homecontrol-backup.lock` a teljes munkára, majd rövid koordináció; minden új feladat érvényteleníti a korábbi szándékot |
| SSH shutdown / késleltetett OFF | Koordinációs lock, majd **nem várakozó** foglalás az AI- és közös backup lockra; sikeres foglalás a teljes SSH/publish alatt megmarad |
| Wake / AI bindingcsere | Koordinációs lock alatt szándéktörlés és az érintett művelet |

Ha egy backup már birtokolja a hosszú lockot, a power művelet nem vár rá a
koordinációs lockkal: sorba állít vagy töröl. Így a két locksorrend között nincs
körkörös várakozás. Ha a power művelet foglal először, a mentés nem kezdhet
egyidejű munkát. A read-only státusz nem hoz létre hiányzó lockfájlt.

A jelenlegi egy gunicorn worker / nyolc thread felállást használjuk. Több worker
bevezetése külön életciklus- és szándéktulajdonosi felülvizsgálatot igényel.

## Heti és restic-check befejezés

A F6 worker a saját `backup_run_id` értékével kér ébresztést és befejező
leállítást. A saját ébresztés megőrizheti az aktuális futás befejezési jogát.
Köztes kézi wake, új shutdownszándék, bindingcsere, backendújraindítás vagy
új backup ezt visszavonja; a régi callback **409** választ kap.

A saját lockját még birtokló weekly/check callback **202/deferred** választ
kap. A worker befejezése és lockelengedése után a backend szándékkezelője
indíthat SSH-leállítást, majd a kért késleltetést. Nem kell újra felvenni a saját
hosszú lockot a workerből, és a `defer_if_backup_running=false` nem ad bypass-jogot.

A régi `ai-shutdown-after-backup.request` nem az új szándék forrása; az új
worker nem olvassa vissza és nem publikál belőle új shutdownkérést.
A közvetlen általános Power Wall kézi aljzatkapcsolás változatlan, nem az itt
leírt mentésvédett AI-leállítási útvonal.

## API és felület

Az AI-státusz és backup-státusz külön közli az ismeretlen guardot, a futó
mentést, a sorba állított shutdownt és a pending OFF-ot. A UI ismeretlen állapotnál
`Unknown` jelzést ad, az AI shutdown gomb tiltott. A visszaszámlálás az aktuális
szerveroldali határidőt használja; régi localStorage határidő nem kelti életre.
Ébresztés és shutdown után a felület újra lekéri az állapotot.

## Ellenőrzés

- Az eredeti reprodukció újrafuttatva: régi kód A-t ütemezett, majd aktív lock
  mellett B-re publikált OFF-ot; a javított változat semmilyen OFF-ot nem küldött.
- **26 HC-31 AI-teszt:** 21 fake-clock/transport és valódi ideiglenes flock eset,
  valamint 5 Flask HTTP-eset. Wake, új backup, A → B → A, topiccsere, újabb
  shutdown, restart, lejárat, permission/hibás állapot, SSH-hiba, self-held
  completion callback, saját/kézi wake, régi callback és két párhuzamos kérés.
- Valódi külön processz a publikálás közben nem tudta felvenni a backup lockot;
  utána fel tudta venni. Fordított sorrendben a shutdown lockfelengedésig vár.
- A teljes backend alapkör: **701 felfedezett, 585 sikeresen futott,
  116 PostgreSQL opt-in kihagyott, 0 failure/error**. Ebből a mentési kör
  49 eset, benne új futásgeneráció-, check-callback- és hibás állapot-próbákkal.
- **98 frontendteszt** (83 mower, 9 AI, 6 backup), 0 hiba, production build sikeres.
- Külön backup-státuszpróba: közös lock látszik, queued szándék látszik,
  törlés megjelenik, olvasási hiba unknown. Python- és shellszintaxis rendben.

Az első suite-futás egy új fixture miatt hibázott: a teljesen offline SSH
megakadályozta a tesztben várt restic parancsot. A fixture az első SSH-probe-ra
korlátozott kiesést kapott, a végső kör hibamentes. Éles I/O nem történt.

Privát bizonyíték: `/tmp/hc31-repair/` — tesztlogok, `backend-results.json`,
`audit-reproduction.json`, `backup-status-probe.json`, előállapot/diff/hash és
`live-scope.json`. A 116 PG-próba és a fizikai shutdown/wake most nem futott;
a hardverpróba az audit szerint külön, felügyelt végrehajtási feladat.

## Függőségek, bevezetés és rollback

**Nincs élesítve.** Az éles r3 ingest és az r2 backend/frontend változatlan,
hat konténer ID/image/indulás/restart-szám azonos, 14 telepített unit és az
eredeti host scriptek változatlanok; DB/MQTT health rendben.

E megvalósítás technikai függősége a helyi **F6 közös runner** és a frissített
weekly/check worker, ugyanazzal a backendkoordinátorral és backupmounttal.
Legacy-only runner nem ad teljes generációs védelmet egy két ellenőrzés között
elindult és befejeződött mentésre. A backend/host/UI ezért együtt adandó át;
az élő régi host scripteket most nem módosítottuk és unitot nem telepítettünk.

A teljes munkafakiadáshoz a HC-07/38/39 migrációs/role/DSN feltételei is
megmaradnak. A HC-17/18 exporthatár, F6a restorepontok, HC-44 hostjogok és
minden más auditpont változatlanul külön munka. Az r3 visszajelzésjavítása
megőrzendő. HC-31 javítása nem jelenti a teljes blokk élesíthetőségét.

Átadás és rollback előtt a függő szándékokat érvényteleníteni kell, a régi
backend processzt és benne az alvó workereket ténylegesen le kell állítani.
A régi, memóriában váró worker nem ismeri az új generációs fájlt.
Az új koordinációt, közös lockot és mentésvédelmet megőrző rollbackcsomag
szükséges; egyszerű régi backend-image visszakapcsolás visszahozná a hibát.
Nem történt fizikai művelet, migráció, automatikus ACK vagy teljes kiadási rollback-próba.
