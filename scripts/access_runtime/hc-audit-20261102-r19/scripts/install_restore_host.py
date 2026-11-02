#!/usr/bin/env python3
import runpy,sys
sys.path.insert(0,'/srv/docker/homecontrol/scripts/access_runtime/hc-audit-20261102-r19/scripts/access_release')
runpy.run_path('/srv/docker/homecontrol/scripts/access_runtime/hc-audit-20261102-r19/scripts/access_release/restore_host.py',run_name="__main__")
