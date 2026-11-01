from ai_images import validate_images, MAX_REQUEST_BYTES
import base64
import io
import json
from PIL import Image, ImageOps
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import ai_domain_replies as hc_replies
except ModuleNotFoundError as exc:
    if exc.name != 'ai_domain_replies':
        raise
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'infra/backend'))
    import ai_domain_replies as hc_replies
approximate_cycle_end = hc_replies.approximate_cycle_end
context_query_focus = hc_replies.context_query_focus
context_value = hc_replies.context_value
cycle_end = hc_replies.cycle_end
cycle_line = hc_replies.cycle_line
cycle_matches_date = hc_replies.cycle_matches_date
cycle_start = hc_replies.cycle_start
direct_context_reply = hc_replies.direct_context_reply
fallback_reply = hc_replies.fallback_reply
hu_trend = hc_replies.hu_trend
human_time = hc_replies.human_time
parse_time = hc_replies.parse_time
period_label = hc_replies.period_label
requested_period_key = hc_replies.requested_period_key
source_label = hc_replies.source_label
start_source_label = hc_replies.start_source_label
status_label = hc_replies.status_label
stop_source_label = hc_replies.stop_source_label
target_date_for_text = hc_replies.target_date_for_text
time_without_repeated_day = hc_replies.time_without_repeated_day


HOST = os.environ.get("AI_SERVER_HOST", "0.0.0.0")
PORT = int(os.environ.get("AI_SERVER_PORT", "8088"))
DEFAULT_PROVIDER = os.environ.get("AI_PROVIDER", "fallback").strip().lower()
DEFAULT_MODEL = os.environ.get("AI_MODEL", "homecontrol-foundation")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/")
DEFAULT_OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
DEFAULT_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REQUEST_TIMEOUT = float(os.environ.get("AI_REQUEST_TIMEOUT", "300"))
PROBE_TIMEOUT = float(os.environ.get("AI_PROBE_TIMEOUT", "1.5"))
CONFIG_PATH = os.environ.get("AI_CONFIG_PATH", "/data/config.json")
PROVIDERS = {"fallback", "ollama", "local_ollama", "remote_ollama", "openai_compatible"}
RECOMMENDED_MODELS = [
    {"name": "qwen3:0.6b", "label": "Qwen3 0.6B", "size": "523 MB", "note": "Connectivity smoke test, weak chat quality"},
    {"name": "qwen3:1.7b", "label": "Qwen3 1.7B", "size": "1.4 GB", "note": "Small default for first local chat tests"},
    {"name": "qwen3:4b", "label": "Qwen3 4B", "size": "2.5 GB", "note": "Good middle ground"},
    {"name": "qwen3:8b", "label": "Qwen3 8B", "size": "5.2 GB", "note": "Recommended first serious model"},
]
CONFIG_LOCK = threading.RLock()
PULL_LOCK = threading.RLock()
PULL_STATUS = {
    "running": False,
    "model": "",
    "status": "idle",
    "completed": 0,
    "total": 0,
    "error": "",
    "started_at": None,
    "finished_at": None,
}


def read_json(handler):
    length = int(handler.headers.get("Content-Length") or "0")
    if length > MAX_REQUEST_BYTES:
        raise ValueError("A kérés legfeljebb 17 MiB lehet.")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def write_json(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def friendly_provider_error(message):
    text = str(message or "")
    if any(part in text.lower() for part in ["ollama unavailable", "urlopen", "no route to host", "connection refused", "timed out"]):
        return "AI server unavailable"
    return text or "AI server unavailable"


def clean_reply_text(text):
    value = str(text or "")
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL)
    if re.search(r"</think>", value, flags=re.IGNORECASE):
        value = re.split(r"</think>", value, flags=re.IGNORECASE)[-1]
    value = re.sub(r"</?think>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?is)^\s*(okay|alright|let me|we need|i need|first,|looking at|hmm,|so the answer).*?(?=\n\s*(a |az |ma |mai |röviden|osszefoglal|összefoglal))", "", value)
    value = value.replace("**", "")
    value = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
































def request_json(url, payload=None, method="GET", timeout=None, headers=None):
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    return urlopen(request, timeout=timeout or REQUEST_TIMEOUT)


def ollama_json(path, payload=None, method="GET", timeout=None, ollama_url=None):
    return request_json(f"{(ollama_url or DEFAULT_OLLAMA_URL).rstrip('/')}{path}", payload, method, timeout)


