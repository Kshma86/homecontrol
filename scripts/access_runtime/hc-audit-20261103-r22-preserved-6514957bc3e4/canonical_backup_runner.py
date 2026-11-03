#!/usr/bin/env python3
"""HC-44 canonical entry point; rendered only into a sealed deployment package."""
from pathlib import Path
import runpy
import sys
FROZEN_ROOT = Path("/srv/docker/homecontrol/scripts/access_runtime/hc-audit-20261103-r22")
sys.path.insert(0, str(FROZEN_ROOT / 'infra/backend'))
runpy.run_path(str(FROZEN_ROOT / 'scripts/hostops/backup_runner.py'), run_name='__main__')
