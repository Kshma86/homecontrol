from worker_runtime import BoundedJobs
import json
import os
import shlex
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from ai_power_coordination import AiPowerCoordinator
from deployment_policy import ai_disabled, unavailable, MESSAGE as RESTRICTION_MESSAGE


class AiNodeService:
    def __init__(
        self,
        fetch_power_wall_command_entity: Callable[[Any], Dict[str, Any]],
        publish_power_wall_switch: Callable[[Dict[str, Any], bool, str], Any],
        api_cache_delete_prefix: Callable[[str], Any],
        invalidate_context_sections: Callable[..., Any],
        process_binding_payload: Callable[[str], Any] = None,
        process_binding_entity_id: Callable[[str], Any] = None,
        *, coordinator=None, clock=None, wall_clock=None, start_worker=True,
    ):
        self.fetch_power_wall_command_entity = fetch_power_wall_command_entity
        self.publish_power_wall_switch = publish_power_wall_switch
        self.api_cache_delete_prefix = api_cache_delete_prefix
        self.invalidate_context_sections = invalidate_context_sections
        self.process_binding_payload = process_binding_payload
        self.process_binding_entity_id = process_binding_entity_id
        self.host = os.environ.get("AI_NODE_HOST", "").strip()
        self.name = os.environ.get("AI_NODE_NAME", "Remote AI Server").strip()
        self.mac = os.environ.get("AI_NODE_MAC", "").strip()
        self.broadcast = os.environ.get("AI_NODE_BROADCAST", "255.255.255.255").strip()
        self.ssh_user = os.environ.get("AI_NODE_SSH_USER", "").strip()
        self.ssh_port = int(os.environ.get("AI_NODE_SSH_PORT", "22"))
        self.ssh_key = os.environ.get("AI_NODE_SSH_KEY", "").strip()
        self.stack_dir = os.environ.get("AI_NODE_STACK_DIR", "~/homecontrol-ai-node").strip()
        self.net_iface = os.environ.get("AI_NODE_NET_IFACE", "").strip()
        self.power_entity_id = os.environ.get("AI_NODE_POWER_ENTITY_ID", "").strip()
        self.power_off_delay_sec = int(os.environ.get("AI_NODE_POWER_OFF_DELAY_SEC", "300"))
        self.ollama_url_override = os.environ.get("AI_NODE_OLLAMA_URL", "").strip().rstrip("/")
        self.openwebui_url = os.environ.get("AI_NODE_OPENWEBUI_URL", "").strip().rstrip("/")
        self.status_timeout = float(os.environ.get("AI_NODE_STATUS_TIMEOUT", "3"))
        self.ssh_timeout = float(os.environ.get("AI_NODE_SSH_TIMEOUT", "20"))
        self.backup_root = Path(os.environ.get("HC_BACKUP_DIR", "/srv/docker/homecontrol/backups"))
        self.backup_lock_file = self.backup_root / "ai-backup.lock"
        self.deferred_shutdown_file = self.backup_root / "ai-shutdown-after-backup.request"
        self.power_coordinator = coordinator or AiPowerCoordinator(self.backup_root)
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or time.time
        self._start_worker = start_worker
        import uuid
        self._owner = uuid.uuid4().hex
        self._pending = None
        self._power_thread = None
        self._power_event = threading.Event()
        self._power_stop = threading.Event()
        self._power_last_cycle = None
        self._power_error = None
        self._power_initialized = False
        self._health_jobs = BoundedJobs('ai-node-health', 2)

    def initialize_power_state(self):
        if not self._power_initialized:
            with self.power_coordinator.locked() as state:
                if self._power_initialized:
                    return
                self.power_coordinator.invalidate(state, 'backend session started')
                state['backend_owner'] = self._owner
                self.power_coordinator.save(state)
                self._power_initialized = True

    def start_power_guard(self):
        if ai_disabled():
            self._pending = None
            return True
        try:
            self.initialize_power_state()
            return True
        except (OSError, ValueError):
            self._power_error = 'AI power guard is unavailable; power actions are blocked'
            return False

    def ollama_url(self):
        if self.ollama_url_override:
            return self.ollama_url_override
        if self.host:
            return f"http://{self.host}:11434"
        return ""

    def public_config(self):
        return {
            "name": self.name,
            "host": self.host,
            "mac_set": bool(self.mac),
            "broadcast": self.broadcast,
            "ssh_user": self.ssh_user,
            "ssh_port": self.ssh_port,
            "ssh_key_set": bool(self.ssh_key),
            "stack_dir": self.stack_dir,
            "net_iface": self.net_iface,
            "power_entity_id": self.active_power_entity_id(),
            "power_off_delay_sec": self.power_off_delay_sec,
            "ollama_url": self.ollama_url(),
            "openwebui_url": self.openwebui_url,
        }

    def backup_guard(self):
        guard = self.power_coordinator.guard()
        try:
            intent = self.power_coordinator.read().get('intent')
        except (OSError, ValueError):
            intent = None
            guard.update(backup_running=None, guard_known=False)
        return {**guard,
            "lock_file": str(self.backup_lock_file),
            "deferred_shutdown": intent if intent and intent.get('owner') == self._owner and intent.get('phase') == 'shutdown' else None,
            "pending_power_off": intent if intent and intent.get('owner') == self._owner and intent.get('phase') == 'off' else None,
            "previous_session_intent_ignored": bool(intent and intent.get('owner') != self._owner),
            "power_error": self._power_error,
        }

    def ai_backup_running(self):
        return self.power_coordinator.guard()['backup_running']

    def deferred_shutdown_request(self):
        return self.backup_guard()['deferred_shutdown']

    def request_deferred_shutdown(self, delay_sec: Any = None):
        return self.shutdown_request(delay_sec, True)[0]

    def active_power_entity_id(self):
        binding_id = self.process_binding_entity_id("ai_node_power_plug") if self.process_binding_entity_id else None
        return str((binding_id if self.process_binding_entity_id else self.power_entity_id) or "").strip()

    def health(self):
        if ai_disabled():
            return {**unavailable(), 'state': 'disabled', 'configured': bool(self.host),
                    'node': self.public_config(), 'ssh': {'ok': False, 'detail': RESTRICTION_MESSAGE},
                    'ollama': {'ok': False, 'detail': RESTRICTION_MESSAGE, 'models': []},
                    'backup_guard': {**self.backup_guard(), 'deferred_shutdown': None,
                                     'pending_power_off': None}}
        config = self.public_config()
        ollama_url = self.ollama_url()
        probe_timeout = min(max(float(self.status_timeout), 0.5), 1.2)

        def check_ssh():
            return self.tcp_probe(self.host, self.ssh_port, probe_timeout)

        def check_ollama():
            if not ollama_url:
                return False, "not configured", []
            try:
                with urlopen(f"{ollama_url}/api/tags", timeout=probe_timeout) as response:
                    data = json.loads(response.read().decode("utf-8") or "{}")
                raw_models = data.get("models") if isinstance(data.get("models"), list) else []
                models = [{"name": item.get("name") or item.get("model") or "", "size": item.get("size")} for item in raw_models if item.get("name") or item.get("model")]
                return True, "reachable", models
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                return False, str(exc), []

        deadline = time.monotonic() + probe_timeout + .5
        futures = []
        for probe in (check_ssh, check_ollama):
            try:
                futures.append(self._health_jobs.submit(probe))
            except Exception:
                futures.append(None)
        try:
            if futures[0] is None:
                raise RuntimeError('probe capacity exhausted')
            ssh_ok, ssh_detail = futures[0].result(timeout=max(0, deadline-time.monotonic()))
        except Exception as exc:
            ssh_ok, ssh_detail = False, str(exc) or "probe timed out or capacity exhausted"
        try:
            if futures[1] is None:
                raise RuntimeError('probe capacity exhausted')
            ollama_ok, ollama_detail, models = futures[1].result(timeout=max(0, deadline-time.monotonic()))
        except Exception as exc:
            ollama_ok, ollama_detail, models = False, str(exc) or "probe timed out or capacity exhausted", []

        return {
            "ok": bool(ssh_ok or ollama_ok),
            "configured": bool(self.host),
            "state": "available" if (ssh_ok or ollama_ok) else "unavailable",
            "node": config,
            "process_bindings": {
                "ai_node_power_plug": self.process_binding_payload("ai_node_power_plug") if self.process_binding_payload else None,
            },
            "ssh": {"ok": ssh_ok, "detail": ssh_detail},
            "ollama": {"ok": ollama_ok, "detail": ollama_detail, "models": models},
            "backup_guard": self.backup_guard(),
        }

    def send_wake_on_lan(self):
        if ai_disabled():
            raise ValueError(RESTRICTION_MESSAGE)
        clean = self.mac.replace("-", "").replace(":", "").replace(".", "").strip()
        if len(clean) != 12:
            raise ValueError("AI_NODE_MAC must contain 12 hex characters")
        try:
            mac_bytes = bytes.fromhex(clean)
        except ValueError as exc:
            raise ValueError("AI_NODE_MAC is not a valid hex MAC address") from exc
        packet = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for _ in range(3):
                for port in (9, 7):
                    sock.sendto(packet, (self.broadcast or "255.255.255.255", port))

    def power_plug_row(self):
        entity_id = self.active_power_entity_id()
        if not entity_id:
            return None
        return self.fetch_power_wall_command_entity(entity_id)

    def set_power_plug(self, value: bool, source: str):
        if ai_disabled():
            return unavailable()
        self.initialize_power_state()
        with self.power_coordinator.locked() as state:
            self.power_coordinator.invalidate(state, 'explicit power request')
            self._pending = None
            self._power_event.set()
            if value:
                return self._publish_power(value, source)
            with self.power_coordinator.reserve_power():
                return self._publish_power(value, source)

    def _publish_power(self, value: bool, source: str, row=None):
        if ai_disabled():
            return unavailable()
        row = row or self.power_plug_row()
        if not row:
            return {
                "ok": False,
                "skipped": not bool(self.active_power_entity_id()),
                "message": "AI node power plug is not configured" if not self.active_power_entity_id() else "AI node power plug entity not found",
            }
        ok, message, topic, payload = self.publish_power_wall_switch(row, value, source)
        self.api_cache_delete_prefix("power_wall_state")
        self.api_cache_delete_prefix("tuya_state")
        self.invalidate_context_sections("power_wall", "tuya")
        return {
            "ok": ok,
            "skipped": False,
            "message": message,
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "topic": topic,
            "payload": payload,
        }

    def _delay(self, delay_sec):
        try:
            delay = int(delay_sec) if delay_sec is not None else int(self.power_off_delay_sec)
        except (TypeError, ValueError):
            delay = int(self.power_off_delay_sec)
        return max(0, min(delay, 24 * 60 * 60))

    @staticmethod
    def _identity(row):
        return {key: str(row.get(key) or '') for key in ('entity_id', 'topic_base', 'platform', 'device_id')}

    def _new_intent(self, state, phase, delay, on_failure=False):
        row = self.power_plug_row()
        self.power_coordinator.invalidate(state, 'new shutdown intent')
        intent = {'owner': self._owner, 'generation': state['generation'],
                  'entity_id': self.active_power_entity_id(), 'identity': self._identity(row or {}),
                  'phase': phase, 'delay_sec': delay, 'on_failure': on_failure,
                  'due': self._clock() + (delay if phase == 'off' else 0),
                  'due_at_epoch': self._wall_clock() + delay if phase == 'off' else None,
                  'expires_at': self._wall_clock() + (delay + 60 if phase == 'off' else 86400)}
        state['intent'] = intent
        self.power_coordinator.save(state)
        self._pending = intent
        return intent

    def _ensure_power_worker(self):
        if self._start_worker and self._power_thread is None:
            self._power_last_cycle = time.monotonic()
            self._power_thread = threading.Thread(target=self._power_loop, name='ai-node-power-intent', daemon=True)
            self._power_thread.start()
        self._power_event.set()

    def _power_loop(self):
        while not self._power_stop.is_set():
            self._power_event.wait(1)
            if self._power_stop.is_set():
                break
            self._power_event.clear()
            self.run_pending_power()
            self._power_last_cycle = time.monotonic()

    def stop_worker(self, timeout=3):
        deadline = time.monotonic() + max(0, timeout)
        self._power_stop.set()
        self._power_event.set()
        if self._power_thread is not None:
            self._power_thread.join(max(0, timeout))
        probes_stopped = self._health_jobs.stop(max(0, deadline-time.monotonic()))
        return not (self._power_thread and self._power_thread.is_alive()) and probes_stopped

    def worker_status(self):
        age = None if self._power_last_cycle is None else max(0, time.monotonic()-self._power_last_cycle)
        running = bool(self._power_thread and self._power_thread.is_alive())
        return {'key': 'ai-node-power-intent', 'name': 'AI power intent',
                'enabled': self._power_thread is not None, 'running': running,
                'last_cycle_age_sec': age, 'stalled': bool(running and age is not None and age > 60),
                'error': self._power_error, 'health_jobs': self._health_jobs.status(),
                'stopping': self._power_stop.is_set()}

    def close(self):
        self.stop_worker(self.ssh_timeout + 2)
        if self._power_initialized:
            try:
                with self.power_coordinator.locked() as state:
                    if (state.get('intent') or {}).get('owner') == self._owner:
                        self.power_coordinator.invalidate(state, 'power worker stopped')
                    self._pending = None
            except (OSError, ValueError):
                self._pending = None

    def cancel_pending_power(self, reason='new use'):
        self.initialize_power_state()
        with self.power_coordinator.locked() as state:
            self.power_coordinator.invalidate(state, reason)
            self._pending = None
            self._power_event.set()

    def wake(self, backup_run_id=None):
        if ai_disabled():
            return unavailable(), 503
        self.initialize_power_state()
        # This lock covers cancellation, power ON and WOL as one ordered action.
        with self.power_coordinator.locked() as state:
            self.power_coordinator.invalidate(state, 'wake', backup_run_id=backup_run_id)
            self._pending = None
            self._power_event.set()
            power = self._publish_power(True, 'homecontrol-ai-node-wake')
            if not self.mac:
                return {'ok': bool(power.get('ok')), 'error': 'AI_NODE_MAC is not configured', 'power': power}, 400
            try:
                self.send_wake_on_lan()
            except ValueError as exc:
                return {'ok': False, 'error': str(exc), 'power': power}, 400
            except OSError:
                return {'ok': False, 'error': 'Wake-on-LAN failed', 'power': power}, 502
            return {'ok': True, 'message': 'power on requested and wake packet sent', 'power': power, 'node': self.public_config()}, 202

    def schedule_power_off(self, delay_sec: Any = None):
        if ai_disabled():
            return {'scheduled': False, 'reason': RESTRICTION_MESSAGE}
        try:
            self.initialize_power_state()
            with self.power_coordinator.locked() as state:
                if not self.power_plug_row():
                    return {'scheduled': False, 'reason': 'AI node power plug is not configured or unavailable'}
                intent = self._new_intent(state, 'off', self._delay(delay_sec))
                self._ensure_power_worker()
                return {'scheduled': True, 'delay_sec': intent['delay_sec'], 'entity_id': intent['entity_id']}
        except (OSError, ValueError):
            return {'scheduled': False, 'reason': 'AI power guard is unavailable'}

    def shutdown_request(self, delay_sec=None, on_failure=False, backup_run_id=None):
        if ai_disabled():
            return unavailable(), 503
        try:
            self.initialize_power_state()
            with self.power_coordinator.locked() as state:
                if backup_run_id is not None and not self.power_coordinator.accepts_completion(state, backup_run_id):
                    return {'ok': False, 'cancelled': True, 'error': 'Stale backup shutdown request'}, 409
                intent = self._new_intent(state, 'shutdown', self._delay(delay_sec), on_failure)
                result = self._execute_power_intent(state, intent)
                self._ensure_power_worker()
                return result
        except (OSError, ValueError):
            self._pending = None
            self._power_error = 'AI power guard is unavailable'
            return {'ok': False, 'error': 'AI power guard is unavailable; shutdown was not dispatched'}, 503

    def _execute_power_intent(self, state, intent):
        if ai_disabled():
            self._pending = None
            return unavailable(), 503
        try:
            with self.power_coordinator.reserve_power():
                current = self.active_power_entity_id()
                row = self.power_plug_row()
                if (current != intent['entity_id'] or self._identity(row or {}) != intent['identity']
                        or self._wall_clock() > intent['expires_at']):
                    self.power_coordinator.invalidate(state, 'binding changed or intent expired')
                    self._pending = None
                    return {'ok': False, 'cancelled': True}, 409
                if intent['phase'] == 'off':
                    result = self._publish_power(False, 'homecontrol-ai-node-delayed-power-off', row)
                    state['intent'] = None
                    state['last_power_off'] = {'state': 'requested' if result.get('ok') else 'failed', 'entity_id': current}
                    self.power_coordinator.save(state)
                    self._pending = None
                    return result, 200 if result.get('ok') else 502
                try:
                    result = self.remote_command('shutdown')
                    status = 200 if result.get('ok') else 502
                except ValueError as exc:
                    result, status = {'ok': False, 'error': str(exc)}, 400
                except subprocess.TimeoutExpired:
                    result, status = {'ok': False, 'error': 'AI node SSH command timed out'}, 504
                except OSError:
                    result, status = {'ok': False, 'error': 'AI node SSH command failed'}, 502
                if row and (result.get('ok') or (intent['on_failure'] and status != 400)):
                    intent.update(phase='off', due=self._clock() + intent['delay_sec'],
                                  due_at_epoch=self._wall_clock() + intent['delay_sec'],
                                  expires_at=self._wall_clock() + intent['delay_sec'] + 60)
                    state['intent'] = intent
                    self._pending = intent
                    self.power_coordinator.save(state)
                    result['power_off'] = {'scheduled': True, 'entity_id': current, 'delay_sec': intent['delay_sec']}
                    if not result.get('ok'):
                        status = 202
                else:
                    state['intent'] = None
                    self.power_coordinator.save(state)
                    self._pending = None
                    result['power_off'] = {'scheduled': False}
                result['action'] = 'shutdown'
                return result, status
        except BlockingIOError:
            if intent['phase'] == 'off':
                self.power_coordinator.invalidate(state, 'backup active at power-off deadline')
                self._pending = None
                return {'ok': False, 'cancelled': True}, 409
            return {'ok': True, 'deferred': True, 'action': 'shutdown',
                    'message': 'Shutdown queued until backup/check releases its locks'}, 202
        except Exception:
            # Still inside the coordination lock: fail this exact intent before
            # another request can replace it. Uncertain execution never retries.
            self._power_error = 'AI power intent cancelled after guard or execution failure'
            self._pending = None
            try:
                self.power_coordinator.invalidate(state, 'guard or execution failure')
            except (OSError, ValueError):
                pass
            return {'ok': False, 'error': self._power_error}, 503

    def run_pending_power(self):
        if ai_disabled():
            self._pending = None
            return None
        if self._power_stop.is_set() or not self._pending:
            return None
        try:
            with self.power_coordinator.locked() as state:
                pending = self._pending
                if not pending or (pending['phase'] == 'off' and self._clock() < pending['due']):
                    return None
                intent = state.get('intent') or {}
                if (state.get('backend_owner') != self._owner or intent.get('owner') != self._owner or intent.get('generation') != pending['generation']
                        or state.get('generation') != pending['generation']):
                    self._pending = None
                    return None
                return self._execute_power_intent(state, intent)
        except Exception:
            # No guard/DB/transport failure authorizes a physical OFF or retry.
            self._power_error = 'AI power intent cancelled after guard or execution failure'
            self._pending = None
            return None

    def ssh_base_command(self):
        if ai_disabled():
            raise ValueError(RESTRICTION_MESSAGE)
        if not self.host:
            raise ValueError("AI_NODE_HOST is not configured")
        if not self.ssh_user:
            raise ValueError("AI_NODE_SSH_USER is not configured")
        command = [
            "ssh",
            "-p",
            str(self.ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"ConnectTimeout={max(1, int(self.status_timeout))}",
        ]
        if self.ssh_key:
            command.extend(["-i", self.ssh_key])
        command.append(f"{self.ssh_user}@{self.host}")
        return command

    def remote_command(self, action: str):
        if ai_disabled():
            raise ValueError(RESTRICTION_MESSAGE)
        stack_dir = shlex.quote(self.stack_dir)
        net_iface = shlex.quote(self.net_iface) if self.net_iface else ""
        wol_enable = f"sudo -n ethtool -s {net_iface} wol g && " if net_iface else ""
        gpu_compose = "docker compose -f docker-compose.yml -f docker-compose.gpu.yml"
        commands = {
            "start_stack": f"cd {stack_dir} && {gpu_compose} up -d",
            "stop_stack": f"cd {stack_dir} && docker compose stop",
            "restart_stack": f"cd {stack_dir} && {gpu_compose} restart",
            "pull_images": f"cd {stack_dir} && {gpu_compose} pull",
            "shutdown": f"{wol_enable}sudo -n shutdown -h now",
        }
        if action not in commands:
            raise ValueError("unsupported AI node command")
        started = time.perf_counter()
        result = subprocess.run(
            self.ssh_base_command() + [commands[action]],
            capture_output=True,
            text=True,
            timeout=self.ssh_timeout,
            check=False,
        )
        payload = {
            "ok": result.returncode == 0,
            "action": action,
            "returncode": result.returncode,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "stdout": (result.stdout or "").strip()[-4000:],
            "stderr": (result.stderr or "").strip()[-4000:],
        }
        if not payload["ok"]:
            payload["error"] = payload["stderr"] or payload["stdout"] or f"AI node command failed with exit code {result.returncode}"
        return payload

    @staticmethod
    def tcp_probe(host: str, port: int, timeout: float = 3.0):
        if not host:
            return False, "not configured"
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, "reachable"
        except OSError as exc:
            return False, str(exc)
