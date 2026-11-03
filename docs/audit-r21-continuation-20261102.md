# r21 – ellenőrzött zárolásfeloldás és élesítési folytatás

REPAIR-073, 2026-11-02. Aktív: `hc-security-20261102-r18`.
A lezárt r21 alkalmazáscsomag változatlan, új alkalmazás-image nem készült.

A root diagnosztika teljes repository-adatellenőrzése sikeres volt, hiányzó pack
nélkül. Egy repository-lock maradt. A hibás r21 előellenőrzés kilépési kódja 1.
A nyers eredeti hibakimenet akkor nem maradt meg, ezért a korábbi hibák mindegyikét
nem tulajdonítjuk bizonyítottan ennek a locknak. A lock tulajdonosát innen nem tudjuk
elolvasni; annak vizsgálata a root folytató kötelező első lépése.

A helyi, eldobható valódi restic 0.12.1 repositoryban reprodukáltuk a tünetet:
élő vagy megszakított mentés megmaradt zárolása mellett a normál teljes check exit 1,
a `--no-lock` teljes check exit 0. A natív `unlock` a friss élő folyamat lockját
megőrizte; a megszakított és megvárt folyamatét eltávolította, majd a normál teljes
check exit 0 lett. A routerhez ez a labor nem kapcsolódott.

## A folytatás menete

1. Valódi helyi root, a külön folytatócsomag és a teljes eredeti r21 csomag hash-
   és bizonyítékellenőrzése. Csak az ismert `RuntimeError`/restic exit 1 fogadható el;
   megkezdett r21 staging, transition, telepített runtime vagy átadás kizáró ok.
2. Az eredeti hiba privát megőrzése és egyszeri indítási nyugta. Az aktív r18,
   minden konténer-ID/image és a meglévő működési guardok újraellenőrzése.
3. A két közös mentési lock és idle-ellenőrzés mellett minden repository-lock
   metaadatának beolvasása. Csak ugyanezen géphez tartozó, érvényes időpontú,
   már nem létező PID-del rendelkező zárolás oldható fel. Élő, idegen géphez tartozó,
   hibás vagy nem ellenőrizhető tulajdonos esetén a folytató módosítás előtt megáll.
   A Go nanomásodperces időbélyegét a host Python 3.10 verziójához normalizáljuk.
4. Változatlan locklista ismételt ellenőrzése, majd kizárólag natív `restic unlock`,
   **`--remove-all` nélkül**. Üres locklista szükséges a továbblépéshez. Nincs pack-,
   index-, snapshot- vagy kulcsjavítás/törlés ebben a zároláskezelési lépésben.
5. Az eredeti r21 teljes aktiválási pipeline-ja indul. A végleges repository normál,
   zárolást használó teljes ellenőrzése most a közös hostlockok alatt történik.
   Ezt nem váltja ki és nem kerüli meg a korábbi `--no-lock` diagnosztika.
6. Az r18 teljes HC/Git/router mentése és az archívumhoz tartozó izolált PG-restore
   a szolgáltatások leállítása előtt kötelező. Ezután három komponens átállítása,
   új teljes mentés/restore, runtime-, komponens-, öt timer- és átadásellenőrzés.
   Az eredeti tranzakció és automatikus r18 rollback megmarad.

A folytató az aktiváló folyamatában az összes repository-példány hibakimenetét
beköti az r21 meglévő privát naplózójába. Így a közvetlen előellenőrzés hibakimenete
is megmarad. A lezárt r21 fájljai helyett csak az aktuális folyamat adaptere változik.
A tényleges mentési workerek az r21 eredeti privát naplózóját és a már ellenőrzött
systemd folyamatfa-felügyeletet használják. Megőrzési szabályt nem módosítottunk;
a rendes heti mentés továbbra is az ellenőrzött meglévő szabályt követi.

## Ellenőrzés

24 sikeres folytatóteszt. Lefedik az élő/idegen/hibás PID és időpont tiltását,
az összes lock előzetes vizsgálatát, a változó locklista elutasítását, a natív
unlock hibájának megállító hatását, a maradó lock tiltását, a force hiányát,
az üres lista írás nélküli kezelését, a root-/csomag-/korábbiállapot-guardokat,
a production előellenőrzés közös lockját és az önmagával ütköző nested flock kerülését.
Egy teszt valódi restic folyamatot indít a helyi laborban, natív Go lock-metaadatot
olvas, ellenőrzi az élő PID tiltását és a megszakított PID elfogadását, majd unlock
után normál teljes adatellenőrzést végez. Minden eset sikeres, kihagyás nélkül.

Az r21 eredeti 799 forráslenyomata és 105 tesztes elfogadása változatlan;
a korábbi 1308 alkalmazásregresszió bizonyítéka megőrzött. Az r18 736 runtime-hashe,
16 konténerbaseline-ja és öt aktív timer csak olvasással újraellenőrzött.
Új, teljes r21 VM-próbát nem állítunk. A root végrehajtás és a tényleges router-lock
metaadatának értékelése még hátravan, ezért az éles javítást nem állítjuk késznek.

## Egyetlen helyi folytatóparancs

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r21-continuation-1/source/resume_r21.py
```

Ez végrehajtó folytatás: igazoltan elavult lock esetén felold és élesít, nem egy
újabb kizárólag diagnosztikai kör. Élő vagy idegen tulajdonost nem kerül meg.
A helyi sudo-jelszó innen nem hozzáférhető, azt kizárólag a felhasználó adja meg.
Végső siker: `deployed_and_audit_handover_complete` és `post-live-check.json`.

HC-41 és HC-43 folyamatban, az AI tiltva marad. Más auditpontot nem módosítottunk.
A jelenlegi javítási kör átadása a sikeres root-eredményig függő.

Bizonyítékok: `backups/releases/hc-audit-20261102-r21-continuation-1/evidence/`.
A root végrehajtás privát lock-metaadatot és hibakimenetet a csomag `private/`
könyvtárában, nyilvános lock-helyreállítási nyugtát az `evidence/lock-recovery.json`
fájlban tart meg. A korábbi csomagokat és hibabizonyítékokat nem írjuk át.
