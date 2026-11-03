# Az engedélyezett hostfrissítés indítója

REPAIR-086, 2026-11-03. A felhasználó engedélyezte a karbantartás folytatását.
**Az indító elkészült; csomagtelepítés, szolgáltatásleállítás és reboot még nem történt.**
A natív `sudo -n true` jelszót kért, ezért a root futás helyi terminálból indítható.
A felhasználó megerősítette, hogy a HC gépet konzolról is eléri.

Az [eredeti, lezárt előkészítés](host-update-preparation-20261103.md) változatlan.
Készlet: `/srv/docker/homecontrol/maintenance/host-update-20261103-executor`.
A készlet `manifest.json` fájlja rögzíti az indító és tesztjeinek SHA-256 értékét,
valamint a 128 artefaktumot lezáró eredeti előkészítési nyugta hashét.

## Helyi indítás

A következő parancsot akkor kell futtatni, amikor a helyi vagy távoli konzolelérés
biztosított. A `--console-ready` kapcsoló ennek operátori állítása; a script nem
tudja ellenőrizni, hogy ténylegesen van-e monitor/billentyűzet vagy távoli konzol.

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103-executor/source/execute.py upgrade --console-ready
```

Az indító létrehozza a root tulajdonú, 0700 módú
`maintenance/host-update-20261103-execution` könyvtárat. A futó indító saját
példánya, a konfigurációs mentés, részletes parancskimenetek és hibák ide kerülnek,
0600 móddal. Az egyszeri indítási nyugta kizárja a vak újraindítást. A systemd
felügyelt worker nyolc órás felső korláttal túléli a klienskapcsolat megszakadását;
a mentő worker saját háromórás korlátját is megtartjuk.

Az indító sorrendje:

1. A lezárt előkészítés, pontos APT-szimuláció, 24 órás időkorlát, csomagadatbázis,
   r22 runtime, konténerazonosságok, mountok, szabad hely és eredeti timer-kapuk.
   Csak dokkolt/töltő robot, inaktív öntözés, üres hostops-sor és szabad közös lockok.
   Aktív APT/mentési munka esetén megáll; lockot nem töröl vagy kerül meg.
2. Privát, jogosultságőrző `/etc`, `/boot`, dpkg- és APT-állapotmentés; route-,
   unit- és firewall-leltár. Ez helyreállítási segédanyag, nem atomikus OS-lemezkép.
3. Mentési timerek, IPC-pathok és automatikus APT-timerek szüneteltetése; az éppen
   futó health oneshot befejezésének kivárása. Friss heti HC/Git/router mentés és
   izolált PG-restore. Mind az öt cél, a hét lefedettségi mező és az archívumok
   SHA-256 azonossága kötelező.
4. Megismételt csomag-/fizikai kapuk, majd hostops és backend szabályos leállítása.
   A korábbi ventilátor-ON szándékok egyeztetése még működő PostgreSQL mellett;
   AI-intent érvénytelenítése saját lockkal, a hozzáférési jogosultságok megtartásával.
   A további komponensek leállítása függőségi sorrendben. Adminer leállítva marad.
5. Újabb sértetlenségellenőrzés és végső APT-szimuláció, majd a pontos helyi
   csomagkészlet telepítése letöltés és eltávolítás nélkül, a normál dpkg-hookokkal.
   A meglévő konfigurációkat megtartjuk; a needrestart csak jelentést készít.
6. Azonos konténerek indítása adatbázis/MQTT függőségi sorrendben; a két
   adatbázis-függőség health ellenőrzése. MQTT guard a backend előtt, hostops
   visszaindítása. Az owned nft-táblák szabályai és policy-hashe változatlan kell
   maradjon; csak a változó számlálókat és handle-öket hagyjuk ki az összevetésből.
7. Ütemezők visszaállítása, readiness, az eredeti teljes `before-reboot` kapuk,
   valamint tényleges Zigbee MQTT- és Growatt HA-adatpróba, vezérlés nélkül.

Siker: `upgraded_pending_reboot`, a `upgrade-success.json` nyugtában
`reboot_performed: false`. **Az indító nem rebootol.** A reboot következő lépése
csak e friss nyugta és az élő állapot értékelése után következik; az elfogadott
karbantartáshoz nem kérünk új általános engedélyt.

A ténylegesen később végrehajtott reboot után külön `finish` művelet készült:
új boot-ID és a 202-es kernel, teljes eredeti r22 postcheck, nft-összevetés,
Zigbee/Growatt kapcsolati próba, majd új teljes utómentés és PG-restore.
Ezt a lépést még nem futtattuk. A kézi eszközfunkciók ellenőrzését a kapcsolati
próbák nem helyettesítik. HC-43 státusza változatlanul Folyamatban.

## Hibánál

Leállítás előtti hibánál a már szüneteltetett ütemezőket és az esetleg leállított
hostopsot visszaállítjuk. A backend leállítása után jelentkező hibánál a script
megőrzi az állapotot, és kézi egyeztetésre vár: részleges APT-művelet vagy sikertelen
szándékegyeztetés után nem indítja vakon vissza a vezérlést. Automatikus
csomagdowngrade vagy host-rollback nincs.

Ne ismételd az indítóparancsot, és ne töröld a privát állapotkönyvtárat.
Titkok nélküli állapotösszefoglaló:

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103-executor/source/execute.py status
```

## Ellenőrzés

31 teszt sikeres: a korábbi 15 előkészítési/boot teszt és 16 új végrehajtási kapu.
Az új tesztek lefedik a hibás/stale/hiányos mentést, eltérő archívumból végzett
restore-t, hiányzó lefedettséget, konténer-/image-/restart-policy eltérést, nft
számlálók és valódi szabályváltozás megkülönböztetését, a kifejezett Zigbee online
állapotot, a részleges timer-szüneteltetés helyreállítását és azt, hogy hibás
előmentés után APT vagy konténerleállítás nem indulhat.

Natív olvasási ellenőrzés: az r22 aktív, 16 konténer/5 mount változatlan, a dpkg
tiszta, nincs hold; a lezárt 32 új/8 régi csomag újraellenőrzése sikeres.
A `homecontrol-backup.service` régi `failed` állapota a 02:15–02:19 közötti,
az r22 átadását megelőző futáshoz tartozik. Nem töröltük; a friss előmentés
sikeressége a karbantartás önálló kötelező kapuja.

Valódi root előellenőrzés/mentés, új daemon, telepítés és reboot ezen a ponton
nincs kipróbálva; a mockolt hibatesztek ezek sikerét nem állítják.
