# HC-06: friss elszívó- és lámpavisszajelzés

2026-10-25, `hc-combustion-feedback-20261025-r3`.

A két tünet közös oka az ingest döntési ága volt: ugyanaz a `should_write`
feltétel ritkította a mérési történetet és az aktuális állapotot. Az elszívó
változatlan fogyasztásának időbélyege ezért nem követte az élő üzeneteket.
A lámpánál a változatlan OFF válasz elmaradt a DB-ből; a `brightness/color`
szabályok intervallum/deadband nélkül az első érték után egyáltalán nem
mentettek új értéket. A lámpa OFF epizódja három próbálkozás után megállt,
és a szabályos további villanások az igazolt OFF-ra vártak.

## Adatfogadás

Az aktív folyamatkötések alapján a `combustion_extractor` `power/power_w`,
illetve a `combustion_indicator` `switch_state/brightness/color` metrikái
`live_feedback` jelölést kapnak. A folyamatkötést a meglévő, 60 másodperces
szabálycache követi. A jelölés nem kötődik hardcoded entity ID-hoz.

Minden validált, élő üzenet frissíti ezen metrikák aktuális DB-állapotát,
változatlan értéknél és a történeti minimumintervallum alatt is. A history
külön megtartja a meglévő ritkítását. A csak állapotfrissítés nem tolja előre
a history cache idejét, ezért változatlan értékből is megmaradnak a szabályos
maximumintervallum szerinti történeti minták.

Letiltott szabályból továbbra sincs mentés; history-only tárolásból nincs
aktuális állapot. Retained feedback nem írhatja felül az élő bizonyítékot.
A Zigbee `/set` és `/get`, valamint ezek property-altopicjai már a jelenlét
és az állapot feldolgozása előtt kimaradnak. Egy kérés nem eszközválasz.

A CO-/füstesemények, rádiós jelenlétük 6 órás határa, az ACK és a tartós
retesz logikája megmaradt. A folyamatos bemenetek korhatára továbbra is 300 s;
valódi adatkimaradás továbbra is ismeretlen állapotot eredményez.

## Forrásoldali jelentés

Az elszívó Zbeacon TS011F konnektora nyugalomban körülbelül ötpercenként
jelentkezett, a meglévő `rmsCurrent` konfiguráció max. 3600 s volt.
A támogatott áramjelentés maximuma 60 s lett; a minimum 5 s és a változásküszöb
50 maradt. A Zigbee2MQTT `device/reporting/configure` API-ja `status=ok`
választ adott, és a `database.db` konfigurációja is tartalmazza az új értéket.
Az `activePower` reporting konfigurációját a telepített Zbeacon-konverter
ismert inkompatibilitás miatt kihagyja; ezt nem írtuk felül.

Az érkező Zigbee2MQTT eszközállapotokból frissül a fogyasztási DB-állapot.
Az egyes fizikai attribútumok és a Zigbee2MQTT összefésült payloadjai közötti
forráskor/correláció továbbra is a meglévő HC-09 korlát; az ingest nem gyárt
új mérést heartbeatből vagy rádiós `lastSeen` mezőből.

## Éles átadás

Csak az ingest kapott új image-et az r2 fagyasztott forrásából. A munkafa
HC-39 role refaktorja nem került bele. A backend/frontend/DB/broker futva
maradt, a konfiguráció és a retesz megmaradt. A lámpának kizárólag egy `state`
GET ment; a valódi OFF válasz rendezte a korábbi kimerült epizódot, a backend
és a próbálkozáskeret újraindítása nélkül. Éles kapcsolási próba vagy ACK
nem történt. A villogási ciklusok és a küszöbátlépések valódi MQTT/PG laborban
voltak ellenőrizve.

A rögzített ingest image és a forrás SHA-256 egyezése ellenőrzött.
A kiadási napló, tesztek, üzemi megfigyelés és visszaállás:
[r3 kiadás](../backups/releases/hc-combustion-feedback-20261025-r3/DEPLOYMENT.md).
