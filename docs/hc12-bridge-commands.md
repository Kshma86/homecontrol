# HC-12 – Korlátos bridge-parancsfeldolgozás

**Aktív: `hc-f10-20261031-r13`, élesítve, szoftveresen ellenőrizve.**
Az r12 HC-12/32 és HC-23/43 részjavításai, valamint az X10 indulási online-jelzés
korrekciója éles. Nyolc alkalmazás a várt image-en healthy, restart0; DB/MQTT
és minden backend health/worker/readiness sikeres. X10 online=1 és friss
telemetriát küld, tölt. Az r13 csak X10+backend újraindítás volt, a másik
14 konténer ID/image változatlan. 690 telepített forráshash egyezik.
Öntözés winter, védelmi API idle, a védelem enabled=true, AI SSD-korlátozás megmaradt.
[Éles r13 átvétel és rollback](../backups/deployments/hc-f10-20261031-r13/DEPLOYMENT.md).
Az első r13 helyi mentés sikeres, 3239 checksum ellenőrizve; fizikai
eszköz-/élőtérképpróba még felügyelt feladat.

A következő feljegyzések korábbi kiadási állapotokat őriznek.

**Aktív: `hc-f10-20261031-r12`, élesítve és szoftveresen ellenőrizve.**
Nyolc pinned alkalmazásimage healthy, restart0; DB/MQTT és worker-readiness jó,
platformkonténer-ID-k változatlanok, frontend HTTP200. Telepített 690 forráshash
rendben. Öntözés winter profil, AI SSD-korlátozás megmaradt. Első éles r12 helyi
mentés completed, 2494 fájl ellenőrzött checksumával.

**Utóellenőrzési javítás előkészítve: r13.** X10 friss adatot küldött, de a régi
retained offline jelzés cache-elődött. A valós online jelzést egyszer helyreállítottuk;
a tartós callback-javítás külön új image, változatlan függőségekkel. Három baked
regresszió, 16 telepítőteszt és 25 image-es offline load sikeres. X10+backend
újraindítás szükséges, a többi szolgáltatás futva marad; helyi sudo-ra vár.
[Éles r12 ellenőrzés](../backups/deployments/hc-f10-20261031-r12/DEPLOYMENT.md),
[r13 javítás átadása](../backups/deployments/hc-f10-20261031-r13/PENDING.md).

A további bejegyzések korábbi helyi/kiadási állapotokat dokumentálnak.

2026-10-31. **Javítva és helyben ellenőrizve; nincs élesítve.**
Elolvasva az eredeti HC-12 megállapítás, az I. reprodukciós táblázat és a J.
AST/barrier módszertani bizonyíték; az F10 lépés F0/F2 előfeltételeivel együtt.
HC-32 vagy más auditpont nem kapott automatikus javítást/lezárást.

## Kiindulási hiba és igazolás

Tuya korlátlan Queue-ját a polling főciklus és külön worker is fogyasztotta.
A F0 SHA256-tal egyező korábbi forrásból, két eredeti függvénnyel és barrierrel
újra reprodukáltuk: az ON előbb került ki a sorból, mégis OFF→ON lett az aktuátor-
fixture hívási sorrendje. A javított tényleges callback+handler mellett ON→OFF.
Gree és X10 minden üzenethez új szálat indított; csak utána vártak az eszközlockra.
Gree/Tuya a callbackben nem szűrte a retained replayt.

## Új feldolgozási szerződés

Bridge-enként egy `CommandDispatcher`, egy parancs-worker, korlátos memóriasor.
A Tuya polling ciklus nem fogyaszt parancsot. Gree/X10 callback csak validál és
befogad vagy elutasít, új parancsszálat nem indít. A normál parancsok FIFO-sak;
mozgási parancsokra nincs általános „utolsó érték” összevonás.

| Beállítás | Tuya | Gree | X10 |
|---|---|---|---|
| Környezeti prefix | `TUYA` | `GREE` | `X10` |
| `*_COMMAND_QUEUE_SIZE` | 32 | 32 | 32 |
| `*_COMMAND_MAX_PAYLOAD_BYTES` | 4096 | 4096 | 4096 |
| `*_COMMAND_MAX_AGE_SEC` | 30 | 30 | 180 |

A 32 a várakozók száma; ezen felül egy művelet futhat. Egy hely STOP/OFF számára
fenntartott, ezért normál paranccsal legfeljebb 31 hely tölthető fel. Teljes
sorban új STOP is elutasítható, ha más célok STOP-jai foglalják el a korlátot.
A hibás beállítás induláskor hibát ad. X10 hosszabb alapértéke a meglévő 120s-os
map subprocess és több lépéses térkép-/ütemezési műveletek miatt szükséges;
éles késések alapján a határok külön konfigurálhatók. Új külső függőség nincs.

