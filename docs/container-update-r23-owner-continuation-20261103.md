# R23 második folytatás – a privát broker-próba tulajdonosi UID-ja

Állapot: **ellenőrzött előkészítés, helyi sudo indítására vár**. Aktív: r22.

A sudo-diagnosztika megerősítette, hogy a korábbi futás a
`prepare_new_private_runtime` fázisban, a konfigurációellenőrzés 115. sorában
állt meg. Mosquitto nem tudta megnyitni a konfigurációt. A 0700-as könyvtár és
0600-as fájl tulajdonosa UID/GID 1883; a próba UID 0, DAC_OVERRIDE nélkül futott.
Az előmentés és PostgreSQL-restore sikeres. Transition, új runtime és új éles
private könyvtár nem keletkezett; a korábbi workerek nem futnak.

A második folytató az eredeti r23 executorát és az első folytatás ellenőrzött
Zigbee-olvasóját használja. Kizárólag az izolált `mosquitto` test/start
parancsokat alakítja át UID/GID 1883-ra, hozzáadott capability nélkül. Az új,
védett konfigurációmásolat, az izolált hálózat, a rögzített image, az ACL-ek,
a backend hitelesítési próbája, az időkorlátok és a teljes cutover/rollback
függvények megmaradnak. A backend próbakliensének saját UID/mount beállításai
változatlanok. Eltérő image, hálózat, config-mount vagy capability elutasított.

A guard újra kiolvassa a root-diagnosztikát, és megköveteli a pontos hibát,
a sikeres korábbi mentés/restore-nyugtát, a staging 1883-as tulajdonosát és az
átállítás teljes hiányát. A két korábbi csomag forráshash-ei ellenőrzöttek;
az eredeti r23 823 forrásfájlja és a 12 frissítendő image változatlan.

Az eredeti indítási jelző, első hiba és napló a helyén marad. A korábbi futás
további privát állapota – staging, izolált próbadata, cache és nyugták – az
eredeti private könyvtáron belüli `preserved-before-owner-continuation` könyvtárba
kerül átnevezéssel, inode- és fájlhash-ellenőrzéssel. A lépések külön root-védett
journalba kerülnek. Nincs törlés, a konfigurációtulajdonos módjai sem változnak.
Váratlan symlink, mount, részleges átállítás vagy már létező megőrzési cél esetén
az eljárás megáll. Az első folytatás saját hibája és naplója változatlanul megmarad.

Minden eredeti kapu újrafut: r22 postcheck, fizikai nyugalmi állapot, teljes
repository-adatellenőrzés, **új** teljes HC/Git/router előmentés és PG-restore,
privát broker- és titkosított bundle-próba, sorrendezett átállítás, friss teljes
utómentés és restore, eszközazonosítók, timerek, tűzfal, runtime-hashek.
A korábbi sikeres előmentés nem helyettesíti az új futás előmentését.

Ellenőrzések:

- 26 célzott teszt a második csomagból; 60 container-update teszt összesen.
  Lefedik a pontos hiba kapuját, a brokerparancs szűk átalakítását,
  a kliens változatlanságát, a fájlok/inode-ok megőrzését, a részleges
  átnevezési hiba naplózását és a teljes eredeti cutover callbackek megőrzését.
- Teljes izolált próba az új Mosquitto- és backend-image-dzsel, szintetikus
  adaton, host bind és éles mount nélkül: az eredeti UID 0 konfigurációpróba
  exit 3; az 1883-as tulajdonosi próba exit 0; brokerindítás, az eredeti
  fagyasztott klienskóddal hitelesítés, persistence és naplóírás sikeres.
  A broker hozzáadott capability nélkül futott.
- Natív éles ellenőrzés: r22, 16 változatlan konténer/image, 805 runtime-forrás,
  25 unitfájl, öt timer és öt backup-mount rendben.
- A korábbi 1327 regressziós és 143 kiadási teszt eredménye megmarad;
  alkalmazásforrás és image ebben a folytatásban nem változik.

Indítás, a robot dokkolt/töltő állapota és öntözési nyugalom mellett:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23-continuation-2/source/resume_r23_owner.py
```

Végállapot siker esetén: `container_updates_backup_restore_verified`.
HC-41/43 továbbra is Folyamatban. Hostreboot nem része az eljárásnak.

Hibánál az indítást ne ismételd. Állapot:

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-containers-20261103-r23-continuation-2/source/resume_r23_owner.py status
```

Bizonyíték és lezárás:
`backups/releases/hc-containers-20261103-r23-continuation-2/evidence/`,
`acceptance.json`. A nyers napló és a privát állapot root-védett marad.
