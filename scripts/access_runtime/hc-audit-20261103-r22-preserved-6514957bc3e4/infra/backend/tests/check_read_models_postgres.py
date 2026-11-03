"""Explicit HC-14/40 restored-DB check; see docs/hc-13-14-21-22-40-repair.md."""
import importlib.util,json,os,statistics,time,re
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from irrigation_summary_queries import DAILY_FORMULAS,bounded_daily_query,INPUT_KEYS
from tests.test_irrigation_service import IrrigationServiceTest
from runtime_utils import to_float,to_int,normalize_text,json_ready
# Explicit opt-in, disposable database only. Never point this check at HC live.
conn=psycopg.connect(os.environ['HC_READ_MODEL_TEST_DSN'],autocommit=True,row_factory=dict_row)
assert conn.info.dbname == 'hc_read_models_test', 'Disposable database name required'
evidence = Path(os.environ['HC_READ_MODEL_EVIDENCE'])
baseline = Path(os.environ['HC_READ_MODEL_BASELINE'])
assert baseline.is_file(), 'Pre-repair irrigation_service.py required'
conn.execute("set timezone='Europe/Budapest'")
conn.execute("set statement_timeout='90s'")
report={'measurement_rows':conn.execute('select count(*) n from hc.measurement').fetchone()['n'],'equivalence':[]}
def rows(sql):return conn.execute(sql).fetchall()
for days in (14,35,200):
 for name,formula in DAILY_FORMULAS.items():
  before=rows(f'select * from hc.{name} where day>=current_date-({days}-1) order by day')
  after=rows(f'select * from ({bounded_daily_query(name,days)}) x order by day')
  assert before==after,(name,days,before[:1],after[:1])
  report['equivalence'].append({'view':name,'days':days,'rows':len(after),'equal':True})
# Small, ordered fixtures cover carry-in, five minute cap, DST, gaps, terminal
# sample (no next_ts), point metrics, repeated timestamps and late arrivals.
conn.execute('create temporary table fixture_measurement (entity_id int, ts timestamptz, key text, v_num double precision, v_bool boolean)')
for tz,end in [('Europe/Budapest','2026-10-26'),('Europe/Budapest','2026-03-30'),('UTC','2026-10-26')]:
 conn.execute("select set_config('TimeZone',%s,false)",(tz,))
 conn.execute('truncate fixture_measurement')
 for name,(keys,intervals) in INPUT_KEYS.items():
  for key in keys:
   for offset,value in [('-1 day',1),('-2 minutes',2),('1 minute',3),('2 hours',4),('12 days 23 hours',5),('13 days 1 hour',6)]:
    conn.execute("insert into fixture_measurement values (1, %s::date - interval '13 days' + %s::interval, %s, %s, %s)",(end,offset,key,value,value%2==0))
 # Duplicate boundary timestamp across entities, with identical values to avoid
 # the original lead(order by ts) formula's unspecified tie order.
 conn.execute("insert into fixture_measurement select 2,ts,key,v_num,v_bool from fixture_measurement where key='pump_current_a' and v_num=2")
 for late in (False,True):
  if late:
   conn.execute("insert into fixture_measurement select 3, %s::date - interval '1 day 30 minutes',key,7,true from fixture_measurement group by key",(end,))
  for name,formula in DAILY_FORMULAS.items():
   original=f"select * from ({formula}) x where day >= date '{end}'-13 order by day"
   bounded=f"select * from ({bounded_daily_query(name,14)}) x order by day"
   original=original.replace('hc.measurement','fixture_measurement')
   bounded=bounded.replace('hc.measurement','fixture_measurement').replace('current_date',f"date '{end}'")
   assert rows(original)==rows(bounded),(tz,end,late,name)
