import random
import threading
from collections import deque
from datetime import timedelta

from config import CHART_RANGES, DEFAULT_VM, VM_IDS, VM_TRAFFIC
from services.providers.base import MonitoringProvider
from services.stats import build_metric
from utils import iso, parse_iso, utc_now

TRAFFIC_SOURCE = "Flow simulasi per VM (DEMO)"
QOS_SOURCE = "iperf3 + delay probe per VM (DEMO)"
RESOURCE_SOURCE = "Glances (DEMO)"
FAIL2BAN_SOURCE = "Fail2Ban (DEMO)"
ATTACK_SOURCE = "Log deteksi LightGBM / Random Forest (DEMO)"

VM_PROFILES = {
    "randomforest-vm": {
        "inbound": 78.0,
        "outbound": 32.0,
        "delay": 18.0,
        "jitter": 2.4,
        "loss": 0.42,
        "throughput": 96.0,
        "cpu": 39.0,
        "memory": 57.0,
    },
    "lightgbm-vm": {
        "inbound": 64.0,
        "outbound": 25.0,
        "delay": 22.0,
        "jitter": 3.1,
        "loss": 0.65,
        "throughput": 88.0,
        "cpu": 46.0,
        "memory": 61.0,
    },
    "fail2ban-vm": {
        "inbound": 41.0,
        "outbound": 17.0,
        "delay": 27.0,
        "jitter": 2.0,
        "loss": 0.3,
        "throughput": 72.0,
        "cpu": 24.0,
        "memory": 43.0,
    },
}

QOS_METRICS = ("delay", "jitter", "packet_loss", "throughput")


