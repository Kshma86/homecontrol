import io
import fcntl
import json
import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional


def normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def validate_schedule_time(value: Any, field: str) -> str:
    text = normalize_text(value)
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        raise ValueError(f"{field} must be HH:MM")
    return parsed.strftime("%H:%M")


class BackupService:
    DEFAULT_SETTINGS = {
        "include_postgres": True,
        "include_apps": True,
        "include_infra": True,
        "include_zigbee2mqtt": True,
        "include_homeassistant": True,
        "include_scripts": True,
        "include_docker_meta": True,
        "include_docker_volumes": True,
        "include_media": True,
        "include_gitea": False,
        "git_enabled": True,
        "ai_backup_host": "192.168.1.2",
        "ai_backup_user": "a",
        "ai_backup_mount": "/mnt/hc-backup",
        "ai_backup_ssh_key": "/srv/docker/homecontrol/infra/ssh/ai_node_key",
        "gitea_url": "http://192.168.1.2:3002",
        "git_repository": "homecontrol/config",
        "git_offsite_enabled": False,
        "git_offsite_remote": "",
        "git_offsite_branch": "main",
        "git_offsite_token_file": "/srv/docker/homecontrol/infra/ssh/git-offsite-token",
        "git_offsite_ssh_key": "",
        "git_paths": [
            "homeassistant/config",
            "homeassistant/docker-compose.yml",
            "infra/docker-compose.yml",
            "infra/backend",
            "infra/frontend",
            "apps",
            "scripts",
        ],
        "restic_enabled": False,
        "restic_repository": "sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol",
        "restic_password_file": "/etc/homecontrol/restic-password",
        "restic_keep_daily": 14,
        "restic_keep_weekly": 8,
        "restic_keep_monthly": 6,
        "restic_required": False,
        "ai_weekly_backup_enabled": True,
        "ai_weekly_backup_schedule": "Sun 03:30",
        "ai_weekly_shutdown_after": True,
        "restic_paths": [
            "/srv/docker/homecontrol/backups/latest archive",
            "/srv/docker/homecontrol/apps",
            "/srv/docker/homecontrol/infra",
            "/srv/docker/homecontrol/homeassistant",
            "/srv/docker/homecontrol/scripts",
            "/var/lib/docker/volumes",
        ],
        "retention_days": 14,
        "schedule_enabled": True,
        "schedule_time": "02:15",
    }

    def __init__(
        self,
        docker_socket_request: Callable[..., Any],
        docker_exec_capture: Callable[[str, Iterable[str]], bytes],
    ):
        self.docker_socket_request = docker_socket_request
        self.docker_exec_capture = docker_exec_capture
        self.backup_root = Path(os.environ.get("HC_BACKUP_DIR", "/srv/docker/homecontrol/backups"))
        self.settings_file = self.backup_root / "backup_settings.json"
        self.ai_backup_lock_file = self.backup_root / "ai-backup.lock"
        self.ai_backup_state_file = self.backup_root / "ai-backup-state.json"
        self.ai_shutdown_request_file = self.backup_root / "ai-shutdown-after-backup.request"
        self.restore_staging_root = Path(os.environ.get("HC_RESTORE_STAGING_DIR", "/srv/docker/homecontrol/restore_staging"))
        self.timer_file = Path(os.environ.get("HC_BACKUP_TIMER_FILE", "/srv/docker/homecontrol/scripts/systemd/homecontrol-backup.timer"))
        self.service_file = Path(os.environ.get("HC_BACKUP_SERVICE_FILE", "/srv/docker/homecontrol/scripts/systemd/homecontrol-backup.service"))
        self.sources = {
            "apps": Path("/srv/docker/homecontrol/apps"),
            "infra": Path("/srv/docker/homecontrol/infra"),
            "zigbee2mqtt/data": Path("/srv/docker/homecontrol/infra/zigbee2mqtt/data"),
            "homeassistant": Path("/srv/docker/homecontrol/homeassistant"),
            "scripts": Path("/srv/docker/homecontrol/scripts"),
        }
        self.restore_targets = {
            "apps": Path("/srv/docker/homecontrol/apps"),
            "infra": Path("/srv/docker/homecontrol/infra"),
            "zigbee2mqtt/data": Path("/srv/docker/homecontrol/infra/zigbee2mqtt/data"),
            "homeassistant": Path("/srv/docker/homecontrol/homeassistant"),
            "scripts": Path("/srv/docker/homecontrol/scripts"),
        }

    def latest_info(self):
        candidates = [
            Path(os.environ.get("HC_BACKUP_DIR", "")) if os.environ.get("HC_BACKUP_DIR") else None,
            Path("/srv/docker/homecontrol/backups"),
            Path(__file__).resolve().parent.parent.parent / "backups",
        ]
        for directory in [item for item in candidates if item]:
            try:
                files = [item for item in directory.iterdir() if item.is_file() and item.name != "backup.log"]
            except Exception:
                continue
            if not files:
                continue
            latest = max(files, key=lambda item: item.stat().st_mtime)
            stat = latest.stat()
            return {
                "ok": True,
                "path": str(latest),
                "name": latest.name,
                "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": stat.st_size,
                "error": "",
            }
        return {
            "ok": False,
            "path": None,
            "name": None,
            "timestamp": None,
            "size_bytes": None,
            "error": "backup directory is not available",
        }

    def settings(self):
        try:
            if self.settings_file.exists():
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                return {**self.DEFAULT_SETTINGS, **data}
        except Exception:
            pass
        return dict(self.DEFAULT_SETTINGS)

    def parse_timer_file(self):
        result = {
            "timer_file": str(self.timer_file),
            "service_file": str(self.service_file),
            "apply_path_source": "/srv/docker/homecontrol/scripts/systemd/homecontrol-backup-apply.path",
            "apply_service_source": "/srv/docker/homecontrol/scripts/systemd/homecontrol-backup-apply.service",
            "timer_file_exists": self.timer_file.exists(),
            "service_file_exists": self.service_file.exists(),
            "on_calendar": "",
            "schedule_time": None,
            "source_enabled": False,
            "systemctl_ok": False,
            "systemctl_error": "",
            "active": None,
            "next_elapse": None,
            "last_trigger": None,
            "reload_required": False,
        }
        try:
            text = self.timer_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip().startswith("OnCalendar="):
                    value = line.split("=", 1)[1].strip()
                    result["on_calendar"] = value
                    result["source_enabled"] = bool(value)
                    parts = value.rsplit(" ", 1)
                    if len(parts) == 2 and ":" in parts[1]:
                        result["schedule_time"] = ":".join(parts[1].split(":")[:2])
                    break
        except Exception as exc:
            result["systemctl_error"] = str(exc)

        systemctl = shutil.which("systemctl")
        if systemctl:
            try:
                proc = subprocess.run(
                    [
                        systemctl,
                        "show",
                        "homecontrol-backup.timer",
                        "--property=ActiveState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec",
                        "--no-pager",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                result["systemctl_ok"] = True
                for line in proc.stdout.splitlines():
                    key, _, value = line.partition("=")
                    if key == "ActiveState":
                        result["active"] = value
                    elif key == "NextElapseUSecRealtime":
                        result["next_elapse"] = value
                    elif key == "LastTriggerUSec":
                        result["last_trigger"] = value
                    elif key == "UnitFileState":
                        result["unit_file_state"] = value
            except Exception as exc:
                result["systemctl_error"] = str(exc)
        else:
            result["systemctl_error"] = result["systemctl_error"] or "systemctl command is not available"
        return result

    def write_timer_file(self, settings: Dict[str, Any]):
        schedule_time = validate_schedule_time(settings.get("schedule_time") or "02:15", "schedule_time")
        enabled = bool(settings.get("schedule_enabled", True))
        self.timer_file.parent.mkdir(parents=True, exist_ok=True)
        on_calendar = f"*-*-* {schedule_time}:00" if enabled else ""
        self.timer_file.write_text(
            "\n".join(
                [
                    "[Unit]",
                    "Description=Run HomeControl backup daily",
                    "",
                    "[Timer]",
                    f"OnCalendar={on_calendar}",
                    "Persistent=true",
                    "",
                    "[Install]",
                    "WantedBy=timers.target",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return self.parse_timer_file()

    def save_settings(self, data: Dict[str, Any]):
        settings = self.settings()
        for key, default in self.DEFAULT_SETTINGS.items():
            if key not in data:
                continue
            if isinstance(default, bool):
                settings[key] = bool(data.get(key))
            elif isinstance(default, list):
                value = data.get(key)
                if isinstance(value, list):
                    settings[key] = [normalize_text(item) for item in value if normalize_text(item)]
                else:
                    settings[key] = [line.strip() for line in str(value or "").splitlines() if line.strip()]
            elif isinstance(default, int):
                settings[key] = max(1, min(int(data.get(key) or default), 365))
            else:
                settings[key] = normalize_text(data.get(key), str(default))
        settings["schedule_time"] = validate_schedule_time(settings.get("schedule_time"), "schedule_time")
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        timer = self.write_timer_file(settings)
        settings["timer_source"] = timer
        return settings

    def archives(self):
        try:
            files = sorted(self.backup_root.glob("homecontrol_*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
        except Exception:
            return []
        result = []
        for item in files:
            stat = item.stat()
            result.append(
                {
                    "name": item.name,
                    "path": str(item),
                    "size_bytes": stat.st_size,
                    "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return result

    def safe_path(self, name: str):
        clean = Path(name).name
        path = self.backup_root / clean
        if not clean.endswith(".tar.gz") or not path.exists() or path.parent.resolve() != self.backup_root.resolve():
            raise ValueError("backup archive not found")
        return path

    def contents(self, name: str, limit: int = 500):
        path = self.safe_path(name)
        rows = []
        components = {}
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                rel = self.strip_root(member.name)
                if not rel:
                    continue
                top = rel.split("/", 1)[0]
                if rel.startswith("zigbee2mqtt/data/"):
                    top = "zigbee2mqtt/data"
                components.setdefault(top, {"name": top, "count": 0, "size_bytes": 0})
                components[top]["count"] += 1
                components[top]["size_bytes"] += max(member.size, 0)
                if len(rows) < limit:
                    rows.append(
                        {
                            "path": rel,
                            "size_bytes": member.size,
                            "type": "dir" if member.isdir() else "file",
                        }
                    )
        return {"components": sorted(components.values(), key=lambda item: item["name"]), "files": rows}

    def read_member_text(self, backup_name: str, rel_path: str, max_bytes: int = 300_000):
        archive_path = self.safe_path(backup_name)
        wanted = rel_path.strip().strip("/")
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                rel = self.strip_root(member.name)
                if rel == wanted:
                    if member.isdir():
                        raise ValueError("directories cannot be compared")
                    if member.size > max_bytes:
                        raise ValueError("file is too large for text compare")
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError("backup file cannot be read")
                    data = source.read(max_bytes + 1)
                    if not self.is_probably_text(data):
                        raise ValueError("backup file is not UTF-8 text")
                    return data.decode("utf-8"), member.size
        raise ValueError("file not found in backup")

    def compare_file(self, backup_name: str, rel_path: str):
        backup_text, backup_size = self.read_member_text(backup_name, rel_path)
        current_path = self.restore_destination_for(rel_path)
        current_exists = bool(current_path and current_path.exists() and current_path.is_file())
        current_text = ""
        current_size = None
        if current_exists:
            current_size = current_path.stat().st_size
            if current_size > 300_000:
                raise ValueError("current file is too large for text compare")
            data = current_path.read_bytes()
            if not self.is_probably_text(data):
                raise ValueError("current file is not UTF-8 text")
            current_text = data.decode("utf-8")
        rows = self.text_diff_rows(current_text, backup_text)
        changed = sum(1 for row in rows if row["type"] != "same")
        return {
            "path": rel_path,
            "current_path": str(current_path) if current_path else None,
            "current_exists": current_exists,
            "current_size_bytes": current_size,
            "backup_size_bytes": backup_size,
            "current_text": current_text,
            "backup_text": backup_text,
            "rows": rows[:2000],
            "truncated": len(rows) > 2000,
            "changed_rows": changed,
            "same": changed == 0 and current_exists,
        }

    def create(self):
        settings = self.settings()
        self.backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        root_name = f"homecontrol_{timestamp}"
        archive_path = self.backup_root / f"{root_name}.tar.gz"
        manifest = []

        with tarfile.open(archive_path, "w:gz") as archive:
            if settings.get("include_postgres"):
                dump = self.docker_exec_capture("homecontrol-postgres", ["pg_dump", "-U", "homecontrol", "-d", "homecontrol", "-Fc"])
                info = tarfile.TarInfo(f"{root_name}/postgres/homecontrol_{timestamp}.dump")
                info.size = len(dump)
                info.mtime = time.time()
                archive.addfile(info, fileobj=io.BytesIO(dump))
                manifest.append(info.name)

            source_map = [
                ("include_apps", "apps", self.sources["apps"]),
                ("include_infra", "infra", self.sources["infra"]),
                ("include_zigbee2mqtt", "zigbee2mqtt/data", self.sources["zigbee2mqtt/data"]),
                ("include_homeassistant", "homeassistant", self.sources["homeassistant"]),
                ("include_scripts", "scripts", self.sources["scripts"]),
            ]
            for setting_key, arcname, source in source_map:
                if settings.get(setting_key):
                    before = len(archive.getmembers())
                    self.add_directory_to_tar(archive, source, f"{root_name}/{arcname}")
                    after = len(archive.getmembers())
                    if after > before:
                        manifest.append(f"{root_name}/{arcname}/")

            if settings.get("include_docker_meta"):
                for filename, content in self.docker_meta_files().items():
                    info = tarfile.TarInfo(f"{root_name}/{filename}")
                    info.size = len(content)
                    info.mtime = time.time()
                    archive.addfile(info, fileobj=io.BytesIO(content))
                    manifest.append(info.name)

            manifest_bytes = ("\n".join(sorted(manifest)) + "\n").encode("utf-8")
            info = tarfile.TarInfo(f"{root_name}/MANIFEST.txt")
            info.size = len(manifest_bytes)
            info.mtime = time.time()
            archive.addfile(info, fileobj=io.BytesIO(manifest_bytes))

        retention_days = int(settings.get("retention_days") or 14)
        cutoff = time.time() - retention_days * 86400
        for old in self.backup_root.glob("homecontrol_*.tar.gz"):
            if old == archive_path:
                continue
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except Exception:
                pass
        stat = archive_path.stat()
        return {
            "name": archive_path.name,
            "path": str(archive_path),
            "size_bytes": stat.st_size,
            "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    def restore_paths(self, name: str, selected: Iterable[str], mode: str = "staging", confirm: str = ""):
        path = self.safe_path(name)
        if mode == "in_place" and confirm != "RESTORE":
            raise ValueError("RESTORE confirmation is required")
        restored = []
        target_root = self.restore_staging_root / path.name.replace(".tar.gz", "") if mode != "in_place" else None
        if target_root:
            target_root.mkdir(parents=True, exist_ok=True)

        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                rel = self.strip_root(member.name)
                if not rel or member.isdir() or not self.selected_restore_paths(rel, selected):
                    continue
                if rel.startswith("postgres/") and mode == "in_place":
                    raise ValueError("database dumps can only be restored to staging in this version")
                destination = (target_root / rel) if target_root else self.restore_destination_for(rel)
                if destination is None:
                    continue
                destination = destination.resolve()
                restore_root = self.restore_root_for(rel)
                allowed_root = target_root.resolve() if target_root else restore_root.resolve() if restore_root else None
                if allowed_root is None:
                    continue
                if allowed_root not in destination.parents and destination != allowed_root:
                    raise ValueError(f"unsafe restore path: {rel}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with open(destination, "wb") as handle:
                    shutil.copyfileobj(source, handle)
                restored.append({"path": rel, "destination": str(destination), "size_bytes": member.size})
        return {"mode": mode, "target": str(target_root) if target_root else "in-place", "restored": restored}

    def update_settings_payload(self, data: Dict[str, Any], context_meta: Callable[..., Dict[str, Any]]):
        settings = self.save_settings(data)
        return {"ok": True, "settings": settings, "timer": self.parse_timer_file(), "plan": self.backup_plan(settings), "context": context_meta("backup")}, 200

    def create_payload(self, context_meta: Callable[..., Dict[str, Any]]):
        backup = self.create()
        return {"ok": True, "backup": backup, "backups": self.archives(), "context": context_meta("backup")}, 200

    def full_ai_backup_payload(self, context_meta: Callable[..., Dict[str, Any]]):
        self.backup_root.mkdir(parents=True, exist_ok=True)
        request_file = self.backup_root / "full-ai-backup.request"
        now = datetime.now()
        if request_file.exists() and now.timestamp() - request_file.stat().st_mtime < 60:
            return {
                "ok": True,
                "mode": "full_ai_backup",
                "request_file": str(request_file),
                "message": "Full AI backup was already requested less than a minute ago",
                "context": context_meta("backup"),
            }, 200

        recent_success = self.latest_log_timestamp("== Weekly AI HDD backup kész ==")
        if recent_success and (now - recent_success).total_seconds() < 30 * 60:
            return {
                "ok": True,
                "mode": "full_ai_backup",
                "request_file": str(request_file),
                "message": f"Full AI backup already completed at {recent_success.strftime('%Y-%m-%d %H:%M:%S')}",
                "context": context_meta("backup"),
            }, 200

        request_file.write_text(datetime.now().isoformat() + "\n", encoding="utf-8")
        return {
            "ok": True,
            "mode": "full_ai_backup",
            "request_file": str(request_file),
            "message": "Full AI backup request queued for host systemd path helper",
            "context": context_meta("backup"),
        }, 202

    def gitea_environment(self):
        settings = self.settings()
        host = normalize_text(settings.get("ai_backup_host"), "192.168.1.2")
        repository = normalize_text(settings.get("git_repository"), "homecontrol/config").strip("/")
        return {
            **os.environ,
            "BASE": "/srv/docker/homecontrol",
            "GITEA_REMOTE": f"ssh://git@{host}:2222/{repository}.git",
            "GITEA_SSH_KEY": normalize_text(settings.get("ai_backup_ssh_key"), "/srv/docker/homecontrol/infra/ssh/ai_node_key"),
            "GITEA_BRANCH": normalize_text(settings.get("git_branch"), "main"),
            "GIT_OFFSITE_ENABLED": "true" if settings.get("git_offsite_enabled") else "false",
            "GIT_OFFSITE_REMOTE": normalize_text(settings.get("git_offsite_remote")),
            "GIT_OFFSITE_BRANCH": normalize_text(settings.get("git_offsite_branch"), "main"),
            "GIT_OFFSITE_TOKEN_FILE": normalize_text(settings.get("git_offsite_token_file"), "/srv/docker/homecontrol/infra/ssh/git-offsite-token"),
            "GIT_OFFSITE_SSH_KEY": normalize_text(settings.get("git_offsite_ssh_key")),
        }

    def run_gitea_script(self, script_name: str, args: Iterable[str] = (), timeout: int = 120):
        script = Path("/srv/docker/homecontrol/scripts") / script_name
        if not script.exists():
            raise ValueError(f"Gitea script not found: {script_name}")
        started = time.perf_counter()
        proc = subprocess.run(
            [str(script), *[str(arg) for arg in args]],
            cwd="/srv/docker/homecontrol",
            env=self.gitea_environment(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "stdout": stdout[-12000:],
            "stderr": stderr[-8000:],
        }

    def gitea_status_payload(self):
        result = self.run_gitea_script("gitea_config_status.sh", timeout=90)
        result.update({"mode": "gitea_status", "message": "Gitea snapshot status checked" if result["ok"] else "Gitea snapshot status failed"})
        return result, 200 if result["ok"] else 502

    def gitea_commit_payload(self, data: Dict[str, Any], context_meta: Callable[..., Dict[str, Any]]):
        message = normalize_text(data.get("message"), "Manual HomeControl configuration snapshot")[:200]
        result = self.run_gitea_script("gitea_config_commit.sh", [message], timeout=180)
        result.update({
            "mode": "gitea_commit",
            "message": "Gitea config snapshot pushed" if result["ok"] else "Gitea config snapshot push failed",
            "context": context_meta("backup"),
        })
        return result, 200 if result["ok"] else 502

    def gitea_restore_payload(self, data: Dict[str, Any]):
        ref = normalize_text(data.get("ref"), "main")[:120]
        result = self.run_gitea_script("gitea_config_restore.sh", [ref], timeout=180)
        result.update({"mode": "gitea_restore", "ref": ref, "message": "Gitea config restored to staging" if result["ok"] else "Gitea staging restore failed"})
        return result, 200 if result["ok"] else 502

    def latest_log_timestamp(self, marker: str):
        log_file = self.backup_root / "backup.log"
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]
        except Exception:
            return None
        for line in reversed(lines):
            if marker not in line or not line.startswith("["):
                continue
            end = line.find("]")
            if end <= 1:
                continue
            try:
                return datetime.strptime(line[1:end], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return None

    def contents_payload(self, name: str, limit: int = 500):
        safe_limit = max(50, min(int(limit or 500), 5000))
        return {"ok": True, **self.contents(name, limit=safe_limit)}, 200

    def compare_payload(self, name: str, rel_path: str):
        clean_path = normalize_text(rel_path)
        if not clean_path:
            return {"ok": False, "error": "path is required"}, 400
        return {"ok": True, **self.compare_file(name, clean_path)}, 200

    def restore_payload(self, data: Dict[str, Any], context_meta: Callable[..., Dict[str, Any]]):
        result = self.restore_paths(
            normalize_text(data.get("backup")),
            data.get("paths") or [],
            normalize_text(data.get("mode"), "staging"),
            normalize_text(data.get("confirm")),
        )
        return {"ok": True, **result, "context": context_meta("backup")}, 200

    def payload(self):
        settings = self.settings()
        return {
            "ok": True,
            "settings": settings,
            "timer": self.parse_timer_file(),
            "backups": self.archives(),
            "staging_root": str(self.restore_staging_root),
            "backup_root": str(self.backup_root),
            "plan": self.backup_plan(settings),
            "activity": self.activity(),
            "ai_shutdown_guard": self.ai_shutdown_guard(),
        }

    def lock_is_held(self, path: Path):
        try:
            self.backup_root.mkdir(parents=True, exist_ok=True)
            with path.open("a+", encoding="utf-8") as handle:
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

    def read_json_file(self, path: Path):
        try:
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            return data if isinstance(data, dict) else {"value": data}
        except Exception as exc:
            return {"error": str(exc), "path": str(path)}

    def ai_shutdown_guard(self):
        state = self.read_json_file(self.ai_backup_state_file)
        deferred = self.read_json_file(self.ai_shutdown_request_file)
        return {
            "backup_running": self.lock_is_held(self.ai_backup_lock_file),
            "state": state,
            "deferred_shutdown": deferred,
            "lock_file": str(self.ai_backup_lock_file),
            "state_file": str(self.ai_backup_state_file),
            "deferred_shutdown_file": str(self.ai_shutdown_request_file),
        }

    def activity(self, max_lines: int = 300):
        log_file = self.backup_root / "backup.log"
        markers = {
            "latest_backup": ["== Backup kész:", "== Backup kész restic nélkül:"],
            "latest_restic_backup": ["-- Restic backup:", "snapshot "],
            "latest_restic_check": ["== Restic check kész ==", "== Restic check indul:"],
            "latest_gitea_sync": ["-- Gitea config snapshot sync kész", "Config sync kész", "Nincs változás, push kihagyva"],
            "latest_gitea_dump": ["-- Gitea dump kész", "Gitea dump kész:", "-- Gitea dump nem futott le"],
            "latest_weekly": ["== Weekly AI HDD backup kész ==", "== Weekly AI HDD backup indul =="],
            "latest_error": ["HIBA:"],
        }
        result = {
            key: None for key in markers
        }
        result["log_file"] = str(log_file)
        result["recent"] = []
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
        except Exception as exc:
            result["error"] = str(exc)
            return result

        result["recent"] = lines[-12:]
        for line in reversed(lines):
            for key, needles in markers.items():
                if result[key] is not None:
                    continue
                if any(needle in line for needle in needles):
                    result[key] = line
        error_ts = self.log_line_timestamp(result.get("latest_error"))
        if error_ts:
            recovery_lines = [
                result.get("latest_backup"),
                result.get("latest_restic_check"),
            ]
            recovery_ts = [self.log_line_timestamp(line) for line in recovery_lines]
            latest_recovery = max([item for item in recovery_ts if item], default=None)
            if latest_recovery and latest_recovery > error_ts:
                result["latest_error_cleared_by"] = latest_recovery.isoformat()
                result["latest_error"] = None
        return result

    @staticmethod
    def log_line_timestamp(line: Optional[str]):
        if not line or not line.startswith("["):
            return None
        end = line.find("]")
        if end <= 1:
            return None
        try:
            return datetime.strptime(line[1:end], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def backup_plan(self, settings: Optional[Dict[str, Any]] = None):
        settings = settings or self.settings()
        git_paths = settings.get("git_paths") or []
        restic_paths = settings.get("restic_paths") or []
        return {
            "git": {
                "enabled": bool(settings.get("git_enabled")),
                "target": settings.get("gitea_url"),
                "repository": settings.get("git_repository"),
                "offsite": {
                    "enabled": bool(settings.get("git_offsite_enabled")),
                    "remote": settings.get("git_offsite_remote"),
                    "branch": settings.get("git_offsite_branch"),
                    "token_file": settings.get("git_offsite_token_file"),
                    "ssh_key": settings.get("git_offsite_ssh_key"),
                },
                "paths": git_paths,
                "remote": {
                    "host": settings.get("ai_backup_host"),
                    "user": settings.get("ai_backup_user"),
                    "mount": settings.get("ai_backup_mount"),
                },
                "covers": [
                    "Home Assistant konfiguraciok",
                    "automatizmusok es scriptek",
                    "docker-compose fajlok",
                    "kezzel szerkesztett HomeControl kod/config",
                ],
            },
            "restic": {
                "enabled": bool(settings.get("restic_enabled")),
                "repository": settings.get("restic_repository"),
                "password_file": settings.get("restic_password_file"),
                "ssh_key": settings.get("ai_backup_ssh_key"),
                "paths": restic_paths,
                "remote": {
                    "host": settings.get("ai_backup_host"),
                    "user": settings.get("ai_backup_user"),
                    "mount": settings.get("ai_backup_mount"),
                    "required_dirs": [
                        f"{settings.get('ai_backup_mount')}/restic/homecontrol",
                        f"{settings.get('ai_backup_mount')}/database",
                        f"{settings.get('ai_backup_mount')}/config",
                        f"{settings.get('ai_backup_mount')}/files",
                    ],
                },
                "mode": "daily best-effort; weekly required when AI weekly timer runs",
                "weekly": {
                    "enabled": bool(settings.get("ai_weekly_backup_enabled")),
                    "schedule": settings.get("ai_weekly_backup_schedule"),
                    "wakes_ai_server": True,
                    "shutdown_after": bool(settings.get("ai_weekly_shutdown_after")),
                },
                "retention": {
                    "daily": settings.get("restic_keep_daily"),
                    "weekly": settings.get("restic_keep_weekly"),
                    "monthly": settings.get("restic_keep_monthly"),
                },
                "covers": [
                    "teljes Home Assistant mappa",
                    "PostgreSQL dumpok es adatbazis allapot",
                    "Docker volume-ok",
                    "mediafajlok",
                    "AI szerver HDD-re erkezo HC snapshotok",
                ],
            },
            "local_archive": {
                "enabled": True,
                "repository": str(self.backup_root),
                "retention_days": settings.get("retention_days"),
                "covers": [
                    key.replace("include_", "")
                    for key in [
                        "include_postgres",
                        "include_apps",
                        "include_infra",
                        "include_zigbee2mqtt",
                        "include_homeassistant",
                        "include_scripts",
                        "include_docker_meta",
                    ]
                    if settings.get(key)
                ],
            },
        }

    @staticmethod
    def strip_root(member_name: str):
        parts = Path(member_name).parts
        if len(parts) <= 1:
            return ""
        return "/".join(parts[1:])

    @staticmethod
    def is_probably_text(data: bytes):
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False

    @staticmethod
    def text_diff_rows(current_text: str, backup_text: str):
        import difflib

        current_lines = current_text.splitlines()
        backup_lines = backup_text.splitlines()
        matcher = difflib.SequenceMatcher(a=current_lines, b=backup_lines)
        rows = []
        current_no = 1
        backup_no = 1
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for offset in range(i2 - i1):
                    rows.append(
                        {
                            "type": "same",
                            "current_line": current_no,
                            "backup_line": backup_no,
                            "current": current_lines[i1 + offset],
                            "backup": backup_lines[j1 + offset],
                        }
                    )
                    current_no += 1
                    backup_no += 1
            elif tag == "replace":
                count = max(i2 - i1, j2 - j1)
                for offset in range(count):
                    has_current = i1 + offset < i2
                    has_backup = j1 + offset < j2
                    rows.append(
                        {
                            "type": "changed",
                            "current_line": current_no if has_current else None,
                            "backup_line": backup_no if has_backup else None,
                            "current": current_lines[i1 + offset] if has_current else "",
                            "backup": backup_lines[j1 + offset] if has_backup else "",
                        }
                    )
                    if has_current:
                        current_no += 1
                    if has_backup:
                        backup_no += 1
            elif tag == "delete":
                for line in current_lines[i1:i2]:
                    rows.append({"type": "removed", "current_line": current_no, "backup_line": None, "current": line, "backup": ""})
                    current_no += 1
            elif tag == "insert":
                for line in backup_lines[j1:j2]:
                    rows.append({"type": "added", "current_line": None, "backup_line": backup_no, "current": "", "backup": line})
                    backup_no += 1
        return rows

    def should_skip_path(self, path: Path):
        text = str(path)
        skip_parts = {
            "postgres/data",
            "mqtt/data",
            "mqtt/log",
            "zigbee2mqtt/data/log",
            "tuya-poller/logs",
            "__pycache__",
        }
        return any(part in text for part in skip_parts)

    def add_directory_to_tar(self, archive: tarfile.TarFile, source: Path, arcname: str):
        if not source.exists():
            return
        for item in source.rglob("*"):
            if self.should_skip_path(item):
                continue
            archive.add(item, arcname=str(Path(arcname) / item.relative_to(source)), recursive=False)

    def docker_meta_files(self):
        return {
            "docker_ps_a.json": self.docker_socket_request("GET", "/containers/json?all=1")[0],
            "docker_images.json": self.docker_socket_request("GET", "/images/json")[0],
            "docker_version.json": self.docker_socket_request("GET", "/version")[0],
        }

    def restore_destination_for(self, rel_path: str):
        if rel_path.startswith("zigbee2mqtt/data/"):
            return self.restore_targets["zigbee2mqtt/data"] / rel_path.removeprefix("zigbee2mqtt/data/")
        top = rel_path.split("/", 1)[0]
        if top not in self.restore_targets:
            return None
        rest = rel_path.split("/", 1)[1] if "/" in rel_path else ""
        return self.restore_targets[top] / rest

    def restore_root_for(self, rel_path: str):
        if rel_path.startswith("zigbee2mqtt/data/"):
            return self.restore_targets["zigbee2mqtt/data"]
        top = rel_path.split("/", 1)[0]
        return self.restore_targets.get(top)

    @staticmethod
    def selected_restore_paths(member_rel: str, selected: Iterable[str]):
        selections = [item.strip().strip("/") for item in selected if item and item.strip()]
        if not selections:
            return False
        return any(member_rel == item or member_rel.startswith(f"{item}/") for item in selections)
