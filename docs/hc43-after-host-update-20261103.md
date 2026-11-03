# HC-43: lezárhatóság a hostfrissítés után

REPAIR-090, 2026-11-03. **HC-43 nem zárható le; státusza Folyamatban marad.**
A hostfrissítés sikeres lezárása változatlan. Az eredeti auditot, a kiadási
készleteket, a futó konfigurációt és az image-eket nem módosítottuk.

Az eredeti audit HC-43 szakasza a futó image-ek Python/npm/OS-függőségeinek
sérülékeny verzióiról szól, és javított image-eket, új leltár/advisory-összevetést,
regressziót és restore/startup ellenőrzést ír elő. A most végrehajtott Ubuntu/Docker/
kernel hostfrissítés külön karbantartás volt. A konténeres maradványok javítását
nem helyettesíti a host csomagjainak frissítése.

## Mai, csak olvasó élő ellenőrzés

A HA, backend és PostgreSQL konténer-ID-ja és image-ID-ja megegyezik az r22
elfogadott állapotával; mindhárom fut. `docker exec` alatt kizárólag verzióleltár
futott, Python-modulok betöltése és eszközvezérlés nélkül.

| Tétel | Éles verzió | Következtetés |
| --- | --- | --- |
| Home Assistant | 2026.10.4 | A korábbi maradványvizsgálat óta változatlan; a hivatalos latest API ma is ezt a stabil kiadást adta. |
| HA Pillow / authlib / oauthlib | 12.3.0 / 1.7.2 / 3.3.1 | Változatlan a korábban rögzített leltárhoz képest. |
| HA pyasn1 / mcp / geopy | 0.6.4 / 1.28.1 / 2.3.0 | Változatlan. |
| HA paramiko / ecdsa / python-jose / setuptools | 3.5.0 / 0.19.2 / 3.5.0 / 84.0.0 | Változatlan. |
| Backend openssh-client | 1:10.0p1-7+deb13u4 | A Debian trixie mai trackerében továbbra is vulnerable a CVE-2026-60002 alatt. |
| PostgreSQL libxml2 | 2.12.7+dfsg+really2.9.14-2.1+deb13u3 | A Debian trixie mai trackerében továbbra is vulnerable a CVE-2026-6653 alatt. |

A két Debian-verzió konkrét, mai advisory-egyezése önmagában kizárja a teljes
HC-43 javítás lezárását. Mindkét tracker más Debian ágban már javított csomagot
is mutat; ez nem a jelenleg használt trixie ág javítása, és nem igazol kompatibilis
helyben frissíthetőséget. A trixie besorolás mindkettőnél no-dsa/minor.
Kihasználási próba és igazolt HC-kompromittálás nincs.

Elsődleges gyártói források, ellenőrizve 2026-11-03:

* [Home Assistant hivatalos latest kiadás](https://api.github.com/repos/home-assistant/core/releases/latest).
* [Debian CVE-2026-60002 / OpenSSH](https://security-tracker.debian.org/tracker/CVE-2026-60002).
* [Debian CVE-2026-6653 / libxml2](https://security-tracker.debian.org/tracker/CVE-2026-6653).

Ez célzott verzió- és gyártói státuszellenőrzés volt, nem új teljes OSV/OS-scan.
A korábbi 98 találati rekordot, 67 aliascsoportot és 122 nem eldöntött rekordot
nem állítjuk mai újraszámolt eredménynek. A HA-csomagok változatlansága nem
helyettesít új advisory-vizsgálatot; itt a korábbi leltár maradványainak
változatlanságát igazoltuk. Privát inventory külső szolgáltatáshoz nem került.

## Döntés és következő lezárási feltétel

A korábbi felhasználói döntés érvényes: „Maradjon folyamatban a gyártói javításig.”
Maradványkockázat-elfogadás nem történt. A szükséges következő javítási kör támogatott,
javított HA-/Debian-image-ekkel, függőségi újraellenőrzéssel és kompatibilitási/
restore-próbákkal végezhető el. Ebben a felülvizsgálatban nem telepítettünk semmit.

A nyilvántartás változatlan: **46 Ellenőrzött, HC-41 és HC-43 Folyamatban**.
