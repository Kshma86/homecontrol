"""Canonical, I/O-free HC fact replies, shared by proxy and provider adapter."""

from typing import Any, Dict, Iterable, List, Optional
import json
from ai_context_plan import context_sections
import re
from datetime import datetime, timedelta, timezone

def climate_power_reply(text, context):
    asks_climate_power = any(word in text for word in ["klím", "klima", "gree", "climate"]) and any(
        word in text for word in ["fogyaszt", "teljesítmény", "teljesitmeny", "watt", "kwh", "energia", "áram", "aram"]
    )
    if not asks_climate_power:
        return ""

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


def _routing_text(message: str, history: Iterable[Any]) -> str:
        if context_sections(message):
            return str(message or "")
        parts = [str(message or "")]
        for item in list(history or [])[-4:]:
            if isinstance(item, dict):
                parts.append(str(item.get("content") or item.get("message") or ""))
            else:
                parts.append(str(item))
        return "\n".join(parts)

def _backend_context_reply(message: str, context: Dict[str, Any], history: Iterable[Any]=()) -> str:
    text = str(message or '').strip().lower()
    combined = _routing_text(message, history).lower()
    asks_ai_audit = any((word in combined for word in ['ai kérés', 'ai keres', 'ai kérések', 'ai keresek', 'chat audit', 'ai audit'])) and any((word in combined for word in ['elemez', 'analiz', 'trend', 'context layer', 'context-layer', 'fejleszt']))
    if asks_ai_audit:
        return ai_audit_analysis_reply(context)
    asks_climate_power = any((word in text for word in ['klím', 'klima', 'gree', 'climate'])) and any((word in text for word in ['fogyaszt', 'teljesítmény', 'teljesitmeny', 'watt', 'kwh', 'energia', 'áram', 'aram']))
    if asks_climate_power:
        return climate_power_reply(text, context)
    asks_settings = any((word in text for word in ['beállítás', 'beallitas', 'paraméter', 'parameter', 'mód', 'mod', 'target', 'célhő', 'celho', 'venti', 'fan', 'általában', 'altalaban', 'használva', 'hasznalva']))
    climate_context = any((word in combined for word in ['klím', 'klima', 'gree', 'climate', 'climate_power']))
    if asks_settings and climate_context:
        climate = context.get('climate') if isinstance(context.get('climate'), dict) else {}
        climate_history = context.get('climate_history') if isinstance(context.get('climate_history'), dict) else {}
        schedules = context.get('climate_schedules') if isinstance(context.get('climate_schedules'), dict) else {}
        enabled = schedules.get('enabled_schedules') if isinstance(schedules.get('enabled_schedules'), list) else []
        lines = [f"Aktuális állapot: power={climate.get('power') or '-'}, mód={climate.get('mode') or '-'}, célhő={(climate.get('target_temperature') if climate.get('target_temperature') is not None else '-')} °C, fan={climate.get('fan_speed') or '-'}, aktuális hőmérséklet={(climate.get('current_temperature') if climate.get('current_temperature') is not None else '-')} °C."]
        if climate_history and climate_history.get('ok'):
            distributions = climate_history.get('distributions_7d') if isinstance(climate_history.get('distributions_7d'), dict) else {}
            numeric = climate_history.get('numeric_7d') if isinstance(climate_history.get('numeric_7d'), dict) else {}
            recent_changes = climate_history.get('recent_setting_changes_7d') if isinstance(climate_history.get('recent_setting_changes_7d'), list) else []
            lines.append('Historikus klíma paraméterek a climate_history blokkból:')
            for (key, label) in [('climate_power', 'power'), ('climate_mode', 'mód'), ('climate_fan_speed', 'fan')]:
                values = distributions.get(key) if isinstance(distributions.get(key), list) else []
                if values:
                    lines.append(f'- {label} 7 napos minták: ' + ', '.join((f"{item.get('value')} ({item.get('sample_count')})" for item in values[:4])))
            for (key, label) in [('climate_target_temperature', 'célhő'), ('climate_current_temperature', 'mért hő')]:
                item = numeric.get(key) if isinstance(numeric.get(key), dict) else {}
                if item:
                    lines.append(f"- {label} 7 nap: átlag {item.get('avg')}, min {item.get('min')}, max {item.get('max')}, minták {item.get('sample_count')}")
            if recent_changes:
                lines.append('Friss beállítás-változások: ' + '; '.join((f"{item.get('key')}={item.get('value')}" for item in recent_changes[:6])))
        else:
            lines.append(f"Historikus klíma paraméter idősor még nem elérhető: {climate_history.get('error') or 'nincs climate_history adat'}.")
        if enabled:
            lines.append(f'Engedélyezett klíma schedule szabályok ({len(enabled)} db):')
            for row in enabled[:7]:
                lines.append(f"- {row.get('label') or row.get('id')}: nap={row.get('day_of_week')}, idő={row.get('start_time')}, power={row.get('power')}, mód={row.get('mode')}, célhő={row.get('target_temperature')} °C, fan={row.get('fan_speed')}, státusz={row.get('schedule_status') or '-'}")
        else:
            lines.append('Nem látok engedélyezett klíma schedule szabályt az AI contextben.')
        lines.append('Szobahőmérő adatból nem következtetek klíma beállításokra, mert az nem ugyanaz az adatforrás.')
        return '\n'.join(lines)
    if asks_settings and (not climate_context) and not context_sections(message):
        return 'Pontosan melyik modul beállításaira gondolsz? Például klíma, öntözés, X10 robot, solar vagy power wall. Modulnév nélkül nem következtetek, mert könnyen rossz adatforrásból válaszolnék.'
    return ''

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

