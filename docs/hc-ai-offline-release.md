# Korlátozott r6 kiadás — AI-szerver nélkül

**Aktuális állapot, 2026-10-27:** felhasználói engedéllyel élesítve a meglévő
HC hoston. Az alábbi szöveg az előkészítési tervet őrzi; a végrehajtás,
ellenőrzés és kompatibilis visszaállás aktuális leírása:
[éles átadás](../backups/deployments/hc-ai-offline-20261027-r6/DEPLOYMENT.md),
AUDIT_REPAIR.md REPAIR-027. HC-31 fizikai és HC-45 VM-es full restore továbbra is nyitott.

2026-10-27. A felhasználó a korlátozott élesítés **előkészítését** kérte.
Ebben a munkában nincs élesítés vagy fizikai AI-próba.
A külön csomag: `backups/releases/hc-refactor-ai-offline-20261027-r6/`.
Az eredeti r4 csomag megmarad. A már éles nyitásérzékelős opening-events safety-javítást az r6 és a rollback is megtartja. Az inaktív r5 előkészítés leváltott, nem telepítendő (`SUPERSEDED.json`). Az auditpontok státuszát a profil nem zárja le.

## A korlátozás határa

- AI wake/WOL, SSH-parancs, shutdown és késleltetett ON/OFF tiltott; a node
  státusza `disabled`, nem tévesen online/offline hardvermegfigyelés.
- Az AI chat/gateway/model műveletei, a gateway admin-újraindítása és az AI-aljzat
  hozzárendelésének módosítása szintén tiltott. A háttérből olvasott AI-státusz
  nem indít hálózati próbát.
- A Power Wall, a Tuya kézi/automatikus kapcsolási útja és a közös MQTT publisher
  sem kapcsolhatja a rögzített 121-es AI-aljzatot. A Tuya fogyasztó külön image-e
  a fizikai device ID-t is ellenőrzi, ezért közvetlen MQTT-kérés, ID-alias vagy
  átnevezés sem ad kapcsolási jogot. A többi aljzat működése megmarad.
- Heti AI-mentés, Gitea/Git/offsite sync, restic és restic-check nem indul.
  A közös runner, a közvetlen worker és az API is ellenőriz; a régi queue-kérés
  őszinte `failed/deployment_restricted` eredménnyel fogy el, nem lesz hamis siker.
- Helyi archívum/PostgreSQL-mentés, leltár/összehasonlítás és staging-restore
  használható. Az éles fájlokra történő webes restore és restore-recovery tiltott,
  hogy régi backupból ne kerülhessen vissza korlátozás nélküli végrehajtó.
- Az operator backupbeállításait a profil nem írja át. Az effektív távoli jelzők
  hamisak, a heti AI- és restic-timer letiltott akkor is, ha a tárolt érték igaz.
  A napi helyi időpont/engedélyezés és a logkarbantartás megmarad.

A profil az image-be és a host runner mellé másolt, kötelező JSON-fájl.
Settings API vagy környezeti változó nem kapcsolja ki. Hiányzó/sérült kötelező
profil esetén az alkalmazás és a védett poller nem indul; remote műveletet
nem engedélyezünk olvasási hibára. Az AI újbóli engedélyezése később külön,
ellenőrzött kiadást igényel.

Ez alkalmazás-/végrehajtóprofil, nem általános LAN-tűzfal vagy hozzáférés-kezelési
refaktor. HC-24/41/44 és a Tuya HC-32 telemetriahibája nem lett automatikusan javítva.

## Csomag és ellenőrzés

Az r4 fagyasztott forrására célzott overlay kerül; új backend, frontend,
védett Tuya és backend-rollback image készül. Az ingest az ellenőrzött r4;
rollbackben az r3 feedbackjavítás marad. Dependencyfrissítés nincs.
Az image ID-k, forrás- és csomag-SHA-k, privát env/ciphertext hash rögzített.
A titkos értékek a `private/` könyvtárban maradnak; sem jelentésbe, sem Gitbe
nem kerülnek nyersen. Saját valódi age-bundle készül, külön offline identityvel.

Csak olvasó integritás-/Compose-ellenőrzés:

```bash
python3 /srv/docker/homecontrol/scripts/check_restricted_release.py
```

Az aktuális éles hostot csak olvasó előellenőrzés, AI-kapcsolat nélkül:

```bash
python3 /srv/docker/homecontrol/scripts/preflight_restricted_release.py
```

A csomag önálló ellenőrzője: `scripts/check_release.py` a release könyvtárában.
A bizonyítékok az `evidence/` könyvtárban vannak. A tesztfuttatók a Docker socketet
csak a host orchestrátorból használják; a laboralkalmazás nem kap éles env-et,
LAN-t, hostportot vagy Docker socketet. A Tuya-laborban a tényleges poller folyamat
és valódi broker fut, de a TinyTuya aktuátortranszport szintetikus.

