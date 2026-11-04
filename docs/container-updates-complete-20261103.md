# A HC konténerfrissítések lezárva

REPAIR-096, 2026-11-03. **Aktív kiadás: `hc-containers-20261103-r23`.**
Végállapot: `container_updates_backup_restore_verified`.

A 12 tervezett image éles, a hozzájuk tartozó 12 szolgáltatás új konténerekkel
fut. Az átállítás előtti teljes repository-adatellenőrzés, friss teljes
HC/Git/router előmentés és külön PostgreSQL-restore teljesült. Az átállítás
után új teljes mentés, router-visszaolvasás és izolált PostgreSQL-restore is
sikeres. Az eredeti health/timer-kapuk a health oneshot sikeres befejezése
után teljesültek.

Az új utómentés nyugtája:

- Run: `0d5e07d8aeef48fda2ef2e2d62c48796`.
- Snapshot: `d1e2af2fc270f95401465946fccc499aca37a2c6f6d26499734ee952b12c2762`.
- Archívum SHA-256: `0a10c9f9ec7ac673468273fe4c1c1d2f96d5490751c2e4998ad77a4fc342748f`.
- Visszaolvasás és adatbázis-visszaállítás: `verified`.

A root kimenet és az eredeti kiadáshoz kiírt nyilvános
`deployment-status.json`, `evidence/post-live-check.json`, valamint
`evidence/router-live-acceptance.json` nyugtái egyeznek. A privát végrehajtási
naplót és megőrzési journalt az asszisztens nem olvasta ki közvetlenül.

## Független éles ellenőrzés

A sudo-futás után külön natív, csak olvasó ellenőrzés is sikeres:

- Mind a 16 konténer a sikeres root átvétel szerinti ID-val, image-dzsel,
  futási/health állapottal és restart-számmal szerepel. 15 fut; az Adminer
  szándékosan leállítva maradt. Nincs más futó tesztkonténer.
- A négy megőrzött konténer – PostgreSQL, PgBouncer, Home Assistant, Adminer –
  eredeti azonosítója egyezik az r22 baseline-nal.
- Mind a **823 runtime-forráshash** és **25 unit/drop-in hash** egyezik.
  Öt timer aktív/engedélyezett, van következő időpontjuk; a health oneshot
  eredménye success, exit 0. A két vezérlő path és a hostops/MQTT guard aktív.
  A natív időzítés-ellenőrzés a root által elfogadott unit-hashekhez és az élő
  systemd-állapothoz hasonlított; az aktuális privát settingsből generált teljes
  eredeti kapukat a root futás ellenőrizte.
- Az öt mentési bind mount az elfogadott host-layout szerint maradt meg.
- Zigbee2MQTT **2.14.3**, **58 inventory-bejegyzés**; a bridge online.
  A root átállítási kapu a teljes előtte/utána eszközazonosító-egyezést is
  ellenőrizte. A külön natív próba a jelenlegi listát és darabszámot olvasta.
- Mosquitto **2.1.2**. A Growatt által használt HA-adat elérhető.
- Pip **26.3** mind a nyolc saját Python-image-ben.
- Frontend/proxy libexpat **2.10.0-r0**; Gree/X10 linux-libc-dev **6.12.115-2**.
- AI továbbra is tiltva; routeres mentés engedélyezve. A host kernel továbbra
  is **5.15.0-202-generic**, ehhez az átállításhoz nem történt új reboot.
- Az eredeti `HC_REFACTOR_AUDIT.md` SHA-256-ja változatlan:
  `51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.

[Nyilvános zárónyugta](audit-evidence/container-updates-20261103/final-handover.json)
és [a független élő ellenőrzés](audit-evidence/container-updates-20261103/independent-live-check.json).

## Megőrzött bizonyítékok és auditállapot

A lezárt kiadási/folytatási csomagokat és korábbi archívumokat nem írtuk át.
A két korai hiba indítási nyugtái és naplói megmaradtak; a második folytató
a korábbi privát execution/staging/cache állapotot a
`backups/releases/hc-containers-20261103-r23/private/preserved-before-owner-continuation`
könyvtárba helyezte át ellenőrzött megőrzési journal mellett.
A friss kiadás 31 image-es offline recovery-archívumot használ, az r22
visszaállításhoz szükséges image-ekkel együtt. A mentés és restore a friss
kiadáshoz tartozó archívumot ellenőrizte.

Előkészítési bizonyítékok: 1327 regressziós, 143 eredeti kiadási teszt;
a két folytatás javításaival 60 container-update teszt. A privát broker UID-jának
javítását teljes izolált broker/config/auth/persistence/log próba ellenőrizte.
Új image vagy alkalmazásmódosítás a második folytatásban nem került a csomagba.

**A konténerfrissítési karbantartás lezárva. Az audit továbbra is
46 Ellenőrzött, HC-41 és HC-43 Folyamatban.** HC-41 az ESP MQTT-jelszó migrációja,
HC-43 a nyilvántartott gyártói maradványok miatt marad nyitva. A korábbi
12 image-es scan a most telepített, azonos image-ID-ket vizsgálta; e lezárásban
új teljes sérülékenységi auditot nem futtattunk. A frissítés nem jelenti minden
nyilvántartott sérülékenység megszűnését.

Az eszközpróbák olvasási/kapcsolati próbák, nem teljes kézi funkcionális tesztek.
Az r23 friss backup/PG-restore átvétele sikeres; új bare-metal/VM-recovery-próbát
ez a kör nem állít. A korábbi aktiváló és folytató indítók egyszeriek, siker
után nem ismétlendők. Későbbi visszaállítást a megőrzött transition, MQTT/Zigbee
adatmásolatok és mentési nyugták alapján kell külön előkészíteni.
