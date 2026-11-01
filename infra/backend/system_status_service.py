from host_operations_client import HostOperationsClient, docker_capability_request
from worker_runtime import BoundedJobs, Busy
import concurrent.futures
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Tuple
from urllib.parse import quote


DOCKER_REQUEST_JOBS = BoundedJobs("docker-status-request", 1)
DOCKER_STATS_JOBS = BoundedJobs("docker-stats", 8)

DOCKER_STATUS_CACHE_TTL = float(os.environ.get("DOCKER_STATUS_CACHE_TTL", "30"))
DOCKER_STATUS_CACHE = {"expires_at": 0.0, "data": None}
DOCKER_STATUS_CACHE_LOCK = threading.Lock()
HARDWARE_TEMPERATURE_HISTORY = []
HARDWARE_TEMPERATURE_HISTORY_LOCK = threading.Lock()
HARDWARE_TEMPERATURE_HISTORY_WINDOW_SEC = 24 * 3600
ABOUT_SOURCE_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sql",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
ABOUT_EXCLUDED_DIRS = {
    ".git",
    ".agents",
    ".codex",
    "backups",
    "data",
    "dist",
    "node_modules",
    "postgres",
    "restore_staging",
    "__pycache__",
}
ABOUT_MODULES = [
    ("backend", "Backend", "infra/backend"),
    ("frontend", "Frontend", "infra/frontend/src"),
    ("db", "Database migrations", "infra/db"),
    ("ingest", "MQTT ingest", "apps/hc_ingest"),
    ("ai_server", "AI server", "apps/ai-server"),
    ("robot", "X10 robot", "apps/xiaomi-x10"),
    ("tuya", "Tuya poller", "apps/tuya-poller"),
    ("gree", "Gree climate", "apps/gree-climate"),
    ("growatt", "Growatt poller", "apps/ha-growatt-poller"),
    ("scripts", "Scripts", "scripts"),
    ("docs", "Docs", "docs"),
]

