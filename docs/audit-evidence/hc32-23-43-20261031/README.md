# HC-32 / HC-23 / HC-43, 2026-10-31

Current result: `summary.json`; audit status and remaining work:
`../../hc32-23-43-followups.md`. No production deployment.

- `before.json`, `original/`, `baseline-addendum.json`: immutable baseline and
  rollback source. The AI gateway originals were recovered from its unchanged
  baseline image/sealed r10 source, as recorded in the addendum.
- `unit-results.json`, `*-tests.log`: successful targeted matrices and a separate
  broad diagnostic. The broad backend discovery is not a successful full suite:
  old/new dependency sets have identical 29 failures, 7 errors, 183 skips.
- `broker.json`: six real broker/Tuya publisher cases; controlled token clock.
  `command-broker.json`: nine queue cases with fake actuators and connection
  adapters. All MQTT networks were internal and exposed no host ports.
- `process-lab.json`: seven Python processes start with unavailable dependencies.
  `frontend-process.json`: final successful static HTTP check, synthetic backend
  DNS alias, no API request. `frontend-process.log` retains an earlier fixture
  diagnostic without the alias; it is not the final acceptance result.
- `candidate-integrity.json`: baked sources/packages/wheels/frontend assets,
  no obsolete frontend bundles, AI isolation preserved.
- `python-before-advisories.json`, `python-candidate-advisories.json`: offline
  public-catalog comparison. Zero evaluable candidate matches; 53 unknown records
  remain. This is not a clean OS/HA/full npm security assessment.
- `os-inventory.json`: package names/versions from 15 live containers, read-only.
  No new OS vulnerability scan or live package update.
- `after.json`: 16 production containers, 646 sealed r10 source files, canonical
  Compose and the original audit unchanged; lab cleanup confirmed.

Reproduction entry points (from the repository root):

```bash
python3 scripts/check_f10_candidates.py
python3 -m unittest discover -s apps/bridge_runtime/tests -v
python3 docs/audit-evidence/hc32-23-43-20261031/run_broker_probe.py
python3 docs/audit-evidence/hc32-23-43-20261031/run_command_broker_probe.py
python3 docs/audit-evidence/hc32-23-43-20261031/run_process_lab.py
python3 docs/audit-evidence/hc32-23-43-20261031/verify_production_unchanged.py
```

Docker access is required for container checks; no sudo is used by these scripts.
The baseline verifier compares with this specific observation period and should
fail if production has since changed. Lab drivers refuse existing container
names and remove only their own containers/networks.

For the focused backend matrix, first stage public fixture sources:

```bash
python3 scripts/stage_f10_test_source.py --output /tmp/hc-f10-tests-new
docker run --rm --network none --read-only --user 1000:1000 \
  --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,exec,nosuid,nodev,size=256m \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --mount type=bind,src=/tmp/hc-f10-tests-new,dst=/srv/docker/homecontrol,readonly \
  --workdir /srv/docker/homecontrol/infra/backend \
  hc-f10-backend:20261031-candidate \
  python -B /srv/docker/homecontrol/scripts/check_f10_units.py
```

The production AI-offline policy is retained, not disabled for the focused suite.
The public catalog ZIP is external to the evidence tree; `catalog.json` records
its URL/hash. A later download can differ and must not silently replace this
dated result. `scripts/dependency_audit.py` requires the pinned `packaging` library
available in the candidate backend image. It sends no network requests.
