"""Execute only selected bridge AST functions: no config loading or device/network imports."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from typing import Any, Dict

from scheduler_feedback import entry_matches, weekly_commands
from tests import test_scheduler_service as fixtures
from tests.test_scheduler_feedback import SCHEDULE

ROOT=Path(__file__).resolve().parents[3]


def functions(path,names,namespace):
    tree=ast.parse((ROOT/path).read_text())
    nodes=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:nodes.append(node)
        if isinstance(node,ast.ClassDef):
            nodes += [child for child in node.body if isinstance(child,ast.FunctionDef) and child.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


class BridgeSampleTest(unittest.TestCase):
    def test_gree_source_clock_is_taken_before_fresh_device_read(self):
        calls=[]
        async def connect():calls.append('device_read');return object()
        ns=functions(Path('apps/gree-climate/gree_climate_bridge.py'),['read_state'],
            {'Any':Any,'Dict':Dict,'time':SimpleNamespace(time=lambda:calls.append('clock') or 100.),
             'connect_device':connect,'state_payload':lambda d:{'ok':True,'power':'on'}})
        payload=asyncio.run(ns['read_state']())
        self.assertEqual(calls,['clock','device_read']);self.assertEqual(payload['sampled_at'],100.)

    def test_gree_correlated_reply_adds_report_time_without_changing_state_time(self):
        calls=[]
        ns=functions(Path('apps/gree-climate/gree_climate_bridge.py'),['publish_json'],
            {'Any':Any,'Dict':Dict,'BASE_TOPIC':'test/gree','json':json,'time':SimpleNamespace(time=lambda:101.)})
        bridge=SimpleNamespace(client=SimpleNamespace(publish=lambda *a,**kw:calls.append((a,kw))))
        ns['publish_json'](bridge,'test/gree/command_result',{'command':{'hc_execution_id':'one'},'state':{'sampled_at':100.}})
        data=json.loads(calls[0][0][1]);self.assertEqual(data['reported_at'],101.)
        self.assertEqual(data['state']['sampled_at'],100.)
        self.assertEqual(data['command']['hc_execution_id'],'one')

    def test_x10_every_actual_read_publishes_unretained_forced_sample(self):
        calls=[];order=[]
        def read(*a):order.append('device_read');return 'same layout'
        ns=functions(Path('apps/xiaomi-x10/xiaomi_x10_bridge.py'),['read_scheduler'],
            {'time':SimpleNamespace(time=lambda:order.append('clock') or 100.),'get_property':read,
             'parse_scheduler_entries_payload':lambda x:[SCHEDULE],
             'publish':lambda *a,**kw:calls.append((a,kw))})
        ns['read_scheduler']();ns['read_scheduler']()
        samples=[c for c in calls if c[0][0]=='scheduler/observation']
        self.assertEqual(len(samples),2);self.assertEqual(order[:2],['clock','device_read'])
        for args,kwargs in samples:
            self.assertEqual(kwargs,{'retain':False,'force':True})
            self.assertEqual(args[1],{'sampled_at':100.,'entries':[SCHEDULE]})

    def test_actual_x10_wire_parser_matches_canonical_zero_fields(self):
        ns=functions(Path('apps/xiaomi-x10/xiaomi_x10_bridge.py'),
            ['build_schedule_entry','parse_scheduler_entry'],{'CONFIG':{}})
        command=weekly_commands(fixtures.SchedulerServiceTest().service(),[SCHEDULE])[0]
        wire=ns['build_schedule_entry'](command['map_id'],command['segments'],command['start_time'],
             enabled=command['enabled'],days=command['days'],task_id=command['task_id'],
             clean_mode=command['mode'],suction=command['suction'],clean_param=command['water_level'])
        parsed=ns['parse_scheduler_entry'](wire)
        self.assertTrue(entry_matches(command,parsed),(command,parsed))

    def test_gree_command_sample_is_read_after_push_not_before(self):
        calls=[]
        async def push():calls.append('push')
        device=SimpleNamespace(push_state_update=push)
        async def connect():calls.append('initial_read');return device
        async def update(d):calls.append('post_write_read')
        async def sleep(n):calls.append('settle')
        ns=functions(Path('apps/gree-climate/gree_climate_bridge.py'),['apply_command'],
            {'Any':Any,'Dict':Dict,'time':SimpleNamespace(time=lambda:calls.append('clock') or float(len(calls))),
             'connect_device':connect,'state_payload':lambda d:{'ok':True,'power':'on'},
             'COMMAND_TIMEOUT':1,'asyncio':SimpleNamespace(wait_for=asyncio.wait_for,sleep=sleep),
             'update_state_and_wait':update})
        result=asyncio.run(ns['apply_command']({'power':'on','hc_execution_id':'one'}))
        self.assertEqual(calls,['clock','initial_read','push','settle','clock','post_write_read'])
        self.assertEqual(result['sampled_at'],5.)

    def test_x10_failed_or_malformed_read_cannot_publish_fresh_observation(self):
        for raw in (None, 123, 'bad;wire'):
            with self.subTest(raw=raw):
                calls=[]
                ns=functions(Path('apps/xiaomi-x10/xiaomi_x10_bridge.py'),['read_scheduler'],
                    {'time':SimpleNamespace(time=lambda:100.),'get_property':lambda *a:raw,
                     'parse_scheduler_entries_payload':lambda x:[],
                     'publish':lambda *a,**kw:calls.append((a,kw))})
                ns['read_scheduler']()
                self.assertFalse(any(args[0]=='scheduler/observation' for args,kw in calls))
