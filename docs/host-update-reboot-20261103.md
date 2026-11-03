# Hostfrissítés: telepítve, reboot következik

REPAIR-087, 2026-11-03. A felhasználó által visszaküldött felügyelt futás sikeres:
`upgraded_pending_reboot`. Friss teljes HC/Git/router előmentés és izolált PG-restore,
függőségi leállítás/indítás, pontos csomagtelepítés és reboot előtti átvétel teljesült.
A lezárt executor csak a Zigbee/Growatt kapcsolati próba sikere után írhatta ezt
a végállapotot. A privát nyugtákat a reboot indítója rootként ismét ellenőrzi.

Független natív olvasási ellenőrzés:

* Docker daemon: **29.9.2**; mind a 32 telepített csomag a pontos tervezett verzión.
* Aktív r22, 16 konténerazonosság és futási állapot, 805 runtime-forrás,
  25 unit/drop-in hash és öt backup-mount változatlan; a dpkg tiszta.
* Robot dokkolt/töltő, nincs aktív öntözés.
* Futó kernel még **5.15.0-187-generic**; a GRUB első bejegyzése és az initrd
  **5.15.0-202-generic**, a megfelelő root UUID-val. Nincs GRUB override.
* Docker, hostops és MQTT guard bootkori indítása engedélyezett.
* Natív nem interaktív sudo továbbra sem használható: helyi jelszót kér.

**Reboot és reboot utáni mentés/restore még nem történt; a hostkarbantartás még
nincs lezárva.** Az r22 kiadás, illetve HC-41/43 auditstátusza változatlan.
Az előkészítő és telepítő korábbi állapotleírásai történetiek; a már felhasznált
upgrade parancsot nem szabad ismételni.

## Következő helyi parancs

A konzolelérést a felhasználó megerősítette, a karbantartási engedély érvényes.

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103-reboot/source/reboot.py reboot
```

Az indító a root tulajdonú, lezárt executor pontos hashét és a jelen boothoz
tartozó sikeres upgrade-/előmentés-/restore-nyugtát ellenőrzi. Újra lefut a teljes
eredeti `before-reboot` ellenőrzés, a fizikai, idle-, közös lock-, nft-, mount-
és kapcsolati kapu. A GRUB-ot nem írja át: csak a pontos alapértelmezett bejegyzést,
az override-ok hiányát, az új kernel dpkg-ellenőrzését és az új/régi kernel+initrd
fájlok meglétét/hashét vizsgálja.

A timer/path és hostops belépési pontokat szünetelteti, majd normál
`systemctl reboot` hívást végez. A konténereket a normál systemd/Docker shutdown
állítja le; külön `docker stop` nem történik, így az `unless-stopped` szabály nem
akadályozza az automatikus bootkori indulásukat. Adminer továbbra is leállítva marad.
Nincs force reboot, csomagtelepítés vagy konfigurációváltás ebben a lépésben.

A részletes napló és a bootfájl-hashek az eredeti root privát állapotkönyvtárba
kerülnek. A reboot-kérés előtti hibánál a már szüneteltetett belépési pontokat
visszaállítjuk. Ha a reboot-kérés már elindult és a válasza bizonytalan, az indító
megőrzi a nyugtát, és nem ismétli vakon a műveletet. Az SSH megszakadása a tényleges
újraindításkor várható.

Újracsatlakozás után a következő kernel várható:

```bash
uname -r
```

Ez önmagában még nem zárja le a karbantartást. A következő lépés az élő állapot
újraellenőrzése, majd a már lezárt executor `finish` művelete: új boot-ID és 202-es
kernel, teljes r22 postcheck és nft-ellenőrzés, Zigbee/Growatt kapcsolat, friss teljes
utómentés és izolált PG-restore. A `finish` csak akkor indítandó, amikor a bootkori
szolgáltatások már készen állnak; az indítás előtti ellenőrzést a következő körben
elvégezzük. Az eszközök kézi funkcionális próbája külön átvételi lépés.

## Új ellenőrzések

Nyolc reboot-kapu teszt sikeres: várt GRUB-bejegyzés, hibás/saved default,
egyszeri boot/recovery override, eltérő kernel/root/initrd, aktuális upgrade-nyugta,
korábbi boot vagy sikertelen átvétel, hiányos előmentés-/restore-nyugta,
és annak ellenőrzése, hogy hibás preflight után reboot/hostops-stop nem történik.
A valódi GRUB-fájlok csak olvasó vizsgálata is sikeres. Rebootot a tesztek nem végeznek.
Az előző 31 teszt és a lezárt telepítési készlet változatlan.
