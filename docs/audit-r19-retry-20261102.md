# Audit átadás – r19 hiba és r20 javítás, 2026-11-02

Az r19 átállt, majd sikeresen készített friss HC/Git/router mentést és külön
PostgreSQL-visszaállítási próbát. A végső időzítő-ellenőrzés azonban hibát jelzett,
ezért az aktiváló automatikusan visszaállította az r18-at. **Az audit átadása még
nem zárult le; jelenleg r18 aktív.** Az r19 aktiválását nem ismételjük meg.

## Bizonyított hibaok

A felhasználó helyi, root jogosultságú, csak olvasó diagnosztikája ezt adta:
`ValueError: Scheduled backup timers are not active`. A nyilvános állapotnyugta
`previous_release_restored`, az aktív marker `hc-security-20261102-r18`.

Az r19 záróellenőrzése a `backups/f6-installed.json` korábbi telepítési nyugtájából
választotta ki az engedélyezett időzítőket, majd ötöt követelt meg. A nyugta még
három aktív időzítővel számol: a heti és restic-check jelző benne hamis. A routeres
beállítások alapján generált tényleges ütemezésben viszont mind az öt engedélyezett,
aktív, és mindnek van következő futása. A nyugta az eredeti F6 telepítés történeti
eredménye; az utólag módosított ütemezés ellenőrzésére nem megfelelő forrás.

Az r19 sikeres mentési nyugtáját megőrizzük, de nem tekintjük az aktív kiadás
bizonyítékának. Run: `30942faa62bd4481b2c8a57abe732beb`;
snapshot: `706c0ee3acd24bb56c1b29b85d9cf11c8915112bed326484dcdd70d765bafd4d`.
A teljes repository-check, SHA-256 archívumellenőrzés, Git és külön PG-restore
sikeres volt; az automatikus visszagörgetéstől ez a bizonyíték megmarad.

## Az r20 változása

Az új kiadás: `hc-audit-20261102-r20`. A három alkalmazás-image azonos az r19-ben
ellenőrzött példánnyal; új build, csomagfrissítés vagy más auditjavítás nincs.
A rollback továbbra is az r18-at állítja vissza. Az r19 csomagot és bizonyítékait
nem írjuk át; az r20 új konténerbaseline-t rögzít a visszagörgetett állapotból.

A záróellenőrzés a lezárt F6-generátort `apply=False, restore_host=True` módban
hívja az aktuális privát mentési beállításokkal. Nem telepít unitot és nem írja
át a történeti nyugtát. A generált 14 alap-unit hashét, a kiadás saját unitjait
és dropinjait, az öt időzítő engedélyezését, aktív állapotát és következő futását
ellenőrzi. Ugyanez az ütemezési ellenőrzés a szolgáltatások leállítása előtt is
lefut; ekkor a kiadásváltásból következő dropin-útvonalak még nem követelmények.
A végső ellenőrzés hibája továbbra is visszagörgetést vált ki, és nem ír auditátadást.

## Ellenőrzés és korlátok

Az r20 lezárt forrásán **26 audit-aktiváló/utóellenőrzési/ütemezési/futtatói,
16 alaptelepítő- és 12 router-tranzakciós teszt sikeres**: összesen 54 friss eset.
A próbák lefedik a valós hibát, a timer kihagyását, az átírt unitot/dropint,
a kikapcsolt ütemezést, a hiányzó következő futást és a visszagörgetési kaput.

A nyilvános aktuális timerfájlokból készített beállítási fixture és a lezárt
F6-generátor 14 egyező unitot állított elő. Az új ellenőrző valódi, csak olvasó
systemd-próbája öt aktív, engedélyezett időzítőt és öt következő futást igazolt.
Ez a fixture-próba nem állítja, hogy root nélkül olvastuk a privát beállításokat;
azok ellenőrzése a helyi sudo aktiválás előkapuja.

Az r19 **1308 külön regressziós esetét** az azonos alkalmazás-/tesztbemenetekhez
tartozó korábbi bizonyítékként őrizzük. A 363 alkalmazás-/tesztfájl bájtra egyezik;
a három image beépített kódja és a csomaglista újraellenőrzött. Az r20-ra nem
állítunk új teljes regressziós vagy bare-metal VM-futtatást. A 19 image-es,
SHA-256-tal védett offline archívum változatlan és az eredeti load-bizonyíték megmarad.

**Az élesítés még hátravan.** A root aktiváló ismét teljes repository-checket,
ellenőrzött helyi mentést, háromkomponensű átállítást, friss Git/router mentést,
SHA-256/PG-restore próbát és végső runtime/systemd ellenőrzést követel meg.
Csak ezek után írja a `docs/audit-final-20261102.md` éles átadási nyugtát.

```bash
sudo python3 /srv/docker/homecontrol/backups/releases/hc-audit-20261102-r20/source/scripts/audit_release/activate.py
```

Az AI tiltva marad. A nyilvántartás változatlanul **46 Ellenőrzött, HC-41 és HC-43
Folyamatban**; HC-43 a felhasználó kifejezett döntése szerint a gyártói javításig.
Az eredeti audit SHA-256 változatlan:
`51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2`.

Bizonyítékok: `backups/releases/hc-audit-20261102-r20/evidence/`;
különösen `audit-retry-tests.log`, `generated-schedule-fixture.json`,
`readonly-live-schedules.json`, `unchanged-regression-inputs.json`,
`baked-code-and-packages.json` és a változatlan korábbi nyugtákat tartalmazó
`prior-r19/` alkönyvtár. A privát naplók és kulcsok nem megoszthatók.