def default_config():
    return {
        "provider": DEFAULT_PROVIDER if DEFAULT_PROVIDER in PROVIDERS else "fallback",
        "model": DEFAULT_MODEL,
        "ollama_url": DEFAULT_OLLAMA_URL,
        "openai_base_url": DEFAULT_OPENAI_BASE_URL,
        "openai_api_key": DEFAULT_OPENAI_API_KEY,
        "format": "",
        "temperature": 0.2,
        "num_ctx": 16384,
        "num_predict": 1536,
        "system_prompt": "Te vagy a HomeControl AI asszisztense. Mindig magyarul válaszolj. A HomeControl öntözés tartályos rendszer: a pumpa a tartályok töltésére szolgál, a csap/szelep indítja a csöpögtető rendszert. A pumpafutási idő és a locsolási/csöpögtetési idő nem ugyanaz, és nem feltétlenül mozognak együtt. Válaszolj érthetően, természetes mondatokban. Ne használj emojikat, markdown félkövért (**), túl sok címsort vagy díszítő elválasztókat. Ha elemzést kérnek, adhatsz hosszabb, tagolt választ, de maradj tárgyszerű és mindig fejezd be rövid összegzéssel. Ne találj ki szerverjogokat vagy eszközvezérlést; ha nincs HC adatod, mondd meg.",
    }


