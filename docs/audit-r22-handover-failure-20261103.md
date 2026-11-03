# r22 – sikeres mentés/restore után visszagörgetett záróellenőrzés

**Frissítés (REPAIR-082): a root összegző a post-boot health timer hiányzó következő
időpontját igazolta.** A szabályos systemd-futás közbeni átmenet reprodukált;
elkészült és 66 teszten átment a külön folytató.
[Aktuális állapot és indítóparancs](audit-r22-timer-continuation-20261103.md).
Az alábbi diagnosztikai kérés történeti állapot.

REPAIR-081, 2026-11-03. Az aktív kiadás ismét **hc-security-20261102-r18**.
Az r22 jóváhagyása érvényes, az éles átadás még nincs lezárva.

A felhasználó lefuttatta az egyszer használható `r22-continuation-1` indítót.
Az EXDEV-adapter sikeres: `verified_copy_after_EXDEV`, 2 006 099 033 bájt,
SHA-256 `c4efe521e1464f26715fd7c291c495527a27907e2ac11ab13aa8166f67a5abc7`.
Az új teljes r18 előmentés és izolált PG-restore után az r22 átállítása megtörtént.
Az r22 új teljes HC/Git/router mentése és külön PG-restore is sikeres:

* Run: `ed5dfbc3bf664bfaa44ef9d58f6153c8`.
* Snapshot: `e13b233aefaeb74e4be4878acb576765d1cec77a1dbac7d6f67a6ab2239fa00b`.
* Archívum SHA-256: `a92a6fe10b97e60e6a8a6c0b30a549a0010a56a8acc66f842e6e72e4e4df7e5f`.
* Archívum: 2 168 351 735 bájt, 9822 ellenőrzött fájl.

Az ellenőrzött privát laborbemenet előkészítése is sikeres; ez még nem egy új
r22 teljes bare-metal/VM restore-próba. A `deployed_and_router_restore_verified`
nyugta köztes siker. Utána az `activate.complete()` végső `capture(final=True)`
ellenőrzése `ValueError` hibát adott, és a kivételkezelő visszaállította az r18-at.
A `deployment-status.json` fázisa `previous_release_restored`; végső auditátadás
és `post-live-check.json` nem készült. A pontos privát hibaüzenet még nem olvasható
az ügynök számára: a natív `sudo -n` helyi jelszót kér.

A natív, csak olvasó utóellenőrzés bizonyítéka:
[`live-rollback.json`](audit-evidence/r22-handover-failure-20261103/live-rollback.json).
Mind a 736 r18 runtime-hash egyezik; mind a 16 konténer r18 image-et használ,
15 fut, 10 healthcheck egészséges, az öt timer aktív, backend `ok: true`.
Az AI tiltott, a routeres mentés engedélyezett. A három átállított komponens
(backend, mDNS, Growatt) konténerazonosítója a valódi visszaállítás miatt új;
a többi 13 konténer az eredeti. Az r22 telepített 805 runtime-hashe is egyezik.
Egy későbbi folytató nem követelheti vakon a három eredeti r18 konténer-ID-t.

Az eredeti r22 és a felhasznált continuation-1 megmarad; egyik aktiválását sem
ismételjük. Előbb a pontos záróhiba szükséges. A csak olvasó összegző nem indít
folyamatot vagy távoli műveletet, nem ír fájlt, nem old fel lockot és nem élesít.
Csak ismert hibaüzenetet és lezárt nyilvános komponensnevet enged ki a privát
naplóból; ismeretlen részleteket visszatart. Öt célzott teszt sikeres, köztük
titok/multiline-szűrés, symlink és túlméretes bemenet elutasítása.

Aktuális helyi diagnosztikai parancs:

```bash
sudo python3 /srv/docker/homecontrol/scripts/audit_release/summarize_r22_handover_failure.py
```

46 Ellenőrzött; HC-41 és HC-43 Folyamatban. A sikeres köztes mentési nyugták
nem igazolják az r22 jelenlegi aktivitását vagy az audit végső lezárását.
