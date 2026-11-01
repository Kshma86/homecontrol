"""HC-33 bounded, idempotent history batches, owned only by the DB worker."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import time
from uuid import uuid4

from psycopg2 import DataError, IntegrityError
from psycopg2.extras import execute_values


@dataclass
class Measurement:
    entity_id: int
    key: str
    values: tuple
    meta: dict
    value: object
    received_at: float
    apply_state: object = None
    confirm: object = None
    sample_id: str = field(default_factory=lambda: str(uuid4()))
    enqueued: float = field(default_factory=time.monotonic)
    attempts: int = 0

    def row(self):
        return (self.sample_id, datetime.fromtimestamp(self.received_at, timezone.utc),
                self.entity_id, self.key, *self.values, json.dumps(self.meta))

    @property
    def size(self):
        # JSON-size cap complements the object-count cap; not a whole-process RSS cap.
        return len(json.dumps([self.entity_id, self.key, self.values, self.meta], default=str).encode())


class MeasurementQueue:
    def __init__(self, max_messages=1000, max_bytes=8*1024*1024, max_age=30, max_attempts=3):
        if max_messages < 1 or max_bytes < 1 or max_attempts < 1 or not 0 < max_age < float('inf'):
            raise ValueError('Measurement limits must be positive and finite')
        self.max_messages, self.max_bytes = max_messages, max_bytes
        self.max_age, self.max_attempts = max_age, max_attempts
        self.items = []
        self.bytes = 0
        self.dropped = Counter()
        self.confirmed = self.duplicates = self.failures = self.high_water = 0
        self.last_data_error = ''

    def __len__(self):
        return len(self.items)

    def append(self, item):
        size = item.size
        reason = ('oversize' if size > self.max_bytes else 'overflow' if
                  len(self.items) >= self.max_messages or self.bytes+size > self.max_bytes else None)
        if reason:
            self.dropped[reason] += 1
            return False
        self.items.append(item)
        self.bytes += size
        self.high_water = max(self.high_water, len(self.items))
        return True

    def clear(self, reason='explicit_clear'):
        self.dropped[reason] += len(self.items)
        self.items.clear()
        self.bytes = 0

    def latest(self, entity_id, key):
        return next((m for m in reversed(self.items) if (m.entity_id,m.key)==(entity_id,key)), None)

    def remove(self, items):
        ids = {m.sample_id for m in items}
        self.items[:] = [m for m in self.items if m.sample_id not in ids]
        self.bytes = sum(m.size for m in self.items)

    def expire(self):
        expired = []
        for m in self.items:
            reason = ('expired' if time.monotonic()-m.enqueued > self.max_age else
                      'retry_exhausted' if m.attempts >= self.max_attempts else None)
            if reason:
                expired.append(m)
                self.dropped[reason] += 1
        self.remove(expired)

    def status(self):
        return dict(queued_messages=len(self), queued_bytes=self.bytes, max_messages=self.max_messages,
                    max_bytes=self.max_bytes, max_age_seconds=self.max_age, max_attempts=self.max_attempts,
                    confirmed=self.confirmed, duplicate_confirmations=self.duplicates,
                    failed_flushes=self.failures, last_data_error=self.last_data_error, dropped=dict(self.dropped), high_water_messages=self.high_water)

    def flush(self, cur, page_size=100):
        self.expire()
        rows = list(self.items)
        if not rows:
            return 0
        for m in rows:
            m.attempts += 1
        inserted, rejected = set(), []
        try:
            cur.execute('BEGIN')
            try:
                inserted = self._insert(cur, rows, page_size)
                for m in rows:
                    if m.sample_id in inserted and m.apply_state:
                        m.apply_state(cur)
            except (DataError, IntegrityError) as exc:
                self.last_data_error = exc.pgcode or type(exc).__name__
                # SQL-data errors only: roll back ALL earlier pages/state writes.
                # Connection errors are never converted into per-row retries.
                cur.execute('ROLLBACK')
                cur.execute('BEGIN')
                inserted = set()
                for m in rows:
                    cur.execute('SAVEPOINT hc33_row')
                    try:
                        new = self._insert(cur, [m], 1)
                        if new and m.apply_state:
                            m.apply_state(cur)
                        inserted.update(new)
                    except (DataError, IntegrityError) as exc:
                        self.last_data_error = exc.pgcode or type(exc).__name__
                        cur.execute('ROLLBACK TO SAVEPOINT hc33_row')
                        rejected.append(m)
                    cur.execute('RELEASE SAVEPOINT hc33_row')
            cur.execute('COMMIT')
        except Exception:
            self.failures += 1
            try:
                cur.execute('ROLLBACK')
            except Exception:
                pass
            # Stable IDs and the original receipt timestamp survive unknown commit.
            # No queue/cache mutation until COMMIT is positively confirmed.
            raise
        rejected_ids = {m.sample_id for m in rejected}
        good = [m for m in rows if m.sample_id not in rejected_ids]
        self.remove(rows)
        self.dropped['invalid_data'] += len(rejected)
        self.confirmed += len(good)
        self.duplicates += len(good)-len(inserted)
        for m in good:
            if m.confirm:
                m.confirm()
        return len(good)

    @staticmethod
    def _insert(cur, rows, page_size):
        result = execute_values(cur, '''insert into hc.measurement
            (ingest_sample_id,ts,entity_id,key,v_num,v_bool,v_text,v_json,meta) values %s
            on conflict (ingest_sample_id) where ingest_sample_id is not null do nothing
            returning ingest_sample_id''', [m.row() for m in rows],
            template='(%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)',
            page_size=page_size, fetch=True)
        return {str(r[0]) for r in result}
