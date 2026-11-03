"""HC-31 coordination shared by the backend and the F6 host runner.

Lock order: a backup owns ai-backup/common locks before the short state lock.
Power actions own the state lock and try both backup locks WITHOUT waiting.
This allows backup-held callbacks to enqueue, without a circular lock wait.
"""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import uuid

from backup_protocol import atomic_json, lock_state, now


class AiPowerCoordinator:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'ai-power-state.json'

    def read(self):
        try:
            with self.path.open() as stream:
                raw = stream.read(65537)
                if len(raw) > 65536:
                    raise ValueError('AI power coordination state too large')
                data = json.loads(raw)
        except FileNotFoundError:
            return {'version': 1, 'generation': None, 'intent': None}
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Invalid AI power coordination state')
        return data

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / 'ai-power-coordination.lock').open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield self.read()

    def save(self, state):
        atomic_json(self.path, state)

    def invalidate(self, state, reason, *, backup_run_id=None):
        backup = state.get('backup') or {}
        own_wake = (backup_run_id and backup.get('active') is True
                    and backup.get('run_id') == backup_run_id
                    and backup.get('generation') == state.get('generation'))
        state.update(generation=uuid.uuid4().hex, intent=None,
                     last_cancel={'reason': reason, 'at': now()})
        if own_wake:
            backup['generation'] = state['generation']
        self.save(state)

    def accepts_completion(self, state, run_id):
        backup = state.get('backup') or {}
        return bool(run_id and backup.get('run_id') == run_id
                    and backup.get('generation') == state.get('generation'))

    def begin_backup(self, run_id):
        with self.locked() as state:
            self.invalidate(state, 'new backup/check')
            state['backup'] = {'run_id': run_id, 'generation': state['generation'], 'active': True}
            self.save(state)

    def finish_backup(self, run_id):
        with self.locked() as state:
            if (state.get('backup') or {}).get('run_id') == run_id:
                state['backup']['active'] = False
                self.save(state)

    def guard(self):
        locks = {name: lock_state(self.root / name)
                 for name in ('ai-backup.lock', 'homecontrol-backup.lock')}
        running = None if None in locks.values() else any(locks.values())
        return {'backup_running': running, 'guard_known': running is not None, 'locks': locks}

    @contextmanager
    def reserve_power(self):
        """Keep both locks through SSH/publish; errors never mean idle."""
        handles = []
        try:
            for name in ('ai-backup.lock', 'homecontrol-backup.lock'):
                handle = (self.root / name).open('a')
                handles.append(handle)
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            for handle in reversed(handles):
                handle.close()
