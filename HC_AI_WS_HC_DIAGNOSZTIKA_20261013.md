# HC → rover WebSocket diagnosztika – 2026-10-13

A felhasználó explicit Kézi mód próbáinak eredménye: előbb INVALID_RESPONSE, majd LINK_LOST, a HC időzítési javítása után TIMEOUT.

## HC javítás

A claim beérkezési határideje 1,5 s lett, a drive/drive_erpm 100 ms korlát változatlan. A kapcsolat elején végzett identity/state/health/parameters olvasások miatt a claimet korábban tévesen a 100 ms drive-határidő dobhatta el. STOP/release nem esik ki a motorcélokra szánt határidő miatt. A belépési snapshot rövid olvasási torlódását legfeljebb 1 s-ig kivárja; az állapot érvényessége és a natív képességjelző továbbra is szükséges. A hibadiagnosztika megkülönbözteti a browser/native frame hibát és a kapcsolat fázisát. 261 backend teszt: 15 kihagyott, a többi sikeres.

## Utolsó kezelői próba

Relénapló:
`stage=browser_receive phase=CLAIMING code=TIMEOUT exception=RoverReadError`

A CLAIMING fázisba érvényes browser claimmel lépett a HC, és a claimet egyszer továbbította az upstream WebSocketre. Native claimed/error válasz nem jutott el a reléhez a belépési határidőn belül. Nincs automatikus claim/ARM vagy motorcél replay.

A csak GET utóellenőrzés: STATE DISARMED, manual_lease_id=null, control_epoch=12. Identity test_manual_control=true, manual_erpm=true. HEALTH stm_peer_alive=true, uart_tx_expired=0, uart_input_errors=0, uart_rx_faults=0. Ez nem bizonyítja, hogy az STM korábban nem kezelte a claimet; a lezárás utáni állapotot mutatja.

## Mozgás nélküli kapcsolatpróbák

A HC backendből a provisioned címen, szerveroldali Bearerrel, `/api/v3/manual` útvonalon és `homecontrol.mower.manual.v3` subprotocollal:

- A kézfogás sikeres: HTTP 101, megfelelő subprotocol.
- A HC bounded kliensével PING után 2 s-ig nincs olvasható PONG/adat: WebSocketTimeoutException.
- Változatlan websocket-client create_connection használatával ugyanez az eredmény.

Ezeken a külön kapcsolatpróbákon nem küldtünk claimet, ARM-ot vagy motorparancsot. A PING hiányzó válasza a claimhibával együtt a natív WS RX/TX feldolgozás további vizsgálatát indokolja; önmagában nem bizonyítja a pontos firmware-hibahelyet.

## Roveroldalon ellenőrizendő

Az authenticated 101 után a masked WS frame feldolgozás, a claim fogadása, a MANUAL_BEGIN/ACK út és a claimed/error válasz tényleges socket-TX-je. Az explicit kezelői claim során szükséges roveroldali napló; nincs új automatikus HC mentés vagy függőkérés-elvetés engedélyezve. Titok/token nincs ebben a jegyzőkönyvben.
