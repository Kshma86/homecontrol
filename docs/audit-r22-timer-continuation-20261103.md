# r22 – a health timer futásának megvárása a végső ellenőrzésben

**Frissítés (REPAIR-083): a felhasználó indítása a tranzakció megkezdése előtt
megállt.** A robot-idle guard újrafuttatásban blokkol, és a korai hibanaplózás
hiányossága is kiderült. Az eredeti csomag változatlan.
[Aktuális állapot és várakozó operátori indító](audit-r22-idle-preflight-20261103.md).
Az alábbi közvetlen indítóparancs történeti; az új indító a robotra vár és a korai
kivételeket is ténylegesen megőrzi.

REPAIR-082, 2026-11-03. Aktív: **hc-security-20261102-r18**.
Az r22 élesítésére adott felhasználói engedély érvényes. Új alkalmazás-image nem
készült; az r22 805 lezárt forráshashe és manifestje változatlan.

## Pontos diagnózis és reprodukció

A felhasználó helyi sudo-val lefuttatott, csak olvasó összegzője igazolta:

```text
ValueError: Scheduled timer has no next trigger: homecontrol-post-boot-health.timer
rollback_verified: true
active_release: hc-security-20261102-r18
handover_exists: false
```

Az r22 elő- és utómentése, valamint izolált PG-restore-ja sikeres volt;
a végső timer-ellenőrzés hibája indította a visszaállítást.

A lezárt timer `OnBootSec=3min`, `OnActiveSec=3min`,
`OnUnitInactiveSec=10min` beállításokat használ. A systemd szerint az utóbbi
a szolgáltatás inaktívvá válásához méri a következő futást; a már elmúlt
`OnBootSec` pedig a timer indulásakor azonnal aktiválhatja a szolgáltatást.
[Elsődleges systemd-dokumentáció](https://www.freedesktop.org/software/systemd/man/256/systemd.timer.html).

Külön átmeneti **user-scope** timerrel, egyszerű `sleep` oneshot szolgáltatással
valódi reprodukció készült. Futás közben `active/running`, a szolgáltatás
`activating/start`, a következő monotonic trigger `infinity`. Sikeres befejezés
után `active/waiting`, a szolgáltatás `inactive/dead`, exit 0, és újra van következő
futási idő. A régi ellenőrzés ezt a szabályos köztes állapotot elutasítja.
Az eredeti hibapillanat service-állapotáról nincs atomikus felvétel; a reprodukció
az azonos hibaüzenethez vezető, szabályos átmenetet igazolja.

A próbák nem módosítottak HC unitot, és eltakarították a saját átmeneti unitjaikat.
Az első próba nyers megfigyelései megmaradtak. A levezetett logikai jelző kezdetben
csak a `0` értéket ismerte fel; javítva az `infinity` értékre is. A nyers adatok és
az első összegzés külön megőrzöttek; a későbbi adapterpróba önállóan is sikeres.

## A külön folytató működése

Csomag: `backups/releases/hc-audit-20261103-r22-continuation-2`.
Az eredeti r22 forrásait és a már felhasznált continuation-1 csomagot nem írja át.
A `timer_settle.py` adapter csak az indító Python-folyamatában egészíti ki az
eredeti schedule-checkert. A timer vagy a health service beállításai változatlanok.

* Csak a pontos r22 health-timer `ValueError`, a sikeres r18 rollback és a konkrét
  korábbi teljes r22 mentési/restore-nyugta után indulhat.
* A rollbackben újralétrehozott backend/mDNS/Growatt három ID-ját veszi át kizárólag
  memóriában. Mind a 16 image az r18-é, a másik 13 ID változatlan, a futási/health
  állapot megfelelő kell legyen. Az eredeti runtime-, compose-, backend-, robot-,
  öntözés- és idle-guardok az elfogadott ID-kkal továbbra is kötelezők.
* A régi r18 runtime és hozzá tartozó hozzáférési unitok hashét is ellenőrzi,
  mielőtt a korábbi r22 célokat megőrzi. Így az aktív r18 guardok működő útvonalai
  nem kerülhetnek át a megőrzött könyvtárnevek alá.
* A sikertelen r22 runtime, teljes privát telepítés, transition és shadow-runner
  atomikusan, célfelülírás nélkül megőrzött nevet kap. A privát telepítésnek a
  staginggel teljesen egyeznie kell, az ismert `installed.json` nyugtával együtt.
* A működő EXDEV-másolási adaptert és a titkosított staging-ellenőrzést újra használja.
  Új repository-lock esetén megáll; unlockot nem ismétel.
* Új teljes r18 HC/Git/router előmentés és izolált PG-restore kell minden átállítás
  előtt. Az r22 átállítása után új teljes mentés/restore és minden eredeti átvétel
  kötelező; a korábbi sikeres mentést nem használja fel e kapuk kiváltására.
* A health oneshot sikeres befejezésére legfeljebb 210 másodpercig vár. Hiba,
  nem nulla exit, inaktív timer, más service-cél vagy határidőtúllépés esetén megáll.
  Inaktív service mellett tartósan hiányzó trigger továbbra is hiba.
* Az összes eredeti byte-, enablement-, aktívállapot- és triggerellenőrzés újrafut.
  Siker csak befejezett health service és új időpont mellett adható. Más timer
  hibáját, hashdriftet vagy hibás beállítást nem kezel átmeneti állapotként.

## Ellenőrzés és korlátok

**66 célzott teszt sikeres:** 17 folytató-, 11 timer-adapter-, 10 cache-,
19 staging- és 9 eredeti schedule-teszt. A timer-tesztek az eredeti lezárt r22
schedule-checkert használják; lefedik a futás közbeni hiányzó időpontot, a sikeres
befejezést, a service-hibát, a beragadást, a várakozás közbeni hashdriftet és a
másik timer hibáját. A megőrzés részleges hibájának visszaállítása is tesztelt.
A valódi systemd-adapterpróba kb. 3 másodpercet várt, és sikeres volt.

Natív, csak olvasó ellenőrzés: 805 r22 forráshash egyezik, 736 r18 runtime-hash
és az r18 hozzáférési unitok egyeznek; 16 r18 image, 13 változatlan konténer-ID.
A teljes root guard root nélküli futtatása a védett hostops-job könyvtárnál
`PermissionError` hibával megállt; ezt nem kerülte meg az ügynök. A valódi
folytatóban a teljes guard rootként kötelező. A root privát staging és transition
új guardja még csak helyi sudo-val ellenőrizhető, még az új mentés előtt.

Bizonyítékok: [`audit-evidence/r22-timer-continuation-20261103`](audit-evidence/r22-timer-continuation-20261103/acceptance.json),
valamint a csomag `evidence` könyvtára. Nincs új teljes r22 VM/bare-metal/reboot
próba. Az audit átadása még függő: 46 Ellenőrzött, HC-41/43 Folyamatban.

A csomag integritásellenőrzése sikeres. A natív `sudo -n` indítás
`sudo: a password is required` eredménnyel megállt; a root folytató nem indult el,
és nem történt új élesítés. Az engedély érvényes; helyi sudo-hitelesítés szükséges.

Aktuális egyszer használható helyi parancs:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261103-r22-continuation-2/source/resume_r22_timer.py
```

Az eredeti `start_r22.py` és a continuation-1 indító nem ismételhető.
