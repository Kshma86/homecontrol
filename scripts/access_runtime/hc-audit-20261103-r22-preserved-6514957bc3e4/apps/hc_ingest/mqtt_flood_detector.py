from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass(frozen=True)
class FloodTransition:
    topic_base: str
    active: bool
    severity: str
    window_count: int
    messages_per_minute: float
    first_exceeded_at: Optional[float]
    detected_at: Optional[float]
    resolved_at: Optional[float]


@dataclass
class _TopicWindow:
    timestamps: Deque[float] = field(default_factory=deque)
    warning_since: Optional[float] = None
    critical_since: Optional[float] = None
    recovery_since: Optional[float] = None
    active_severity: Optional[str] = None
    detected_at: Optional[float] = None


class MqttFloodDetector:
    """Tracks raw MQTT message rates before HC measurement thinning."""

    def __init__(
        self,
        warning_per_minute: int = 60,
        critical_per_minute: int = 180,
        sustain_seconds: float = 120.0,
        recovery_seconds: float = 120.0,
        window_seconds: float = 60.0,
    ):
        if warning_per_minute <= 0 or critical_per_minute <= warning_per_minute:
            raise ValueError("invalid MQTT flood thresholds")
        self.warning_per_minute = warning_per_minute
        self.critical_per_minute = critical_per_minute
        self.sustain_seconds = sustain_seconds
        self.recovery_seconds = recovery_seconds
        self.window_seconds = window_seconds
        self._topics: Dict[str, _TopicWindow] = {}

    @staticmethod
    def device_topic_base(topic: str) -> Optional[str]:
        parts = topic.split("/")
        if len(parts) != 2 or parts[0] != "zigbee" or parts[1] == "bridge":
            return None
        return topic

    def observe(self, topic: str, timestamp: float) -> List[FloodTransition]:
        topic_base = self.device_topic_base(topic)
        if not topic_base:
            return []
        window = self._topics.setdefault(topic_base, _TopicWindow())
        window.timestamps.append(timestamp)
        return self._evaluate_topic(topic_base, window, timestamp)

    def sweep(self, timestamp: float) -> List[FloodTransition]:
        transitions: List[FloodTransition] = []
        for topic_base, window in list(self._topics.items()):
            transitions.extend(self._evaluate_topic(topic_base, window, timestamp))
            if not window.timestamps and window.active_severity is None:
                del self._topics[topic_base]
        return transitions

    def snapshot(self, topic_base: str, timestamp: float) -> Optional[FloodTransition]:
        window = self._topics.get(topic_base)
        if not window:
            return None
        self._trim(window, timestamp)
        return self._transition(topic_base, window, timestamp, resolved_at=None)

    def _trim(self, window: _TopicWindow, timestamp: float) -> None:
        cutoff = timestamp - self.window_seconds
        while window.timestamps and window.timestamps[0] <= cutoff:
            window.timestamps.popleft()

    def _evaluate_topic(self, topic_base: str, window: _TopicWindow, timestamp: float) -> List[FloodTransition]:
        self._trim(window, timestamp)
        count = len(window.timestamps)

        window.warning_since = self._threshold_since(
            count >= self.warning_per_minute, window.warning_since, timestamp
        )
        window.critical_since = self._threshold_since(
            count >= self.critical_per_minute, window.critical_since, timestamp
        )

        desired: Optional[str] = None
        if window.critical_since is not None and timestamp - window.critical_since >= self.sustain_seconds:
            desired = "critical"
        elif window.warning_since is not None and timestamp - window.warning_since >= self.sustain_seconds:
            desired = "warning"

        if desired is not None:
            window.recovery_since = None
            if desired != window.active_severity:
                if window.detected_at is None:
                    window.detected_at = timestamp
                window.active_severity = desired
                return [self._transition(topic_base, window, timestamp, resolved_at=None)]
            return []

        if window.active_severity is None:
            window.recovery_since = None
            return []

        if count >= self.warning_per_minute:
            window.recovery_since = None
            return []

        if window.recovery_since is None:
            window.recovery_since = timestamp
            return []
        if timestamp - window.recovery_since < self.recovery_seconds:
            return []

        transition = self._transition(topic_base, window, timestamp, resolved_at=timestamp)
        window.active_severity = None
        window.detected_at = None
        window.recovery_since = None
        return [transition]

    @staticmethod
    def _threshold_since(is_above: bool, previous: Optional[float], timestamp: float) -> Optional[float]:
        if not is_above:
            return None
        return timestamp if previous is None else previous

    def _transition(
        self,
        topic_base: str,
        window: _TopicWindow,
        timestamp: float,
        resolved_at: Optional[float],
    ) -> FloodTransition:
        count = len(window.timestamps)
        severity = "resolved" if resolved_at is not None else (window.active_severity or "resolved")
        first_exceeded = window.critical_since if severity == "critical" else window.warning_since
        return FloodTransition(
            topic_base=topic_base,
            active=resolved_at is None and window.active_severity is not None,
            severity=severity,
            window_count=count,
            messages_per_minute=round(count * 60.0 / self.window_seconds, 2),
            first_exceeded_at=first_exceeded,
            detected_at=window.detected_at,
            resolved_at=resolved_at,
        )
