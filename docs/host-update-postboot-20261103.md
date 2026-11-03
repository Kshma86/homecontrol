# Hostfrissítés: az új boot ellenőrzött, utómentés következik

**Lezárt karbantartás: REPAIR-089.** [Sikeres végállapot és bizonyítékok](host-update-complete-20261103.md).
Az alábbi korábbi állapotleírás történeti; a parancsok nem ismétlendők.

REPAIR-088, 2026-11-03. A felhasználó visszajelzése és a független natív
olvasási ellenőrzés szerint **5.15.0-202-generic** fut, új boot-ID-val.

Az r22 aktív, a 16 konténerazonosság és futási állapot, 805 runtime-forrás,
25 systemd unit/drop-in hash és öt mentési bind mount egyezik az elfogadott
állapottal. Mind a 32 hostcsomag a tervezett verzión van, a dpkg audit tiszta.
Öt timer aktív és engedélyezett; a post-boot health oneshot sikeres (exit 0),
jelenleg befejezett. Backend health/readiness sikeres, AI tiltva, routeres mentés
engedélyezve. Robot-/öntözéskapu teljesül, a Zigbee MQTT bridge online,
a Growatt HA-adat elérhető. Ezek a próbák nem vezéreltek eszközt.

A lezárt executor sértetlenségét külön ellenőriztük; nem módosítottuk.
Nem interaktív sudo továbbra sem használható, ezért a záró root futást a helyi
terminálból kell indítani:

```bash
sudo python3 /srv/docker/homecontrol/maintenance/host-update-20261103-executor/source/execute.py finish
```

Ez a már előkészített, systemd által felügyelt záróművelet: teljes eredeti r22
postcheck, pontos csomagverziók és új kernel/boot, root nft-összevetés, kapcsolati
és idle-kapuk, majd friss heti HC/Git/router utómentés és izolált PostgreSQL-restore.
A mentési ütemezőket a próba idejére szünetelteti, majd visszaállítja, és ismét
ellenőrzi az eredeti timer-kapukat. A friss archívum, router-visszaolvasás és
adatbázispróba SHA-256 azonossága kötelező.

**Az utómentés/restore még nem futott le; a hostkarbantartás még nincs lezárva.**
A következő sikeres végállapot szükséges:
`host_updated_reboot_backup_restore_verified`, root privát `finish-success.json`
nyugtával. Hibánál az indítót nem szabad vakon ismételni; a privát állapot és
napló megmarad. A kézi eszközfunkciók átvétele külön lépés.

HC-41/43 továbbra is Folyamatban; a hostfrissítés nem zárja le a konténeres
gyártói sérülékenységeket. A korábbi [telepítési](host-update-execution-20261103.md)
és [reboot](host-update-reboot-20261103.md) indítókat nem kell megismételni.
