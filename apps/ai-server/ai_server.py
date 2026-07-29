import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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


def parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def human_time(value):
    parsed = parse_time(value)
    if not parsed:
        return "-"
    now = datetime.now(parsed.tzinfo or timezone.utc)
    day_delta = (parsed.date() - now.date()).days
    clock = parsed.strftime("%H:%M")
    if day_delta == 0:
        return f"ma {clock}"
    if day_delta == -1:
        return f"tegnap {clock}"
    if day_delta == 1:
        return f"holnap {clock}"
    return parsed.strftime("%m.%d %H:%M")


def status_label(value):
    labels = {
        "auto_stopped": "automatikusan leállt",
        "stopped": "leállt",
        "running": "fut",
        "manual_stopped": "kézzel leállítva",
    }
    return labels.get(str(value or "").lower(), value or "-")


def source_label(value, started_by=None):
    source = str(value or "").strip().lower()
    starter = str(started_by or "").strip().lower()
    combined = f"{source} {starter}".strip()
    if source == "automatic" or any(part in combined for part in ["scheduler", "pilot", "v2_scheduler"]):
        return "automata vezérlés"
    if source == "manual" or any(part in combined for part in ["admin", "manual", "homecontrol-admin", "user", "dashboard"]):
        return "kézi/admin indítás"
    return "nem egyértelmű"


def stop_source_label(value):
    labels = {
        "automatic": "automatikus leállítás",
        "manual": "manuális leállítás",
        "not_stopped": "még nem állt le",
        "unknown": "nem egyértelmű leállítási mód",
    }
    return labels.get(str(value or "").lower(), "nem egyértelmű leállítási mód")


def target_date_for_text(text, tzinfo):
    now = datetime.now(tzinfo or timezone.utc)
    if re.search(r"\btegnap\b", text):
        return now.date() - timedelta(days=1), "tegnap"
    if re.search(r"\b(ma|mai)\b", text):
        return now.date(), "ma"
    return None, ""


def cycle_start(cycle):
    return parse_time((cycle or {}).get("started_at"))


def cycle_end(cycle):
    return parse_time((cycle or {}).get("ended_at"))


def cycle_matches_date(cycle, target_date):
    started = cycle_start(cycle)
    if not started or not target_date:
        return False
    return started.date() == target_date


def approximate_cycle_end(cycle):
    started = cycle_start(cycle)
    duration = (cycle or {}).get("duration_min")
    try:
        minutes = float(duration)
    except (TypeError, ValueError):
        return None
    if not started:
        return None
    return started + timedelta(minutes=minutes)


def time_without_repeated_day(value, day_label):
    text = human_time(value)
    prefix = f"{day_label} "
    if day_label and text.startswith(prefix):
        return text[len(prefix):]
    return text


def requested_period_key(text):
    if any(part in text for part in ["180 nap", "fél év", "felev", "félév", "6 hónap", "6 honap"]):
        return "last_180d"
    if any(part in text for part in ["30 nap", "egy hónap", "egy honap", "hónap", "honap"]):
        return "last_30d"
    if any(part in text for part in ["nyár", "nyari", "nyári", "szezon"]):
        return "summer_season"
    if any(part in text for part in ["7 nap", "egy hét", "egy het", "hét", "het"]):
        return "last_7d"
    return "last_30d"


def period_label(key, period=None):
    if isinstance(period, dict) and period.get("label"):
        return period["label"]
    labels = {
        "last_7d": "utolsó 7 nap",
        "last_30d": "utolsó 30 nap",
        "last_180d": "utolsó 180 nap",
        "summer_season": "aktuális nyári szezon",
    }
    return labels.get(key, "kért időszak")


def start_source_label(value, started_by=None):
    return source_label(value, started_by)


def cycle_line(cycle, index=None):
    prefix = f"{index}. " if index is not None else ""
    return (
        f"{prefix}{human_time(cycle.get('started_at'))} -> {human_time(cycle.get('ended_at'))}, "
        f"hossz: {cycle.get('duration_min', '-')} perc, "
        f"indítás: {start_source_label(cycle.get('start_source'), cycle.get('started_by'))}, "
        f"leállítás: {stop_source_label(cycle.get('stop_source'))}."
    )


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
        "temperature": 0.2,
        "num_ctx": 16384,
        "num_predict": 1536,
        "system_prompt": "Te vagy a HomeControl AI asszisztense. Mindig magyarul válaszolj. A HomeControl öntözés tartályos rendszer: a pumpa a tartályok töltésére szolgál, a csap/szelep indítja a csöpögtető rendszert. A pumpafutási idő és a locsolási/csöpögtetési idő nem ugyanaz, és nem feltétlenül mozognak együtt. Válaszolj érthetően, természetes mondatokban. Ne használj emojikat, markdown félkövért (**), túl sok címsort vagy díszítő elválasztókat. Ha elemzést kérnek, adhatsz hosszabb, tagolt választ, de maradj tárgyszerű és mindig fejezd be rövid összegzéssel. Ne találj ki szerverjogokat vagy eszközvezérlést; ha nincs HC adatod, mondd meg.",
    }


