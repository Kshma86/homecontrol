import concurrent.futures
import fcntl
import json
import os
import shlex
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class AiNodeService:
    def __init__(
        self,
        fetch_power_wall_command_entity: Callable[[Any], Dict[str, Any]],
        publish_power_wall_switch: Callable[[Dict[str, Any], bool, str], Any],
        api_cache_delete_prefix: Callable[[str], Any],
        invalidate_context_sections: Callable[..., Any],
        process_binding_payload: Callable[[str], Any] = None,
        process_binding_entity_id: Callable[[str], Any] = None,
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
        return {
            "backup_running": self.ai_backup_running(),
            "lock_file": str(self.backup_lock_file),
            "deferred_shutdown": self.deferred_shutdown_request(),
        }

    def ai_backup_running(self):
        try:
            self.backup_root.mkdir(parents=True, exist_ok=True)
            with self.backup_lock_file.open("a+", encoding="utf-8") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return True
                finally:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_UN)
                    except OSError:
                        pass
        except OSError:
            return False
        return False

    def deferred_shutdown_request(self):
        try:
            if not self.deferred_shutdown_file.exists():
                return None
            data = json.loads(self.deferred_shutdown_file.read_text(encoding="utf-8") or "{}")
            return data if isinstance(data, dict) else {"raw": data}
        except Exception as exc:
            return {"error": str(exc), "path": str(self.deferred_shutdown_file)}

    def request_deferred_shutdown(self, delay_sec: Any = None):
        try:
            delay = int(delay_sec) if delay_sec is not None else int(self.power_off_delay_sec)
        except (TypeError, ValueError):
            delay = int(self.power_off_delay_sec)
        delay = max(0, min(delay, 24 * 60 * 60))
        self.backup_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "power_off_delay_sec": delay,
            "reason": "shutdown requested while AI HDD backup is running",
        }
        self.deferred_shutdown_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "deferred": True,
            "action": "shutdown",
            "message": "AI HDD backup is running; shutdown will run after backup completes",
            "request_file": str(self.deferred_shutdown_file),
            "backup_guard": self.backup_guard(),
        }

    def active_power_entity_id(self):
        binding_id = self.process_binding_entity_id("ai_node_power_plug") if self.process_binding_entity_id else None
        return str(binding_id or self.power_entity_id or "").strip()

    def health(self):
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            ssh_future = executor.submit(check_ssh)
            ollama_future = executor.submit(check_ollama)
            try:
                ssh_ok, ssh_detail = ssh_future.result(timeout=probe_timeout + 0.5)
            except Exception as exc:
                ssh_ok, ssh_detail = False, str(exc) or "probe timed out"
            try:
                ollama_ok, ollama_detail, models = ollama_future.result(timeout=probe_timeout + 0.5)
            except Exception as exc:
                ollama_ok, ollama_detail, models = False, str(exc) or "probe timed out", []

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
        row = self.power_plug_row()
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

    def schedule_power_off(self, delay_sec: Any = None):
        try:
            delay = int(delay_sec) if delay_sec is not None else int(self.power_off_delay_sec)
        except (TypeError, ValueError):
            delay = int(self.power_off_delay_sec)
        delay = max(0, min(delay, 24 * 60 * 60))
        entity_id = self.active_power_entity_id()
        if not entity_id:
            return {"scheduled": False, "reason": "AI node power plug is not configured"}

        def worker():
            time.sleep(delay)
            result = self.set_power_plug(False, "homecontrol-ai-node-delayed-power-off")
            print(f"[AI_NODE] delayed power off result={result}", flush=True)

        threading.Thread(target=worker, name="ai-node-power-off-delay", daemon=True).start()
        return {"scheduled": True, "delay_sec": delay, "entity_id": entity_id}

    def ssh_base_command(self):
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