class MockProvider(MonitoringProvider):
    data_mode = "demo"
    default_vm = DEFAULT_VM
    vm_ids = VM_IDS

    def __init__(self, config, telegram_service):
        self.config = config
        self.telegram = telegram_service
        self.interval_seconds = max(config.get("POLL_INTERVAL_MS", 5000), 1000) / 1000.0
        self.window_seconds = config.get("STATS_WINDOW_SECONDS", 300)
        self.max_points = config.get("HISTORY_MAX_POINTS", 900)
        self.random = random.Random(20261020)
        self.lock = threading.Lock()

        self.vm_traffic = {
            vm: deque(maxlen=self.max_points) for vm in self.vm_ids
        }
        self.vm_qos = {
            vm: {metric: deque(maxlen=self.max_points) for metric in QOS_METRICS}
            for vm in self.vm_ids
        }
        self.hosts = {
            vm: {
                "cpu": deque(maxlen=self.max_points),
                "memory": deque(maxlen=self.max_points),
            }
            for vm in self.vm_ids
        }

        self._seed_history()
        self._blocked = self._seed_blocked()
        self._attacks = self._seed_attacks()

    def _resolve_vm(self, vm):
        selected = vm or self.default_vm
        if selected not in self.vm_ids:
            raise ValueError(f"VM tidak dikenal: {selected}")
        return selected

    def _seed_history(self):
        now = utc_now()
        step = max(self.interval_seconds, 1)
        history_seconds = max(CHART_RANGES.values())
        points = min(self.max_points, max(12, int(history_seconds // step) + 1))
        start = now - timedelta(seconds=(points - 1) * step)
        state = {vm: dict(VM_PROFILES[vm]) for vm in self.vm_ids}

        for index in range(points):
            timestamp = iso(start + timedelta(seconds=index * step))
            for vm, profile in state.items():
                profile["inbound"] = self._walk(profile["inbound"], 6.0, 8.0, 260.0)
                profile["outbound"] = self._walk(profile["outbound"], 3.2, 4.0, 180.0)
                profile["delay"] = self._walk(profile["delay"], 1.6, 9.0, 42.0)
                profile["jitter"] = self._walk(profile["jitter"], 0.35, 0.5, 7.5)
                profile["loss"] = self._walk(profile["loss"], 0.12, 0.0, 2.5)
                profile["throughput"] = self._walk(profile["throughput"], 6.0, 45.0, 145.0)
                profile["cpu"] = self._walk(profile["cpu"], 4.5, 6.0, 92.0)
                profile["memory"] = self._walk(profile["memory"], 2.0, 25.0, 93.0)

                self.vm_traffic[vm].append(
                    {
                        "t": timestamp,
                        "inbound": round(profile["inbound"], 2),
                        "outbound": round(profile["outbound"], 2),
                    }
                )
                self.vm_qos[vm]["delay"].append(
                    {"t": timestamp, "value": round(profile["delay"], 2)}
                )
                self.vm_qos[vm]["jitter"].append(
                    {"t": timestamp, "value": round(profile["jitter"], 2)}
                )
                self.vm_qos[vm]["packet_loss"].append(
                    {"t": timestamp, "value": round(profile["loss"], 2)}
                )
                self.vm_qos[vm]["throughput"].append(
                    {"t": timestamp, "value": round(profile["throughput"], 2)}
                )
                self.hosts[vm]["cpu"].append(
                    {"t": timestamp, "value": round(profile["cpu"], 2)}
                )
                self.hosts[vm]["memory"].append(
                    {"t": timestamp, "value": round(profile["memory"], 2)}
                )

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
            spreads = {
                "delay": (1.6, 9.0, 42.0),
                "jitter": (0.35, 0.5, 7.5),
                "packet_loss": (0.12, 0.0, 2.5),
                "throughput": (6.0, 45.0, 145.0),
            }
            for vm, profile in {vm: dict(VM_PROFILES[vm]) for vm in self.vm_ids}.items():
                last_traffic = self.vm_traffic[vm][-1]
                profile["inbound"] = self._walk(last_traffic["inbound"], 6.0, 8.0, 260.0)
                profile["outbound"] = self._walk(last_traffic["outbound"], 3.2, 4.0, 180.0)
                self.vm_traffic[vm].append(
                    {
                        "t": timestamp,
                        "inbound": round(profile["inbound"], 2),
                        "outbound": round(profile["outbound"], 2),
                    }
                )

                for key in QOS_METRICS:
                    previous = self.vm_qos[vm][key][-1]["value"]
                    spread, low, high = spreads[key]
                    self.vm_qos[vm][key].append(
                        {
                            "t": timestamp,
                            "value": round(self._walk(previous, spread, low, high), 2),
                        }
                    )

                cpu = self.hosts[vm]["cpu"][-1]["value"]
                memory = self.hosts[vm]["memory"][-1]["value"]
                self.hosts[vm]["cpu"].append(
                    {"t": timestamp, "value": round(self._walk(cpu, 4.5, 6.0, 92.0), 2)}
                )
                self.hosts[vm]["memory"].append(
                    {"t": timestamp, "value": round(self._walk(memory, 2.0, 25.0, 93.0), 2)}
                )
            self._last_sample = now

    def _window(self, series, window_seconds=None):
        seconds = self.window_seconds if window_seconds is None else int(window_seconds)
        cutoff = utc_now() - timedelta(seconds=seconds)
        result = []
        for point in series:
            timestamp = parse_iso(point.get("t"))
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

    def get_overview(self, vm=None, window_seconds=None):
        selected = self._resolve_vm(vm)
        window = self.window_seconds if window_seconds is None else int(window_seconds)
        self._maybe_append_sample()

        if VM_TRAFFIC.get(selected, True):
            traffic_series = self._window(self.vm_traffic[selected], window)
            traffic = {
                "status": "ok" if traffic_series else "empty",
                "source": f"{TRAFFIC_SOURCE} · {selected}",
                "unit": "Mbps",
                "error": None if traffic_series else "Belum ada sampel traffic.",
                "series": traffic_series,
            }
        else:
            traffic = {
                "status": "unavailable",
                "source": f"{TRAFFIC_SOURCE} · {selected}",
                "unit": "Mbps",
                "error": "Network flow tidak tersedia untuk VM ini.",
                "series": [],
                "disabled": True,
            }

        metrics = {}
        for key, unit in (
            ("delay", "ms"),
            ("jitter", "ms"),
            ("packet_loss", "%"),
            ("throughput", "Mbps"),
        ):
            series = self._window(self.vm_qos[selected][key], window)
            metrics[key] = build_metric(series, unit, f"{QOS_SOURCE} · {selected}")
            if not series:
                metrics[key].update(status="empty", error="Belum ada sampel pengukuran.")

        qos = {
            "status": "ok",
            "source": f"{QOS_SOURCE} · {selected}",
            "error": None,
            "metrics": metrics,
            "test": {
                "protocol": self.config.get("IPERF3_TEST_PROTOCOL", "udp").upper(),
                "direction": "upload",
                "client": "monitoring-laptop (DEMO)",
                "server": f"{selected} (DEMO)",
                "duration_seconds": self.config.get("IPERF3_TEST_DURATION_SECONDS", 10),
                "status": "success",
                "timestamp": iso(self._last_sample),
            },
        }

        host_ids = self.vm_ids if vm is None else (selected,)
        hosts = []
        for host in host_ids:
            cpu_series = self._window(self.hosts[host]["cpu"], window)
            memory_series = self._window(self.hosts[host]["memory"], window)
            hosts.append(
                {
                    "id": host,
                    "host": host,
                    "status": "ok" if cpu_series and memory_series else "empty",
                    "source": f"{RESOURCE_SOURCE} · {host}",
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
            "vm": selected,
            "traffic": traffic,
            "qos": qos,
            "resources": resources,
            "blocked_ips": {
                "status": "ok" if self._blocked else "empty",
                "source": FAIL2BAN_SOURCE,
                "error": None,
                "items": self._blocked,
                "total": len(self._blocked),
                "truncated": False,
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