def normalize_config(data):
    current = default_config()
    if isinstance(data, dict):
        current.update({k: v for k, v in data.items() if k in current})
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


def context_query_focus(context, message):
    if not isinstance(context, dict):
        return {}
    text = str(message or "").strip().lower()
    if not text:
        return {}
    home_stats = context.get("home_statistics") if isinstance(context.get("home_statistics"), dict) else {}
    matches = []
    for sensor in home_stats.get("sensors") or []:
        if not isinstance(sensor, dict):
            continue
        names = []
        for key in ["name", "display_name"]:
            if sensor.get(key):
                names.append(str(sensor.get(key)))
        names.extend(str(item) for item in sensor.get("aliases") or [])
        clean_names = [name for name in dict.fromkeys(names) if name]
        negated = any(
            f"do not use {name.lower()}" in text
            or f"don't use {name.lower()}" in text
            or f"not {name.lower()}" in text
            or f"ne {name.lower()}" in text
            for name in clean_names
        )
        if negated:
            continue
        if any(name.lower() in text for name in clean_names):
            matches.append(sensor)
    return {"home_statistics_sensor_matches": matches[:3]} if matches else {}


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


def context_value(context, *path):
    current = context
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def hu_trend(value):
    labels = {
        "rising": "emelkedik",
        "falling": "csökken",
        "stable": "stabil",
        "unknown": "nem egyértelmű",
    }
    return labels.get(str(value or "").lower(), value or "-")


def fallback_reply(message, history, context=None):
    text = " ".join(str(message or "").strip().split())
    if not text:
        return "Írj egy kérdést vagy feladatot, és válaszolok. Most még alap AI mód fut, HC vezérlési jogosultság nélkül."

    lowered = text.lower()
    if any(word in lowered for word in ["szia", "hello", "hali"]):
        return "Szia! Az AI szerver első alapverziója fut. Ma még beszélgetünk, a HomeControl hatásköröket később kötjük rá."
    if any(word in lowered for word in ["öntöz", "locsol", "eső", "csapadék"]):
        rain = context_value(context, "weather", "rain_24h_mm")
        forecast = context_value(context, "weather", "forecast_rain_24h_mm")
        valve = context_value(context, "irrigation", "manual_valve_state")
        blocked = context_value(context, "irrigation", "manual_valve_blocked")
        pump_today = context_value(context, "irrigation", "analysis", "pump", "today") or {}
        moisture = context_value(context, "irrigation", "analysis", "moisture_24h") or []
        moisture_text = ", ".join(
            f"{item.get('name')}: {item.get('latest_percent')}% ({item.get('trend_24h')})"
            for item in moisture[:3]
            if isinstance(item, dict)
        ) or "nincs moisture összefoglaló"
        return (
            f"Az aktuális HC context alapján az elmúlt 24 óra csapadéka {rain if rain is not None else '-'} mm, "
            f"az előrejelzett 24 órás eső {forecast if forecast is not None else '-'} mm. "
            f"A kézi szelep állapota: {valve or '-'}, blokkolás: {'igen' if blocked else 'nem' if blocked is not None else '-'}. "
            f"Mai pumpafutás: {pump_today.get('runtime_min', '-')} perc, {pump_today.get('watt_hours', '-')} Wh. "
            f"Moisture trend: {moisture_text}."
        )
    if any(word in lowered for word in ["klíma", "klima", "hőmérséklet", "homerseklet"]):
        power = context_value(context, "climate", "power")
        mode = context_value(context, "climate", "mode")
        current = context_value(context, "climate", "current_temperature")
        target = context_value(context, "climate", "target_temperature")
        return f"A klíma context szerint power={power or '-'}, mód={mode or '-'}, aktuális hőmérséklet={current if current is not None else '-'} °C, cél={target if target is not None else '-'} °C."
    if any(word in lowered for word in ["porszívó", "x10", "robot"]):
        status = context_value(context, "robot", "status")
        battery = context_value(context, "robot", "battery")
        task = context_value(context, "robot", "task_state")
        return f"A robot context szerint státusz: {status or '-'}, akkumulátor: {battery if battery is not None else '-'}%, feladatállapot: {task or '-'}."
    if "homecontrol" in lowered or "hc" in lowered:
        status = context_value(context, "house", "status")
        generated_at = context_value(context, "generated_at")
        return f"A HomeControl context már be van kötve. Rendszerállapot: {status or '-'}, context időpont: {generated_at or '-'}."
    if "mit tudsz" in lowered or "mire vagy képes" in lowered:
        return "Most már látom a HC Context Layert olvasási módban: időjárás, öntözés, klíma, robot, power wall, napelem és jegyzetek állapotát. Eszközt még nem vezérlek."

    turns = len(history or [])
    return (
        f"Vettem: „{text}”. A beszélgetés API-ja működik, és a HC context is megérkezett olvasási módban. "
        f"Eddig {turns} előzmény üzenetet kaptam."
    )


