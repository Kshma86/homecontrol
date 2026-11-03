# HC-45 – valódi VM-es visszaállítási próba

2026-10-30. **Sikeres helyi VM-ellenőrzés; élesítés nem történt.**
A felhasználó kérésére az audit HC-45 és F6a szerinti friss hostos próbát
helyben létrehozott, eldobható KVM VM-ben végeztük el. Az éles r9/r8 rendszer
és az ESP-megerősítési kapu változatlan marad.

## Ami a próbához kellett

| Erőforrás | Használt környezet |
| --- | --- |
| Virtualizáció | KVM, külön QEMU-eszközkonténer, hostcsomag-telepítés nélkül |
| VM | 2 vCPU, 6 GiB RAM, 32 GiB virtuális lemez, külön qcow2 overlay |
| OS | Ubuntu 22.04 LTS, 20261020 cloud image, valódi systemd PID1 |
| Docker / Compose | 29.1.5 / 5.0.2, az éles hosttal egyező image-tárolási mód |
| Időzóna | Europe/Budapest, a naptári időzítések OS-előfeltétele |
| Bemenet | Ellenőrzött valós mentés, age-kulcs/bundle, fagyasztott r10 kód és offline image-ek |
| Visszaállítási forrás | A vendégen belüli valódi Git és SSH/SFTP/restic repository |

Az Ubuntu-image aláírása az Ubuntu cloud-image kulcstárával és SHA256-ja is
ellenőrzött. A QEMU külső folyamata UID1000, capabilityk nélkül fut; nincs host
Docker-socket, host rootkönyvtár vagy fizikai hálózati bridge átadva. A KVM-eszköz
és kizárólag a labor lemezkönyvtára elérhető számára.

