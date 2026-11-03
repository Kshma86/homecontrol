# A HC hostfrissítés előkészítése

**Lezárt karbantartás: REPAIR-089.** [Sikeres végállapot és bizonyítékok](host-update-complete-20261103.md).
Az alábbi korábbi állapotleírás történeti; a parancsok nem ismétlendők.

REPAIR-085, 2026-11-03. **Előkészítve; telepítés és reboot nem történt.**
Az r22 éles átadása lezárt marad; HC-41/43 státusza változatlan.

A felhasználó azóta engedélyezte a folytatást. Az elkészült felügyelt indító
és az aktuális, még nem telepített állapot: [REPAIR-086](host-update-execution-20261103.md).

Készlet: `/srv/docker/homecontrol/maintenance/host-update-20261103`.

## A konkrét terv

Ubuntu **22.04.5 LTS / jammy** marad. A meglévő Ubuntu- és hivatalos Docker-
források friss, APT által hitelesített katalógusából készült a szimuláció.
Az indexek külön munkakönyvtárba kerültek; a host APT-listáit és dpkg-adatbázisát
nem frissítettük. Aláírás-ellenőrzést vagy lejárati ellenőrzést nem tiltottunk ki.
A metadata-letöltés APT-hookjai ki vannak ürítve, így az előkészítés nem indít
hoston konfigurált utófeldolgozó parancsot. A későbbi telepítés külön konfigurációja
megtartja a rendes dpkg-hookokat.

**30 csomagfrissítés + 2 új függőség, 0 eltávolítás.** Minden pontos verzió és
SHA-256 a `plan.json` fájlban, a verziólista a `package-versions.tsv` fájlban található.

| Komponens | Jelenlegi | Előkészített |
| --- | --- | --- |
| Docker Engine és CLI | 29.1.5 | 29.9.2 |
| containerd | 2.2.1 | 2.4.2 |
| Compose plugin | 5.0.2 | 5.7.0 |
| Buildx plugin | 0.30.1 | 0.38.1 |
| Netplan és libnetplan | 0.106.1 | 0.107.1 |
| nftables | 1.0.2-1ubuntu3 | 1.0.2-1ubuntu3.1 |
| Futó kernel / következő boot | 5.15.0-187-generic | a már telepített 5.15.0-202-generic |

Az új csomagok `netplan-generator` és `python3-netplan` függőségek. További
érintett csomagok többek között a Kerberos/LDAP könyvtárak, iproute2, firmware,
snapd és cloud-init. Az `ubuntu-release-upgrader-core` csomag frissítése szerepel
a tervben; disztribúcióváltó parancsot nem futtatunk.

Az új csomagok **455 459 286 bájt** méretben letöltve; mind a 32 fájl mérete,
SHA-256 értéke, neve/verziója/architektúrája ellenőrzött az APT-katalógushoz képest.
Nyolc korábbi Docker/containerd/Compose/Buildx/Netplan csomag is letöltve,
**91 393 200 bájt** méretben. Ez helyreállítási segédanyag, nem tesztelt automatikus
OS- vagy Docker-adattár-visszagörgetés. Az új Netplan-függőségek kezelését egy
esetleges visszalépésnél külön meg kell tervezni.

## Tényleges ellenőrzések

* Nincs félbemaradt dpkg-konfigurálás vagy kézzel visszatartott csomag.
* Az előkészítés után a dpkg-adatbázis SHA-256 értéke változatlan. Mind a 32
  tervezett csomag eredeti telepítési állapotát külön is ellenőriztük.
* Az r22 aktív: 805 runtime-forráshash, 16 konténerazonosság és futási állapot,
  readiness, AI-tiltás, routeres policy és 25 unit/drop-in hash ellenőrzött.
  Nincs más, a karbantartási leltárból kimaradt futó konténer.
* Mind az öt mentési bind mount UUID-ja és fájlrendszeren belüli forrása rögzített;
  az aktív timerek és a hostops/MQTT guardok ellenőrzöttek.
* Az induló szabad hely közel 15,8 GiB a rooton, 142,5 GiB a `/var`-on és
  40,4 GiB a `/srv`-n. Az összes új csomag teljes kibontott mérete 1,55 GiB;
  ez konzervatív méretadat, nem a tényleges növekmény. A cache a `/srv`-n van.
* A már telepített következő kernel és a korábbi kernel/initramfs fájlok megvannak.
  A rendszer rebootot kér. A root által védett kernel bájthashét és a tényleges
  következő bootot ez az előkészítés nem hitelesítette.
* **15 új célzott teszt sikeres:** csomagterv értelmezése, eltávolítás/ambiguitás
  elutasítása, hiteles katalógus-metaadat és deb-tartalom egyezése, symlink és
  hashhiba elutasítása, reboot-/kernel-/mount-/dpkg-kapuk.
* Az új CLI és Compose külön kibontva ténylegesen futott. A CLI olvasással
  elérte a jelenlegi 29.1.5 daemont; a Compose azonos 14 szolgáltatásos JSON-t
  renderelt, privát env-fájlok feloldása nélkül. A próbabinarisok eltávolíthatók;
  a hiteles deb-készlet és a próbanyugta megmarad.
* A külön telepítési konfiguráció szimulációja pontosan ugyanazt a 32 tranzakciót
  adta, mint az előkészítési konfiguráció. A telepítési parancs nem futott.

