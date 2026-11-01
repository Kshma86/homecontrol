# HC-34 — Forráshoz kötött árammetrikák

2026-10-28. **Élesítve az r9 ingesttel, 22:13:26 CET.**
[Éles ellenőrzés és visszaállítás](../backups/deployments/hc-ingest-20261028-r9/DEPLOYMENT.md).
Elolvasva az eredeti HC-34 bizonyíték és az audit F10 lépése, benne a Tuya state,
per-metric, öntözési áram és solar-ág ellenőrzési követelménye.

A `map_key()` pumpa-/szelep-/vezérlő-aliasai kizárólag a
`homecontrol/tele/irrigation/<controller>/pump_metrics` és `/solar` topicokon
futnak. A solar-átnevezés is ehhez a családhoz kötött. Tuya `current_a` így
`current_a` marad, az öntözési `current_a` továbbra is `pump_current_a`.
A már normalizált `valve_current_a` és solar-metrikák megmaradnak. Az általános
energia-, kapcsoló- és feszültségmapping nem változott.

A kiadási labor a helyiségnév nélküli Tuya `/m/current_a` út hibáját is feltárta:
a parser legalább 7 szegmenst várt, pedig a producer opcionális helyiségnévvel
hat szegmensből is érvényes topicot küld. Az élesben hat ilyen rövid eszköztopic
van. A parser mindkét formát elfogadja, üres eszköz-/helyszegmens nélkül.
Ez a HC-34 előírt per-metric fogadásának része; a bridge-eket nem módosítottuk.

Ellenőrzés: régi AST-mapping reprodukció, négy célzott forrásteszt state és
per-metric rövid/hosszú formával, öntözési pumpa-/szelepáram, solar-ág,
normalizált metrikák és változatlan általános mapping. A kész r9 image teljes
52 ingest unit-/regressziós, 15 valódi MQTT/PostgreSQL és 14 átadási tesztje
sikeres. A 6,84 milliós, owner/ACL-es másolaton tényleges új→régi→új ingest,
transaction-mode PgBouncer és meglévő Tuya-szabályok mellett a state és rövid
per-metric áramadat ténylegesen eljutott state-be/historyba. Éles olvasó
ellenőrzés: 6 aktív Tuya current-szabály, 5 helyes numerikus metrikadefiníció,
négy megfelelő öntözési/solar-szabály; konfigurációírás nem történt.

A HC-11/33 ugyanebbe a külön ingest-kiadásba kerül. A HC-23-ból a kiadáshoz
szükséges image-/verziórögzítés és mellékhatásmentes ingest liveness/readiness
készült el; a globális HC-23 nyitott. A HC-43 frissítést nem vontuk be: a futó
paho-mqtt 2.1.0 és psycopg2-binary 2.9.13 verzió maradt, hálózat nélküli builddel.
Más auditpont státusza nem változik. A korábbi mérésekre nincs átnevezés/backfill.

Az r9 csomag külön, az átadáskor alkalmazott 062-es migrációt, friss helyi mentést,
pontos image-azonosítókat, offline image-tartalékot és ellenőrzött ingest-only
rollbacket tartalmaz. Az r8 backend/frontend megmaradt; csak az r4 ingestet cseréltük.

[Előkészített kiadás és parancsok](../backups/releases/hc-ingest-20261028-r9/DEPLOYMENT.md),
[javítási bizonyítékok](audit-evidence/hc34-20261028/summary.json).
