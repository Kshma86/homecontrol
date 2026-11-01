# HC-09 — pontos küldési eredmény és friss eszköz-visszaigazolás

2026-10-27. Helyileg javítva és izolált környezetben ellenőrizve; **nincs
élesítve**. Az aktív kiadás továbbra is a korlátozott r6. Napló:
AUDIT_REPAIR.md REPAIR-029. Áttekintve az eredeti audit HC-09 bizonyítéka,
F2/F3 lépése és az F4/HC-08 tranzakciós előfeltétel.

## Működés

A közös MQTT-publisher sikerhez az `rc=SUCCESS` mellett a várakozás utáni
`is_published() == True` értéket is megköveteli. Timeout vagy kivétel esetén
bizonytalan/sikertelen transporteredményt ad; ez nem bizonyítja, hogy a parancs
nem érkezett meg. A loop és kapcsolat lezárása egymástól független. A korábbi
safety/stop próbálkozási korlátok változatlanok; nincs új generikus retry.

| Állapot | Bizonyíték |
|---|---|
| sent | A transport publikálási művelete befejeződött. |
| accepted | Az adott execution azonosítójával korrelált bridge-válasz sikeres. |
| confirmed | Friss, a mentett szándék után olvasott eszközállapot egyezik a kéréssel. |
| unknown | A kimenet bizonytalan vagy a visszaigazolás határideje lejárt; nincs automatikus újraküldés. |

Klímánál a HC-08 commitolt küldési foglalása megmarad. A parancs
`hc_execution_id` mezőt és tartós megfigyelési időhatárt kap. A Gree `state`
vagy a korrelált `command_result.state` adhat fizikai állapottal alátámasztott
visszaigazolást, minden kért mező szigorú összevetésével. Az önálló sikeres
bridge-válasz csak `accepted`. A parancseredmény végleges mentése előtt
megszakadt küldési foglalást nem játsszuk újra és nem minősítjük automatikusan.

X10-nél a heti program szinkronja külön, tartós run/event/plan/execution
láncot kap. Létrehozása atomi, a párhuzamos végrehajtókat közös tranzakciós
lock sorosítja. Először egyszeri, **csak olvasó** `command/read_scheduler` kérés
megy ki. Friss eltérés, engedélyezett domain/global flag és nem aktív takarítás
mellett egyszeri heti programírás foglalható, commit után, DB-tranzakción kívül.
Egyező friss olvasatnál nem kell programot írni. Publikálási hiba,
eredménymentési hiba, elveszett commit-válasz vagy restart nem ad új írási jogot.

Az X10 `confirmed` kizárólag a **roboton tárolt heti program egyezését**
jelenti, nem a takarítás elindulását vagy befejeződését. Idő, napmaszk,
engedélyezés, térkép, mód, szívóerő, víz és szobák mind számítanak; a nulla
érték is tényleges érték. Duplikált elvárt slot vagy váratlan aktív heti slot
kizárja az egyezést. Csak a pontosan illeszkedő, előzetesen összekötött egyedi
auditok kaphatnak közös visszaigazolást, a saját létrehozásuk utáni mintából.
Üres engedélyezett lista `skipped`, nem bizonyított siker.

Azonos kívánt program bizonytalan szinkronját későbbi tick sem írja újra.
Lezárt siker után új esedékes audit vagy újonnan megfigyelt eltérés indíthat
új olvasási ciklust; megváltozott kívánt program új szándék. Lejárt, változatlan
szándék operátori állapotegyeztetést igényel. Nincs új kézi recovery API vagy
SQL-alapú automatikus bizonytalan→pending átírás.

## Mintakor és bridge-szerződés

A bridge-ek additív `sampled_at` Unix-időt adnak a tényleges eszközlekérdezés
**kezdete előtt**. A Gree parancs utáni állapotnál ez az írás és a meglevő
2 s várakozás utáni új olvasás kezdete. A `reported_at` csak a bridge-válasz
ideje, önmagában nem frissíti a benne lévő állapotot.

Az X10 régi retained, változásra deduplikált `scheduler/entries` listája
megmarad. Új `scheduler/observation` tartalmazza a forrásidőt és a beolvasott
listát: nem retained, minden sikeres, feldolgozható fizikai olvasáskor kimegy,
azonos programnál is. Hibás/hiányzó/malformed válaszból nem készül friss
megfigyelés. Nincs új idle polling; a meglévő olvasások és az egyszeri
szinkronlekérdezés adnak mintát. A Gree meglévő pollperiódusa sem változott.

