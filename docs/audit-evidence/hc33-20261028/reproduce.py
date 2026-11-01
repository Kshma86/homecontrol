import json
from pathlib import Path
from psycopg2 import OperationalError
pending_measurements=[(1,'a',1,None,None,None,'{}'),(1,'b',2,None,None,None,'{}')]
MEASUREMENT_BATCH_SIZE=100
def execute_values(*a,**kw): raise OperationalError('fixture disconnected')
def log_limited(*a): pass
class Cursor:
 def execute(self,*a):raise OperationalError('fixture disconnected')
def insert_measurement_one(cur, row):
    (entity_id, key, v_num, v_bool, v_text, v_json, meta) = row
    cur.execute('\n        insert into hc.measurement (ts, entity_id, key, v_num, v_bool, v_text, v_json, meta)\n        values (now(), %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)\n    ', (entity_id, key, v_num, v_bool, v_text, v_json, meta))

def flush_measurements(cur):
    if not pending_measurements:
        return 0
    rows = pending_measurements[:]
    pending_measurements.clear()
    sql = '\n        insert into hc.measurement (ts, entity_id, key, v_num, v_bool, v_text, v_json, meta)\n        values %s\n    '
    template = '(now(), %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)'
    try:
        execute_values(cur, sql, rows, template=template, page_size=MEASUREMENT_BATCH_SIZE)
        return len(rows)
    except Exception as e:
        log_limited('batch_insert_error', f'[BATCH_ERR] execute_values failed, falling back row-by-row: {e}')
        inserted = 0
        for row in rows:
            try:
                insert_measurement_one(cur, row)
                inserted += 1
            except Exception as row_e:
                log_limited(f'row_insert:{row[0]}:{row[1]}', f'[ROW_ERR] entity={row[0]} key={row[1]} error={row_e}')
                continue
        return inserted
result=flush_measurements(Cursor())
assert result==0 and not pending_measurements
Path('/evidence/baseline-reproduction.json').write_text(json.dumps({'inserted':result,'remaining':len(pending_measurements),'connection_error_escaped':False,'device_io':False},indent=2)+'\n')