def _extended_context_reply(message, context=None, history=None):
    text = str(message or '').strip().lower()
    if not isinstance(context, dict) or not text:
        return ''
    combined = _routing_text(message, history or []).lower()
    asks_home_stats = 'hc stats' in text or 'home statistics' in text or 'homecontrol statistics' in text
    asks_climate_values = any((word in text for word in ['humidity', 'pár', 'para', 'temperature', 'hőmér', 'homersek', 'temp']))
    asks_moisture = any((word in text for word in ['moisture', 'talajnedv', 'talaj nedv', 'soil']))
    asks_weather = any((word in text for word in ['időjár', 'idojar', 'weather', 'eső', 'eso', 'csapad', 'tegnap', 'mai']))
    asks_irrigation_effect = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'reagált', 'reagalt', 'hatott', 'ciklus']))
    asks_irrigation_start_time = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'csöpögtet', 'csopogtet'])) and any((word in text for word in ['indult', 'kezd', 'start']))
    asks_irrigation_stop_time = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'csöpögtet', 'csopogtet', 'leáll', 'leallit'])) and any((word in text for word in ['mikor', 'leáll', 'leallit', 'állt le', 'utoljára', 'utoljara']))
    asks_irrigation_duration_distribution = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'csöpögtet', 'csopogtet'])) and any((word in text for word in ['90', 'rövidebb', 'rovidebb', 'hosszabb'])) and any((word in text for word in ['hányszor', 'hanyszor', 'mennyi', 'darab']))
    asks_irrigation_cycle_list = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'csöpögtet', 'csopogtet', 'ciklus'])) and any((word in text for word in ['sorold', 'felsorol', 'listáz', 'listaz', 'lista']))
    asks_todays_irrigation_summary = any((word in text for word in ['locsol', 'öntöz', 'ontoz', 'csöpögtet', 'csopogtet'])) and any((word in text for word in ['ma', 'mai', 'mesélj', 'meselj', 'összefoglal', 'osszefoglal']))
    focus = context_query_focus(context, message)
    matches = focus.get('home_statistics_sensor_matches') or []
    asks_hc_server_power = ('hc szerver' in text or 'homecontrol szerver' in text) and any((word in text for word in ['fogyaszt', 'teljesítmény', 'teljesitmeny', 'watt', 'kwh', 'energia', 'átlag', 'atlag', 'mesélj', 'meselj']))
    if asks_hc_server_power:
        server_power = context.get('server_power') if isinstance(context.get('server_power'), dict) else {}
        if not server_power or server_power.get('ok') is False:
            devices = context_value(context, 'power_wall', 'devices') or []
            match = next((item for item in devices if isinstance(item, dict) and 'hc szerver' in str(item.get('name') or '').strip().lower()), None)
            if match:
                return f"A HC szerver itt a Tuya fogyasztásmérős okoskonnektor, nem az AI szerver. A részletes 7/30 napos server_power összesítés most nincs az AI contextben, de a power_wall pillanatnyi adata alapján az aktuális teljesítménye {match.get('power_w', '-')} W, kapcsolóállapot: {match.get('switch', '-')}, státusz: {match.get('status', '-')}."
            return f"A HC szerver fogyasztásmérő adata nem elérhető az AI contextben: {server_power.get('error') or 'nincs server_power adat'}."
        device = server_power.get('device') if isinstance(server_power.get('device'), dict) else {}
        name = device.get('display_name') or device.get('entity_name') or 'HC szerver'
        avg_24h = server_power.get('avg_power_w_24h')
        avg_7d = server_power.get('avg_daily_energy_kwh_7d')
        avg_30d = server_power.get('avg_daily_energy_kwh_30d')
        today = server_power.get('today_energy_kwh')
        current = server_power.get('current_power_w')
        samples = server_power.get('sample_count_24h')
        return f"A {name} itt a Tuya fogyasztásmérős okoskonnektor, nem az AI szerver. Az utolsó 24 óra átlagos teljesítménye {(avg_24h if avg_24h is not None else '-')} W ({(samples if samples is not None else 0)} minta alapján). A 7 napos átlagos napi energiafogyasztás {(avg_7d if avg_7d is not None else '-')} kWh/nap, a 30 napos átlag {(avg_30d if avg_30d is not None else '-')} kWh/nap. Mai eddigi fogyasztás: {(today if today is not None else '-')} kWh, aktuális teljesítmény: {(current if current is not None else '-')} W."
    if asks_todays_irrigation_summary and (not asks_moisture) and (not asks_irrigation_cycle_list):
        cycles = [cycle for cycle in context_value(context, 'irrigation', 'analysis', 'cycles', 'recent') or [] if isinstance(cycle, dict)]
        first_started = cycle_start(cycles[0]) if cycles else None
        (today_date, day_label) = target_date_for_text('ma', first_started.tzinfo if first_started else timezone.utc)
        todays = [cycle for cycle in cycles if cycle_matches_date(cycle, today_date)]
        if not todays:
            return 'Ma nem látok naplózott locsolási/csöpögtetési ciklust az AI summary-ban.'
        lines = [f'Ma {len(todays)} naplózott locsolási/csöpögtetési ciklust látok:']
        for cycle in todays[:5]:
            lines.append(f"- {time_without_repeated_day(cycle.get('started_at'), day_label)} -> {time_without_repeated_day(cycle.get('ended_at'), day_label)}, hossz: {cycle.get('duration_min', '-')} perc, indítás: {source_label(cycle.get('start_source'), cycle.get('started_by'))}, leállítás: {stop_source_label(cycle.get('stop_source'))}, státusz: {status_label(cycle.get('status'))}.")
        pilot = context.get('irrigation_pilot') if isinstance(context.get('irrigation_pilot'), dict) else {}
        recommendation = pilot.get('recommendation') if isinstance(pilot.get('recommendation'), dict) else {}
        today_decision = pilot.get('today_decision') if isinstance(pilot.get('today_decision'), dict) else {}
        if recommendation or today_decision:
            mode = (pilot.get('config') or {}).get('mode') if isinstance(pilot.get('config'), dict) else recommendation.get('mode')
            rules = today_decision.get('triggered_rules') or recommendation.get('triggered_rules') or []
            status = today_decision.get('execution_status')
            reason = today_decision.get('reason') or recommendation.get('reason')
            lines.append(f"Pilot/scheduler szabály: mód {mode or '-'}, aktív szabályok {rules or []}, döntési státusz {status or '-'}, indok: {reason or '-'}.")
        moisture_rows = context_value(context, 'irrigation', 'analysis', 'moisture_24h') or []
        if moisture_rows:
            parts = []
            for item in moisture_rows[:3]:
                if isinstance(item, dict):
                    parts.append(f"{item.get('name')}: {item.get('latest_percent')}% ({hu_trend(item.get('trend_24h'))})")
            if parts:
                lines.append('Talajnedvesség 24h kép: ' + '; '.join(parts) + '.')
        lines.append('Fontos: a leállítás okát csak akkor lehet konkrét szabályhoz kötni, ha azt a pilot döntés vagy a session stop_payload/stop_policy is tartalmazza.')
        return '\n'.join(lines)
    if asks_irrigation_cycle_list and (not asks_moisture):
        period_key = requested_period_key(text)
        cycles_key = 'last_30d' if period_key == 'last_30d' else 'recent'
        cycles = [cycle for cycle in context_value(context, 'irrigation', 'analysis', 'cycles', cycles_key) or [] if isinstance(cycle, dict)]
        if not cycles:
            return f'Nem látok naplózott locsolási/csöpögtetési ciklusokat az {period_label(period_key)} időszakra.'
        period = context_value(context, 'irrigation', 'analysis', 'pump', 'periods', period_key) or {}
        lines = [f'{period_label(period_key, period).capitalize()} ciklusai ({len(cycles)} db):']
        lines.extend((cycle_line(cycle, index + 1) for (index, cycle) in enumerate(cycles)))
        return '\n'.join(lines)
    if asks_irrigation_duration_distribution and (not asks_moisture):
        period_key = requested_period_key(text)
        period = context_value(context, 'irrigation', 'analysis', 'pump', 'periods', period_key) or {}
        distribution = period.get('cycle_duration_distribution_90m') if isinstance(period, dict) else {}
        if not isinstance(distribution, dict) or not distribution:
            return 'Nem látok ciklus-időtartam eloszlást az AI summary-ban a kért időszakra.'
        total = period.get('cycle_count', 0)
        target = distribution.get('target_min', 90)
        tolerance = distribution.get('tolerance_min', 5)
        return f"Az {period_label(period_key, period)} alatt {total} naplózott locsolási/csöpögtetési ciklust látok. Kb. {target:g} percesnek a {target - tolerance:g}-{target + tolerance:g} perc közötti ciklusokat vettem: {distribution.get('near_target_count', 0)} ilyen volt. Rövidebb: {distribution.get('shorter_count', 0)}, hosszabb: {distribution.get('longer_count', 0)}. Az átlagos ciklushossz ebben az időszakban {period.get('cycle_avg_duration_min', '-')} perc, ezért az átlagot nem szabad úgy értelmezni, mintha a ciklusok többsége 90 perces lenne."
    if asks_irrigation_stop_time and (not asks_moisture) and (not asks_irrigation_start_time):
        cycles = [cycle for cycle in context_value(context, 'irrigation', 'analysis', 'cycles', 'recent') or [] if isinstance(cycle, dict)]
        manual_only = any((word in text for word in ['manuál', 'manual', 'kézi', 'kezi']))
        automatic_only = any((word in text for word in ['automata', 'automatikus', 'gép', 'gep', 'scheduler']))
        first_end = cycle_end(cycles[0]) if cycles else None
        (target_date, day_label) = target_date_for_text(text, first_end.tzinfo if first_end else timezone.utc)
        selected = [cycle for cycle in cycles if cycle.get('ended_at') and (not target_date or (cycle_end(cycle) and cycle_end(cycle).date() == target_date))]
        if manual_only:
            selected = [cycle for cycle in selected if cycle.get('stop_source') == 'manual' or str(cycle.get('status') or '').lower() in {'stopped', 'manual_stopped'}]
        elif automatic_only:
            selected = [cycle for cycle in selected if cycle.get('stop_source') == 'automatic' or str(cycle.get('status') or '').lower() == 'auto_stopped']
        if not selected:
            qualifier = 'manuális ' if manual_only else 'automatikus ' if automatic_only else ''
            when = f'{day_label} ' if day_label else ''
            return f'Nem látok {when}{qualifier}locsolási leállítást az AI summary legutóbbi ciklusai között.'
        cycle = selected[0]
        return f"A legutóbbi {stop_source_label(cycle.get('stop_source'))} {human_time(cycle.get('ended_at'))}-kor volt. A ciklus {human_time(cycle.get('started_at'))}-kor indult, indítás módja: {source_label(cycle.get('start_source'), cycle.get('started_by'))}, időtartam: {cycle.get('duration_min', '-')} perc, státusz: {status_label(cycle.get('status'))}."
    if asks_irrigation_start_time and (not asks_moisture):
        cycles = context_value(context, 'irrigation', 'analysis', 'cycles', 'recent') or []
        first_started = cycle_start(cycles[0]) if cycles else None
        (target_date, day_label) = target_date_for_text(text, first_started.tzinfo if first_started else timezone.utc)
        selected = [cycle for cycle in cycles if isinstance(cycle, dict) and cycle_matches_date(cycle, target_date)] if target_date else [cycle for cycle in cycles if isinstance(cycle, dict)][:1]
        if not selected:
            when = day_label or 'a kért időszakban'
            return f'{when.capitalize()} nem látok naplózott csöpögtetési/locsolási ciklust az AI contextben.'
        lines = []
        prefix = day_label.capitalize() if day_label else 'A legutóbbi naplózott ciklus'
        if len(selected) == 1:
            cycle = selected[0]
            end_text = human_time(cycle.get('ended_at'))
            if end_text == '-':
                approx = approximate_cycle_end(cycle)
                end_part = f"A leállási időpont nincs külön a summary-ban; a {cycle.get('duration_min', '-')} perces naplózott időtartam alapján kb. {time_without_repeated_day(approx, day_label)} körül fejeződhetett be."
            else:
                end_part = f"Leállás: {time_without_repeated_day(cycle.get('ended_at'), day_label)}."
            source_part = source_label(cycle.get('start_source'), cycle.get('started_by'))
            return f"{prefix} {time_without_repeated_day(cycle.get('started_at'), day_label)}-kor indult. Indítás módja: {source_part}. Naplózott időtartam: {cycle.get('duration_min', '-')} perc, státusz: {status_label(cycle.get('status'))}. {end_part}"
        lines.append(f'{prefix} {len(selected)} naplózott csöpögtetési/locsolási ciklust látok:')
        for cycle in selected[:5]:
            source_part = source_label(cycle.get('start_source'), cycle.get('started_by'))
            stop_part = f", leállás {human_time(cycle.get('ended_at'))}" if cycle.get('ended_at') else ''
            lines.append(f"- indulás {human_time(cycle.get('started_at'))}{stop_part}, {source_part}, időtartam {cycle.get('duration_min', '-')} perc, státusz {status_label(cycle.get('status'))}.")
        return '\n'.join(lines)
    if asks_home_stats and asks_climate_values and (len(matches) == 1):
        sensor = matches[0]
        name = sensor.get('display_name') or sensor.get('name') or 'selected sensor'
        temp = sensor.get('latest_temperature_c')
        humidity = sensor.get('latest_humidity_percent')
        abs_humidity = sensor.get('latest_absolute_humidity_g_m3')
        temp_trend = (sensor.get('temperature') or {}).get('trend_24h') or '-'
        humidity_trend = (sensor.get('humidity') or {}).get('trend_24h') or '-'
        ts = human_time(sensor.get('latest_ts'))
        return f"{name} HC Stats értékei: hőmérséklet {(temp if temp is not None else '-')} °C, páratartalom {(humidity if humidity is not None else '-')}%, abszolút páratartalom {(abs_humidity if abs_humidity is not None else '-')} g/m3. 24 órás trend: hőmérséklet {temp_trend}, páratartalom {humidity_trend}. Utolsó minta: {ts}."
    if asks_moisture:
        rows = context_value(context, 'irrigation', 'analysis', 'moisture_24h') or []
        if rows:
            selected = []
            for item in rows:
                if not isinstance(item, dict):
                    continue
                names = [str(item.get('name') or ''), str(item.get('entity_id') or '')]
                if any((name and name.lower() in text for name in names)):
                    selected.append(item)
            if not selected:
                selected = [item for item in rows if isinstance(item, dict)]
            weather = context.get('weather') or {}
            pump_today = context_value(context, 'irrigation', 'analysis', 'pump', 'today') or {}
            cycles = context_value(context, 'irrigation', 'analysis', 'cycles', 'recent') or []
            latest_cycle = cycles[0] if cycles and isinstance(cycles[0], dict) else {}
            title = 'Moisture szenzor 24 órás elemzése:' if len(selected) == 1 else 'Moisture szenzorok 24 órás képe:'
            lines = [title]
            if asks_weather:
                lines.append(f"Időjárási háttér: elmúlt 24h csapadék {weather.get('rain_24h_mm', '-')} mm, előrejelzett 24h csapadék {weather.get('forecast_rain_24h_mm', '-')} mm, csapadék valószínűség {weather.get('pop_percent', '-')}%.")
                lines.append('Külön tegnapi napi bontás nincs az AI contextben, ezért itt a 24 órás összesítésből és a mai/előrejelzett adatokból lehet következtetni.')
            if asks_irrigation_effect:
                lines.append(f"Öntözőrendszer háttér: tartályos rendszer, ahol a pumpa a tartályt tölti, a csap/szelep pedig a csöpögtető kört indítja. Mai mért pumpafutás tartálytöltéshez: {pump_today.get('runtime_min', '-')} perc, pumpa fogyasztás {pump_today.get('watt_hours', '-')} Wh. Legutóbbi naplózott csöpögtetési/locsolási ciklus: {latest_cycle.get('duration_min', '-')} perc, státusz {latest_cycle.get('status', '-')}, indulás {human_time(latest_cycle.get('started_at'))}.")
            for item in selected[:6]:
                if not isinstance(item, dict):
                    continue
                name = item.get('name') or item.get('entity_id') or 'moisture'
                latest = item.get('latest_percent')
                avg = item.get('avg_24h_percent')
                trend = item.get('trend_24h') or '-'
                delta = item.get('delta_24h_percent')
                samples = item.get('sample_count')
                lines.append(f'- {name}: legutóbbi {latest}%, 24h átlag {avg}%, trend {hu_trend(trend)}, változás {delta}%, minták {samples}.')
                if len(selected) == 1 and asks_irrigation_effect:
                    responses = item.get('watering_response') or []
                    response = responses[0] if responses and isinstance(responses[0], dict) else {}
                    if response:
                        rise = response.get('rise_from_pre_min_percent')
                        lines.append(f"Locsolási reakció: a ciklus előtti minimum {response.get('pre_cycle_min_percent', '-')}% volt ({human_time(response.get('pre_cycle_min_ts'))}), a ciklus utáni/atti csúcs {response.get('peak_after_start_percent', '-')}% ({human_time(response.get('peak_ts'))}). Emelkedés: {(rise if rise is not None else '-')} százalékpont, csúcsig eltelt idő: {response.get('minutes_start_to_peak', '-')} perc.")
                        if rise is not None and float(rise) >= 10:
                            reaction = 'Ez erős és jól látható nedvességválasz, tehát a csöpögtetési ciklus ezen a szenzoron hatékonynak látszik.'
                        elif rise is not None and float(rise) >= 5:
                            reaction = 'Ez mérsékelt, de látható nedvességválasz, a csöpögtetés hatása valószínűleg megjelent a szenzoron.'
                        elif rise is not None and float(rise) > 0:
                            reaction = 'Ez gyenge nedvességválasz; lehet hatás, de nem erős.'
                        else:
                            reaction = 'A ciklushoz kötött emelkedés nem látszik egyértelműen.'
                    elif delta is None:
                        reaction = 'A locsolásra adott reakció nem ítélhető meg, mert nincs elég ciklushoz kötött minta.'
                    elif float(delta) > 1:
                        reaction = 'A 24 órás ablakban emelkedés látszik, ez összefügghet a locsolással.'
                    elif float(delta) < -1:
                        reaction = 'A 24 órás ablakban csökkenés látszik, vagyis nincs tartós emelkedés.'
                    else:
                        reaction = 'A 24 órás összkép stabil, de ez önmagában nem zárja ki a ciklus utáni rövidebb emelkedést.'
                    lines.append(f'Értelmezés: {reaction}')
                    if response and response.get('cycle_duration_min') and (response.get('peak_after_start_percent') is not None):
                        lines.append('Ha magasabb talajnedvességi csúcsot szeretnél, érdemes óvatosan hosszabb csöpögtetési időt próbálni, majd ugyanígy a ciklus előtti minimumot és utáni csúcsot összevetni.')
            if len(selected) == 1:
                lines.append('Mire figyelj: ennél a szenzornál a ciklus előtti minimum és a ciklus utáni csúcs sokkal beszédesebb, mint a teljes 24 órás első-utolsó trend.')
            else:
                lines.append('Mire figyelj: az alacsonyabb vagy gyorsan eső értékeket kezeld fontosabb jelzésként. A moisture változás összefügghet a locsolással, de önmagában nem bizonyít közvetlen ok-okozatot.')
            lines.append('Összegzés: a trendet, a változás mértékét, a mintaszámot, a locsolási ciklusnaplót és a tartálytöltési pumpaadatot együtt érdemes nézni, nem csak az utolsó értéket.')
            return '\n'.join(lines)
    return ''

def direct_context_reply(message, context=None, history=None):
    if not isinstance(context, dict):
        return ""
    reply = _backend_context_reply(message, context, history or [])
    if not any(name in context for name in ('irrigation', 'home_statistics', 'server_power', 'weather')):
        return reply
    return reply or _extended_context_reply(message, context, history or [])

