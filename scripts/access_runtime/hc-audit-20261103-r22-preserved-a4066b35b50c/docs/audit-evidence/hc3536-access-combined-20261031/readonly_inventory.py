import json,os,psycopg
from psycopg.rows import dict_row
from process_binding_service import ProcessBindingService,PROCESS_BINDING_DEFINITIONS
with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row) as c:
 c.execute('set transaction read only')
 c.execute("set local statement_timeout='5s'")
 def one(sql,params=()):return c.execute(sql,params).fetchone()
 def all_rows(sql,params=()):return c.execute(sql,params).fetchall()
 def denied(*args,**kwargs):raise AssertionError('Read-only inventory attempted a write or command')
 service=ProcessBindingService(all_rows,one,denied,denied,lambda x:str(x).strip(),denied,denied)
 service._schema_ready=True
 bindings={key:service.binding(key) for key in PROCESS_BINDING_DEFINITIONS}
 policies=all_rows('select entity_id, auto_climate, auto_climate_delay_minutes, auto_climate_on_at from hc.power_wall_policy order by entity_id')
 print(json.dumps({'read_only_transaction':True,'bindings':bindings,'policies':policies},default=str))