def normalize_config(data):
    current = default_config()
    if isinstance(data, dict):
        current.update({k: v for k, v in data.items() if k in current})
    current["format"] = "json" if current.get("format") == "json" else ""
    provider = str(current.get("provider") or "fallback").strip().lower()
    current["provider"] = provider if provider in PROVIDERS else "fallback"
    current["model"] = str(current.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    current["ollama_url"] = str(current.get("ollama_url") or DEFAULT_OLLAMA_URL).strip().rstrip("/") or DEFAULT_OLLAMA_URL
    current["openai_base_url"] = str(current.get("openai_base_url") or DEFAULT_OPENAI_BASE_URL).strip().rstrip("/") or DEFAULT_OPENAI_BASE_URL
    current["openai_api_key"] = str(current.get("openai_api_key") or "").strip()
    try:
        current["temperature"] = max(0, min(2, float(current.get("temperature", 0.2))))
    except (TypeError, ValueError):
        current["temperature"] = 0.2
    try:
        current["num_ctx"] = max(512, min(262144, int(current.get("num_ctx", 16384))))
    except (TypeError, ValueError):
        current["num_ctx"] = 16384
    try:
        current["num_predict"] = max(16, min(4096, int(current.get("num_predict", 1536))))
    except (TypeError, ValueError):
        current["num_predict"] = 1536
    current["system_prompt"] = str(current.get("system_prompt") or default_config()["system_prompt"]).strip()
    return current


def public_config(config):
    visible = dict(config)
    visible["openai_api_key"] = ""
    visible["openai_api_key_set"] = bool(config.get("openai_api_key"))
    return visible


def read_config():
    with CONFIG_LOCK:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                return normalize_config(json.load(handle))
        except FileNotFoundError:
            config = default_config()
            write_config(config)
            return config
        except (OSError, json.JSONDecodeError):
            return default_config()


def write_config(config):
    incoming = dict(config or {})
    current = read_config() if os.path.exists(CONFIG_PATH) else default_config()
    if "openai_api_key" in incoming and not str(incoming.get("openai_api_key") or "").strip():
        incoming["openai_api_key"] = current.get("openai_api_key", "")
    normalized = normalize_config({**current, **incoming})
    with CONFIG_LOCK:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp_path = f"{CONFIG_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIG_PATH)
    return normalized


def model_names(models):
    return {item.get("name") for item in models if item.get("name")}


def list_ollama_models(ollama_url=None, timeout=10):
    with ollama_json("/api/tags", timeout=timeout, ollama_url=ollama_url) as response:
        data = json.loads(response.read().decode("utf-8") or "{}")
    models = data.get("models") if isinstance(data.get("models"), list) else []
    return [
        {
            "name": item.get("name") or item.get("model") or "",
            "size": item.get("size"),
            "modified_at": item.get("modified_at"),
            "details": item.get("details") or {},
        }
        for item in models
        if item.get("name") or item.get("model")
    ]


def pull_worker(model, ollama_url):
    with PULL_LOCK:
        PULL_STATUS.update({
            "running": True,
            "model": model,
            "status": "starting",
            "completed": 0,
            "total": 0,
            "error": "",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "finished_at": None,
        })
    try:
        with ollama_json("/api/pull", {"model": model, "stream": True}, method="POST", timeout=3600, ollama_url=ollama_url) as response:
            for raw_line in response:
                if not raw_line:
                    continue
                try:
                    item = json.loads(raw_line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                with PULL_LOCK:
                    PULL_STATUS["status"] = item.get("status") or PULL_STATUS["status"]
                    if item.get("completed") is not None:
                        PULL_STATUS["completed"] = item.get("completed")
                    if item.get("total") is not None:
                        PULL_STATUS["total"] = item.get("total")
                    if item.get("error"):
                        PULL_STATUS["error"] = item.get("error")
        with PULL_LOCK:
            PULL_STATUS["running"] = False
            PULL_STATUS["status"] = "done" if not PULL_STATUS.get("error") else "failed"
            PULL_STATUS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception as exc:
        with PULL_LOCK:
            PULL_STATUS["running"] = False
            PULL_STATUS["status"] = "failed"
            PULL_STATUS["error"] = str(exc)
            PULL_STATUS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())




def compact_context_for_prompt(context, message=None):
    if not isinstance(context, dict):
        return ""
    irrigation = context.get("irrigation") if isinstance(context.get("irrigation"), dict) else {}
    allowed = {
        "schema_version": context.get("schema_version"),
        "generated_at": context.get("generated_at"),
        "user_query_focus": context_query_focus(context, message),
        "house": context.get("house"),
        "weather": context.get("weather"),
        "home_statistics": context.get("home_statistics"),
        "irrigation": {
            "analysis": irrigation.get("analysis"),
            "manual_valve_blocked": irrigation.get("manual_valve_blocked"),
            "manual_valve_state": irrigation.get("manual_valve_state"),
            "sessions": (irrigation.get("sessions") or [])[:3],
            "schedules": (irrigation.get("schedules") or [])[:7],
        },
        "irrigation_pilot": context.get("irrigation_pilot"),
        "climate": context.get("climate"),
        "climate_power": context.get("climate_power"),
        "climate_history": context.get("climate_history"),
        "climate_schedules": context.get("climate_schedules"),
        "robot": context.get("robot"),
        "power_wall": context.get("power_wall"),
        "solar": context.get("solar"),
        "server_power": context.get("server_power"),
        "tuya": context.get("tuya"),
        "scheduler": context.get("scheduler"),
        "backup": context.get("backup"),
        "open_notes": context.get("open_notes"),
        "errors": context.get("errors"),
    }
    return json.dumps(allowed, ensure_ascii=False, separators=(",", ":"), default=str)[:14000]


def context_system_message(context, message=None):
    compact = compact_context_for_prompt(context, message)
    knowledge = context.get("knowledge_docs") if isinstance(context, dict) and isinstance(context.get("knowledge_docs"), dict) else {}
    knowledge_text = str(knowledge.get("content") or "").strip()
    if not compact and not knowledge_text:
        return ""
    knowledge_intro = ""
    if knowledge_text:
        selected = ", ".join(knowledge.get("selected_modules") or []) or "global"
        knowledge_intro = (
            "HomeControl modul-tudásbázis következik. "
            "Ezeket tekintsd irányadó domain-szabályoknak, de aktuális állapotkérdésnél a JSON context a frissebb adatforrás. "
            "Ne találj ki üzleti szabályt; ha a tudásbázis és az aktuális context nem elég, mondd meg. "
            f"Kiválasztott modulok: {selected}.\n"
            f"{knowledge_text}\n\n"
        )
    return (
        knowledge_intro +
        "Aktuális HomeControl context következik JSON formában. "
        "Ezt használd elsődleges adatforrásként HC állapotkérdéseknél. "
        "Ha a user_query_focus nem üres, az a felhasználó kérdéséhez determinisztikusan kiválasztott legfontosabb adat; "
        "ilyen esetben abból válaszolj, és ne keress helyette hasonló nevű szenzort. "
        "Öntözési elemzésnél az irrigation.analysis alatt találod a tank 24h, moisture 24h, pumpa napi, pump.periods hosszabb időszakos és cycles ciklus adatokat. "
        "Fontos domain-modell: ez tartályos öntözőrendszer. A pumpa a tartályok töltésére való; a csap/szelep indítja a csöpögtető/locsolási kört. "
        "Ezért a pumpafutási idő és a locsolási/csöpögtetési ciklus időtartama nem ugyanaz, és nem feltétlenül függ össze közvetlenül. "
        "A pumpaadatait tartálytöltés/fogyasztás bizonyítékként kezeld, ne locsolási időként. "
        "Az irrigation.sessions vagy cycles a locsolási/csöpögtetési ciklus naplója lehet; eltérés esetén mondd ki a különbséget. "
        "Locsolás elemzésnél kapcsold össze az irrigation.schedules, irrigation.sessions/cycles, irrigation_pilot és scheduler blokkokat. "
        "Az irrigation_pilot.config.mode mondja meg, hogy navigator vagy pilot aktív: navigator módban a szabály csak ajánlás/napló, pilot módban a final_duration és skip szabály végrehajtási szándék. "
        "Az aktív pilot szabályokat a recommendation.triggered_rules, latest_decision/today_decision.triggered_rules, reason és execution_status mezőkből olvasd. "
        "A scheduler.engine.publish_domains és command_owner mutatja, hogy V2 ténylegesen vezérelhet-e; ha nincs irrigation publish domain, ne állítsd, hogy a V2 indított. "
        "Ha egy session start_payload mezőiben pilot_final_duration, pilot_triggered_rules, pilot_reason vagy stop_policy van, azt kösd a pilot/scheduler döntéshez. "
        "A HC Stats tab hőmérséklet/páratartalom adatai a home_statistics blokkban vannak, szenzoronkénti 24 órás trendekkel. "
        "Klíma fogyasztási kérdésnél kizárólag a climate_power blokkot használd. "
        "A climate_power a Gree klíma Tuya fogyasztásmérője; a server_power a HC szerver okoskonnektora, és nem klímaadat. "
        "Klíma beállítási kérdésnél a climate blokk aktuális power/mode/target_temperature/fan_speed mezőit és a climate_history történeti paraméter-idősort használd; a climate_schedules csak konfigurált szándék, nem mért használat. "
        "Ne használd a home_statistics szobahőmérőit klíma beállításként. "
        "Ha a climate_history nem elérhető vagy kevés mintát tartalmaz, mondd ki, hogy a historikus klíma-paraméter adat még hiányzik vagy melegszik. "
        "A 'HC szerver' egy Tuya fogyasztásmérős okoskonnektor/power_wall eszköz, nem az AI szerver és nem a remote AI node. "
        "HC szerver fogyasztási kérdésnél a server_power blokkot használd: avg_power_w_24h watt átlagteljesítmény, avg_daily_energy_kwh_7d/30d napi energiaátlag kWh/nap, today_energy_kwh mai energia. "
        "Ne keverd össze a HC szerver fogyasztását a klíma fogyasztásával, az irrigation pumpa futásával vagy az AI szerver modellel. "
        "Ha a felhasználó UI-ban látható angol helyiségnevet mond, a home_statistics.sensors display_name és aliases mezői alapján válaszd ki a szenzort. "
        "A tabok adatairól kérdezve ezekből dolgozz: tényeket, trendeket és óvatos következtetéseket adj, ne találj ki hiányzó mintákat. "
        "Ha adatminőségi gondot látsz, például kevés minta, régi minta, üres ciklus vagy ellentmondó pumpa/moisture adat, ezt mondd ki. "
        "Stílus: ne használj emojikat, markdown félkövért (**), hosszú markdown címhierarchiát vagy dekoratív elválasztókat. "
        "Elemzésnél rövid alcímek és sima felsorolások elégségesek. "
        "Ne állíts oksági kapcsolatot biztos tényként; például moisture változásnál írd azt, hogy valószínűleg vagy összefügghet a locsolással, ha a context nem bizonyít közvetlen okot. "
        "Ne mondd, hogy egy adott helyen a rendszer külön nem indított locsolást, ha csak globális locsolási/pumpa adat van. "
        "Ne találj ki SQL-lekérdezéseket, ne állítsd, hogy közvetlen adatbázist olvastál, "
        "és ne adj eszközvezérlési ígéretet. Ha a contextben nincs adat, mondd meg röviden.\n"
        f"{compact}"
    )










def vision_messages(message, history, config, context=None):
    # Reserve room for image tokens instead of attaching the full HC knowledge pack.
    messages = [{"role": "system", "content": config["system_prompt"][:4000]}]
    if isinstance(context, dict) and context:
        knowledge = context.get("knowledge_docs") or {}
        compact = {
            "hc_context_excerpt": compact_context_for_prompt(context, message)[:3000],
            "knowledge_excerpt": str(knowledge.get("content") or "")[:2000],
        }
        messages.append({"role": "system", "content": "Rövidített, részleges HC háttéradat; a hiányzó adatokat ne találd ki. " + json.dumps(compact, ensure_ascii=False)})
    remaining = 3000
    recent = []
    for item in reversed((history or [])[-4:]):
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content"):
            text = str(item["content"])
            if len(text) > remaining:
                break
            recent.append({"role": item["role"], "content": text})
            remaining -= len(text)
    messages.extend(reversed(recent))
    messages.append({"role": "user", "content": str(message or "")})
    return messages


def reduced_vision_images(images):
    result = []
    for item in images:
        with Image.open(io.BytesIO(base64.b64decode(item["data"]))) as original:
            img = ImageOps.exif_transpose(original)
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format="PNG")
            result.append(base64.b64encode(output.getvalue()).decode("ascii"))
    return result


