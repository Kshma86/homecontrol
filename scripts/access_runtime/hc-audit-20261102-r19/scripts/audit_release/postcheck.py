"""Read-only live acceptance and append-only audit handover after r19 succeeds."""
import hashlib,json,subprocess,urllib.request
from datetime import datetime,timezone
from pathlib import Path
BASE=Path('/srv/docker/homecontrol');NAME='hc-audit-20261102-r19';KIT=BASE/'backups/releases'/NAME

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def capture(core,m,final=False):
 marker=json.loads((BASE/'infra/access-release.json').read_text())
 if marker['release']!=NAME:raise ValueError('New release is not active')
 runtime=BASE/'scripts/access_runtime'/NAME
 drift=[n for n,h in m['source_sha256'].items() if not (runtime/n).is_file() or sha(runtime/n)!=h]
 if drift:raise ValueError('Deployed runtime differs from sealed source')
 changed={core.container(n) for n in m['changed_services']};rows={}
 for name,before in m['baseline'].items():
  r=json.loads(core.call(['docker','inspect',name]).stdout)[0]
  wanted=next((m['images'][s] for s in m['images'] if core.container(s)==name),before['image'])
  if r['Image']!=wanted:raise ValueError('Unexpected live image: '+name)
  if name not in changed and r['Id']!=before['id']:raise ValueError('Unchanged container replaced: '+name)
  if name!='homecontrol-adminer' and not r['State']['Running']:raise ValueError('Component is not running: '+name)
  health=r['State'].get('Health',{}).get('Status')
  if r['State']['Running'] and health not in (None,'healthy'):raise ValueError('Unhealthy component: '+name)
  rows[name]={'id':r['Id'],'image':r['Image'],'running':r['State']['Running'],'health':health,'restart_count':r['RestartCount']}
 policy=core.request('/api/deployment/status')
 if policy.get('ai_enabled') is not False or policy.get('router_backup_enabled') is not True:raise ValueError('AI/router policy changed')
 if final:
  installed=json.loads((BASE/'backups/f6-installed.json').read_text())
  for n,h in installed['units'].items():
   if sha(Path('/etc/systemd/system')/n)!=h:raise ValueError('Backup unit changed: '+n)
  timers={n:core.active(n) for n,on in installed['enabled'].items() if on and n.endswith('.timer')}
  if len(timers)!=5 or not all(timers.values()):raise ValueError('Scheduled backup timers are not active')
 else:timers={}
 return {'ok':True,'release':NAME,'checked_at':datetime.now(timezone.utc).isoformat(),
 'runtime_source_count':len(m['source_sha256']),'runtime_drift':drift,'containers':rows,
 'changed_services':m['changed_services'],'unchanged_container_count':len(rows)-len(changed),
 'ai_enabled':False,'router_backup_enabled':True,'active_timers':timers,'hc41':'in_progress','hc43':'in_progress_until_vendor_patch'}

def finish(core,live=None):
 m=core.load();live=capture(core,m,final=True) if live is None else live
 accepted=json.loads((KIT/'evidence/router-live-acceptance.json').read_text())
 if not accepted.get('ok') or accepted.get('release')!=NAME:raise ValueError('Missing completed Git/router restore acceptance')
 live.update(backup=accepted,audit_checked=46,audit_in_progress=['HC-41','HC-43'])
 core.platform().write_json(KIT/'evidence/post-live-check.json',live,0o644)
 summary=f'''# Audit javítási kör – éles átadás, 2026-11-02

Aktív: **{NAME}**. A HC-15/16/20/23/24/26 javításai élesek.
A backend, mDNS és Growatt-poller új image-en fut; a többi konténer megőrzött.
Mind a {live['runtime_source_count']} runtime-forráshash egyezik, az öt timer aktív,
a komponensek állapota és az AI-tiltás/routeres mentés ellenőrzött.

Friss helyi/HC/Git/router mentés és külön PostgreSQL-restore sikeres.
Run: `{accepted['run_id']}`; snapshot: `{accepted['snapshot_id']}`.
A pontos nyugták: `backups/releases/{NAME}/evidence/post-live-check.json`
és `router-live-acceptance.json`. A lezárt csomagot és korábbi bizonyítékokat nem írtuk át.

**A jelenlegi javítási kör átvétele lezárva: 46 Ellenőrzött; HC-41 és HC-43 Folyamatban.**
HC-41 az ESP MQTT-jelszó migrációja miatt, HC-43 a felhasználó döntése szerint a gyártói
javításig marad nyilvántartva. Ezeket nem minősítjük javítottnak. Az AI tiltva marad.
A korábbi ellenőrzött r18 recovery-jelölt teljes friss/ismételt/reboot próbája megmaradt;
ez nem új r19 bare-metal VM-próba. Az új kiadás friss mentésének SHA-256/PG-restore átvétele sikeres.

Rollback csak ugyanennek vagy az előző kiadásnak az aktív állapotából:

```bash
sudo python3 {KIT}/source/scripts/audit_release/activate.py rollback
```

A visszagörgetés az r18-at állítja vissza. Későbbi kiadásról a guard elutasítja.
A privát csomagtartalom nem megosztható. Újraaktiválást sikeres csomagon nem ismétlünk.
'''
 target=BASE/'docs/audit-final-20261102.md'
 if target.exists():raise ValueError('Live handover already exists; do not overwrite it')
 target.write_text(summary)
 for name in ('AUDIT_REPAIR.md','DEPLOYMENT_PREP.md'):
  p=BASE/name;text=p.read_text();head,sep,body=text.partition('\n')
  note=f'''\n**Éles átadás lezárva: {NAME}, 2026-11-02 (REPAIR-068).**
A HC-15/16/20/23/24/26 javításai most már élesek; 46 Ellenőrzött, 2 Folyamatban (HC-41/43).
Friss HC/Git/router mentés és PG-restore, runtime-hashek, health és öt timer ellenőrzött.
[Éles átadás és bizonyítékok](docs/audit-final-20261102.md).
**Az alábbi korábbi előkészítési/kiadási állapotok történetiek; az éles r19 átadás felülírja őket.**\n\n'''
  p.write_text(head+sep+note+body)
 (BASE/'backups/deployments'/NAME).mkdir(parents=True,exist_ok=True)
 (BASE/'backups/deployments'/NAME/'DEPLOYMENT.md').write_text(summary)
 print(json.dumps({'ok':True,'release':NAME,'audit_checked':46,'audit_in_progress':['HC-41','HC-43'],'state':'deployed_and_audit_handover_complete'}))
