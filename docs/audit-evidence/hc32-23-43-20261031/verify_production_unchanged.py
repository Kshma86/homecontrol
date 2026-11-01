"""Read-only comparison with the captured F10 baseline. No secret/environment reads."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/srv/docker/homecontrol')
OUT=Path(__file__).resolve().parent


def run(args):
    return subprocess.check_output(args,text=True,timeout=30)


if __name__=='__main__':
    before=json.loads((OUT/'before.json').read_text())
    items=json.loads(run(['docker','inspect',*before['containers']]))
    after={x['Name'].lstrip('/'):{'id':x['Id'],'image':x['Image'],
        'started_at':x['State']['StartedAt'],'restart_count':x['RestartCount'],
        'status':x['State']['Status']} for x in items}
    assert after==before['containers'],'production containers changed'
    release=json.loads((ROOT/'backups/releases/hc-access-20261030-r10/release.json').read_text())
    runtime=ROOT/'scripts/access_runtime/hc-access-20261030-r10'
    for name,digest in release['source_sha256'].items():
        assert hashlib.sha256((runtime/name).read_bytes()).hexdigest()==digest,name
    for path in ('HC_REFACTOR_AUDIT.md','infra/docker-compose.yml'):
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==before['source_sha256'][path],path
    containers=run(['docker','ps','-a','--format','{{.Names}}']).splitlines()
    prefixes=('hc-f10-lab-','hc-f10-queue-','hc32-23-43-20261031-',
              'hc-f10-frontend-smoke','hc-f10-frontend-diagnose')
    assert not [n for n in containers if n.startswith(prefixes)]
    networks=run(['docker','network','ls','--format','{{.Name}}']).splitlines()
    assert 'hc-f10-queue-net' not in networks and 'hc32-23-43-20261031-net' not in networks
    result={'checked_at':datetime.now(timezone.utc).isoformat(),
        'production_containers_unchanged':len(after),
        'r10_runtime_sources_unchanged':len(release['source_sha256']),
        'audit_unchanged':True,'active_compose_unchanged':True,
        'lab_containers_and_networks_removed':True,'containers':after}
    (OUT/'after.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='containers'}))
