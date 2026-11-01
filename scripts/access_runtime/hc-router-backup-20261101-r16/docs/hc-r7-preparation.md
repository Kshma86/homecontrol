# HC-08/09 + X10 — r7 kiadás előkészítése

2026-10-27. A felhasználó az élesítéshez szükséges előkészítést kérte.
**Élesítés nem történt.** Az aktív r6 változatlan, az új kiadás külön könyvtárban:
[hc-scheduler-x10-20261027-r7](../backups/releases/hc-scheduler-x10-20261027-r7/DEPLOYMENT.md).

A szoftveres csomag előkészített és laborban ellenőrzött. **A teljes élesítés
még blokkolt:** a működésre várt Nano nem ad friss STATUS/TELE állapotot, és a
125-ös fizikai kézi session egyeztetetlen. A felhasználó jelezte, hogy a vezérlőnek
működnie kellene, ezért ezt nem fogadtuk el szándékos téli áramtalanításként.

## Elkészült

- Három új, immutable ID-re rögzített image: backend, Gree, X10. Az alap a
  jelenleg éles r6/Gree/X10; csak a feladathoz tartozó modulok kerültek az overlaybe.
  A build helyi alapimage-ekkel, hálózat nélkül, minimális, titokmentes contextből futott.
- Egymáshoz illő release/rollback Compose és ellenőrzött, 0600 privát env-másolat.
  Új migráció nincs; a frontend, ingest, Tuya, DB, broker, PgBouncer és F6 nem cserélendő.
- Megőrzött kötelező AI-offline profil és byte szerint megőrzött éles safety-kód.
- Privát, friss DB-dump és szerepkörleltár; valódi izolált owner/ACL-visszatöltés,
  6 840 083 mérési sorral. Helyi F6 mentés completed/0, minden belső checksum
  ellenőrizve. Mind a hat release/rollback image külön offline tarban is elmentve.
- Alapból csak olvasó ellenőrző; `--apply` nélküli hívás nem cserél szolgáltatást.
  Az átadás megállítja a régi writereket, csak három szolgáltatást indít, majd
  health/profil/image/config/safety ACK/mérés és friss bridge-minta után aktiválja a symlinket.
- Visszaálláskor az előző három image indul, AI-offline profillal. A négy V2
  indítási flag tiltott, így a régi scheduler nem küldhet újra bizonytalan r7
  műveletet. Safety/stop megmarad; DB-restore, auditadat-törlés és replay nincs.
  Hibás vagy hiányzó backendkonténer mellett is van ellenőrzött rollback-út.

## Talált és javított integrációs hiba

A HC-09 egyszeri X10 olvasási kérése `command/scheduler` topicra ment, miközben
az X10 bridge `command/read_scheduler` parancsot fogad. A korábbi izolált
publisherteszt nem kapcsolta össze a két tényleges oldalt. A hívó és kapcsolódó
PG-tesztek javítva; a mostani valódi brokeres integráció a tényleges bridge
parancsfeldolgozóján bizonyította az egyezést. A történeti HC-09 bizonyítékot
nem írtuk át; az új diff és eredmény az r7 bizonyítékai között van.

## Ellenőrzések

**330 backend + 31 X10 + 14 átadási kaputeszt sikeres, 0 hiba/kihagyás.**
A régi 330 és 83 eredményt nem összegezzük ehhez, mert átfednek.
A release → rollback → release laborpróbában mindhárom megfelelő image
valóban elindult minden fázisban, saját hálózat nélküli PG16 mellett,
PgBouncerrel és brokerrel. A bridge-ek valódi r7/r6 kódot futtattak szintetikus
eszközmeghajtókkal. A scheduler automatikus worker a laborban ki volt kapcsolva;
a végrehajtási protokollokat explicit hívtuk. Nem történt valódi robot-/Gree-/Nano-parancs.

A próba igazolta a read → friss eltérés → egyetlen heti írás → confirmation
utat, a Gree korrelált friss állapotát, broker mellett hiányzó eszközfogyasztó
esetén az unknown/no-replay állapotot és a történeti láncpótlást küldés nélkül.
A visszaálláskor az eredeti auditbelépési pont tiltott klímaküldését is teszteltük.
A kezelői konfigurációk, safety ACK, mérési sorok és a konkrét uncertain execution
megmaradtak a három fázison át. Ez nem éles hardverpróba vagy teljes VM-restore.

## Mi hiányzik még a tényleges váltáshoz?

Az ESP-ről tárolt diagnosztika szerint `nano_online=false`,
`nano_serial_healthy=false`, a szelep UNKNOWN, a kézi szelep CONFLICT. Sok
parancsidőtúllépés és sérült parancsnyom látszott. A legutóbbi TELE forráskora
közel három nap; a primer Nano-topicok hiányoznak. A `SUPPLY_LOW` az eltett
utolsó Nano-kód, nem friss feszültségmérés. A diagnosztika saját fogadási kora
az [r7 bizonyítékban](../backups/releases/hc-scheduler-x10-20261027-r7/evidence/irrigation-readiness.json) szerepel.
Friss állapot nélkül nem állítunk bizonyított fizikai szelephelyzetet.

Helyszíni Nano-táp/UART-ellenőrzés, friss online STATUS és zárt szelepek,
valamint a 125-ös fizikai kézi session egyeztetése szükséges. A sessiont
nem zártuk le bizonyíték nélkül. Hiányzó TELE önmagában nem tilt, ha friss
STATUS bizonyítja az állapotot. A téli profil és az AI korlátozása megmarad.

A Nano rendezése után a csomag ellenőrzője ismét futtatható. A váltáshoz
30 percnél frissebb helyi mentés kell, ezért későbbi bevezetés előtt a
mellékelt `backup.py --create` parancs újra lefuttatandó. Felügyelt robot/klíma/
két szintes térképátvétel a tényleges váltás része. A HC-31 AI-próba és a
HC-45 teljes VM-restore külön nyitott, nem kaptak lezárt státuszt.

A végrehajtható parancsok, privát mentések kezelése és a rollback pontos
korlátozásai a [csomag runbookjában](../backups/releases/hc-scheduler-x10-20261027-r7/DEPLOYMENT.md) vannak.
