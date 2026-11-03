"""HC-15: the exact former app queries keep their payload and validation."""
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from climate_service import ClimateService
from irrigation_service import IrrigationService
from runtime_utils import normalize_text

QUERIES=json.loads((Path(__file__).with_name('fixtures')/'hc15_queries.json').read_text())


class DomainScheduleReadTest(unittest.TestCase):
    def climate(self):
        # Exercise the real domain method with explicit synthetic dependencies.
        service=ClimateService.__new__(ClimateService)
        service.normalize_text=normalize_text
        service.ensure_season_profile_schema=Mock()
        service.ensure_scheduler_schema=Mock()
        service.fetch_all=Mock(return_value=[{'id':7,'schedule_status':'armed'}])
        return service

    def test_climate_profiles_keep_the_old_query_and_payload(self):
        for profile,normalized in [(None,None),('',None),('  ',None),(' summer ','summer'),('winter','winter')]:
            with self.subTest(profile=profile):
                service=self.climate();events=[]
                service.ensure_season_profile_schema.side_effect=lambda:events.append('season')
                service.ensure_scheduler_schema.side_effect=lambda:events.append('scheduler')
                service.fetch_all.side_effect=lambda *args:events.append('query') or [{'id':7,'schedule_status':'armed'}]
                self.assertEqual(service.fetch_schedule_rules(profile),[{'id':7,'schedule_status':'armed'}])
                sql,params=service.fetch_all.call_args.args
                self.assertEqual(re.sub(r'\s+',' ',sql).strip(),re.sub(r'\s+',' ',QUERIES['fetch_climate_schedule_rules']).strip())
                self.assertEqual(params,(normalized,));self.assertEqual(events,['season','scheduler','query'])

    def test_invalid_profiles_preserve_validation_and_never_query(self):
        for value in ('autumn','SUMMER',17,['winter']):
            service=self.climate()
            with self.subTest(profile=value),self.assertRaisesRegex(ValueError,'profile must be summer or winter'):
                service.fetch_schedule_rules(value)
            service.ensure_season_profile_schema.assert_called_once()
            service.ensure_scheduler_schema.assert_called_once()
            service.fetch_all.assert_not_called()

    def test_schema_failure_propagates_before_the_domain_query(self):
        service=self.climate();service.ensure_season_profile_schema.side_effect=RuntimeError('schema unavailable')
        with self.assertRaisesRegex(RuntimeError,'schema unavailable'):service.fetch_schedule_rules()
        service.ensure_scheduler_schema.assert_not_called();service.fetch_all.assert_not_called()

    def test_v2_session_preserves_query_conversion_result_and_missing_row(self):
        for source_ref in ('42',42,None):
            for result in (None,{'requested_stop_at':'2026-11-02T14:00:00+00:00'}):
                fetch=Mock(return_value=result)
                self.assertIs(IrrigationService.fetch_v2_session(SimpleNamespace(fetch_one=fetch),source_ref),result)
                sql,params=fetch.call_args.args
                self.assertEqual(re.sub(r'\s+',' ',sql).strip(),re.sub(r'\s+',' ',QUERIES['fetch_irrigation_v2_session']).strip())
                self.assertEqual(params,(str(source_ref),))
