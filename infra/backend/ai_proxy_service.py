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
    HISTORY_CONTEXT_WINDOW = 10

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

    def status(self) -> Tuple[Dict[str, Any], int]:
        return self._proxy("/health", success_status=200)

    def chat(self, body: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        message = str(body.get("message") or "").strip()
        if not message:
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
        history = body.get("history") if isinstance(body.get("history"), list) else []
        try:
            context_started = time.perf_counter()
            context = self.json_ready(self._context_summary_with_trace(context_trace))
            context_ms = round((time.perf_counter() - context_started) * 1000, 1)
            knowledge_started = time.perf_counter()
            knowledge_docs = self.knowledge_loader.build(message, history, trace=skill_trace)
            knowledge_ms = round((time.perf_counter() - knowledge_started) * 1000, 1)
            context["knowledge_docs"] = knowledge_docs
            direct_reply = self.direct_context_reply(message, context, history)
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
                        "knowledge_version": knowledge_docs.get("version"),
                        "knowledge_max_chars": knowledge_docs.get("max_chars"),
                    },
                }
            )

    def _context_summary_with_trace(self, trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return self.context_summary(trace=trace)
        except TypeError:
            return self.context_summary()

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
        text = str(message or "").strip().lower()
        combined = AiKnowledgeLoader._routing_text(message, history).lower()
        asks_ai_audit = any(word in combined for word in ["ai kérés", "ai keres", "ai kérések", "ai keresek", "chat audit", "ai audit"]) and any(
            word in combined for word in ["elemez", "analiz", "trend", "context layer", "context-layer", "fejleszt"]
        )
        if asks_ai_audit:
            return AiProxyService.ai_audit_analysis_reply(context)
        asks_climate_power = any(word in text for word in ["klím", "klima", "gree", "climate"]) and any(
            word in text for word in ["fogyaszt", "teljesítmény", "teljesitmeny", "watt", "kwh", "energia", "áram", "aram"]
        )
        if asks_climate_power:
            climate_power = context.get("climate_power") if isinstance(context.get("climate_power"), dict) else {}
            if not climate_power or climate_power.get("ok") is False:
                return f"A klíma fogyasztásmérő adata nem elérhető az AI contextben: {climate_power.get('error') or 'nincs climate_power adat'}."
            meter = climate_power.get("meter") if isinstance(climate_power.get("meter"), dict) else {}
            name = meter.get("entity_name") or meter.get("device_name") or "Gree klíma"
            if any(word in text for word in ["hónap", "honap"]):
                energy = climate_power.get("month_energy_kwh")
                days = climate_power.get("month_days")
                avg_daily = round(float(energy) / float(days), 3) if energy is not None and days else None
                return (
                    "A klíma havi fogyasztását a climate_power blokk alapján számolom, nem a HC szerver fogyasztásmérőjéből. "
                    f"Az aktuális hónap eddigi mért fogyasztása {energy if energy is not None else '-'} kWh "
                    f"({days if days is not None else 0} napi sor alapján). "
                    f"Ez napi átlagban {avg_daily if avg_daily is not None else '-'} kWh/nap. "
                    f"Mai eddigi fogyasztás: {climate_power.get('today_energy_kwh', '-')} kWh, "
                    f"aktuális teljesítmény: {climate_power.get('current_power_w', '-')} W, mérő: {name}."
                )
            return (
                f"A klíma fogyasztásmérője: {name}. "
                f"Mai eddigi fogyasztás {climate_power.get('today_energy_kwh', '-')} kWh, "
                f"aktuális teljesítmény {climate_power.get('current_power_w', '-')} W, "
                f"utolsó 30 nap {climate_power.get('energy_kwh_30d', '-')} kWh. "
                "Ez climate_power adat, nem HC szerver/server_power adat."
            )
        asks_settings = any(word in text for word in ["beállítás", "beallitas", "paraméter", "parameter", "mód", "mod", "target", "célhő", "celho", "venti", "fan", "általában", "altalaban", "használva", "hasznalva"])
        climate_context = any(word in combined for word in ["klím", "klima", "gree", "climate", "climate_power"])
        if asks_settings and climate_context:
            climate = context.get("climate") if isinstance(context.get("climate"), dict) else {}
            climate_history = context.get("climate_history") if isinstance(context.get("climate_history"), dict) else {}
            schedules = context.get("climate_schedules") if isinstance(context.get("climate_schedules"), dict) else {}
            enabled = schedules.get("enabled_schedules") if isinstance(schedules.get("enabled_schedules"), list) else []
            lines = [
                (
                    f"Aktuális állapot: power={climate.get('power') or '-'}, mód={climate.get('mode') or '-'}, "
                    f"célhő={climate.get('target_temperature') if climate.get('target_temperature') is not None else '-'} °C, "
                    f"fan={climate.get('fan_speed') or '-'}, "
                    f"aktuális hőmérséklet={climate.get('current_temperature') if climate.get('current_temperature') is not None else '-'} °C."
                ),
            ]
            if climate_history and climate_history.get("ok"):
                distributions = climate_history.get("distributions_7d") if isinstance(climate_history.get("distributions_7d"), dict) else {}
                numeric = climate_history.get("numeric_7d") if isinstance(climate_history.get("numeric_7d"), dict) else {}
                recent_changes = climate_history.get("recent_setting_changes_7d") if isinstance(climate_history.get("recent_setting_changes_7d"), list) else []
                lines.append("Historikus klíma paraméterek a climate_history blokkból:")
                for key, label in [
                    ("climate_power", "power"),
                    ("climate_mode", "mód"),
                    ("climate_fan_speed", "fan"),
                ]:
                    values = distributions.get(key) if isinstance(distributions.get(key), list) else []
                    if values:
                        lines.append(f"- {label} 7 napos minták: " + ", ".join(f"{item.get('value')} ({item.get('sample_count')})" for item in values[:4]))
                for key, label in [
                    ("climate_target_temperature", "célhő"),
                    ("climate_current_temperature", "mért hő"),
                ]:
                    item = numeric.get(key) if isinstance(numeric.get(key), dict) else {}
                    if item:
                        lines.append(f"- {label} 7 nap: átlag {item.get('avg')}, min {item.get('min')}, max {item.get('max')}, minták {item.get('sample_count')}")
                if recent_changes:
                    lines.append("Friss beállítás-változások: " + "; ".join(f"{item.get('key')}={item.get('value')}" for item in recent_changes[:6]))
            else:
                lines.append(f"Historikus klíma paraméter idősor még nem elérhető: {climate_history.get('error') or 'nincs climate_history adat'}.")
            if enabled:
                lines.append(f"Engedélyezett klíma schedule szabályok ({len(enabled)} db):")
                for row in enabled[:7]:
                    lines.append(
                        f"- {row.get('label') or row.get('id')}: nap={row.get('day_of_week')}, idő={row.get('start_time')}, "
                        f"power={row.get('power')}, mód={row.get('mode')}, célhő={row.get('target_temperature')} °C, "
                        f"fan={row.get('fan_speed')}, státusz={row.get('schedule_status') or '-'}"
                    )
            else:
                lines.append("Nem látok engedélyezett klíma schedule szabályt az AI contextben.")
            lines.append("Szobahőmérő adatból nem következtetek klíma beállításokra, mert az nem ugyanaz az adatforrás.")
            return "\n".join(lines)
        if asks_settings and not climate_context:
            return "Pontosan melyik modul beállításaira gondolsz? Például klíma, öntözés, X10 robot, solar vagy power wall. Modulnév nélkül nem következtetek, mert könnyen rossz adatforrásból válaszolnék."
        return ""

    @staticmethod
    def ai_audit_analysis_reply(context: Dict[str, Any]) -> str:
        audit = context.get("ai_chat_audit") if isinstance(context.get("ai_chat_audit"), dict) else {}
        if not audit or audit.get("ok") is False:
            return f"Az AI kérés audit adat nem elérhető az AI contextben: {audit.get('error') or 'nincs ai_chat_audit adat'}."
        sample_size = audit.get("sample_size") or 0
        success = audit.get("success") if isinstance(audit.get("success"), dict) else {}
        latency = audit.get("latency") if isinstance(audit.get("latency"), dict) else {}
        top_skills = audit.get("top_skills") if isinstance(audit.get("top_skills"), list) else []
        top_sources = audit.get("top_data_sources") if isinstance(audit.get("top_data_sources"), list) else []
        slow_context = audit.get("slow_context_sections") if isinstance(audit.get("slow_context_sections"), list) else []
        slow_skills = audit.get("slow_skills") if isinstance(audit.get("slow_skills"), list) else []
        recent_questions = audit.get("recent_questions") if isinstance(audit.get("recent_questions"), list) else []

        lines = [
            f"Az AI kérés audit alapján elemzek, nem emlékezetből. Minta: {sample_size} legutóbbi kérés.",
            (
                f"Sikeresség: {success.get('ok_rate_percent', '-')}% ok, "
                f"hibák: {success.get('error_count', '-')}. Átlag válaszidő: {latency.get('avg_total_ms', '-')} ms, "
                f"max: {latency.get('max_total_ms', '-')} ms, átlag DB lekérdezés: {latency.get('avg_db_query_count', '-')}."
            ),
        ]
        if top_skills:
            lines.append("Leggyakoribb skill útvonalak: " + ", ".join(f"{item.get('name')} ({item.get('count')})" for item in top_skills[:5]))
        if top_sources:
            lines.append("Leggyakrabban használt adatforrások: " + ", ".join(f"{item.get('name')} ({item.get('count')})" for item in top_sources[:5]))
        if slow_context:
            lines.append("Context-layer teljesítmény fókusz: " + ", ".join(f"{item.get('name')} avg {item.get('avg_ms')} ms" for item in slow_context[:5]))
        if slow_skills:
            lines.append("Knowledge/skill betöltési fókusz: " + ", ".join(f"{item.get('name')} avg {item.get('avg_ms')} ms" for item in slow_skills[:5]))
        if recent_questions:
            question_text = "; ".join(str(item.get("question") or "")[:80] for item in recent_questions[:5] if item.get("question"))
            if question_text:
                lines.append(f"Friss kérdésminták: {question_text}")
        lines.append(
            "Context-layer fejlesztési irány: a gyakori kérdésmintákhoz legyen explicit, kompakt context mező; a lassú szekciókat cache/SQL oldalról kell nézni; ahol sok a DB lekérdezés, ott érdemes aggregált read modelt adni az AI contextnek."
        )
        return "\n".join(lines)

    def request(self, path: str, payload: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, Any]:
        url = f"{self.server_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        with self.urlopen(req, timeout=self.timeout) as response:
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
            data = self.request(path, payload, method=method)
            return data, success_status
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
