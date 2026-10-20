import locale
import os
import re
import subprocess
import threading
from collections import deque

from utils import iso, utc_now

_AVG_PATTERNS = (
    re.compile(r"rtt\s+min/avg/max(?:/mdev)?\s*=\s*[\d.,]+/([\d.,]+)/", re.IGNORECASE),
    re.compile(
        r"(?:Average|Rata-rata|Mittelwert|Moyenne|Promedio|Media)\s*=\s*([\d.,]+)\s*ms",
        re.IGNORECASE,
    ),
)
_LINUX_RTT_PATTERN = re.compile(
    r"rtt\s+min/avg/max(?:/mdev)?\s*=\s*([\d.,]+)/([\d.,]+)/([\d.,]+)", re.IGNORECASE
)
_MIN_PATTERN = re.compile(r"(?:Minimum|Min)\s*=\s*([\d.,]+)\s*ms", re.IGNORECASE)
_MAX_PATTERN = re.compile(r"(?:Maximum|Maksimum|Max)\s*=\s*([\d.,]+)\s*ms", re.IGNORECASE)
_TIME_PATTERN = re.compile(
    r"(?:time|waktu|temps|zeit)\s*[=<]\s*([\d.,]+)\s*ms", re.IGNORECASE
)
_LOSS_PATTERN = re.compile(
    r"\(\s*([\d.,]+)%\s*(?:packet\s+)?(?:loss|hilang|verlust|perte)\s*\)", re.IGNORECASE
)


class PingRunner:
    def __init__(self, config):
        self.binary = config.get("PING_BINARY") or "ping"
        self.target = (config.get("PING_TARGET_HOST") or "").strip()
        self.count = max(1, int(config.get("PING_COUNT", 5) or 5))
        self.timeout_ms = max(100, int(config.get("PING_TIMEOUT_MS", 1000) or 1000))
        self.max_points = max(1, int(config.get("QOS_HISTORY_POINTS", 240) or 240))

        self.history = deque(maxlen=self.max_points)
        self.lock = threading.Lock()
        self._running = False
        self.meta = None
        self.error = None

    def configured(self):
        return bool(self.target)

    @property
    def running(self):
        with self.lock:
            return self._running

    def status_error(self):
        if not self.target:
            return "Host target delay belum dikonfigurasi (PING_TARGET_HOST)."
        return self.error

    def series(self):
        with self.lock:
            return list(self.history)

    def start(self):
        if not self.configured():
            return False
        with self.lock:
            if self._running:
                return False
            self._running = True
            self.meta = self._meta("running", iso(utc_now()))
        threading.Thread(target=self._run_guarded, name="ping-runner", daemon=True).start()
        return True

    def _run_guarded(self):
        try:
            self.run()
        finally:
            with self.lock:
                self._running = False

    def run(self):
        timestamp = iso(utc_now())
        if not self.target:
            self._fail("Host target delay belum dikonfigurasi (PING_TARGET_HOST).", timestamp)
            return

        timeout_seconds = self.count * (self.timeout_ms / 1000 + 1) + 5
        try:
            result = subprocess.run(
                self._build_command(),
                capture_output=True,
                timeout=timeout_seconds,
            )
        except FileNotFoundError:
            self._fail("Binari ping tidak ditemukan. Set PING_BINARY ke path lengkap.", timestamp)
            return
        except subprocess.TimeoutExpired:
            self._fail(f"Ping melebihi batas waktu {int(timeout_seconds)} detik.", timestamp)
            return
        except OSError as exc:
            self._fail(f"Ping gagal dijalankan ({exc.__class__.__name__}).", timestamp)
            return

        text = f"{self._decode(result.stdout)}\n{self._decode(result.stderr)}"
        stats = self.parse(text)
        if stats["avg"] is None:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            detail = lines[-1] if lines else "Tidak ada balasan ICMP."
            self._fail(f"ICMP tidak dijawab target ({detail}).", timestamp)
            return

        with self.lock:
            self._append(timestamp, stats["avg"])
            self.meta = {
                "method": "ICMP",
                "target": self.target,
                "count": self.count,
                "delay_ms": stats["avg"],
                "min_ms": stats["min"],
                "max_ms": stats["max"],
                "packet_loss_percent": stats["loss"],
                "status": "success",
                "timestamp": timestamp,
                "error": None,
            }
            self.error = None

    def parse(self, text):
        linux = _LINUX_RTT_PATTERN.search(text)
        if linux:
            average = self._number(linux.group(2))
            minimum = self._number(linux.group(1))
            maximum = self._number(linux.group(3))
            samples = []
        else:
            average = self._search(text, _AVG_PATTERNS)
            minimum = self._search(text, (_MIN_PATTERN,))
            maximum = self._search(text, (_MAX_PATTERN,))
            samples = [self._number(value) for value in _TIME_PATTERN.findall(text)]
            samples = [value for value in samples if value is not None]

        if average is None and samples:
            average = sum(samples) / len(samples)
        if minimum is None and samples:
            minimum = min(samples)
        if maximum is None and samples:
            maximum = max(samples)

        loss_match = _LOSS_PATTERN.search(text)
        loss = self._number(loss_match.group(1)) if loss_match else None

        return {
            "avg": None if average is None else round(average, 3),
            "min": None if minimum is None else round(minimum, 3),
            "max": None if maximum is None else round(maximum, 3),
            "loss": None if loss is None else round(loss, 3),
        }

    def _build_command(self):
        if os.name == "nt":
            return [
                self.binary,
                "-n",
                str(self.count),
                "-w",
                str(self.timeout_ms),
                self.target,
            ]
        return [
            self.binary,
            "-c",
            str(self.count),
            "-W",
            str(max(1, round(self.timeout_ms / 1000))),
            self.target,
        ]

    def _meta(self, status, timestamp):
        return {
            "method": "ICMP",
            "target": self.target or None,
            "count": self.count,
            "delay_ms": None,
            "min_ms": None,
            "max_ms": None,
            "packet_loss_percent": None,
            "status": status,
            "timestamp": timestamp,
            "error": None,
        }

    def _fail(self, message, timestamp):
        with self.lock:
            self.error = message
            self.meta = self._meta("failed", timestamp)
            self.meta["error"] = message

    def _append(self, timestamp, value):
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        self.history.append({"t": timestamp, "value": round(float(value), 3)})

    @classmethod
    def _search(cls, text, patterns):
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                value = cls._number(match.group(1))
                if value is not None:
                    return value
        return None

    @staticmethod
    def _number(raw):
        try:
            return float(str(raw).replace(",", "."))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decode(raw):
        if not raw:
            return ""
        for encoding in ("utf-8", locale.getpreferredencoding(False), "cp1252"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")