BACKUP_RESTORE_DEEP_DIVE = [
    {
        "title": "Cel es mentalis modell",
        "body": "A HC backup rendszer tobb retegu vedelmet ad. A helyi tar.gz archívum gyors napi mentés és kézi visszaállítási alap. A Gitea a szöveges konfigurációk verziótörténete. A restic az AI szerver HDD-jére készülő, titkosított, deduplikált, restore-grade snapshot. A havi restic check és a restore smoke test azt bizonyítja, hogy a mentés olvasható is.",
        "items": [
            "Helyi archívum: /srv/docker/homecontrol/backups/homecontrol_YYYY-MM-DD_HH-MM-SS.tar.gz.",
            "Gitea web: http://192.168.1.2:3002/homecontrol/config.",
            "Restic repository: sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol.",
            "AI HDD mount: /mnt/hc-backup, ext4 HC_BACKUP labellel.",
            "Visszaállítás első lépése mindig staging vagy /tmp próba, nem az éles fájlok felülírása.",
        ],
    },
    {
        "title": "Mit ment a helyi archívum",
        "body": "A napi és kézi backup először mindig készít egy konzisztens helyi archívumot. Ez a leggyorsabban ellenőrizhető és böngészhető mentési forma, ebből dolgozik a Backup tab restore preview része is.",
        "items": [
            "PostgreSQL dump: pg_dump custom formatban a homecontrol adatbázisról.",
            "Apps könyvtár: /srv/docker/homecontrol/apps, logok nélkül.",
            "Infra könyvtár: compose és backend/frontend konfigurációk, de futó PostgreSQL/MQTT/Zigbee runtime data nélkül.",
            "Zigbee2MQTT data külön komponensként, logok nélkül.",
            "Home Assistant mappa, ha létezik és engedélyezett.",
            "Scripts könyvtár, beleértve backup, restore, systemd és admin helper scripteket.",
            "Docker meta: konténerek, image-ek, volume-ok, networkök és fontos inspect kimenetek.",
            "Host meta: uname, hostnamectl, docker version/info, df, mount, crontab.",
            "MANIFEST.txt és SHA256SUMS.txt az archívum belső ellenőrzéséhez.",
        ],
    },
    {
        "title": "Mit ment Gitea",
        "body": "A Gitea nem teljes backup, hanem verziókövetés. Arra való, hogy lásd, mikor változott konfiguráció, script, compose fájl vagy HC web/backend forrás, és vissza tudj nézni korábbi állapotokra. Titkokat és runtime adatokat szándékosan nem visz fel.",
        "items": [
            "Remote repository: ssh://git@192.168.1.2:2222/homecontrol/config.git.",
            "Webes repo: http://192.168.1.2:3002/homecontrol/config.",
            "Mentett területek: homeassistant/config, homeassistant/docker-compose.yml, infra/docker-compose.yml, infra/backend, infra/frontend, scripts, apps, backup dokumentáció.",
            "Kizártak: .env, secrets.yaml, infra/ssh, adatbázisok, logok, cache, Home Assistant .storage, deps, tts, node_modules, dist/build, runtime capture adatok.",
            "A sync script: /srv/docker/homecontrol/scripts/sync_config_to_gitea.sh.",
            "Offsite Git mirror opcionális: ugyanaz a snapshot GitHubra vagy más külső Git remote-ra is pusholható.",
            "Offsite mezők: git_offsite_enabled, git_offsite_remote, git_offsite_branch, git_offsite_token_file, git_offsite_ssh_key.",
            "A heti backup automatikusan lefuttatja a Gitea syncet, mielőtt kötelező restic backupot készít.",
        ],
    },
    {
        "title": "Kézi Gitea workflow",
        "body": "A HC projektkönyvtárban most nem egy klasszikus Git working tree a fő munkamód, ezért a kézi workflow szűrt snapshot scriptekkel dolgozik. Ez védi a titkokat, adatbázisokat és runtime fájlokat attól, hogy véletlenül repo-ba kerüljenek.",
        "items": [
            "Webes panel: Backup tab / Gitea Control.",
            "Status / Diff: megmutatja, hogy a jelenlegi szűrt snapshot eltér-e a Gitea repo állapotától.",
            "Commit & Push: kézi commit üzenettel feltolja a friss snapshotot; ha nincs változás, nem készít üres commitot.",
            "Ha az offsite mirror engedélyezett, a Commit & Push a külső Git remote-ra is pusholja ugyanazt a snapshotot.",
            "Restore to Staging: branch/tag/commit refet klónoz a restore_staging alá, éles fájlt nem ír felül.",
            "Open Gitea: megnyitja a webes repo oldalt; privát repo esetén belépés kellhet.",
            "Státusz/diff: scripts/gitea_config_status.sh.",
            "Kézi commit/push: scripts/gitea_config_commit.sh \"Leíró commit üzenet\".",
            "Branch push: GITEA_BRANCH=teszt-valtozas scripts/gitea_config_commit.sh \"Teszt snapshot\".",
            "Nem romboló restore stagingbe: scripts/gitea_config_restore.sh main.",
            "Konkrét commit restore stagingbe: scripts/gitea_config_restore.sh 0770d86.",
            "Restore cél alapból: /srv/docker/homecontrol/restore_staging/gitea-config-YYYY-MM-DD_HH-MM-SS.",
            "A restore script nem ír felül éles fájlokat, csak stagingbe clone-ol.",
        ],
    },
    {
        "title": "Mit ment restic az AI HDD-re",
        "body": "A restic a hosszabb távú, deduplikált és titkosított snapshot réteg. Ez SFTP-n keresztül ír az AI szerver HDD-jére. Ha a napi futáskor az AI szerver alszik, a local archívum sikeres marad és a restic rész kimarad. A heti futásnál az AI elérése kötelező.",
        "items": [
            "Források: friss helyi archívum, apps, infra, homeassistant, scripts és engedélyezve Docker volume-ok.",
            "Kizárások: futó PostgreSQL data, MQTT data/log, Zigbee2MQTT log, Tuya logok, __pycache__.",
            "Jelszófájl: /etc/homecontrol/restic-password.",
            "SSH kulcs: /srv/docker/homecontrol/infra/ssh/ai_node_key.",
            "Retention: 14 daily, 8 weekly, 6 monthly snapshot.",
            "Repo check: /srv/docker/homecontrol/scripts/restic_check_ai_backup.sh.",
        ],
    },
    {
        "title": "Automatikus időzítések",
        "body": "Három systemd timer dolgozik. A napi backup a rutin mentés, a heti backup garantáltan elindítja vagy megvárja az AI szervert, a havi check pedig külön ellenőrzi a restic repo olvashatóságát.",
        "items": [
            "homecontrol-backup.timer: napi mentés 02:15-kor, restic best-effort módban.",
            "homecontrol-ai-weekly-backup.timer: heti AI HDD backup vasárnap 03:30 körül, RandomizedDelaySec miatt pár perccel késhet.",
            "homecontrol-restic-check.timer: havi első vasárnap 04:30 körül, restic check.",
            "Telepítés/frissítés: cd /srv/docker/homecontrol && sudo scripts/apply_backup_timer.sh.",
            "Állapot: systemctl list-timers 'homecontrol*backup*' 'homecontrol-restic-check*'.",
            "Napló: journalctl -u homecontrol-backup.service -n 120 --no-pager.",
        ],
    },
    {
        "title": "Kézi mentés menete",
        "body": "Kézi mentést a Backup tab Create Backup gombja vagy a systemd service indítása készít. A sikeres kézi mentés után a Backup Activity panelben látszania kell az új archívum és restic soroknak.",
        "items": [
            "UI: Backup tab -> Create Backup.",
            "UI full mentés: Backup tab -> Run Full AI Backup.",
            "A full AI backup webes gomb a backups/full-ai-backup.request fájlt frissíti, ezt a host systemd path helper veszi észre.",
            "Host CLI: sudo systemctl start homecontrol-backup.service.",
            "Közvetlen script: cd /srv/docker/homecontrol && sudo scripts/backup_hc.sh.",
            "Siker jele: backup.log végén '== Backup kész: ... ==' sor.",
            "Ha az AI szerver alszik, napi módban a logban 'Restic snapshot kihagyva' jelenhet meg; ez nem local backup hiba.",
            "Ha kötelező AI mentést akarsz: sudo systemctl start homecontrol-ai-weekly-backup.service.",
        ],
    },
    {
        "title": "Heti AI HDD backup folyamata",
        "body": "A heti feladat a legerősebb automatizált mentési út. Ha az AI szerver már megy, használja és bekapcsolva hagyja. Ha nem elérhető, felébreszti, lefuttatja a Gitea/restic mentést, majd siker után leállíthatja.",
        "items": [
            "1. A script SSH-n ellenőrzi, hogy az AI szerver már elérhető-e.",
            "2. Ha nem elérhető, Backend AI node API wake kérést küld.",
            "3. A script SSH-n várja az AI szervert legfeljebb 900 másodpercig.",
            "4. Lefut a sync_config_to_gitea.sh, amely pusholja a szűrt konfigurációkat Gitea-ba és engedélyezve GitHubra.",
            "5. Remote oldalon lefut az apps/ai-node/backup_gitea.sh, ha elérhető.",
            "6. RESTIC_REQUIRED=true mellett elindul a backup_hc.sh.",
            "7. Ha a restic repo vagy AI HDD nem elérhető, a heti feladat hibával áll le.",
            "8. Siker után csak akkor kér automatikus leállítást, ha ő ébresztette fel az AI szervert.",
        ],
    },
    {
        "title": "Gitea belépés és ellenőrzés",
        "body": "A Gitea repo privát, ezért belépés nélkül a webes link 404-et mutathat. Ez normális. Bejelentkezés után a fájlböngészőben és commit historyban látszik, mi lett verziózva.",
        "items": [
            "Web: http://192.168.1.2:3002.",
            "Repo: http://192.168.1.2:3002/homecontrol/config.",
            "Felhasználó: a.",
            "Jelszó az AI szerveren: /mnt/hc-backup/gitea/gitea-admin-password.txt.",
            "CLI ellenőrzés: GIT_SSH_COMMAND='ssh -i /srv/docker/homecontrol/infra/ssh/ai_node_key -o BatchMode=yes -o StrictHostKeyChecking=accept-new' git ls-remote ssh://git@192.168.1.2:2222/homecontrol/config.git refs/heads/main.",
            "Ha belépés nélkül 404 van, de SSH ls-remote működik, a repo rendben van.",
        ],
    },
    {
        "title": "Nem romboló restore smoke test",
        "body": "A restore smoke test nem ír éles HomeControl fájlokra. Ideiglenes /tmp könyvtárban ellenőrzi a helyi archívumot, a Gitea elérést és resticből egy minimális visszahozást.",
        "items": [
            "Parancs: cd /srv/docker/homecontrol && sudo scripts/restore_smoke_test.sh.",
            "Első ellenőrzés: tar -tzf, MANIFEST.txt és SHA256SUMS.txt megléte.",
            "Második ellenőrzés: Gitea repo elérhető-e SSH-n.",
            "Harmadik ellenőrzés: restic latest snapshotból vissza tud-e hozni legalább egy homecontrol_*.tar.gz archívumot.",
            "Sikeres kimenet vége: '== Restore smoke test kész =='.",
            "Hiba esetén az első hibasor alapján kell eldönteni, hogy local archive, Gitea vagy restic oldali probléma van.",
        ],
    },
    {
        "title": "Visszaállítás helyi archívumból",
        "body": "A legbiztonságosabb visszaállítási út a staging. Először bontsd ki a kiválasztott komponenseket stagingbe, hasonlítsd össze, majd csak a szükséges fájlokat mozgasd át az éles helyre.",
        "items": [
            "UI: Backup tab -> válassz archívumot -> Open -> Restore and file compare.",
            "Mode: staging preview. Ez a /srv/docker/homecontrol/restore_staging alá bont.",
            "Compare: kis szövegfájloknál megmutatja az aktuális és mentett verzió különbségét.",
            "In-place restore csak RESTORE megerősítéssel engedett, és nem DB dump restore-ra való.",
            "CLI kibontás: mkdir -p /tmp/hc-restore && tar -xzf /srv/docker/homecontrol/backups/homecontrol_YYYY-MM-DD_HH-MM-SS.tar.gz -C /tmp/hc-restore.",
            "Éles fájlcsere előtt állítsd le az érintett konténert vagy szolgáltatást.",
        ],
    },
    {
        "title": "PostgreSQL restore irány",
        "body": "A PostgreSQL mentés dump formában van, mert a futó adatkönyvtár vak másolása nem megbízható. Éles adatbázis visszaállítás előtt mindig teszt adatbázisba kell betölteni a dumpot.",
        "items": [
            "Dump helye archívumban: homecontrol_*/postgres/homecontrol_YYYY-MM-DD_HH-MM-SS.dump.",
            "Teszt DB: docker exec homecontrol-postgres createdb -U homecontrol homecontrol_restore_test.",
            "Dump bemásolás: docker cp /tmp/hc-restore/homecontrol_*/postgres/homecontrol_*.dump homecontrol-postgres:/tmp/homecontrol_restore_test.dump.",
            "Teszt restore: docker exec homecontrol-postgres pg_restore -U homecontrol -d homecontrol_restore_test /tmp/homecontrol_restore_test.dump.",
            "Éles restore előtt friss mentés, érintett appok leállítása, majd kontrollált DB csere kell.",
            "Ha csak konfiguráció sérült, DB restore helyett előbb Gitea vagy staging fájlrestore legyen.",
        ],
    },
    {
        "title": "Restic restore irány",
        "body": "Resticből akkor érdemes dolgozni, ha a HC szerveren elveszett vagy sérült a helyi backup root, vagy régebbi snapshot kell. Restic restore-t mindig külön target könyvtárba indíts, ne közvetlenül az éles /srv/docker/homecontrol alá.",
        "items": [
            "Snapshot lista: sudo RESTIC_REPOSITORY=sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol RESTIC_PASSWORD_FILE=/etc/homecontrol/restic-password restic snapshots.",
            "Restore külön célba: sudo RESTIC_REPOSITORY=... RESTIC_PASSWORD_FILE=... restic restore latest --target /tmp/hc-restic-restore.",
            "A repo SFTP commandot a scriptek automatikusan beállítják az SSH kulccsal; kézi restic parancsnál erre figyelni kell.",
            "Ne állíts vissza futó PostgreSQL data könyvtárat vakon; a mentési modell dump alapú DB restore-t használ.",
            "Restic check: sudo scripts/restic_check_ai_backup.sh.",
        ],
    },
    {
        "title": "Encrypted secrets bundle",
        "body": "A Git/Gitea/GitHub snapshot nem tartalmaz nyers titkokat. A katasztrófa-restore-hoz szükséges kulcsok, jelszavak és tokenek külön age-gel titkosított csomagban vannak a secrets könyvtárban.",
        "items": [
            "Gitben látható: secrets/homecontrol-secrets-latest.tar.gz.age és .sha256.",
            "Gitben látható: secrets/age-recipient.txt és secrets/manifest.txt.",
            "Gitben nem lehet nyers .env, secrets.yaml, SSH private key vagy restic password.",
            "Bundle készítés: sudo scripts/create_secrets_bundle.sh.",
            "Staging decrypt próba: sudo scripts/restore_secrets_bundle.sh.",
            "Éles secrets restore csak új gépen: sudo scripts/restore_secrets_bundle.sh --apply --confirm.",
            "A private age key külön mentett emergency adat, Gitbe nem kerülhet.",
        ],
    },
    {
        "title": "Disaster restore bootstrap v0.1",
        "body": "A scripts/bootstrap_restore_v0_1.sh friss Ubuntu szerverre készült újraépítő script. Alapból stagingben dolgozik: clone, secrets decrypt, restic restore és archive kibontás. Éles helyekre csak explicit kapcsolókkal ír.",
        "items": [
            "One-file launcher: scripts/homecontrol_restore_magic.sh.",
            "Alap age key hely one-file módban: a magic script melletti homecontrol-secrets-age-key.txt.",
            "Gyors restore: cd /tmp; curl -fsSL https://raw.githubusercontent.com/Kshma86/homecontrol/main/scripts/homecontrol_restore_magic.sh -o homecontrol_restore_magic.sh; chmod +x homecontrol_restore_magic.sh.",
            "Kulcs beillesztése: nano /tmp/homecontrol-secrets-age-key.txt.",
            "Indítás: sudo /tmp/homecontrol_restore_magic.sh --confirm-new-hc-server.",
            "Új gépen sorrend: cd /tmp; curl -fsSL https://raw.githubusercontent.com/Kshma86/homecontrol/main/scripts/homecontrol_restore_magic.sh -o homecontrol_restore_magic.sh; chmod +x homecontrol_restore_magic.sh.",
            "Másold mellé az age kulcsot: /tmp/homecontrol-secrets-age-key.txt.",
            "Teljes restore új gépen: sudo ./homecontrol_restore_magic.sh --confirm-new-hc-server.",
            "Staging-only próba: sudo ./homecontrol_restore_magic.sh --staging-only.",
            "Restore utáni ellenőrzés: sudo docker ps --format '{{.Names}} {{.Status}}' | sort, majd curl -sS http://127.0.0.1:8095/health.",
            "Régi HC-ról compare: cd /srv/docker/homecontrol && scripts/compare_restore_tree.sh a@192.168.1.161.",
            "Bootstrap közvetlen futtatásnál az age key explicit: sudo scripts/bootstrap_restore_v0_1.sh --age-key /path/to/homecontrol-secrets-age-key.txt --install-packages.",
            "Repo override: --repo-url https://github.com/Kshma86/homecontrol.git vagy ssh://git@192.168.1.2:2222/homecontrol/config.git.",
            "Éles fájlok visszaírása: --apply.",
            "Resticből visszahozott HC fájlok overlaye: --apply-restic-files.",
            "DB csere csak: --restore-db --confirm-db-replace.",
            "Konténerek indítása csak: --start.",
            "Staging könyvtárak: /tmp/homecontrol-restore-v0.1/project, secrets/rootfs, restic és archive.",
            "A v0.1 célja a sorrend automatizálása; restore után smoke test és dashboard ellenőrzés kell.",
        ],
    },
    {
        "title": "Gyakori hibák és mit jelentenek",
        "body": "A backup log első hibasora általában elég pontosan megmondja, melyik réteg állt meg. A napi backupnál az AI szerver alvása nem végzetes, a heti backupnál viszont hiba.",
        "items": [
            "Permission denied /mnt/hc-backup: az AI HDD mount jogosultságát kell ellenőrizni: owner a:a, mode 750.",
            "restic password file missing: /etc/homecontrol/restic-password nincs meg vagy nem olvasható rootként.",
            "AI server not reachable: ellenőrizd az AI szerver áramellátást, IP-t, WOL-t, SSH kulcsot.",
            "Gitea web 404: privát repo esetén belépés nélkül normális; jelentkezz be.",
            "Gitea SSH permission denied: a HC public key nincs a Gitea user SSH key listájában, vagy rossz kulccsal fut a parancs.",
            "PostgreSQL dump hiba: homecontrol-postgres konténer állapotát és pg_dump jogosultságot kell nézni.",
            "systemctl timer nem frissül: futtasd újra: sudo scripts/apply_backup_timer.sh.",
        ],
    },
    {
        "title": "Vészhelyzeti sorrend",
        "body": "Ha tényleges adatvesztés vagy konfigurációs törés van, a cél a további károsodás megállítása, majd a legkisebb szükséges visszaállítás.",
        "items": [
            "1. Ne indíts azonnal in-place restore-t.",
            "2. Készíts pillanatnyi mentést, ha a rendszer még olvasható.",
            "3. Nézd meg a Gitea commit historyt, ha konfigurációs hiba történt.",
            "4. A kiválasztott helyi archívumot stagingbe bontsd.",
            "5. Egy fájlt vagy komponenst állíts vissza, ne mindent egyszerre.",
            "6. Adatbázis problémánál először test DB restore.",
            "7. Resticből csak külön /tmp targetbe állíts vissza, onnan válogass.",
            "8. Restore után futtasd a backend/frontend health ellenőrzéseket és nézd a logokat.",
        ],
    },
]

