# Az AI SSD-hiba miatt félretett mentési ellenőrzések

2026-11-01. Felhasználói döntés: **az AI maradjon letiltva; a mentési pontokat
a routeres rendszerrel kell lezárni**. Ez nem engedély fizikai AI-ébresztésre.

| Régi korlát | Most igazolt állapot | Fennmaradó munka |
| --- | --- | --- |
| Aktuális távoli restic nem ellenőrizhető az AI nélkül | Az r15 routeres repository teljes visszaolvasása sikeres | Nincs a jelenlegi célra |
| Heti mentés, Git és megőrzés éles próbája | Mind sikeres; a törlést teljes adatellenőrzés előzi meg és követi | Nincs az r15 éles körére |
| Titkosított archívum és PostgreSQL visszaállítása | 4788 fájlchecksum és külön valódi PostgreSQL-restore sikeres | Teljes friss hostos útvonal külön |
| Friss host és valódi systemd/host IPC | A valódi r15 mentési adat + javított kód tiszta és ismételt teljes restore-ja, rebootja, root IPC-je és hibás FTP-cél próbája sikeres | Az r16 élesítése, majd az új tényleges éles snapshot ellenőrzése |
| Aktuális külső Git tartalma/története | Független mirror klón és fsck sikeres; 33 commit, 1442 történeti blob, a vizsgált hitelesítési mintákra 0 találat | 111 runtime térképfájl exportjegyzék-eltérésének r16 javítása elkészült; éles visszaellenőrzése hátravan |
| HC-31 fizikai shutdown/OFF/wake | AI letiltva, fizikai próba nem futott | Csak későbbi újraaktiválás előtt; nem minősül sikeresen teszteltnek |
| Régi AI-Gitea teljes története | A jelenlegi mentési lánc nem használja | A régi lemez története nem lett ellenőrzöttnek nyilvánítva |

Az eredeti audit és a történeti naplóbejegyzések megmaradnak. HC-15/16/20/24/26,
a globális HC-23/43 és az ESP legacy MQTT-kivétele külön feladat; ezeket az SSD
miatti mentési kérés nem zárja le.

## Már rendelkezésre álló éles bizonyíték

Kiadás: `hc-router-backup-20261101-r15`.
Mentés: `b105be08ce6943fdb3b10cdf835547ee`.
Snapshot: `b381d1287149a95a1277d4724969677bd53c11736d7eb4365f307336463b49d6`.
Archívum SHA-256: `aec568c763787a737fb9a9525f46b94806607f4e28e97c685e1428712f86f2a6`.

[Éles nyugta](../backups/releases/hc-router-backup-20261101-r15/evidence/router-live-acceptance.json),
[utóellenőrzés és időzítők](../backups/releases/hc-router-backup-20261101-r15/evidence/post-live-check.json),
[FTP-incidens lezárása](router-ftp-backup-incident-20261101.md).

## A teljes próba előkészítése

Az [előkészítő](../scripts/router_release/prepare_audit_restore.py) a közös
mentési lock alatt csak olvasó másolatot készít a titkosított routeres repositoryról,
teljes helyi restic-adatellenőrzést futtat, a jóváhagyott külső Gitből mirror klónt
készít, ellenőrzi annak objektumait és az aktuális titkosított bundle egyezését.
Ezután az operátornak ad át egy külön, 0700/0600 jogú privát laborbemenetet.
Az FTP-jelszó és a privát kulcs nem kerül a terminálra vagy a nyilvános riportba.
A termelési routeres repositoryra nem küld író parancsot.

Az eredeti előkészítéshez helyi sudo kellett a privát FTP/restic/Git
beállításokhoz. A felhasználó ezt lefuttatta. A kulcs tulajdonosellenőrzése
hibásan csak root tulajdont fogadott el root futáskor; az age-kulcs valójában
az operátoré, megfelelő 0600 joggal. Az ellenőrzést javítottuk, és az operátori
export befejezése újabb sudo nélkül sikerült. Az eredeti parancs, történeti
hivatkozásként:

```bash
sudo python3 /srv/docker/homecontrol/scripts/router_release/prepare_audit_restore.py
```

