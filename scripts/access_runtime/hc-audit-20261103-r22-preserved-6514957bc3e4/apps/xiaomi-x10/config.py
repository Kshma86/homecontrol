import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def env_str(name, default):
    return os.environ.get(name, default)


def env_int(name, default):
    return int(os.environ.get(name, str(default)))


def env_path(name, default):
    return Path(os.environ.get(name, str(default))).expanduser()


MQTT_HOST = env_str("X10_MQTT_HOST", "192.168.1.133")
MQTT_PORT = env_int("X10_MQTT_PORT", 1883)
BASE_TOPIC = env_str("X10_BASE_TOPIC", "homecontrol/xiaomi_x10")

ROBOT_IP = env_str("X10_ROBOT_IP", "192.168.1.157")
ROBOT_TOKEN = env_str("X10_ROBOT_TOKEN", "")

MIIOCLI = env_path("X10_MIIOCLI", Path.home() / ".local/bin/miiocli")
MAP_SCRIPT = env_path("X10_MAP_SCRIPT", BASE_DIR / "xiaomi_x10_map.py")
MAP_OUTPUT_DIR = env_path("X10_MAP_OUTPUT_DIR", BASE_DIR / "x10_maps")
MAPS_INDEX = env_path("X10_MAPS_INDEX", MAP_OUTPUT_DIR / "maps_index.json")
XIAOMI_CLOUD_AUTH = env_path("X10_XIAOMI_CLOUD_AUTH", MAP_OUTPUT_DIR / "xiaomi_cloud_auth.json")
CAPTURE_DIR = env_path("X10_CAPTURE_DIR", MAP_OUTPUT_DIR / "captures")

XIAOMI_CLOUD_COUNTRY = env_str("X10_XIAOMI_CLOUD_COUNTRY", "de")

APP_HOST = env_str("X10_APP_HOST", "0.0.0.0")
APP_PORT = env_int("X10_APP_PORT", 5050)
APP_DEBUG = env_str("X10_APP_DEBUG", "0").lower() in {"1", "true", "yes", "on"}

POLL_IDLE_SEC = env_int("X10_POLL_IDLE_SEC", 60)
POLL_CLEANING_SEC = env_int("X10_POLL_CLEANING_SEC", 10)
MAP_CHECK_CLEANING_SEC = env_int("X10_MAP_CHECK_CLEANING_SEC", 20)
MAP_CHECK_IDLE_SEC = env_int("X10_MAP_CHECK_IDLE_SEC", 60)
SCHEDULER_WATCH_SEC = env_int("X10_SCHEDULER_WATCH_SEC", 10)
CAPTURE_STATUS_SEC = env_int("X10_CAPTURE_STATUS_SEC", 5)
CAPTURE_MAP_SEC = env_int("X10_CAPTURE_MAP_SEC", 20)
CAPTURE_SCHEDULER_SEC = env_int("X10_CAPTURE_SCHEDULER_SEC", 30)

ROOM_CLEAN_TASK_ID = env_int("X10_ROOM_CLEAN_TASK_ID", 1)
ROOM_CLEAN_DELAY_MIN = env_int("X10_ROOM_CLEAN_DELAY_MIN", 2)
ROOM_CLEAN_SUCTION = env_int("X10_ROOM_CLEAN_SUCTION", 3)
ROOM_CLEAN_PARAM = env_int("X10_ROOM_CLEAN_PARAM", 3)
SET_MAP_SIID = env_int("X10_SET_MAP_SIID", 6)
SET_MAP_AIID = env_int("X10_SET_MAP_AIID", 2)

# Shared by the bridge and the map subprocess; never remove a held lock file.
MIIO_LOCK_FILE = env_path("X10_MIIO_LOCK_FILE", "/tmp/homecontrol-x10-miio.lock")
MIIO_TIMEOUT_SEC = env_int("X10_MIIO_TIMEOUT_SEC", 20)
MIIO_LOCK_TIMEOUT_SEC = env_int("X10_MIIO_LOCK_TIMEOUT_SEC", 30)
WATCHDOG_TIMEOUT_SEC = env_int("X10_WATCHDOG_TIMEOUT_SEC", 300)
WATCHDOG_CHECK_SEC = env_int("X10_WATCHDOG_CHECK_SEC", 5)
if min(MIIO_TIMEOUT_SEC, MIIO_LOCK_TIMEOUT_SEC, WATCHDOG_TIMEOUT_SEC, WATCHDOG_CHECK_SEC) <= 0:
    raise ValueError("X10 time limits must be positive seconds")
if WATCHDOG_CHECK_SEC >= WATCHDOG_TIMEOUT_SEC:
    raise ValueError("X10 watchdog check interval must be shorter than its timeout")
if WATCHDOG_TIMEOUT_SEC <= max(POLL_IDLE_SEC, POLL_CLEANING_SEC) + MIIO_LOCK_TIMEOUT_SEC + MIIO_TIMEOUT_SEC:
    raise ValueError("X10 watchdog timeout must exceed a poll interval plus a MIIO wait/command budget")
