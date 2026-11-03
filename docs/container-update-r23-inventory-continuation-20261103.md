# R23 folytatás – javított Zigbee-eszközlista-olvasás

Állapot: **előkészítve, helyi sudo indítására vár**. Aktív kiadás r22.
Az eredeti r23 csomag, indítási jelző és privát hibanapló megőrizve.

A kezelő sudo-diagnosztikája igazolta a pontos korai hibát: `starting` fázis,
`RuntimeError`/`TimeoutError`, utolsó parancs a `zigbee/bridge/devices` olvasása.
Sem progress, timer-szüneteltetési nyugta, mentési nyugta, staging, transition,
sem új runtime/private könyvtár nem keletkezett. Az első olvasó 65 536 bájtos
korlátja az élő, 197 796 bájtos, 58 eszközös üzenetet elutasította.

A folytató az eredeti lezárt executor `execute` függvényét hívja, annak összes
elő-/utómentési, repository-, restore-, fizikai, tűzfal-, timer- és rollback
kapujával. Egyetlen funkcionális adaptere a Zigbee-olvasó: a konkrét két topic
legfeljebb 2 MiB-os üzenetét olvassa, legfeljebb 1024 eszközzel, IEEE-cím- és
duplikációellenőrzéssel. A pontos bridge-verzió és a teljes eszközazonosító-lista
előtte/utána/rollback alatti egyezése továbbra is kötelező. Publish-t vagy
eszközvezérlést nem ad hozzá.

A folytató frissen visszaellenőrzi az eredeti root-diagnózist, a worker tétlenségét,
az r22 aktív állapotát, a korai állapot teljes hiányát és az eredeti privát
könyvtár megengedett bejegyzéseit. Eltérő hiba, részleges átállítás, hiányzó vagy
csonkolt bizonyíték esetén megáll. Az eredeti manifest, acceptance, launcher és
mind a 823 lezárt forrás hash-ellenőrzött. A 12 image és az offline archívum
változatlan; az eredeti executor a teljes image- és archívumkaput is újrafuttatja.

Külön, egyszeri folytatási nyugta és systemd-felügyelet készül. A régi három
fájlt (`activation-attempt.json`, `activation-error.json`, `activation-private.log`)
nem írja át: induló és záró SHA-256-nyugtával ellenőrzi megőrzésüket. Az új
napló a folytatási csomag root-védett `private` könyvtárába kerül. A további,
első futásnál még hiányzó execution/staging/transition állapotot az eredeti
executor az eredeti helyére írja; a végső átvétel az eredeti r23 kiadáshoz tartozik.

Ellenőrzések:

- 17 célzott teszt sikeres a folytatási csomagból: pontos hibaállapot-kapu,
  root-követelmény, a változatlan executor és cutover callbackek, adatméret,
  IEEE-azonosítók, duplikáció, verziókapu és diagnosztikai redakció.
- Összesen 43 container-update teszt sikeres a munkafából a korábbi
  tranzakciós/adatvisszaállítási tesztekkel együtt.
- Az éles r22 olvasási próbája mind az 58 eszközzel sikeres.
- Az új backend- és Mosquitto-image izolált, éles mount nélküli próbája sikeres
  egy 207 350 bájtos, 58 eszközös retained listával és 2.14.3 bridge-információval.
- Az eredeti 1327 regressziós és 143 kiadási teszt eredménye megmarad;
  alkalmazásforrás vagy image nem változott ebben a folytatásban.

Indítás:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23-continuation-1/source/resume_r23_inventory.py
```

A robot legyen dokkolva/töltésen, öntözés ne fusson. A root jelszót helyben
kell megadni. A friss teljes előmentés és PG-restore, majd az átállítás utáni
friss teljes mentés és PG-restore kötelező. Végállapot siker esetén:
`container_updates_backup_restore_verified`. HC-41/43 továbbra is Folyamatban.

Hibánál az indítást ne ismételd. Állapot, redaktált naplóösszegzéssel:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23-continuation-1/source/resume_r23_inventory.py status
```

Bizonyítékok és a folytatás lezárása:
`backups/releases/hc-containers-20261103-r23-continuation-1/evidence/`,
`acceptance.json`. A napló és a nyers eszközlista privát marad.