Az új Docker daemon indulását, az új Netplan tényleges hálózatalkalmazását és a
host rebootját még nem teszteltük. A 15 teszt nem jelent teljes hostfrissítési
vagy új VM-visszaállítási próbát.

## Végrehajtási sorrend a karbantartási ablakban

A következő lépés már szolgáltatáskieséssel járó hostkarbantartás; a mostani
kérés az előkészítésre szólt. A telepítést és rebootot külön kell elindítani.

1. Az előkészített készlet ellenőrzése az alábbi `verify` paranccsal. A terv
   legfeljebb 24 órás lehet, a host csomagállapota és APT-konfigurációja nem térhet
   el. Eltérésnél új terv kell; a csomagkészletet nem írjuk felül.
2. Helyi vagy távoli konzolelérés biztosítása a Netplan-frissítés és a reboot
   idejére. Ennek elérhetőségét az előkészítés során nem erősítettük meg.
3. Valódi root előellenőrzés: aktív öntözés hiánya, robot dokkolt/töltő állapota,
   üres hostops-/mentési sor és szabad közös lockok; a backup-storage `check`.
   A védett `/etc/netplan`, hálózati/firewall-konfiguráció, fstab, GRUB, APT és
   dpkg-metaadatok privát, jogosultságőrző mentése a telepítés előtt.
4. Friss teljes r22 HC/Git/router mentés és izolált PG-restore. A legutóbbi ismert
   siker a `7a6236e4b0a5472a8566024665ffc619` run; a tényleges karbantartásnál
   új előmentést kell készíteni. A mentési timerek/IPC-munkák szüneteltetését és
   a folyamatfelügyeletet a végrehajtás részeként kell kezelni.
5. A vezérlési szándékok ellenőrzött egyeztetése, majd a HC komponensek szabályos
   leállítása adatbázis-függőségi sorrendben. A Docker/containerd frissítése miatt
   kieséssel kell számolni; SSH-kapcsolatot túlélő, naplózott végrehajtás szükséges.
6. A rögzített katalógus és a helyi cache használatával az előre szimulált csomagok
   telepítése. Eltávolítás, disztribúcióváltás, image-csere vagy automatikus
   kernel-/Docker-cache-takarítás nem része ennek a tervnek. A tényleges parancs
   előtt ismételt szimuláció és teljes egyezés szükséges.
7. Komponensek és ütemezők visszaindítása, MQTT nft-hozzáférési szabályok tételes
   root ellenőrzése. Sikeres `before-reboot` ellenőrzés után külön, tervezett reboot.
8. Reboot után `postcheck`: új boot-ID, a 202-es kernel, változatlan r22 image-ek,
   805 runtime-hash, öt helyes backup-mount, 25 unit/drop-in és öt működő timer,
   backend readiness, AI-tiltás és pontosan a jóváhagyott hostcsomagverziók.
   A health oneshot végét az r22-ben már átvett adapter várja meg.
9. Friss utómentés/restore, mentési és eszközkapcsolati ellenőrzés; a karbantartási
   nyugta csak ezekkel zárható. HC-43-at ez az OS-frissítés nem zárja le.

## Elkészült parancsok

A következő parancs **csak ellenőriz**, nem telepít:

```bash
python3 /srv/docker/homecontrol/maintenance/host-update-20261103/source/check.py verify
```

A későbbi telepítés **után**, még a reboot előtt:

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103/source/check.py before-reboot
```

A későbbi reboot **után**:

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103/source/check.py postcheck
```

A csomag tartalmaz egy `apt/install-reviewed.conf` fájlt az előre letöltött,
pontos katalógus/cache használatához. A tényleges APT-művelet előkészített alakja:

```text
apt-get -c /srv/docker/homecontrol/maintenance/host-update-20261103/apt/install-reviewed.conf --no-download --no-remove --with-new-pkgs upgrade
```

Ez önmagában nem végrehajtó wrapper: nem készít mentést, nem egyezteti a fizikai
vezérlést és nem állítja le sorrendben a szolgáltatásokat. A fenti kapukat a
felügyelt végrehajtásnak teljesítenie kell. Automatikus, ezeket megkerülő
telepítőindítót nem adtunk a készlethez.

A `before-reboot` és `postcheck` szoftveres ellenőrzés: nem helyettesíti a friss
mentési/restore próbát, a root firewall-vizsgálatot vagy az eszközkapcsolati átvételt.
Az r22 kiadási/folytatási indítói felhasználtak; hostkarbantartáshoz nem ismétlendők.

## Források és bizonyítékok

* [Pontos csomagterv nyilvános összefoglalója](audit-evidence/host-update-20261103/plan-summary.json).
* [Előkészítési elfogadási nyugta](audit-evidence/host-update-20261103/acceptance.json).
* [Docker/Compose klienspróba](audit-evidence/host-update-20261103/candidate-cli-probe.json).
* [Docker 29 kiadási megjegyzések](https://docs.docker.com/engine/release-notes/29/).
* [Docker Ubuntu-frissítési útmutató](https://docs.docker.com/engine/install/ubuntu/).

A Docker 29.9.2 kiadás biztonsági Go-frissítést tartalmaz; a gyártói kiadási
megjegyzés tanúsítványlánc-ellenőrzést érintő változást is rögzít. Az image-pull/
push és a backup/recovery út működését ezért az éles utóellenőrzésben is vizsgálni
kell. A helyi klienspróba nem helyettesíti az új daemon átvételét.
