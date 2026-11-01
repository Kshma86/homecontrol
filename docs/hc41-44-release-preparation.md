# HC-41/44 – r10 kiadási előkészítés, 2026-10-30

**Aktuális állapot, 2026-10-31: élesítve.** A felhasználó root terminálból
sikeresen telepített; DB/MQTT/hostops és új helyi mentés ellenőrzött.
X10 térkép-URL hiba, PC-kliens és fizikai átadás marad; HC-41 az ESP-kivétel
miatt folyamatban. [Éles átadás és rollback](../backups/deployments/hc-access-20261030-r10/DEPLOYMENT.md).
Az alábbi előkészítési leírás történeti állapot, a deployt ne ismételjük.

**Előkészítve, nincs élesítve.** 2026-10-31: az élesítés engedélyezett,
de a host sudo-jelszót kér; friss mentés/előellenőrzés kész, telepítés nem indult.
[Folytatás root terminálból](../backups/deployments/hc-access-20261030-r10/PENDING.md). Aktív továbbra is az r9 ingest és r8 backend/frontend.
Frissítés, 2026-10-31: a felhasználó megerősítette az ESP 192.168.1.179 címét
és a routeres DHCP-foglalást. A policy/bundle véglegesítve; a HC-35/36 is
bekerült a közös backend/frontend kiadásba. [A közös revízió ellenőrzése és korlátai](hc3536-access-combined-20261031.md). A HC-41/44 auditbizonyítékait és az
F1a/F1b lépéseket, továbbá a szükséges HC-45/F6a restore-függőséget átnéztük.
A kiadás HC-35/36 és HC-41/44 javításokat tartalmaz, a szükséges HC-45 restore-integrációval; más auditpontot nem aktivál automatikusan.

A fagyasztott csomag: `backups/releases/hc-access-20261030-r10`.
A `release.json` a források, privát fájlok és image-archívum SHA256-leltára.
Az `install.py check` sikeres, de ez integritásellenőrzés, nem élesítési engedély.
A privát könyvtár 0700; jelszó nem szerepel a dokumentációban vagy bizonyítékokban.

## Mit tartalmaz a kiadás?

- Hét kiadási image: hat Python-szolgáltatás (backend, ingest, Tuya, X10, Gree,
  HA–Growatt) és frontend. A backend/frontend együtt tartalmazza a HC-35/36
  koordinációját és érvénytelen-binding kezelését. Függőségfrissítés és DB-migráció nincs.
- Hitelesített belső MQTT 1884, hoston kizárólag 127.0.0.1:1884. Zigbee2MQTT
  saját identitást kap. Összesen 11 szerepkör előkészítve, beleértve az opcionális
  dashboardot és a csak olvasó Explorert. Grott/legacy X10 API nem aktiválódik.
- Az ESP-nek megmaradó 1883: csak a saját öntözési topicok, külön hálózati
  forrás-IP-szűréssel. A cím 192.168.1.179, a felhasználó DHCP-foglalással megerősítette.
- Nem root, csak olvasható backend, capabilityk és közvetlen Docker-socket nélkül;
  pontosan négy írható adat-/lockmount. Külön root host-végrehajtó, root:10001
  0660 socket, SO_PEERCRED-ellenőrzés, engedélyezett műveletek és privát feladatnapló.
- Öt F6 drop-in, kanonikus runner, új post-boot MQTT-probe és helyreállítási adapter.
  A közös lockfájlok inode-ja megmarad. Az AI-állapot átadásakor a korábbi függő
  szándékot töröljük és generációt váltunk; aktív mentés megállítja az átállást.

