# A HC hostfrissítés lezárva

REPAIR-089, 2026-11-03. **A host operációsrendszer-karbantartása sikeresen lezárult.**
Végállapot: `host_updated_reboot_backup_restore_verified`.

Az Ubuntu 22.04 LTS hoston a tervezett 30 frissítés és két új függőség települt,
eltávolítás és disztribúcióváltás nélkül. A Docker daemon 29.9.2; reboot után
**5.15.0-202-generic** fut, új boot-ID-val. A korábbi kernel és a helyreállítási
csomagok megmaradtak; automatikus OS-rollbacket nem állítunk.

A felhasználó által visszaküldött root `finish` kimenet szerint az új booton
két teljes eredeti postcheck sikeres volt, közöttük friss heti HC/Git/router
utómentéssel, router-visszaolvasással és izolált PostgreSQL-restore-ral.
Mind az öt timer eredeti kapui teljesültek; a health oneshot eredménye success,
exit 0, a timer waiting állapotú. A lezárt executor a végállapot előtt ellenőrizte
a root nft-szabályok egyezését, a kapcsolati és idle-kapukat, mind az öt mentési
célt, a teljes archívumlefedettséget és az archívum-/restore SHA-256 azonosságot.
Friss teljes előmentés/restore a telepítés előtt is sikeres volt.

A záró futás utáni független, natív olvasási ellenőrzés sikeres:

* aktív `hc-audit-20261103-r22`, változatlan 16 konténerazonosság és futási állapot;
* 805 runtime-forráshash, 25 unit/drop-in hash és öt mentési bind mount egyezik;
* mind a 32 hostcsomag pontosan a tervezett verziójú, a dpkg audit tiszta;
* új boot és a 202-es kernel, backend health/readiness, öt aktív/engedélyezett timer;
* AI tiltva, routeres mentés engedélyezve, Zigbee MQTT bridge online és Growatt HA-adat elérhető;
* az eredeti `HC_REFACTOR_AUDIT.md` változatlan.

[Nyilvános zárónyugta és bizonyítékok](audit-evidence/host-update-20261103/final-handover.json).
A root mentési/restore bizonyítékok forrása a felhasználó által közölt sikeres,
lezárt executor-futás; a privát nyugtát az asszisztens nem olvasta ki közvetlenül.
Helye: `maintenance/host-update-20261103-execution/finish-success.json`.
A nyilvános nyugta külön jelöli a független élő ellenőrzést és a root futás kimenetét;
privát naplót vagy hitelesítési adatot nem tartalmaz.

Az eszközpróbák olvasási és kapcsolati próbák voltak, teljes kézi funkcionális
tesztet nem állítunk. A lezárt telepítési/folytatási indítók nem ismétlendők;
a korábbi készleteket, archívumokat és privát bizonyítékokat megőriztük.

Az r22 auditátadása változatlan: **46 Ellenőrzött, HC-41 és HC-43 Folyamatban**.
A hostfrissítés nem módosította a konténer-image-eket, ezért a gyártói javításra
váró HC-43 sérülékenységeket nem zárja le. Új teljes auditot ebben a karbantartási
körben nem futtattunk.