DOCUMENTATION_MODULES = [
    {
        "key": "overview",
        "label": "HomeControl overview",
        "domain": "core",
        "module_key": "backend",
        "summary": "A HomeControl a hazai automatizalasi adatok gyujto-, dontesi- es vezerlofelulete. A fo adatforras az MQTT es a PostgreSQL adatbazis, a frontend pedig ezekbol keszit kezelheto dashboardokat.",
        "responsibilities": [
            "Osszefogja a szenzoradatokat, es egyseges API-n adja tovabb a frontendnek.",
            "A jelenlegi allapotot az hc.entity_state tablaban tartja, az idosoros mereseket az hc.measurement tablaban gyujti.",
            "A folyamatok es eszkozok kozotti kezi hozzarendelest a Function Bindings kezeli.",
            "A tabok tobbnyire kontextus-szekciokat kernek le, amelyeket a backend cache-el es frissit.",
        ],
        "prerequisites": ["PostgreSQL/pgbouncer", "MQTT broker", "backend API", "frontend kontener"],
        "outputs": ["Dashboard payloadok", "allapot- es idosoros adatok", "vezerlesi HTTP endpointok", "admin es About/Dokumentacio nezetek"],
        "files": ["infra/backend/app.py", "infra/backend/api_route_modules.py", "infra/backend/context_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "irrigation",
        "label": "Irrigation",
        "domain": "irrigation",
        "module_key": "backend",
        "device_keywords": ("irrigation", "moisture", "garden", "tank", "pump", "solar", "rain"),
        "binding_domains": ("irrigation",),
        "summary": "Az ontozesi modul a tartaly, pumpa, szelepek, eso/idojaras es kerti talajnedvesseg adataibol allit elo allapotot es javasolt ontozesi idot.",
        "responsibilities": [
            "Megmutatja a live ontozesi allapotot: tartaly, pumpa, szelepek, napelem, lokalis szenzorok.",
            "A pilot kiszamolja, hogy az idojaras es a soil moisture alapjan mennyit erdemes locsolni.",
            "Manual inditast/leallitast es szelepkonfigot ad, de a tenyleges publikacio vedett backend endpointokon at megy.",
            "Statisztikat keszit tartalyrol, pumpa fogyasztasrol, solar toltodesrol es soil moisture tortenetrol.",
        ],
        "prerequisites": ["MQTT uzenetek az irrigation ESP/Nano felol", "OpenWeather konfiguracio", "irrigation_pilot_config", "soil moisture binding"],
        "outputs": ["Irrigation tab", "Irrigation Stats tab", "pilot recommendation", "manual command ack es meresi sorok"],
        "files": ["infra/backend/irrigation_service.py", "infra/backend/mqtt_monitor_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "climate",
        "label": "Climate",
        "domain": "climate",
        "module_key": "backend",
        "device_keywords": ("climate", "gree", "klima", "klíma", "fan"),
        "binding_domains": ("climate",),
        "summary": "A klima modul a Gree split AC allapotat, celhomersekletet, modot, fogyasztasmerot es extra venti konnektort fogja ossze.",
        "responsibilities": [
            "Kiolvassa es megjeleniti a klima pillanatnyi allapotat.",
            "A fogyasztasmerovel napi/ossz energia statot keszit.",
            "Az extra venti socketet a Function Bindings alapjan tudja a klima melle kapcsolni.",
            "A scheduler V2 preflight ellenorzi, hogy a klima vezerles biztonsagosan engedelyezheto-e.",
        ],
        "prerequisites": ["Gree klima MQTT/API bridge", "climate power meter binding", "extra fan socket binding"],
        "outputs": ["Climate tab", "climate power history", "klima commandok", "scheduler climate preflight"],
        "files": ["infra/backend/climate_service.py", "apps/gree-climate", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "power_wall",
        "label": "Power Wall",
        "domain": "power_wall",
        "module_key": "backend",
        "device_keywords": ("plug", "socket", "konnektor", "power", "energia", "szerver", "nyestriaszt"),
        "binding_domains": ("power_wall", "performance", "ai"),
        "summary": "A Power Wall a kapcsolhato es fogyasztast mero konnektorok kozos felulete. Itt latszik, mi online, mi mennyit fogyaszt, es innen indithato vedett kapcsolas.",
        "responsibilities": [
            "Osszegyujti a Tuya/Zigbee socketek allapotat, teljesitmenyet es energiamero adatait.",
            "A nyestriaszto, AI gep tap, HC szerver fogyasztas es klima extra venti is innen kap eszkozt.",
            "Biztonsagi orablokkot es kapcsolasi guardot hasznal, hogy ne kapcsoljon vissza tul gyorsan.",
        ],
        "prerequisites": ["Aktiv power metric entityk", "kapcsolhato switch entityk", "Function Bindings a specialis funkciokhoz"],
        "outputs": ["Power Wall tab", "switch command endpoint", "energia es teljesitmeny tablazatok"],
        "files": ["infra/backend/power_wall_service.py", "infra/backend/energy_device_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "x10",
        "label": "X10 Robot",
        "domain": "robot",
        "module_key": "robot",
        "device_keywords": ("x10", "xiaomi", "robot"),
        "binding_domains": ("robot",),
        "summary": "Az X10 Robot modul a porszivo allapotat, terkepet, szobatakaritasi terveket es heti schedule-t kezeli.",
        "responsibilities": [
            "Megjeleniti a robot statuszt, akkut, terkepet es utolso feladatot.",
            "Szobakra bontott takaritasi tervet tud kezelni.",
            "A schedulerhez preflight es futasi tortenet tartozik.",
        ],
        "prerequisites": ["X10 MQTT bridge", "robot map adatok", "scheduler bejegyzesek"],
        "outputs": ["X10 tab", "robot commandok", "scheduler history", "map preview"],
        "files": ["infra/backend/robot_service.py", "apps/xiaomi-x10", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "scheduler",
        "label": "Scheduler",
        "domain": "scheduler",
        "module_key": "backend",
        "device_keywords": ("schedule", "scheduler", "calendar"),
        "binding_domains": ("irrigation", "climate", "power_wall"),
        "summary": "A Scheduler az idozitett es automatizalt muveletek kozos motorja. Nem csak idopontokat tarol, hanem preflight ellenorzeseket is futtat.",
        "responsibilities": [
            "Kezeli az ontozes, X10 es klima idozitett folyamatainak bejegyzeseit.",
            "Preflight listaban mutatja, hogy egy folyamat miert futtathato vagy miert blokkolt.",
            "Feature flag-ekkel vedett: kulon engedely kell a vegrehajtasi publikaciohoz.",
        ],
        "prerequisites": ["scheduler tablazatok", "HC_V2_EXECUTION_* feature flag-ek", "elerheto celmodulok"],
        "outputs": ["Scheduler tab", "preflight eredmenyek", "event/plan/execution history"],
        "files": ["infra/backend/scheduler_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "ai",
        "label": "AI",
        "domain": "ai",
        "module_key": "ai_server",
        "device_keywords": ("ai", "ollama"),
        "binding_domains": ("ai",),
        "summary": "Az AI modul a helyi/remote modell gateway statuszat, chatet, auditot es az AI gep tapellatasat fogja ossze.",
        "responsibilities": [
            "Ellenorzi az AI gateway, modell es remote node allapotat.",
            "Chat valaszt ker ugy, hogy a HC kontextusbol osszerakott roviditett adatablakot ad a modellnek.",
            "Clear funkcioval tisztithato a frontend chat context window.",
            "Az AI node power plug binding hatarozza meg, melyik konnektor kapcsolja az AI gepet.",
        ],
        "prerequisites": ["AI server/gateway", "modell elerhetoseg", "AI node power plug binding"],
        "outputs": ["AI chat", "AI admin status", "ai_chat_audit DB sorok", "model pull status"],
        "files": ["infra/backend/ai_proxy_service.py", "infra/backend/ai_node_service.py", "apps/ai-server", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "tuya",
        "label": "Tuya",
        "domain": "tuya",
        "module_key": "tuya",
        "device_keywords": ("tuya",),
        "binding_domains": ("power_wall",),
        "summary": "A Tuya modul a Tuya eszkozok pollolt allapotat es friss mereseit teszi lathatova, kulonosen a power/switch jellegu eszkozoknel.",
        "responsibilities": [
            "Tuya cloud/poller adatokat hoz be MQTT/DB iranyba.",
            "Eszkozallapotot, battery es metric sorokat jelenit meg.",
            "A Power Wall tobb kapcsolhato/fogyasztasmero eleme innen is erkezhet.",
        ],
        "prerequisites": ["Tuya poller", "Tuya eszkoz regisztracio", "entity_metric mapping"],
        "outputs": ["Tuya tab", "Power Wall input adatok", "recent measurements"],
        "files": ["apps/tuya-poller", "infra/backend/energy_device_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "solar",
        "label": "Solar / Growatt",
        "domain": "solar",
        "module_key": "growatt",
        "device_keywords": ("solar", "growatt", "pv", "battery"),
        "binding_domains": ("solar",),
        "summary": "A Solar modul a Growatt es ontozesi solar telemetriat jeleniti meg: akku, PV feszultseg, toltoaram es napi termeles jellegu adatok.",
        "responsibilities": [
            "Growatt cloud adatokat pollol es publikaltat.",
            "Solar state es measurement sorokat mutat.",
            "Az ontozesi statisztikaban is megjelennek a solar napi osszesitesek.",
        ],
        "prerequisites": ["Growatt poller", "solar metric mapping", "MQTT/DB ingest"],
        "outputs": ["Solar tab", "irrigation solar charts", "battery/PV/toltes allapot"],
        "files": ["apps/ha-growatt-poller", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "backup",
        "label": "Backup",
        "domain": "backup",
        "module_key": "backend",
        "summary": "A Backup modul a HC mentéseket, Gitea verziókövetést, AI HDD-re írt restic snapshotokat, restore próbákat és visszaállítási guardokat fogja össze. A cél nem csak az, hogy legyen mentés, hanem hogy látható és bizonyítható legyen: a mentés olvasható, visszahozható és biztonságosan használható.",
        "responsibilities": [
            "Kézi és napi helyi tar.gz archívumot készít PostgreSQL dumpból, konfigurációkból, scriptekből, Home Assistant állományokból és Docker metaadatokból.",
            "Gitea-ba szinkronizálja a kézzel szerkesztett konfigurációkat, automatizmusokat, scripteket és compose fájlokat titkok és runtime adatok nélkül.",
            "Restic-kel titkosított, deduplikált snapshotot készít az AI szerver /mnt/hc-backup HDD-jére.",
            "Kezeli az alvó AI szerver esetét: napi mentésnél best-effort, heti mentésnél kötelező wake/wait/backup.",
            "Havi restic checkkel és nem romboló restore smoke testtel ellenőrzi, hogy a mentések olvashatók.",
            "A Backup tabon listázza az archívumokat, mutatja az aktivitást, és staging restore/compare felületet ad.",
        ],
        "prerequisites": [
            "HC szerveren elérhető /srv/docker/homecontrol/backups könyvtár.",
            "Futó homecontrol-postgres konténer a pg_dump készítéshez.",
            "Telepített restic és /etc/homecontrol/restic-password jelszófájl.",
            "SSH kulcsos HC -> AI kapcsolat: /srv/docker/homecontrol/infra/ssh/ai_node_key.",
            "AI szerveren csatolt és írható /mnt/hc-backup HDD.",
            "Gitea az AI szerveren: http://192.168.1.2:3002, SSH port 2222.",
            "Telepített systemd timerek: napi backup, heti AI backup, havi restic check.",
        ],
        "outputs": [
            "Backup tab archívumlista és Activity panel.",
            "Helyi homecontrol_*.tar.gz archívumok.",
            "Gitea homecontrol/config repository.",
            "Restic snapshotok az AI HDD-n.",
            "Gitea dumpok az AI HDD /mnt/hc-backup/gitea-dumps könyvtárában.",
            "Restore staging tartalom /srv/docker/homecontrol/restore_staging alatt.",
            "backup.log és systemd journal ellenőrzési nyomok.",
        ],
        "files": [
            "infra/backend/backup_service.py",
            "infra/frontend/src/main.jsx",
            "scripts/backup_hc.sh",
            "scripts/weekly_ai_backup.sh",
            "scripts/restic_check_ai_backup.sh",
            "scripts/restore_smoke_test.sh",
            "scripts/sync_config_to_gitea.sh",
            "scripts/export_gitea_config_snapshot.sh",
            "scripts/gitea_config_status.sh",
            "scripts/gitea_config_commit.sh",
            "scripts/gitea_config_restore.sh",
            "apps/ai-node/backup_gitea.sh",
            "docs/backup-restore-runbook.md",
        ],
        "deep_dive": BACKUP_RESTORE_DEEP_DIVE,
    },
    {
        "key": "admin",
        "label": "HC Admin",
        "domain": "admin",
        "module_key": "backend",
        "summary": "A HC Admin az a hely, ahol a rendszer katalogusat es a funkcio-eszkoz hozzarendeleseket lehet rendezni.",
        "responsibilities": [
            "Eszkoz/entity/metric adminisztracio.",
            "Function Bindings: itt dontod el, melyik folyamat melyik szenzor vagy konnektor adatabol dolgozik.",
            "UI V2 tab kapcsolok es nehany rendszerbeallitas.",
        ],
        "prerequisites": ["admin API", "hc.device/entity/entity_metric tablazatok", "process_sensor_binding tabla"],
        "outputs": ["Admin bootstrap payload", "binding modositasi endpointok", "eszkoz katalogus valtozasok"],
        "files": ["infra/backend/admin_service.py", "infra/backend/process_binding_service.py", "infra/frontend/src/main.jsx"],
    },
    {
        "key": "about_docs",
        "label": "About + Documentation",
        "domain": "system",
        "module_key": "backend",
        "summary": "Az About es Documentation tabok nem vezerelnek eszkozt, hanem a rendszer onleirasat adjak: kodmeret, kontenerek, szerver, DB, modulok es mukodesi leiras.",
        "responsibilities": [
            "About: forraskod meret, modul sorok, kontenerek, szerver es adatbazis stat.",
            "Documentation: modulonkenti szoveges es dinamikus leiras.",
            "Segit gyorsan megtalalni, mi hol van es mi mire hat.",
        ],
        "prerequisites": ["system_status_service", "DB metadata", "Docker status elerhetoseg"],
        "outputs": ["About tab", "Documentation tab", "modul-adatlapok"],
        "files": ["infra/backend/system_status_service.py", "infra/frontend/src/main.jsx"],
    },
]

DOCUMENTATION_BUTTONS = {
    "overview": [
        {"name": "Sidebar tab buttons", "does": "Atvalt a kivalsztott HC tabra, es a hash URL-t is frissiti, hogy vissza lehessen nyitni ugyanazt a nezetet.", "guard": "Nincs eszkozvezerles, csak navigacio."},
        {"name": "Menu", "does": "Kis kepernyon kinyitja vagy becsukja az oldalso navigacios listat.", "guard": "Csak navigacios UI allapotot valt."},
        {"name": "Mobile/tablet status cards", "does": "Mobil/tablet dashboardon egy status kartya reszleteit nyitja ki vagy zarja be.", "guard": "Csak megjelenitest valt, parancsot nem kuld."},
        {"name": "Refresh buttons", "does": "Az adott tab friss API payloadjat keri le, es ujrarajzolja a nezetet.", "guard": "Nem indit folyamatot; csak adatot olvas."},
    ],
    "irrigation": [
        {"name": "Refresh", "does": "Ujratolti az ontozesi allapotot, szenzorokat, pilot eredmenyt es kapcsolodo bindingot.", "guard": "Csak olvasas."},
        {"name": "Start / Manual start", "does": "Manual ontozesi ciklust indit a megadott idotartammal es szelepkiosztassal.", "guard": "Backend limit, preflight es manual maximum vedheti."},
        {"name": "Stop", "does": "Leallitja a manual ontozest, majd visszaellenorzi, hogy a szelep/pumpa tenyleg zart-e.", "guard": "Tobb megerositesi probat hasznal a STOP_* beallitasok szerint."},
        {"name": "Save / Nano config", "does": "Elmenti az irrigation controller/Nano beallitasait.", "guard": "Csak ervenyes payload es ismert controller mellett mukodik."},
        {"name": "Evaluate", "does": "Az irrigation pilotot kezzel lefuttatja, hogy most milyen ontozesi javaslat szuletne.", "guard": "Dontest keszit, onmagaban nem feltetlen indit ontozest."},
        {"name": "Fetch weather", "does": "Friss OpenWeather adatot ker, amit a pilot kovetkezo kalkulacioja felhasznal.", "guard": "OpenWeather API kulcs es koordinata kell."},
        {"name": "Refresh weather", "does": "Az Irrigation Pilot tabon explicit idojaras frissitest indit es ment.", "guard": "API kulcs, koordinata es elerheto weather service kell."},
        {"name": "Test log", "does": "Az aktualis pilot kalkulaciot decision logba menti vezerlesi parancs kuldese nelkul.", "guard": "Tesztelesre valo; nem nyit szelepet."},
        {"name": "Navigator / Pilot", "does": "Atvaltja, hogy a scheduler fix navigator modban vagy pilot kalkulacioval dolgozzon.", "guard": "Csak konfig valtozas, Save config utan lesz tartos."},
        {"name": "Save config", "does": "Elmenti a pilot parametereket, peldaul talajnedvesseg es idojaras korrekciokat.", "guard": "Ervenyes szammezok es ismert sensor binding kell."},
        {"name": "24h / 7d", "does": "Az Irrigation Stats soil moisture grafikon idotavjat valtja.", "guard": "Csak frontend nezetvaltas."},
    ],
    "climate": [
        {"name": "Refresh", "does": "Frissiti a klima allapotot, fogyasztasmerot, extra venti bindingot es napi energia statot.", "guard": "Csak olvasas."},
        {"name": "Power / mode buttons", "does": "Klima bekapcsolas, kikapcsolas vagy modvaltas parancsot kuld.", "guard": "A backend csak ismert klimara es ervenyes modra engedi."},
        {"name": "On / Off", "does": "A klimat bekapcsolja vagy kikapcsolja.", "guard": "Csak elerheto klima bridge mellett mukodik."},
        {"name": "Light", "does": "A klima kijelzo/vilagitas allapotat valtja.", "guard": "A klima aktualis light allapotabol forditott parancsot kuld."},
        {"name": "Target temperature controls", "does": "A kivant celhomersekletet allitja.", "guard": "A klima altal elfogadott tartomanyra kell esnie."},
        {"name": "Apply", "does": "A draft klima beallitasokat egyben kuldi el: mod, celhomerseklet, venti, swing jellegu mezok.", "guard": "Csak ervenyes draft es nem busy allapot mellett aktiv."},
        {"name": "Extra fan toggle", "does": "A Function Bindings-ben kivalasztott extra venti konnektort kapcsolja.", "guard": "Csak akkor van ertelme, ha a climate_extra_fan_socket binding be van allitva."},
    ],
    "power_wall": [
        {"name": "Refresh", "does": "Ujratolti a kapcsolhato/fogyasztasmero eszkozok allapotat es mereseit.", "guard": "Csak olvasas."},
        {"name": "ON / OFF switch", "does": "A kivalasztott kapcsolhato entityre switch parancsot kuld.", "guard": "Csak online, kapcsolhato eszkozon mukodik; backend guard ved gyors ujrakapcsolas ellen."},
        {"name": "Device row expand/details", "does": "Megmutatja az adott eszkoz reszletes allapotat es metrikait.", "guard": "Csak UI bontas, nem vezerel."},
        {"name": "Edit display name", "does": "Szerkesztheto mezove alakitja az eszkoz megjelenitett nevet.", "guard": "Csak UI draft, Save utan mentodik."},
        {"name": "Save display name", "does": "Elmenti a Power Wall eszkoz megjelenitett nevet.", "guard": "Aktiv entity/device es nem ures nev kell."},
    ],
    "x10": [
        {"name": "Refresh", "does": "Frissiti a robot statuszt, terkepet, schedule-t es history-t.", "guard": "Csak olvasas."},
        {"name": "Start / room clean", "does": "Szoba vagy terv szerinti takaritasi parancsot keszit/kuld.", "guard": "Scheduler/preflight es feature flag-ek foghatjak."},
        {"name": "Activate map", "does": "A kivalasztott X10 terkepet aktivalja.", "guard": "Kivalasztott map id es elerheto robot bridge kell."},
        {"name": "Refresh map", "does": "A robot map listajat frissiti.", "guard": "Csak X10 bridge mellett mukodik."},
        {"name": "Start / Stop / Dock / Status / Scheduler", "does": "Kozvetlen X10 parancsokat kuld: inditas, leallitas, dokkolas, statuszkeres, schedule olvasas.", "guard": "Busy allapotban tiltott, es az X10 bridge-nek elerhetonek kell lennie."},
        {"name": "Start Capture / Stop Capture", "does": "X10 map vagy raw adat capture folyamatot indit/leallit.", "guard": "Capture kozben az ellenkezo gomb aktiv, busy allapot blokkol."},
        {"name": "Save schedule", "does": "Elmenti a heti X10 takaritasi bejegyzeseket.", "guard": "Ervenyes nap/idopont/szoba adat kell."},
        {"name": "Disable & Save", "does": "Letiltja a heti X10 schedule-t es elmenti ezt az allapotot.", "guard": "Nem torli a draftot, csak disabled allapotot ment."},
        {"name": "Schedule", "does": "Gyors szobatakaritasi idozitest hoz letre a kivalasztott szegmensekre.", "guard": "Legalabb egy szegmens kell, aktiv DND eseten tiltott."},
        {"name": "Apply Now", "does": "Az aktualis X10 takaritasi beallitasokat azonnal elkuldi.", "guard": "Csak ervenyes cleaning settings mellett."},
        {"name": "Add DND / Remove Last", "does": "A Do Not Disturb ablaklistahoz ad uj sort vagy leveszi az utolsot.", "guard": "Csak UI draft, menteshez kulon Apply/Save kell."},
        {"name": "Stop / dock jellegu parancsok", "does": "Robot parancsot kuld leallitasra vagy visszateresre, ha a felulet felkinalja.", "guard": "Csak elerheto X10 bridge mellett mukodik."},
    ],
    "scheduler": [
        {"name": "Refresh", "does": "Ujratolti a scheduler konfiguraciot, jobokat, preflightot es history-t.", "guard": "Csak olvasas."},
        {"name": "Save", "does": "Elmenti a scheduler beallitasokat vagy egy adott domain schedule listajat.", "guard": "Validalt payload es ismert domain kell."},
        {"name": "Add", "does": "Uj scheduler sort ad a kivalasztott naphoz vagy listahoz.", "guard": "Csak draft sort hoz letre, kulon Save kell."},
        {"name": "Delete", "does": "Torli a kivalasztott scheduler sort.", "guard": "Meglevo sor id kell; busy allapotban tiltott."},
        {"name": "Mode buttons", "does": "A scheduler execution modjat valasztja ki, peldaul irrigation, X10, climate vagy kombinacio.", "guard": "A tenyleges futtatast feature flag-ek tovabbra is blokkolhatjak."},
        {"name": "Simulate / Preflight", "does": "Megmutatja, hogy egy folyamat futtathato lenne-e, es hol akadna el.", "guard": "Nem publikal eszkozparancsot."},
        {"name": "Dry Run", "does": "Szimulalt scheduler futast indit, ami megmutatja a dontesi lancot.", "guard": "Nem vezerel eszkozt."},
        {"name": "Execute jellegu gombok", "does": "A V2 execution motoron keresztul tenyleges folyamatot indithat.", "guard": "HC_V2_EXECUTION_ENABLED es domain-specifikus allow flag nelkul blokkolt."},
    ],
    "ai": [
        {"name": "Refresh", "does": "Frissiti az AI gateway, modell, remote node es pull statuszt.", "guard": "Csak olvasas."},
        {"name": "Send", "does": "A chat uzenetet elkuldi az AI proxynak a roviditett HC kontextussal.", "guard": "Csak ready modell mellett aktiv."},
        {"name": "Clear", "does": "Torli a frontend AI chat context windowt es a draftot.", "guard": "Nem torol adatbazis audit sort, csak a helyi chat ablakot."},
        {"name": "Pull model", "does": "Modell letoltest indit az AI szerveren.", "guard": "AI server kapcsolat es szabad eroforras kell."},
        {"name": "AI node power", "does": "Az AI gephez rendelt konnektort kapcsolja.", "guard": "Az ai_node_power_plug binding hatarozza meg a cel eszkozt."},
        {"name": "Wake PC", "does": "Bekapcsolasi/WOL muveletet ker a tavoli AI gepre.", "guard": "MAC cim es node konfiguracio kell."},
        {"name": "Start AI / Stop AI / Restart AI", "does": "A tavoli AI stack szolgaltatasait inditja, leallitja vagy ujrainditja.", "guard": "A gepnek elerhetonek kell lennie; busy allapotban tiltott."},
        {"name": "Restart Gateway", "does": "A HomeControl AI gatewayt inditja ujra es frissiti a cache-t.", "guard": "Gateway muvelet kozben tiltott."},
        {"name": "Connect", "does": "A gatewayt a tavoli Ollama vegpontra allitja.", "guard": "Ollama URL es futo remote stack kell."},
        {"name": "Shut Down PC", "does": "Tavoli AI gep leallitast es kesleltetett aramtalanitast ker.", "guard": "Power entity binding kell; veszelyesebb muvelet, ezert kulon gomb."},
        {"name": "Use model", "does": "A listabol kivalasztott modellt beallitja aktiv chat modellnek.", "guard": "Installed vagy elerheto modellnev kell."},
        {"name": "Advanced", "does": "Kinyitja vagy becsukja a halado AI konfiguracios mezoket.", "guard": "Csak UI reszletezes."},
        {"name": "Save Config / Refresh Config", "does": "Elmenti vagy ujratolti az AI provider/model/gateway konfiguraciot.", "guard": "Valid konfiguracio es elerheto backend kell."},
    ],
    "tuya": [
        {"name": "Refresh", "does": "Ujratolti a Tuya eszkozok allapotat, battery listat es friss mereseket.", "guard": "Csak olvasas."},
        {"name": "Switch buttons", "does": "Tuya kapcsolhato eszkoz allapotat valtja, ha a sor ezt tamogatja.", "guard": "Csak online es kapcsolhato entitynel aktiv."},
        {"name": "Row action/details", "does": "Az adott Tuya eszkoz reszletes metrikait mutatja.", "guard": "Csak UI reszletezes."},
    ],
    "solar": [
        {"name": "Refresh", "does": "Frissiti a Growatt/solar state-et, chartokat es friss mereseket.", "guard": "Csak olvasas."},
        {"name": "Chart hover / selection", "does": "Grafikonpontok ertekeit mutatja meg idoponttal.", "guard": "Csak UI interakcio."},
    ],
    "backup": [
        {"name": "Refresh", "does": "Ujratolti a backup listat, timer/source infot es restore beallitasokat.", "guard": "Csak olvasas."},
        {"name": "Create Backup", "does": "Uj backup archive kesziteset inditja.", "guard": "Backup root es szukseges fajlrendszer jogosultsag kell."},
        {"name": "Run Full AI Backup", "does": "Full AI HDD mentest ker: Gitea sync, Gitea dump, kotelezo restic backup es opcionális AI leallitas.", "guard": "Ha az AI szerver mar ment indulasnal, bekapcsolva marad; ha a backup ebresztette, siker utan leallithatja."},
        {"name": "Gitea Status / Diff", "does": "Osszeveti az aktualis szurt HC snapshotot a Gitea repositoryval, es status/diff stat kimenetet mutat.", "guard": "Csak olvasas a repo szempontjabol; mukodo Gitea SSH kapcsolat kell."},
        {"name": "Gitea Commit & Push", "does": "Kezi commit uzenettel snapshotot keszit es pusholja a Gitea homecontrol/config repoba.", "guard": "Titkokat es runtime adatokat a snapshot exporter kizar; ha nincs valtozas, nincs ures commit."},
        {"name": "Gitea Restore to Staging", "does": "Branch, tag vagy commit refet klonoz a restore_staging ala osszehasonlitashoz.", "guard": "Nem ir felul eles fajlt; visszamasolas csak kulon, kezi dontes utan."},
        {"name": "Open Gitea", "does": "Megnyitja a webes Gitea repository oldalt.", "guard": "Privat repo eseten bejelentkezes kellhet."},
        {"name": "Open", "does": "A kivalasztott backup tartalmat listazza.", "guard": "Kivalasztott backup kell."},
        {"name": "Save settings", "does": "Elmenti a backup/restore beallitasokat.", "guard": "Validalt admin payload kell."},
        {"name": "Compare", "does": "A kivalasztott fajlt osszehasonlitja az aktualis workspace verzioval.", "guard": "Kivalasztott fajl vagy path kell."},
        {"name": "Prev / Next", "does": "A diff talalatcsoportok kozott leptet.", "guard": "Csak akkor aktiv, ha van diff group."},
        {"name": "Restore", "does": "A kivalasztott archive alapjan visszaallitasi folyamatot indit vagy stagingbe bont.", "guard": "In-place restore kulon guardot es beallitast igenyel."},
    ],
    "admin": [
        {"name": "Refresh", "does": "Ujratolti az admin bootstrap adatokat: eszkozok, entityk, metrikak, bindingok.", "guard": "Csak olvasas."},
        {"name": "Save device/entity", "does": "Eszkozt, entityt vagy metrikat hoz letre/modosit.", "guard": "Kotelezo mezok es egyedi azonositok kellenek."},
        {"name": "Auto", "does": "Eszkoz cimbol/topicbol automatikusan kitolti a topic mezot, ahol ez ertelmezheto.", "guard": "Csak ismert cimformatumnal ad jo eredmenyt."},
        {"name": "Register Device / Update Device", "does": "Uj eszkozt regisztral vagy meglvo eszkozt frissit entityvel egyutt.", "guard": "Device id, nev, platform es entity adatok validalva vannak."},
        {"name": "Save Metric", "does": "Entity metric mappingot hoz letre vagy frissit.", "guard": "Entity es metric key kell."},
        {"name": "Function Bindings select/save", "does": "Egy folyamatot egy konkret entityhez rendel, peldaul soil moisture vagy AI power plug.", "guard": "Csak az adott funkciohoz elfogadhato metric candidate valaszthato."},
    ],
    "about_docs": [
        {"name": "Refresh About", "does": "Ujraszamolja a forraskod, kontener, szerver es adatbazis statisztikakat.", "guard": "Csak olvasas, de Docker/DB metadata kellhet."},
        {"name": "Refresh Documentation", "does": "Ujratolti a modul-katalogust es a dinamikus eszkoz/binding listakat.", "guard": "Csak olvasas."},
        {"name": "Module buttons", "does": "A bal oldali listaban modult valaszt, es a jobb oldali adatlap tartalmat csereli.", "guard": "Csak UI navigacio."},
        {"name": "Issues / Requests", "does": "A Notes uj bejegyzes tipusat valasztja ki.", "guard": "Csak draft tipus."},
        {"name": "Add", "does": "Uj issue/request bejegyzest ment.", "guard": "Ures szoveget nem enged."},
        {"name": "Done checkbox", "does": "Egy note kesz/allapot jeloleset menti.", "guard": "Meglevo note id kell."},
        {"name": "Delete note", "does": "Torli a kivalasztott note-ot.", "guard": "Meglevo note id kell; a UI optimistan frissit, hiba eseten visszaallit."},
    ],
}


def read_proc_stat_cpu():
    with open("/proc/stat", "r", encoding="utf-8") as handle:
        parts = handle.readline().split()
    values = [int(value) for value in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def system_cpu_percent():
    try:
        idle_a, total_a = read_proc_stat_cpu()
        time.sleep(0.08)
        idle_b, total_b = read_proc_stat_cpu()
    except Exception as exc:
        return {"ok": False, "percent": None, "error": str(exc)}
    total_delta = total_b - total_a
    idle_delta = idle_b - idle_a
    percent = 0 if total_delta <= 0 else (1 - (idle_delta / total_delta)) * 100
    return {"ok": True, "percent": round(max(0, min(percent, 100)), 1), "error": ""}


def system_memory():
    try:
        values = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        if not total or available is None:
            raise ValueError("MemTotal or MemAvailable is missing")
        used = total - available
        return {
            "ok": True,
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "percent": round((used / total) * 100, 1),
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "total_bytes": None, "available_bytes": None, "used_bytes": None, "percent": None, "error": str(exc)}


def read_sysfs_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def sysfs_temperature_c(raw: str) -> Optional[float]:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not (-100000 <= value <= 200000):
        return None
    if abs(value) > 250:
        value = value / 1000.0
    return round(value, 1)


def hardware_sensor_text(sensor: Dict[str, Any]) -> str:
    return " ".join([sensor.get("chip") or "", sensor.get("label") or "", sensor.get("display_name") or ""]).lower()


def append_hardware_temperature_history(ts: str, cpu_temperature_c: Optional[float], chipset_temperature_c: Optional[float]):
    timestamp = datetime.fromisoformat(ts).timestamp()
    cutoff = timestamp - HARDWARE_TEMPERATURE_HISTORY_WINDOW_SEC
    with HARDWARE_TEMPERATURE_HISTORY_LOCK:
        HARDWARE_TEMPERATURE_HISTORY.append({
            "ts": ts,
            "cpu_temperature_c": cpu_temperature_c,
            "chipset_temperature_c": chipset_temperature_c,
        })
        fresh = [
            row for row in HARDWARE_TEMPERATURE_HISTORY
            if datetime.fromisoformat(row["ts"]).timestamp() >= cutoff
        ]
        HARDWARE_TEMPERATURE_HISTORY[:] = fresh[-2880:]
        return list(HARDWARE_TEMPERATURE_HISTORY)


def system_temperature_sensors():
    sensors = []
    seen = set()

    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        chip = read_sysfs_text(hwmon / "name") or hwmon.name
        for temp_input in sorted(hwmon.glob("temp*_input")):
            value = sysfs_temperature_c(read_sysfs_text(temp_input))
            if value is None:
                continue
            suffix = temp_input.name.removeprefix("temp").removesuffix("_input")
            label = read_sysfs_text(hwmon / f"temp{suffix}_label")
            display_name = f"{chip} {label}".strip() if label else chip
            sensor_id = f"hwmon:{chip}:{suffix}"
            seen.add(sensor_id)
            sensors.append({
                "id": sensor_id,
                "source": "hwmon",
                "chip": chip,
                "label": label or f"temp{suffix}",
                "display_name": display_name,
                "temperature_c": value,
                "path": str(temp_input),
            })

    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        label = read_sysfs_text(zone / "type") or zone.name
        value = sysfs_temperature_c(read_sysfs_text(zone / "temp"))
        if value is None:
            continue
        sensor_id = f"thermal:{label}"
        label_lower = label.lower()
        already_hwmon_cpu = any("coretemp" in str(item.get("chip") or "").lower() for item in sensors)
        duplicate_chip = any(label_lower in {str(item.get("chip") or "").lower(), str(item.get("display_name") or "").lower()} for item in sensors)
        duplicate_cpu_zone = already_hwmon_cpu and any(part in label_lower for part in ["x86_pkg", "cpu", "pkg"])
        if sensor_id in seen or duplicate_chip or duplicate_cpu_zone:
            continue
        sensors.append({
            "id": sensor_id,
            "source": "thermal",
            "chip": label,
            "label": label,
            "display_name": label,
            "temperature_c": value,
            "path": str(zone / "temp"),
        })

    cpu_package_candidates = [
        item for item in sensors
        if any(
            part in hardware_sensor_text(item)
            for part in ["pkg", "package", "x86_pkg", "tctl", "tdie"]
        )
    ]
    cpu_candidates = [
        item for item in sensors
        if any(
            part in hardware_sensor_text(item)
            for part in ["coretemp", "k10temp", "cpu", "tctl", "tdie"]
        )
    ]
    chipset_candidates = [
        item for item in sensors
        if any(
            part in hardware_sensor_text(item)
            for part in ["pch", "chipset", "cannonlake", "soc"]
        )
    ]
    primary_cpu = max(cpu_package_candidates or cpu_candidates, key=lambda item: item.get("temperature_c") or -999) if (cpu_package_candidates or cpu_candidates) else None
    primary_chipset = max(chipset_candidates, key=lambda item: item.get("temperature_c") or -999) if chipset_candidates else None
    display_sensors = []
    if primary_cpu:
        display_sensors.append({**primary_cpu, "id": "cpu", "display_name": "CPU"})
    if primary_chipset:
        display_sensors.append({**primary_chipset, "id": "chipset", "display_name": "Chipset"})
    generated_at = datetime.now().isoformat()
    history = append_hardware_temperature_history(
        generated_at,
        primary_cpu.get("temperature_c") if primary_cpu else None,
        primary_chipset.get("temperature_c") if primary_chipset else None,
    )

    return {
        "ok": bool(display_sensors),
        "generated_at": generated_at,
        "cpu_temperature_c": primary_cpu.get("temperature_c") if primary_cpu else None,
        "cpu_sensor_id": primary_cpu.get("id") if primary_cpu else "",
        "cpu_sensor_name": primary_cpu.get("display_name") if primary_cpu else "",
        "chipset_temperature_c": primary_chipset.get("temperature_c") if primary_chipset else None,
        "chipset_sensor_id": primary_chipset.get("id") if primary_chipset else "",
        "chipset_sensor_name": primary_chipset.get("display_name") if primary_chipset else "",
        "sensors": display_sensors,
        "history_24h": history,
        "summary": {
            "sensor_count": len(display_sensors),
            "raw_sensor_count": len(sensors),
            "history_samples": len(history),
            "max_temperature_c": max((item["temperature_c"] for item in display_sensors), default=None),
        },
    }


def docker_socket_containers(timeout=4):
    body, _ = docker_socket_request('GET', '/containers/json?all=1', timeout=timeout)
    containers = []
    for item in json.loads(body.decode("utf-8")):
        names = item.get("Names") or []
        containers.append(
            {
                "id": (item.get("Id") or "")[:12],
                "full_id": item.get("Id") or "",
                "name": names[0].lstrip("/") if names else "-",
                "image": item.get("Image"),
                "service": (item.get("Labels") or {}).get("com.docker.compose.service") or "",
                "state": item.get("State"),
                "status": item.get("Status"),
            }
        )
    return containers


def docker_cpu_percent(stats: Dict[str, Any]) -> Optional[float]:
    try:
        cpu_stats = stats.get("cpu_stats") or {}
        precpu_stats = stats.get("precpu_stats") or {}
        cpu_delta = (cpu_stats.get("cpu_usage") or {}).get("total_usage", 0) - (precpu_stats.get("cpu_usage") or {}).get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
        online_cpus = cpu_stats.get("online_cpus") or len((cpu_stats.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
        if cpu_delta <= 0 or system_delta <= 0:
            return 0.0
        return round((cpu_delta / system_delta) * online_cpus * 100, 2)
    except Exception:
        return None


def docker_network_bytes(stats: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    networks = stats.get("networks") or {}
    if not networks:
        return None, None
    rx = sum(int(item.get("rx_bytes") or 0) for item in networks.values())
    tx = sum(int(item.get("tx_bytes") or 0) for item in networks.values())
    return rx, tx


def docker_block_bytes(stats: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    entries = (stats.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
    if not entries:
        return None, None
    read = sum(int(item.get("value") or 0) for item in entries if str(item.get("op") or "").lower() == "read")
    write = sum(int(item.get("value") or 0) for item in entries if str(item.get("op") or "").lower() == "write")
    return read, write


def docker_container_live_stats(container_id: str, timeout=2.5) -> Dict[str, Any]:
    return HostOperationsClient().call('stats',container=container_id,timeout=timeout)


def docker_log_stream_text(raw: bytes) -> str:
    if not raw:
        return ""
    chunks = []
    index = 0
    framed = False
    while index + 8 <= len(raw):
        stream_type = raw[index]
        size = int.from_bytes(raw[index + 4 : index + 8], "big")
        if stream_type not in (1, 2) or size < 0 or index + 8 + size > len(raw):
            break
        framed = True
        index += 8
        chunks.append(raw[index : index + size])
        index += size
    if framed:
        return b"".join(chunks).decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def docker_debug_log_sources():
    containers = docker_socket_containers()
    if containers is None:
        return {"ok": False, "logs": [], "error": "docker socket is not available"}
    rows = []
    for container in sorted(containers, key=lambda item: str(item.get("name") or "")):
        rows.append(
            {
                "id": container.get("id") or "",
                "name": container.get("name") or "-",
                "service": container.get("service") or "",
                "image": container.get("image") or "",
                "state": container.get("state") or "",
                "status": container.get("status") or "",
            }
        )
    return {"ok": True, "logs": rows, "error": ""}


def docker_debug_container_log(container_ref: str, tail: int = 300):
    containers = docker_socket_containers()
    if containers is None:
        return {"ok": False, "error": "docker socket is not available", "lines": [], "text": ""}
    container_ref = str(container_ref or "").strip()
    selected = next(
        (
            item
            for item in containers
            if container_ref in {item.get("id"), item.get("full_id"), item.get("name"), item.get("service")}
        ),
        None,
    )
    if not selected:
        return {"ok": False, "error": "unknown log source", "lines": [], "text": ""}
    tail = max(20, min(3000, int(tail or 300)))
    encoded_id = quote(selected.get("full_id") or selected.get("id") or selected.get("name"), safe="")
    response, _ = docker_socket_request("GET", f"/containers/{encoded_id}/logs?stdout=1&stderr=1&timestamps=1&tail={tail}", timeout=6)
    text = docker_log_stream_text(response).replace("\r\n", "\n")
    lines = text.splitlines()
    return {
        "ok": True,
        "source": {
            "id": selected.get("id") or "",
            "name": selected.get("name") or "-",
            "service": selected.get("service") or "",
            "image": selected.get("image") or "",
            "state": selected.get("state") or "",
            "status": selected.get("status") or "",
        },
        "tail": tail,
        "line_count": len(lines),
        "lines": lines,
        "text": text,
    }


def decode_chunked_body(body: bytes) -> bytes:
    decoded = bytearray()
    rest = body
    while rest:
        size_raw, _, rest = rest.partition(b"\r\n")
        if not size_raw:
            break
        size = int(size_raw.split(b";", 1)[0], 16)
        if size == 0:
            break
        decoded.extend(rest[:size])
        rest = rest[size + 2 :]
    return bytes(decoded)


def docker_socket_request(method: str, path: str, body: Optional[bytes] = None, content_type: str = "application/json", timeout: float = 30):
    return docker_capability_request(method,path,body,content_type,timeout)


def docker_exec_capture(container: str, command: Iterable[str]) -> bytes:
    raise RuntimeError('General Docker exec is not available to the API')


def docker_container_status():
    with DOCKER_STATUS_CACHE_LOCK:
        if DOCKER_STATUS_CACHE['data'] is not None and DOCKER_STATUS_CACHE['expires_at'] > time.monotonic():
            return DOCKER_STATUS_CACHE['data']
    deadline = time.monotonic() + 4
    try:
        future = DOCKER_REQUEST_JOBS.submit(_build_docker_container_status, deadline)
        return future.result(timeout=max(.001, deadline-time.monotonic()))
    except (Busy, concurrent.futures.TimeoutError):
        return {'ok': False, 'containers': [], 'error': 'docker status deadline or capacity exhausted'}


def _build_docker_container_status(deadline):
    now = time.monotonic()
    with DOCKER_STATUS_CACHE_LOCK:
        if DOCKER_STATUS_CACHE["data"] is not None and DOCKER_STATUS_CACHE["expires_at"] > now:
            return DOCKER_STATUS_CACHE["data"]

    result = None
    try:
        socket_containers = docker_socket_containers(timeout=max(.001, deadline-time.monotonic()))
        if socket_containers is not None:
            pending = {}
            todo = iter(c for c in socket_containers if c.get('state') == 'running')
            exhausted = False
            while time.monotonic() < deadline:
                while len(pending) < 8 and not exhausted:
                    container = next(todo, None)
                    if container is None:
                        exhausted = True
                        break
                    container_id = container.get('full_id') or container.get('id') or container.get('name')
                    try:
                        future = DOCKER_STATS_JOBS.submit(
                            lambda cid=container_id: docker_container_live_stats(cid, timeout=max(.001, min(2.5, deadline-time.monotonic()))))
                    except Busy:
                        container['stats_error'] = 'docker stats capacity exhausted'
                        continue
                    pending[future] = container
                if not pending:
                    break
                done, _ = concurrent.futures.wait(pending, timeout=max(0, deadline-time.monotonic()),
                                                  return_when=concurrent.futures.FIRST_COMPLETED)
                if not done:
                    break
                for future in done:
                    container = pending.pop(future)
                    try:
                        container.update(future.result())
                    except Exception as exc:
                        container['stats_error'] = str(exc)
            for future, container in pending.items():
                container['stats_error'] = 'docker stats timeout'
                future.cancel()
            for container in todo:
                container['stats_error'] = 'docker stats deadline exceeded before dispatch'
            for container in socket_containers:
                container.pop("full_id", None)
            result = {"ok": True, "containers": socket_containers, "error": ""}
    except Exception as exc:
        socket_error = str(exc)
    else:
        socket_error = ""

    if result is not None:
        with DOCKER_STATUS_CACHE_LOCK:
            DOCKER_STATUS_CACHE["data"] = result
            DOCKER_STATUS_CACHE["expires_at"] = time.monotonic() + DOCKER_STATUS_CACHE_TTL
        return result

    return {"ok": False, "containers": [], "error": socket_error or "Host executor is unavailable"}


class SystemStatusService:
    def __init__(
        self,
        fetch_all: Callable[..., Any],
        fetch_one: Callable[..., Any],
        mqtt_monitor: Any,
        api_performance_log: Callable[..., Any],
        cached_api_payload: Callable[..., Any],
        server_power_history_payload: Callable[[], Dict[str, Any]],
        latest_backup_info: Callable[[], Dict[str, Any]],
        safety_worker_enabled: bool,
        worker_status: Callable[[], Dict[str, Any]] = None,
    ):
        self.fetch_all = fetch_all
        self.fetch_one = fetch_one
        self.mqtt_monitor = mqtt_monitor
        self.api_performance_log = api_performance_log
        self.cached_api_payload = cached_api_payload
        self.server_power_history_payload = server_power_history_payload
        self.latest_backup_info = latest_backup_info
        self.safety_worker_enabled = safety_worker_enabled
        self.worker_status = worker_status

    def debug_log_sources(self):
        return docker_debug_log_sources()

    def debug_container_log(self, container_ref: str, tail: int = 300):
        return docker_debug_container_log(container_ref, tail=tail)

    def about_source_stats(self):
        root = Path(os.environ.get("HC_REPO_ROOT", "/srv/docker/homecontrol"))

        def count_path(path: Path):
            stats = {"files": 0, "lines": 0, "bytes": 0}
            if not path.exists():
                return stats
            for current_root, dirs, files in os.walk(path):
                dirs[:] = [name for name in dirs if name not in ABOUT_EXCLUDED_DIRS]
                for filename in files:
                    file_path = Path(current_root) / filename
                    if file_path.suffix.lower() not in ABOUT_SOURCE_EXTENSIONS:
                        continue
                    try:
                        raw = file_path.read_bytes()
                    except OSError:
                        continue
                    stats["files"] += 1
                    stats["bytes"] += len(raw)
                    stats["lines"] += raw.count(b"\n") + (0 if raw.endswith(b"\n") or not raw else 1)
            return stats

        modules = []
        totals = {"files": 0, "lines": 0, "bytes": 0}
        for key, label, relative_path in ABOUT_MODULES:
            stats = count_path(root / relative_path)
            module = {"key": key, "name": label, "path": relative_path, **stats}
            modules.append(module)
            for field in totals:
                totals[field] += stats[field]
        return {
            "root": str(root),
            "module_count": sum(1 for item in modules if item["files"] > 0),
            "modules": modules,
            "totals": totals,
        }

    def about_inventory_stats(self):
        device_summary = self.fetch_one(
            """
            select
              count(*)::int as devices_total,
              count(*) filter (where is_active)::int as devices_active,
              count(distinct platform)::int as platform_count,
              count(distinct nullif(model, ''))::int as model_count
            from hc.device
            """
        ) or {}
        entity_summary = self.fetch_one(
            """
            select
              count(*)::int as entities_total,
              count(*) filter (where is_active)::int as entities_active
            from hc.entity
            """
        ) or {}
        sensor_types = self.fetch_all(
            """
            select
              d.platform,
              coalesce(nullif(d.model, ''), nullif(d.manufacturer, ''), d.platform::text, 'unknown') as type,
              count(distinct d.id)::int as device_count,
              count(distinct e.id)::int as entity_count,
              string_agg(distinct d.name, ', ' order by d.name) as examples,
              string_agg(distinct d.location, ', ' order by d.location) filter (where nullif(d.location, '') is not null) as locations,
              array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
            from hc.device d
            left join hc.entity e on e.device_id = d.id
            left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled
            where d.is_active
            group by d.platform, coalesce(nullif(d.model, ''), nullif(d.manufacturer, ''), d.platform::text, 'unknown')
            order by device_count desc, type
            """
        )
        metric_types = self.fetch_all(
            """
            select
              em.metric_key,
              count(distinct em.entity_id)::int as entity_count
            from hc.entity_metric em
            join hc.entity e on e.id = em.entity_id
            where em.is_enabled
              and e.is_active
            group by em.metric_key
            order by entity_count desc, em.metric_key
            limit 24
            """
        )
        return {
            "devices": device_summary,
            "entities": entity_summary,
            "sensor_types": [self.describe_sensor_type(row) for row in sensor_types],
            "metric_types": metric_types,
        }

    def describe_sensor_type(self, row: Dict[str, Any]):
        metrics = [str(item) for item in (row.get("metrics") or [])]
        metric_set = set(metrics)
        capabilities = []
        capability_rules = [
            ("Climate control", {"climate_power", "climate_mode", "climate_target_temperature"}),
            ("Power metering", {"power_w", "energy_kwh", "current_a", "mains_voltage_v"}),
            ("Temperature / humidity", {"temperature", "humidity"}),
            ("Soil moisture", {"soil_moisture", "dry"}),
            ("Water level", {"liquid_level_percent", "liquid_depth"}),
            ("Watering controller", {"pump_running", "valve_state", "manual_valve_state"}),
            ("Battery / link", {"battery", "battery_low", "linkquality"}),
            ("Contact / opening", {"contact"}),
            ("Leak / rain", {"water_leak"}),
            ("Robot telemetry", {"x10_robot_state", "x10_task_state", "x10_battery"}),
            ("Solar telemetry", {"solar_battery_voltage_v", "solar_charge_current_a", "solar_pv_voltage_v"}),
        ]
        for label, keys in capability_rules:
            if metric_set.intersection(keys):
                capabilities.append(label)
        return {
            **row,
            "metrics": metrics,
            "capabilities": capabilities or ["Telemetry"],
        }

    def about_server_stats(self):
        root_path = Path(os.environ.get("HC_REPO_ROOT", "/srv/docker/homecontrol"))

        def disk_payload(path: Path):
            try:
                usage = shutil.disk_usage(path)
                used = usage.total - usage.free
                return {
                    "path": str(path),
                    "total_bytes": usage.total,
                    "used_bytes": used,
                    "free_bytes": usage.free,
                    "percent": round((used / usage.total) * 100, 1) if usage.total else None,
                    "ok": True,
                    "error": "",
                }
            except Exception as exc:
                return {"path": str(path), "total_bytes": None, "used_bytes": None, "free_bytes": None, "percent": None, "ok": False, "error": str(exc)}

        cpu_info = {}
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        break
                    key, _, value = line.partition(":")
                    if key and value:
                        cpu_info[key.strip().lower()] = value.strip()
        except Exception:
            cpu_info = {}

        uptime_sec = None
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as handle:
                uptime_sec = int(float(handle.readline().split()[0]))
        except Exception:
            uptime_sec = None

        try:
            load_avg = [round(value, 2) for value in os.getloadavg()]
        except Exception:
            load_avg = []

        return {
            "hostname": socket.gethostname(),
            "cpu": {
                "architecture": os.uname().machine if hasattr(os, "uname") else "",
                "vendor": cpu_info.get("vendor_id") or cpu_info.get("cpu implementer") or "",
                "model": cpu_info.get("model name") or cpu_info.get("hardware") or cpu_info.get("processor") or "unknown",
                "family": cpu_info.get("cpu family") or "",
                "model_id": cpu_info.get("model") or "",
                "stepping": cpu_info.get("stepping") or "",
                "mhz": float(cpu_info["cpu mhz"]) if cpu_info.get("cpu mhz") else None,
                "cache": cpu_info.get("cache size") or "",
                "flags_count": len((cpu_info.get("flags") or cpu_info.get("features") or "").split()),
                "bogomips": float(cpu_info["bogomips"]) if cpu_info.get("bogomips") else None,
                "cores": os.cpu_count(),
                "load_avg": load_avg,
                **system_cpu_percent(),
            },
            "memory": system_memory(),
            "disk": {
                "root": disk_payload(Path("/")),
                "repo": disk_payload(root_path),
            },
            "uptime_sec": uptime_sec,
        }

    def about_database_stats(self):
        started = time.perf_counter()
        try:
            summary = self.fetch_one(
                """
                select
                  current_database() as name,
                  current_setting('server_version') as server_version,
                  current_setting('server_encoding') as encoding,
                  current_setting('TimeZone') as timezone,
                  pg_database_size(current_database())::bigint as size_bytes,
                  (select count(*)::int from information_schema.schemata where schema_name not in ('pg_catalog', 'information_schema')) as schema_count,
                  (select count(*)::int from information_schema.tables where table_schema = 'hc' and table_type = 'BASE TABLE') as table_count,
                  (select count(*)::int from pg_indexes where schemaname = 'hc') as index_count
                """
            ) or {}
            relation_summary = self.fetch_one(
                """
                select
                  count(*)::int as table_count,
                  coalesce(sum(n_live_tup), 0)::bigint as estimated_rows,
                  coalesce(sum(pg_total_relation_size(relid)), 0)::bigint as total_bytes,
                  coalesce(sum(pg_relation_size(relid)), 0)::bigint as table_bytes,
                  coalesce(sum(pg_indexes_size(relid)), 0)::bigint as index_bytes
                from pg_stat_user_tables
                where schemaname = 'hc'
                """
            ) or {}
            measurement = self.fetch_one(
                """
                select
                  (select c.reltuples::bigint
                   from pg_class c
                   join pg_namespace n on n.oid = c.relnamespace
                   where n.nspname = 'hc' and c.relname = 'measurement'
                   limit 1) as row_estimate,
                  min(ts) as first_ts,
                  max(ts) as last_ts,
                  count(*) filter (where ts >= now() - interval '24 hours')::bigint as samples_24h,
                  count(distinct entity_id) filter (where ts >= now() - interval '24 hours')::int as active_entities_24h,
                  count(distinct key) filter (where ts >= now() - interval '24 hours')::int as metric_keys_24h
                from hc.measurement
                """
            ) or {}
            top_tables = self.fetch_all(
                """
                select
                  c.relname as name,
                  c.reltuples::bigint as row_estimate,
                  pg_total_relation_size(c.oid)::bigint as total_bytes,
                  pg_relation_size(c.oid)::bigint as table_bytes,
                  pg_indexes_size(c.oid)::bigint as index_bytes
                from pg_class c
                join pg_namespace n on n.oid = c.relnamespace
                where n.nspname = 'hc'
                  and c.relkind in ('r', 'p')
                order by pg_total_relation_size(c.oid) desc
                limit 12
                """
            )
            metric_activity = self.fetch_all(
                """
                select
                  key,
                  count(*)::bigint as samples_24h,
                  count(distinct entity_id)::int as entities_24h,
                  max(ts) as last_ts
                from hc.measurement
                where ts >= now() - interval '24 hours'
                group by key
                order by samples_24h desc, key
                limit 10
                """
            )
            schema_tables = self.fetch_all(
                """
                with table_columns as (
                  select
                    table_name,
                    count(*)::int as column_count,
                    string_agg(
                      column_name || ' ' || data_type ||
                      case when is_nullable = 'NO' then ' not null' else '' end,
                      ', ' order by ordinal_position
                    ) as columns
                  from information_schema.columns
                  where table_schema = 'hc'
                  group by table_name
                ),
                primary_keys as (
                  select
                    tc.table_name,
                    string_agg(kcu.column_name, ', ' order by kcu.ordinal_position) as primary_key
                  from information_schema.table_constraints tc
                  join information_schema.key_column_usage kcu
                    on kcu.constraint_schema = tc.constraint_schema
                   and kcu.constraint_name = tc.constraint_name
                   and kcu.table_name = tc.table_name
                  where tc.table_schema = 'hc'
                    and tc.constraint_type = 'PRIMARY KEY'
                  group by tc.table_name
                ),
                foreign_keys as (
                  select
                    table_name,
                    count(*)::int as foreign_key_count
                  from information_schema.table_constraints
                  where table_schema = 'hc'
                    and constraint_type = 'FOREIGN KEY'
                  group by table_name
                )
                select
                  t.table_name as name,
                  coalesce(pk.primary_key, '') as primary_key,
                  coalesce(tc.column_count, 0) as column_count,
                  coalesce(fk.foreign_key_count, 0) as foreign_key_count,
                  coalesce(tc.columns, '') as columns
                from information_schema.tables t
                left join table_columns tc on tc.table_name = t.table_name
                left join primary_keys pk on pk.table_name = t.table_name
                left join foreign_keys fk on fk.table_name = t.table_name
                where t.table_schema = 'hc'
                  and t.table_type = 'BASE TABLE'
                order by t.table_name
                """
            )
            connections = self.postgres_connection_stats()
            return {
                "ok": True,
                **summary,
                "relation_summary": relation_summary,
                "measurement": measurement,
                "top_tables": top_tables,
                "metric_activity_24h": metric_activity,
                "schema_tables": schema_tables,
                "connections": connections,
                "response_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": "",
            }
        except Exception as exc:
            return {"ok": False, "response_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(exc)}

    def documentation_bindings(self):
        try:
            return self.fetch_all(
                """
                select
                  psb.process_key,
                  psb.updated_at,
                  e.id as entity_id,
                  e.name as entity_name,
                  e.topic_base,
                  d.name as device_name,
                  d.location,
                  d.platform,
                  coalesce(nullif(d.model, ''), nullif(d.manufacturer, ''), d.platform::text, 'unknown') as device_type
                from hc.process_sensor_binding psb
                left join hc.entity e on e.id = psb.entity_id
                left join hc.device d on d.id = e.device_id
                order by psb.process_key
                """
            )
        except Exception:
            return []

    def documentation_devices(self):
        try:
            return self.fetch_all(
                """
                select
                  d.id,
                  d.name,
                  d.location,
                  d.platform,
                  coalesce(nullif(d.model, ''), nullif(d.manufacturer, ''), d.platform::text, 'unknown') as device_type,
                  count(e.id)::int as entity_count,
                  array_agg(distinct em.metric_key order by em.metric_key) filter (where em.metric_key is not null) as metrics
                from hc.device d
                left join hc.entity e on e.device_id = d.id and e.is_active
                left join hc.entity_metric em on em.entity_id = e.id and em.is_enabled
                where d.is_active
                group by d.id, d.name, d.location, d.platform, coalesce(nullif(d.model, ''), nullif(d.manufacturer, ''), d.platform::text, 'unknown')
                order by d.location nulls last, d.name
                """
            )
        except Exception:
            return []

    def documentation_snapshot(self):
        started = time.perf_counter()
        source_by_key = {item["key"]: item for item in self.about_source_stats().get("modules", [])}
        bindings = self.documentation_bindings()
        devices = self.documentation_devices()
        binding_definitions = {
            "irrigation_soil_moisture": ("irrigation", "Irrigation soil moisture"),
            "marten_power_socket": ("power_wall", "Marten deterrent socket"),
            "climate_extra_fan_socket": ("climate", "Climate extra fan socket"),
            "climate_power_meter": ("climate", "Climate power meter"),
            "ai_node_power_plug": ("ai", "AI node power plug"),
            "hc_server_power_meter": ("performance", "HC server power meter"),
        }

        def device_matches(module, device):
            keywords = [str(item).lower() for item in module.get("device_keywords", ())]
            if not keywords:
                return False
            haystack = " ".join(
                str(device.get(field) or "")
                for field in ("name", "location", "platform", "device_type")
            ).lower()
            metrics = " ".join(str(item) for item in (device.get("metrics") or [])).lower()
            return any(keyword in haystack or keyword in metrics for keyword in keywords)

        modules = []
        for order, module in enumerate(DOCUMENTATION_MODULES):
            module_key = module.get("module_key")
            module_bindings = []
            for binding in bindings:
                process_key = binding.get("process_key")
                domain, label = binding_definitions.get(process_key, ("", process_key))
                if domain in module.get("binding_domains", ()):
                    module_bindings.append({**binding, "label": label, "domain": domain})
            module_devices = [device for device in devices if device_matches(module, device)]
            source = source_by_key.get(module_key or module["key"], {})
            modules.append(
                {
                    **module,
                    "order": order,
                    "source": source,
                    "buttons": DOCUMENTATION_BUTTONS.get(module["key"], []),
                    "bindings": module_bindings,
                    "devices": module_devices[:16],
                    "device_count": len(module_devices),
                }
            )
        return {
            "ok": True,
            "generated_at": datetime.now().isoformat(),
            "modules": modules,
            "summary": {
                "module_count": len(modules),
                "dynamic_device_count": len(devices),
                "binding_count": len(bindings),
            },
            "api": {"response_ms": round((time.perf_counter() - started) * 1000, 1)},
        }

    def about_snapshot(self):
        started = time.perf_counter()
        docker_status = docker_container_status()
        source = self.about_source_stats()
        inventory = self.about_inventory_stats()
        server = self.about_server_stats()
        database = self.about_database_stats()
        containers = docker_status.get("containers", [])
        return {
            "ok": True,
            "generated_at": datetime.now().isoformat(),
            "source": source,
            "inventory": inventory,
            "server": server,
            "database": database,
            "docker": {
                "ok": docker_status.get("ok", False),
                "error": docker_status.get("error", ""),
                "containers": containers,
                "summary": {
                    "total": len(containers),
                    "running": sum(1 for item in containers if item.get("state") == "running"),
                },
            },
            "api": {"response_ms": round((time.perf_counter() - started) * 1000, 1)},
        }

    def postgres_connection_stats(self):
        started = time.perf_counter()
        try:
            row = self.fetch_one(
                """
                select
                  count(*)::int as total,
                  count(*) filter (where state = 'active')::int as active,
                  count(*) filter (where state = 'idle')::int as idle,
                  count(*) filter (where wait_event is not null)::int as waiting
                from pg_stat_activity
                """
            )
            max_row = self.fetch_one("select setting::int as max_connections from pg_settings where name = 'max_connections'")
            return {
                "ok": True,
                "total": row["total"],
                "active": row["active"],
                "idle": row["idle"],
                "waiting": row["waiting"],
                "max": max_row["max_connections"] if max_row else None,
                "response_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": "",
            }
        except Exception as exc:
            return {"ok": False, "total": None, "active": None, "idle": None, "waiting": None, "max": None, "response_ms": None, "error": str(exc)}

    def entity_heartbeats(self):
        try:
            return self.fetch_all(
                """
                select
                  e.id,
                  e.name as entity_name,
                  d.name as device_name,
                  d.platform,
                  d.location,
                  p.status,
                  p.last_seen_ts,
                  case
                    when p.last_seen_ts is null then null
                    else extract(epoch from (now() - p.last_seen_ts))::int
                  end as age_sec
                from hc.entity e
                join hc.device d on d.id = e.device_id
                left join hc.entity_presence p on p.entity_id = e.id
                where e.is_active = true
                order by p.last_seen_ts desc nulls last, d.name, e.name
                """
            )
        except Exception:
            return []

    def background_worker_status(self):
        if self.worker_status is not None:
            status = self.worker_status()
        else:
            status = {'workers': []}
        return {**status, 'thread_count': len(threading.enumerate()),
                'jobs': list(status.get('jobs', [])) + [DOCKER_REQUEST_JOBS.status(), DOCKER_STATS_JOBS.status()]}

    def performance_snapshot(self):
        started = time.perf_counter()
        mqtt_snapshot = self.mqtt_monitor.snapshot()
        postgres = self.postgres_connection_stats()
        docker_status = docker_container_status()
        workers = self.background_worker_status()
        return {
            "ok": True,
            "generated_at": datetime.now().isoformat(),
            "cpu": system_cpu_percent(),
            "hardware_sensors": system_temperature_sensors(),
            "memory": system_memory(),
            "postgres": postgres,
            "mqtt": {
                "ok": bool(mqtt_snapshot.get("mqtt_connected")),
                "connected": bool(mqtt_snapshot.get("mqtt_connected")),
                "broker": mqtt_snapshot.get("broker"),
                "subscriptions": mqtt_snapshot.get("subscriptions", []),
                "last_error": mqtt_snapshot.get("last_error") or "",
            },
            "heartbeats": self.entity_heartbeats(),
            "docker": docker_status,
            "workers": workers["workers"],
            "thread_count": workers["thread_count"],
            "api": {
                "response_ms": round((time.perf_counter() - started) * 1000, 1),
                "db_response_ms": postgres.get("response_ms"),
            },
            "api_log": self.api_performance_log(),
            "server_power": self.cached_api_payload("performance_server_power", 60, self.server_power_history_payload),
            "backup": self.latest_backup_info(),
            "summary": {
                "docker_running": sum(1 for item in docker_status.get("containers", []) if item.get("state") == "running"),
                "docker_total": len(docker_status.get("containers", [])),
                "workers_running": sum(1 for item in workers["workers"] if item["running"]),
                "workers_total": len(workers["workers"]),
            },
        }