Az üres OS csomagtelepítésekor még nincs HC-adat a vendégben. A visszaállításkor
már **Docker network=none és QEMU restrict=on** védi: HC, ESP, AI, internet és a
QEMU-host tesztkapcsolata mind tiltott. Az egyetlen SSH-forward a QEMU-konténer
saját loopback címén érhető el. A vendég saját Docker-daemonja ténylegesen működik.
[QEMU hálózati opciók](https://qemu-project.gitlab.io/qemu/system/invocation.html),
[Ubuntu-image](https://cloud-images.ubuntu.com/releases/jammy/release-20261020/),
[Docker hivatalos telepítése](https://docs.docker.com/engine/install/ubuntu/).

## Bemenet és a bizonyíték határa

A valódi r9 mentés SHA256-ja:
`c2c2542ac386a6d4f3a6ee23f90382d5c4d5455246c21f2d6f6ce2f23a7c2598`.
969 belső checksum sikeres. Az ebből vett eredeti PostgreSQL-dump SHA256-ja:
`da5025d29278f4e0212ed290eed9975b7290ab4b832fa7f37dc7388c969fcae8`.

Mivel az r10 még nincs élesítve, az első próba egy világosan jelölt, előállított
r10 restore-fixture-t használ: valós, változatlan r9 dump + előkészített r10
fájlkészlet. Az ESP címét kizárólag a laborpéldányban 192.0.2.179-re állítottuk,
a valódi age-bundle-t a labor saját restic-céljához újratitkosítottuk. Ez nem
az éles ESP azonosságának/fix címének igazolása. A termelési bundle és jelszavak
nem változtak. A Home Assistant meglévő image-e offline előfeltételként került a
vendégbe; a PostgreSQL előzetes tagjét a végső próba előtt eltávolítottuk, hogy
a recovery-image betöltését ténylegesen a bootstrap végezze.

Az első tiszta teljes restore és az azonos work-dirben végzett ismétlés
bootstrapje egyaránt sikeres. 7 006 285 mérési sor, 66 entity és 61 HC-tábla
elérhető; a kiválasztott dump SHA256-ja mindkét esetben egyezik. A backend
DB/MQTT-health sikeres, UID10001/read-only/socket nélküli, a tényleges root IPC-n
14 engedélyezett vendégkonténer leltára elérhető, a forrás-/archívumírás tiltott.

## A VM által feltárt és javított hibák

- A kiválasztott archívum recovery-image-eit és hostfeladat-naplóját a bootstrap
  nem emelte ki. Új, csak ismert útvonalakat elfogadó `restore_assets.py` előbb
  a teljes checksumot, markert és image-manifestet ellenőrzi, majd privát stagingbe
  másolja az asseteket. A pinned PostgreSQL-image még a dump-formátum ellenőrzése
  előtt betöltődik; a kanonikus állapot és DB ezután módosulhat.
- A restore-wrapper importútvonala nem tartalmazta a fagyasztott adaptert.
  Ezt explicit útvonal egészíti ki. A Compose run nem támogatja az előkészítéskor
  tévesen hozzáadott `--no-build` kapcsolót; a run rögzített image-et használ
  `--pull never` mellett, builddefiníció nélkül.
- Friss hoston a még hiányzó unit `systemctl stop` hívása 5-ös hibakóddal tér
  vissza. Ezt kizárólag az explicit fresh-host mód fogadja el már leállítottként.
- A post-boot timer korábbi ismételt engedélyezésekor nem mindig maradt jövőbeli
  trigger. Most OnBootSec=3min, OnActiveSec=3min és OnUnitInactiveSec=10min
  biztosítja a késői telepítés utáni indulást és az egyszeri futás végétől számított
  ismétlést. A next-trigger ellenőrzése legfeljebb 60 másodpercet vár. A javított
  timer a normál r10 telepítési manifestben is szerepel.
- A mentési beállítás önálló fájlja nem volt a teljes archívumban. A fagyasztott
  worker most ezt is checksum alá teszi; a restore a kiválasztott archívumból
  állítja vissza, és a naptári beállítást előre validálja. Ez a HC-45 időzítőinek
  megőrzéséhez szükséges lefedés, nem más auditpont automatikus aktiválása.

- A host-végrehajtó újraindítása lecserélte a bindmountolt socketkönyvtárat.
  `RuntimeDirectoryPreserve=yes` megőrzi az inode-ot; a fix nevű socketet az
  `ExecStopPost` eltávolítja. A valódi systemd restart és SIGKILL utáni automatikus
  újraindulás után a backend konténer-újraindítás nélkül ismét eléri az IPC-t.
- Az első valódi rebootkor egy dinamikus Docker-peer megkapta a broker rögzített
  címét, ezért a broker `Address already in use` hibával leállt. A runtime és
  rollback Compose most mind a 11 meglévő HC bridge-endpoint jelenlegi címét
  rögzíti. A telepítő a teljes endpointleltárt ellenőrzi, idegen/megváltozott peernél
  megáll. Ez 13 érintett szolgáltatás újralétrehozását igényli a későbbi átálláskor:
  az eredeti nyolcon felül PostgreSQL, PgBouncer, frontend, proxy és AI API-konténer
  is érintett; utóbbi a HC-n fut, nem a fizikai AI-gép ébresztése. Az öt további
  image és környezet változatlan. A DB-konténer újralétrehozása rövid DB/API-kiesés,
  nem DB-restore vagy migráció. Az élesítés/rollback ezt külön kezelendő hatásként
  dokumentálja; a megosztott hálózat utólagos új fogyasztója új felülvizsgálatot igényel.

A restore az ismétlés előtt leállítja a megfelelő watchereket/végrehajtót,
aktív backup vagy hostfeladat esetén megáll. A korábban bizonyítottan saját
nft-táblák tulajdonosi állapotát megőrzi; idegen táblát nem vesz át automatikusan.
A megszakadt feladat `uncertain` marad, nincs automatikus visszajátszás.

## Valódi mentésből végzett további kör

A VM backendje valódi UID10001 → root IPC → systemd runner útvonalon készített
új teljes mentést. A próbában a napi mentést szándékosan **04:27-re** állítottuk.
Az új archívum 1 480 belső checksumot tartalmaz, mérete 782 586 653 byte, SHA256-ja:
`6ae0cb9794b706ef58372d2a865c7b5a4e9687ade28df2edfb4344d10882ce7b`.
A beállítás és az offline image-cache ténylegesen benne van.

Az új restic snapshot a termelési forráslistát használja: archívum, apps, infra,
scripts és homeassistant; az önálló backup_settings fájl kimarad. A vendégből
ezt külön is eltávolítottuk a restore előtt. Ez ellenőrzi, hogy a 04:27 valóban az
ellenőrzött archívumból tér vissza, nem egy próbaforrásban meghagyott fájlból.

## Ellenőrzési állapot

- Tiszta VM teljes bootstrap: sikeres.
- Ismételt teljes bootstrap, azonos work-dir: sikeres; a telepített unit-/drop-in
  bájtok azonosak, egyetlen system scope, várt next-trigger és AI-offline tiltások.
- Valódi mentésből visszaállítás és 04:27 megőrzése: sikeres. A kiválasztott
  új dump SHA256-ja `344d4cf4a3adf7e76297ea914a6b0e744e56fec89748f945599082594fcfeb66`.
  A végleges kóddal a teljes bootstrap is ismét sikeres.
- Szándékosan hibás unitengedélyezés utáni rollback: a végleges VM-en is sikeres;
  16 unitfájl és a korábbi enabled állapot visszaállt. Egyetlen enable-hívás hibakódja
  volt injektált, minden további systemctl-hívás valódi.
- Teljes vendégreboot: a javított végleges kóddal sikeres, új boot-ID-val.
  A DB/MQTT-health, root IPC, unitok, tényleges next-trigger és mindkét nft-tábla
  ellenőrzött. A broker címe ütközésmentes; mind a 11 Docker-endpoint konfigurációja
  a várt fix címet tartalmazza.
- Elérhetetlen SFTP/restic repository esetén a bootstrap nemnulla kóddal megállt,
  nem jelzett teljes sikert; a kanonikus fájlok/unitok és DB-konténer érintetlenek.
- Újabb helyi feladatnaplónál a restore megtagadta a felülírást DB-csere előtt.
  A laborban a teljes újabb naplót külön megőriztük, és explicit egyeztetés után
  ismételtük a restore-t; nincs automatikus naplótörlés.
- Valódi non-root IPC → vendég-Docker backend-restart, valamint a host-végrehajtó
  kézi és SIGKILL utáni automatikus újraindulása sikeres.
- 430 kiadási regressziós teszt és külön 52 célzott restore-/unittelepítési teszt
  sikeres; a két suite átfed, nem összeadott darabszám.

A fizikai eszközök, a meghibásodott AI-host, aktuális külső Gitea/restic és a
valódi ESP telemetria/STOP/visszaigazolás nem része ennek a hálózat nélküli
próbának. A figyelmeztető hardverállapotot nem minősítjük hibátlan fizikai működésnek.

## Bizonyítékok és élesítési határ

[Gépi összesítés](audit-evidence/hc45-vm-20261030/summary.json),
[végső reboot](audit-evidence/hc45-vm-20261030/reboot-result.json),
[időzítők és IPC reboot után](audit-evidence/hc45-vm-20261030/after-reboot-probe.json),
[unit-visszagörgetés](audit-evidence/hc45-vm-20261030/unit-rollback.json),
[éles változatlanság](audit-evidence/hc45-vm-20261030/production-unchanged.json).
A mérési sorok a VM saját új mintái miatt a 7 006 285-ös eredeti dump fölé nőhetnek;
az archívum/dump azonosítója a visszaállítás bizonyítéka, nem a változó live darabszám.

A próba előfeltételként telepített OS-csomagokat és offline image-eket használt.
A külső `homecontrol_restore_magic.sh` letöltési/telepítési útvonala nem futott;
a tényleges teljes bootstrap Git → age → SFTP/restic → pg_restore → systemd →
Docker útvonala igen. A teljes r9→r10→r9 telepítési tranzakció nem futott ebben a
VM-ben: a rollback-bizonyíték az audit által kért unitfájl-/enabledállapot-rollbackre
vonatkozik. A későbbi felügyelt átadás és annak rollbackje külön kiadási művelet.

A labor egyik korábbi restic snapshotjából kimaradtak a termelési kizárások,
emiatt a nyers PGDATA felesleges másolása megtöltötte a tesztlemezt. A staginghibát
javítottuk, a futás hibával megállt; ez nem kapott sikeres minősítést. A helyes
kizárásokkal a 32 GiB-os lemez elegendő volt, az ismételt tesztstagingeket külön
takarítottuk. A mentés/restore tervezésénél a staging és image-cache helyigényével
is számolni kell.

Az eredeti audit, 37 aktív hostfájl, 16 éles konténer, MQTT-konfiguráció és a
combustion-safety forrás változatlan. A VM nem érte el a fizikai rendszert.
Az ESP megerősítése továbbra is `false`; a termelési bundle nem módosult.
HC-45 helyben ellenőrzött; a kiadás nincs élesítve, HC-41 folyamatban, HC-35/36 kimarad.

A bizonyítékok mentése után a két saját VM-konténert, a vendéglemezeket és a
privát laboradatokat/kulcsmásolatokat eltávolítottuk. Az eredeti éles mentés és
kulcsok megmaradtak; hostcsomag-telepítés nem történt.
