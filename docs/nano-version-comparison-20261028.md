# Nano-kapcsolat: régi és éles HC összehasonlítása

Vizsgálat: 2026-10-28, Budapest. Kizárólag olvasás és hálózat nélküli feldolgozási próba; alkalmazáskód, konfiguráció, adatbázis, auditstátusz és éles kiadás nem változott. Eszközparancs, újraindítás vagy visszaállítás nem történt. A lezárt r7 csomagot nem módosítottuk.

## Eredmény

A vizsgált kódok és az aktuális MQTT-forgalom alapján nincs bizonyíték arra, hogy a legutóbbi HC-élesítés miatt tűnt volna el a Nano. Az ESP napelemes MQTT-adatokat küld, de a megfigyelés alatt sem STATUS, sem TELE nem jelent meg a brokeren. Az ESP legutóbb tárolt diagnosztikája maga is hibás Nano/UART-kapcsolatot jelent. A pontos fizikai vagy firmware-ok további helyszíni/UART-vizsgálat nélkül nem dönthető el.

## Kódösszehasonlítás

A tényleges Docker-képekből kiolvasott öt modul: `topic_contract.py`, `mqtt_monitor_service.py`, `settings.py`, `app.py`, `irrigation_service.py`.

| Verzió | Nano fogadása és döntési logikája |
| --- | --- |
| Audit előtti `rollback-hc-audit-20261022-r1` | Azonos topicok, eszközazonosító, monitorindítás és feliratkozások. A szelepdöntés még a mintakor és online állapot ellenőrzése nélkül használta a gyorsítótárat. |
| Október 23-i `hc-sleeping-20261023-r2` | Már tartalmazza a HC-01 frissességi ellenőrzést. |
| Előző `hc-opening-events-20261027-r4` | Nano-fogadása és `live_valve_state` döntése azonos az r2-ével. |
| Éles `hc-refactor-ai-offline-20261027-r6` | A monitor fogadási ága az előzőével azonos; az új policy a publikálást korlátozza. A Nano szelepdöntésének AST-hashe megegyezik az r2/r4-ével. |

Mind a négy kép `topic_contract.py` fájlja bájtra azonos. Az `IRRIGATION_DEVICE_ID` alapértéke változatlanul `esp-irrigation-1`; az éles konténerben nincs ezt felülíró környezeti változó. A monitorindítás AST-je is azonos. A `nano_status` és `pump_metrics` pontos topicjai mellett mindkét teljes `tele/irrigation/esp-irrigation-1/#` és `stat/irrigation/esp-irrigation-1/#` ág fel van iratkozva.

Az r2 és az éles r6 fagyasztott `Irrigation.jsx` fájlja szintén bájtra azonos: SHA-256 `dd1919f7035575539b10ea691017818f4443dfae0601365199f85121badbb1a9`.

A régi kód a meglévő régi mintát tovább használhatta; ez nem bizonyít friss Nano-kapcsolatot. A most hiányzó STATUS/TELE üzeneteket az audit előtti feldolgozó sem tudná előállítani.

## Éles megfigyelés

- Közvetlen, csak feliratkozó, egyedi kliensazonosítós MQTT-megfigyelés: **13:52:10–13:52:55 CET**, `homecontrol/tele/#` és `homecontrol/stat/#`, a kimenet Nano/öntözési topicokra szűrve. Két nem retained `solar` üzenet érkezett. STATUS, TELE és más néven érkező friss Nano-üzenet nem volt ebben az ablakban. Ez időben korlátozott megfigyelés, nem teljes forgalmi történet.
- A HC API szerint a monitor MQTT-kapcsolata működik, `last_error` üres; `esp_nano_status` és `pump_metrics` nincs a gyorsítótárában. A napelemes adat közben frissül.
- Utolsó **adatbázisba fogadott** Nano-mérési csomag: **2026-10-25 22:24:43 CET**, topic `.../pump_metrics`, nem retained. Ekkor `voltage_12v=10.81`, motoros szelep `UNKNOWN`, kézi szelep `OPEN`. Ez fogadási idő, nem igazolt mintavételi idő; újrapublikálás lehetséges. Nem tekinthető a jelenlegi fizikai állapotnak.
- A legutóbb tárolt ESP-diagnosztika fogadási ideje **2026-10-28 13:48:00 CET**. A kiolvasáskor 347 másodperces volt: `nano_online=false`, `nano_serial_healthy=false`, `nano_cmd_timeout_count=61861`, `nano_cmd_fail_count=61863`, `nano_health=FAULT`, `nano_code_text=SUPPLY_LOW`. A legutóbb megőrzött hibás PING-parancsban sérült karakterek is vannak. Ezek tárolt diagnosztikai értékek, nem most végzett elektromos mérés.
- Ugyanebben a diagnosztikában a TELE mintakora `300125 s`. A fogadási időből visszaszámolva ez körülbelül **október 25. 02:25:55 CET** mintára utal. A napi óraátállítást a Europe/Budapest időzóna kezeli. A számláló és az ESP firmware működése miatt ez becslés; a későbbi DB-fogadásból sem következik új Nano-minta.
- Az éles r6 backend csak **október 27. 18:47:35 CET** indult: a tárolt Nano-adatok megszakadása korábbi.

Az ESP→MQTT→HC útvonal napelemes adatokkal működik. A diagnosztika az ESP↔Nano soros kommunikáció vizsgálatát indokolja: Nano tápellátás, közös GND, RX/TX csatlakozások, illetve UART/firmware működés. A `SUPPLY_LOW` és a régi 10.81 V táphibát is felvet, de nem bizonyít jelenlegi alulfeszültséget. Nano/ESP firmware-forrás nem található a vizsgált helyi `apps`/`infra` forrásokban.

## Külön, korábbi topiceltérés

A brokeren van retained `.../nano_config`, miközben a HC `nano_config` nevű belső állapotához a szerződés **`.../nano_cfg`** topicot rendel. Ez már az audit előtti képen is így szerepel. A wildcard fogadja az üzenetet, de a nevesített konfigurációs mezőben emiatt nem jelenik meg. A konfigurációs kijelzés külön hibája; a `nano_status`/`pump_metrics` hiányát nem magyarázza. Ebben a vizsgálatban nem javítottuk.

## Ellenőrzés és bizonyítékok

Mind a négy eredeti monitoron hálózat nélküli visszajátszást futtattunk. Az észlelt topicokból egyik sem állított elő hiányzó STATUS/TELE vagy nevesített konfigurációs adatot; a helyes topicokra helyben beadott szintetikus STATUS és TELE üzenetet mind a négy feldolgozta. Az összes feliratkozás azonos. A próba kizárólag callbackhívás, nem csatlakozik brokerhez, nem publikál, és nem igazol fizikai Nano-működést.

[Szűrt API-állapot](audit-evidence/nano-version-comparison-20261028/live-state.json), [passzív MQTT-megfigyelés](audit-evidence/nano-version-comparison-20261028/passive-mqtt.json), [ESP-diagnosztika](audit-evidence/nano-version-comparison-20261028/diag-latest.json), [utolsó tárolt mérések](audit-evidence/nano-version-comparison-20261028/last-nano-measurements.json), [kódhashek és összevetés](audit-evidence/nano-version-comparison-20261028/code-comparison.json), [visszajátszás eredménye](audit-evidence/nano-version-comparison-20261028/replay-results.json), [képek azonosítói](audit-evidence/nano-version-comparison-20261028/images.txt).
