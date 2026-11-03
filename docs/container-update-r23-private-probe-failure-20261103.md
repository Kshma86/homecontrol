# R23 – leállás a privát MQTT-próbánál

Állapot: **az éles r22 változatlan; a pontos privát hiba diagnosztikája hátravan**.
Az inventory-folytató teljes repository-ellenőrzés, friss előmentés és külön
PostgreSQL-restore után a `prepare_new_private_runtime` fázisban állt meg
`RuntimeError` hibával. Az átállítási fázis nem kezdődött el.

A független natív állapotellenőrzés sikeres: ugyanaz a 16 konténer/image,
805 runtime-forrás, 25 unitfájl, öt timer és öt backup-mount. A folytató workere
nem fut. A régi és új indítási nyugtákat, naplókat, staginget és mentéseket
megőrizzük; indítást nem ismételtünk.

Külön reprodukálható hiba az előkészített `private_mqtt_probe` indításában:
a stage `mosquitto.conf` fájlja a broker UID-jének kizárólagos olvasására van
állítva (0700 könyvtár, 0600 fájl), de a tesztkonténer UID 0, `cap-drop ALL`,
csak SETUID/SETGID képességekkel indul. Mosquitto a konfigurációt a felhasználó
váltása előtt olvassa; a root ebben a konténerben nem rendelkezik DAC_OVERRIDE
jogosultsággal, így a másik UID fájlját nem olvashatja. Ez az előkészített próba
hibája, nem a termelési broker konfigurációjának hibájára utaló bizonyíték.

Az új Mosquitto-image ugyanazon szintetikus, a konfiguráció tulajdonosának
fenntartott másolattal a fagyasztott root indításnál exit 3 / konfiguráció nem
olvasható eredményt adott; a konfiguráció tulajdonosának UID-jével, hozzáadott
capability nélkül azonos `--test-config` exit 0 lett. Éles mount nem vett részt
a próbában. Bizonyíték:
`maintenance/container-update-20261103/mqtt-owner-probe/result.json`.

A root-védett naplóval a mostani leállást még pontosan össze kell vetni:

```bash
sudo python3 /srv/docker/homecontrol/scripts/container_update/diagnose_prepare.py
```

A diagnosztika csak olvas: megmutatja a redaktált Mosquitto hibaosztályt,
a parancs fajtáját, a trace ismert helyeit, az előmentés/restore nyugtáját,
a staging UID/mód adatait és a vezérlődirektívák neveit. Konfigurációértéket,
hitelesítőadatot, nyers naplót vagy eszközlistát nem ad ki. A hat célzott
redakciós teszt sikeres. A lezárt r23 és continuation-1 csomag nem változott.
