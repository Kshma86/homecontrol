"""HC-41 MQTT credentials; mirrored verbatim into independent build contexts."""
import os
from pathlib import Path


def configure_mqtt_auth(client, *, prefix="MQTT", fallback=None):
    """Configure before connect; invalid explicit credentials never become anonymous.

    No credentials preserves the existing deployment until AUTH_REQUIRED is enabled.
    A password file takes precedence only when no plaintext password was supplied.
    """
    names = [prefix] if prefix == "MQTT" else [prefix, "MQTT"]
    configured = None
    for name in names:
        keys = (name + "_USERNAME", name + "_USER", name + "_PASSWORD", name + "_PASSWORD_FILE")
        if any(key in os.environ for key in keys):
            configured = name
            break
    required = any(os.getenv(name + "_AUTH_REQUIRED", "").lower() in ("1", "true", "yes") for name in names)
    if configured:
        username = os.getenv(configured + "_USERNAME", os.getenv(configured + "_USER", ""))
        password = os.getenv(configured + "_PASSWORD")
        path = os.getenv(configured + "_PASSWORD_FILE")
        if password is not None and path:
            raise ValueError("MQTT password and password file are mutually exclusive")
        if path:
            try:
                with Path(path).open(encoding="utf-8") as stream:
                    raw = stream.read(4098)
                    if len(raw) > 4097:
                        raise ValueError("MQTT password file exceeds size limit")
                    password = raw.removesuffix("\n")
            except (OSError, UnicodeError):
                raise ValueError("MQTT password file cannot be read") from None
    elif fallback:
        username, password = fallback
    else:
        username, password = None, None
    if not configured and not username and not password and not required:
        return False
    if not isinstance(username, str) or not username or any(c in username for c in "\r\n\0"):
        raise ValueError("MQTT username is required")
    if not isinstance(password, str) or not password or len(password) > 4096 or any(c in password for c in "\r\n\0"):
        raise ValueError("MQTT password is missing or invalid")
    client.username_pw_set(username, password)
    return True
