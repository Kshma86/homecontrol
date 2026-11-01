from datetime import datetime
from typing import Any


def validate_schedule_time(value: Any, field: str, normalize_text) -> str:
    text = normalize_text(value)
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        raise ValueError(f"{field} must be HH:MM")
    return parsed.strftime("%H:%M")


def text_upper(value: Any) -> str:
    return str(value or "").upper()


def reaction_current_active(to_float, value: Any) -> bool:
    return (to_float(value, 0) or 0) > 0.01