## Későbbi átadás a meglévő hoston

Az előkészítés nem futtatja az alábbi műveleteket. Root/systemd telepítési jog és
külön felhasználói élesítési utasítás szükséges a tényleges átadáshoz.

1. Integritás, aktuális konténerazonosság, DB/MQTT health, szabad hely és a rögzített
   AI-binding/device ID ellenőrzése a HC helyi adataiból, AI-kapcsolat nélkül.
   Futó backup/check/restore és függő fizikai szándék rendezendő. Függő fájlrestore
   nem vihető át automatikusan egy restore-recoveryt letiltó profilba.
2. Friss privát helyi pre-cutover DB-dump és config/env/image/unit/enable-state,
   safety latch és operator policy előállapot. A régi AI request-marker/queue
   előállapota megőrzendő; az elavult AI-kérést elkülönítjük, nem indítjuk el.
   Ehhez nem használható AI-restic vagy Git-tár.
3. Régi system/user mentési timerek és source watcherek felfüggesztése, a futó
   munkák szabályos befejezésének megvárása. Régi alvó backend workerek szabályos
   konténerleállítással szűnjenek meg; az új policy nem tudja őket utólag letiltani.
4. Csak ezután kerülhetnek át a fagyasztott F6 runner/workerek/CLI/exporter és a
   hozzájuk tartozó backend Python-segédmodulok, **köztük a kötelező policy.py/json**,
   a canonical hostutakra. A legacy `backup_hc`, `weekly`, `sync_config`,
   `restic_check` belépők a profilvédett közös runner wrapperjeire cserélődnek.
   A r5 csomagba másolt források helyett nem használható az időközben módosuló munkafa.
5. 059/060/061 explicit admin migráció és hc_app/hc_lab provision az előkészített
   privát jelszavakkal; meglévő DB-n nincs baseline, adatdobás vagy újraseedelés.
   PgBouncer, backend, frontend, ingest és a védett Tuya image együtt váltandó,
   `--no-build --pull never` módban. A Tuya config/local key és naplómount megmarad.
6. A meglévő hoston az F6 telepítő normál `--apply --wait-idle` útja fut;
   **nem** a fresh/full-restore ág. User duplikációk kivezetése, installed hash,
   enable/active és következő trigger ellenőrzése. Heti AI/restic kikapcsolt;
   a neve ellenére a `full-ai-backup-request.path` a közös webes local queue-t is
   szolgálja, ezért aktív marad, de a runner a remote módot nem indítja el.
7. DB/MQTT/UI/ingest/reader-jog, operator policy és tartós safety latch ellenőrzése;
   deployment státusz `ai-offline`, AI API-k blokkoltak. Fizikai AI-próba és ACK
   nincs. A napi helyi mentési út és a timerek állapota külön igazolandó.
   Csak sikeres ellenőrzés után változhat az aktív override jelölése.

A teljes friss gépes restore indítója nem része a minősített korlátozott
átadási műveletnek. HC-45 valódi VM/systemd/offline-kulcs próbája külön nyitott.
A meglévő host frissítése és a teljes katasztrófa-restore külön bizonyítási szint.
HC-31 fizikai próba az SSD javítása után folytatható; addig az AI-funkciók tiltottak.
Ezekre nincs feltétel nélküli teljes kiadási jóváhagyás.

## Visszaállás

A külön r5 rollback backend ugyanazt a kötelező AI-profilt és MQTT-tiltást viszi.
A védett r5 Tuya image **rollbackben is marad**. Frontend: korábbi r2;
ingest: r3. A fallback UI nem kap új profillámpát, az API-k a tiltást ettől még
érvényesítik. SQL Lab és webes backup-módosítás a korábbi rollback szerződés
szerint 503; a helyi host backup tovább működhet az új F6 runnerrel.

Az additív DB-séma, hc_app/hc_lab env, közös lock és a hostprofil megmarad.
Automatikus dump-restore vagy régi, korlátozás nélküli poller/backend visszaindítása
nem rollbacklépés. Sima programrollback nem törölhet közben gyűjtött méréseket.
A host telepítő unit-előképei és a cutover privát fájlelőállapota megőrzendő;
restore-katasztrófa külön eljárás, a VM-bizonyítékot ez a próba nem helyettesíti.

Végső ellenőrzés: 756 backend regresszió, 19 profilspecifikus eset, 98 frontendteszt/build; a kiadási és rollback image-en egyenként 67 safety-eset. Az r6 tényleges image-eivel a háromfázisú izolált WSGI/PG/PgBouncer/MQTT/poller kör sikeres, AI-aktuátorhívás nélkül. A minősítés az elkülönített szoftveres próbára vonatkozik; fizikai aktuátor és valódi VM/systemd-manager nem vett részt benne.
