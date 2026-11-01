# HC rovervezérlés – 2026-10-13

A HC egyetlen kezelője superuser. Külön rover-kezelői bejelentkezés nincs; a natív rover tokenje továbbra is szerveroldali.

Egyetlen konfiguráció: `infra/private/rover-config.json`. Az érvényes szerkesztés automatikusan mentődik. Nincs külön HC draft, aktív konfiguráció kiválasztás, Apply-előzmény, 128-as korlát vagy beragadt Apply zárolás. Az Alkalmazás egyetlen natív POST; elveszett válasz esetén nincs automatikus újraküldés, de új kezelői kérés indítható. A régi állományok és adatbázis-bejegyzések történeti adatként maradnak, nem vesznek részt az engedélyezésben.

A régi UNKNOWN parancsok nem állnak helyre böngésző-tárolóból és nem zárolnak. Korábbi HC firmware munkamenet nem akadályoz normál vezérlést. Firmware fájlnév, HC aktív-konfiguráció jelző vagy régi konfigurációs állapot nem feltétele a kézi vezérlésnek. A natív rover fogadja el vagy utasítja el a parancsot saját valós állapota alapján.

WebSocket: legfeljebb 1024 bájtos, 100 ms-nál rövidebb torlódás átmeneti; helyreállás után a legfrissebb célérték megy ki. Tartós kapcsolatvesztés, deadman felengedés, böngésző elhagyása, tényleges motorhatárok és natív hibák továbbra is érvényesek.

A térkép/projekt editor előkészítésre, importra, exportra és szimulációra elérhető. Nem küld régi protokollú mozgási parancsokat. A telepített MOTOR_TEST firmware `autonomous_enabled=false`; autonóm végrehajtáshoz megfelelő rover firmware és annak natív küldetésfeltöltési integrációja szükséges. Ez a változás nem valósít meg autonóm fűnyírást.

Ez a dokumentum a korábbi blokk-audit és motor-test kezelői leírás HC-zárolásokra vonatkozó részeit felülírja.
