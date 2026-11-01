"""HC-35/36: order fan binding, policy, intent and publish across DB clients.

Always take the local lock before the transaction advisory lock. No session
lock is used: this also works with transaction-mode PgBouncer. The binding
mutation uses this cursor; power-wall operations retain the lock through the
bounded publish so a completed binding change cannot be followed by an old ON.
"""
from contextlib import contextmanager
import threading


class ClimateFanCoordinator:
    def __init__(self, connect):
        self.connect = connect
        self._lock = threading.RLock()

    @contextmanager
    def locked(self):
        with self._lock:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute('set transaction isolation level read committed')
                    cur.execute("set local lock_timeout = '2s'")
                    cur.execute("set local statement_timeout = '5s'")
                    cur.execute('select pg_advisory_xact_lock(350036, 1)')
                    yield cur
