"""Bounded, durable close-only recovery for uncertain HC irrigation sessions."""
import json
import threading
import time
from datetime import datetime


class IrrigationSessionRecovery:
    def __init__(self, service, start_grace_seconds, retry_seconds, max_attempts):
        self.service = service
        self.start_grace_seconds = start_grace_seconds
        self.retry_seconds = retry_seconds
        self.max_attempts = max_attempts
        self.initialized = False
        self.blocked = False
        self._init_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._observation_boundaries = {}

    def _interrupt_starts(self, startup):
        rows = self.service.fetch_all(
            """
            update hc.irrigation_manual_session
            set status = 'stop_failed', stopped_at = null,
                error = 'interrupted start; physical valve state requires reconciliation',
                stop_payload = coalesce(stop_payload, '{}'::jsonb) || jsonb_build_object(
                  'recovery', jsonb_build_object('origin_status', 'starting', 'state', 'pending')
                    || coalesce(stop_payload -> 'recovery', '{}'::jsonb))
            where status = 'starting' and started_by <> 'physical_manual'
              and (%s or started_at <= now() - (%s * interval '1 second')
                   or least(requested_stop_at, safety_stop_at) <= now())
            returning id
            """,
            (startup, self.start_grace_seconds),
        )
        if rows:
            self.service._cancel_open_requests()
        return rows

    def _unresolved(self):
        return self.service.fetch_all(
            """
            select *, now() as recovery_checked_at,
                   greatest(0, extract(epoch from (now() - started_at))) as recovery_age_sec
            from hc.irrigation_manual_session
            where status = 'stop_failed' and started_by <> 'physical_manual'
            order by started_at, id
            """
        )

    def initialize(self):
        if self.initialized:
            return
        with self._init_lock:
            if self.initialized:
                return
            # No new HC start may pass initialization until this DB scan succeeds.
            self._interrupt_starts(startup=True)
            self.blocked = bool(self._unresolved())
            self.initialized = True

    @staticmethod
    def _metadata(row):
        metadata = (row.get('stop_payload') or {}).get('recovery') or {}
        if not isinstance(metadata, dict):
            raise ValueError('invalid session recovery metadata')
        attempts = metadata.get('attempts', 0)
        if type(attempts) is not int or attempts < 0:
            raise ValueError('invalid session recovery attempt count')
        return metadata, attempts

    def tick(self):
        if not self._tick_lock.acquire(blocking=False):
            return
        try:
            self.initialize()
            self._interrupt_starts(startup=False)
            rows = self._unresolved()
            self.blocked = bool(rows)
            for row in rows:
                try:
                    if self._recover(row):
                        break  # At most one physical recovery attempt per pass.
                except Exception as exc:
                    # One failed DB/transport operation must not hide other rows.
                    print(f"[IRRIGATION_RECOVERY] session={row['id']} error: {exc}", flush=True)
        finally:
            self._tick_lock.release()

    def _recover(self, row):
        session_id = int(row['id'])
        metadata, attempts = self._metadata(row)
        boundary = self._observation_boundaries.setdefault(session_id, time.monotonic())
        state = self.service.live_valve_state(after_monotonic=boundary)
        if state.get('motor_closed'):
            self._finish(row, True, 'fresh CLOSED observed during recovery', {'observed_state': state})
            return
        next_at = metadata.get('next_attempt_at')
        if next_at:
            next_at = datetime.fromisoformat(next_at.replace('Z', '+00:00'))
            if next_at > row['recovery_checked_at']:
                return
        if attempts >= self.max_attempts:
            return  # Still unresolved/visible; a later fresh CLOSED may settle it.
        self.service._cancel_open_requests()
        claimed = self.service.execute_one(
            """
            update hc.irrigation_manual_session
            set stopped_at = null,
                error = 'recovery close attempt pending; physical result unknown',
                stop_payload = coalesce(stop_payload, '{}'::jsonb) || jsonb_build_object(
                  'recovery', coalesce(stop_payload -> 'recovery', '{}'::jsonb) ||
                    jsonb_build_object('attempts', %s::int, 'state', 'attempting',
                      'last_attempt_at', now(),
                      'next_attempt_at', now() + (%s * interval '1 second')))
            where id = %s and status = 'stop_failed' and started_by <> 'physical_manual'
              and coalesce(stop_payload -> 'recovery', '{}'::jsonb) = %s::jsonb
              and coalesce((stop_payload #>> '{recovery,next_attempt_at}')::timestamptz, '-infinity') <= now()
            returning *
            """,
            (attempts + 1, self.retry_seconds, session_id, json.dumps(metadata)),
        )
        if not claimed:
            return
        # The claim commits before MQTT. A crash spends this slot, never resets it.
        self._observation_boundaries[session_id] = time.monotonic()
        try:
            ok, message, details = self.service.publish_stop_with_confirmation('session_recovery', attempt_limit=1)
        except Exception as exc:
            ok, message, details = False, f'recovery publish/confirmation failed: {exc}', {}
        self._finish(claimed, ok, message, details)
        return True

    def _finish(self, row, ok, message, details):
        metadata, _ = self._metadata(row)
        status = ('start_failed' if metadata.get('origin_status') == 'starting' else 'auto_stopped') if ok else 'stop_failed'
        payload = {
            'confirmation': {'ok': ok, 'message': message, **details},
            'recovery': {**metadata, 'state': 'confirmed' if ok else 'pending', 'message': message},
        }
        result = self.service.execute_one(
            """
            update hc.irrigation_manual_session
            set status = %s, stopped_at = case when %s then now() else null end,
                stop_payload = coalesce(stop_payload, '{}'::jsonb) || %s::jsonb,
                error = %s
            where id = %s and status = 'stop_failed' and started_by <> 'physical_manual'
              and coalesce(stop_payload -> 'recovery', '{}'::jsonb) = %s::jsonb
            returning *
            """,
            (status, ok, json.dumps(payload),
             ('interrupted start; closed during recovery' if status == 'start_failed' else None) if ok else message,
             row['id'], json.dumps(metadata)),
        )
        if result:
            self.service.invalidate_snapshot()
            self.service.invalidate_context('irrigation')

    def payload(self):
        rows = self.service.fetch_all(
            """
            select *, greatest(0, extract(epoch from (now() - started_at))) as recovery_age_sec
            from hc.irrigation_manual_session
            where status in ('starting', 'stop_failed') and started_by <> 'physical_manual'
            order by started_at, id
            """
        )
        items = []
        for row in rows:
            try:
                metadata, attempts = self._metadata(row)
                exhausted = attempts >= self.max_attempts
            except (ValueError, TypeError, AttributeError):
                metadata, attempts, exhausted = {}, None, True
            items.append({
                'id': row['id'], 'status': row['status'], 'age_sec': row.get('recovery_age_sec'),
                'attempts': attempts, 'max_attempts': self.max_attempts,
                'next_attempt_at': metadata.get('next_attempt_at'),
                'requires_attention': exhausted, 'error': row.get('error'),
            })
        return {'initialized': self.initialized, 'unresolved': items, 'blocked': bool(items)}
