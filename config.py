import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

VM_SPECS = (
    {
        "id": "randomforest-vm",
        "label_key": "GLANCES_RANDOM_FOREST_LABEL",
        "role": "Network flow · QoS · resource",
    },
    {
        "id": "lightgbm-vm",
        "label_key": "GLANCES_LIGHTGBM_LABEL",
        "role": "Resource host",
    },
    {
        "id": "fail2ban-vm",
        "label_key": "GLANCES_FAIL2BAN_LABEL",
        "role": "Resource host",
    },
)
VM_IDS = tuple(spec["id"] for spec in VM_SPECS)
DEFAULT_VM = "randomforest-vm"


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _text(name, default=""):
    return (os.getenv(name) or default).strip()


class Config:
    SECRET_KEY = _text("SECRET_KEY", "dev-only-change-me")
    DATABASE = _text("DATABASE_PATH", str(BASE_DIR / "instance" / "dashboard.db"))

    DATA_MODE = _text("DATA_MODE", "demo").lower()
    POLL_INTERVAL_MS = _int("POLL_INTERVAL_MS", 5000)
    STATS_WINDOW_SECONDS = _int("STATS_WINDOW_SECONDS", 300)
    HISTORY_MAX_POINTS = _int("HISTORY_MAX_POINTS", 120)
    API_TIMEOUT_SECONDS = _int("API_TIMEOUT_SECONDS", 4)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 8))
    CSRF_ENABLED = _bool(os.getenv("CSRF_ENABLED"), True)

    API_BASE_URL = _text("API_BASE_URL", "http://localhost:5000")
    LIGHTGBM_API_URL = _text("LIGHTGBM_API_URL")
    RANDOM_FOREST_API_URL = _text("RANDOM_FOREST_API_URL")
    FAIL2BAN_API_URL = _text("FAIL2BAN_API_URL")
    ATTACK_HISTORY_API_URL = _text("ATTACK_HISTORY_API_URL")
    ATTACK_HISTORY_API_TOKEN = _text("ATTACK_HISTORY_API_TOKEN")
    FLOW_FEATURES_API_URL = _text("FLOW_FEATURES_API_URL")
    FLOW_FEATURES_API_TOKEN = _text("FLOW_FEATURES_API_TOKEN")
    FLOW_FEATURES_LIGHTGBM_URL = _text("FLOW_FEATURES_LIGHTGBM_URL")
    FLOW_FEATURES_RANDOM_FOREST_URL = _text("FLOW_FEATURES_RANDOM_FOREST_URL")
    FLOW_FEATURES_FAIL2BAN_URL = _text("FLOW_FEATURES_FAIL2BAN_URL")

    GLANCES_LIGHTGBM_URL = _text("GLANCES_LIGHTGBM_URL")
    GLANCES_RANDOM_FOREST_URL = _text("GLANCES_RANDOM_FOREST_URL")
    GLANCES_FAIL2BAN_URL = _text("GLANCES_FAIL2BAN_URL")
    GLANCES_LIGHTGBM_LABEL = _text("GLANCES_LIGHTGBM_LABEL", "lightgbm-vm")
    GLANCES_RANDOM_FOREST_LABEL = _text("GLANCES_RANDOM_FOREST_LABEL", "randomforest-vm")
    GLANCES_FAIL2BAN_LABEL = _text("GLANCES_FAIL2BAN_LABEL", "fail2ban-vm")

    QOS_HISTORY_POINTS = _int("QOS_HISTORY_POINTS", 240)
    QOS_VM = _text("QOS_VM", DEFAULT_VM)

    IPERF3_ENABLED = _bool(os.getenv("IPERF3_ENABLED"), False)
    IPERF3_RESULT_URL = _text("IPERF3_RESULT_URL")
    IPERF3_BINARY = _text("IPERF3_BINARY", "iperf3")
    IPERF3_CLIENT_HOST = _text("IPERF3_CLIENT_HOST")
    IPERF3_SERVER_HOST = _text("IPERF3_SERVER_HOST")
    IPERF3_PORT = _int("IPERF3_PORT", 5201)
    IPERF3_BANDWIDTH = _text("IPERF3_BANDWIDTH", "100M")
    IPERF3_OMIT_SECONDS = _int("IPERF3_OMIT_SECONDS", 1)
    IPERF3_TEST_PROTOCOL = _text("IPERF3_TEST_PROTOCOL", "udp")
    IPERF3_TEST_DURATION_SECONDS = _int("IPERF3_TEST_DURATION_SECONDS", 10)
    IPERF3_TEST_INTERVAL_SECONDS = _int("IPERF3_TEST_INTERVAL_SECONDS", 60)
    DELAY_API_URL = _text("DELAY_API_URL")
    PING_BINARY = _text("PING_BINARY", "ping")
    PING_TARGET_HOST = _text("PING_TARGET_HOST")
    PING_COUNT = _int("PING_COUNT", 5)
    PING_TIMEOUT_MS = _int("PING_TIMEOUT_MS", 1000)

    TELEGRAM_BOT_TOKEN = _text("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = _text("TELEGRAM_CHAT_ID")
    TELEGRAM_API_BASE = _text("TELEGRAM_API_BASE", "https://api.telegram.org")
