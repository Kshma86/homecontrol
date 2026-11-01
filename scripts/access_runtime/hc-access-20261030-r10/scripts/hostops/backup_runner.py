#!/usr/bin/env python3
"""HC-44 F6 adapter: preserve the runner and use isolated shared AI state."""
import importlib.util
from pathlib import Path
import sys
BASE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BASE/'infra/backend'))
from scoped_ai_power_coordination import ScopedAiPowerCoordinator
spec=importlib.util.spec_from_file_location('hc44_f6_runner',BASE/'scripts/backup_runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.AiPowerCoordinator=ScopedAiPowerCoordinator
# Workers import the unchanged BackupService in their own processes; the
# coordinator state path is used by this adapter, not changed in the live runner.
if __name__=='__main__':raise SystemExit(runner.main())
