"""Keep SQL handover available across a PostgreSQL image replacement."""
import json
import time


def restore_database_owner(core, manifest):
    # Compose attributes/volumes/credentials are invariant across this release;
    # only its image changes. Start the previous image explicitly even when the
    # candidate Compose is still installed. The backend remains stopped.
    override = core.KIT/'private/postgres-rollback-image.json'
    core.platform().write_json(override, {'services': {'postgres': {
        'image': manifest['baseline']['homecontrol-postgres']['image'],
        'pull_policy': 'never'}}})
    core.call(core.compose(core.BASE/'infra/docker-compose.yml') + ['-f',str(override),
        'up','-d','--no-deps','--no-build','--pull','never','postgres'])
    command = ['docker','exec','homecontrol-postgres','sh','-c',
        'pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" >/dev/null && '
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1"']
    for _ in range(90):
        result = core.call(command, allowed=(0,1,2,3), timeout=10)
        if result.returncode == 0 and result.stdout.strip() == b'1':
            return
        time.sleep(1)
    raise RuntimeError('Previous PostgreSQL owner is not ready; backend restart blocked')


def install_hooks(core, manifest):
    if 'postgres' not in manifest['changed_services']:
        raise ValueError('Expected reviewed full-platform scope')
    original_reconcile = core.reconcile

    def stop(context):
        core.phase('stop_applications_keep_postgres_for_handover')
        core.call(['docker','stop','--time','30','homecontrol-backend'])
        peers = [core.container(s) for s in manifest['changed_services'] if s not in ('backend','postgres')]
        if peers:
            core.call(['docker','stop','--time','30',*peers])
        core.call(['systemctl','stop','homecontrol-hostops.service'])

    def reconcile(reason):
        if reason == 'rollback':
            restore_database_owner(core, manifest)
        result = original_reconcile(reason)
        if reason == 'deploy':
            # The old backend and all peers are already stopped. Cancel its
            # pending fan ON intents before making SQL unavailable.
            core.call(['docker','stop','--time','60','homecontrol-postgres'], timeout=90)
        return result

    core.Cutover.stop = stop
    core.reconcile = reconcile
