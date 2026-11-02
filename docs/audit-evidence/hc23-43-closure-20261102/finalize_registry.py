"""Record HC23 closure only after successful real candidate restore and reboot."""
import json,re
from pathlib import Path
BASE=Path('/srv/docker/homecontrol');OUT=Path(__file__).resolve().parent
vm=json.loads((OUT/'bounded-lab/vm-acceptance.json').read_text())
assert vm['ok'] and vm['reboot_verified'] and vm['unavailable_repository_preserves_live_state']
assert json.loads((OUT/'user-hc43-decision.json').read_text())['explicit_risk_acceptance'] is False
p=BASE/'AUDIT_REPAIR.md';s=p.read_text()
replacements={
'**Auditösszesítés:** 45 ellenőrzött, 0 nyitott, 3 folyamatban.':'**Auditösszesítés:** 46 ellenőrzött, 0 nyitott, 2 folyamatban (HC-41/43).',
'HC-12 és HC-32 javítása éles; az aktív runtime r18. HC-23/43 globális részei és\nHC-41 az ESP legacy kivétel miatt folyamatban.':'HC-12 és HC-32 javítása éles; az aktív runtime r18. HC-23 kódja ellenőrzött, az új recovery-javítás még nem éles. HC-43 a felhasználó döntése szerint gyártói javításig, HC-41 az ESP legacy kivétel miatt folyamatban.',
'**Legújabb ellenőrzött kódjavítás:** REPAIR-066, kizárólag HC-26; nem éles.\n[Módosítás és ellenőrzés](docs/hc-26-repair.md). A korábbi HC-15/16/20/24 javítások\n(REPAIR-062–065) megőrzöttek, szintén nem élesek.':'**Legújabb ellenőrzött kódjavítás:** REPAIR-067, HC-23; nem éles.\n[Friss és ismételt restore, FTP-kiesés, reboot, tesztek és kiadási függőség](docs/hc23-43-closure-20261102.md). A korábbi HC-15/16/20/24/26 javítások (REPAIR-062–066) megőrzöttek, szintén nem élesek.',
'a globális auditpontok továbbra is folyamatban. [Scope, bizonyítékok és nyitott találatok](docs/hc23-43-platform-release-20261102.md).':'a HC-43 gyártói találatok miatt továbbra is folyamatban. [Korábbi r18 scope és bizonyítékok](docs/hc23-43-platform-release-20261102.md).',
'HC-23/41/43 továbbra is folyamatban. Más feladat':'HC-41/43 továbbra is folyamatban. HC-23 ellenőrzött; az új recovery-forrás éles kiadása még szükséges. Más feladat',
'| HC-23 | P2 | Reprodukálható telepítés és alkalmazásszintű állapotellenőrzés | F10 | Folyamatban |':'| HC-23 | P2 | Reprodukálható telepítés és alkalmazásszintű állapotellenőrzés | F10 | Ellenőrzött |',
'**Aktuális összesítés:** 0 nyitott; 3 folyamatban (HC-23/41/43); 0 javítva – ellenőrzésre vár;\n45 ellenőrzött; 0 halasztott.':'**Aktuális összesítés:** 0 nyitott; 2 folyamatban (HC-41/43); 0 javítva – ellenőrzésre vár;\n46 ellenőrzött; 0 halasztott. HC-23 REPAIR-067 kódjavítása ellenőrzött, még nem éles.',
}
for old,new in replacements.items():
 assert old in s,old;s=s.replace(old,new,1)
