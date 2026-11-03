"""Private diagnostics for failed restic/rclone calls; never expose argv or env."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid

LIMIT = 4 * 1024 * 1024
OPERATIONS = {'backup', 'check', 'snapshots', 'restore', 'init', 'forget', 'version', 'lsf', 'mkdir'}


class OperationLog:
    def __init__(self, root, run_id, run=subprocess.run):
        if not re.fullmatch(r'[0-9a-f]{32}', run_id):
            raise ValueError('Invalid diagnostic run ID')
        self.directory = Path(root) / 'router-diagnostics'
        self.run_id = run_id
        self.execute = run
        self.last_failure = None
        self.record_failed = False

    def __call__(self, args, **kwargs):
        result = self.execute(args, **kwargs)
        if result.returncode and Path(str(args[0])).name in ('restic', 'rclone'):
            operation = next((str(arg) for arg in args[1:] if str(arg) in OPERATIONS), 'other')
            self.last_failure = {'tool': Path(str(args[0])).name, 'operation': operation,
                                 'exit_code': result.returncode}
            payload = {**self.last_failure, 'run_id': self.run_id,
                       'timestamp': datetime.now(timezone.utc).isoformat()}
            for field in ('stdout', 'stderr'):
                value = getattr(result, field, '') or ''
                if isinstance(value, bytes):
                    value = value.decode(errors='replace')
                payload[field] = value[-LIMIT:]
                payload[field + '_truncated'] = len(value) > LIMIT
            try:
                self._write(payload)
            except OSError:
                self.record_failed = True
        return result

    def _write(self, payload):
        for path in (self.directory, *self.directory.parents):
            if path.is_symlink():
                raise OSError('Symlink in private diagnostic path')
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise OSError('Private diagnostic directory ownership/mode mismatch')
        fd, temporary = tempfile.mkstemp(prefix='.failure-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(payload, stream)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            target = self.directory / (self.run_id + '-' + uuid.uuid4().hex + '.json')
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
