# r21 – repository-előellenőrzés megállt

REPAIR-072, 2026-11-02. Az aktív csomag továbbra is r18.

A felhasználó elindította az r21 aktiválását. Az inaktív image-cache példányok
SHA-256 ellenőrzése és összekapcsolása sikeres: négy korábbi inode-ból egy lett,
három helyettesítéssel. A bájtok és hozzáférési jogok megőrzését az aktiváló
nyugtája igazolja; a szabad hely 9,2 GiB-ra nőtt. Mentési archívum törlése nem történt.
A külön router-probe és annak visszaolvasása sikeres volt.

Ezután a végleges repository teljes ellenőrzése `RuntimeError` hibával megállt.
Az alkalmazások előmentése és átállítása még nem indult el: nincs r21 transition,
telepített r21 runtime vagy r21 deployment-status. Az utólagos, csak olvasó ellenőrzés
mind a 16 konténer rögzített ID/image baseline-ját és az r18 736 runtime-hashét
változatlannak találta; a futó komponensek egészségesek. Az Adminer továbbra is áll.
A felsorolt mentési/ellenőrzési service-ek jelenleg inaktívak; ez nem bizonyítja,
hogy a korábbi hibapillanatban sem volt ütközés.

Az eredeti kivétel részlete root-only fájlban van, innen nem olvasható.
A részletes naplózás r21-ben csak a mentési workerbe került be; az aktiváló
közvetlen repository-előellenőrzésében a subprocess stdout/stderr továbbra is
elveszett. Ez az előkészítés hiányossága. A korábbi sikeres diagnosztikai snapshot
nem bizonyítja az új ellenőrzés sikerét; a mostani hiba oka még ismeretlen.

Külön `scripts/audit_release/diagnose_r21_precheck.py` készült. A lezárt r21 forrását,
799 lenyomatát és meglévő bizonyítékait nem módosítottuk. A diagnosztika a tényleges
fagyasztott r21 ellenőrző kódját és transport-beállításait használja, r18-baseline-t
és hiányzó átállítási állapotot követel meg. A két közös mentési lock alatt
csak repository-locklistát és teljes adatellenőrzést futtat, explicit `--no-lock`
kapcsolóval. Nem készít snapshotot, nem futtat megőrzést, unlockot, indexjavítást,
initet vagy alkalmazásátállítást. A parancsok pozitív allowlistje tiltja ezeket.

A nyers stdout/stderr külön root-private, 0600-as fájlokba kerül. A terminál és
a nyilvános összefoglaló csak kilépési kódot, hiányzó pack-/lockszámot és ellenőrzött
hibakategóriákat mutat. A részleges kimenet timeout esetén is megmarad.
A már kipróbált systemd folyamatfa-felügyelet külön diagnosztikai unitot használ.

Kilenc célzott teszt sikeres: titkos részletek visszatartása, kilépési kód,
tiltott módosító parancsok, `--no-lock`/privát kimenet, timeout részleges kimenete,
lockszám összegzése, meglévő átállítás és megváltozott runtime elutasítása,
root nélküli futtatás tiltása. A root diagnosztika innen nem indult el:
`sudo -n` helyi jelszót követel.

```bash
sudo python3 /srv/docker/homecontrol/scripts/audit_release/diagnose_r21_precheck.py
```

A pontos diagnózis a következő szükséges függőség. Az aktiválót nem ismételjük,
új aktiválási kísérletet nem készítünk a részletes eredmény vizsgálata előtt.
A javítási kör átadása függő; HC-41/43 és az AI-tiltás változatlan.
Más auditpontot nem javítottunk és nem zártunk le.

Bizonyítékok: `docs/audit-evidence/r21-precheck-20261102/`;
az aktiváló cache-nyugtája: `backups/releases/hc-audit-20261102-r21/evidence/image-cache-capacity.json`.
