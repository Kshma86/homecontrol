"""Short PostgreSQL transaction shared by every HC irrigation start path."""
import json


class IrrigationSessionAdmission:
    def __init__(self, connect):
        # connect returns a fresh connection with dictionary rows. No shared
        # connection, session advisory lock or MQTT work crosses this boundary.
        self.connect = connect

    def reserve(self, *, minutes, safety_minutes, started_by, start_payload, schedule_id=None):
        if not started_by or started_by == 'physical_manual':
            raise ValueError('HC admission cannot create physical manual observations')
        result = {'session': None, 'blocked_by': None}
        with self.connect() as conn:
            with conn.cursor() as cur:
                # READ COMMITTED gives the check a new snapshot after waiting
                # for a previous writer. Transaction pooling is supported.
                cur.execute('set transaction isolation level read committed')
                cur.execute("set local lock_timeout = '2s'")
                cur.execute("set local statement_timeout = '5s'")
                # Also orders against existing ingest/stop/recovery writers,
                # without modifying their physical_manual tracking semantics.
                cur.execute('lock table hc.irrigation_manual_session in share row exclusive mode')
                cur.execute("""
                    select * from hc.irrigation_manual_session
                    where status in ('starting', 'running', 'stop_failed')
                    order by (status = 'stop_failed') desc, started_at, id
                    limit 1
                    """)
                active = cur.fetchone()
                if active:
                    result.update(blocked_by='active_session', blocking_session=active)
                else:
                    if schedule_id is not None:
                        # Recheck eligibility and consume the schedule day in
                        # the SAME transaction as admission. Preparation outside
                        # this transaction cannot authorize a stale/day-2 start.
                        cur.execute("""
                            update hc.irrigation_schedule
                            set last_started_on = current_date, updated_at = now()
                            where id = %s and is_active = true
                              and day_of_week = extract(isodow from now())::int - 1
                              and localtime >= start_time and localtime < stop_time
                              and last_started_on is distinct from current_date
                            returning id
                            """, (schedule_id,))
                        if not cur.fetchone():
                            result['blocked_by'] = 'schedule_not_due'
                    if not result['blocked_by']:
                        cur.execute("""
                            insert into hc.irrigation_manual_session
                              (requested_stop_at, safety_stop_at, status, started_by, start_payload)
                            values (now() + (%s * interval '1 minute'),
                                    now() + (%s * interval '1 minute'), 'starting', %s, %s::jsonb)
                            returning *
                            """, (minutes, safety_minutes, started_by, json.dumps(start_payload)))
                        result['session'] = cur.fetchone()
                        if not result['session']:
                            raise RuntimeError('session admission returned no reservation')
        # The connection context has committed successfully before any caller
        # may publish. A lost commit reply raises; it never authorizes OPEN.
        return result
