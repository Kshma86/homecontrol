import concurrent.futures,json,sys,threading
sys.path.insert(0,sys.argv[1])
from context_service import ContextService
from runtime_utils import ApiCache
from tests.test_irrigation_service import IrrigationServiceTest
results={}
for name in ('context','api','irrigation_snapshot','irrigation_pilot','irrigation_weather'):
 start,release=threading.Event(),threading.Event();version=[0];calls=[]
 def build():
  value=version[0];calls.append(value)
  if len(calls)==1:
   start.set()
   if not release.wait(3):raise RuntimeError('test timeout')
  return {'value':value}
 if name=='context':
  cache=ContextService({'key':build});read=lambda:cache.section('key');invalidate=lambda:cache.invalidate('key')
 elif name=='api':
  cache=ApiCache();read=lambda:cache.cached_payload('prefix:key',60,build);invalidate=lambda:cache.delete_prefix('prefix:')
 else:
  cache=IrrigationServiceTest().service();source,reader,invalidator={'irrigation_snapshot':('build_snapshot','snapshot','invalidate_snapshot_cache'),'irrigation_pilot':('evaluate_pilot','cached_pilot_recommendation','invalidate_pilot_cache'),'irrigation_weather':('weather_summary','cached_weather_summary','invalidate_weather_summary_cache')}[name];setattr(cache,source,build);read=getattr(cache,reader);invalidate=getattr(cache,invalidator)
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  f=pool.submit(read)
  try:
   assert start.wait(3);version[0]=1;invalidate()
  finally:release.set()
  value=f.result(3)
 results[name]={'returned_value':value['value'],'next_read_value':read()['value'],'builder_versions':calls}
print(json.dumps(results,indent=2))
