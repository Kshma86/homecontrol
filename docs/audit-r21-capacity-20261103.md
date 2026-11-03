# r21 – tárhely helyreállítva, a sikeres lock-feloldás megőrizve

**REPAIR-077:** a második folytató rootként már elindult, majd a teljes r18 előmentés
router-snapshot hibájánál megállt. Az alábbi folytatóparancsot ne ismételd.
[Aktuális hibaállapot és naplóösszesítés](audit-r21-baseline-failure-20261103.md).

**REPAIR-076 frissítés:** a mentési tárhely sikeresen a `/var` partícióra költözött.
A `/srv` és a mentési fájlrendszer kapacitáskapuja is teljesül. Aktív továbbra is r18;
az alábbi lezárt folytató változatlan. A tárhelyellenőrzéssel összekötött aktuális
[indítás és éles utóellenőrzés](backup-storage-live-20261103.md) külön dokumentált.
Az alábbi kapacitásszámok a REPAIR-074 korábbi állapotát rögzítik.

REPAIR-074, 2026-11-03. Az aktív kiadás továbbra is r18.

A felhasználó futtatta az első r21 folytatót. A nyilvános lock-helyreállítási
nyugta bizonyítja: a helyi, már nem létező 2129370 PID 2026-11-02 22:06:35 CET
idejű lockját natív, nem kényszerített unlock eltávolította; a maradó lockszám nulla.
Snapshot- és adatfájl törlése ebben a lépésben nem történt.

A folytató ezután az inaktív cache-ek idempotens ellenőrzése után ValueError hibával
megállt. Nincs r21 deployment-status, transition vagy telepített runtime.
A privát kivételfájl innen root nélkül nem olvasható. Az ellenőrzött látható állapot
alapján a következő tárhelykapu nem teljesült: 6 980 861 952 bájt szabad helyre
7 776 078 862 bájt szükséges. Az új, 02:15-kor indult éjszakai mentés helyi
archívuma 2 814 297 607 bájt; a log szerint a snapshot elkészült, a megőrzés hibázott.
Ezt a hibás mentési futást nem minősítjük sikeresnek.

Az új folytató rootként **pontosan** az előző ValueError tárhelyüzenetét követeli meg.
Ha más hiba szerepel a privát naplóban, nem próbál más szakaszt automatikusan folytatni.
A tárhelyhiány jelenlegi tényét és a konkrét privát kivétel azonosságát külön kezeljük.

## Elvégzett tárhely-előkészítés

Az inaktív r11 és r12 operator-owned `private/access-images.tar.gz` fájlja ugyanazt
az 1 411 092 197 bájtot tartalmazta két külön inode-on. Mindkét csomag manifestje és
a teljes fájltartalom SHA-256 ellenőrzése:
`b179836e78ce8f3fa359673e954de9eb07a32ed03a3e8e8ce6a7e18eef9cdd20`.
A már hét esetben tesztelt, fagyasztott r21 cache-kezelő azonos tulajdonos,
csoport, 0600-as mód és fájlrendszer mellett hard linkkel közös tárolásra váltotta őket.
A tartalom, tulajdonos és hozzáférési mód változatlan; mentési archívum törlése nem történt.
A szabad hely 8 391 835 648 bájtra, kb. 7,8 GiB-ra nőtt.

A szükséges hely számítását nem enyhítettük: két, a legnagyobb befejezett helyi
archívummal azonos méretű új mentés és további 2 GiB tartalék továbbra is kötelező.
A root-indítás ezt frissen újraméri, bájtpontosan kiírja és elégtelen hely esetén megáll.

## Folytatás

Új, külön, lezárt `hc-audit-20261102-r21-continuation-2` folytató készült.
A korábbi r21 csomag, az első folytató forrása, elfogadása és hibája megőrzött.
Az új belépő a korábbi folytató pontosan hash-ellenőrzött adapterét használja:
az eredeti hiba és átállítás előtti állapot őrei, a privát előellenőrzési naplózás,
a közös repository-lock adapter és az r21 teljes aktiválási pipeline-ja változatlan.

A korábbi natív unlock helyett az új folytatás csak üres locklistát fogad el,
a két közös hostlock alatt. Új lock esetén megáll; unlockot nem ismétel.
A korábbi, sikeres feloldás nyugtájának pontos hashét és a privát kapacitáshibát
ellenőrzi. Külön egyszeri indítási nyugtát és privát naplót használ.

A normál, teljes repository-ellenőrzés, a futó r18 teljes HC/Git/router előmentése,
az archívumhoz tartozó izolált PostgreSQL-restore, a háromkomponenses átállítás,
az új teljes mentés/restore és az öt timerrel együtt végzett záróellenőrzés kötelező.
A meglévő rollback és megőrzési szabály változatlan.

10 új teszt sikeres: az eredeti kapacitásküszöb pontos megőrzése és egybájtos
alulteljesítés tiltása; befejezetlen/hibás archívumnyugta; új lock megállító hatása,
unlock ismétlésének hiánya; pontos előző hiba és hiteles locknyugta követelménye;
root nélküli indítás tiltása. A korábbi 24 folytatóteszt, natív restic-labor és
105 r21 aktiválóteszt bizonyítékai megőrzöttek, újrafuttatásnak nem számoljuk őket.
A 799 eredeti r21 forráshash és az r18 baseline ellenőrzése a lezárás része.

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r21-continuation-2/source/resume_r21_capacity.py
```

Ez az élesítést is végrehajtó folytatás, nem újabb önálló diagnosztika.
A helyi sudo-hitelesítés és a root szakasz végrehajtása még függő.
Végső siker: `deployed_and_audit_handover_complete`.
HC-41/43 folyamatban, az AI tiltva marad. Más auditpontot nem javítottunk.

Bizonyíték: `docs/audit-evidence/r21-capacity-20261103/` és a külön folytatócsomag
`acceptance.json`, `evidence/` állományai.
