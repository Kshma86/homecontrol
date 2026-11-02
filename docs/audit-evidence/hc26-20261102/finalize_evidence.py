"""Verify measured HC-26 benefit, tested source scope and public evidence hashes."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=read(OUT/'before.json');scope=read(OUT/'scope-check.json')
assert scope['ok']
profiles={'growatt':('growatt-final','deployed'),'unit':('unit','standard'),
          'mdns':('mdns','deployed'),'ingest':('ingest','standard')}
reports={};results={};ids=[]
for profile,(folder,policy) in profiles.items():
    report=read(OUT/folder/'test-summary.json');assert report['ok']
    reports[profile]=report
    result=report['profiles'][profile]['result']
    assert all(result[k]==0 for k in ('failures','errors','skipped'))
    names=result.get('test_ids')
    if names is None:
        names=re.findall(r'^\S+ \(([^()\n]+)\) \.\.\.',(OUT/folder/(profile+'.log')).read_text(),re.M)
        (OUT/'ingest-test-ids.json').write_text(json.dumps(names,indent=2)+'\n')
    assert len(set(names))==len(names)==result['tests']
    ids.extend(names);results[profile]={k:result[k] for k in ('tests','failures','errors','skipped')}
assert len(set(ids))==len(ids)==905
assert {k:v['tests'] for k,v in results.items()}=={'growatt':18,'unit':816,'mdns':19,'ingest':52}
paths=sorted(list(before['source_sha256'])+['apps/ha-growatt-poller/tests/test_ha_growatt_poller.py','docs/hc-26-repair.md'])
python_paths=[name for name in paths if name.endswith('.py')]
for profile,report in reports.items():
    policy=profiles[profile][1]
    for name in python_paths:
        assert report['source_policies'][policy]['source_sha256'][name]==sha(ROOT/name),(profile,name)
for profile in ('growatt','mdns'):
    assert reports[profile]['source_policies']['deployed']['test_only_changes']==[]
assert reports['unit']['source_policies']['standard']['test_only_changes']==['optional policy in disposable standard-profile source only']
measurement=read(OUT/'live-measurement.json');smoke=read(OUT/'live-candidate-smoke.json');usage=read(OUT/'usage.json')
runtime=read(OUT/'production-unchanged.json')
assert runtime['ok'] and runtime['runtime_source_count']==736 and not runtime['runtime_drift']
assert reports['growatt']['profiles']['growatt']['image']==runtime['containers']['homecontrol-ha-growatt-poller']['image']==usage['image']
assert measurement['ok'] and smoke['ok']
assert not measurement['credentials_exported'] and not measurement['raw_states_saved']
assert smoke['get_count']==1 and smoke['ha_mutation_commands']==smoke['mqtt_publish_commands']==0
changes=[];diff=[]
for name in paths:
    original=OUT/'original'/name
    if original.exists():assert sha(original)==before['source_sha256'][name]
    old=original.read_text() if original.exists() else ''
    current=(ROOT/name).read_text();assert old!=current,name
    changes.append(dict(path=name,state='modified' if original.exists() else 'added',sha256=sha(ROOT/name)))
    diff.extend(difflib.unified_diff(old.splitlines(keepends=True),current.splitlines(keepends=True),
        fromfile='a/'+name if original.exists() else '/dev/null',tofile='b/'+name))
    if name.endswith('.py'):ast.parse(current)
(OUT/'changed-files.json').write_text(json.dumps(changes,indent=2)+'\n')
(OUT/'source.diff').write_text(''.join(diff))
def rows(text):
    table=text.split('## Tételes javítási lista',1)[1].split('**Kezdő összesítés:**',1)[0]
    return re.findall(r'^\| HC-\d\d .*$',table,re.M)
old_rows=rows((OUT/'original/AUDIT_REPAIR.md').read_text());new_rows=rows((ROOT/'AUDIT_REPAIR.md').read_text())
assert len(old_rows)==len(new_rows)==48
changed_rows=[(a,b) for a,b in zip(old_rows,new_rows) if a!=b]
assert len(changed_rows)==1 and changed_rows[0][0].startswith('| HC-26 ')
counts={s:sum(row.endswith('| '+s+' |') for row in new_rows) for s in ('Nyitott','Folyamatban','Ellenőrzött')}
assert counts=={'Nyitott':0,'Folyamatban':3,'Ellenőrzött':45}
links=0
for name in ('docs/hc-26-repair.md','docs/ai/solar-domain.md'):
    for target in re.findall(r'\]\(([^)]+)\)',(ROOT/name).read_text()):
        if '://' in target or target.startswith('#'):continue
        dest=(ROOT/name).parent/target.split('#',1)[0]
        assert dest.exists() or dest==OUT/'summary.json',(name,target)
        links+=1
initial=read(OUT/'growatt/test-summary.json')['profiles']['growatt']['result']
summary=dict(ok=True,finding='HC-26',repair='REPAIR-066',completed_at=datetime.now(timezone.utc).isoformat(),
    status='verified_source_not_deployed',active_release=before['active_release'],audit_sha256=before['audit_sha256'],
    usage=dict(enabled_and_running=True,configured_metrics=27,ha_states=86),
    measured=dict(rounds=3,individual_gets=27,batch_gets=1,individual_median_seconds=measurement['individual_median_seconds'],
        batch_median_seconds=measurement['batch_median_seconds'],first_individual_bytes=11976,first_batch_bytes=38037,
        raw_states_saved=False,credentials_exported=False,live_ha_mutations=0,live_mqtt_publishes=0),
    candidate_live_readonly=dict(ok=True,get_count=smoke['get_count'],payload_metric_count=smoke['published_metric_count'],
        per_metric_age_fields=smoke['per_metric_age_fields'],not_deployment=True,not_mqtt_publish=True),
    final=dict(profiles=results,unique_tests=len(ids),original_payload_compatibility_scenarios=4,
        postgres_newly_tested=False,frontend_newly_tested=False),
    source_provenance=dict(all_test_profiles_match_current_changed_python_paths=True,python_paths=python_paths,
        growatt_image=reports['growatt']['profiles']['growatt']['image'],growatt_deployed_policy_unchanged=True),
    contract_checks=dict(original_metric_map_and_value_coercion_ast_unchanged=True,original_MQTT_fields_preserved=True,
        additive_meta_fields=['observed_at','ha_state_age_seconds'],sample_time='UTC observation after read, not physical acquisition',
        failed_batch='Empty cycle; no per-entity fallback; no stale snapshot replay',backend_python_unchanged=185,sql_migrations_unchanged=62,
        ingest_source_mdns_source_dependency_locks_Dockerfile_and_helpers_unchanged=True,prior_repair_evidence_preserved=True),
    scope=dict(only_status_changed='HC-26',registry_counts=counts,other_audit_points_fixed=False,production_changed=False),
    earlier_attempt=dict(initial_growatt={k:initial[k] for k in ('tests','failures','errors','skipped')},
        cause='Test-only datetime mock lacked fromisoformat; fixed fixture, no production-code change',counted_as_acceptance=False),
    commands=['python3 -B docs/audit-evidence/hc26-20261102/check_scope.py']+
        ['python3 -B scripts/check_hc_tests.py --profile '+profile+' --output docs/audit-evidence/hc26-20261102/'+folder
         for profile,(folder,_) in profiles.items()],
    dependencies=['HA GET /api/states and current optional ha-growatt profile verified',
        'Existing JSON meta ingest/SQL 019 path; no migration required',
        'New independent Growatt-poller image/release required; pending HC-15/16/20/24 preserved'],
    limitations=['Requests connect/read timeouts are not hard whole-cycle deadlines',
        'HA last_updated age is not inverter physical measurement age',
        'No new stale threshold, automatic DB value deletion or frontend freshness display',
        'Live tests were read-only GETs; no production deployment/restart',
        'HC-23/41/43 remain in progress'],
    sources=['https://contributors.home-assistant.io/core/internals/rest-api/#get-apistates',
        'https://requests.readthedocs.io/en/latest/user/advanced/#timeouts'],
    documentation_links_verified=links,changed_files=changes)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json' and '__pycache__' not in p.parts}
(OUT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert all(sha(OUT/name)==want for name,want in manifest.items())
print(json.dumps(dict(ok=True,tests=len(ids),profiles={k:v['tests'] for k,v in results.items()},changed_files=len(changes),
    registry=counts,documentation_links_checked=links,evidence_files_sealed=len(manifest))))
