"""HC-09: persist one weekly-sync intent, observe/read, write once, then observe.

Missing feedback never authorizes a repeated write. All MQTT calls follow a
committed claim; a new read cycle requires a changed desired layout, a new due
audit after confirmation, or newly observed drift after a confirmed layout.
"""
import hashlib
import json
import uuid

from scheduler_audit import SchedulerAudit
from scheduler_feedback import fence, fresh_frame, entry_matches, weekly_commands, weekly_observation


EXECUTOR = 'v2_x10_weekly_sync'


class X10ScheduleDelivery:
    def __init__(self, scheduler):
        self.s = scheduler
        self.audit = SchedulerAudit(scheduler)

    def observe(self, snapshot, commands, boundary):
        return weekly_observation(snapshot, commands, boundary, self.s.feedback_max_age_seconds,
                                  self.s.feedback_wall_clock(), self.s.feedback_monotonic_clock())

    def bound_audits(self, queries, commands):
        rows = queries.fetch_all("""select * from hc.execution where domain='xiaomi_x10'
            and executor='v2_x10_audit' and status in ('shadow_ready','pending')
            and created_at>=now()-interval '2 days' order by created_at,id limit 100""")
        return [r for r in rows if any(entry_matches(r['command_payload'], c) for c in commands)]

    def create(self, queries, commands, fingerprint, snapshot, audits):
        execution_id, event_id, plan_id = (str(uuid.uuid4()) for _ in range(3))
        command = {'map_id': commands[0]['map_id'], 'schedules': commands, 'source': 'v2_scheduler',
                   'hc_execution_id': execution_id}
        metadata = {'feedback_protocol': 'hc09-v1', 'desired_fingerprint': fingerprint,
                    'bound_audits': [str(r['id']) for r in audits], 'side_effects': False}
        run = self.audit.scoped(queries).insert_run_once('hc09:x10-weekly:'+execution_id,
                'xiaomi_x10', 'weekly_sync', 'dispatch_intent', payload=command)
        queries.execute_one("""insert into hc.event(id,type,source,domain,idempotency_key,payload,metadata)
            values(%s,'scheduler.weekly_sync','v2_scheduler','xiaomi_x10',%s,%s::jsonb,%s::jsonb) returning *""",
            (event_id, 'hc09:x10-weekly:'+execution_id, self.s.json_dumps({**command,'scheduler_run_id':run['id']}), self.s.json_dumps(metadata)))
        queries.execute_one("""insert into hc.plan(id,event_id,domain,type,status,actions,metadata)
            values(%s,%s,'xiaomi_x10','xiaomi_x10.weekly_sync','prepared',%s::jsonb,%s::jsonb) returning *""",
            (plan_id,event_id,self.s.json_dumps([{'command':command}]),self.s.json_dumps(metadata)))
        result = {'phase': 'observing', 'published': False, 'publish_attempted': False,
                  'read_requested': True, 'physical_confirmation': False,
                  'feedback_fence': fence(snapshot,self.s.feedback_wall_clock(),self.s.feedback_monotonic_clock())}
        return queries.execute_one("""insert into hc.execution(id,event_id,plan_id,domain,executor,status,
            command_topic,command_payload,result,metadata,started_at)
            values(%s,%s,%s,'xiaomi_x10',%s,'unknown',%s,%s::jsonb,%s::jsonb,%s::jsonb,now()) returning *""",
            (execution_id,event_id,plan_id,EXECUTOR,self.s.x10_weekly_schedule_topic,
             self.s.json_dumps(command),self.s.json_dumps(result),self.s.json_dumps(metadata)))

    def update_bound(self, queries, row, status, result, observation):
        for execution_id in row['metadata'].get('bound_audits', []):
            audit = queries.fetch_one("""select * from hc.execution where id=%s and executor='v2_x10_audit'
                and status in ('shadow_ready','pending','sent','accepted','unknown') for update""", (execution_id,))
            if not audit:
                continue
            # A fresh weekly snapshot must also follow this individual audit.
            if status == 'confirmed' and observation.get('sampled_at',0) < audit['created_at'].timestamp():
                continue
            queries.execute_one("""update hc.execution set status=%s,result=result || %s::jsonb,
                confirmation=%s::jsonb,updated_at=now(),ended_at=now() where id=%s returning *""",
                (status,self.s.json_dumps({'weekly_sync_id':str(row['id']),
                    'physical_confirmation':status=='confirmed','feedback_fence':result['feedback_fence'],
                    'confirmation_scope':'robot_weekly_schedule_not_cleaning_completion'}),
                 self.s.json_dumps(observation),execution_id))

    def save_observation(self, queries, row, observation, status, phase):
        result = {**row['result'], 'phase':phase, 'physical_confirmation':status=='confirmed'}
        terminal = phase in ('confirmed','unknown','blocked')
        observation = {**observation,'terminal':terminal,'confirmed':status=='confirmed'}
        saved = queries.execute_one("""update hc.execution set status=%s,result=%s::jsonb,
            confirmation=%s::jsonb,updated_at=now(),ended_at=case when %s then now() else ended_at end
            where id=%s returning *""",(status,self.s.json_dumps(result),self.s.json_dumps(observation),terminal,row['id']))
        self.update_bound(queries,saved,status,result,observation)
        return saved

    def tick(self, desired):
        commands = weekly_commands(self.s,desired)
        fingerprint = hashlib.sha256(json.dumps(json.loads(self.s.json_dumps(commands)),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        snapshot = self.s.x10_monitor_snapshot()
        action = None
        with self.audit.transaction() as queries:
            queries.fetch_one('select pg_advisory_xact_lock(8009009)')
            row = queries.fetch_one("""select * from hc.execution where domain='xiaomi_x10'
                and executor=%s order by created_at desc,id desc limit 1 for update""",(EXECUTOR,))
            audits = self.bound_audits(queries,commands)
            new_cycle = row is None or row['metadata'].get('desired_fingerprint') != fingerprint
            if row and row['status']=='confirmed' and not new_cycle:
                new_audits = {str(r['id']) for r in audits} - set(row['metadata'].get('bound_audits',[]))
                observation = self.observe(snapshot,commands,None)
                drift = (observation.get('fresh') and not observation['confirmed']
                         and observation.get('sampled_at',0)>row['confirmation'].get('sampled_at',0))
                new_cycle = bool(new_audits or drift)
            if new_cycle:
                scoped = self.audit.scoped(queries)
                engine = scoped.engine_state(scoped.config())
                if not engine['enabled'] or 'xiaomi_x10' not in engine['publish_domains']:
                    return {'ok': True, 'skipped': True, 'reason': 'x10_publish_not_enabled'}
                row = self.create(queries,commands,fingerprint,snapshot,audits)
                action = 'read'
            elif row['result']['phase'] in ('observing','awaiting'):
                boundary = row['result']['feedback_fence']
                observation = self.observe(snapshot,commands,boundary)
                expired = self.s.feedback_wall_clock()>boundary['wall']+self.s.confirmation_timeout_seconds
                if expired:
                    row = self.save_observation(queries,row,{**observation,'reason':'confirmation_timeout_no_replay'},'unknown','unknown')
                elif observation['confirmed']:
                    row = self.save_observation(queries,row,observation,'confirmed','confirmed')
                elif observation.get('fresh') and row['result']['phase']=='observing':
                    engine = self.audit.scoped(queries).engine_state(self.audit.scoped(queries).config())
                    if not engine['enabled'] or 'xiaomi_x10' not in engine['publish_domains']:
                        row = self.save_observation(queries,row,{'reason':'x10_domain_disabled'},'blocked','blocked')
                    elif not self.s.x10_active_cleaning_state()['active']:
                        # Persist the post-WRITE observation fence before I/O.
                        result = {**row['result'],'phase':'awaiting','publish_attempted':True,'published':None,
                                  'feedback_fence':fence(snapshot,self.s.feedback_wall_clock(),self.s.feedback_monotonic_clock())}
                        row = queries.execute_one("""update hc.execution set status='unknown',attempt=1,
                            result=%s::jsonb,metadata=metadata || '{"side_effects":true}'::jsonb,
                            updated_at=now() where id=%s returning *""",(self.s.json_dumps(result),row['id']))
                        action = 'write'
                else:
                    accepted = self.acceptance(snapshot,row)
                    row = self.save_observation(queries,row,{**observation,'accepted':accepted},
                        'accepted' if accepted is True else row['status'],row['result']['phase'])
        if action:
            self.perform(row,action)
        # Read back the committed current row; no device I/O here.
        current = self.s.fetch_one('select * from hc.execution where id=%s',(row['id'],))
        return {'ok':current['status']=='confirmed','status':current['status'],
                'result':current['result'],'confirmation':current['confirmation'],'execution_id':str(current['id'])}

    def acceptance(self,snapshot,row):
        reply,_ = fresh_frame(snapshot,'command_result',row['result']['feedback_fence'],
            self.s.feedback_max_age_seconds,self.s.feedback_wall_clock(),self.s.feedback_monotonic_clock(),
            source=lambda p:{'sampled_at':p.get('reported_at')})
        if (reply and reply.get('command')=='schedule_clean_week' and isinstance(reply.get('extra'),dict)
                and reply['extra'].get('hc_execution_id')==str(row['id']) and type(reply.get('ok')) is bool):
            return reply['ok']
        return None

    def perform(self,row,action):
        topic = self.s.x10_weekly_schedule_topic
        command = row['command_payload']
        if action=='read':
            topic = topic.rsplit('/',1)[0]+'/read_scheduler'
            command = {'hc_execution_id':str(row['id']),'source':'v2_scheduler_observation'}
        try:
            ok,message = self.s.publish_mqtt(topic,command) if self.s.publish_mqtt else (False,'publisher unavailable')
        except Exception as exc:
            ok,message = False,'publisher exception: '+type(exc).__name__
        delta = {action+'_transport_published':bool(ok),action+'_transport_message':str(message)[:512]}
        if action=='write':delta['published']=bool(ok)
        with self.audit.transaction() as queries:
            saved = queries.execute_one("""update hc.execution set result=result || %s::jsonb,
                status=case when %s='write' and status='unknown' and result->>'phase'='awaiting'
                            then %s else status end,updated_at=now() where id=%s returning *""",
                (self.s.json_dumps(delta),action,'sent' if ok else 'unknown',row['id']))
            if action=='write':self.update_bound(queries,saved,saved['status'],saved['result'],{'confirmed':False})
