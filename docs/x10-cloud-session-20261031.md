# X10 térképletöltés – lejárt felhőmunkamenet, 2026-10-31

**Igazolt ok:** az X10 saját konténeréből végzett, csak olvasó Xiaomi-felhőhívás
HTTP426 választ ad, JSON `message=SERVICETOKEN_EXPIRED`.
A helyi connector minden nem-200 választ `None`-ként ad vissza, ezért a bridge
csak `Failed to get file URL: None` hibát naplózott. Nem MQTT-hitelesítési hiba:
az állapot, pozíció és heartbeat frissül, a bridge a 1884-en bejelentkezett.
A robot dokkolón van (`charging`), battery100.

Az aktív `/app/x10_maps/xiaomi_cloud_auth.json` módosítása 2026-08-21 07:53:43 UTC;
a tartalék június18-i. Újabb használható session nincs a felcsatolt cache-ben.
A felhasználó megerősítette: csak a robot 32 karakteres helyi tokenjét frissítette.
A helyi MIIO-token és a Xiaomi-felhő serviceToken/ssecurity párosa külön hitelesítés.
Fiókadat/jelszó/sessiontoken nem került chatbe, dokumentációba vagy publikus bizonyítékba.

## CAPTCHA/QR megnyitása a fejlesztői PC-n

A régi program 127.0.0.1 képcíme SSH-n futtatva a HC képszerverét jelenti;
a PC böngészőjéből alagút nélkül ez a PC saját loopback-címe lenne.
A segéd most saját ideiglenes képszervert használ, kizárólag a HC 127.0.0.1:31415
címén. A legutóbbi CAPTCHA/QR-képet adja vissza, cache nélkül, a belépés végén
(siker, hiba vagy Ctrl+C) leáll. Nem indít grafikus képnézőt a HC-n.

1. A korábbi tokenkinyerő/belépés futását zárd le (szükség esetén Ctrl+C).
2. A fejlesztői PC egy külön termináljában hagyd futva:

   ```bash
   ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:31416:127.0.0.1:31415 a@192.168.1.133
   ```

3. A HC másik SSH-termináljában indítsd a lent megadott belépősegédet.
4. Amikor CAPTCHA/QR-képet kér, a PC böngészőjében nyisd meg:
   **http://127.0.0.1:31416/**. Új kép esetén frissítsd az oldalt.
   A CAPTCHA megoldását a HC termináljába írd be. QR-belépésnél a képet magad
   olvasd be a Xiaomi alkalmazással; a segéd semmit nem old meg automatikusan.

Foglalt HC31415 port esetén a segéd egyértelmű hibával megáll, nem mutat másik
folyamatból származó képet. A PC31416 port foglaltságát az SSH-alagút jelzi.
A tényleges fejlesztői PC/böngésző és felhasználói belépés még nem ellenőrzött.

## Új belépés

A HC saját interaktív SSH-termináljában:

```bash
python3 /srv/docker/homecontrol/scripts/refresh_x10_cloud_auth.py
```

**A segéd javítva a felhasználói elakadás után.** A saját
`~/Xiaomi-cloud-tokens-extractor/token_extractor.py` program eredeti `p/q`
menüjét használja, ugyanabban a helyi Python-környezetben. E program, a repo
és az aktív image tokenkinyerő-forrása SHA256 szerint egyezik.
A régi programból előbb ki kell lépni, majd a fenti segédet a HC interaktív
termináljában futtatni. A korábban működő jelszavas vagy QR-os módszer választható.
A jelszót rejtett terminálbekérésbe, az esetleges ellenőrzőkódot ugyanott kell megadni.
Nem parancssori kapcsoló, környezeti változó vagy chatüzenet kapja a jelszót.
A fióknak egyeznie kell az előző munkamenetével. A belépés után külön felhőhívás
ellenőrzi a sessiont; hiba/hiányos hitelesítés/eltérő fiók esetén nincs csere.
A validált session kizárólag stdin-en jut az X10 konténer mentési részéhez,
parancssorba/környezeti változóba/staging fájlba nem kerül. A script megállítja
az eredeti programot az eszköztokenek listázása előtt. A célkonténer a fiókot
és a régiót újból ellenőrzi. Az új fájl ideiglenes 0600 fájlból fsync + atomikus replace útján kerül a helyére,
a korábbi teljes fájl 0600 `.previous.*` példányban megmarad. A jelszót nem menti.

