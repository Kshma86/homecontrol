#!/usr/bin/env python3
"""Seal the prepared r18 only after every offline acceptance gate passes."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import BASE, KIT, EVIDENCE, digest


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = read(KIT/'release.json')
    require(not manifest['ready_for_root_deploy'], 'Never reseal an accepted release')
    require(read(BASE/'infra/access-release.json')['release'] == manifest['previous_release'], 'Baseline changed')
    require(digest(BASE/'infra/docker-compose.yml') == manifest['previous_compose_sha256'], 'Compose changed')
    require(digest(BASE/'homeassistant/docker-compose.yml') == manifest['previous_ha_compose_sha256'], 'HA Compose changed')
    require(digest(BASE/'homeassistant/config/configuration.yaml') == manifest['previous_ha_configuration_sha256'], 'HA config changed')
    require(digest(KIT/'private/access-images.tar.gz') == manifest['offline_image_archive_sha256'], 'Recovery archive changed')
    require(digest(KIT/'tools/rclone') == manifest['rclone_sha256'], 'Recovery transport changed')
    require(digest(BASE/'HC_REFACTOR_AUDIT.md') == '51b28cca083f7ebe1ceba65d5ded3761af0a4ad9a309764f51dc1b0b0f3f25e2', 'Original audit changed')
    image_lock = read(EVIDENCE/'candidate-image-lock.json')
    expected_images = set(manifest['images'].values()) | {manifest['homeassistant_image']}
    require(set(image_lock.values()) == expected_images, 'Candidate image inventory changed')
    for name, expected in manifest['baseline'].items():
        row = json.loads(subprocess.check_output(['docker','inspect','--format',
            '{"id":{{json .Id}},"image":{{json .Image}}}',name], text=True))
        require(row == expected, 'Production baseline changed: '+name)
    for image in expected_images:
        actual = subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
        require(actual == image, 'Candidate image missing')

    # Preserve the precise summary AND its referenced logs. No failed historical
    # attempts are substituted for these successful final profiles.
    counts = {}
    profiles = [('candidate-unit-final','unit',795),('candidate-postgres','postgres',190),
                ('candidate-ownership','ownership',2),('candidate-policy','deployed',19),
                ('candidate-bridges','bridges',54),('candidate-ingest','ingest',52),
                ('candidate-x10','x10',33),('frontend-final','frontend',114)]
    for folder, profile, minimum in profiles:
        path = EVIDENCE/folder/'test-summary.json'; report = read(path)
        require(report['ok'], 'Failed test profile: '+profile)
        result = report['profiles'][profile]
        rows = list(result['modules'].values()) if profile == 'postgres' else [result]
        count = 0
        for row in rows:
            value = row['result']
            require(row['ok'] and row['returncode'] == 0 and not any(value[k] for k in ('failures','errors','skipped')), 'Incomplete test profile')
            count += value['tests']
        require(count >= minimum, 'Test coverage unexpectedly reduced')
        counts[profile] = count
        shutil.copytree(path.parent,KIT/'evidence'/folder,dirs_exist_ok=True)

    for name, count in [('installer',16),('router-transaction',12),('ha-transaction',16),('platform-transaction',8),('ha-sqlite',2)]:
        text = (KIT/'evidence'/(name+'-tests.log')).read_text()
        require(re.search(r'Ran '+str(count)+r' tests in ',text) and text.rstrip().endswith('OK'), 'Failed transaction tests: '+name)
        counts[name] = count

    require(read(KIT/'evidence/integration.json')['ok'], 'DB/MQTT integration failed')
    transition = read(KIT/'evidence/postgres-platform-transition.json')
    require(transition['ok'] and [r['stage'] for r in transition['stages']] == ['previous','candidate','rollback'], 'PostgreSQL image transition failed')
    require(transition['stages'][1]['image'] == manifest['images']['postgres']
            and transition['stages'][2]['image'] == manifest['baseline']['homecontrol-postgres']['image'], 'Wrong PostgreSQL images tested')
    for name in ('ha-migration.json','ha-old-image-restore.json'):
        report = read(EVIDENCE/name)
        require(report['ok'] and report['rows_preserved'] and report['network'] == 'none', 'HA private-copy test failed')
    require(read(EVIDENCE/'ha-migration.json')['image'] == manifest['homeassistant_image'], 'Wrong HA candidate tested')
    http = read(EVIDENCE/'frontend-http.json')
    require(http['ok'] and http['image'] == image_lock['homecontrol-frontend'], 'Wrong frontend tested')
    npm = read(EVIDENCE/'npm-candidate-advisories.json')
    require(not npm['matches'] and not npm['unknown'], 'npm advisories unresolved')
    python = read(EVIDENCE/'python-candidate-advisories.json')
    require(all(row['components'] == ['homeassistant'] for row in python['matches']), 'New own-component Python finding')
    os_report = read(EVIDENCE/'os-candidate-advisories.json')
    require(os_report['ok'] and {r['image'] for r in os_report['images']} == expected_images, 'Incomplete OS image scan')
    require(not any(r['fixed_available'] for r in os_report['images']), 'Available OS patch not applied')
    process = read(EVIDENCE/'process-lab.json')['results']
    require(len(process) == 7 and all(r['running'] and (r.get('live_exit') == 0 and r.get('ready_exit') == 1
        if 'live_exit' in r else r['http']['/health/live'] == 200 and r['http']['/health/ready'] == 503) for r in process.values()), 'Dependency-outage behavior failed')
    require(read(EVIDENCE/'dependency-triage.json')['hc43_closed'] is False, 'Residual findings hidden')

    inputs = read(KIT/'evidence/build-inputs.json')['sha256']
    for name, sha in inputs.items():
        require(digest(KIT/'build-inputs'/name) == sha, 'Public build input changed')
    load_log = BASE/'backups/releases/hc-audit-20261102-r19/evidence/offline-load.log'
    require(load_log.is_file(), 'Missing actual offline Docker load')
    # Docker may print a tag instead of an ID. A separately verified inventory
    # records every requested image after the successful load command.
    proof = read(KIT/'evidence/offline-load.json')
    require(proof['ok'] and set(proof['verified_images']) == set(manifest['recovery_images'])
            and proof['archive_sha256'] == manifest['offline_image_archive_sha256'], 'Offline load incomplete')

    for name in ('candidate-image-lock.json','candidate-python.json','catalogs.json','os-candidates.json',
                 'python-candidate-advisories.json','npm-candidate-advisories.json','os-candidate-advisories.json',
                 'dependency-triage.json','ha-copy.json','ha-migration.json','ha-old-image-restore.json',
                 'frontend-http.json','process-lab.json','postgres-collation-before.txt'):
        shutil.copyfile(EVIDENCE/name,KIT/'evidence'/name)
    shutil.copyfile(BASE/'docs/hc23-43-platform-release-20261102.md',KIT/'evidence/release-review.md')
    source = KIT/'source'
    for path in source.rglob('*'):
        require(not path.is_symlink(), 'Unexpected source symlink')
        if path.is_file() and path.suffix == '.py':
            ast.parse(path.read_bytes(),filename=str(path))
    subprocess.run(['bash','-n',str(source/'scripts/backup_archive_worker.sh')],check=True)
    manifest['source_sha256'] = {str(p.relative_to(source)):digest(p) for p in sorted(source.rglob('*'))
                                if p.is_file() and '__pycache__' not in p.parts}
    evidence = KIT/'evidence'
    # Failed historical attempts remain beside the receipt but are explicitly
    # excluded from the acceptance evidence, rather than presented as passes.
    hashes = {str(p.relative_to(evidence)):digest(p) for p in sorted(evidence.rglob('*'))
              if p.is_file() and p.name != 'acceptance.json' and 'initial-' not in p.name}
    acceptance = {'ok':True,'state':'offline_acceptance_passed_not_deployed',
        'release':manifest['release'],'sealed_at':datetime.now(timezone.utc).isoformat(),
        'production_changed':False,'counts':counts,'hc23_closed':False,'hc43_closed':False,
        'pending_local_activation_gates':['Full protected HA auth/config copy and offline probe',
            'Fresh local backup; guarded production cutover',
            'Authenticated live HA/Growatt and PostgreSQL collation',
            'Fresh Git/router backup, archive and isolated PostgreSQL restore'],
        'residual_findings':'dependency-triage.json','evidence_sha256':hashes}
    (evidence/'acceptance.json').write_text(json.dumps(acceptance,indent=2)+'\n')
    manifest.update(acceptance_sha256=digest(evidence/'acceptance.json'),ready_for_root_deploy=True,
        status='sealed_ready_for_local_sudo_not_deployed',deployed=False)
    (KIT/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'release':manifest['release'],'ready_for_root_deploy':True,
        'source_files':len(manifest['source_sha256']),'acceptance_sha256':manifest['acceptance_sha256']}))


if __name__ == '__main__':
    main()
