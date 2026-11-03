# r22 – sikeres előmentés/restore, visszagörgetett telepítés és EXDEV-folytató

**Lezárás (REPAIR-084): az r22 éles átadása sikeres; a korábbi indítók nem ismétlendők.**
[Aktuális végső állapot és bizonyítékok](audit-r22-live-handover-20261103.md).
Az alábbi előkészítési/hibaállapot történeti.

**Frissítés (REPAIR-081): a folytatót a felhasználó lefuttatta, nem ismételhető.**
Az EXDEV-javítás és az új r22 mentés/restore sikeres, de a végső záróellenőrzés
`ValueError` hibája ismét r18 rollbacket indított.
[Aktuális állapot és diagnosztikai parancs](audit-r22-handover-failure-20261103.md).
Az alábbi előkészítés történeti állapot.

REPAIR-080, 2026-11-03. Aktív: **`hc-security-20261102-r18`**.
A felhasználó kifejezett r22-élesítési engedélye érvényes. Új alkalmazáskiadás
vagy image nem készült; az r22 805 lezárt forrása változatlan.

## Mi történt az éles futásban

Az r22 root indítója a korábbi megszűnt helyi folyamat lockját natív,
nem kényszerített unlockkal eltávolította, a maradó lockszám nulla.
A router-próba és a normál teljes repository-check sikeres volt.
Az új transporttal futó r18 shadow-runner teljes mentése is **sikeres**:
helyi archívum, secrets-bundle, külső Git, router snapshot és retention.

* Run: `497cb0e2c4764d18b14e1d821f694413`.
* Snapshot: `55e891e9fcc196161729015c0cddba4a42175a4fd5ad9c08eea3a53deeebde18`.
* Archívum: `homecontrol_2026-11-03_11-16-21_497cb0e2c4764d18b14e1d821f694413.tar.gz`.
* Méret: 2 815 007 933 bájt; 8113 ellenőrzött fájl.
* SHA-256: `8f3faac99a6437f99e275dab5b0ef399c8984d95f09916b6acad1e4432fa50ed`.

Az `evidence/baseline-backup-restore.json` szerint a routerről történő
visszaolvasás és az izolált PostgreSQL-restore is sikeres. A felhasználó
terminálkimenetének utolsó sikerüzenete után az átállítás megkezdődött;
`Error` kivétellel megállt, majd az automatikus rollback lefutott.
A nyilvános fázis **`previous_release_restored`**.

Az első ügynöki értelmezést a nyugták pontosították: nem a restore volt hibás.
Az új r22 runtime-könyvtár már létezik, de a kiadás nem aktív. Mind a 805
runtime-fájl egyezik a lezárt r22-vel; a privát telepítési cél részleges.
Az eredeti privát `entry-error.json` tartalmát az ügynök nem olvasta.

A natív hoston csak olvasással ellenőrzött: mind a 16 konténer ID/image
egyezik az r18 baseline-nal, a 10 healthcheck healthy, backend `ok: true`,
mind az öt timer aktív, hostops fut. Az AI tiltva, routeres policy engedélyezve.
Az r22 acceptance-supervisor inaktív, `MainPID=0`, `LoadState=not-found`.
Mind a 736 élő r18 runtime-hash és az eredeti r22 pecsét egyezik.

## A reprodukált telepítési hiba

A tárhelyterv hibás feltételezése volt, hogy a régi inode-ok és az azonos
fájlrendszer-azonosító megőrzése önmagában elég az új cache-hardlinkekhez.
A `backups/releases` külön bind mount, az `infra/ssh` másik VFS-mounton érhető el.
A kernel az új hardlinket ezek között azonos `st_dev` mellett is `EXDEV`
hibával utasítja el. Az eredeti átállítási próbák ezt az útvonalpárt nem fedték le.

A tényleges mountok között két egyedi, eldobható tesztkönyvtárral reprodukáltuk:
azonos `st_dev`, `os.link` eredménye errno 18. Ez összhangban van a telepítő
`shutil.copytree`/image-cache útvonalával és a részlegesen megmaradt célokkal.
A konkrét privát kivétel azonosságát ettől külön kezeljük: a folytató csak
akkor indul tovább, ha rootként pontosan egyetlen, a két ismert cache-útvonal
közötti `[Errno 18]` copytree-hibát talál. Más hiba esetén módosítás előtt megáll.

A javított cache-átvitel először továbbra is hardlinket próbál. Kizárólag a
kernel `EXDEV` hibájánál másol egy egyedi, privát ideiglenes fájlba.
Ellenőrzi a teljes SHA-256-ot másolás közben és visszaolvasással, a forrás
változatlanságát, a méretet, tulajdonost és hozzáférési módot; megőrzi az xattrokat
és az időbélyegeket. A cél közzététele kizárólagos: meglévő fájlt nem ír felül.
Más I/O-, jogosultság-, helyhiány- vagy tartalomhiba nem kap ilyen fallbacket.