A [sikeres előkészítési riport](audit-evidence/ai-ssd-closure-20261101/input-preparation.json)
igazolja a teljes letöltött repository-adatellenőrzést, a külső Git objektumait,
a titkosított bundle egyezését és a privát bemenet átadását. Az eredeti hibát
követő folytatás csak az operátori kulcs és a publikus eszközök másolása volt;
az ellenőrzött mentéseket nem kellett újra letölteni. A privát bemenet eldobható,
a teszt befejezése után törlendő; a riport történeti bizonyítékként megmarad.

Az új KVM-gép valódi systemd PID1-et, Docker 29.1.5-öt és Compose 5.0.2-t futtat.
A HC könyvtár és az image-tár ellenőrzötten üres, HC-adat/kulcs még nincs benne.
[OS-próba](audit-evidence/ai-ssd-closure-20261101/os-ready.json),
[Ubuntu-image SHA-256](audit-evidence/ai-ssd-closure-20261101/cloud-image.json).

Az előkészített [VM-vezérlő](audit-evidence/ai-ssd-closure-20261101/lab_vm.py)
Docker network=none és QEMU restrict=on mellett indít; a vendég nem kap host
Docker-socketet. A [vendég-előkészítő](audit-evidence/ai-ssd-closure-20261101/setup_guest.py)
a tényleges, titkosított repository másolatát saját FTP-kiszolgálón, csak olvasható
adatokkal és külön ideiglenes lock-könyvtárral szolgálja ki. A helyreállítás a
vendég saját `/srv/docker/homecontrol` könyvtárát módosítja. A labor a fizikai
eszközöket és a termelési hálózatot nem érheti el. A catch-up mentési feladatokat
kizárólag a laborban külön systemd-feltétel gátolja, a timerek ellenőrizhetők.

## A valódi próba által feltárt, r16-ban javított hibák

Az r15 offline image-cache 29 image-et tartalmaz, köztük a Home Assistantot is,
de a Docker-export manifestje egyikhez sem őriz RepoTags értéket. A külön HA
Compose továbbra is a `ghcr.io/home-assistant/home-assistant:stable` nevet használja.
A korábbi r10 VM-próba előfeltételként betöltött HA-image-et használt. Az új
kód a checksum-ellenőrzött archívum Docker-metaadatából választja ki az egyetlen
megfelelő, a cache-ben ténylegesen szereplő image ID-t, és abból állítja vissza
a HA-taget. A régi és a Docker29-es táblázatformátum is tesztelt; hiányzó vagy
kétértelmű kép a fájl-/DB-csere előtt elutasítást okoz. A HA-indítás `--pull never`.

Az első teljes bootstrap a Git gyökerében levő régi `access_release` segédet
választotta a fagyasztott r15 helyett, és a kiadásazonosság ellenőrzésénél
megállt. A javítás kifejezetten a megfelelő fagyasztott kiadás segédjét hívja.

A 077-es caller umask a publikus Git-checkout SQL-fájljait is 0600/0700-ra
hozta létre. Emiatt a nem rootként futó sémaellenőrzés nem olvasta a 059 SQL-t.
A klónozás saját 022-es umaskot kapott a továbbra is 0700-as privát work-rooton
belül. Valódi Git/age első és ismételt staging tesztje igazolja a forrásfájlok
0644/0755, valamint a kulcsok/beállítások 0600 módját. A diagnosztikai VM-ben
a megfelelő forrásjogokkal a valódi séma-/ACL-migráció sikeres.

A Git eredeti exportjegyzéke 111 runtime térképfájlt is felsorolt, amelyeket
az örökölt ignore-szabályok kihagytak. A runtime térképcache most a titkosított
archívum/restic része; a publikus forrásleltár kizárja. A validált exportot külön
staging-lépés adja a Git-indexhez, és az index útvonalait egyezteti a jegyzékkel.
Egy örökölt ignore többé nem hagyhat ki csendben egy jegyzékben szereplő forrást.
Ez helyi staging-force, a távoli push továbbra sem force push.