A lejárat monoton időből indul. A worker és az eszköz-/transportlock megszerzése
után is ellenőrzi: Tuya közvetlenül set_status előtt; Gree az induló hálózati
olvasás után és push/persist előtt; X10 a közös MIIO-flockon belül, minden új
transporthívás előtt. A már elküldött I/O nem szakítható vissza; a lejárat vagy
STOP a későbbi őrzött lépéseket tiltja meg. A szokásos transporttimeoutok és az
X10 watchdog megmaradtak, új automatikus parancsretry nincs.

### STOP/OFF domainpolitika

- **Tuya:** érvényes OFF elsőbbségi. A name/device_id alias ugyanarra a kanonikus
  célra oldódik. A cél régebbi várakozó kapcsolásait visszavonja, más eszközökhöz
  tartozó parancsokat megőrzi. A már futó ON után OFF következik; régi ON nem
  éledhet fel utána. A poll miatti runtime-rebuild is ugyanazon eszközlockot használja.
- **Gree:** validált `power=off` elsőbbségi. Hibás kevert OFF/settings nem vonhat
  vissza érvényes munkát. A régi célbeállítások visszavonódnak; queue-hibánál a
  command_result megőrzi a `command.hc_execution_id` korrelációját.
- **X10:** `stop` elsőbbségi. Korábbi mozgás/beállítás/ütemezésírás/capture és
  belső watch-intent visszavonható; `status`, `read_scheduler`, `check_map`,
  `refresh_map` olvasások megmaradnak. A `home` önálló mozgásparancs, normál FIFO.
  A HC helyi késleltetett direct-start fallbackje STOP-kor megszűnik akkor is,
  ha a fizikai STOP küldése hibázik. A robotban már tárolt jövőbeli/ heti
  ütemezések törlése külön művelet; a STOP nem törli őket automatikusan.

A később érkező új ON/start új kezelői szándék, végrehajtható. Egy elutasított
STOP nem módosítja a korábbi szándékot; a visszavonás és befogadás atomi.
Az X10 belső watch/direct-start ugyanahhoz a workerhez került, mert különben
második actuator-owner maradt volna. A periodikus watch csak üres/tétlen,
online sornál kerül be, nem halmozódik fel. MQTT-ről a belső művelet nem hívható.

### Elutasítás és kapcsolatvesztés

Retained replay, túl nagy/hibás payload, queue_full, expired, offline,
connection_lost/reset, superseded_by_stop és shutdown elkülönített kimenet.
A meglévő command_result sémában `ok=false` és kód jelzi a sor döntését;
a befogadás önmagában nem sikeres fizikai végrehajtás. A Gree megőrzi a
korrelációs mezőket. A Tuya új callback/sorelutasítása közvetlen, QoS0, nem retained,
nem futtatja a régi szinkron reconnect-helperét. Offline az eredmény csak a
lokális queue-számlálóban marad; a hálózati visszaigazolás nem garantált.

Minden kapcsolati generáció eldobja a várakozó sort, és érvényteleníti a futó
parancs későbbi őrzött lépéseit. Reconnect/restartkor nincs visszajátszás.
Rendezett lezáráskor a sor törlődik, a workerre legfeljebb 2s-os join történik;
a folyamat/transport további életciklusát nem helyettesíti ez a lokális API.
Az MQTT3 retained-bit a replayt jelöli; a már online feliratkozónak küldött,
RETAIN-flages publikációt e protokoll nem különbözteti meg általánosan.

## Érintett forrás és csomagolás

Kanonikus `apps/bridge_runtime/command_dispatcher.py`, azonos önálló másolattal
mindhárom bridge contextben. A másolatok egyezését teszt ellenőrzi. A Tuya/Gree
Dockerfile a dispatchert és a meglévő `mqtt_credentials.py`-t együtt másolja;
X10 eddigi COPY-ja tartalmazza az új modult. Ez az önálló bridge-build működéséhez
szükséges HC-41-integráció, nem új broker-/hitelesítésmódosítás.

A bridge-ek és az X10 runtime/teszt változott; backend/frontend, DB/migráció,
függőségverzió vagy éles Compose nem. A Tuya `mqtt_publish`,
`mqtt_publish_changed`, `parse_partial`, `mqtt_publish_device` függvény AST-je
változatlan a korábbi forráshoz képest: HC-32/34 nem lett belekeverve.

## Ellenőrzés

