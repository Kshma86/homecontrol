# Helyi mentési tárhely a /var partíción

**REPAIR-080 pontosítás:** a megőrzött inode-ok ellenére a külön bind mountok
közötti új cache-hardlink kernel `EXDEV` hibába ütközhet. A korábbi terv ezt
a VFS-korlátot nem vette figyelembe. [Valódi reprodukció és javított r22
cache-átvitel](audit-r22-install-continuation-20261103.md) külön dokumentált;
a tárhelyátállás maga sikeres maradt.

REPAIR-075 előkészítés; REPAIR-076 sikeres éles átállás, 2026-11-03. Aktív: r18.
**A felhasználó root futtatása `ok: true`, `phase: complete` eredménnyel lezárult.**
[Éles utóellenőrzések és az r21 következő lépése](backup-storage-live-20261103.md).
Az alábbi szöveg az eredeti előkészítést és működési szerződést dokumentálja.
Az audit alkalmazásjavításainak r21 élesítése ettől külön, továbbra is függő.

## Elhelyezés és kapacitás

Az ellenőrzött kiosztás: `/srv` kb. 8 GiB, `/var` kb. 198 GiB, `/` kb. 37 GiB
szabad hellyel rendelkezik. A korábbi 7,2 GiB kapu minimum volt; a mentő a `/srv`
partíción dolgozott, ezért a `/var` szabad területe nem segített rajta.

Az előkészített csomag: `backups/releases/hc-backup-storage-20261103`.
Az új fizikai adattár: `/var/lib/homecontrol-backup-storage/data`.
A programok által használt útvonal továbbra is `/srv/docker/homecontrol/backups`.
Ezt tartós systemd bind mount kapcsolja az új adattárhoz. A routeres repository,
az FTP-hozzáférés, a titkosítás, a Git-cél és a megőrzési szabály változatlan.
Új kvótát nem állítunk be. A `/var` kapacitása a helyi mentések rendelkezésére áll;
30 GiB tartalékot ellenőrzünk a rendszer és Docker számára, plusz két nagy archívum
helyigényét az ütemezett mentések előtt. Ez megmaradó szabad hely, nem mentési maximum.

A lezárt csomagok (`backups/releases`), az élő `ai-control` könyvtár és a két
közös zárolófájl eredeti inode-jai a `/srv` fájlrendszeren maradnak, négy alárendelt
bind mounttal, a `.backups-before-var-20261103` könyvtárból. Így az r21 cache-hardlinkjei,
a root/alkalmazás jogosultságok és a zárolási protokoll változatlanul használhatók.
Nincs partícióátméretezés, szimbolikus útvonal-átirányítás vagy új alkalmazás-image.
A bind mountok megőrzik a restic által látott logikai fájlneveket is.

