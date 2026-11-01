import ast,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
from context_service import ContextService
from tests.test_irrigation_service import IrrigationServiceTest
clock=[0];calls=[];domain=IrrigationServiceTest().service()
domain.build_snapshot=lambda:calls.append(clock[0]) or {'value':1}
new='section_ttls' in __import__('inspect').signature(ContextService).parameters
if new:
 context=ContextService({'irrigation':domain.build_snapshot},realtime_ttl=5,section_ttls={'irrigation':10})
 context._cache.clock=lambda:clock[0];domain._read_cache.clock=lambda:clock[0]
else:context=ContextService({'irrigation':domain.snapshot},realtime_ttl=5)
with patch('context_service.time.monotonic',side_effect=lambda:clock[0]):
 for value in [0,5,9,10,15,20]:
  clock[0]=value;assert context.section('irrigation')['value']==1
print(json.dumps({'request_seconds':[0,5,9,10,15,20],'domain_builder_seconds':calls,'domain_builder_count':len(calls),'invalidation_events':0},indent=2))
