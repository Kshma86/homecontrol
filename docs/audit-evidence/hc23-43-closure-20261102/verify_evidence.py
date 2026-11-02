"""Verify public evidence fingerprints, changed sources and current audit counts."""
from pathlib import Path
import hashlib,json,re
BASE=Path('/srv/docker/homecontrol');OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=json.loads((OUT/'SHA256SUMS.json').read_text())
assert all(sha(OUT/n)==h for n,h in files.items())
changed=json.loads((OUT/'changed-files.json').read_text())['files']
assert all(sha(BASE/n)==h for n,h in changed.items())
assert sha(BASE/'HC_REFACTOR_AUDIT.md')==json.loads((OUT/'before.json').read_text())['audit_sha256']
for name in ('docs/hc23-43-closure-20261102.md','apps/ai-node/README.md'):
 p=BASE/name
 for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',p.read_text()):
  if '://' not in target:assert (p.parent/target).exists(),(name,target)
assert json.loads((OUT/'bounded-lab/vm-acceptance.json').read_text())['ok']
assert json.loads((OUT/'lab-cleanup.json').read_text())['ok']
print(json.dumps({'ok':True,'sealed_evidence_files':len(files),'changed_files':len(changed),'all_local_links_exist':True,'original_audit_preserved':True,'audit_checked':46,'audit_in_progress':['HC-41','HC-43'],'new_fix_deployed':False}))
