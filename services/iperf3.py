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
        self.timeout_margin = max(
            5, int(config.get("IPERF3_TIMEOUT_MARGIN_SECONDS", 30) or 30)
        )
        self.max_points = max(1, int(config.get("QOS_HISTORY_POINTS", 240) or 240))

        self.history = {
            "throughput": deque(maxlen=self.max_points),
            "jitter": deque(maxlen=self.max_points),
            "packet_loss": deque(maxlen=self.max_points),
        }
        self.lock = threading.Lock()
        self._running = False
        self._next_duration = self.duration
        self._next_bandwidth = self.bandwidth
        self._next_protocol = self.protocol
        # Profil kedua (opsional) untuk metrik loss/jitter: mis. UDP ringan.
        self._loss_duration = 0
        self._loss_bandwidth = ""
        self._loss_protocol = "udp"
        self._loss_running = False
        self._loss_port = int(config.get("QOS_AUTO_LOSS_PORT", 5202) or 5202)
        self.meta = None
        self.error = None

    def configured(self):
        return self.enabled and bool(self.server)

    @property
    def running(self):
        with self.lock:
            return self._running

    @property
    def protocol_in_use(self):
        """Protocol of the running/last test (bisa dioverride per run)."""
        return self._next_protocol

    @property
    def loss_running(self):
        with self.lock:
            return self._loss_running

    def start_loss(self, duration_seconds=None, bandwidth=None, protocol=None):
        """Jalankan tes kedua (UDP ringan) khusus untuk jitter & packet loss."""
        if not self.configured():
            return False
        with self.lock:
            if self._loss_running:
                return False
            self._loss_running = True
            self._loss_duration = max(1, int(duration_seconds or 3))
            self._loss_bandwidth = str(bandwidth or "").strip()
            self._loss_protocol = str(protocol or "udp").strip().lower() or "udp"
        threading.Thread(
            target=self._run_loss_guarded, name="iperf3-loss-runner", daemon=True
        ).start()
        return True

    def _run_loss_guarded(self):
        try:
            self.run_loss()
        finally:
            with self.lock:
                self._loss_running = False

    def status_error(self):
        if not self.enabled:
            return "Pengujian iperf3 dinonaktifkan (IPERF3_ENABLED=false)."
        if not self.server:
            return "Host server iperf3 belum dikonfigurasi (IPERF3_SERVER_HOST)."
        return self.error

    def series(self, key):
        with self.lock:
            return list(self.history[key])

    def start(self, duration_seconds=None, bandwidth=None, protocol=None):
        if not self.configured():
            return False
        with self.lock:
            if self._running:
                return False
            self._running = True
            if duration_seconds:
                self._next_duration = max(1, int(duration_seconds))
            else:
                self._next_duration = self.duration
            if bandwidth is None:
                self._next_bandwidth = self.bandwidth
            else:
                self._next_bandwidth = str(bandwidth).strip()
            if protocol is None:
                self._next_protocol = self.protocol
            else:
                self._next_protocol = str(protocol).strip().lower() or self.protocol
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
        duration = self._next_duration
        try:
            result = subprocess.run(
                self._build_command(),
                capture_output=True,
                timeout=duration + self.timeout_margin,
            )
        except FileNotFoundError:
            self._fail("Binari iperf3 tidak ditemukan. Set IPERF3_BINARY ke path lengkap.", timestamp)
            return
        except subprocess.TimeoutExpired:
            self._fail(
                f"iperf3 melebihi batas waktu {duration + self.timeout_margin} detik.",
                timestamp,
            )
            return
        except OSError as exc:
            self._fail(f"iperf3 gagal dijalankan ({exc.__class__.__name__}).", timestamp)
            return

        stdout = self._decode(result.stdout)
        stderr = self._decode(result.stderr)
        if result.returncode != 0:
            self._fail(self._error_detail(stdout, stderr), timestamp)
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
            if self._next_protocol == "udp":
                self._append(self.history["jitter"], timestamp, parsed["jitter"])
                self._append(self.history["packet_loss"], timestamp, parsed["packet_loss"])
            self.meta = self._meta("success", timestamp, error=None)
            self.error = None

    def run_loss(self):
        """Tes UDP singkat; hanya jitter & packet loss yang diambil."""
        timestamp = iso(utc_now())
        try:
            result = subprocess.run(
                self._build_loss_command(),
                capture_output=True,
                timeout=self._loss_duration + self.timeout_margin,
            )
        except (FileNotFoundError, OSError):
            return
        except subprocess.TimeoutExpired:
            return
        if result.returncode != 0:
            return
        try:
            payload = json.loads(self._decode(result.stdout))
        except ValueError:
            return
        parsed = self.parse(payload)
        with self.lock:
            self._append(self.history["jitter"], timestamp, parsed["jitter"])
            self._append(self.history["packet_loss"], timestamp, parsed["packet_loss"])

    def _build_loss_command(self):
        command = [
            self.binary,
            "-c",
            self.server,
            "-p",
            str(self._loss_port),
            "-t",
            str(self._loss_duration),
            "-J",
        ]
        if self._loss_protocol == "udp":
            command.append("-u")
            if self._loss_bandwidth:
                command.extend(["-b", self._loss_bandwidth])
        return command

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
            str(self._next_duration),
            "-J",
        ]
        if self.omit:
            command.extend(["-O", str(self.omit)])
        if self._next_protocol == "udp":
            command.append("-u")
            if self._next_bandwidth:
                command.extend(["-b", self._next_bandwidth])
        return command

    def _meta(self, status, timestamp, error):
        return {
            "protocol": self._next_protocol.upper(),
            "direction": "upload",
            "client": self.client_host or None,
            "server": self.server or None,
            "port": self.port,
            "bandwidth": self._next_bandwidth or None,
            "duration_seconds": self._next_duration,
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
    def _error_detail(stdout, stderr):
        """Return the most useful error line from an iperf3 failure."""
        text = stdout or ""
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
        for source in (stderr, stdout):
            lines = [line.strip() for line in (source or "").splitlines() if line.strip()]
            if lines:
                return lines[-1]
        return "iperf3 gagal tanpa pesan error."

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
