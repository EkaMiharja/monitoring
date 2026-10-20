import math
import threading
from collections import deque
from datetime import timedelta

import requests

from services.delay import PingRunner
from services.iperf3 import Iperf3Runner
from services.providers.base import MonitoringProvider
from services.stats import build_metric
from utils import iso, parse_iso, utc_now

HOSTS = (
    ("lightgbm-vm", "GLANCES_LIGHTGBM_URL", "GLANCES_LIGHTGBM_LABEL"),
    ("randomforest-vm", "GLANCES_RANDOM_FOREST_URL", "GLANCES_RANDOM_FOREST_LABEL"),
    ("fail2ban-vm", "GLANCES_FAIL2BAN_URL", "GLANCES_FAIL2BAN_LABEL"),
)


class LiveProvider(MonitoringProvider):
    data_mode = "live"

    def __init__(self, config, telegram_service):
        self.config = config
        self.telegram = telegram_service
        self.timeout = config.get("API_TIMEOUT_SECONDS", 4)
        self.window_seconds = config.get("STATS_WINDOW_SECONDS", 300)
        self.max_points = config.get("HISTORY_MAX_POINTS", 120)
        self.lock = threading.Lock()
        self.qos = {
            "delay": deque(maxlen=self.max_points),
            "jitter": deque(maxlen=self.max_points),
            "packet_loss": deque(maxlen=self.max_points),
            "throughput": deque(maxlen=self.max_points),
        }
        self.resources = {
            host: {"cpu": deque(maxlen=self.max_points), "memory": deque(maxlen=self.max_points)}
            for host, _key, _label in HOSTS
        }
        self.iperf_runner = Iperf3Runner(config)
        self.delay_runner = PingRunner(config)
        self.iperf_meta = None
        self.iperf_error = None
        self.delay_meta = None

    def _get_json(self, url, token=None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.get(url, timeout=self.timeout, headers=headers)
            response.raise_for_status()
            return response.json(), None
        except requests.RequestException as exc:
            return None, f"Tidak dapat mengakses sumber data ({exc.__class__.__name__})."
        except ValueError:
            return None, "Respons sumber data bukan JSON yang valid."

    def _window(self, series):
        cutoff = utc_now() - timedelta(seconds=self.window_seconds)
        result = []
        for point in series:
            timestamp = parse_iso(point["t"])
            if timestamp is not None and timestamp >= cutoff:
                result.append(point)
        return result

    def _append_once(self, series, timestamp, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if series and series[-1]["t"] == timestamp:
            return
        series.append({"t": timestamp, "value": round(float(value), 3)})

    def _load_iperf(self):
        if self.iperf_runner.configured():
            self.iperf_meta = self.iperf_runner.meta
            self.iperf_error = self.iperf_runner.status_error()
            return

        url = self.config.get("IPERF3_RESULT_URL")
        if not url:
            self.iperf_error = (
                self.iperf_runner.status_error() or "Endpoint hasil iperf3 belum dikonfigurasi."
            )
            return
        if not self.config.get("IPERF3_ENABLED", False):
            self.iperf_error = "Pengujian iperf3 dinonaktifkan (IPERF3_ENABLED=false)."
            return

        payload, error = self._get_json(url)
        if error:
            self.iperf_error = error
            return
        if not isinstance(payload, dict):
            self.iperf_error = "Format hasil iperf3 tidak dikenali."
            return

        timestamp = payload.get("timestamp") or iso()
        protocol = str(payload.get("protocol") or self.config.get("IPERF3_TEST_PROTOCOL", "udp")).lower()
        throughput = payload.get("throughput_mbps", payload.get("throughput"))
        jitter = payload.get("jitter_ms", payload.get("jitter"))
        loss = payload.get("packet_loss_percent", payload.get("packet_loss"))

        with self.lock:
            self._append_once(self.qos["throughput"], timestamp, throughput)
            if protocol == "udp":
                self._append_once(self.qos["jitter"], timestamp, jitter)
                self._append_once(self.qos["packet_loss"], timestamp, loss)
            self.iperf_meta = {
                "protocol": protocol.upper(),
                "direction": payload.get("direction", "upload"),
                "client": payload.get("client") or self.config.get("IPERF3_CLIENT_HOST") or None,
                "server": payload.get("server") or self.config.get("IPERF3_SERVER_HOST") or None,
                "duration_seconds": payload.get("duration_seconds")
                or self.config.get("IPERF3_TEST_DURATION_SECONDS"),
                "status": payload.get("status", "success"),
                "timestamp": timestamp,
            }
            self.iperf_error = None

    def _load_delay(self):
        if self.delay_runner.configured():
            self.delay_meta = self.delay_runner.meta
            error = self.delay_runner.status_error()
            if error:
                return error
            if not self.delay_runner.series():
                return "Belum ada hasil pengukuran delay. Jalankan pengukuran."
            return None

        self.delay_meta = None
        url = self.config.get("DELAY_API_URL")
        if not url:
            return "Metode/sumber pengukuran delay belum ditentukan."
        payload, error = self._get_json(url)
        if error:
            return error
        if not isinstance(payload, dict):
            return "Format hasil pengukuran delay tidak dikenali."
        timestamp = payload.get("timestamp") or iso()
        value = payload.get("delay_ms", payload.get("value_ms", payload.get("value")))
        with self.lock:
            self._append_once(self.qos["delay"], timestamp, value)
        return None

    def _qos_series(self):
        if self.iperf_runner.configured():
            throughput = self.iperf_runner.series("throughput")
            jitter = self.iperf_runner.series("jitter")
            packet_loss = self.iperf_runner.series("packet_loss")
        else:
            throughput = self._window(self.qos["throughput"])
            jitter = self._window(self.qos["jitter"])
            packet_loss = self._window(self.qos["packet_loss"])

        if self.delay_runner.configured():
            delay = self.delay_runner.series()
        else:
            delay = self._window(self.qos["delay"])

        return {
            "delay": delay,
            "jitter": jitter,
            "packet_loss": packet_loss,
            "throughput": throughput,
        }

    def _glances_quicklook(self, base_url):
        base = base_url.rstrip("/")
        last_error = None
        for version in ("4", "3"):
            payload, error = self._get_json(f"{base}/api/{version}/quicklook")
            if payload is not None:
                return payload, None
            last_error = error
        return None, last_error

    @staticmethod
    def _extract_number(payload, keys):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, dict):
                for nested in ("total", "percent", "usage"):
                    nested_value = value.get(nested)
                    if isinstance(nested_value, (int, float)) and not isinstance(nested_value, bool):
                        return float(nested_value)
        return None

    def _load_resources(self):
        hosts = []
        any_ok = False
        for host, config_key, label_key in HOSTS:
            label = str(self.config.get(label_key) or host)
            url = self.config.get(config_key)
            if not url:
                hosts.append(
                    {
                        "host": label,
                        "status": "unavailable",
                        "source": "Glances",
                        "error": f"URL Glances untuk {label} belum dikonfigurasi.",
                        "cpu": build_metric([], "%", "Glances", status="unavailable", error="URL belum dikonfigurasi."),
                        "memory": build_metric([], "%", "Glances", status="unavailable", error="URL belum dikonfigurasi."),
                    }
                )
                continue

            payload, error = self._glances_quicklook(url)
            if error:
                hosts.append(
                    {
                        "host": label,
                        "status": "error",
                        "source": "Glances",
                        "error": error,
                        "cpu": build_metric([], "%", "Glances", status="error", error=error),
                        "memory": build_metric([], "%", "Glances", status="error", error=error),
                    }
                )
                continue

            cpu = self._extract_number(payload, ("cpu", "cpu_percent", "cpu_usage"))
            memory = self._extract_number(payload, ("mem", "memory", "memory_percent", "mem_usage"))
            timestamp = payload.get("timestamp") or iso()
            with self.lock:
                if cpu is not None:
                    self._append_once(self.resources[host]["cpu"], timestamp, cpu)
                if memory is not None:
                    self._append_once(self.resources[host]["memory"], timestamp, memory)
                cpu_series = self._window(self.resources[host]["cpu"])
                memory_series = self._window(self.resources[host]["memory"])

            if cpu is None and memory is None:
                hosts.append(
                    {
                        "host": label,
                        "status": "error",
                        "source": "Glances",
                        "error": "Field CPU/memori tidak ditemukan pada respons Glances.",
                        "cpu": build_metric(cpu_series, "%", "Glances", status="error", error="Field CPU tidak ditemukan."),
                        "memory": build_metric(memory_series, "%", "Glances", status="error", error="Field memori tidak ditemukan."),
                    }
                )
                continue

            any_ok = True
            hosts.append(
                {
                    "host": label,
                    "status": "ok",
                    "source": "Glances",
                    "error": None,
                    "cpu": build_metric(cpu_series, "%", "Glances"),
                    "memory": build_metric(memory_series, "%", "Glances"),
                }
            )

        status = "ok" if any_ok else "unavailable"
        return {
            "status": status,
            "source": "Glances",
            "error": None if any_ok else "Tidak ada host Glances yang dapat diakses.",
            "hosts": hosts,
        }

    def _load_blocked(self):
        url = self.config.get("FAIL2BAN_API_URL")
        if not url:
            return {
                "status": "unavailable",
                "source": "Fail2Ban",
                "error": "Endpoint Fail2Ban belum dikonfigurasi.",
                "items": [],
            }
        payload, error = self._get_json(url)
        if error:
            return {"status": "error", "source": "Fail2Ban", "error": error, "items": []}

        raw_items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return {
                "status": "error",
                "source": "Fail2Ban",
                "error": "Format daftar IP dari Fail2Ban tidak dikenali.",
                "items": [],
            }

        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            ip = raw.get("ip") or raw.get("source_ip") or raw.get("address")
            if not ip:
                continue
            status = str(raw.get("status", "blocked")).lower()
            if status not in {"blocked", "banned", "active"}:
                continue
            items.append(
                {
                    "ip": ip,
                    "blocked_at": raw.get("blocked_at") or raw.get("timestamp") or raw.get("time"),
                    "jail": raw.get("jail") or raw.get("source"),
                    "status": "blocked",
                    "source": raw.get("source") or "Fail2Ban",
                }
            )

        return {
            "status": "ok" if items else "empty",
            "source": "Fail2Ban",
            "error": None,
            "items": items,
        }

    def _load_attacks(self):
        url = self.config.get("ATTACK_HISTORY_API_URL")
        if not url:
            return {
                "status": "unavailable",
                "source": "API deteksi",
                "error": "Endpoint attack history belum dikonfigurasi.",
                "items": [],
            }
        token = self.config.get("ATTACK_HISTORY_API_TOKEN")
        payload, error = self._get_json(url, token)
        if error:
            return {"status": "error", "source": "API deteksi", "error": error, "items": []}
        raw_items = payload.get("items") if isinstance(payload, dict) else payload
        source = payload.get("source") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return {
                "status": "error",
                "source": source or "API deteksi",
                "error": "Format attack history tidak dikenali.",
                "items": [],
            }

        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "detected_at": raw.get("detected_at") or raw.get("timestamp") or raw.get("time"),
                    "source_ip": raw.get("source_ip") or raw.get("ip"),
                    "target": raw.get("target"),
                    "attack_type": raw.get("attack_type") or raw.get("type") or "SSH Brute Force",
                    "detection": raw.get("detection") or raw.get("result") or raw.get("prediction"),
                    "model": raw.get("model"),
                    "blocking_status": raw.get("blocking_status") or raw.get("blocked"),
                }
            )
        items.sort(key=lambda item: item.get("detected_at") or "", reverse=True)

        return {
            "status": "ok" if items else "empty",
            "source": source or "API deteksi",
            "error": None,
            "items": items[:50],
        }

    def _load_traffic(self):
        """Build the 14-feature flow monitor from processed RF feature rows."""
        url = self.config.get("FLOW_FEATURES_API_URL")
        if not url:
            return {
                "status": "unavailable",
                "source": "Random Forest flow features",
                "error": "Endpoint flow features belum dikonfigurasi.",
                "features": [],
            }

        token = self.config.get("FLOW_FEATURES_API_TOKEN") or self.config.get(
            "ATTACK_HISTORY_API_TOKEN"
        )
        payload, error = self._get_json(url, token)
        if error:
            return {
                "status": "error",
                "source": "Random Forest flow features",
                "error": error,
                "features": [],
            }

        raw_items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return {
                "status": "error",
                "source": "Random Forest flow features",
                "error": "Format flow features tidak dikenali.",
                "features": [],
            }

        names = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(names, list) or not names:
            names = []
            for item in raw_items[:1]:
                if isinstance(item, dict) and isinstance(item.get("features"), dict):
                    names = list(item["features"])

        def sort_key(item):
            timestamp = parse_iso(item.get("detected_at")) if isinstance(item, dict) else None
            return timestamp.timestamp() if timestamp else 0

        ordered = sorted(
            (item for item in raw_items if isinstance(item, dict)),
            key=sort_key,
        )
        series = {name: [] for name in names}
        for item in ordered:
            timestamp = item.get("detected_at")
            values = item.get("features")
            if not timestamp or not isinstance(values, dict):
                continue
            for name in names:
                value = values.get(name)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if not math.isfinite(value):
                    continue
                series[name].append({"t": timestamp, "value": round(float(value), 6)})

        features = []
        for name in names:
            points = series.get(name) or []
            current = points[-1]["value"] if points else None
            previous = points[-2]["value"] if len(points) > 1 else None
            delta = None
            if current is not None and previous is not None:
                delta = round(current - previous, 6)
            features.append(
                {
                    "name": name,
                    "current": current,
                    "previous": previous,
                    "delta": delta,
                    "series": points[-50:],
                }
            )

        latest = ordered[-1] if ordered else {}
        status = "ok" if any(feature["series"] for feature in features) else "empty"
        return {
            "status": status,
            "source": (payload.get("source") if isinstance(payload, dict) else None)
            or "Random Forest flow features",
            "error": None if status == "ok" else "Belum ada sampel fitur flow.",
            "feature_count": len(features),
            "sample": {
                "detected_at": latest.get("detected_at"),
                "source_ip": latest.get("source_ip"),
                "target": latest.get("target"),
                "auth_result": latest.get("auth_result"),
            },
            "features": features,
        }

    def get_overview(self):
        self._load_iperf()
        delay_error = self._load_delay()

        series_map = self._qos_series()
        qos_source = (
            "iperf3 / ICMP ping"
            if (self.iperf_runner.configured() or self.delay_runner.configured())
            else "iperf3 / delay probe"
        )

        metrics = {}
        for key, unit in (
            ("delay", "ms"),
            ("jitter", "ms"),
            ("packet_loss", "%"),
            ("throughput", "Mbps"),
        ):
            series = series_map[key]
            if series:
                metrics[key] = build_metric(series, unit, qos_source)
                continue

            if key == "delay":
                error = delay_error or "Belum ada sampel pengukuran delay."
            elif key == "throughput":
                error = self.iperf_error or "Belum ada sampel pengukuran iperf3."
            elif str(self.config.get("IPERF3_TEST_PROTOCOL", "udp")).lower() != "udp":
                error = f"{key.replace('_', ' ').title()} hanya tersedia dari hasil iperf3 UDP."
            else:
                error = self.iperf_error or "Belum ada sampel pengukuran iperf3."
            metrics[key] = build_metric(
                series, unit, qos_source, status="unavailable", error=error
            )

        qos_status = "ok" if any(metrics[key]["series"] for key in metrics) else "unavailable"
        qos_error = None if qos_status == "ok" else (self.iperf_error or delay_error or "Belum ada hasil pengukuran QoS.")

        traffic = self._load_traffic()

        resources = self._load_resources()
        blocked = self._load_blocked()
        attacks = self._load_attacks()

        telegram_items = self.telegram.history()
        telegram = {
            "status": "ok" if telegram_items else "empty",
            "source": "Telegram Bot API",
            "error": None if self.telegram.configured() else "Token/chat ID Telegram belum dikonfigurasi.",
            "items": telegram_items,
        }

        return {
            "traffic": traffic,
            "qos": {
                "status": qos_status,
                "source": qos_source,
                "error": qos_error,
                "metrics": metrics,
                "test": self.iperf_meta
                or {
                    "protocol": self.config.get("IPERF3_TEST_PROTOCOL", "udp").upper(),
                    "direction": "upload",
                    "client": self.config.get("IPERF3_CLIENT_HOST") or None,
                    "server": self.config.get("IPERF3_SERVER_HOST") or None,
                    "duration_seconds": self.config.get("IPERF3_TEST_DURATION_SECONDS"),
                    "status": "unavailable",
                    "timestamp": None,
                },
                "delay_test": self.delay_meta,
            },
            "resources": resources,
            "blocked_ips": blocked,
            "attacks": attacks,
            "telegram": telegram,
            "errors": [],
        }
