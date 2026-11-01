#!/usr/bin/env python3
"""Filesystem verification and optional isolated DB proof; pin the restic ID."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import sys
import tarfile
from restore_archive import latest_archive, prepare_database, snapshot
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'infra/backend'))
from backup_protocol import atomic_json, verify_archive
from backup_restore import archive_index


def database_probe(dump, run=subprocess.run):
    # postgres:16 supplies a fresh anonymous PGDATA volume; --rm removes it.
    # Full data/index restore must not compete with a tiny RAM-only filesystem.
    command = '''set -eu
cat > /tmp/selected.dump
initdb -D "$PGDATA/proof-db" -A trust >/dev/null
pg_ctl -D "$PGDATA/proof-db" -o '-h "" -k /tmp -p 55432' -w start >/dev/null
trap 'pg_ctl -D "$PGDATA/proof-db" -m immediate stop >/dev/null' EXIT
createdb -h /tmp -p 55432 restore_proof
pg_restore --exit-on-error --no-owner --no-privileges -h /tmp -p 55432 -d restore_proof /tmp/selected.dump
psql -h /tmp -p 55432 -d restore_proof -v ON_ERROR_STOP=1 -Atc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='hc' and c.relkind='r'"'''
    with Path(dump).open('rb') as source:
        run(['docker','run','--rm','--network','none','--read-only','--user','postgres',
             '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','3g',
             '--tmpfs','/tmp:rw,size=256m','-i','postgres:16','bash','-c',command],stdin=source,check=True)


def verify(path):
    with tarfile.open(path,'r:gz') as archive: archive_index(archive)
    return verify_archive(path)


def smoke(base, archive=None, db_check=False, run=subprocess.run):
    base=Path(base); root=Path(os.environ.get('BACKUP_ROOT',base/'backups'))
    settings_path=root/'backup_settings.json'
    settings=json.loads(settings_path.read_text()) if settings_path.exists() else {}
    result={'ok':False,'filesystem':'not_run','database':'not_run','restic':'disabled','snapshot_id':None}
    root.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='hc-restore-smoke-') as temporary:
            work=Path(temporary)
            selected=Path(archive) if archive else latest_archive(root)
            result['local_archive']=dict(path=str(selected),**verify(selected))
            if settings.get('git_enabled',True):
                host=settings.get('ai_backup_host','192.168.1.2');repository=settings.get('git_repository','homecontrol/config')
                key=settings.get('ai_backup_ssh_key',str(base/'infra/ssh/ai_node_key'))
                env={**os.environ,'GIT_SSH_COMMAND':'ssh -i '+shlex.quote(key)+' -o BatchMode=yes -o StrictHostKeyChecking=accept-new'}
                remote=os.environ.get('GITEA_REMOTE','ssh://git@'+host+':2222/'+repository+'.git')
                run(['git','ls-remote',remote,'HEAD','refs/heads/main'],env=env,check=True,stdout=subprocess.DEVNULL)
            if settings.get('restic_enabled',False):
                host=settings.get('ai_backup_host','192.168.1.2');user=settings.get('ai_backup_user','a')
                key=settings.get('ai_backup_ssh_key',str(base/'infra/ssh/ai_node_key'))
                env={**os.environ,'RESTIC_REPOSITORY':settings.get('restic_repository','sftp:'+user+'@'+host+':/mnt/hc-backup/restic/homecontrol'),
                     'RESTIC_PASSWORD_FILE':settings.get('restic_password_file','/etc/homecontrol/restic-password'),
                     'RESTIC_CACHE_DIR':str(work/'cache')}
                if not Path(env['RESTIC_PASSWORD_FILE']).is_file(): raise ValueError('Restic password file missing')
                args=['restic','-o','sftp.command=ssh -i '+shlex.quote(key)+' -o BatchMode=yes -o StrictHostKeyChecking=accept-new '+shlex.quote(user+'@'+host)+' -s sftp']
                rows=run(args+['snapshots','--json','--tag','homecontrol'],env=env,check=True,capture_output=True,text=True)
                pinned=snapshot(json.loads(rows.stdout));result['snapshot_id']=pinned
                restored=work/'restic';restored.mkdir()
                run(args+['restore',pinned,'--target',str(restored),'--include','/srv/docker/homecontrol/backups/homecontrol_*.tar.gz'],env=env,check=True)
                selected=latest_archive(restored/'srv/docker/homecontrol/backups')
                result['restic_archive']=dict(path=str(selected),**verify(selected));result['restic']='sha256_verified'
            result['filesystem']='sha256_verified'
            if db_check:
                chosen=prepare_database(selected,work/'database');database_probe(chosen['dump'],run=run)
                result['database']='restore_verified_without_owner_acl';result['database_archive_sha256']=chosen['archive_sha256']
            result['ok']=True
    except Exception as exc:
        result['error']=type(exc).__name__
        raise
    finally:
        atomic_json(root/'restore-smoke-result.json',result,0o600)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',nargs='?');parser.add_argument('--db-check',action='store_true')
    args=parser.parse_args()
    print(json.dumps(smoke(os.environ.get('BASE','/srv/docker/homecontrol'),args.archive,args.db_check),indent=2))


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('Restore smoke failed; no restore success recorded. See the private result and command log.')