## A végrehajtó parancs

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-backup-storage-20261103/source/migrate.py apply
```

Az előkészítés során ezt nem futtattuk. A natív host root-jogosultsága szükséges,
az ügynök sandboxában a `/var` nem írható. Jogosultságkerülés nem történt.

A végrehajtás csak a csomaghoz rögzített, egészséges r18/konténerbaseline-ból indul.
Futó hostfeladat vagy foglalt mentési lock esetén az aktív feladatot nem állítja le.
A közös lockokat a hostops leállítása előtt foglalja, így aktív mentést nem szakít meg.
Átmenetileg megállítja az öt timert, a két kérést figyelő path unitot és a hostopsot.
A HC működik a nagy másolás alatt; a mentési/beállítási root műveletek szünetelnek.

A másolás `rsync -aHAXS --numeric-ids --checksum` módban történik. A program teljes
SHA-256 tartalom-, uid/gid-, hozzáférés-, ACL/xattr-, link- és időbélyeg-ellenőrzést
végez, a symlinkek célját követés nélkül másolja. A könyvtár/symlink időbélyegeket
külön is helyreállítja és szigorúan ellenőrzi. Speciális fájlt vagy váratlan fájlrendszert
nem másol át csendben. A forrás változatlanságát a váltás előtt újraellenőrzi.
A több tíz GiB adat és a teljes ellenőrzések miatt a folyamat hosszabb ideig tarthat.

A végső váltásnál csak a backend áll le és indul újra, azonos konténer-ID/image mellett.
A DB, MQTT, HA és a többi konténer működése megmarad. A program a Docker daemon saját
mount namespace-ében is ellenőrzi, hogy az új gyökér és a lockok valóban látszanak.
Utána a komponenseket, a backend readiness-t és az AI-offline/router policy-t ellenőrzi.

Csak az új adattárban pontosan ellenőrzött másolatok régi fizikai példányait takarítja
meg. A megváltozott vagy ismeretlen fájlokat megtartja; logikai mentési archívumot
nem töröl. A mentési útvonalakon minden archívum elérhető marad. A forráson felszabaduló
és a célon megmaradó pontos helyet a root végrehajtás méri meg, nem állítjuk előre késznek.

Az öt mount-unit és az egyedi service-dropinek biztosítják az újrainduláskori
sorrendet. Docker és hostops csak a teljes elhelyezés mellett indul; a Docker
kapacitáshiány miatt nem kerül letiltásra, ott csak az elhelyezést ellenőrizzük.
Az ütemezett mentők a szabad helyet is ellenőrzik. A meglévő F6/hozzáférési dropineket
nem írjuk felül. Az `/etc/fstab` nem változik.

## Állapot és visszaállás

Siker: `ok: true`, `phase: complete`. A részletes root-nyugták és hibakimenetek:
`/var/lib/homecontrol-backup-storage/state/`. Az ellenőrző és rollback-kód külön,
root által telepített másolatot kap, ezért részleges mountnál is elérhető.

```bash
sudo python3 /usr/local/lib/homecontrol-backup-storage/migrate.py check
sudo python3 /usr/local/lib/homecontrol-backup-storage/migrate.py rollback
```

A rollback előbb visszamásolja és ellenőrzi az időközben keletkezett adatokat is,
majd visszaadja az eredeti útvonalat. A backend csak a visszaváltás végén áll le.
Ha a megnőtt adatállomány később már nem fér a `/srv`-re, nem bontja le a működő
`/var` elhelyezést. Az eredeti lock-inode-ok és a korábbi watcher-állapotok megmaradnak.
Hiba esetén a már végrehajtott szakaszt és a privát naplót kell vizsgálni; a program
nem ír felül korábbi vagy idegen átállítási célkönyvtárat.

## Ellenőrzési bizonyítékok és határok

* 10 sikeres fájlrendszer-/rsync-/jogosultság-/hardlink-/zárolás-/unitgenerátor-teszt.
* 13 sikeres próba valódi, elkülönített user+mount namespace-ben, külön tmpfs célon.
  Tényleges másolás, kernel bind mount és visszagörgetés történik. Lefedett a sérült
  másolat, a részleges csatolás, a health-hiba, a megtisztítás utáni hiba, a csak
  olvasható cél, az aktív munka, a foglalt lock, az új mountpoint létrehozási hibája,
  a rollback helyhiánya, az újrainduláskori visszacsatolás és a natív nsenter/stat probe.
  A váltás után létrehozott új mentés is visszakerült a rollbackben.
* Külön valódi, hálózat nélküli Docker-konténerrel ellenőrzött: az újraindítás
  az új könyvtárat látja és megtartja az ID-t. Éles konténert a próba nem módosított.
* Az öt mount-unit és a nyolc érintett szolgáltatás teljes, meglévő dropineket is
  tartalmazó függőségi gráfjának `systemd-analyze verify` ellenőrzése exit 0.
  Egy meglévő snapd-unit verziófigyelmeztetése a naplóban megmaradt; szolgáltatás
  nem indult, és nem minősítjük teljes host-reboot próbának.

A kezdeti laborhibák a könyvtár/symlink időbélyegek beállítását és a fájl-bindmountok
felismerését javították; a tartalom- és jogosultságellenőrzést nem enyhítettük.
A kezdeti sikertelen mount-labor naplója megőrzött. Végső tesztekben nincs hiba/kihagyás.

Az éles host átállítása a REPAIR-076 szerint sikeres; valódi újraindítás még nem
történt meg. Friss OS-recovery
esetén a fizikai tárhelyelhelyezés új, aktuális baseline-ból külön újraalkalmazandó;
az eredeti HC-restore továbbra is a változatlan `/srv/docker/homecontrol/backups`
logikai útvonalat használja. Új teljes bare-metal VM-bizonyítékot nem állítunk.
A korábbi r18/r21 recovery-bizonyítékokat és 799 lezárt r21 forráslenyomatot megőrizzük.
HC-41/43 folyamatban marad; más auditpont javítása vagy automatikus lezárása nem történt.

A csatolási útvonalak és sorrend ellenőrzéséhez használt elsődleges referencia:
[systemd 249 mount-unit dokumentáció](https://www.freedesktop.org/software/systemd/man/249/systemd.mount.html).
A tényleges rendszerhez generált unitok és tesztbizonyítékok:
`docs/audit-evidence/backup-storage-20261103/` és a lezárt csomag `evidence/` könyvtára.
