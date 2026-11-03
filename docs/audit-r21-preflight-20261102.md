# r21 – mentési kapu az átállítás előtt

REPAIR-071, 2026-11-02. Aktív: `hc-security-20261102-r18`.
Az r21 előkészített kiadás; a sikeres éles átadás még nem történt meg.

Az r20 első kísérlete a mentési folyamat külső, 900 másodperces időkorlátjánál
állt meg. A külön, állapothoz kötött folytatás már elvégezte az átállítást,
de a friss heti mentés restic-lépése hibázott, ezért az automatikus rollback
visszaállította az r18-at. Az eredeti aktiválókat és a folytatót nem ismételjük.
A lezárt r19/r20/continuation forrás és bizonyítékok megőrzöttek.

## Mit bizonyított a diagnosztika?

A felhasználó által rootként futtatott diagnosztika teljesen visszaellenőrizte
a megőrzött helyi archívumot (2 162 709 837 bájt, 8082 fájl,
SHA-256 `3a8e1372a39a229971a8adfaee195a6e792fd387428d8d24efa67eb881881595`).
A repository teljes adatellenőrzése és a külön címkéjű diagnosztikai snapshot
is sikeres: exit 0, snapshot rövid azonosítója `e9113e45`.
Szolgáltatásváltás, megőrzés és törlés ebben a diagnosztikában nem történt.

Az eredeti restic-hiba nem ismétlődött meg. Pontos oka ismeretlen, mert az akkori
kód elnyelte a részletes hibakimenetet. A későbbi siker nem minősíti sikeresnek
a korábbi hibás mentési futást. A felhasználói kimenetet külön bizonyítékként
rögzítettük; a root-only eredeti naplót nem olvastuk jogosultságkerüléssel.

## Az r21 változásai

* A sikertelen restic/rclone műveletek stdout/stderr kimenete futásonként privát,
  0600-as fájlba kerül a `backups/router-diagnostics/` 0700-as könyvtárban.
  Parancssor és környezeti változók nem kerülnek a naplóba. A nyers kimenet privát
  marad; a nyilvános státusz csak a műveletet és kilépési kódot tartalmazza.
  A restic 3-as kódja továbbra is hibát jelent, nem válik sikeres mentéssé.
* Az átállítás előtt a még futó r18 teljes heti HC/Git/router mentést készít,
  majd visszaolvassa az archívumot és külön PostgreSQL-restore-t futtat.
  Négy kötelező mentési cél sikerét és az eredeti/visszaolvasott archívum
  SHA-256 egyezését követeljük meg. Addig az alkalmazások futnak.
* Ehhez külön r18-másolat futtatja az ellenőrzött mentőt az új privát naplózással;
  az éles r18 runtime és titkosított recovery-névtér változatlan.
* A korábban kipróbált systemd felügyelet a mentő teljes folyamatfáját kezeli:
  worker 10800 s, service 11400 s, szabályos leállítási türelem 90 s.
  Klienshiba esetén az aktiváló előbb leállítja a saját mentőegységét.
* A négy inaktív r19/r20 image-cache minden bájtját SHA-256-tal ellenőrizzük,
  és csak azonos tulajdonos/jogosultság/fájlrendszer mellett kapcsoljuk össze
  hard linkkel. A felhasználó inventoryja mind a négyre root:root, 0644,
  2 006 097 161 bájt, négy külön inode adatot igazolt. A művelet várhatóan
  6 018 291 483 bájtot, kb. 5,6 GiB-ot szabadít fel. Ez még nem történt meg.
  Mentési archívumot nem törlünk; a cache tartalma és hozzáférési jogai megmaradnak.
  Az új staging és telepített image-cache ugyanezeket a hitelesített bájtokat használja.
* A kapacitásellenőrzés két, a legnagyobb meglévő archívummal azonos méretű új
  mentéshez és további 2 GiB tartalékhoz kér szabad helyet; elégtelen hely esetén megáll.

A HC-15/16/20/23/24/26 korábban ellenőrzött javításai kerülnek élesítésre:
backend, mDNS és Growatt-poller image változik. Az alkalmazásforrások és image-ek
az r20-szal azonosak; új dependency, migráció vagy más auditpont-javítás nincs.
A fennmaradó 13 konténer megőrzése, HA API/PG ellenőrzés, titkosított titokmentés,
teljes repository-ellenőrzés, rollback és átállítás utáni teljes mentés/restore kötelező.

## Ellenőrzés és határok

105 friss sikeres teszt: 43 aktiváló/ütemezés/felügyelet/kapacitás, 16 tényleges
telepítő/rollback, 12 router-aktiváló, 4 privát naplózás, 21 router-szerződés,
9 mentési worker. A hoston hiányzó Flask és a konténerben hiányzó hosteszközök
miatti sikertelen próbák naplói megőrzöttek; a teljes érintett osztályokat
a megfelelő környezetben sikeresen újrafuttattuk, kihagyás nélkül.
Az első telepítő-fixture túl engedékeny fájlmódját a védelmi ellenőrzés elutasította;
a privát fixture jogosultságát javítottuk, az ellenőrzést nem lazítottuk.

A változatlan 363 alkalmazás-/tesztfájl és a három pontos image-ID igazolja a
korábbi 1308 külön regressziós teszt és baked-kód/csomaglista-bizonyíték átvételét.
Ezeket nem számoljuk újrafuttatott tesztnek. Új r21 bare-metal VM-próba nem történt;
a korábbi r18+recovery-javítás friss/ismételt/FTP-kiesési/reboot bizonyítéka megmaradt.
A teljes éles r18 és jelölt mentési/visszaállítási próbák a helyi root-aktiválás kapui.

Az eredeti audit SHA-256 lenyomata változatlan. A nyilvántartás továbbra is
46 Ellenőrzött és 2 Folyamatban: HC-41 ESP MQTT-jelszó, HC-43 a felhasználó
kifejezett döntése szerint gyártói javításig. Maradványkockázat-elfogadás nincs.
Az AI tiltva marad. A javítási kör éles átadását még nem állítjuk lezártnak.

## Helyi root-indítás

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r21/source/scripts/audit_release/activate.py
```

Az aktiváló egyszer indítandó. Előmentési hiba esetén nincs alkalmazásátállítás;
a továbblépéshez a napló és a rögzített állapot vizsgálandó. Átállítás utáni hibánál
a meglévő tranzakció visszaállítja az r18-at. Vakon egyik aktiválót sem ismételjük.
Csak az `ok: true`, `state: deployed_and_audit_handover_complete` eredmény és a
végső post-live-check igazolja az éles átadást. Az előzetes
`deployed_and_router_restore_verified` üzenet önmagában nem a végső eredmény.

A gyűjtött bizonyítékok és pecsétek:
`backups/releases/hc-audit-20261102-r21/evidence/acceptance.json`, `release.json`.
Éles siker után a `docs/audit-final-20261102.md` és a kiadás deployment-dokumentuma
automatikusan készül el. Addig a jelen dokumentumban szereplő függő állapot érvényes.