report['boundary_cases']={'timezones':['UTC','Europe/Budapest'],'spring_and_autumn_dst':True,'carry_in_and_cap':True,'late_arrival':True,'cases':30}
conn.execute("set timezone='Europe/Budapest'")
counts={'queries':0,'updates':0,'summary_upserts':0}
def query(sql,params=(),one=False,write=False):
 counts['queries']+=1
 counts['updates']+=len(re.findall(r'\bupdate\s+hc\.irrigation_solar_pump_config\b',sql,re.I))
 counts['summary_upserts']+=len(re.findall(r'insert\s+into\s+hc\.irrigation_\w+_summary',sql,re.I))
 cur=conn.execute(sql,params or None)
 return (cur.fetchone() if one else cur.fetchall()) if cur.description else None
def service(old=False):
 obj=IrrigationServiceTest().service(fetch_all=lambda s,p=():query(s,p),fetch_one=lambda s,p=():query(s,p,True),execute_one=lambda s,p=():query(s,p,True,True),execute_sql=lambda s,p=None:query(s,p or (),write=True),to_float=to_float,to_int=to_int,normalize_text=normalize_text,daily_summary_days=200)
 obj._summary_schema_ready=True
 if old:
  spec=importlib.util.spec_from_file_location('hc_before_irrigation',str(baseline));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);obj.__class__=mod.IrrigationService
 return obj
# Same restored source, same warm DB, same callback inventory. Exclude volatile
# DB now()/age fields only when comparing business payloads below.
old,new=service(True),service()
for label,obj in [('before',old),('after',new)]:
 conn.execute('checkpoint')
 counts.update(queries=0,updates=0,summary_upserts=0)
 start_lsn=conn.execute('select pg_current_wal_insert_lsn() lsn').fetchone()['lsn']
 times=[];payloads=[]
 for _ in range(20):
  start=time.perf_counter();payloads.append(obj.build_snapshot());times.append((time.perf_counter()-start)*1000)
 wal=conn.execute('select pg_wal_lsn_diff(pg_current_wal_insert_lsn(),%s) n',(start_lsn,)).fetchone()['n']
 report[label]={'requests':20,'cold_ms':round(times[0],2),'warm_p95_ms':round(sorted(times[1:])[int(.95*(len(times)-2))],2),'queries':counts['queries'],'diagnostic_updates':counts['updates'],'summary_upserts':counts['summary_upserts'],'wal_bytes':int(wal)}
 if label=='before':old_payload=payloads[-1]
 else:new_payload=payloads[-1]
# Fragments unaffected by generated_at, evolving ages or relative run duration.
for key in ['energy_daily','pump_daily','solar_daily','tank_daily','temp_daily','schedules','sessions','latest']:
 assert old_payload[key]==new_payload[key],key
report['payload_equal_sections']=['energy_daily','pump_daily','solar_daily','tank_daily','temp_daily','schedules','sessions','latest']
# Read-only transaction protects the complete builders and evaluator. Failed
# legacy latest_decision UPDATE is also tested as a negative control.
conn.execute('begin read only')
try:
 for name,args in [('build_snapshot',()),('statistics_payload',('24h',)),('evaluate_solar_pump_scheduler',())]:
  getattr(service(),name)(*args)
 conn.execute('rollback')
 report['readonly_builders']=['build_snapshot','statistics_payload','evaluate_solar_pump_scheduler']
except BaseException:
 conn.execute('rollback');raise
conn.execute('begin read only')
try:
 old.evaluate_solar_pump_scheduler()
except psycopg.errors.ReadOnlySqlTransaction:
 report['negative_control_old_evaluation_writes']=True
else:raise AssertionError('Old evaluator unexpectedly read-only')
finally:conn.execute('rollback')
start=time.perf_counter();new.refresh_daily_summaries(force=True);report['background_refresh_ms']=round((time.perf_counter()-start)*1000,2)
(evidence/'postgres-results.json').write_text(json.dumps(json_ready(report),indent=2)+'\n');print(json.dumps(json_ready(report)))
