"""Cancel pre-handover fan ON intents after the old backend has stopped.

Bindings, policy flags and other scheduled work are preserved. Receipts are
evidence only: neither deployment nor rollback replays their pending timestamps.
"""
import json
from pathlib import Path
import subprocess

from common import write_json

SQL = """BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5s';
SELECT pg_advisory_xact_lock(350036, 1);
SELECT json_build_object(
  'bindings', (SELECT coalesce(json_agg(row_to_json(b)), '[]')
               FROM (SELECT * FROM hc.process_sensor_binding ORDER BY process_key) b),
  'policies', (SELECT coalesce(json_agg(row_to_json(p)), '[]')
               FROM (SELECT * FROM hc.power_wall_policy ORDER BY entity_id) p));
UPDATE hc.power_wall_policy SET auto_climate_on_at = NULL
 WHERE auto_climate_on_at IS NOT NULL;
COMMIT;
"""


def reconcile(directory, reason, run=subprocess.run):
    if reason not in ('deploy','rollback','restore'):raise ValueError('Explicit handover phase required')
    stopped=run(['docker','inspect','--type','container','--format','{{.State.Running}}','homecontrol-backend'],
                capture_output=True,text=True)
    absent=stopped.returncode!=0 and 'no such' in stopped.stderr.lower()
    if not absent and (stopped.returncode!=0 or stopped.stdout.strip()!='false'):
        raise RuntimeError('Stop the backend before reconciling fan intents')
    result=run(['docker','exec','-i','homecontrol-postgres','sh','-c',
        'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "${POSTGRES_DB:-homecontrol}"'],
        input=SQL,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Fan intent handover failed; do not start the previous/new backend')
    records=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    if len(records)!=1:raise RuntimeError('Fan handover receipt missing; reconcile before proceeding')
    before=records[0]
    receipt=dict(reason=reason,committed=True,previous_state=before,
        cancelled_entity_ids=[p['entity_id'] for p in before['policies'] if p.get('auto_climate_on_at') is not None],
        old_on_intents_replayed=False,bindings_and_policy_flags_preserved=True)
    write_json(Path(directory)/(reason+'-climate-handover.json'),receipt)
    return receipt
