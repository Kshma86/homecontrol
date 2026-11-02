"""Seal public evidence after real acceptance; no credentials or VM logs exported."""
from pathlib import Path
import hashlib,json,re,difflib
BASE=Path('/srv/docker/homecontrol');OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((OUT/n).read_text())
def save(n,v):(OUT/n).write_text(json.dumps(v,indent=2)+'\n')
assert read('test-aggregate.json')['ok']
assert read('production-unchanged.json')['ok']
assert read('lab-cleanup.json')['ok']
unit=read('restore-fix-tests/test-summary.json')
for name in ('scripts/access_release/restore_assets.py','infra/backend/tests/test_access_release.py'):
 assert unit['source_policies']['standard']['source_sha256'][name]==sha(BASE/name)
vm=read('bounded-lab/vm-acceptance.json');assert vm['ok'] and vm['reboot_verified']
assert read('bounded-lab/capacity-watch.json')['ok']
assert vm['fresh']['candidate_fixes_applied'] and vm['repeat']['candidate_fixes_applied']
assert read('unmodified-vm-acceptance.json')['ok'] is False
assert read('residual-risk-review.json')['hc43_closed'] is False
assert read('user-hc43-decision.json')['explicit_risk_acceptance'] is False
rows=re.findall(r'^\| (HC-\d+) \|.*?\| ([^|]+) \|$',(BASE/'AUDIT_REPAIR.md').read_text(),re.M)
assert len(rows)==48 and sum(v.strip()=='Ellenőrzött' for _,v in rows)==46
assert {n for n,v in rows if v.strip()=='Folyamatban'}=={'HC-41','HC-43'}
names=['apps/ai-node/docker-compose.yml','apps/ai-node/README.md','apps/ai-node/image-pins.json',
 'scripts/access_release/restore_assets.py','infra/backend/tests/test_access_release.py',
 'AUDIT_REPAIR.md','DEPLOYMENT_PREP.md','docs/hc23-43-platform-release-20261102.md',
 'docs/hc23-43-closure-20261102.md']
save('changed-files.json',{'files':{n:sha(BASE/n) for n in names},'deployed':False,
 'other_pending_fingerprints_preserved':True,'sealed_r18_runtime_modified':False,
 'audit_findings_changed':['HC-23','HC-43 review only; user explicitly kept it in progress'],
 'hc41_changed':False})
save('summary.json',{'ok':True,'hc23_code_verified':True,'hc23_fix_deployed':False,
 'hc43_remediated':False,'hc41_unchanged':True,'ai_enabled':False,
 'unmodified_r18_fresh_restore':'failed_before_target_apply',
 'corrected_candidate_fresh_repeat_reboot':'verified','production_deploy_or_restart':False,
 'unique_tests':read('test-aggregate.json')['total_unique_tests'],'frontend_build':True,
 'release':'hc-security-20261102-r18','required_next_step':'Publish/deploy a new sealed recovery release; keep existing pending HC15/16/20/24/26 fixes explicit. HC43 remains in progress until supported vendor patches, per explicit user decision.'})
parts=[]
for name in names[:5]:
 originals=[folder/name for folder in (OUT/'original',OUT/'originals') if (folder/name).is_file()]
 old=originals[0].read_text().splitlines(True) if originals else []
 parts.extend(difflib.unified_diff(old,(BASE/name).read_text().splitlines(True),fromfile='a/'+name if originals else '/dev/null',tofile='b/'+name))
(OUT/'source.diff').write_text(''.join(parts))
files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json' and '__pycache__' not in p.parts}
save('SHA256SUMS.json',files)
print(json.dumps({'ok':True,'evidence_files':len(files),'unique_tests':read('test-aggregate.json')['total_unique_tests']}))