def is_context_overflow(detail):
    return bool(re.search(r"exceed_context_size_error|exceeds (?:the )?available context|context length exceeded", detail, re.IGNORECASE))


def ollama_reply(message, history, config, context=None, images=None, image_timeout=None):
    if images and len(images) != 1:
        raise ValueError("Egy Ollama-kérés pontosan egy képet tartalmazhat.")
    messages = vision_messages(message, history, config, context) if images else build_messages(message, history, config, context)
    if images:
        messages[-1]["images"] = [item["data"] for item in images]
    options = {"temperature": config["temperature"], "num_ctx": config["num_ctx"], "num_predict": config["num_predict"]}
    payload = {"model": config["model"], "messages": messages, "stream": False, "think": False, "options": options}
    if config.get("format") == "json":
        payload["format"] = "json"
    for attempt in range(2):
        try:
            request_options = {"timeout": image_timeout or REQUEST_TIMEOUT} if images else {}
            with ollama_json("/api/chat", payload, method="POST", ollama_url=config["ollama_url"], **request_options) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if not images or exc.code != 400:
                raise
            detail = exc.read().decode("utf-8", errors="replace")
            if not is_context_overflow(detail):
                raise HTTPError(exc.url, exc.code, exc.reason, exc.headers, io.BytesIO(detail.encode("utf-8"))) from exc
            if attempt:
                raise ValueError("A képek és a kérdés nem férnek a modell kontextusába. Küldj egyszerre kevesebb képet vagy rövidebb kérdést.") from None
            # One bounded retry; keep the user's question, discard optional context.
            payload["messages"] = [messages[0], {
                "role": "user", "content": str(message or ""),
                "images": reduced_vision_images(images),
            }]
    response_message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content = response_message.get("content") or data.get("response") or response_message.get("thinking") or data.get("thinking") or ""
    return str(content).strip()


