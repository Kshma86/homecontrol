"""HC-08: atomic audit preparation and separately claimed climate dispatch.

The database never spans device I/O. An unknown dispatch is deliberately not
replayed: a committed claim may have reached a device even if its reply was lost.
"""
from contextlib import contextmanager
from copy import copy
from scheduler_feedback import fence, climate_observation


PROTOCOL = 'hc08-v1'


class AuditQueries:
    def __init__(self, connection):
        self.connection = connection

    def fetch_one(self, query, params=()):
        return self.connection.execute(query, params).fetchone()

    def fetch_all(self, query, params=()):
        return self.connection.execute(query, params).fetchall()

    execute_one = fetch_one


@contextmanager
def scheduler_audit_transaction(connect):
    with connect() as connection:
        with connection.transaction():
            connection.execute('set transaction isolation level read committed')
            connection.execute("set local lock_timeout='5s'")
            connection.execute("set local statement_timeout='10s'")
            yield AuditQueries(connection)


class SchedulerAudit:
    def __init__(self, scheduler):
        self.scheduler = scheduler

    def transaction(self):
        if self.scheduler.audit_transaction is None:
            raise RuntimeError('HC-08 requires an explicit scheduler transaction adapter')
        return self.scheduler.audit_transaction()

    def scoped(self, queries):
        # Do not replace callbacks on the shared service while other threads read it.
        service = copy(self.scheduler)
        service.fetch_one = queries.fetch_one
        service.fetch_all = queries.fetch_all
        service.execute_one = queries.execute_one
        service.ensure_schema_callback = lambda: None
        return service

    @staticmethod
    def unique(queries, table, column, value):
        # Identifiers come only from the fixed call sites below.
        rows = queries.fetch_all('select * from hc.' + table + ' where ' + column + '=%s', (value,))
        if len(rows) > 1:
            raise RuntimeError('Duplicate scheduler audit links require explicit reconciliation')
        return rows[0] if rows else None

    def prepare(self, event):
        self.scheduler.ensure_schema_callback()
        domain, action, key = event['domain'], event['action'], event['key']
        allowed = {'irrigation': ('water_start', 'water_stop'), 'xiaomi_x10': ('clean_start',), 'climate': ('climate_set',)}
        if action not in allowed.get(domain, ()) or not key.startswith('shadow:'):
            raise ValueError('Unsupported scheduler audit event')
        climate_snapshot = {}
        if domain == 'climate' and self.scheduler.climate_state_payload:
            existing_plan = self.scheduler.fetch_one("""select p.id from hc.plan p
                join hc.event e on e.id=p.event_id where e.idempotency_key=%s limit 1""", ('v2:' + key,))
            if not existing_plan:
                # The UI snapshot can read other repositories. Capture it before
                # reserving audit rows, never hold the transaction across it.
                climate_snapshot = self.scheduler.climate_state_payload()
        with self.transaction() as queries:
            # Serialize writers even before a scheduler_run row exists. All four
            # inserts and legacy gap repair share this transaction/connection.
            queries.fetch_one('select pg_advisory_xact_lock(hashtextextended(%s, 8008))', (key,))
            service = self.scoped(queries)
            service.climate_state_payload = lambda: climate_snapshot
            run = self.unique(queries, 'scheduler_run', 'idempotency_key', key)
            created = run is None
            if created:
                payload = {**event['payload'], '_audit_protocol': PROTOCOL}
                run = service.insert_run_once(key, domain, action, event['status'], payload=payload)
            if not run or run['domain'] != domain or run['action'] != action:
                raise RuntimeError('Scheduler audit run identity mismatch')
            payload = dict(run['payload'])
            payload['scheduler_run_id'] = run['id']
            if payload.get('_audit_protocol') != PROTOCOL:
                # A legacy missing execution may have published before crashing.
                # Complete its diagnostic chain, never manufacture a replay right.
                payload['_audit_legacy_recovery'] = True
            event_row = self.unique(queries, 'event', 'idempotency_key', 'v2:' + key)
            if not event_row:
                event_row = service.insert_v2_event_once('v2:' + key, domain, action, run['status'], payload)
            if (not event_row or event_row['domain'] != domain
                    or str(event_row['payload'].get('scheduler_run_id')) != str(run['id'])):
                raise RuntimeError('Scheduler event link is missing or inconsistent')
            plan = self.unique(queries, 'plan', 'event_id', event_row['id'])
            if not plan:
                builder = {'irrigation': service.insert_v2_irrigation_plan_once,
                           'xiaomi_x10': service.insert_v2_x10_plan_once,
                           'climate': service.insert_v2_climate_plan_once}[domain]
                plan = builder(event_row, action, payload)
            if not plan or plan['domain'] != domain:
                raise RuntimeError('Scheduler plan is missing or inconsistent')
            execution = self.unique(queries, 'execution', 'plan_id', plan['id'])
            if not execution:
                if domain == 'irrigation':
                    execution = service.insert_v2_irrigation_execution_once(plan, action, payload)
                elif domain == 'xiaomi_x10':
                    execution = service.insert_v2_x10_execution_once(plan, payload)
                else:
                    execution = service.insert_v2_climate_execution_once(plan, payload)
                if execution and payload.get('_audit_legacy_recovery'):
                    # Existing domain executors mark recent shadow rows. A July
                    # backfill must not become today's executable/confirmed work.
                    recovered = {'audit_recovered': True, 'delivery_uncertain': True,
                                 'published': None, 'publish_attempted': None,
                                 'reason': 'legacy_partial_chain_publish_unknown'}
                    execution = queries.execute_one("""update hc.execution set status='unknown',
                        created_at=%s, result=result || %s::jsonb,
                        metadata=metadata || '{"audit_recovered":true}'::jsonb
                        where id=%s returning *""",
                        (run['requested_at'], service.json_dumps(recovered), execution['id']))
            if (not execution or execution['domain'] != domain
                    or execution['event_id'] != event_row['id']):
                raise RuntimeError('Scheduler execution link is missing or inconsistent')
            return {'created': created, 'run': run, 'execution': execution}

    def recover(self):
        # Recovery is independent of the current due minute/day. Bounded batches
        # also repair legacy run-only/event-only/plan-only chains after a restart.
        with self.transaction() as queries:
            runs = queries.fetch_all("""
                select r.* from hc.scheduler_run r
                where r.idempotency_key like 'shadow:%%'
                  and ((r.domain='irrigation' and r.action in ('water_start','water_stop'))
                    or (r.domain='xiaomi_x10' and r.action='clean_start')
                    or (r.domain='climate' and r.action='climate_set'))
                  and not exists (
                    select 1 from hc.event e join hc.plan p on p.event_id=e.id
                    join hc.execution x on x.plan_id=p.id and x.event_id=e.id
                    where e.idempotency_key='v2:' || r.idempotency_key)
                order by r.requested_at, r.id limit 50
            """)
        for run in runs:
            self.prepare({'key': run['idempotency_key'], 'domain': run['domain'],
                          'action': run['action'], 'status': run['status'], 'payload': run['payload']})
        return len(runs)

    def record_due(self):
        self.scheduler.ensure_schema_callback()
        self.recover()
        return sum(int(self.prepare(event)['created']) for event in self.scheduler.shadow_audit_events())

    def claim_climate(self, execution_id):
        with self.transaction() as queries:
            row = queries.fetch_one("""
                select x.*, date_trunc('minute',r.requested_at)=date_trunc('minute',now()) as due_now
                from hc.execution x join hc.plan p on p.id=x.plan_id and p.event_id=x.event_id
                join hc.event e on e.id=x.event_id
                join hc.scheduler_run r on r.id::text=e.payload->>'scheduler_run_id'
                where x.id=%s and x.domain='climate' and x.status='pending'
                  and x.metadata->>'audit_protocol'=%s
                  and r.payload->>'_audit_protocol'=%s
                for update of x skip locked
            """, (execution_id, PROTOCOL, PROTOCOL))
            if not row:
                return None
            service = self.scoped(queries)
            engine = service.engine_state(service.config())
            allowed = (engine['enabled'] and 'climate' in engine['publish_domains'] and row['due_now']
                       and row['command_topic'] == self.scheduler.climate_command_topic)
            if not allowed:
                queries.execute_one("""update hc.execution set status='blocked', ended_at=now(), updated_at=now(),
                    result=result || %s::jsonb where id=%s returning *""",
                    (self.scheduler.json_dumps({'reason': 'dispatch_expired_or_domain_disabled', 'publish_attempted': False}), execution_id))
                return None
            result = {**row['result'], 'shadow': False, 'publish_attempted': True, 'published': None,
                      'delivery_uncertain': True, 'reason': 'dispatch_claimed_do_not_replay'}
            result['feedback_fence'] = fence(self.scheduler.climate_monitor_snapshot(),
                                            self.scheduler.feedback_wall_clock(), self.scheduler.feedback_monotonic_clock())
            command = {**row['command_payload'], 'hc_execution_id': str(row['id'])}
            metadata = {**row['metadata'], 'component': 'v2_scheduler_executor',
                        'command_owner': 'v2_climate_dispatch', 'side_effects': True}
            return queries.execute_one("""update hc.execution set status='unknown', attempt=1,
                started_at=now(), updated_at=now(), result=%s::jsonb, metadata=%s::jsonb
                ,command_payload=%s::jsonb
                where id=%s and status='pending' returning *""",
                (self.scheduler.json_dumps(result), self.scheduler.json_dumps(metadata), self.scheduler.json_dumps(command), execution_id))

    def dispatch(self, execution_id):
        # The context must commit successfully before any external side effect.
        claim = self.claim_climate(execution_id)
        if not claim:
            return None
        command = claim['command_payload']
        result = dict(claim['result'])
        result['physical_confirmation'] = False
        status = 'unknown'
        error = None
        try:
            if self.scheduler.publish_mqtt is None:
                raise RuntimeError('Climate publisher unavailable')
            ok, message = self.scheduler.publish_mqtt(claim['command_topic'], command)
            result.update(published=bool(ok), message=str(message)[:512])
            auto = []
            if ok and self.scheduler.sync_auto_climate_power_wall:
                if command.get('power') in ('on', 'off'):
                    auto = self.scheduler.sync_auto_climate_power_wall(command['power'])
                if result.get('extra_fan') in ('on', 'off'):
                    auto = self.scheduler.sync_auto_climate_power_wall(result['extra_fan'])
            result.update(auto_power_wall=auto, delivery_uncertain=not bool(ok),
                          reason='publisher_reported_success' if ok else 'publisher_result_uncertain')
            status = 'sent' if ok else 'unknown'
        except Exception as exc:
            result.update(delivery_uncertain=True, reason='dispatch_exception', exception_type=type(exc).__name__)
            error = 'Dispatch outcome uncertain; automatic replay is disabled'
        result['delivery_finalized'] = True
        with self.transaction() as queries:
            saved = queries.execute_one("""update hc.execution set status=%s, result=%s::jsonb,
                error=%s, ended_at=now(), updated_at=now()
                where id=%s and status='unknown' and attempt=1 returning *""",
                (status, self.scheduler.json_dumps(result), error, execution_id))
            if not saved:
                raise RuntimeError('Climate dispatch result was not persisted; do not replay')
            return saved

    def climate_tick(self):
        self.scheduler.ensure_schema_callback()
        with self.transaction() as queries:
            candidates = queries.fetch_all("""select id from hc.execution
                where domain='climate' and status='pending' and metadata->>'audit_protocol'=%s
                order by created_at, id limit 50""", (PROTOCOL,))
        dispatched = [self.dispatch(row['id']) for row in candidates]
        self.reconcile_climate()
        return dispatched

    def reconcile_climate(self):
        snapshot = self.scheduler.climate_monitor_snapshot()
        wall, mono = self.scheduler.feedback_wall_clock(), self.scheduler.feedback_monotonic_clock()
        with self.transaction() as queries:
            rows = queries.fetch_all("""select * from hc.execution where domain='climate'
                and status in ('sent','accepted','unknown') and metadata->>'audit_protocol'=%s
                and result->>'delivery_finalized'='true' and result ? 'feedback_fence'
                and coalesce(confirmation->>'terminal','false')<>'true'
                order by created_at, id limit 100 for update skip locked""", (PROTOCOL,))
            for row in rows:
                boundary = row['result']['feedback_fence']
                observation = climate_observation(snapshot, row['command_payload'], boundary,
                    self.scheduler.feedback_max_age_seconds, wall, mono)
                expired = wall > boundary['wall'] + self.scheduler.confirmation_timeout_seconds
                confirmed = observation['confirmed'] and not expired
                status = 'confirmed' if confirmed else 'unknown' if expired else 'accepted' if observation['accepted'] is True else row['status']
                observation.update(terminal=bool(confirmed or expired), confirmed=confirmed)
                if expired:
                    observation['reason'] = 'confirmation_timeout_no_automatic_replay'
                result = {**row['result'], 'physical_confirmation': confirmed,
                          'bridge_accepted': observation['accepted']}
                queries.execute_one("""update hc.execution set status=%s, confirmation=%s::jsonb,
                    result=%s::jsonb, updated_at=now() where id=%s returning *""",
                    (status, self.scheduler.json_dumps(observation), self.scheduler.json_dumps(result), row['id']))