A HC a forráskort és az MQTT-fogadás óta eltelt monoton időt együtt vizsgálja,
a faliórával számolt korhatárt is megkövetelve. Tiltott a retained, korábbi
kapcsolatból maradt, offline, hiányos, jövőbeli, nem véges vagy a szándék előtti
minta. Folyamaton belül monoton időhatárt is ellenőriz; restart után új
monitorazonosító, aktuális kapcsolat és a tartós faliórás forrásidő szükséges.
Az újrapublikált régi forrásminta nem válik frissé. A bridge-ek ugyanazon HC
host óráját használják; hibás időrend esetén a döntés elutasító.

Kezdeti, konfigurálható limitek a backendben:

- `HC_SCHEDULER_FEEDBACK_MAX_AGE_SECONDS=90`: eszközmegfigyelés maximális kora.
- `HC_SCHEDULER_CONFIRMATION_TIMEOUT_SECONDS=120`: külön visszaigazolási határidő.

Ezek pozitív, véges értékek lehetnek. A klíma/X10 limitek nem módosítják a
Nano STATUS/TELE 70/25 s-os korhatárait vagy az 5/30 s parancs-várakozásokat.
Éles késésmérés és felügyelt eszközpróba szükséges a véglegesítésükhöz.

## Ellenőrzés és korlátok

**330 kapcsolódó teszt: 0 hiba, 0 kihagyás.** Ebből 48 új HC-09 teszt:
23 valódi PostgreSQL-tranzakciós eset, 6 bridge-függvénypróba és 19
transport/frissességi eset. A PG-próbák hc_app szerepkörrel, két független
kapcsolattal, minden lánc-insert megszakításával, commit-válaszvesztéssel,
MQTT közbeni crash-sel, eredménymentési hibával és restarttal futottak.
A régi HC-01–08 safety/stop/recovery, ablakvezérlés és AI-offline tesztek is
részei a csomagnak. A tényleges Paho 2.1.0 izolált próbája megerősítette:
wait-timeout után `rc=0`, miközben `is_published=False`.

A futtatás rögzített r6 Python-függőségekkel, a módosított forrás olvasásra
csatolásával történt. A tesztkonténerek saját network-none PG16 hálózati
névteret használtak; nem kaptak LAN-t, hostportot vagy Docker socketet. A
bridge-próbák csak a kijelölt AST-függvényeket futtatták hamis eszközökkel,
konfiguráció-/titokbetöltés nélkül. A saját konténerek és tmpfs DB törölve.

A 9 éles konténer ID/image/start/restart adata és a 37 aktív hostfájl hash-e
változatlan. DB/MQTT health sikeres; az AI-offline profil és az éles
nyitásérzékelős safety-kód megmaradt. Az eredeti audit változatlan. Éles
eszközparancs, adatpótlás és migráció nem történt. A 330 teszt nem helyettesíti
a felügyelt klíma-/robotpróbát vagy a külön hiányzó teljes VM-restore próbát.

[Titokmentes bizonyítékok](audit-evidence/hc09-20261027/): teszteredmény,
Paho-reprodukció, forrásdiff/-hash, éles változatlanság, labor törlése.

## Függőségek és későbbi kiadás

- **HC-08:** helyi előfeltétel; az új feedback-modulokkal és app-bekötéssel együtt kell kiadni. Új migráció nincs; a r6 alapsémája elegendő.
- **Gree és X10 bridge:** az új forrásidő, olvasati topic és korreláció miatt összehangolt backend/bridge kiadás kell. A régi bridge adata nem ad új confirmationt; X10-nél hiányzó új olvasat esetén programírás sem indul.
- **HC-12/13:** parancs-worker/határidő külön nyitott munka; nem változott. A késő eredmény `unknown` lehet, vak retry nélkül.
- **HC-35/36:** ventilátor/binding külön munka; a klíma állapotának visszaigazolása nem bizonyít ventilátorműködést.
- A HC-08-ban rögzített régi `physical_manual` session 125 operátori egyeztetése és a fizikai átvétel továbbra is kiadási feladat. Nem módosítottuk.
- Az AI SSD-hibás rendszer és a HC-45 VM-próba nem része ennek a javításnak; a korlátozott profil megmarad.

Rollbackhez a backend és a két bridge rögzített, egymáshoz illesztett image-e
kell. Előbb a függő fizikai szándékokat egyeztetni kell; az auditadatokat és
az új státuszokat meg kell őrizni. A történeti confirmed sorokat nem írtuk át.
A forrás Compose két új env-bejegyzése nem érinti az aktív, fagyasztott r6-ot;
most nincs új kiadási csomag vagy élesítési engedélykérés.
