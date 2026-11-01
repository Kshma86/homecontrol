# Közös r10 revízió – 2026-10-31

Az aktuális eredmény a summary.json. A suite-ok átfedhetnek, nem összeadott tesztszámok.
A postgres-labor kizárólag belső, eldobható adatbázist/poolert használ. Az öt
átadási/restore-eset valódi PostgreSQL tranzakciót és Docker stopped/running
állapotot vizsgál; az alkalmazás dump/restore-ja kis klímaállapot-fixture.
Az integration_lab.py Docker CLI-je külön szigorú fixture, a mai teljes VM-
bootstrap/reboot és a teljes r9→r10→r9 cutover nem futott. A régi VM-bizonyíték
külön 2026-10-30-i scope; a mai root unitok nem változtak.

A megtartott scriptek a tényleges tesztkörnyezet felépítését dokumentálják,
abszolút workspace-/tmp-útvonalakat használnak; futtatás előtt a külön labor
neveit, függőségeit és a fagyasztott csomagot ellenőrizni kell. A privát fixture-
inputok a munka végén törlődnek, az éles környezetre tesztparancs nem irányul.
A live-binding-inventory.json kizárólag READ ONLY kompatibilitási leltár eredménye.
