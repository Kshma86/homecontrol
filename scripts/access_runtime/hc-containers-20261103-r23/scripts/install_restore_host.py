#!/usr/bin/env python3
import runpy,sys
sys.path.insert(0,'/srv/docker/homecontrol/scripts/access_runtime/hc-containers-20261103-r23/scripts/access_release')
runpy.run_path('/srv/docker/homecontrol/scripts/access_runtime/hc-containers-20261103-r23/scripts/access_release/restore_host.py',run_name="__main__")
