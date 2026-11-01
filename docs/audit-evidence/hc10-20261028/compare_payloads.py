import ast,hashlib,inspect,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from runtime_utils import ApiCache
from admin_service import AdminService
from energy_device_service import EnergyDeviceService
from power_wall_service import PowerWallService
from tests.test_irrigation_service import IrrigationServiceTest
result={}
def fixture(cls):
 calls=[];cache=ApiCache()
 def fetch_all(query,*args,**kwargs):calls.append(['all',query,args]);return []
 def fetch_one(query,*args,**kwargs):calls.append(['one',query,args]);return None
 options={'fetch_all':fetch_all,'fetch_one':fetch_one,'execute_one':lambda *a,**kw:None,'execute_sql':lambda *a,**kw:None,'db_conn':lambda:None,'dict_row':None,'publish_mqtt':lambda *a,**kw:(_ for _ in ()).throw(AssertionError('unexpected publish')),'normalize_text':lambda value,default='':str(value or '').strip() or default,'json_ready':lambda x:x,'api_cache_get':cache.get,'api_cache_set':cache.set,'api_cache_delete_prefix':cache.delete_prefix,'cached_api_payload':cache.cached_payload,'invalidate_context':lambda *a,**kw:None,'context_meta':lambda *a,**kw:{},'absolute_humidity_g_m3':lambda *a:None,'irrigation_context':lambda:{},'scheduler_state':lambda:{},'ensure_schema':lambda:None,'guard_repeat_seconds':30}
 if cls is None:
  service=IrrigationServiceTest().service(fetch_all=fetch_all,fetch_one=fetch_one,api_cache_get=cache.get,api_cache_set=cache.set,api_cache_delete_prefix=cache.delete_prefix)
  if hasattr(service,'cached_api_payload'):service.cached_api_payload=cache.cached_payload
  service.refresh_daily_summaries=lambda *a,**kw:None
  service.evaluate_solar_pump_scheduler=lambda:{'state':'disabled'}
  service.latest_solar_pump_runs=lambda *a:[]
 else:service=cls(**{n:options[n] for n in inspect.signature(cls).parameters if n in options})
 if cls is AdminService:
  service.ensure_opening_schema=lambda:None;service.ensure_temperature_schema=lambda:None
 return service,calls,cache
cases=[('home24h',AdminService,'homecontrol_statistics_payload',{}),('homecustom',AdminService,'homecontrol_statistics_payload',{'hours':48}),('tuya',EnergyDeviceService,'tuya_state_payload',{}),('power_wall',PowerWallService,'state_payload',{}),('marten',PowerWallService,'marten_motion_payload',{}),('power_history',PowerWallService,'history_payload',{'entity_id':3}),('irrigation',None,'snapshot',{}),('irrigation24h',None,'statistics_payload',{}),('irrigation7d',None,'statistics_payload',{'range_key':'7d'}),('irrigationcustom',None,'statistics_payload',{'hours':49})]
for label,cls,method,kw in cases:
 service,calls,cache=fixture(cls);payload=getattr(service,method)(**kw);cold=len(calls);encoded=json.dumps(payload,sort_keys=True,default=str);call_data=json.dumps(calls,sort_keys=True,default=str);getattr(service,method)(**kw)
 result[label]={'payload':json.loads(encoded),'query_count_cold':cold,'query_count_warm':len(calls)-cold,'query_sha256':hashlib.sha256(call_data.encode()).hexdigest()}
print(json.dumps(result,indent=2,ensure_ascii=False))