def direct_context_reply(message, context=None, history=None):
    text = str(message or "").strip().lower()
    if not isinstance(context, dict) or not text:
        return ""
    combined = "\n".join([text] + [str(item.get("content") or item.get("message") or item) for item in (history or [])[-4:] if item]).lower()
    asks_home_stats = "hc stats" in text or "home statistics" in text or "homecontrol statistics" in text
    asks_climate_values = any(word in text for word in ["humidity", "pár", "para", "temperature", "hőmér", "homersek", "temp"])
    asks_moisture = any(word in text for word in ["moisture", "talajnedv", "talaj nedv", "soil"])
    asks_weather = any(word in text for word in ["időjár", "idojar", "weather", "eső", "eso", "csapad", "tegnap", "mai"])
    asks_irrigation_effect = any(word in text for word in ["locsol", "öntöz", "ontoz", "reagált", "reagalt", "hatott", "ciklus"])
    asks_irrigation_start_time = any(word in text for word in ["locsol", "öntöz", "ontoz", "csöpögtet", "csopogtet"]) and any(word in text for word in ["indult", "kezd", "start"])
    asks_irrigation_stop_time = any(word in text for word in ["locsol", "öntöz", "ontoz", "csöpögtet", "csopogtet", "leáll", "leallit"]) and any(word in text for word in ["mikor", "leáll", "leallit", "állt le", "utoljára", "utoljara"])
    asks_irrigation_duration_distribution = any(word in text for word in ["locsol", "öntöz", "ontoz", "csöpögtet", "csopogtet"]) and any(word in text for word in ["90", "rövidebb", "rovidebb", "hosszabb"]) and any(word in text for word in ["hányszor", "hanyszor", "mennyi", "darab"])
    asks_irrigation_cycle_list = any(word in text for word in ["locsol", "öntöz", "ontoz", "csöpögtet", "csopogtet", "ciklus"]) and any(word in text for word in ["sorold", "felsorol", "listáz", "listaz", "lista"])
    asks_todays_irrigation_summary = any(word in text for word in ["locsol", "öntöz", "ontoz", "csöpögtet", "csopogtet"]) and any(word in text for word in ["ma", "mai", "mesélj", "meselj", "összefoglal", "osszefoglal"])
    focus = context_query_focus(context, message)
    matches = focus.get("home_statistics_sensor_matches") or []
    asks_climate_power = any(word in text for word in ["klím", "klima", "gree", "climate"]) and any(word in text for word in ["fogyaszt", "teljesítmény", "teljesitmeny", "watt", "kwh", "energia", "áram", "aram"])
    if asks_climate_power:
        climate_power = context.get("climate_power") if isinstance(context.get("climate_power"), dict) else {}
        if not climate_power or climate_power.get("ok") is False:
            return f"A klíma fogyasztásmérő adata nem elérhető az AI contextben: {climate_power.get('error') or 'nincs climate_power adat'}."
        meter = climate_power.get("meter") if isinstance(climate_power.get("meter"), dict) else {}
        name = meter.get("entity_name") or meter.get("device_name") or "Gree klíma"
        if any(word in text for word in ["hónap", "honap"]):
            energy = climate_power.get("month_energy_kwh")
            days = climate_power.get("month_days")
            avg_daily = (round(float(energy) / float(days), 3) if energy is not None and days else None)
            return (
                f"A klíma havi fogyasztását a climate_power blokk alapján számolom, nem a HC szerver fogyasztásmérőjéből. "
                f"Az aktuális hónap eddigi mért fogyasztása {energy if energy is not None else '-'} kWh "
                f"({days if days is not None else 0} napi sor alapján). "
                f"Ez napi átlagban {avg_daily if avg_daily is not None else '-'} kWh/nap. "
                f"Mai eddigi fogyasztás: {climate_power.get('today_energy_kwh', '-')} kWh, "
                f"aktuális teljesítmény: {climate_power.get('current_power_w', '-')} W, mérő: {name}."
            )
        if any(word in text for word in ["30 nap", "harminc"]):
            return (
                f"A klíma utolsó 30 napos fogyasztása {climate_power.get('energy_kwh_30d', '-')} kWh "
                f"({climate_power.get('daily_days', 0)} napi sor alapján). "
                f"A 30 napos napi átlag {climate_power.get('avg_daily_energy_kwh_30d', '-')} kWh/nap; "
                f"a 24 órás átlagteljesítmény {climate_power.get('avg_power_w_24h', '-')} W."
            )
        if any(word in text for word in ["7 nap", "hét", "het"]):
            return (
                f"A klíma utolsó 7 napos fogyasztása {climate_power.get('energy_kwh_7d', '-')} kWh. "
                f"A 7 napos napi átlag {climate_power.get('avg_daily_energy_kwh_7d', '-')} kWh/nap; "
                f"mai eddigi fogyasztás {climate_power.get('today_energy_kwh', '-')} kWh."
            )
        return (
            f"A klíma fogyasztásmérője: {name}. "
            f"Mai eddigi fogyasztás {climate_power.get('today_energy_kwh', '-')} kWh, "
            f"aktuális teljesítmény {climate_power.get('current_power_w', '-')} W, "
            f"utolsó 24 órás átlag {climate_power.get('avg_power_w_24h', '-')} W. "
            f"Ez climate_power adat, nem HC szerver/server_power adat."
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
            lines.append("Historikus klíma paraméterek a climate_history blokkból:")
            for key, label in [("climate_power", "power"), ("climate_mode", "mód"), ("climate_fan_speed", "fan")]:
                values = distributions.get(key) if isinstance(distributions.get(key), list) else []
                if values:
                    lines.append(f"- {label} 7 napos minták: " + ", ".join(f"{item.get('value')} ({item.get('sample_count')})" for item in values[:4]))
            for key, label in [("climate_target_temperature", "célhő"), ("climate_current_temperature", "mért hő")]:
                item = numeric.get(key) if isinstance(numeric.get(key), dict) else {}
                if item:
                    lines.append(f"- {label} 7 nap: átlag {item.get('avg')}, min {item.get('min')}, max {item.get('max')}, minták {item.get('sample_count')}")
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
    asks_hc_server_power = ("hc szerver" in text or "homecontrol szerver" in text) and any(word in text for word in ["fogyaszt", "teljesítmény", "teljesitmeny", "watt", "kwh", "energia", "átlag", "atlag", "mesélj", "meselj"])
    if asks_hc_server_power:
        server_power = context.get("server_power") if isinstance(context.get("server_power"), dict) else {}
        if not server_power or server_power.get("ok") is False:
            devices = context_value(context, "power_wall", "devices") or []
            match = next(
                (
                    item for item in devices
                    if isinstance(item, dict)
                    and "hc szerver" in str(item.get("name") or "").strip().lower()
                ),
                None,
            )
            if match:
                return (
                    "A HC szerver itt a Tuya fogyasztásmérős okoskonnektor, nem az AI szerver. "
                    "A részletes 7/30 napos server_power összesítés most nincs az AI contextben, "
                    f"de a power_wall pillanatnyi adata alapján az aktuális teljesítménye {match.get('power_w', '-')} W, "
                    f"kapcsolóállapot: {match.get('switch', '-')}, státusz: {match.get('status', '-')}."
                )
            return f"A HC szerver fogyasztásmérő adata nem elérhető az AI contextben: {server_power.get('error') or 'nincs server_power adat'}."
        device = server_power.get("device") if isinstance(server_power.get("device"), dict) else {}
        name = device.get("display_name") or device.get("entity_name") or "HC szerver"
        avg_24h = server_power.get("avg_power_w_24h")
        avg_7d = server_power.get("avg_daily_energy_kwh_7d")
        avg_30d = server_power.get("avg_daily_energy_kwh_30d")
        today = server_power.get("today_energy_kwh")
        current = server_power.get("current_power_w")
        samples = server_power.get("sample_count_24h")
        return (
            f"A {name} itt a Tuya fogyasztásmérős okoskonnektor, nem az AI szerver. "
            f"Az utolsó 24 óra átlagos teljesítménye {avg_24h if avg_24h is not None else '-'} W "
            f"({samples if samples is not None else 0} minta alapján). "
            f"A 7 napos átlagos napi energiafogyasztás {avg_7d if avg_7d is not None else '-'} kWh/nap, "
            f"a 30 napos átlag {avg_30d if avg_30d is not None else '-'} kWh/nap. "
            f"Mai eddigi fogyasztás: {today if today is not None else '-'} kWh, aktuális teljesítmény: {current if current is not None else '-'} W."
        )
    if asks_todays_irrigation_summary and not asks_moisture and not asks_irrigation_cycle_list:
        cycles = [cycle for cycle in (context_value(context, "irrigation", "analysis", "cycles", "recent") or []) if isinstance(cycle, dict)]
        first_started = cycle_start(cycles[0]) if cycles else None
        today_date, day_label = target_date_for_text("ma", first_started.tzinfo if first_started else timezone.utc)
        todays = [cycle for cycle in cycles if cycle_matches_date(cycle, today_date)]
        if not todays:
            return "Ma nem látok naplózott locsolási/csöpögtetési ciklust az AI summary-ban."
        lines = [f"Ma {len(todays)} naplózott locsolási/csöpögtetési ciklust látok:"]
        for cycle in todays[:5]:
            lines.append(
                f"- {time_without_repeated_day(cycle.get('started_at'), day_label)} -> "
                f"{time_without_repeated_day(cycle.get('ended_at'), day_label)}, "
                f"hossz: {cycle.get('duration_min', '-')} perc, "
                f"indítás: {source_label(cycle.get('start_source'), cycle.get('started_by'))}, "
                f"leállítás: {stop_source_label(cycle.get('stop_source'))}, "
                f"státusz: {status_label(cycle.get('status'))}."
            )
        pilot = context.get("irrigation_pilot") if isinstance(context.get("irrigation_pilot"), dict) else {}
        recommendation = pilot.get("recommendation") if isinstance(pilot.get("recommendation"), dict) else {}
        today_decision = pilot.get("today_decision") if isinstance(pilot.get("today_decision"), dict) else {}
        if recommendation or today_decision:
            mode = (pilot.get("config") or {}).get("mode") if isinstance(pilot.get("config"), dict) else recommendation.get("mode")
            rules = today_decision.get("triggered_rules") or recommendation.get("triggered_rules") or []
            status = today_decision.get("execution_status")
            reason = today_decision.get("reason") or recommendation.get("reason")
            lines.append(
                f"Pilot/scheduler szabály: mód {mode or '-'}, aktív szabályok {rules or []}, "
                f"döntési státusz {status or '-'}, indok: {reason or '-'}."
            )
        moisture_rows = context_value(context, "irrigation", "analysis", "moisture_24h") or []
        if moisture_rows:
            parts = []
            for item in moisture_rows[:3]:
                if isinstance(item, dict):
                    parts.append(f"{item.get('name')}: {item.get('latest_percent')}% ({hu_trend(item.get('trend_24h'))})")
            if parts:
                lines.append("Talajnedvesség 24h kép: " + "; ".join(parts) + ".")
        lines.append("Fontos: a leállítás okát csak akkor lehet konkrét szabályhoz kötni, ha azt a pilot döntés vagy a session stop_payload/stop_policy is tartalmazza.")
        return "\n".join(lines)
    if asks_irrigation_cycle_list and not asks_moisture:
        period_key = requested_period_key(text)
        cycles_key = "last_30d" if period_key == "last_30d" else "recent"
        cycles = [cycle for cycle in (context_value(context, "irrigation", "analysis", "cycles", cycles_key) or []) if isinstance(cycle, dict)]
        if not cycles:
            return f"Nem látok naplózott locsolási/csöpögtetési ciklusokat az {period_label(period_key)} időszakra."
        period = context_value(context, "irrigation", "analysis", "pump", "periods", period_key) or {}
        lines = [f"{period_label(period_key, period).capitalize()} ciklusai ({len(cycles)} db):"]
        lines.extend(cycle_line(cycle, index + 1) for index, cycle in enumerate(cycles))
        return "\n".join(lines)
    if asks_irrigation_duration_distribution and not asks_moisture:
        period_key = requested_period_key(text)
        period = context_value(context, "irrigation", "analysis", "pump", "periods", period_key) or {}
        distribution = period.get("cycle_duration_distribution_90m") if isinstance(period, dict) else {}
        if not isinstance(distribution, dict) or not distribution:
            return "Nem látok ciklus-időtartam eloszlást az AI summary-ban a kért időszakra."
        total = period.get("cycle_count", 0)
        target = distribution.get("target_min", 90)
        tolerance = distribution.get("tolerance_min", 5)
        return (
            f"Az {period_label(period_key, period)} alatt {total} naplózott locsolási/csöpögtetési ciklust látok. "
            f"Kb. {target:g} percesnek a {target - tolerance:g}-{target + tolerance:g} perc közötti ciklusokat vettem: "
            f"{distribution.get('near_target_count', 0)} ilyen volt. "
            f"Rövidebb: {distribution.get('shorter_count', 0)}, hosszabb: {distribution.get('longer_count', 0)}. "
            f"Az átlagos ciklushossz ebben az időszakban {period.get('cycle_avg_duration_min', '-')} perc, "
            f"ezért az átlagot nem szabad úgy értelmezni, mintha a ciklusok többsége 90 perces lenne."
        )
    if asks_irrigation_stop_time and not asks_moisture and not asks_irrigation_start_time:
        cycles = [cycle for cycle in (context_value(context, "irrigation", "analysis", "cycles", "recent") or []) if isinstance(cycle, dict)]
        manual_only = any(word in text for word in ["manuál", "manual", "kézi", "kezi"])
        automatic_only = any(word in text for word in ["automata", "automatikus", "gép", "gep", "scheduler"])
        first_end = cycle_end(cycles[0]) if cycles else None
        target_date, day_label = target_date_for_text(text, first_end.tzinfo if first_end else timezone.utc)
        selected = [cycle for cycle in cycles if cycle.get("ended_at") and (not target_date or (cycle_end(cycle) and cycle_end(cycle).date() == target_date))]
        if manual_only:
            selected = [cycle for cycle in selected if cycle.get("stop_source") == "manual" or str(cycle.get("status") or "").lower() in {"stopped", "manual_stopped"}]
        elif automatic_only:
            selected = [cycle for cycle in selected if cycle.get("stop_source") == "automatic" or str(cycle.get("status") or "").lower() == "auto_stopped"]
        if not selected:
            qualifier = "manuális " if manual_only else "automatikus " if automatic_only else ""
            when = f"{day_label} " if day_label else ""
            return f"Nem látok {when}{qualifier}locsolási leállítást az AI summary legutóbbi ciklusai között."
        cycle = selected[0]
        return (
            f"A legutóbbi {stop_source_label(cycle.get('stop_source'))} "
            f"{human_time(cycle.get('ended_at'))}-kor volt. "
            f"A ciklus {human_time(cycle.get('started_at'))}-kor indult, "
            f"indítás módja: {source_label(cycle.get('start_source'), cycle.get('started_by'))}, "
            f"időtartam: {cycle.get('duration_min', '-')} perc, státusz: {status_label(cycle.get('status'))}."
        )
    if asks_irrigation_start_time and not asks_moisture:
        cycles = context_value(context, "irrigation", "analysis", "cycles", "recent") or []
        first_started = cycle_start(cycles[0]) if cycles else None
        target_date, day_label = target_date_for_text(text, first_started.tzinfo if first_started else timezone.utc)
        selected = [cycle for cycle in cycles if isinstance(cycle, dict) and cycle_matches_date(cycle, target_date)] if target_date else [cycle for cycle in cycles if isinstance(cycle, dict)][:1]
        if not selected:
            when = day_label or "a kért időszakban"
            return f"{when.capitalize()} nem látok naplózott csöpögtetési/locsolási ciklust az AI contextben."
        lines = []
        prefix = day_label.capitalize() if day_label else "A legutóbbi naplózott ciklus"
        if len(selected) == 1:
            cycle = selected[0]
            end_text = human_time(cycle.get("ended_at"))
            if end_text == "-":
                approx = approximate_cycle_end(cycle)
                end_part = f"A leállási időpont nincs külön a summary-ban; a {cycle.get('duration_min', '-')} perces naplózott időtartam alapján kb. {time_without_repeated_day(approx, day_label)} körül fejeződhetett be."
            else:
                end_part = f"Leállás: {time_without_repeated_day(cycle.get('ended_at'), day_label)}."
            source_part = source_label(cycle.get("start_source"), cycle.get("started_by"))
            return (
                f"{prefix} {time_without_repeated_day(cycle.get('started_at'), day_label)}-kor indult. "
                f"Indítás módja: {source_part}. "
                f"Naplózott időtartam: {cycle.get('duration_min', '-')} perc, státusz: {status_label(cycle.get('status'))}. "
                f"{end_part}"
            )
        lines.append(f"{prefix} {len(selected)} naplózott csöpögtetési/locsolási ciklust látok:")
        for cycle in selected[:5]:
            source_part = source_label(cycle.get("start_source"), cycle.get("started_by"))
            stop_part = f", leállás {human_time(cycle.get('ended_at'))}" if cycle.get("ended_at") else ""
            lines.append(f"- indulás {human_time(cycle.get('started_at'))}{stop_part}, {source_part}, időtartam {cycle.get('duration_min', '-')} perc, státusz {status_label(cycle.get('status'))}.")
        return "\n".join(lines)
    if asks_home_stats and asks_climate_values and len(matches) == 1:
        sensor = matches[0]
        name = sensor.get("display_name") or sensor.get("name") or "selected sensor"
        temp = sensor.get("latest_temperature_c")
        humidity = sensor.get("latest_humidity_percent")
        abs_humidity = sensor.get("latest_absolute_humidity_g_m3")
        temp_trend = (sensor.get("temperature") or {}).get("trend_24h") or "-"
        humidity_trend = (sensor.get("humidity") or {}).get("trend_24h") or "-"
        ts = human_time(sensor.get("latest_ts"))
        return (
            f"{name} HC Stats értékei: hőmérséklet {temp if temp is not None else '-'} °C, "
            f"páratartalom {humidity if humidity is not None else '-'}%, "
            f"abszolút páratartalom {abs_humidity if abs_humidity is not None else '-'} g/m3. "
            f"24 órás trend: hőmérséklet {temp_trend}, páratartalom {humidity_trend}. "
            f"Utolsó minta: {ts}."
        )
    if asks_moisture:
        rows = context_value(context, "irrigation", "analysis", "moisture_24h") or []
        if rows:
            selected = []
            for item in rows:
                if not isinstance(item, dict):
                    continue
                names = [str(item.get("name") or ""), str(item.get("entity_id") or "")]
                if any(name and name.lower() in text for name in names):
                    selected.append(item)
            if not selected:
                selected = [item for item in rows if isinstance(item, dict)]

            weather = context.get("weather") or {}
            pump_today = context_value(context, "irrigation", "analysis", "pump", "today") or {}
            cycles = context_value(context, "irrigation", "analysis", "cycles", "recent") or []
            latest_cycle = cycles[0] if cycles and isinstance(cycles[0], dict) else {}
            title = "Moisture szenzor 24 órás elemzése:" if len(selected) == 1 else "Moisture szenzorok 24 órás képe:"
            lines = [title]

            if asks_weather:
                lines.append(
                    "Időjárási háttér: "
                    f"elmúlt 24h csapadék {weather.get('rain_24h_mm', '-')} mm, "
                    f"előrejelzett 24h csapadék {weather.get('forecast_rain_24h_mm', '-')} mm, "
                    f"csapadék valószínűség {weather.get('pop_percent', '-')}%."
                )
                lines.append("Külön tegnapi napi bontás nincs az AI contextben, ezért itt a 24 órás összesítésből és a mai/előrejelzett adatokból lehet következtetni.")

            if asks_irrigation_effect:
                lines.append(
                    "Öntözőrendszer háttér: tartályos rendszer, ahol a pumpa a tartályt tölti, "
                    "a csap/szelep pedig a csöpögtető kört indítja. "
                    f"Mai mért pumpafutás tartálytöltéshez: {pump_today.get('runtime_min', '-')} perc, "
                    f"pumpa fogyasztás {pump_today.get('watt_hours', '-')} Wh. "
                    f"Legutóbbi naplózott csöpögtetési/locsolási ciklus: {latest_cycle.get('duration_min', '-')} perc, "
                    f"státusz {latest_cycle.get('status', '-')}, indulás {human_time(latest_cycle.get('started_at'))}."
                )

            for item in selected[:6]:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("entity_id") or "moisture"
                latest = item.get("latest_percent")
                avg = item.get("avg_24h_percent")
                trend = item.get("trend_24h") or "-"
                delta = item.get("delta_24h_percent")
                samples = item.get("sample_count")
                lines.append(f"- {name}: legutóbbi {latest}%, 24h átlag {avg}%, trend {hu_trend(trend)}, változás {delta}%, minták {samples}.")

                if len(selected) == 1 and asks_irrigation_effect:
                    responses = item.get("watering_response") or []
                    response = responses[0] if responses and isinstance(responses[0], dict) else {}
                    if response:
                        rise = response.get("rise_from_pre_min_percent")
                        lines.append(
                            "Locsolási reakció: "
                            f"a ciklus előtti minimum {response.get('pre_cycle_min_percent', '-')}% volt "
                            f"({human_time(response.get('pre_cycle_min_ts'))}), "
                            f"a ciklus utáni/atti csúcs {response.get('peak_after_start_percent', '-')}% "
                            f"({human_time(response.get('peak_ts'))}). "
                            f"Emelkedés: {rise if rise is not None else '-'} százalékpont, "
                            f"csúcsig eltelt idő: {response.get('minutes_start_to_peak', '-')} perc."
                        )
                        if rise is not None and float(rise) >= 10:
                            reaction = "Ez erős és jól látható nedvességválasz, tehát a csöpögtetési ciklus ezen a szenzoron hatékonynak látszik."
                        elif rise is not None and float(rise) >= 5:
                            reaction = "Ez mérsékelt, de látható nedvességválasz, a csöpögtetés hatása valószínűleg megjelent a szenzoron."
                        elif rise is not None and float(rise) > 0:
                            reaction = "Ez gyenge nedvességválasz; lehet hatás, de nem erős."
                        else:
                            reaction = "A ciklushoz kötött emelkedés nem látszik egyértelműen."
                    elif delta is None:
                        reaction = "A locsolásra adott reakció nem ítélhető meg, mert nincs elég ciklushoz kötött minta."
                    elif float(delta) > 1:
                        reaction = "A 24 órás ablakban emelkedés látszik, ez összefügghet a locsolással."
                    elif float(delta) < -1:
                        reaction = "A 24 órás ablakban csökkenés látszik, vagyis nincs tartós emelkedés."
                    else:
                        reaction = "A 24 órás összkép stabil, de ez önmagában nem zárja ki a ciklus utáni rövidebb emelkedést."
                    lines.append(f"Értelmezés: {reaction}")
                    if response and response.get("cycle_duration_min") and response.get("peak_after_start_percent") is not None:
                        lines.append("Ha magasabb talajnedvességi csúcsot szeretnél, érdemes óvatosan hosszabb csöpögtetési időt próbálni, majd ugyanígy a ciklus előtti minimumot és utáni csúcsot összevetni.")

            if len(selected) == 1:
                lines.append("Mire figyelj: ennél a szenzornál a ciklus előtti minimum és a ciklus utáni csúcs sokkal beszédesebb, mint a teljes 24 órás első-utolsó trend.")
            else:
                lines.append("Mire figyelj: az alacsonyabb vagy gyorsan eső értékeket kezeld fontosabb jelzésként. A moisture változás összefügghet a locsolással, de önmagában nem bizonyít közvetlen ok-okozatot.")
            lines.append("Összegzés: a trendet, a változás mértékét, a mintaszámot, a locsolási ciklusnaplót és a tartálytöltési pumpaadatot együtt érdemes nézni, nem csak az utolsó értéket.")
            return "\n".join(lines)
    return ""


def ollama_reply(message, history, config, context=None):
    messages = build_messages(message, history, config, context)
    options = {"temperature": config["temperature"], "num_ctx": config["num_ctx"], "num_predict": config["num_predict"]}
    payload = {"model": config["model"], "messages": messages, "stream": False, "think": False, "options": options}
    with ollama_json("/api/chat", payload, method="POST", ollama_url=config["ollama_url"]) as response:
        data = json.loads(response.read().decode("utf-8"))
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    content = message.get("content") or data.get("response") or message.get("thinking") or data.get("thinking") or ""
    return str(content).strip()


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


def chat_response(message, history, context=None):
    started = time.time()
    config = read_config()
    provider = config["provider"]
    try:
        direct_reply = direct_context_reply(message, context, history)
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
            "error": f"AI provider error: HTTP {exc.code}: {detail or exc.reason}",
            "provider": provider,
            "model": config["model"],
        }, 502
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(context, dict) and context:
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
            "error": friendly_provider_error(f"AI provider error: {exc}"),
            "provider": provider,
            "model": config["model"],
        }, 502


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeControlAI/0.1"

    def log_message(self, fmt, *args):
        print(f"[AI] {self.address_string()} {fmt % args}", flush=True)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            config = read_config()
            ready, detail = provider_health(config)
            public_detail = detail if ready else friendly_provider_error(detail)
            write_json(self, 200, {
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
        except json.JSONDecodeError:
            write_json(self, 400, {"ok": False, "error": "invalid JSON"})
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
        result, status = chat_response(message, history[-20:], context)
        write_json(self, status, result)


def main():
    config = read_config()
    print(f"[AI] starting provider={config['provider']} model={config['model']} listen={HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