A fagyasztott éles r15 és az eredeti audit változatlan. Az r16 csomag lezárva,
a tiszta OS-ről induló javított teljes VM-próba sikeres. A Git-próba
eredeti külső commitja és a javítások külön laborcommitja külön szerepel a
bizonyítékokban; ez nem változatlan r15 bootstrapnek tulajdonított siker.

Az előkészítő 6, a séma-/asset-/jogosultsági 23, a restore/export szerződések 27,
a mentési folyamat 29 hálózat nélküli, az aktiválás 12 és a tranzakció 16 tesztje
sikeres. A külön Git/age/umask staging teszt is sikeres. Ezek átfedő suite-ok,
nem összeadott tesztdarabszám. A cache tényleges Docker-loadja és az image-be
épített hat módosuló modul forráshash-egyezése is ellenőrzött.

[Folyamatállapot](audit-evidence/ai-ssd-closure-20261101/acceptance-progress.json).
Az r16 nincs élesítve; teljes lezárás még nem történt.

A bootstrap első javított tiszta OS-es köre parancsszinten befejeződött, de az
utóellenőrzésnél az MQTT broker nem indult: a tényleges mount az r10 privát
könyvtárát használja, a permissions lépés csak az új kiadási könyvtárat javította.
A javítás a modellben ténylegesen megadott broker- és backend-credential mountot
ellenőrzi és állítja be, csak a cold restore `restore-prepare` lépésében.
A nem hivatkozott korábbi könyvtárakat nem módosítja. Symlink/idegen útvonal
előtt nem történik chown. Az éles r15 brokerhez a munka nem nyúlt.

Az explicit broker-javítást követő diagnosztikai probe sikeres: 7 139 946 mérés,
66 entitás, 61 HC-tábla, 5 időzítő, valódi root IPC, várt non-root/read-only/no-socket
backend, offline HA-image, valamint a kiválasztott archívum és dump hash-egyezése.
Ez külön [diagnosztikai bizonyíték](audit-evidence/ai-ssd-closure-20261101/post-mqtt-correction-diagnostic.json),
nem a teljesen automatikus tiszta restore végleges elfogadása. Az újabb tiszta
OS-es teljes kör már a broker-fixet is tartalmazza, és kézi javítás nélkül sikeres.

## Lezárt helyi átvétel és élesítési határ

[Teljes VM-nyugta](audit-evidence/ai-ssd-closure-20261101/vm-acceptance.json): tiszta
OS-ről és azonos work-dirből ismételt teljes restore sikeres; a teljes vendégreboot
új boot-ID-val sikeres. A 14 alapunit és a kiadási adapterek bájtjai egyeznek,
5 időzítő aktív/engedélyezett és jövőbeli triggerrel rendelkezik. A tényleges
root IPC, a non-root/read-only/socket nélküli backend és az offline HA ellenőrzött.
Az elérhetetlen FTP-s kör nemnulla kóddal megállt, a kanonikus fájlok/unitok és
a DB-konténer változatlan maradt. A kijelölt archívum hash-e minden körben az
éles nyugtával egyezett, a dump SHA-256:
`ccbf9799f8dfe6d13967be3fe1f9a20bbb50628efbf8cca814b20155218c8f47`.

Az eredeti külső commit `d612e6e3db13e3bc836bacf7338ef879d9c50532`, a tesztelt
javítási laborcommit `014e1c2d663a746e9df6b632bc7d158d0584552a`. A funkcionális
javítások az r16 csomaggal a kiadásnév normalizálása után bájtra egyeznek.
A 711 forrásfájlos r16 csomag lezárt, élesítésre kész. A tényleges éles r16
új mentése és külső Git-visszaellenőrzése az aktiválás után következik.

[Privát laboradatok takarítása](audit-evidence/ai-ssd-closure-20261101/lab-cleanup.json):
a VM leállt, a HC-adatot tartalmazó guest lemez és a delegált age-kulcs/Git/repository
másolata törölt. A HC-adat nélküli tiszta OS-alap megmaradt az r16 utópróbájához.
[Éles utóellenőrzés](audit-evidence/ai-ssd-closure-20261101/production-after.json):
16 éles konténer változatlan, a 706 r15 forráshash és az eredeti audit egyezik,
readiness jó, failed systemd unit nincs. Az AI továbbra is letiltott.