def sequential_image_replies(message, images, config):
    results = []
    # Reserve time for one context-size retry per image within the existing
    # gateway request budget; four sequential images must not each take 300s.
    image_timeout = REQUEST_TIMEOUT / (2 * len(images))
    for index, image in enumerate(images, 1):
        try:
            reply = clean_reply_text(ollama_reply(message, [], config, images=[image], image_timeout=image_timeout))
            if not reply:
                raise ValueError("A modell nem adott választ a képre.")
            results.append({"index": index, "ok": True, "reply": reply})
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            results.append({"index": index, "ok": False, "error": f"A képfeldolgozás sikertelen: HTTP {exc.code}: {detail or exc.reason}"})
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            results.append({"index": index, "ok": False, "error": friendly_provider_error(str(exc))})
    return results


def image_results_reply(results):
    return "\n\n".join(f"{row['index']}. kép\n" + (row["reply"] if row["ok"] else f"Hiba: {row['error']}") for row in results)


def build_messages(message, history, config, context=None):
    messages = [
        {
            "role": "system",
            "content": config["system_prompt"],
        }
    ]
    context_message = context_system_message(context, message)
    if context_message:
        messages.append({"role": "system", "content": context_message})
    for item in history or []:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": str(message or "")})
    return messages


def openai_compatible_reply(message, history, config, context=None):
    api_key = config.get("openai_api_key") or DEFAULT_OPENAI_API_KEY
    if not api_key:
        raise ValueError("OpenAI-compatible provider is missing an API key.")
    payload = {
        "model": config["model"],
        "messages": build_messages(message, history, config, context),
        "temperature": config["temperature"],
        "max_tokens": config["num_predict"],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    with request_json(f"{config['openai_base_url']}/chat/completions", payload, method="POST", headers=headers) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    first = choices[0] if choices else {}
    answer = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = answer.get("content") or first.get("text") or ""
    return str(content).strip()


def provider_health(config):
    provider = config["provider"]
    if provider == "fallback":
        return False, "No usable LLM provider is configured."
    if provider in {"ollama", "local_ollama", "remote_ollama"}:
        try:
            models = list_ollama_models(config["ollama_url"], timeout=PROBE_TIMEOUT)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return False, f"Ollama unavailable: {exc}"
        installed = model_names(models)
        if config["model"] not in installed:
            return False, f"Model is not installed on Ollama endpoint: {config['model']}"
        return True, f"Ollama model ready at {config['ollama_url']}"
    if provider == "openai_compatible":
        if not config.get("openai_api_key"):
            return False, "OpenAI-compatible provider is missing an API key."
        if not config.get("model"):
            return False, "OpenAI-compatible provider is missing a model name."
        return True, f"OpenAI-compatible provider configured at {config['openai_base_url']}"
    return False, f"Unsupported AI provider: {provider}"


def chat_response(message, history, context=None, images=None):
    started = time.time()
    config = read_config()
    provider = config["provider"]
    try:
        images = validate_images(images)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}, 400
    try:
        if images:
            if provider not in {"ollama", "local_ollama", "remote_ollama"}:
                return {"ok": False, "error": "Képet csak Ollama vision modellnek lehet küldeni."}, 400
            with ollama_json("/api/show", {"model": config["model"]}, method="POST", ollama_url=config["ollama_url"]) as response:
                model_info = json.loads(response.read().decode("utf-8"))
                capabilities = model_info.get("capabilities") if isinstance(model_info, dict) else None
            if not isinstance(capabilities, list) or "vision" not in capabilities:
                return {"ok": False, "error": "A kiválasztott modell nem támogat képfeldolgozást. Válassz vision modellt."}, 400
        direct_reply = None if images else direct_context_reply(message, context, history)
        if direct_reply:
            return {
                "ok": True,
                "reply": clean_reply_text(direct_reply),
                "provider": "hc_context",
                "model": "deterministic",
                "context": {
                    "ok": bool(context.get("ok")) if isinstance(context, dict) else False,
                    "schema_version": context.get("schema_version") if isinstance(context, dict) else None,
                    "generated_at": context.get("generated_at") if isinstance(context, dict) else None,
                },
                "elapsed_ms": int((time.time() - started) * 1000),
            }, 200
        if provider in {"ollama", "local_ollama", "remote_ollama"}:
            ready, detail = provider_health(config)
            if not ready:
                raise ConnectionError(detail)
            if images:
                image_results = sequential_image_replies(message, images, config)
                reply = image_results_reply(image_results)
                if not any(row["ok"] for row in image_results):
                    return {"ok": False, "error": reply, "image_results": image_results, "provider": provider, "model": config["model"]}, 502
            else:
                reply = ollama_reply(message, history, config, context)
        elif provider == "openai_compatible":
            reply = openai_compatible_reply(message, history, config, context)
        else:
            provider = "fallback"
            reply = fallback_reply(message, history, context)
        if not reply:
            raise ValueError("AI provider returned an empty response. Try a smaller model or raise Max Tokens.")
        return {
            "ok": True,
            "reply": clean_reply_text(reply),
            **({"image_results": image_results, "partial": any(not row["ok"] for row in image_results)} if images else {}),
            "provider": provider,
            "model": config["model"],
            "context": {
                "ok": bool(context.get("ok")) if isinstance(context, dict) else False,
                "schema_version": context.get("schema_version") if isinstance(context, dict) else None,
                "generated_at": context.get("generated_at") if isinstance(context, dict) else None,
            },
            "elapsed_ms": int((time.time() - started) * 1000),
        }, 200
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
        return {
            "ok": False,
            "error": (f"A képfeldolgozás sikertelen: HTTP {exc.code}: {detail or exc.reason}" if images else f"AI provider error: HTTP {exc.code}: {detail or exc.reason}"),
            "provider": provider,
            "model": config["model"],
        }, 502
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        if not images and isinstance(context, dict) and context:
            return {
                "ok": True,
                "reply": clean_reply_text(fallback_reply(message, history, context)),
                "provider": "fallback_context",
                "model": "hc-context",
                "provider_error": friendly_provider_error(f"AI provider error: {exc}"),
                "context": {
                    "ok": bool(context.get("ok")),
                    "schema_version": context.get("schema_version"),
                    "generated_at": context.get("generated_at"),
                },
                "elapsed_ms": int((time.time() - started) * 1000),
            }, 200
        return {
            "ok": False,
            "error": friendly_provider_error(f"A képfeldolgozás sikertelen: {exc}" if images else f"AI provider error: {exc}"),
            "provider": provider,
            "model": config["model"],
        }, 502


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeControlAI/0.1"

    def log_message(self, fmt, *args):
        print(f"[AI] {self.address_string()} {fmt % args}", flush=True)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health/live":
            write_json(self, 200, {"ok": True, "gateway_ok": True})
            return
        if path in {"/health", "/health/ready"}:
            config = read_config()
            ready, detail = provider_health(config)
            public_detail = detail if ready else friendly_provider_error(detail)
            write_json(self, 200 if path == '/health' or ready else 503, {
                "ok": ready,
                "gateway_ok": True,
                "ready": ready,
                "provider": config["provider"],
                "model": config["model"],
                "ollama_url": config["ollama_url"],
                "openai_base_url": config["openai_base_url"],
                "detail": public_detail,
            })
            return
        if path == "/config":
            write_json(self, 200, {"ok": True, "config": public_config(read_config()), "recommended_models": RECOMMENDED_MODELS})
            return
        if path == "/models":
            config = read_config()
            try:
                local = list_ollama_models(config["ollama_url"], timeout=PROBE_TIMEOUT)
                installed = model_names(local)
                recommended = [{**item, "installed": item["name"] in installed} for item in RECOMMENDED_MODELS]
                write_json(self, 200, {"ok": True, "local_models": local, "recommended_models": recommended, "ollama_url": config["ollama_url"]})
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                recommended = [{**item, "installed": False} for item in RECOMMENDED_MODELS]
                write_json(self, 200, {"ok": False, "error": "AI server unavailable", "local_models": [], "recommended_models": recommended, "ollama_url": config["ollama_url"]})
            return
        if path == "/models/pull/status":
            with PULL_LOCK:
                write_json(self, 200, {"ok": True, "pull": dict(PULL_STATUS)})
            return
        write_json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/chat", "/config", "/models/pull"}:
            write_json(self, 404, {"ok": False, "error": "not found"})
            return
        try:
            payload = read_json(self)
        except (json.JSONDecodeError, ValueError):
            write_json(self, 400, {"ok": False, "error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            write_json(self, 400, {"ok": False, "error": "A kérés JSON objektum legyen."})
            return
        if path == "/config":
            config = write_config(payload.get("config") if isinstance(payload.get("config"), dict) else payload)
            write_json(self, 200, {"ok": True, "config": public_config(config)})
            return
        if path == "/models/pull":
            config = read_config()
            model = str(payload.get("model") or "").strip()
            if not model:
                write_json(self, 400, {"ok": False, "error": "model is required"})
                return
            with PULL_LOCK:
                if PULL_STATUS.get("running"):
                    write_json(self, 409, {"ok": False, "error": f"pull already running for {PULL_STATUS.get('model')}", "pull": dict(PULL_STATUS)})
                    return
                PULL_STATUS.update({"running": True, "model": model, "status": "queued", "error": "", "completed": 0, "total": 0})
            threading.Thread(target=pull_worker, args=(model, config["ollama_url"]), name=f"pull-{model}", daemon=True).start()
            write_json(self, 202, {"ok": True, "pull": dict(PULL_STATUS)})
            return
        message = str(payload.get("message") or "").strip()
        history = payload.get("history") if isinstance(payload.get("history"), list) else []
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        result, status = chat_response(message, history[-20:], context, payload.get("images"))
        write_json(self, status, result)


def main():
    config = read_config()
    print(f"[AI] starting provider={config['provider']} model={config['model']} listen={HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
