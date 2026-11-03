import unittest
from ingest_healthcheck import assess


class HealthTest(unittest.TestCase):
    def state(self,**changes):
        return dict(process_start_ticks='123',received_epoch=100,running=True,db_ready=True,
                    mqtt_connected=True,stalled=False,stopping=False,**changes)
    def test_healthy_live_and_ready(self):
        for mode in ('live','ready'):self.assertTrue(assess(self.state(),100,now=110,start_ticks='123',mode=mode))
    def test_database_mqtt_outage_or_stall_is_live_but_not_ready(self):
        for key,value in [('db_ready',False),('mqtt_connected',False),('stalled',True),('running',False),('stopping',True)]:
            state=self.state();state[key]=value
            self.assertTrue(assess(state,100,now=110,start_ticks='123'))
            self.assertFalse(assess(state,100,now=110,start_ticks='123',mode='ready'))
    def test_stale_future_or_other_process_files_cannot_claim_health(self):
        for timestamp,ticks in [(50,'123'),(120,'123'),(float('nan'),'123'),(100,'old')]:
            state=self.state();state['received_epoch']=timestamp
            self.assertFalse(assess(state,100,now=110,start_ticks=ticks))
        self.assertFalse(assess(self.state(),50,now=110,start_ticks='123'))
    def test_invalid_limits_and_missing_status_are_unhealthy(self):
        for limit in (0,-1,float('nan'),float('inf')):
            self.assertFalse(assess(self.state(),100,now=110,start_ticks='123',maximum=limit))
        self.assertFalse(assess({},100,now=110,start_ticks='123'))
