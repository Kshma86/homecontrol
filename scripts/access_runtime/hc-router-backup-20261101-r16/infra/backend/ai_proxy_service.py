import ai_domain_replies as hc_replies
import inspect
from ai_context_plan import context_sections
from worker_runtime import BoundedJobs, Busy
from concurrent.futures import TimeoutError as JobTimeout
import copy
from ai_images import validate_images
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class AiKnowledgeLoader:
    DEFAULT_MAX_CHARS = 26000
    CACHE_TTL_SEC = 30
    BASE_FILES = [
        "README.md",
        "module-map.md",
        "homecontrol-agent-guide.md",
    ]
    MODULES = {
        "irrigation": {
            "files": ["irrigation-domain.md", "irrigation-scenarios.md"],
            "keywords": ["irrigation", "öntöz", "ontoz", "locsol", "csöpögtet", "csopogtet", "szelep", "valve", "pumpa", "rain", "eső", "eso", "moisture", "talaj", "pilot", "navigator", "active rule", "active rules"],
        },
        "solar": {
            "files": ["solar-domain.md", "solar-scenarios.md"],
            "keywords": ["solar", "napelem", "growatt", "inverter", "termelés", "termeles", "pv"],
        },
        "x10": {
            "files": ["x10-domain.md", "x10-scenarios.md"],
            "keywords": ["x10", "xiaomi", "robot", "porszívó", "porszivo", "vacuum", "room clean", "térkép", "terkep"],
        },
        "climate": {
            "files": ["climate-domain.md", "climate-scenarios.md"],
            "keywords": ["climate", "klíma", "klima", "gree", "hűt", "hut", "fűt", "fut", "hőmér", "homersek", "fan", "temperature"],
        },
        "power_wall": {
            "files": ["power-wall-domain.md", "power-wall-scenarios.md"],
            "keywords": ["power wall", "power-wall", "konnektor", "plug", "smart plug", "always on", "always-on", "auto climate", "fogyasztás", "fogyasztas", "hc szerver", "homecontrol szerver"],
        },
        "tuya": {
            "files": ["tuya-domain.md", "tuya-scenarios.md"],
            "keywords": ["tuya", "dps", "switch", "kapcsoló", "kapcsolo"],
        },
        "performance": {
            "files": ["performance-domain.md", "performance-scenarios.md"],
            "keywords": ["performance", "teljesítmény", "teljesitmeny", "docker", "postgres", "cpu", "memory", "memória", "memoria", "mqtt", "worker", "health", "hc szerver", "homecontrol szerver"],
        },
        "scheduler": {
            "files": ["scheduler-domain.md", "scheduler-scenarios.md"],
            "keywords": ["scheduler", "ütemez", "utemez", "schedule", "v2", "event", "plan", "execution", "preflight", "shadow", "active rule", "active rules", "rule_engine"],
        },
        "backup": {
            "files": ["backup-domain.md", "backup-scenarios.md"],
            "keywords": ["backup", "mentés", "mentes", "restore", "visszaáll", "visszaall", "archive", "tar"],
        },
        "notes_admin": {
            "files": ["notes-admin-domain.md", "notes-admin-scenarios.md"],
            "keywords": ["notes", "jegyzet", "admin", "metric", "device", "entity", "opening", "ablak", "ajtó", "ajto"],
        },
        "ai": {
            "files": ["ai-domain.md", "ai-scenarios.md"],
            "keywords": ["ai", "ollama", "model", "prompt", "chat", "node", "openwebui", "gpu", "context layer", "context-layer", "ai kérés", "ai keres", "kérések", "keresek", "audit", "skill"],
        },
    }

    def __init__(self, docs_dir: Optional[Path] = None, max_chars: Optional[int] = None):
        self.docs_dir = Path(docs_dir) if docs_dir else self.default_docs_dir()
        self.max_chars = int(max_chars or self.DEFAULT_MAX_CHARS)
        self._cache: Dict[str, Any] = {"expires_at": 0.0, "files": {}}
        self._lock = threading.Lock()

    @staticmethod
    def default_docs_dir() -> Path:
        env_dir = os.environ.get("HC_AI_DOCS_DIR", "").strip()
        if env_dir:
            return Path(env_dir)
        current_path = Path(__file__).resolve()
        candidates = [
            Path("/srv/docker/homecontrol/docs/ai"),
            Path("/docs/ai"),
        ]
        for parent in current_path.parents:
            candidates.append(parent / "docs" / "ai")
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def build(self, message: str, history: Iterable[Any] = (), trace: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        text = self._routing_text(message, history)
        modules = self.route_modules(text)
        file_groups = [("base", self.BASE_FILES)] + [(module, self.MODULES[module]["files"]) for module in modules]
        files = [filename for _, group_files in file_groups for filename in group_files]
        planned_files = list(dict.fromkeys(files))
        docs = []
        used_files = []
        seen_files = set()
        skill_timings = []
        remaining = self.max_chars
        for skill, group_files in file_groups:
            skill_started_at = _utc_now()
            skill_started = time.perf_counter()
            skill_files = []
            skill_chars = 0
            skill_truncated = False
            if remaining <= 0:
                skill_timings.append(
                    {
                        "skill": skill,
                        "started_at": skill_started_at,
                        "duration_ms": 0,
                        "files": skill_files,
                        "chars": skill_chars,
                        "truncated": True,
                    }
                )
                continue
            for filename in group_files:
                if filename in seen_files:
                    continue
                seen_files.add(filename)
                content = self.read_file(filename).strip()
                if not content:
                    continue
                header = f"\n\n--- docs/ai/{filename} ---\n"
                chunk = header + content
                if len(chunk) > remaining:
                    if remaining < len(header) + 400:
                        skill_truncated = True
                        break
                    chunk = header + content[: max(0, remaining - len(header))] + "\n\n[truncated by AI knowledge budget]"
                    skill_truncated = True
                docs.append(chunk)
                used_files.append(filename)
                skill_files.append(filename)
                skill_chars += len(chunk)
                remaining -= len(chunk)
                if remaining <= 0:
                    skill_truncated = True
                    break
            if skill_files or skill == "base" or skill in modules:
                skill_timings.append(
                    {
                        "skill": skill,
                        "started_at": skill_started_at,
                        "duration_ms": round((time.perf_counter() - skill_started) * 1000, 1),
                        "files": skill_files,
                        "chars": skill_chars,
                        "truncated": skill_truncated,
                    }
                )
        if trace is not None:
            trace.extend(skill_timings)
        return {
            "enabled": True,
            "version": "homecontrol-ai-context.v1",
            "selected_modules": modules,
            "files": planned_files,
            "included_files": used_files,
            "max_chars": self.max_chars,
            "truncated": remaining <= 0,
            "skill_timings": skill_timings,
            "content": "".join(docs).strip(),
        }

    def route_modules(self, text: str) -> List[str]:
        selected = []
        lowered = text.lower()
        for module, spec in self.MODULES.items():
            if any(keyword in lowered for keyword in spec["keywords"]):
                selected.append(module)
        if any(word in lowered for word in ["minden", "összes", "osszes", "homecontrol", "hc rendszer", "modul"]):
            for module in ["scheduler", "performance"]:
                if module not in selected:
                    selected.append(module)
        return selected[:4]

    @staticmethod
    def _routing_text(message: str, history: Iterable[Any]) -> str:
        parts = [str(message or "")]
        for item in list(history or [])[-4:]:
            if isinstance(item, dict):
                parts.append(str(item.get("content") or item.get("message") or ""))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    def read_file(self, filename: str) -> str:
        path = (self.docs_dir / filename).resolve()
        try:
            if path.parent != self.docs_dir.resolve():
                return ""
            stat = path.stat()
        except OSError:
            return ""
        now = time.monotonic()
        cache_key = str(path)
        with self._lock:
            cached = self._cache["files"].get(cache_key)
            if cached and cached.get("mtime") == stat.st_mtime and self._cache["expires_at"] > now:
                return cached.get("content") or ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        with self._lock:
            self._cache["files"][cache_key] = {"mtime": stat.st_mtime, "content": content}
            self._cache["expires_at"] = time.monotonic() + self.CACHE_TTL_SEC
        return content

    def clear_cache(self) -> None:
        with self._lock:
            self._cache = {"expires_at": 0.0, "files": {}}


class AiProxyService:
    HISTORY_CONTEXT_WINDOW = 20

    def __init__(
        self,
        server_url: str,
        timeout: float,
        *,
        context_summary: Callable[..., Dict[str, Any]],
        json_ready: Callable[[Any], Any],
        urlopen_func: Callable[..., Any] = urlopen,
        knowledge_loader: Optional[AiKnowledgeLoader] = None,
        audit_logger: Optional[Callable[[Dict[str, Any]], Any]] = None,
        db_query_count: Optional[Callable[[], Optional[int]]] = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.context_summary = context_summary
        self.json_ready = json_ready
        self.urlopen = urlopen_func
        self.knowledge_loader = knowledge_loader or AiKnowledgeLoader()
        self.audit_logger = audit_logger
        self.db_query_count = db_query_count or (lambda: None)
        self._chat_jobs = BoundedJobs("ai-chat", 1)
        self._transport_jobs = BoundedJobs("ai-transport", 1)
        self._request_deadline = threading.local()
        self._status_cache = None
        self._status_cache_at = 0.0
        self._status_cache_lock = threading.Lock()
        self._status_cache_ttl = max(5.0, float(os.getenv("AI_STATUS_CACHE_TTL", "30")))

    def status(self, force: bool = False) -> Tuple[Dict[str, Any], int]:
        from deployment_policy import ai_disabled, unavailable
        if ai_disabled():
            return unavailable(), 503
        current = time.monotonic()
        with self._status_cache_lock:
            if not force and self._status_cache is not None and current - self._status_cache_at < self._status_cache_ttl:
                payload, status = self._status_cache
                return copy.deepcopy(payload), status
            payload, status = self._proxy("/health", success_status=200)
            self._status_cache = (copy.deepcopy(payload), status)
            self._status_cache_at = current
            return payload, status

    def clear_status_cache(self) -> None:
        with self._status_cache_lock:
            self._status_cache = None
            self._status_cache_at = 0.0

    def chat(self, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        deadline = time.monotonic() + self.timeout
        try:
            from flask import has_request_context, copy_current_request_context
            callback = lambda: self._chat_with_deadline(body, deadline)
            if has_request_context():
                callback = copy_current_request_context(callback)
            future = self._chat_jobs.submit(callback)
            return future.result(timeout=max(.001, deadline-time.monotonic()))
        except Busy:
            return {"ok": False, "code": "capacity_exhausted", "error": "AI request already running"}, 503
        except JobTimeout:
            return {"ok": False, "code": "deadline_exceeded", "error": "AI total request deadline exceeded"}, 504

    def _chat_with_deadline(self, body, deadline):
        self._request_deadline.value = deadline
        try:
            return self._chat(body)
        finally:
            self._request_deadline.value = None

    def worker_status(self):
        return {**self._chat_jobs.status(), 'transport': self._transport_jobs.status()}

    def stop_worker(self, timeout=0):
        deadline = time.monotonic() + max(0, timeout)
        chat_stopped = self._chat_jobs.stop(timeout)
        transport_stopped = self._transport_jobs.stop(max(0, deadline-time.monotonic()))
        return chat_stopped and transport_stopped

    def _chat(self, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        message = str(body.get("message") or "").strip()
        try:
            images = validate_images(body.get("images"))
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}, 400
        if not message and not images:
            return {"ok": False, "error": "message is required"}, 400
        started_at = _utc_now()
        started = time.perf_counter()
        context_ms = None
        knowledge_ms = None
        model_ms = None
        context_trace: List[Dict[str, Any]] = []
        skill_trace: List[Dict[str, Any]] = []
        knowledge_docs: Dict[str, Any] = {}
        response_payload: Dict[str, Any] = {}
        response_status = 500
        source = "unknown"
        sections = []
        history = body.get("history") if isinstance(body.get("history"), list) else []
        try:
            context_started = time.perf_counter()
            sections = context_sections(message, history, images=bool(images))
            context = self.json_ready(self._context_summary_with_trace(context_trace, sections))
            context_ms = round((time.perf_counter() - context_started) * 1000, 1)
            knowledge_started = time.perf_counter()
            knowledge_docs = self.knowledge_loader.build(message, history, trace=skill_trace)
            knowledge_ms = round((time.perf_counter() - knowledge_started) * 1000, 1)
            context["knowledge_docs"] = knowledge_docs
            direct_reply = None if images else self.direct_context_reply(message, context, history)
            if direct_reply:
                source = "direct_context_reply"
                response_payload = {
                    "ok": True,
                    "reply": direct_reply,
                    "provider": "hc_context",
                    "model": "deterministic",
                    "context": {
                        "schema_version": context.get("schema_version"),
                        "generated_at": context.get("generated_at"),
                        "ok": context.get("ok"),
                    },
                }
                response_status = 200
                return response_payload, response_status
            payload = {"message": message, "history": history[-self.HISTORY_CONTEXT_WINDOW:], "context": context}
            if images:
                payload["images"] = images
            model_started = time.perf_counter()
            data, status = self._proxy("/chat", payload, method="POST", success_status=200, failure_status=502)
            model_ms = round((time.perf_counter() - model_started) * 1000, 1)
            source = "ai_server"
            if status < 400:
                if isinstance(data.get("reply"), str):
                    data["reply"] = self.clean_reply_text(data["reply"])
                data.setdefault(
                    "context",
                    {
                        "schema_version": context.get("schema_version"),
                        "generated_at": context.get("generated_at"),
                        "ok": context.get("ok"),
                    },
                )
                response_payload = data
                response_status = 200 if data.get("ok") else 502
                return response_payload, response_status
            response_payload = data
            response_status = status
            return response_payload, response_status
        finally:
            deadline = getattr(self._request_deadline, 'value', None)
            if deadline is not None and time.monotonic() >= deadline:
                # A late job must not audit a successful response after its
                # HTTP caller already received the total-deadline failure.
                response_status = 504
                response_payload = {"ok": False, "error": "AI total request deadline exceeded"}
                source = "deadline_exceeded"
            self._log_chat_audit(
                {
                    "started_at": started_at,
                    "question": message,
                    "answer": response_payload.get("reply"),
                    "provider": response_payload.get("provider"),
                    "model": response_payload.get("model"),
                    "status_code": response_status,
                    "ok": bool(response_payload.get("ok")),
                    "error": response_payload.get("error"),
                    "source": source,
                    "total_ms": round((time.perf_counter() - started) * 1000, 1),
                    "context_ms": context_ms,
                    "knowledge_ms": knowledge_ms,
                    "model_ms": model_ms,
                    "db_query_count": self.db_query_count(),
                    "skills": knowledge_docs.get("selected_modules", []),
                    "data_sources": self._audit_data_sources(context_trace, knowledge_docs),
                    "skill_timings": skill_trace,
                    "context_timings": context_trace,
                    "upstream": {
                        "server_url": self.server_url,
                        "history_count": len(history),
                        "history_sent_count": min(len(history), self.HISTORY_CONTEXT_WINDOW),
                        "knowledge_truncated": knowledge_docs.get("truncated"),
                    },
                    "request_meta": {
                        "context_sections": sections,
                        "knowledge_version": knowledge_docs.get("version"),
                        "knowledge_max_chars": knowledge_docs.get("max_chars"),
                    },
                }
            )

    def _context_summary_with_trace(self, trace, sections):
        parameters = inspect.signature(self.context_summary).parameters
        any_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())
        kwargs = {}
        if 'trace' in parameters or any_kwargs:
            kwargs['trace'] = trace
        if 'sections' in parameters or any_kwargs:
            kwargs['sections'] = sections
        return self.context_summary(**kwargs)

    @staticmethod
    def _audit_data_sources(context_trace: List[Dict[str, Any]], knowledge_docs: Dict[str, Any]) -> List[Dict[str, Any]]:
        sources = [
            {
                "type": "context_section",
                "name": item.get("section"),
                "cache_hit": item.get("cache_hit"),
                "ok": item.get("ok"),
            }
            for item in context_trace
            if item.get("section")
        ]
        sources.extend(
            {"type": "knowledge_doc", "name": filename}
            for filename in knowledge_docs.get("files", [])
        )
        return sources

    def _log_chat_audit(self, row: Dict[str, Any]) -> None:
        if not self.audit_logger:
            return
        try:
            self.audit_logger(row)
        except Exception:
            pass

    @staticmethod
    def clean_reply_text(text: str) -> str:
        value = str(text or "")
        value = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL)
        if re.search(r"</think>", value, flags=re.IGNORECASE):
            value = re.split(r"</think>", value, flags=re.IGNORECASE)[-1]
        value = re.sub(r"</?think>", "", value, flags=re.IGNORECASE)
        value = re.sub(
            r"(?is)^\s*(okay|alright|let me|we need|i need|first,|looking at|hmm,|so the answer).*?(?=\n\s*(a |az |ma |mai |röviden|osszefoglal|összefoglal))",
            "",
            value,
        )
        return value.strip()

    def config(self) -> Tuple[Dict[str, Any], int]:
        data, status = self._proxy("/config", success_status=200, failure_status=502)
        if status < 400:
            return data, 200 if data.get("ok") else 502
        return data, status

    def save_config(self, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        data, status = self._proxy("/config", body, method="POST", success_status=200, failure_status=502)
        if status < 400:
            return data, 200 if data.get("ok") else 502
        return data, status

    def models(self) -> Tuple[Dict[str, Any], int]:
        data, status = self._proxy("/models", success_status=200)
        if status == 502:
            data.setdefault("local_models", [])
            data.setdefault("recommended_models", [])
        return data, status

    def pull_model(self, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        model = str(body.get("model") or "").strip()
        if not model:
            return {"ok": False, "error": "model is required"}, 400
        data, status = self._proxy("/models/pull", {"model": model}, method="POST", success_status=202, failure_status=502)
        if status < 400:
            return data, 202 if data.get("ok") else 502
        return data, status

    def pull_status(self) -> Tuple[Dict[str, Any], int]:
        data, status = self._proxy("/models/pull/status", success_status=200, failure_status=502)
        if status < 400:
            return data, 200 if data.get("ok") else 502
        return data, status

    def clear_knowledge_cache(self) -> None:
        self.knowledge_loader.clear_cache()

    @staticmethod
    def direct_context_reply(message: str, context: Dict[str, Any], history: Iterable[Any] = ()) -> str:
        return hc_replies.direct_context_reply(message, context, history)

    @staticmethod
    def ai_audit_analysis_reply(context: Dict[str, Any]) -> str:
        return hc_replies.ai_audit_analysis_reply(context)

    def request(self, path: str, payload: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, Any]:
        from deployment_policy import ai_disabled, MESSAGE
        if ai_disabled():
            raise OSError(MESSAGE)
        url = f"{self.server_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        deadline = getattr(self._request_deadline, 'value', None)
        remaining = self.timeout if deadline is None else deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('AI total request deadline exceeded')
        with self.urlopen(req, timeout=remaining) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")

    def _proxy(
        self,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        method: str = "GET",
        success_status: int = 200,
        failure_status: int = 502,
    ) -> Tuple[Dict[str, Any], int]:
        try:
            deadline = getattr(self._request_deadline, 'value', None)
            if deadline is None:
                deadline = time.monotonic() + self.timeout
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise JobTimeout()
            def transport():
                self._request_deadline.value = deadline
                try:
                    return self.request(path, payload, method=method)
                finally:
                    self._request_deadline.value = None
            data = self._transport_jobs.submit(transport).result(timeout=remaining)
            return data, success_status
        except Busy:
            return {"ok": False, "code": "capacity_exhausted", "error": "AI transport already running"}, 503
        except JobTimeout:
            return {"ok": False, "code": "deadline_exceeded", "error": "AI total request deadline exceeded"}, 504
        except HTTPError as exc:
            return self.http_error_payload(exc), exc.code
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"AI server unavailable: {exc}", "server_url": self.server_url}, failure_status

    def http_error_payload(self, exc: HTTPError) -> Dict[str, Any]:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
        except Exception:
            payload = {"ok": False, "error": str(exc)}
        payload.setdefault("server_url", self.server_url)
        return payload