- **33 új queue-/tényleges bridge-függvényes teszt**, 0 hiba.
  2000-es burst, korlát/fenntartott STOP-hely, egy fogyasztó, name/id alias,
  FIFO, retained, lejárat a poll-lock után, megszakadt kapcsolat és shutdown;
  Gree hibás kevert OFF és kezdeti hálózati olvasás utáni lejárat;
  X10 mozgási sorrend, belső watch-owner és STOP utáni fallback-visszavonás.
- **32 X10 runtime-/watchdog-/map-regresszió**, 0 hiba, benne a MIIO-záron belüli
  pre-send guard, hibájánál a lock felszabadulása és a következő poll sikere.
- **25 backend scheduler/bridge-feedback szerződésteszt**, 0 hiba.
  Friss eszközminta, korrelált Gree-válasz és X10 wire parser megmaradt.
- **9 valódi izolált brokeres eset** (3 bridge × retained, telített sor+STOP,
  reconnect), mind sikeres. A tényleges on_message és handlerfüggvények,
  helyettesített aktuátorok futottak. A kapcsolati callback a labor adaptere,
  nem a teljes bridge-processz indulása. 13 telítettségi válasz/bridge és
  3 STOP által visszavont várakozó intent/bridge; a megfigyelt aktuátorhívások
  ON→OFF, illetve start→stop. A retained replay reconnectkor sem indított eszközt.

A broker külön `--internal` Docker-hálózatban futott, publikált port nélkül;
a kliens read-only/capability nélküli, az aktuátor és eszköz-I/O fixture.
A labor anonymous brokert használt, a már éles HC-41 ACL-t nem változtatta.
A konténerek/hálózat eltakarítva. A fizikai kapcsolási/STOP-próbát és a teljes
három bridge-processz hardveres/offline terhelését ez nem helyettesíti.
A suite-ok végső futásai összesen 90 teszt, a 9 brokeres eset külön bizonyíték.
Az X10 meglévő regex escape figyelmeztetése nem új hiba, ezen nem változtattunk.
A köztes próbaútvonal-hibák nem kaptak sikeres minősítést.

A végén mind a **16 éles konténer** ID/image/start/restart/status változatlan,
a r10 **646 lezárt runtime-forrásfájlja** hash szerint egyezik. Az eredeti audit
SHA256 változatlan. Nincs build/élesítés, fizikai parancs vagy újraindítás.

## Függőségek és későbbi átadás

**Utókövetés:** a későbbi REPAIR-055 már javította és ellenőrizte HC-32-t;
HC-23/43 részben elkészült. Az aktuális kiadási kapuk és eredmények a
[kapcsolódó javításoknál](hc32-23-43-followups.md) vannak. Ez a HC-12 dokumentum
és a lenti eredeti leírás a REPAIR-054 külön ellenőrzött forrásállapotát őrzi.

A REPAIR-054 idején HC-32 általános Tuya publish/fingerprint hibája külön nyitott pont volt. A jelen
lokális queue-helyességet nem blokkolja, de megbízható end-to-end telemetria-
átadást nem szabad a régi publisherből levezetni. HC-23/43 reprodukálható
build/health és függőségfrissítés külön nyitott marad. A HC-09/F2 állapotszerződés,
a HC-13/korábbi MIIO timeoutok és a HC-41 hitelesítési beállításai megőrzendők.
Nem készül automatikus javítás ezekhez vagy a natív robotütemezésekhez.

Élesítés előtt bridge-enként külön, rögzített jelenlegi alapra épített image,
az új modul és meglévő auth-helper együtt; izolált teljes processz-/hardverpróba,
aktív munka nélküli átadás és a régi kép/forrás megőrzése kell. A három bridge
külön kiadható. Az aktuális r10 kit/runtime nem írható felül e munkafával.

## Visszaállítás

Éles átadás most nincs, így éles rollback sem kell. A lokális régi források az
`audit-evidence/hc12-20261031/original/` alatt a F0 hash-leltárhoz igazoltan
megőrizve; a két Dockerfile-ból csak a hozzáadott COPY-sor elhagyása rekonstruálta
az eredeti F0 hash-t, az X10 runtime az aktív változatlan image forrásából származik.
A többi eredeti a lezárt runtime-ból vagy változatlan helyi fájlból ellenőrzött.
Későbbi rollback a korábbi bridge-image-et állítsa vissza, a régi RAM-sort soha
ne játssza vissza. X10 helyi fallback-intentet se állítsunk vissza egy régi snapshotból.

[Gépi összesítés](audit-evidence/hc12-20261031/summary.json),
[előállapot](audit-evidence/hc12-20261031/before.json),
[eredeti sorrendhiba](audit-evidence/hc12-20261031/before-order.json),
[izolált broker](audit-evidence/hc12-20261031/broker.json),
[éles változatlanság](audit-evidence/hc12-20261031/after.json).
