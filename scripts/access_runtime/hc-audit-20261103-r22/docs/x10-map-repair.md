# X10 térképfrissítés — közös MIIO-zár és watchdog

2026-10-27. A felhasználó által hozott hibaanalízis alapján készült célzott
helyi javítás. **Nincs élesítve; az éles bridge nem indult újra.**
Napló: AUDIT_REPAIR.md REPAIR-030. Az eredeti audit változatlan, a HC-12/13
átfogó feladatai ettől nem kaptak lezárt státuszt.

## Talált hibák és változás

A státusz-, parancs- és élőtérkép-szál eddig egymástól függetlenül indíthatott
MIIO-kérést. A mentett térképet letöltő külön Python-folyamat saját,
időkorlát nélküli miiocli-hívást használt. A konténer futása önmagában nem
mutatta a sikeres feldolgozás elmaradását. A forrás ezeket a hibalehetőségeket
igazolta; valódi roboton csomagütközést nem idéztünk elő.

Új `x10_runtime.py` kezeli a robotkommunikációt. A bridge minden MIIO-hívása
és a térképfolyamat robotlekérdezése ugyanazon belépési ponton halad át.
A szálzár mellett közös fájlon tartott Linux `flock` működik, így a külön
folyamatok kérései sem fedik egymást. A zár minden siker-/hibaágon felszabadul;
folyamatkilépéskor a kernel is elengedi. A lockfájlt nem töröljük vagy cseréljük
újrainduláskor. A cloudletöltés és képrenderelés nem tartja a robot MIIO-zárját.

A zárra várás és a miiocli futása korlátos. Timeout, nem nulla exit vagy
miiocli-hibakimenet hibának számít; nincs automatikus parancsismétlés.
A `python-miio` verzióját nem cseréltük: a belső TypeError továbbra is hibás
művelet, de nem számít sikeres lekérdezésnek. A timeout és hibakimenet nem
exportálhatja a robot tokenjét. Hibás/hiányzó property-válaszból nem készül
sikeres lekérdezés. A watchdogot csak érvényes robotállapot és akkumulátoradat
frissíti, nem egy lefutott, de értékelhetetlen válasz.

A teljes térképfrissítő folyamat 120 s-os határa megmarad, de timeoutkor a
saját teljes folyamatcsoportját állítjuk le, a benne futó MIIO-gyermekkel együtt.
Így egy megállított export nem hagyhat futó robotlekérdezést maga után.

További közvetlen térképhiba: a kód már a letöltés **előtt** mentette az új
MD5-öt. Ha a letöltés elbukott, ugyanazt a térképet később frissítettnek
tekintette. Az MD5 most csak a sikeres export és indexbetöltés után változik;
hiba vagy hiányzó export után a következő meglévő térképellenőrzés újrapróbálja.
Ez olvasási/exportművelet, nem új takarítási parancs.

## Watchdog

Külön szál figyeli a főciklus haladását, a sikeres státuszmintát és — aktív
követés/takarítás alatt — a sikeres élőtérkép teljes feldolgozását. Az egyik
ág sikere nem fedi el a másik beragadását. Inaktív robotnál nem követelünk
folyamatos élőtérképet; követés aktiválásakor külön türelmi idő indul.
A meglévő élőtérképes hibavisszalépés és utolsó teljes vászon megőrzése megmarad.

Tartós elmaradáskor a watchdog naplózza az érintett ágat és 75-ös kóddal
kilépteti a bridge-et. Nem vár beragadt szálra és nem végez MQTT-/robot-I/O-t.
A meglévő Docker `restart: unless-stopped`, illetve systemd `Restart=always`
indítja újra. A Dockerben az éles újraindítási szabályt olvasással ellenőriztük;
valódi újraindítást vagy robotműveletet nem futtattunk.
Felügyelet nélkül, kézzel indított Python esetén a watchdog kilép, automatikus
újraindítás nincs. Tartós robot-/hálózati/cloudhiba újraindítás után is fennállhat.

