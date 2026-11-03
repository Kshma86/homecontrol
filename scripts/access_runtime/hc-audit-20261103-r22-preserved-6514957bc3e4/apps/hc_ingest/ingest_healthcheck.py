"""Read-only HC-23 ingest liveness/readiness; no app import, SQL or MQTT I/O."""
import argparse
import json
import math
import os
from pathlib import Path
import time


def assess(status, heartbeat_epoch, *, now, start_ticks, maximum=30, mode='live'):
    if mode not in ('live','ready') or not math.isfinite(maximum) or maximum<=0:
        return False
    def fresh(value):
        return (isinstance(value,(float,int)) and not isinstance(value,bool)
                and math.isfinite(value) and 0<=now-value<=maximum)
    alive=(isinstance(status,dict) and status.get('process_start_ticks')==start_ticks
           and fresh(status.get('received_epoch')) and fresh(heartbeat_epoch))
    if not alive or mode=='live':
        return bool(alive)
    return (status.get('running') is True and status.get('db_ready') is True
            and status.get('mqtt_connected') is True and status.get('stalled') is False
            and status.get('stopping') is False)


def check(mode='live'):
    try:
        path=Path('/tmp/hc_ingest_status.json')
        if path.stat().st_size>65536:
            return False
        status=json.loads(path.read_text())
        ticks=Path('/proc/1/stat').read_text().rsplit(')',1)[1].split()[19]
        return assess(status,Path('/tmp/hc_ingest_heartbeat').stat().st_mtime,
            now=time.time(),start_ticks=ticks,
            maximum=float(os.getenv('INGEST_HEALTH_MAX_AGE_SECONDS','30')),mode=mode)
    except (OSError,ValueError,IndexError,TypeError):
        return False


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('live','ready'),default='live')
    raise SystemExit(0 if check(parser.parse_args().mode) else 1)
