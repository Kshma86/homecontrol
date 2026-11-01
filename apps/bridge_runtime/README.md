# Bridge command runtime (HC-12)

Canonical standalone module: `command_dispatcher.py`. Each independent Docker
build context contains an identical copy in `tuya-poller`, `gree-climate`, and
`xiaomi-x10`. The copy-equality test is part of the semantic test suite:

```bash
python3 -m unittest discover -s apps/bridge_runtime/tests -v
```

After changing the canonical file, update those three copies together. Do not
import a sibling bridge or require a shared container deployment. The two narrow
Dockerfiles explicitly copy the dispatcher and existing MQTT credential helper;
X10 already copies its context. This change adds no third-party dependency.

Each dispatcher owns one worker, a bounded pending queue, monotonic expiry,
connection generations and a target-specific STOP/OFF barrier. Ordinary commands
remain FIFO. A fresh command submitted after a STOP is a new allowed intent.
The caller validates payloads/targets before admitting priority commands and
rechecks the item inside the existing hardware lock before sending.

The callback rejection function must be nonblocking and must not reconnect.
Outcome publishing is best effort. A queue acceptance or handler return does
not prove physical completion. No pending command is stored or replayed after a
process restart. The queue limits and priorities are documented in
`docs/hc12-bridge-commands.md` at the repository root.

HC-23 adds `worker_health.py` as another standalone canonical module. Keep its
copies in Tuya, Gree, X10 and Growatt identical. Its reporter observes actual poll
and command-owner progress; the probe only reads a bounded JSON file and checks
the producing process identity. It must not perform device/network I/O.
Current follow-up verification and release limits: `docs/hc32-23-43-followups.md`.