| Beállítás | Alapérték | Jelentés |
|---|---|---|
| `X10_MIIO_LOCK_FILE` | `/tmp/homecontrol-x10-miio.lock` | Közös, stabil lockfájl a bridge és export között. |
| `X10_MIIO_TIMEOUT_SEC` | 20 s | Egy miiocli-hívás futáskorlátja. |
| `X10_MIIO_LOCK_TIMEOUT_SEC` | 30 s | Teljes szál-/folyamatzár-várakozás korlátja. |
| `X10_WATCHDOG_TIMEOUT_SEC` | 300 s | Elmaradó siker/haladás megengedett ideje. |
| `X10_WATCHDOG_CHECK_SEC` | 5 s | Watchdog-ellenőrzések periódusa. |

A watchdog ezért jellemzően a 300 s-os határ utáni következő, legfeljebb
5 s múlva esedékes ellenőrzéskor lép. Az operációs rendszer ütemezése ezt
késleltetheti; ez nem kemény valós idejű határ. Érvénytelen limitek indulási
hibát okoznak. A watchdog-határnak meg kell haladnia a hosszabb státuszpoll
periódusát és egy MIIO-zárvárakozás+hívás időkeretét. Szokatlanul lassú,
de még haladó eszköznél a 300 s is lejárhat; éles késések alapján hangolható.

A lock a közös fájlrendszert használó, ezen helperen át kommunikáló HC-hívásokat
sorosítja. Más alkalmazás vagy másik konténer/host saját zár nélküli robotkéréseit
nem szabályozza. A teljes parancssor/STOP-prioritás átalakítása HC-12 külön feladat.

## Ellenőrzés

**31 új célzott teszt + 52 kapcsolódó regresszió: 83 sikeres, 0 hiba/kihagyás.**
A célzott tesztek az éles X10 image rögzített Python-környezetével, a módosított
forrással futottak. Teljes bridge/map importpróba is sikeres. Az új konténerek
network-none módban, olvasásra csatolt forrással, rootjog és Docker socket
nélkül futottak, robot-/cloud-/MQTT-elérés nélkül.

Ellenőrizve a szálak és két folyamat közös zárja; a zárvárakozási határ;
valódi MIIO-próbafolyamat timeoutja és eltűnése; a megölt zártulajdonos utáni
felszabadulás; TypeError/hibás válasz; külön watchdog-határidők, inaktív követés,
naplózási hiba, valódi 75-ös folyamatkilépés; mapfolyamat és gyermeke leállítása;
MD5-hiba utáni újrapróbálás; konfigurációellenőrzés. A korábbi HC-09
bridge/frissesség/scheduler/MQTT tesztek is sikeresek.

A 9 éles konténer és 37 aktív hostfájl egyezik a korábbi HC-09 checkpointtal;
a feladat előtti és utáni X10 ID/image/start/restart adat külön is egyezik.
DB/MQTT health és AI-offline profil jó. Az eredeti audit és az éles safety-forrás
hash-e változatlan. A saját tesztkonténerek törölve, éles parancsküldés nem történt.
[Titokmentes bizonyítékok](audit-evidence/x10-map-20261027/).

## Későbbi kiadás és visszaállás

Együtt szükséges a `x10_runtime.py`, a bridge, a map helper és a `config.py`.
Új DB-migráció nincs. A munkafabeli bridge a még nem éles HC-09 változásait
is tartalmazza; a következő rögzített kiadáscsomagban ezek összehangolása kell.
A teljes MIIO-függőségfrissítés és a HC-12/13 tágabb refaktorja külön munka.

A kiadáskor külön, rögzített X10 image és az előző image megőrzése szükséges;
felügyelt, robotot nem zavaró ablakban ellenőrizendő a státusz, pozíció és
mindkét szint térképe. A későbbi bevezetéskor kell igazolni a restart és
átvétel valós működését. Visszaálláskor a megfelelő korábbi image/config
választandó, a térképfájlokat és auditadatokat nem kell törölni. A mostani
munkához nem készült új éles image vagy bevezetési csomag.
