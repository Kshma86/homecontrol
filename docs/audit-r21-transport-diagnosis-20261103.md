# r21 – az előmentési hiba pontosított kiértékelése

**REPAIR-079 frissítés:** a második root összesítés konkrét FTP-vezérlőkapcsolati
írási timeoutot igazolt. A hibautat helyi valódi FTP/rclone próbában reprodukáltuk,
a javítás külön r22 csomagban lezárt, még nem éles.
[Aktuális javítás és végrehajtó indítóparancs](audit-r22-ftp-idle-20261103.md).
Az alábbi naplóösszesítő-lépés történeti, azt már lefuttatta a felhasználó.

REPAIR-078, 2026-11-03. Aktív: r18. Az audit éles átadása függő.

A felhasználó 10:28:16 CET-kor futtatta a REPAIR-077 naplóösszesítőjét.
Az eredmény egy restic `backup` hibát jelzett (`exit_code: 1`), `transport`
és `backend_write` osztállyal. Az átállítási könyvtár és az új runtime hiányát
a root ellenőrzés megerősítette. Új távoli művelet nem történt.

Két korlátot javítottunk az összesítőben:

* Az első verzió `ftp_reply_codes: ["500"]` mezője valójában csak egy számmintát
  talált. Ebből nem következik, hogy a router küldött FTP 500 választ.
  Az rclone 1.75.2 `serve restic` HTTP-rétege maga is 500 választ adhat a tároló
  írási hibájára. A válasz protokollját és konkrét okát az első összesítés nem
  határozta meg. Az előző ügynöki FTP-címkézés ezért túl erős következtetés volt.
* `stdout_truncated: true` szerepelt az eredményben. A megtartott részben nulla
  forráshiba és nulla snapshot-summary található; ez nem bizonyítja, hogy az
  eredeti teljes kimenetben sem volt ilyen. A stderr nem volt csonkolva.

Az eredeti összesítő forrása és a felhasználó által megosztott eredmény megőrzött:
`docs/audit-evidence/r21-baseline-failure-20261103/summarizer-v1.py` és
`reported-summary-v1.json`. A nyers root naplóhoz az ügynök nem fért hozzá.

## Az összesítő módosítása

A frissített összesítő elkülöníti az egyértelmű HTTP-válaszokat, az ismert
FTP-válaszszöveggel egyező kódokat és a nem azonosítható számmintákat.
Külön jelzi a TCP olvasási/írási timeoutot, kapcsolat-resetet, broken pipe-ot,
EOF-ot, parancshibát és más, előre rögzített hibatípusokat. Az ismert rclone
hibahelyeket is megkülönbözteti: feltöltés, szülőkönyvtár létrehozása,
módosítási idő, feltöltés utáni metaadatolvasás és a restic HTTP-híd műveletei.
Az ismétlődő stderr-sorokat rögzített címkékből álló csoportokba összesíti.

A kimenet nem másol nyers naplószöveget. Nem ad át IP-címet, felhasználónevet,
jelszót, privát fájlnevet vagy objektumazonosítót. A címkék naplómintákat
jeleznek, önmagukban nem teljes okbizonyítékok. A csak olvasó működés megmaradt:
nincs új folyamat, hálózati művelet, fájlírás, unlock, javítás vagy élesítés.

20 sikeres teszt, köztük 8 új eset: HTTP 500 téves FTP-címkézésének elkerülése,
ismeretlen számminta, tényleges FTP parancshiba, feltöltési kontrollkapcsolat
timeoutjának osztályozása titkok átadása nélkül, ismétlésszámlálás,
csonkolt forráshiba-leltár, objektumazonosító visszatartása és vegyes HTTP/FTP hiba.
Az eredeti root-, futásazonosító-, jogosultság- és fájltípus-guardok tesztjei is
sikeresek. Mind a 799 lezárt r21 forráshash változatlan.

## Következő helyi lépés

Az új natív `sudo -n` próba továbbra is helyi jelszót kér. A pontosított elemzést
ugyanazon, már meglévő naplón kell lefuttatni; új mentés nem szükséges:

```bash
sudo python3 /srv/docker/homecontrol/scripts/audit_release/summarize_r21_baseline_failure.py
```

Az előző aktiváló és folytató nem indítható újra. Transportbeállítást a konkrét
hiba megismerése nélkül nem változtattunk; az rclone verziója, a megőrzési szabály,
a repository és az alkalmazáskiadás változatlan. A további javítás és az állapothoz
kötött élesítési folytatás még hátravan. 46 Ellenőrzött; HC-41/43 Folyamatban.

Elsődleges referenciák a telepített verzióhoz:
[rclone 1.75.2 restic-híd, postObject hibaág](https://github.com/rclone/rclone/blob/v1.75.2/cmd/serve/restic/restic.go#L424),
[rclone 1.75.2 FTP feltöltés és metaadatkezelés](https://github.com/rclone/rclone/blob/v1.75.2/backend/ftp/ftp.go#L1298).
Az upstream forrás a lehetséges hibautakat mutatja; nem helyettesíti a konkrét
éles napló kiértékelését.
