#!/usr/bin/env python3
"""HC-44 installation plan/validation. This tool has no apply mode."""
import argparse,json,os,stat
from pathlib import Path

API_UID=10001
API_GID=10001
ALLOWED_WRITES={
 '/srv/docker/homecontrol/backups/ai-control',
 '/srv/docker/homecontrol/backups/homecontrol-backup.lock',
 '/srv/docker/homecontrol/backups/ai-backup.lock',
 '/srv/docker/homecontrol/infra/private'}


def validate_backend(container):
    problems=[];config=container.get('Config') or {};host=container.get('HostConfig') or {}
    if config.get('User')!='10001:10001':problems.append('backend_must_use_10001_10001')
    if not host.get('ReadonlyRootfs'):problems.append('backend_rootfs_must_be_read_only')
    if host.get('Privileged'):problems.append('privileged_backend_forbidden')
    if 'ALL' not in (host.get('CapDrop') or []):problems.append('all_backend_capabilities_must_be_dropped')
    if not any(str(v).startswith('no-new-privileges') for v in host.get('SecurityOpt') or []):problems.append('no_new_privileges_required')
    for mount in container.get('Mounts') or []:
        destination=mount['Destination'];source=mount.get('Source','')
        if source.endswith('/docker.sock') or destination in ('/var/run','/run','/','/var/run/docker.sock'):
            problems.append('raw_host_socket_or_root_mount_forbidden')
        if mount.get('RW') and mount.get('Type')!='tmpfs' and destination not in ALLOWED_WRITES:
            problems.append('unexpected_backend_write_mount:'+destination)
    return sorted(set(problems))


def plan(release_root):
    root=Path(release_root).resolve()
    return dict(finding='HC-44',applied=False,release_root=str(root),
      prerequisites=['Frozen reviewed release, verified backup and previous runtime/unit metadata',
        'Old backend stopped and both common backup locks idle',
        'All allowed operations passed isolated tests; no unverified in-place archives',
        'HC-45 restore manifest must include hostops service and F6 drop-ins before deployment'],
      service_template='scripts/systemd/hostops/homecontrol-hostops.service',
      executor_entrypoint=str(root/'scripts/hostops/server.py'),
      canonical_runner_template='scripts/hostops/canonical_backup_runner.py.in',
      units=[str(p.relative_to(root)) for p in sorted((root/'scripts/systemd/hostops').rglob('*')) if p.is_file()],
      permissions=[{'path':'backups/ai-control','uid':API_UID,'gid':API_GID,'mode':'0700','purpose':'AI state only'},
        {'path':'infra/private','uid':API_UID,'gid':API_GID,'mode':'0700','purpose':'Rover JSON data only'},
        {'path':'backups/ai-backup.lock','gid':API_GID,'mode':'0660','preserve_inode':True},
        {'path':'backups/homecontrol-backup.lock','gid':API_GID,'mode':'0660','preserve_inode':True}],
      protected=['backups archives/receipts/settings','restore_staging journals','source trees','host job journal'],
      steps=['Render service/drop-in ExecStart paths to the frozen release, not the mutable worktree',
        'Snapshot existing units and file metadata; never unlink or replace a held lock inode',
        'Create missing data directories and lock files, reject symlinks and unsafe API ownership of protected parents',
        'With old backend/F6 consumers stopped and locks idle, preserve and validate the existing AI coordination state; transfer it to ai-control and reconcile pending intents instead of starting from an empty state',
        'Atomically replace the canonical scripts/backup_runner.py with the frozen launcher; all existing CLI wrappers must use it',
        'Install hostops unit and all five F6 drop-ins together, daemon-reload, start host executor',
        'Start only the new non-root backend; check UID, mounts, RPC status and allowed/denied operations',
        'Verify AI-offline/winter policies and backups; preserve interrupted job states without automatic replay'],
      rollback=['Stop new backend and executor; reconcile any running backup/restore or uncertain job',
        'Restore exact previous backend image, units and original permission metadata',
        'Reconcile the current scoped AI state with the restored coordinator path; never restore an old shutdown intent or generation blindly',
        'Keep archive, staging and job data; do not resurrect old AI/actuator intents'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--container-inspect',type=Path)
    args=parser.parse_args()
    if args.container_inspect:
        value=json.loads(args.container_inspect.read_text());print(json.dumps(validate_backend(value),indent=2))
    else:print(json.dumps(plan(args.release_root),indent=2))


if __name__=='__main__':main()
