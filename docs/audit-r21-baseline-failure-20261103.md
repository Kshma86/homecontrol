# r21 – a teljes r18 előmentés router-snapshot hibája

**REPAIR-078 frissítés:** az első root összesítés megérkezett. Transport/backend-write
hiba látszik, de az 500-as kód protokollját az első verzió nem azonosította.
A stdout csonkolt. [Pontosított elemző és következő lépés](audit-r21-transport-diagnosis-20261103.md).
Az alábbi tesztszám és összesítőleírás a REPAIR-077 történeti változata.

REPAIR-077, 2026-11-03. Aktív: `hc-security-20261102-r18`.
Az r21 folytatóját nem szabad újraindítani a hiba feltárása nélkül.

A felhasználó futtatta a tárhelyellenőrzőt és a második r21 folytatót.
A tárhelyellenőrző `ok: true`, `phase: complete` eredményt adott;
168 646 090 752 bájt szabad mentési tárhelyet mért. Az r21 kapacitásnyugtájában
51 521 966 080 bájt szabad `/srv`-hely áll a szükséges 7 776 078 862 bájttal szemben.
A korábbi lock-feloldást ellenőrizte, új unlock nem történt. A router-próba és
a normál teljes repository-check után elindult az átállítás előtti r18 mentés.

## Bizonyított hiba és éles állapot

A `backups/backup-state.json` szerint a `37e3acdd8a374fc4a2a48422ab830ed5`
azonosítójú futás `failed` állapotú. A secrets-bundle, a külső Git és a helyi
archívum célja `succeeded`; a restic cél `failed`, `restic backup exit 1` hibával.
A nyugta szerinti archívum:

* Név: `homecontrol_2026-11-03_10-07-09_37e3acdd8a374fc4a2a48422ab830ed5.tar.gz`.
* Méret: 2 814 808 725 bájt; 8106 ellenőrzött fájl.
* SHA-256: `894acb8a7e64313dbfd0c950f233ca9b4c836d48df6f13afc0e1b7f0a6004956`.

Az archívum és befejezési nyugtája megmaradt. A teljes mentést nem minősítjük
sikeresnek: a kötelező router-cél nem teljesült, a hozzá tartozó izolált
PG-restore még nem indult. A privát archívumot az ügynök ebben a körben nem
olvasta vissza; a fenti értékeket a nyugta és a futási állapot rögzíti.

Az r21 `deployment-status.json` fázisa `baseline_full_backup` maradt. Ez egy
megszakadt előmentés fázisjelzője, nem sikeres vagy jelenleg futó élesítés.
A telepített r21 runtime és az r21 `infra/ssh` cél nem létezik; a kiadásjelölő r18.
A kód a teljes sikeres előmentés és restore után készítené el az átállítási
snapshotot és állítaná le a komponenseket. A root-only átállítási könyvtár
hiányát a helyi összesítő még külön ellenőrzi.

A natív hoston csak olvasással újraellenőrizve: mind a 16 konténer ID/image
baseline-ja egyezik, a 10 healthcheck healthy, backend `ok: true`, mind az öt
timer aktív, a hostops fut. Az AI tiltva, routeres mentési policy engedélyezve.
A `homecontrol-r21-acceptance-backup.service` inaktív, `MainPID=0`,
`LoadState=not-found`; az elfogadási worker nem maradt futó supervisor alatt.

## Következő szükséges lépés

A pontos restic-hiba a `backups/router-diagnostics/` root-only naplóiban van.
Az ügynök natív `sudo -n` próbája helyi jelszót kér, ezért ezeket nem olvasta.
Tárhely-, lock-, hálózati vagy repository-sérülési okot az exit-kód önmagában
nem bizonyít; automatikus unlock, repair, prune vagy újraélesítés nem történt.

Az új `scripts/audit_release/summarize_r21_baseline_failure.py` csak a konkrét
hibás futás meglévő naplóit és állapotfájljait olvassa. Nincs benne subprocess,
hálózati hívás vagy fájlírás. A root tulajdonú, privát módú reguláris naplókat
fogadja el, symlinket és túl nagy fájlt elutasít. A kimenet rögzített hibaosztályokat,
FTP válaszkódokat és forráscsoportokat tartalmaz; nyers argv/env, szerverüzenet,
felhasználónév, jelszó és privát fájlnév nem kerül át a kimenetre.

12 sikeres teszt: a nyers értékek visszatartása, hibaosztályozás, kimeneti korlátok,
hibás JSON-sorok, root-guard, symlink/jogosultság/FIFO tiltása, forráscsoportok,
konkrét futásra szűrt teljes összesítés és megváltozott futás elutasítása.
A lezárt r21 és korábbi folytatócsomagok változatlanok.

```bash
sudo python3 /srv/docker/homecontrol/scripts/audit_release/summarize_r21_baseline_failure.py
```

Ez csak diagnosztika; a kimenete megosztható. A korábbi kapacitásfolytató egyszeri
root indítása már megtörtént, ezért annak újraindítása nem megfelelő következő lépés.
A hiba konkrét okának megismerése és az ehhez kötött folytatás még függő.
46 Ellenőrzött; HC-41 és HC-43 Folyamatban; az audit éles átadása nincs lezárva.
