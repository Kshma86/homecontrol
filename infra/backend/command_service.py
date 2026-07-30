import time
from typing import Any, Callable, Dict, Iterable, List, Optional


class CommandService:
    def __init__(self, context_service_getter: Callable[[], Any]):
        self.context_service_getter = context_service_getter
        self.events = []
        self.max_events = 300

    def normalize_sections(self, sections: Iterable[str]) -> List[str]:
        unique_sections = []
        for section in sections:
            clean = str(section or "").strip()
            if clean and clean not in unique_sections:
                unique_sections.append(clean)
        return unique_sections

    def invalidate(self, *sections: str, source: str = "command") -> List[str]:
        unique_sections = self.normalize_sections(sections)
        if not unique_sections:
            return []
        service = self.context_service_getter()
        for section in unique_sections:
            service.invalidate(section)
        self.record_event(source, unique_sections)
        return unique_sections

    def meta(self, *sections: str, source: str = "command") -> Dict[str, Any]:
        unique_sections = self.normalize_sections(sections)
        return {
            "source": source,
            "invalidated": unique_sections,
            "read_after": [f"/api/context/{section}" for section in unique_sections],
        }

    def invalidate_and_meta(self, *sections: str, source: str = "command") -> Dict[str, Any]:
        invalidated = self.invalidate(*sections, source=source)
        return self.meta(*invalidated, source=source)

    def observe_mqtt_topic(self, topic: str):
        sections = self.sections_for_mqtt_topic(topic)
        if sections:
            self.invalidate(*sections, source=f"mqtt:{topic}")
        return sections

    def sections_for_mqtt_topic(self, topic: str):
        text = str(topic or "")
        sections = []
        if "/irrigation/" in text or text.startswith("homecontrol/tele/irrigation/") or text.startswith("homecontrol/stat/irrigation/"):
            sections.extend(["irrigation", "irrigation_pilot"])
        if text.startswith("zigbee/0xa4c13844a0908898") or text.startswith("zigbee/0xa4c1387594b09c83"):
            sections.extend(["irrigation", "irrigation_pilot", "irrigation_statistics"])
        if "xiaomi_x10" in text:
            sections.append("robot")
        if "gree_climate" in text:
            sections.extend(["climate", "climate_power_history"])
        if "/tuya/" in text or text.startswith("tuya/"):
            sections.extend(["tuya", "power_wall"])
        return self.normalize_sections(sections)

    def record_event(self, source: str, sections: Iterable[str]):
        event = {
            "source": source,
            "sections": self.normalize_sections(sections),
            "ts": time.time(),
        }
        self.events.insert(0, event)
        self.events = self.events[: self.max_events]
        return event

    def recent_events(self, limit: Optional[int] = None):
        size = 50 if limit is None else max(1, min(int(limit), self.max_events))
        return self.events[:size]
