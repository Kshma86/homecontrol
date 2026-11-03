# ws-stack16 HC integráció

Forrás: HC_AI_MANUAL_WS_JAVITAS_ATADAS_20261013.md.

A natív observed frame claim nélkül és CLAIMING közben is érkezhet. A HC szerver és böngésző elfogadja a sémahelyes állapotjelzést, de nem ad lease-t, nem vált ACTIVE módra, nem küld motorcélt és nem ismétli meg a claimet. Csak a natív claimed válasz enged kézi vezérlést, friss, azonos boothoz kötött kapcsolaton. A régi ESP/STM bootra érkező claimed nem aktiválja a kapcsolatot.

A szerver továbbra is egyetlen explicit claimet továbbít, 1,5 s belépési határidővel; a drive/drive_erpm 100 ms limit változatlan. Native error esetén a pontos code látható és a böngésző friss STATE-et kér. Nincs Apply/ARM/claim/drive replay. A release az adott lease-re vonatkozik.

Az opcionális HEALTH esp_stack_min_bytes.manual_ws a snapshot és a diagnosztikai panel része. Null esetén még nincs mérés; egyébként bájtérték. Nem mozgási feltétel, hiánya nem tilt kézi módot.

Mozgás nélküli ellenőrzésben a rover már küld observed frame-et a sikeres natív WebSocket kézfogás után. Teljes kézi belépés és motorcél-próba csak explicit kezelői művelettel történik.

Éles, claim nélküli ellenőrzések: a native PING azonos tartalmú PONG választ kapott 58 ms alatt. A `ws://127.0.0.1:5000/api/mower/v3/manual` HC relén át megérkezett a `type=observed, lease_id=0, last_input_seq=0, state=IDLE, stopped=true` frame. A próbák nem küldtek claimet vagy motorcélt, és nem igazolnak ARM/claimed eredményt. 263 backend tesztből 15 kihagyott; a többi és mind a 79 frontend teszt sikeres.

Kapcsolatbontási vizsgálat: a kezelői claim eljutott ACTIVE fázisig. A relé egy native_receive/ConnectionResetError esetet is rögzített; ez a rover felőli TCP-bontás bizonyítéka, a pontos firmware-ok még nem ismert. A heartbeat 75 ms-ra módosult, hogy a régi natív 20 üzenet/s plafon alatt maradjon és a kezelői nullázásnak is maradjon tartalék. A 100 ms drive-frissesség és 350 ms natív input timeout változatlan. Ez önmagában nem bizonyítja a korábbi bontás okát. A natív WS CLOSE kód most külön megjelenik; nincs automatikus újracsatlakozás.

Aktív lease érvényességi javítás: a browser állapotkorában a backend feldolgozási ideje nem számolódik kétszer. A snapshot Server-Timing fejlécet ad; a kliens az RTT-ből levonja ezt, és csak a fennmaradó tranzitidőt adja a backend effektív forráskorához. Hiányzó fejlécnél a korábbi konzervatív számítás marad. BUSY esetén 200 ms múlva kér új állapotot, a régi bizonyíték határidejének megújítása nélkül. A fennálló lease-t nem vonja vissza az új claimet engedélyező capabilities.manual jelző: friss STM STATE, boot, epoch és lease-egyezés marad kötelező. A stale/boot/state-váltás továbbra is lezárja a kapcsolatot. 263 backend tesztből 15 kihagyott; a többi és mind a 82 frontend teszt sikeres. A frontend proxy továbbítja a Server-Timing fejlécet.
