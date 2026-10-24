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
        "role": "Network flow · QoS · resource",
    },
    {
        "id": "fail2ban-vm",
        "label_key": "GLANCES_FAIL2BAN_LABEL",
        "role": "Resource · QoS",
        "traffic": False,
    },
)
VM_IDS = tuple(spec["id"] for spec in VM_SPECS)
VM_TRAFFIC = {spec["id"]: spec.get("traffic", True) for spec in VM_SPECS}
DEFAULT_VM = "randomforest-vm"

CHART_RANGES = {"5m": 300, "30m": 1800, "1h": 3600}
CHART_RANGE_LABELS = {"5m": "5 menit", "30m": "30 menit", "1h": "1 jam"}
DEFAULT_CHART_RANGE = "5m"

# Target pengukuran QoS per VM (host yang diukur ping & iperf3).
# Diturunkan dari VM_HOST / RF_VM_HOST supaya hanya ada satu tempat per IP.
QOS_TARGET_HOSTS = {
    "lightgbm-vm": os.getenv("VM_HOST", "").strip(),
    "randomforest-vm": os.getenv("RF_VM_HOST", "").strip(),
    "fail2ban-vm": os.getenv("FAIL2BAN_VM_HOST", "").strip(),
}


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
    HISTORY_MAX_POINTS = _int("HISTORY_MAX_POINTS", 900)
    API_TIMEOUT_SECONDS = _int("API_TIMEOUT_SECONDS", 4)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("SESSION_LIFETIME_HOURS", 8))
    CSRF_ENABLED = _bool(os.getenv("CSRF_ENABLED"), True)

    API_BASE_URL = _text("API_BASE_URL", "http://localhost:5000")
    LIGHTGBM_API_URL = _text("LIGHTGBM_API_URL")
    LIGHTGBM_BLOCKED_API_URL = _text("LIGHTGBM_BLOCKED_API_URL")
    LIGHTGBM_API_TOKEN = _text("LIGHTGBM_API_TOKEN")
    RANDOM_FOREST_API_URL = _text("RANDOM_FOREST_API_URL")
    RANDOM_FOREST_BLOCKED_API_URL = _text("RANDOM_FOREST_BLOCKED_API_URL")
    RANDOM_FOREST_API_TOKEN = _text("RANDOM_FOREST_API_TOKEN")
    FAIL2BAN_VM_HOST = _text("FAIL2BAN_VM_HOST")
    FAIL2BAN_API_URL = _text("FAIL2BAN_API_URL")
    FAIL2BAN_ATTACKS_API_URL = _text("FAIL2BAN_ATTACKS_API_URL")
    FAIL2BAN_API_TOKEN = _text("FAIL2BAN_API_TOKEN")
    ATTACK_HISTORY_API_URL = _text("ATTACK_HISTORY_API_URL")
    ATTACK_HISTORY_API_TOKEN = _text("ATTACK_HISTORY_API_TOKEN")
    ATTACK_HISTORY_EXTRA_API_URLS = _text("ATTACK_HISTORY_EXTRA_API_URLS")
    ATTACK_HISTORY_EXTRA_API_TOKENS = _text("ATTACK_HISTORY_EXTRA_API_TOKENS")
    FLOW_FEATURES_API_URL = _text("FLOW_FEATURES_API_URL")
    FLOW_FEATURES_API_TOKEN = _text("FLOW_FEATURES_API_TOKEN")
    FLOW_FEATURES_LIGHTGBM_TOKEN = _text("FLOW_FEATURES_LIGHTGBM_TOKEN")
    FLOW_FEATURES_RANDOM_FOREST_TOKEN = _text("FLOW_FEATURES_RANDOM_FOREST_TOKEN")
    FLOW_FEATURES_FAIL2BAN_TOKEN = _text("FLOW_FEATURES_FAIL2BAN_TOKEN")
    FLOW_FEATURES_LIGHTGBM_URL = _text("FLOW_FEATURES_LIGHTGBM_URL")
    FLOW_FEATURES_RANDOM_FOREST_URL = _text("FLOW_FEATURES_RANDOM_FOREST_URL")
    FLOW_FEATURES_FAIL2BAN_URL = _text("FLOW_FEATURES_FAIL2BAN_URL")

    GLANCES_LIGHTGBM_URL = _text("GLANCES_LIGHTGBM_URL")
    GLANCES_RANDOM_FOREST_URL = _text("GLANCES_RANDOM_FOREST_URL")
    GLANCES_FAIL2BAN_URL = _text("GLANCES_FAIL2BAN_URL")
    GLANCES_LIGHTGBM_LABEL = _text("GLANCES_LIGHTGBM_LABEL", "lightgbm-vm")
    GLANCES_RANDOM_FOREST_LABEL = _text("GLANCES_RANDOM_FOREST_LABEL", "randomforest-vm")
    GLANCES_FAIL2BAN_LABEL = _text("GLANCES_FAIL2BAN_LABEL", "fail2ban-vm")

    QOS_HISTORY_POINTS = _int("QOS_HISTORY_POINTS", 480)
    QOS_VM = _text("QOS_VM", DEFAULT_VM)
    QOS_VMS = _text("QOS_VMS")
    QOS_TARGETS = QOS_TARGET_HOSTS
    QOS_AUTO_ENABLED = _bool(os.getenv("QOS_AUTO_ENABLED"), False)
    QOS_AUTO_INTERVAL_SECONDS = _int("QOS_AUTO_INTERVAL_SECONDS", 5)
    QOS_AUTO_METRICS = _text("QOS_AUTO_METRICS", "ping,iperf3")
    QOS_AUTO_IPERF3_DURATION_SECONDS = _int("QOS_AUTO_IPERF3_DURATION_SECONDS", 0)
    QOS_AUTO_IPERF3_BANDWIDTH = _text("QOS_AUTO_IPERF3_BANDWIDTH")
    QOS_AUTO_IPERF3_COOLDOWN_SECONDS = _int("QOS_AUTO_IPERF3_COOLDOWN_SECONDS", 2)
    QOS_AUTO_IPERF3_PROTOCOL = _text("QOS_AUTO_IPERF3_PROTOCOL", "tcp")
    QOS_AUTO_LOSS_ENABLED = _bool(os.getenv("QOS_AUTO_LOSS_ENABLED"), True)
    QOS_AUTO_LOSS_DURATION_SECONDS = _int("QOS_AUTO_LOSS_DURATION_SECONDS", 2)
    QOS_AUTO_LOSS_BANDWIDTH = _text("QOS_AUTO_LOSS_BANDWIDTH", "1M")
    QOS_AUTO_LOSS_INTERVAL_SECONDS = _int("QOS_AUTO_LOSS_INTERVAL_SECONDS", 10)
    QOS_AUTO_LOSS_PORT = _int("QOS_AUTO_LOSS_PORT", 5202)
    # Sumber metrik QoS: "vm" = angka hasil probe in-VM (link yang dipakai ML),
    # "laptop" = probe dari laptop ke VM lewat jaringan lab.
    QOS_SOURCE_MODE = _text("QOS_SOURCE_MODE", "vm")
    # Probe dari laptop hanya dipakai saat sumber metrik adalah laptop.
    QOS_LOCAL_PROBE = _bool(os.getenv("QOS_LOCAL_PROBE"), False)
    # Interval probe in-VM (detik), mengikuti timer qos-probe.timer di VM.
    QOS_PROBE_INTERVAL_SECONDS = _int("QOS_PROBE_INTERVAL_SECONDS", 10)

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
    IPERF3_TIMEOUT_MARGIN_SECONDS = _int("IPERF3_TIMEOUT_MARGIN_SECONDS", 30)
    IPERF3_TEST_INTERVAL_SECONDS = _int("IPERF3_TEST_INTERVAL_SECONDS", 60)
    DELAY_API_URL = _text("DELAY_API_URL")
    PING_BINARY = _text("PING_BINARY", "ping")
    PING_TARGET_HOST = _text("PING_TARGET_HOST")
    PING_COUNT = _int("PING_COUNT", 5)
    PING_TIMEOUT_MS = _int("PING_TIMEOUT_MS", 1000)

    TELEGRAM_BOT_TOKEN = _text("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = _text("TELEGRAM_CHAT_ID")
    TELEGRAM_API_BASE = _text("TELEGRAM_API_BASE", "https://api.telegram.org")
    TELEGRAM_BLOCK_NOTIFY_ENABLED = _bool(
        os.getenv("TELEGRAM_BLOCK_NOTIFY_ENABLED"), False
    )
