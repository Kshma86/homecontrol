# X10 Xiaomi-felhőbelépés – későbbi HC-webes beépítés

**Felhasználói kérés, 2026-10-31:** a működő CAPTCHA/QR-belépőkódot megőrizzük,
később a HC weboldalába építjük. Most nincs webes implementáció vagy élesítés.

## Megőrzött alap

- Működő segéd: `scripts/refresh_x10_cloud_auth.py`.
- Célzott tesztek: `scripts/tests/test_refresh_x10_cloud_auth.py` (12 sikeres).
- Natív tokenkinyerő a helyi, repo és X10 image példányában SHA256-egyező.
- Lezárt, titokmentes másolat: `backups/releases/hc-x10-cloud-login-20261031-v1`;
  források, tesztek, natív extractor/LICENSE/requirements, kezelői leírás, hash-leltár.
- A felhasználó a CAPTCHA SSH-alagutas megjelenítését és a belépést működőnek
  jelezte. Az éles session mentése igazolt; cloud HTTP200, három mentett térkép
  újrarenderelve. Robot charging, nincs szükség takarításindításra az igazoláshoz.
  Az aktív takarítás közbeni élőtérkép-próba külön hátravan.

## A webes felület kívánt menete

Az X10 beállításainál jelenjen meg a Xiaomi-felhő kapcsolat állapota és az
újrabelépés lehetősége. A kezelő ugyanott választhasson jelszavas vagy QR-módot;
a CAPTCHA/QR kép a HC felületén jelenjen meg, a megoldást/2FA-kódot a kezelő adja meg.
Legyen érthető folyamatállapot, hiba, megszakítás és lejárat. Sikernél a felület
külön jelezze a felhőhitelesítés és a térképletöltés eredményét.

## Megőrzendő működés és függőségek

- Ugyanabból az egyszeri belépésből származzon a validált munkamenet;
  a device-token listázása nem része a felhasználói folyamatnak.
- Fiók/régió egyezés, külön cloud-validálás, 0600 atomikus csere és korábbi
  munkamenet megőrzése. A jelszó/2FA csak a folyamat idejére legyen memóriában;
  session/token/jelszó ne kerüljön API-válaszba vagy naplóba.
- A webes képet a jogosult admin-munkamenethez kell kötni és cache nélkül
  visszaadni. A mostani CLI loopback-képszerver nem közvetlen webes endpoint.
- A HC-44 non-root backendhez engedélyezett, név szerinti művelet vagy elkülönített
  belépési worker kell; közvetlen Docker-socket/szabad shell nem kerülhet a backendbe.
  A jelenlegi root-only authfájl célzott mentési jogosultságát is rendezni kell.
- Sikeres csere után naplózott térképletöltési próba, a live-map kliens session-
  újraolvasása és aktuális robotállapottal egyeztetett esetleges bridge-restart kell.
- Az új credentialt a helyreállítási/titokmentési láncba is be kell venni;
  ez nem maradhat a régi, lejárt session snapshotjára támaszkodó lépés.
- A munka előtt a kapcsolódó adminhitelesítési és hostműveleti auditfüggőségeket
  át kell nézni. E feljegyzés nem javít vagy zár le más auditpontot.

## Későbbi elfogadási próbák

Felhasználó által megoldott CAPTCHA/QR/2FA, hibás belépés/lejárat/megszakítás,
fiók/régió eltérés, sikertelen fájlcsere és helyreállítás, titokmentes naplók,
valamint sikeres felhőbelépés utáni mentett és élőtérkép-frissülés.
A jelenlegi 12 CLI-teszt megőrzendő alap, nem kész webes funkció bizonyítéka.