A hálózati telepítő saját `bridge hc41_r10` és `inet hc41_r10` nft-táblákban dolgozik,
egyetlen tranzakcióval; nincs globális flush vagy host sysctl-változtatás.
A natív bridge forward/output hook a közvetlen Docker-klienst és hostkimenetet is
szűri; a host IPv6 1883 elérése tiltott. Az éles IPv4-only bridge és broker-IP
előfeltételét a telepítő ellenőrzi. Docker ExecStartPre drop-in gondoskodik arról,
hogy újraindításkor a konténerek előtt felkerüljön a szűrés; a drop-in rollbackkor
is megmarad a kompatibilis policyval. [Bridge-szűrés](https://wiki.nftables.org/wiki-nftables/index.php/Bridge_filtering),
[atomi szabálycsere](https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement).

## Mentés és visszaállítás

Friss, valódi helyi teljes mentés készült:
`homecontrol_2026-10-30_19-01-45_2ca584d8dd584af5977fb9cc84c4fc40.tar.gz`.
Méret 132 458 573 byte; mind a 969 belső checksum sikeres. SHA256:
`c2c2542ac386a6d4f3a6ee23f90382d5c4d5455246c21f2d6f6ce2f23a7c2598`.
Ez a jelenlegi r9 rendszer mentése, nem az új runtime teljes restore-próbája.

A privát kiadási csomag tartalmazza a hat új és a visszaállításhoz szükséges
korábbi/infrastruktúra-image-ek offline archívumát: 21 image, 650 291 715 byte.
Az összes 241 blob SHA256-ja és a linux/amd64 platform teljes fájllánca ellenőrzött.
A többplatformos upstream indexek más architektúrái/attestationjai nem exportáltak;
a csomag a jelenlegi linux/amd64 hosthoz készült. Éles Docker-load nem történt.

Az új titkosított bundle 50 titokfájlt tartalmaz, 13 jelenlegi fájl frissített
snapshotjával; valódi age-dekódolás/ellenőrzött kibontás/SHA256 roundtrip sikeres.
Az offline image-cache külön marad, nem kerül a kis titokbundle-be.
A policy és a bundle 2026-10-31-én együtt véglegesítve: `esp_confirmed=true`,
a dekódolt bundle-ben is az igazolt ESP-cím szerepel. A jelenlegi jóváhagyási fájl
a kiadás privát könyvtárának `esp-approval.confirmed.json` fájlja; újabb confirm-esp
futtatás nem szükséges.

Telepítés után a runtime a `scripts/access_runtime/hc-access-20261030-r10`, a titkok
az `infra/ssh/hc-access-20261030-r10` alatt élnek. A fagyasztott mentési worker
az image-cache-t és a root feladatnaplót a teljes mentésbe teszi még a checksumok
lezárása előtt. A folyamatban lévő hostfeladat másolata `uncertain`; nincs visszajátszás.
A titokmanifest és a kanonikus titkosított bundle telepítése is része az átállásnak.
A restore a rögzített image-eket tölti be, telepíti a guard/hostops/F6 unitokat;
nem épít új backendimage-et. A friss host csomaglistájába bekerült az nftables.
Azonos journal ismételt helyreállítása engedett, újabb helyi feladat felülírása tiltott.

Rollbackkor a pontos korábbi Compose, image-ek, környezet, runner, bootstrap,
titokbundle, unit/drop-in fájlok és jogosultságok visszaállnak. Futó backup vagy
hostművelet esetén előbb egyeztetés kell. Archívum/journal nem törlődik, régi
AI-leállítási szándék nem éled újra. A hálózati korlátozás megmarad: kompatibilis
rollback módban az ESP mellett a Docker-alhálózat és a 192.168.1.89 fejlesztői PC
elérheti a régi brokert; más LAN-forrás tiltott. Ez a visszaállási mód tágabb
hozzáférés az ESP-only üzemnél, ezért külön szerepel az átadási ellenőrzésben.

## Ellenőrzés és bizonyítási határok

[Gépi eredmények](audit-evidence/hc41-44-release-20261030/summary.json).

- **441 kiadási backend/unit/regressziós teszt**, 0 failure/error/skip.
  Ez a közös HC-35/36 + HC-41/44 fagyasztott kiadási forrás suite-ja. További
  113 frontendteszt/build, 19 PostgreSQL/PgBouncer teszt, 5 átadási/restore-eset és
  54 célzott restore-/unitteszt sikeres; az 54-es suite átfed a 441-essel.
- Valódi izolált PostgreSQL + transaction PgBouncer + hitelesített Mosquitto:
  a kész non-root backend és ingest DB/MQTT-ready; root host-végrehajtóval az
  inventory és backup-sorbaállítás működik, idegen UID és önkényes parancs tiltott.
  A broker ténylegesen UID1883-ként olvassa a 0600 konfigurációt/jelszóadatbázist.
  A root végrehajtó Docker CLI-je szigorú fixture, nincs daemon-socket: ez nem
  valódi hostrestart-próba. Ezt az alább hivatkozott külön KVM-próba egészíti ki
  tényleges vendég-Docker és systemd végrehajtással.
- Natív nft namespace-labor: ESP DNAT engedett; idegen LAN, közvetlen Docker-peer,
  host és IPv6 proxy tiltott; 1884 érintetlen; ismételt alkalmazás és rollback
  engedélylistája sikeres. Kizárólag `unshare -Urn` namespace-ek szabályai változtak.
- Mind a hat Python-image módosított fájljai megegyeznek a fagyasztott forrással.
  A frontend valódi HTTP-indexe és HC-admin assetje a builddel egyezik. A közös
  klímakoordinátor, scoped AI-koordináció és read-only/non-root működés ellenőrzött.
- `systemd-analyze verify`: 16 unit és 9 drop-in, valamint a Docker alapunit, exit 0; hostfüggőségi/sandbox
  figyelmeztetésekkel. Éles daemon-reload/enable/start nem történt. A külön
  [HC-45 KVM-próba](hc45-vm-restore-20261030.md) valódi PID1/systemd/Docker környezetben
  igazolta a friss teljes restore-t, ismétlést, valódi mentésből új restore-t,
  a 04:27-es beállítás megőrzését, unit-rollbacket és a végleges javításokkal a rebootot.
  Ez a 2026-10-30-i, HC-35/36 nélküli jelölt bizonyítéka. A közös revízióval a
  teljes VM-bootstrap/reboot és r9→r10→r9 cutover nem lett megismételve; a mai
  új restore-egyeztetés valódi DB/Docker-állapotokkal és wiring tesztekkel ellenőrzött.
- Korábbi REPAIR-043: 15 valódi brokeres ACL/retained/LWT/reconnect/STOP-ack/
  Explorer-MQTT5 eset sikeres. Ezt nem számoltuk új mai tesztnek.
- Mind a 16 éles konténer ID/image/indulás/restartszáma és 37 védett hostfájl
  változatlan; eredeti audit, safety-forrás, MQTT-konfiguráció és r9 override megmaradt.

Az előkészítés közben javított integrációs hibák: root által létrehozott AI-state/
lock most a UID10001 API számára elérhető; symlink/FIFO/hardlink visszaélés tiltott.
A host Docker-parancs nem örökölhet távoli Docker-contextet; az üres célengedélylista
üres marad. A restore-policy/bundle és a fagyasztott restore-eszközök együtt kerülnek
a kiadásba. Ezek a HC-41/44 működéséhez szükséges korrekciók.

## A VM-próba utáni szükséges kiegészítések

Az új `restore_assets.py` a checksumolt kiválasztott archívumból előre ellenőrzi
és kiemeli az offline image-eket, hostfeladat-naplót és mentési beállítást.
A pinned PG-image a DB-csere előellenőrzése előtt betöltődik; a wrapper importja,
a Compose run kapcsolói és a friss hoston hiányzó unit kezelése javított.
A beállítás a valódi teljes mentésben is szerepel. A post-boot timer késői
telepítéskor/ismétléskor is kap következő futást, a normál telepítési manifestben is.

A host-végrehajtó unit megőrzi a bindmountolt socketkönyvtárat, és a fix nevű
socketet stop után eltávolítja. Kézi restart és SIGKILL utáni automatikus restart
után a backend újraindítása nélkül is elérhető marad.

**Átállási hatás bővült:** az első reboot címütközést mutatott. A runtime és a
rollback most mind a 11 HC bridge-endpoint jelenlegi címét rögzíti; a telepítő
a teljes hálózati leltárt ellenőrzi, idegen/módosult peer esetén megáll.
Az érintett szolgáltatások száma **13**: az eredeti nyolc mellett PostgreSQL,
PgBouncer, frontend, proxy és a HC-n futó AI API-konténer is újralétrejön.
Az öt további közül a frontend a HC-35/36 miatt új image-et kap; PostgreSQL,
PgBouncer, proxy és AI API image/környezet változatlan. DB-migráció és
függőségfrissítés nincs.
Rövid DB/API-kieséssel és a kiesés alatti QoS0 mérési üzenetek eldobásával számolni kell.
Az AI-offline/téli profil megmarad, a fizikai AI-host nem ébred fel.
Más konténert a hálózatra új felülvizsgálat nélkül ne adjunk.

A végleges csomag checksumját a VM-javítások után újrazártuk.
A teljes r9→r10→r9 cutover-tranzakció nem futott ezen VM-en; a tényleges
unit-rollback és a korábbi izolált hálózati rollback bizonyítéka külön szint.
A felügyelt átadás, fizikai eszköz- és PC-klienspróbák továbbra is kellenek.

## Hátralevő lépések

Az ESP-azonosság/fix cím megerősítése és a policy/bundle véglegesítése kész.
A privát jóváhagyás: `backups/releases/hc-access-20261030-r10/private/esp-approval.confirmed.json`.

1. Új `install.py check`, friss éles baseline-/mentésellenőrzés, felügyelt ablak,
   root hostjog és működő fizikai stop. A telepítő eltérő image/környezet,
   hálózati leltár vagy aktív backup esetén megáll.
2. Külön élesítési utasításra: `python3 scripts/access_release/install.py deploy --approval /srv/docker/homecontrol/backups/releases/hc-access-20261030-r10/private/esp-approval.confirmed.json`.
   Régi backend stop után a függő klímaventilátor-ON-ok naplózottan visszavonódnak,
   binding/policy és más ütemezett munka megmarad. A backend és frontend együtt cserélődik.
3. HC-kliensek reconnect/telemetria, fizikai STOP/visszaigazolás, kiválasztott
   bindingek és ventilátorműködés, UI és jogosultságok ellenőrzése.
4. Fejlesztői PC SSH-alagút + dashboard/Explorer jelszavas reconnect és tényleges próba.
   Hiba esetén `install.py rollback`: az új backend leállása és a friss függő
   ventilátor-ON-ok visszavonása megelőzi a korábbi backend/frontend indulását.
   Régi ON-időpontot a rollback sem támaszt fel.

Broker/kliens restartkor QoS0 üzenetvesztés lehetséges. Automatikus riasztás-ACK,
öntözésindítás és AI-ébresztés nem része az előkészítésnek. Az AI-offline/téli
profil megmarad. A teljes HC-41 csak az ESP későbbi jelszavas átállásával és a
legacy listener megszüntetésével zárható; HC-45 helyben ellenőrzött, nincs élesítve.