A segéd **nem indítja újra a bridge-et** és nem mozgatja a robotot.
Sikeres belépés után felügyelt cloud-map letöltés/render és az API élőtérképének
ellenőrzése következik. A tartósan cache-elt live-map kliens miatt a régi session
újraolvasásához szükség lehet az X10 bridge célzott restartjára; ezt előbb a robot
állapotával kell egyeztetni. A többi szolgáltatás és a lezárt r10 kit nem változik.
A friss session titokmentési/export útvonalát is ellenőrizni kell, majd helyi mentés
szükséges. A régi lejárt sessionre visszaállás önmagában nem oldja meg a térképhibát.

## Ellenőrzés és korlát

Nyolc célzott teszt sikeres: hibás/hiányos session, más fiók és más régió nem
cserél fájlt; sikeres sessionnél atomikus csere és 0600 régi/új példány;
replace-hibánál a régi fájl megmarad és a temporary eltűnik; sikertelen natív
login nem validál/ment; mindkét natív menüág az eszköztoken-listázás előtt átadja
a sessiont stdin-en. Külön a tényleges helyi tokenkinyerő p/q menüjével is
sikeres szintetikus próba futott, hálózat és hitelesítéscsere nélkül.
A nem interaktív használatot a wrapper megtagadja.
Ez a segéd ellenőrzése; új felhasználói belépés, sikeres térképletöltés és
bridge-reconnect még nem történt meg. A hiba **azonosított, nem lezárt**.


## 2026-10-31 felhasználói próba után

A felhasználó a régi `python3 token_extractor.py` futásából sikeres eszközlistát
kapott. Ez önmagában nem ment új `xiaomi_cloud_auth.json` fájlt. Az éles fájl
módosítási ideje változatlan, felhőlekérdezése továbbra is HTTP426/lejárt session.
A robot címe az aktív konfigurációban már a lista szerinti 192.168.1.158,
helyi kommunikáció működik; a bemásolt tokeneket nem tároltuk a dokumentációban.
Az első segéd kizárólag jelszavas loginra korlátozott, hibakijelzése túl általános
volt. Az elakadás pontos felhasználói hibaüzenete nem áll rendelkezésre, ezért
nem tekintjük bizonyítottnak, hogy kizárólag ez okozta az elakadást.
A módosítás most a ténylegesen működő program teljes eredeti loginválasztását
használja és a sessiont ugyanabból a belépésből veszi át, külön újrabelépés nélkül.
Éles munkamenetcsere/térképletöltési siker még nem történt.


## CAPTCHA-előnézet ellenőrzése (2026-10-31)

12 célzott teszt sikeres (a korábbi 8-at is tartalmazza). Valódi helyi HTTP-
kéréssel, szintetikus PNG/JPEG képadatokkal ellenőrzött a legutóbbi kép
kiszolgálása, Content-Type/no-store fejlécek, loopback kötés és leállítás.
A fájlútvonal nem szolgálható ki, a foglalt port egyértelmű hiba.
Az eredeti extractor valódi callback-globális névterébe való beillesztés és
hiba utáni cleanup fixture-rel ellenőrzött. Ez nem felhasználói CAPTCHA-
megoldás vagy sikeres éles felhőbelépés. Az éles bridge/credential változatlan.


## Sikeres felhasználói belépés és megőrzés (2026-10-31)

A felhasználó jelezte, hogy a CAPTCHA-alagutas megoldás működött, és kérte a kód
megőrzését a későbbi HC-webes beépítéshez. Az éles auth módosítása
2026-10-31 15:04:25 UTC (16:04:25 CET), korábbi privát példány megmaradt.
A Xiaomi-felhő hitelesített lekérdezése HTTP200/code0; három mentett térkép
újrarenderelődött, index módosítása 15:05:13 UTC (16:05:13 CET).
Nincs bridge-restart vagy takarításindítás. A korábbi live-map hiba még retained
állapotként látszik; aktív takarítás közbeni siker nem igazolt.
A kód titokmentes, checksumos példánya `backups/releases/hc-x10-cloud-login-20261031-v1`.
[A későbbi webes feladat](x10-cloud-web-integration.md) rögzítve; most webes
implementáció és további auditjavítás nem történt.
