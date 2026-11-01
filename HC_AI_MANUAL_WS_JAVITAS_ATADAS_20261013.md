# HC kézi WebSocket — feltöltött roverjavítás, 2026-10-13

Az ESP ws-stack16 javítása **fenn van és mozgásmentesen boardon ellenőrzött**.
Az előző 101 utáni eltűnés oka a rover WS-workerének veremtúlcsordulása volt.
A lokális Wslay-puffer veremterhelése csökkent, a worker több vermet kapott.
Nem HC-deadline vagy motorengedély-kapu lett lazítva.

Élő bizonyíték: érvényes 101 + `homecontrol.mower.manual.v3`, claim nélkül
16 observed frame 3 s alatt, külön kapcsolaton PING → azonos payloadú PONG
71 ms alatt, stabil ESP boot. Mért minimum WS-veremtartalék: 5100 byte.
Rev4/CRC3351E452 ACTIVE/APPLIED megmaradt; nincs Apply vagy függőkérés-elvetés.
Részletes jegyzőkönyv: `artifacts/rover-ws-stack16-20261013/RELEASE_STATUS.md`.

## HC-n kell-e módosítani?

Útvonal, Bearer, subprotocol és claim/claimed/error/observed séma változatlan.
A HC 1,5 s claim-határa és a drive/drive_erpm 100 ms határa maradjon.
Új, opcionális diagnosztikai mező a GET `/api/v3/health` válaszban:
`esp_stack_min_bytes.manual_ws`. Null, ha még nem futott WS-worker; különben
valós bájtérték. Nem ARM-engedély, nem HC által teljesítendő új feltétel.

## Következő explicit kezelői próba

1. Friss entry snapshot, új WS kapcsolat; a régi boot/session/lease objektumok
   nem használhatók újra. Az ESP a feltöltés során újraindult.
2. A kezelő Kézi mód belépése egyetlen claimet küldjön. Várt út:
   HC claim → ESP MANUAL_BEGIN → STM ACK → ESP claimed vagy natív error.
3. `observed` és PONG nem claimed/ARM igazolás. CLAIMING alatt érkező observed
   frame miatt ne aktiválj hajtást és ne ismételd meg a claimet.
4. Elveszett válaszra nincs automatikus claim/ARM/drive replay. Native error
   esetén a pontos code és friss STATE szükséges, nem új Apply a paraméterekre.
5. Csak igazolt claimed után, külön kezelői művelettel jöjjön motorcél-próba;
   disconnect/release maradjon scope-olt és motorcélok nélküli.

Ebben a körben tényleges board claim/MANUAL_BEGIN/ARM/motorparancs nem történt.
A transport javítása igazolt; a HC-n át történő teljes kézimód-belépést a
kezelő következő próbájával kell ellenőrizni. Nem autonóm/VG/OTA minősítés.