A tényleges mountpár között 8 MiB + 7 bájtos szintetikus cache sikeresen
átkerült, azonos SHA-val és xattrral, külön inode-on. Minden tesztfájl eltávolítva.
Nem történt éles archívummásolás vagy jogosultságkerülés az ügynöki próbában.

## A külön folytató ellenőrzései

Csomag: `hc-audit-20261103-r22-continuation-1`.
52 végső sikeres teszt, hiba és kihagyás nélkül: 26 új cache-/folytatóteszt,
7 meglévő cache-teszt és 19 átvett staging-/folytatóteszt.
Lefedett a tényleges copytree-kivétel alakja és az utána sikeres javított
copytree, a forrásváltozás, a hash-/mód-/tulajdonos-/symlink-/special-file guard,
a cél létrehozási versenye, a másolási hiba utáni takarítás, a pontos rollback
és előmentési nyugta, az eltérő vagy többes kivétel tiltása, valamint a megőrző
átnevezés ütközése és részleges hibájának visszaállítása.

Az átvett staging-teszt eredetileg a valódi r22 privát útvonalat tekintette
nem létező fixture-nek. A tesztet elkülönített tmp-útvonalra javítottuk;
az eredeti sikertelen napló megmaradt. Runtime-guardot nem enyhítettünk.
A korábbi 165 r22 teszt és a sikeres éles előmentési/restore-nyugta megőrzött;
ezeket nem számoljuk újrafuttatottnak. Új teljes VM/reboot-próba nem volt.

Az indító ugyanannak a jóváhagyott r22-nek a teljes pipeline-ját használja.
A cache-függvényt csak az aktiváló folyamatában adapterezi a külön lezárt
helperre; az r22 forrás-/runtime-hasheket és image-eket nem írja át.
A munkapéldány kanonikus cache-helperje a jövőbeli előkészítésekhez is javított.

## Egyetlen helyi végrehajtóparancs

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261103-r22-continuation-1/source/resume_r22_install.py
```

Az ügynöki `sudo -n` indítás helyi jelszót kér; a folytató rootként még nem futott.
Az r22 korábbi kifejezett élesítési engedélye alapján indítandó, új engedélykérés
nélkül. Ez végrehajtó folytatás, nem önálló diagnosztika.

1. A külön folytató és a teljes eredeti r22 pecsétje, az eredeti privát egyetlen
   cache-EXDEV hiba, a sikeres rollback és előmentés/restore, a teljes/részleges
   célok, a változatlan éles r18 és az idle állapot ellenőrzése kötelező.
2. Mindkét közös hostlock alatt újraellenőriz mindent, visszafejti és a jelenlegi
   r18 bemenetekhez hasonlítja a staging titkosított bundle-jét. Csak üres
   repository-locklistát fogad el; unlockot nem ismétel.
3. Törlés helyett egyedi `-preserved-<azonosító>` néven megőrzi a félbemaradt
   runtime-ot, privát célt, korábbi tranzakciót és befejezett shadow-runnert,
   mindegyiket a saját szülőkönyvtárán belül. Az átnevezés atomikusan elutasít
   meglévő célt. A terv és az eredmény külön privát nyugtát kap.
4. Új normál teljes repository-check, új teljes r18 HC/Git/router előmentés
   és izolált PG-restore következik. A korábbi sikeres mentést sem használja
   ezek helyett. Csak utána jöhet a szokásos háromkomponenses átállítás,
   új r22 teljes mentés/restore, timer-/runtime-/policy-átvétel és auditátadás.
   A meglévő automatikus r18 rollback megmarad.

Végső siker: **`deployed_and_audit_handover_complete`**.
Az eredeti r22 indítót és a korábbi r21 folytatókat ne ismételd. Hiba után ezt
a folytatót se indítsd vakon újra. A privát eredeti hiba root-ellenőrzése és a
tényleges folytatás még függő; a javítási kör éles átadása nincs lezárva.
Az r18 aktív mentője továbbra is a korábbi kódot használja: az r22 sikeres
shadow-előmentése önmagában nem jelent befejezett éles transportfrissítést.

46 Ellenőrzött; HC-41 és HC-43 Folyamatban; az AI tiltva marad.
Bizonyítékok: a külön folytató `acceptance.json`, `evidence/` és `source/`
könyvtára, az eredeti r22 `evidence/baseline-backup-restore.json` nyugtája,
valamint `docs/audit-evidence/r22-install-continuation-20261103/`.
