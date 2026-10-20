import json
import subprocess
import threading
from collections import deque

from utils import iso, utc_now


class Iperf3Runner:
    def __init__(self, config):
        self.enabled = bool(config.get("IPERF3_ENABLED", False))
        self.binary = config.get("IPERF3_BINARY") or "iperf3"
        self.server = (config.get("IPERF3_SERVER_HOST") or "").strip()
        self.client_host = (config.get("IPERF3_CLIENT_HOST") or "").strip()
        self.port = int(config.get("IPERF3_PORT", 5201) or 5201)
        self.protocol = (config.get("IPERF3_TEST_PROTOCOL") or "udp").strip().lower()
        self.bandwidth = (config.get("IPERF3_BANDWIDTH") or "").strip()
        self.omit = max(0, int(config.get("IPERF3_OMIT_SECONDS", 1) or 0))
        self.duration = max(1, int(config.get("IPERF3_TEST_DURATION_SECONDS", 10) or 10))
        self.max_points = max(1, int(config.get("QOS_HISTORY_POINTS", 240) or 240))

        self.history = {
            "throughput": deque(maxlen=self.max_points),
            "jitter": deque(maxlen=self.max_points),
            "packet_loss": deque(maxlen=self.max_points),
        }
        self.lock = threading.Lock()
        self._running = False
        self.meta = None
        self.error = None

    def configured(self):
        return self.enabled and bool(self.server)

    @property
    def running(self):
        with self.lock:
            return self._running

    def status_error(self):
        if not self.enabled:
            return "Pengujian iperf3 dinonaktifkan (IPERF3_ENABLED=false)."
        if not self.server:
            return "Host server iperf3 belum dikonfigurasi (IPERF3_SERVER_HOST)."
        return self.error

    def series(self, key):
        with self.lock:
            return list(self.history[key])

    def start(self):
        if not self.configured():
            return False
        with self.lock:
            if self._running:
                return False
            self._running = True
            self.meta = self._meta("running", iso(utc_now()), error=None)
        threading.Thread(target=self._run_guarded, name="iperf3-runner", daemon=True).start()
        return True

    def _run_guarded(self):
        try:
            self.run()
        finally:
            with self.lock:
                self._running = False

    def run(self):
        timestamp = iso(utc_now())
        try:
            result = subprocess.run(
                self._build_command(),
                capture_output=True,
                timeout=self.duration + 30,
            )
        except FileNotFoundError:
            self._fail("Binari iperf3 tidak ditemukan. Set IPERF3_BINARY ke path lengkap.", timestamp)
            return
        except subprocess.TimeoutExpired:
            self._fail(f"iperf3 melebihi batas waktu {self.duration + 30} detik.", timestamp)
            return
        except OSError as exc:
            self._fail(f"iperf3 gagal dijalankan ({exc.__class__.__name__}).", timestamp)
            return

        stdout = self._decode(result.stdout)
        stderr = self._decode(result.stderr)
        if result.returncode != 0:
            lines = [line.strip() for line in (stderr or stdout).splitlines() if line.strip()]
            detail = lines[-1] if lines else f"iperf3 keluar dengan kode {result.returncode}."
            self._fail(detail, timestamp)
            return

        try:
            payload = json.loads(stdout)
        except ValueError:
            self._fail("Keluaran iperf3 bukan JSON yang valid.", timestamp)
            return

        parsed = self.parse(payload)
        if parsed["throughput"] is None:
            self._fail("Throughput tidak ditemukan pada keluaran iperf3.", timestamp)
            return

        with self.lock:
            self._append(self.history["throughput"], timestamp, parsed["throughput"])
            if self.protocol == "udp":
                self._append(self.history["jitter"], timestamp, parsed["jitter"])
                self._append(self.history["packet_loss"], timestamp, parsed["packet_loss"])
            self.meta = self._meta("success", timestamp, error=None)
            self.error = None

    def parse(self, payload):
        end = payload.get("end") if isinstance(payload, dict) else None
        if not isinstance(end, dict):
            end = {}
        received = end.get("sum_received") if isinstance(end.get("sum_received"), dict) else {}
        sent = end.get("sum_sent") if isinstance(end.get("sum_sent"), dict) else {}
        summary = end.get("sum") if isinstance(end.get("sum"), dict) else {}

        bits_per_second = self._first_number(
            received.get("bits_per_second"),
            summary.get("bits_per_second"),
            sent.get("bits_per_second"),
        )
        return {
            "throughput": None if bits_per_second is None else round(bits_per_second / 1_000_000, 3),
            "jitter": self._first_number(summary.get("jitter_ms"), received.get("jitter_ms")),
            "packet_loss": self._first_number(
                summary.get("lost_percent"), received.get("lost_percent")
            ),
        }

    def _build_command(self):
        command = [
            self.binary,
            "-c",
            self.server,
            "-p",
            str(self.port),
            "-t",
            str(self.duration),
            "-J",
        ]
        if self.omit:
            command.extend(["-O", str(self.omit)])
        if self.protocol == "udp":
            command.append("-u")
            if self.bandwidth:
                command.extend(["-b", self.bandwidth])
        return command

    def _meta(self, status, timestamp, error):
        return {
            "protocol": self.protocol.upper(),
            "direction": "upload",
            "client": self.client_host or None,
            "server": self.server or None,
            "port": self.port,
            "bandwidth": self.bandwidth or None,
            "duration_seconds": self.duration,
            "status": status,
            "timestamp": timestamp,
            "error": error,
        }

    def _fail(self, message, timestamp):
        with self.lock:
            self.error = message
            self.meta = self._meta("failed", timestamp, error=message)

    @staticmethod
    def _decode(raw):
        if not raw:
            return ""
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _append(series, timestamp, value):
        if value is None or isinstance(value, bool):
            return
        if not isinstance(value, (int, float)):
            return
        series.append({"t": timestamp, "value": round(float(value), 3)})

    @staticmethod
    def _first_number(*values):
        for value in values:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None
