import random
import threading
from collections import deque
from datetime import timedelta

from services.providers.base import MonitoringProvider
from services.stats import build_metric
from utils import iso, parse_iso, utc_now

TRAFFIC_SOURCE = "Pengukuran lokal laptop monitoring (DEMO)"
QOS_SOURCE = "iperf3 + delay probe (DEMO)"
RESOURCE_SOURCE = "Glances (DEMO)"
FAIL2BAN_SOURCE = "Fail2Ban (DEMO)"
ATTACK_SOURCE = "Log deteksi LightGBM / Random Forest (DEMO)"


class MockProvider(MonitoringProvider):
    data_mode = "demo"

    def __init__(self, config, telegram_service):
        self.config = config
        self.telegram = telegram_service
        self.interval_seconds = max(config.get("POLL_INTERVAL_MS", 5000), 1000) / 1000.0
        self.window_seconds = config.get("STATS_WINDOW_SECONDS", 300)
        self.max_points = config.get("HISTORY_MAX_POINTS", 120)
        self.random = random.Random(20261020)
        self.lock = threading.Lock()

        self.traffic = deque(maxlen=self.max_points)
        self.qos = {
            "delay": deque(maxlen=self.max_points),
            "jitter": deque(maxlen=self.max_points),
            "packet_loss": deque(maxlen=self.max_points),
            "throughput": deque(maxlen=self.max_points),
        }
        self.hosts = {
            "lightgbm-vm": {"cpu": deque(maxlen=self.max_points), "memory": deque(maxlen=self.max_points)},
            "randomforest-vm": {"cpu": deque(maxlen=self.max_points), "memory": deque(maxlen=self.max_points)},
            "fail2ban-vm": {"cpu": deque(maxlen=self.max_points), "memory": deque(maxlen=self.max_points)},
        }

        self._seed_history()
        self._blocked = self._seed_blocked()
        self._attacks = self._seed_attacks()

    def _seed_history(self):
        now = utc_now()
        step = max(self.interval_seconds, 1)
        points = min(self.max_points, max(12, int(self.window_seconds // step)))
        start = now - timedelta(seconds=(points - 1) * step)

        inbound = 78.0
        outbound = 32.0
        delay = 18.0
        jitter = 2.4
        loss = 0.42
        throughput = 96.0
        cpu = {"lightgbm-vm": 46.0, "randomforest-vm": 39.0, "fail2ban-vm": 24.0}
        memory = {"lightgbm-vm": 61.0, "randomforest-vm": 57.0, "fail2ban-vm": 43.0}

        for index in range(points):
            timestamp = iso(start + timedelta(seconds=index * step))
            inbound = self._walk(inbound, 6.0, 8.0, 260.0)
            outbound = self._walk(outbound, 3.2, 4.0, 180.0)
            delay = self._walk(delay, 1.6, 9.0, 42.0)
            jitter = self._walk(jitter, 0.35, 0.5, 7.5)
            loss = self._walk(loss, 0.12, 0.0, 2.5)
            throughput = self._walk(throughput, 6.0, 45.0, 145.0)

            self.traffic.append({"t": timestamp, "inbound": round(inbound, 2), "outbound": round(outbound, 2)})
            self.qos["delay"].append({"t": timestamp, "value": round(delay, 2)})
            self.qos["jitter"].append({"t": timestamp, "value": round(jitter, 2)})
            self.qos["packet_loss"].append({"t": timestamp, "value": round(loss, 2)})
            self.qos["throughput"].append({"t": timestamp, "value": round(throughput, 2)})

            for host in self.hosts:
                cpu[host] = self._walk(cpu[host], 4.5, 6.0, 92.0)
                memory[host] = self._walk(memory[host], 2.0, 25.0, 93.0)
                self.hosts[host]["cpu"].append({"t": timestamp, "value": round(cpu[host], 2)})
                self.hosts[host]["memory"].append({"t": timestamp, "value": round(memory[host], 2)})

        self._last_sample = start + timedelta(seconds=(points - 1) * step)

    def _walk(self, value, spread, low, high):
        value += self.random.uniform(-spread, spread)
        return min(high, max(low, value))

    def _maybe_append_sample(self):
        now = utc_now()
        elapsed = (now - self._last_sample).total_seconds()
        if elapsed < max(3.5, self.interval_seconds * 0.8):
            return
        with self.lock:
            if (now - self._last_sample).total_seconds() < max(3.5, self.interval_seconds * 0.8):
                return
            timestamp = iso(now)
            last_traffic = self.traffic[-1]
            last = {key: self.qos[key][-1]["value"] for key in self.qos}
            self.traffic.append(
                {
                    "t": timestamp,
                    "inbound": round(self._walk(last_traffic["inbound"], 6.0, 8.0, 260.0), 2),
                    "outbound": round(self._walk(last_traffic["outbound"], 3.2, 4.0, 180.0), 2),
                }
            )
            spreads = {
                "delay": (1.6, 9.0, 42.0),
                "jitter": (0.35, 0.5, 7.5),
                "packet_loss": (0.12, 0.0, 2.5),
                "throughput": (6.0, 45.0, 145.0),
            }
            for key, value in last.items():
                spread, low, high = spreads[key]
                self.qos[key].append(
                    {"t": timestamp, "value": round(self._walk(value, spread, low, high), 2)}
                )
            for host, data in self.hosts.items():
                cpu = data["cpu"][-1]["value"]
                memory = data["memory"][-1]["value"]
                data["cpu"].append({"t": timestamp, "value": round(self._walk(cpu, 4.5, 6.0, 92.0), 2)})
                data["memory"].append(
                    {"t": timestamp, "value": round(self._walk(memory, 2.0, 25.0, 93.0), 2)}
                )
            self._last_sample = now

    def _window(self, series):
        cutoff = utc_now() - timedelta(seconds=self.window_seconds)
        result = []
        for point in series:
            timestamp = parse_iso(point["t"])
            if timestamp is not None and timestamp >= cutoff:
                result.append(point)
        return result

    def _seed_blocked(self):
        now = utc_now()
        return [
            {
                "ip": "203.0.113.45",
                "blocked_at": iso(now - timedelta(minutes=42)),
                "jail": "sshd",
                "status": "blocked",
                "source": "Fail2Ban (DEMO)",
            },
            {
                "ip": "198.51.100.23",
                "blocked_at": iso(now - timedelta(hours=2, minutes=18)),
                "jail": "sshd",
                "status": "blocked",
                "source": "Fail2Ban (DEMO)",
            },
            {
                "ip": "192.0.2.77",
                "blocked_at": iso(now - timedelta(hours=4, minutes=51)),
                "jail": "sshd",
                "status": "blocked",
                "source": "Fail2Ban (DEMO)",
            },
        ]

    def _seed_attacks(self):
        now = utc_now()
        rows = [
            (37, "203.0.113.45", "LightGBM", "Blocked"),
            (96, "198.51.100.23", "Random Forest", "Blocked"),
            (154, "203.0.113.45", "LightGBM", "Blocked"),
            (219, "192.0.2.77", "LightGBM", "Not blocked"),
            (311, "198.51.100.23", "Random Forest", "Blocked"),
            (428, "192.0.2.77", "Random Forest", "Not blocked"),
        ]
        return [
            {
                "detected_at": iso(now - timedelta(minutes=minutes)),
                "source_ip": source_ip,
                "target": "ssh",
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": model,
                "blocking_status": blocking,
            }
            for minutes, source_ip, model, blocking in rows
        ]

    def get_overview(self):
        self._maybe_append_sample()

        traffic_series = self._window(self.traffic)
        traffic = {
            "status": "ok" if traffic_series else "empty",
            "source": TRAFFIC_SOURCE,
            "unit": "Mbps",
            "error": None if traffic_series else "Belum ada sampel traffic.",
            "series": traffic_series,
        }

        metrics = {}
        for key, unit in (
            ("delay", "ms"),
            ("jitter", "ms"),
            ("packet_loss", "%"),
            ("throughput", "Mbps"),
        ):
            series = self._window(self.qos[key])
            metrics[key] = build_metric(series, unit, QOS_SOURCE)
            if not series:
                metrics[key].update(status="empty", error="Belum ada sampel pengukuran.")

        qos = {
            "status": "ok",
            "source": QOS_SOURCE,
            "error": None,
            "metrics": metrics,
            "test": {
                "protocol": self.config.get("IPERF3_TEST_PROTOCOL", "udp").upper(),
                "direction": "upload",
                "client": "monitoring-laptop (DEMO)",
                "server": "lightgbm-vm (DEMO)",
                "duration_seconds": self.config.get("IPERF3_TEST_DURATION_SECONDS", 10),
                "status": "success",
                "timestamp": iso(self._last_sample),
            },
        }

        hosts = []
        for host, data in self.hosts.items():
            cpu_series = self._window(data["cpu"])
            memory_series = self._window(data["memory"])
            hosts.append(
                {
                    "host": host,
                    "status": "ok" if cpu_series and memory_series else "empty",
                    "source": RESOURCE_SOURCE,
                    "cpu": build_metric(cpu_series, "%", RESOURCE_SOURCE),
                    "memory": build_metric(memory_series, "%", RESOURCE_SOURCE),
                }
            )

        resources = {
            "status": "ok" if any(host["status"] == "ok" for host in hosts) else "empty",
            "source": RESOURCE_SOURCE,
            "error": None,
            "hosts": hosts,
        }

        telegram_items = self.telegram.history()
        telegram = {
            "status": "ok" if telegram_items else "empty",
            "source": "Telegram Bot API (DEMO)",
            "error": None,
            "items": telegram_items,
        }

        return {
            "traffic": traffic,
            "qos": qos,
            "resources": resources,
            "blocked_ips": {
                "status": "ok" if self._blocked else "empty",
                "source": FAIL2BAN_SOURCE,
                "error": None,
                "items": self._blocked,
            },
            "attacks": {
                "status": "ok" if self._attacks else "empty",
                "source": ATTACK_SOURCE,
                "error": None,
                "items": self._attacks,
            },
            "telegram": telegram,
            "errors": [],
        }