needle='HC-23/43 részjavításai élesek;\na globális pontok/upstream találatok nyitottak.'
assert needle in s;s=s.replace(needle,'HC-23/43 korábbi részjavításai élesek;\nHC-23 új JSON Compose recovery-javítása külön ellenőrzött, még nem éles (REPAIR-067). HC-43 upstream találatai folyamatban maradnak.',1)
s=s.replace('**HC-23 módosítás:**','**HC-23 státusz: Ellenőrzött kódjavítás, nem éles.** A friss és ismételt helyreállítás, az FTP-kiesési próba és a valódi guest-reboot sikeres; 14 system-scope unit, 5 timer, 12 hozzáférési unit/drop-in, DB-dump/checksum és root IPC ellenőrzött.\n\n**HC-23 módosítás:**',1)
p.write_text(s)
rows=re.findall(r'^\| (HC-\d+) \|.*?\| ([^|]+) \|$',s,re.M)
assert len(rows)==48 and sum(v.strip()=='Ellenőrzött' for _,v in rows)==46
assert {n for n,v in rows if v.strip()=='Folyamatban'}=={'HC-41','HC-43'}
p=BASE/'DEPLOYMENT_PREP.md';s=p.read_text().replace('**HC-23/43 lezárási felülvizsgálat folyamatban (REPAIR-067).**','**HC-23 ellenőrzötten lezárva; HC-43 folyamatban (REPAIR-067).**',1)
s=s.replace('A friss r18 hostrestore-ban talált HA JSON Compose-kompatibilitási hiba külön\njavítva, 818 unit teszten ellenőrizve;','A friss r18 hostrestore-ban talált HA JSON Compose-kompatibilitási hiba külön\njavítva, 818 unit teszten és friss/ismételt restore + FTP-kiesés + reboot próbán ellenőrizve;',1);p.write_text(s)
p=BASE/'docs/hc23-43-closure-20261102.md';s=p.read_text();i=s.index('\n')+1
s=s[:i]+'\n**HC-23: Ellenőrzött kódjavítás, még nem éles. HC-43: felhasználói döntés szerint Folyamatban a gyártói javításig. HC-41 változatlan.**\n'+s[i:]
s+='''
## Végső ellenőrzési záradék

A méretkorlátos, hálózatilag leválasztott új KVM-vendég teljes átvétele sikeres.
A valós r18 snapshot és Git-export változatlan; a recovery-jelölt egyetlen
explicit JSON Compose-kompatibilitási forrásjavítással készült. Az eredeti r18
sikertelen próbája külön megmaradt; a javított jelölt nem éles kiadás.

| Ellenőrzés | Tényleges eredmény |
|---|---|
| Teljes regresszió | 1194 külön Python- és 114 frontendteszt; 1308 külön eset, 0 hiba/kihagyás; frontend build sikeres. Az egyetlen későbbi recovery-javítás után a teljes 818 unit teszt újrafutott. |
| Üres host/image-tár | Valódi r18 snapshotból teljes restore; PostgreSQL és backend DB/MQTT ellenőrzött, HA a várt offline image-en fut; a kiválasztott dump hash-e és az archívum receiptje egyezik. |
| FTP-kiesés | Nem nulla kilépés; a már visszaállított kanonikus fájlok/unitok és DB-konténer változatlanok. |
| Megismételt restore | Sikeres, ugyanaz a dump, az összes unit bájtja azonos. |
| Valódi guest-reboot | Új boot-ID; DB/MQTT/backend, a HA futó image-e, root IPC és timerek újra ellenőrizve. |
| Hostvégrehajtás | 14 system-scope mentési unit, 12 hozzáférési unit/drop-in, 5 aktív timer; nincs függő feladat-visszajátszás. Backend non-root/readonly, Docker-socket nélkül; root IPC 0660/10001. |
| Tiltások | AI továbbra is false; produkciós LAN/eszközvezérlés, MQTT-publish és router/Git távoli írás nincs. |
| Tárhelyhatárok | A bounded-lab tárhelyőre nem jelzett küszöbsértést. A befejezett labor saját lemezei és kulcsai eltávolítva; az eredeti privát recovery-bemenet megőrzött. |
| Éles utóellenőrzés | Az eredeti konténer-ID/image és mind a 736 runtime-hash változatlan; 15 komponens fut, 10 healthcheck healthy, restart0, systemd failed unit nincs. |

**Nyilvántartás:** 46 Ellenőrzött, 2 Folyamatban (HC-41/43), 0 Nyitott,
0 Halasztva. A HC-23 forrásjavítás bevezetése új, ellenőrzött recovery-/kiadási
csomagot és Git-exportot igényel; a korábbi HC-15/16/20/24/26 kódjavítások is
külön nyilvántartott, még nem éles munkák. Más auditpont státusza nem módosult.
''';p.write_text(s)
print(json.dumps({'hc23':'Ellenőrzött; not deployed','hc43':'Folyamatban; explicit user decision','checked':46,'in_progress':2}))
