# Az r22 éles átadása lezárva

REPAIR-084, 2026-11-03. Aktív kiadás: **hc-audit-20261103-r22**.
Végső állapot: **deployed_and_audit_handover_complete**.

A felhasználó a helyi sudo-val futó operátori indítóval végrehajtotta az
engedélyezett átállítást. Az új teljes r18 előmentés és izolált PostgreSQL-restore,
majd az r22 átállítása, új teljes mentése és külön PostgreSQL-restore-ja sikeres.
A végső ellenőrzés megvárta a health service sikeres befejezését; ezután minden
eredeti schedule-ellenőrzés teljesült. Várakozás: 1,238 másodperc.

## Éles utóellenőrzés

A 15:48 CET-kor végzett független, natív, csak olvasó utóellenőrzés szerint:

* Mind a 805 telepített runtime-hash és az eredeti lezárt forrás egyezik.
* 16 konténerből 15 fut; az Adminer a tervezett leállított állapotban van.
* Mind a 10 healthcheck egészséges; backend health és readiness `ok: true`.
* Az átadási nyugtához képest nincs konténer-ID- vagy image-drift. A backend,
  mDNS és Growatt az új image-eket használja; a másik 13 konténer ID-ja megmaradt.
* Mind az öt timer engedélyezett, aktív, várakozó és következő időponttal rendelkezik.
  A 25 ellenőrzött unit/drop-in hashében nincs eltérés.
* A hostops és MQTT-hozzáférési guard aktív; az elfogadási mentő-supervisor inaktív.
* Az AI továbbra is tiltott; routeres mentés engedélyezett.

## Mentési és visszaállítási bizonyítékok

| Bizonyíték | r18 előmentés | r22 utómentés |
| --- | --- | --- |
| Run | `d721ad3af9624b7abe5faa161df89d58` | `7a6236e4b0a5472a8566024665ffc619` |
| Snapshot | `f4319a0d17fe1d875ccc45a141ddd830248bca743db87f8736055c2f0021ee07` | `08acafbc0721e29c85997a3f12298f81fe0b28c088fd3b494adf3f58bc2b5d45` |
| Git | pushed | pushed |
| Router-visszaolvasás | verified | verified |
| Izolált PostgreSQL-restore | verified | verified |

Az r22 heti archívuma `homecontrol_2026-11-03_15-17-41_7a6236e4b0a5472a8566024665ffc619.tar.gz`,
2 170 892 529 bájt, 10 690 ellenőrzött fájl.
SHA-256: `2161ff04db539fd0c2dfd2601eb5bd5c9aeeb8dc3511de5e7c20d5883bd77ec5`.
Minden kért lefedettség (PostgreSQL, appok, infra, Zigbee2MQTT, Home Assistant,
scripts, Docker-metaadatok) szerepel. A helyi archívum, restic, külső Git,
titkosított secrets-bundle és restic retention célállapota sikeres; exit 0.

A PG/restore elfogadás a sikeres root-folyamat nyilvános nyugtájából származik.
Az ügynök a külön root-only `restore-smoke-result.json` tartalmát nem olvasta;
új restore-t nem futtatott a már sikeres próba megismétlésére.

## Laborbemenet és az átadás határa

Az `audit_input_prepared: false` érték megmarad a végső bizonyítékban.
A korábbi, sikeresen elkészített laborbemenet létezik:
`/tmp/hc-audit-final-r22-20261103/input`, snapshotja
`e13b233aefaeb74e4be4878acb576765d1cec77a1dbac7d6f67a6ab2239fa00b`.
Ez nem a mostani mentés másolata; nem címkéztük át, és nem írtuk felül.

Az exportáló lezárt kód létező bemeneti cél esetén még a másolás előtt megáll.
A megfigyelt régi bemenet és a korai exportmegállás ezzel összhangban van;
a root-only `audit-input-error.json` pontos kivételét az ügynök nem olvasta.
Az exporter külön kezelt, nem kötelező labor-előkészítő lépés: a sikertelen
előkészítés nem váltja ki és nem minősíti sikertelennek a kötelező, előtte már
teljesült friss mentési/visszaolvasási/PG-restore kapukat.

**Új teljes r22 VM/bare-metal/reboot próbát nem állítunk.** A korábbi r18 recovery
próbák megőrzöttek, a friss r22 archívum és izolált PostgreSQL-restore átvétele sikeres.

## Auditállapot

**A jelenlegi javítási kör éles átadása lezárva: 46 Ellenőrzött, 2 Folyamatban.**
HC-41 az ESP MQTT-jelszó migrációja miatt marad nyitva. HC-43 a felhasználó
korábbi döntése szerint a támogatott gyártói javításig marad nyilvántartva.
Ezeket nem minősítjük javítottnak; az eredeti `HC_REFACTOR_AUDIT.md` változatlan.

Az eredeti root által létrehozott átadási lap és telepítési nyugták megmaradtak.
Ez a külön, olvasható lap a nyilvános nyugták és a natív utóellenőrzés alapján
készült. Az automatikus átadási szöveg REPAIR-079 jelölése a régi sablonból ered;
a tényleges lezárást és kiegészítő bizonyítékokat ez a REPAIR-084 bejegyzés rögzíti.

Bizonyítékok:

* [Végső root-átvételi nyugta](audit-evidence/r22-live-handover-20261103/post-live-check.json).
* [Független natív éles utóellenőrzés](audit-evidence/r22-live-handover-20261103/native-post-live-check.json).
* [Mentési állapot és elfogadási nyugták egyeztetése](audit-evidence/r22-live-handover-20261103/backup-restore-verification.json).
* [Lezárt deployment-állapot](audit-evidence/r22-live-handover-20261103/deployment-status.json).

Az élesítő és folytató indítók felhasználtak, nem ismétlendők. A külön laborbemenet
jövőbeli frissítése nem igényli az r22 újraélesítését.
