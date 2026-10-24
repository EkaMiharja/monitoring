import math
import threading
from collections import deque
from datetime import timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from config import DEFAULT_VM, VM_IDS, VM_TRAFFIC
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

FLOW_URL_KEYS = {
    "lightgbm-vm": "FLOW_FEATURES_LIGHTGBM_URL",
    "randomforest-vm": "FLOW_FEATURES_RANDOM_FOREST_URL",
    "fail2ban-vm": "FLOW_FEATURES_FAIL2BAN_URL",
}

FLOW_TOKEN_KEYS = {
    "lightgbm-vm": "FLOW_FEATURES_LIGHTGBM_TOKEN",
    "randomforest-vm": "FLOW_FEATURES_RANDOM_FOREST_TOKEN",
    "fail2ban-vm": "FLOW_FEATURES_FAIL2BAN_TOKEN",
}

VM_LABEL_KEYS = {
    "lightgbm-vm": "GLANCES_LIGHTGBM_LABEL",
    "randomforest-vm": "GLANCES_RANDOM_FOREST_LABEL",
    "fail2ban-vm": "GLANCES_FAIL2BAN_LABEL",
}

QOS_API_URL_KEYS = {"fail2ban-vm": "FAIL2BAN_API_URL"}
QOS_API_TOKEN_KEYS = {"fail2ban-vm": "FAIL2BAN_API_TOKEN"}

QOS_KEYS = ("delay", "jitter", "packet_loss", "throughput")
FLOW_HISTORY_MAX_POINTS = 4000
FLOW_SERIES_MAX_POINTS = 300
FLOW_SAMPLE_LIMIT = 200
FLOW_FALLBACK_MAX_POINTS = 50


class LiveProvider(MonitoringProvider):
    data_mode = "live"
    default_vm = DEFAULT_VM
    vm_ids = VM_IDS

    def __init__(self, config, telegram_service):
        self.config = config
        self.telegram = telegram_service
        self.timeout = config.get("API_TIMEOUT_SECONDS", 4)
        self.window_seconds = config.get("STATS_WINDOW_SECONDS", 300)
        self.max_points = config.get("HISTORY_MAX_POINTS", 900)
        self.qos_vm = config.get("QOS_VM", DEFAULT_VM)
        if self.qos_vm not in self.vm_ids:
            self.qos_vm = DEFAULT_VM
        self.qos_targets = self._resolve_qos_targets()
        self.lock = threading.Lock()
        self.vm_qos = {
            vm: {metric: deque(maxlen=self.max_points) for metric in QOS_KEYS}
            for vm in self.vm_ids
        }
        self.resources = {
            host: {"cpu": deque(maxlen=self.max_points), "memory": deque(maxlen=self.max_points)}
            for host, _key, _label in HOSTS
        }
        self.flow_history = {vm: [] for vm in self.vm_ids}
        self.qos_runners = self._build_qos_runners()
        primary = self._primary_qos_vm()
        self.iperf_runner = self.qos_runners[primary]["iperf3"]
        self.delay_runner = self.qos_runners[primary]["ping"]
        self.iperf_meta = None
        self.iperf_error = None
        self.delay_meta = None
        self.iperf_state = {}
        self.delay_state = {}

    def _resolve_qos_targets(self):
        """Return {vm_id: host} untuk setiap VM yang punya target pengukuran QoS."""
        raw = (self.config.get("QOS_VMS") or "").strip()
        if raw:
            names = [part.strip() for part in raw.split(",") if part.strip()]
        else:
            names = [self.qos_vm]
        targets = self.config.get("QOS_TARGETS") or {}
        if not isinstance(targets, dict):
            targets = {}
        fallback = (self.config.get("IPERF3_SERVER_HOST") or "").strip()
        result = {}
        for name in names:
            if name not in self.vm_ids:
                continue
            host = str(targets.get(name) or "").strip() or fallback
            if host:
                result[name] = host
        return result

    def _primary_qos_vm(self):
        for name in self.qos_targets:
            return name
        return self.qos_vm

    def _build_qos_runners(self):
        runners = {}
        for vm, host in self.qos_targets.items():
            scoped = dict(self.config)
            scoped["IPERF3_SERVER_HOST"] = host
            scoped["PING_TARGET_HOST"] = host
            runners[vm] = {
                "iperf3": Iperf3Runner(scoped),
                "ping": PingRunner(scoped),
            }
        if not runners:
            runners[self.qos_vm] = {
                "iperf3": Iperf3Runner(self.config),
                "ping": PingRunner(self.config),
            }
        return runners

    def _runners_for(self, vm):
        return self.qos_runners.get(vm) or self.qos_runners.get(self._primary_qos_vm())

    def _qos_source_mode(self):
        mode = str(self.config.get("QOS_SOURCE_MODE") or "vm").strip().lower()
        return mode if mode in {"vm", "laptop"} else "vm"

    def _merge_vm_series(self, series_map, vm_qos, vm, window_seconds=None):
        """Ganti seri dengan histori probe in-VM (bila tersedia).

        Histori berisi banyak titik sehingga grafik bisa membentuk garis;
        probe terakhir dipakai sebagai fallback saat histori belum ada.
        """
        if not isinstance(vm_qos, dict):
            return series_map
        history = vm_qos.get("history")
        probe = vm_qos.get("probe")
        merged = dict(series_map)

        for key, probe_key in (
            ("delay", "delay_ms"),
            ("jitter", "jitter_ms"),
            ("packet_loss", "packet_loss_percent"),
            ("throughput", "throughput_mbps"),
        ):
            points = []
            if isinstance(history, list):
                for item in history:
                    if not isinstance(item, dict):
                        continue
                    point = self._series_from_probe(item, probe_key, time_key="t")
                    if point:
                        points.append(point)
            if not points and isinstance(probe, dict):
                point = self._series_from_probe(probe, probe_key, time_key="timestamp")
                if point:
                    points.append(point)
            if points:
                merged[key] = self._limit_series(points, window_seconds)
        return merged

    def _limit_series(self, points, window_seconds=None):
        """Batasi jumlah titik & buang yang di luar jendela waktu."""
        limited = points[-self.max_points:]
        return self._window(limited, window_seconds)

    def _vm_status_detail(self, vm_qos):
        """Status VM + info jumlah sampel probe untuk UI."""
        detail = dict(vm_qos) if isinstance(vm_qos, dict) else {}
        history = detail.get("history")
        detail["history_points"] = len(history) if isinstance(history, list) else 0
        detail.pop("history", None)
        detail["probe_interval_seconds"] = int(
            self.config.get("QOS_PROBE_INTERVAL_SECONDS", 10) or 10
        )
        return detail

    def _qos_protocol(self, vm):
        runner = self._runners_for(vm)["iperf3"]
        return str(getattr(runner, "protocol_in_use", None) or runner.protocol).lower()

    def _qos_api_url(self, vm):
        """Base URL API VM untuk vm terpilih (flow features atau API Fail2Ban)."""
        specific = self.config.get(QOS_API_URL_KEYS.get(vm, "")) or ""
        url = specific or self._flow_url_for(vm) or ""
        if not url:
            return ""
        return url.rsplit("/api/", 1)[0]

    def _qos_token_for(self, vm):
        key = QOS_API_TOKEN_KEYS.get(vm)
        if key:
            return (self.config.get(key) or "").strip() or None
        return self._flow_token_for(vm)

    def _load_vm_qos(self, vm):
        """Baca status QoS & pipeline dari dalam VM (endpoint /api/qos).

        Angka ini diukur di link yang sama dengan beban pipeline ML, jadi
        merepresentasikan dampak serangan terhadap performa server.
        """
        base = self._qos_api_url(vm)
        if not base:
            return None
        token = self._qos_token_for(vm)
        payload, error = self._get_json(f"{base}/api/qos", token)
        if error or not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _series_from_probe(probe, value_key, time_key="timestamp"):
        """Buat satu titik seri dari hasil probe in-VM."""
        if not isinstance(probe, dict):
            return None
        value = probe.get(value_key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        timestamp = probe.get(time_key) or probe.get("timestamp")
        if not timestamp:
            return None
        return {"t": timestamp, "value": round(float(value), 3)}

    def _resolve_vm(self, vm):
        selected = vm or self.default_vm
        if selected not in self.vm_ids:
            raise ValueError(f"VM tidak dikenal: {selected}")
        return selected

    def _flow_url_for(self, vm):
        specific = self.config.get(FLOW_URL_KEYS.get(vm, "")) or ""
        if vm == "randomforest-vm":
            return specific or self.config.get("FLOW_FEATURES_API_URL") or ""
        return specific

    def _vm_label(self, vm):
        return str(self.config.get(VM_LABEL_KEYS.get(vm, "")) or vm)

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

    def _window(self, series, window_seconds=None):
        seconds = self.window_seconds if window_seconds is None else int(window_seconds)
        cutoff = utc_now() - timedelta(seconds=seconds)
        result = []
        for point in series:
            timestamp = parse_iso(point.get("t"))
            if timestamp is not None and timestamp >= cutoff:
                result.append(point)
        return result

    @staticmethod
    def _with_query(url, **params):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({key: str(value) for key, value in params.items()})
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    def _append_once(self, series, timestamp, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if series and series[-1]["t"] == timestamp:
            return
        series.append({"t": timestamp, "value": round(float(value), 3)})

    def _load_iperf(self, vm):
        """Load iperf3 state for one VM (runner per VM, URL fallback bila ada)."""
        runner = self._runners_for(vm)["iperf3"]
        meta = None
        error = None

        if runner.configured():
            meta = runner.meta
            error = runner.status_error()
        else:
            url = self.config.get("IPERF3_RESULT_URL")
            if not url:
                error = runner.status_error() or "Endpoint hasil iperf3 belum dikonfigurasi."
            elif not self.config.get("IPERF3_ENABLED", False):
                error = "Pengujian iperf3 dinonaktifkan (IPERF3_ENABLED=false)."
            else:
                payload, load_error = self._get_json(url)
                if load_error:
                    error = load_error
                elif not isinstance(payload, dict):
                    error = "Format hasil pengukuran iperf3 tidak dikenali."
                else:
                    timestamp = payload.get("timestamp") or iso()
                    protocol = str(
                        payload.get("protocol")
                        or self.config.get("IPERF3_TEST_PROTOCOL", "udp")
                    ).lower()
                    throughput = payload.get("throughput_mbps", payload.get("throughput"))
                    jitter = payload.get("jitter_ms", payload.get("jitter"))
                    loss = payload.get("packet_loss_percent", payload.get("packet_loss"))
                    with self.lock:
                        self._append_once(self.vm_qos[vm]["throughput"], timestamp, throughput)
                        if protocol == "udp":
                            self._append_once(self.vm_qos[vm]["jitter"], timestamp, jitter)
                            self._append_once(self.vm_qos[vm]["packet_loss"], timestamp, loss)
                    meta = {
                        "protocol": protocol.upper(),
                        "direction": payload.get("direction", "upload"),
                        "client": payload.get("client")
                        or self.config.get("IPERF3_CLIENT_HOST")
                        or None,
                        "server": payload.get("server")
                        or self.qos_targets.get(vm)
                        or self.config.get("IPERF3_SERVER_HOST")
                        or None,
                        "duration_seconds": payload.get("duration_seconds")
                        or self.config.get("IPERF3_TEST_DURATION_SECONDS"),
                        "status": payload.get("status", "success"),
                        "timestamp": timestamp,
                    }

        self.iperf_state[vm] = {"meta": meta, "error": error}
        if vm == self._primary_qos_vm():
            self.iperf_meta = meta
            self.iperf_error = error

    def _load_delay(self, vm):
        """Load delay state for one VM."""
        runner = self._runners_for(vm)["ping"]
        meta = None
        error = None

        if runner.configured():
            meta = runner.meta
            error = runner.status_error()
            if not error and not runner.series():
                error = "Belum ada hasil pengukuran delay. Jalankan pengukuran."
        else:
            url = self.config.get("DELAY_API_URL")
            if not url:
                error = "Metode/sumber pengukuran delay belum ditentukan."
            else:
                payload, load_error = self._get_json(url)
                if load_error:
                    error = load_error
                elif not isinstance(payload, dict):
                    error = "Format hasil pengukuran delay tidak dikenali."
                else:
                    timestamp = payload.get("timestamp") or iso()
                    value = payload.get(
                        "delay_ms", payload.get("value_ms", payload.get("value"))
                    )
                    with self.lock:
                        self._append_once(self.vm_qos[vm]["delay"], timestamp, value)

        self.delay_state[vm] = {"meta": meta, "error": error}
        if vm == self._primary_qos_vm():
            self.delay_meta = meta
        return error

    def _qos_series(self, vm, window_seconds=None):
        runners = self._runners_for(vm)
        iperf_runner = runners["iperf3"]
        delay_runner = runners["ping"]
        if iperf_runner.configured():
            throughput = self._window(iperf_runner.series("throughput"), window_seconds)
            jitter = self._window(iperf_runner.series("jitter"), window_seconds)
            packet_loss = self._window(iperf_runner.series("packet_loss"), window_seconds)
        else:
            throughput = self._window(self.vm_qos[vm]["throughput"], window_seconds)
            jitter = self._window(self.vm_qos[vm]["jitter"], window_seconds)
            packet_loss = self._window(self.vm_qos[vm]["packet_loss"], window_seconds)

        if delay_runner.configured():
            delay = self._window(delay_runner.series(), window_seconds)
        else:
            delay = self._window(self.vm_qos[vm]["delay"], window_seconds)

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

    def _load_resources(self, vm=None, window_seconds=None):
        hosts = []
        any_ok = False
        for host, config_key, label_key in HOSTS:
            if vm is not None and host != vm:
                continue
            label = str(self.config.get(label_key) or host)
            url = self.config.get(config_key)
            if not url:
                hosts.append(
                    {
                        "id": host,
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
                        "id": host,
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
                cpu_series = self._window(self.resources[host]["cpu"], window_seconds)
                memory_series = self._window(self.resources[host]["memory"], window_seconds)

            if cpu is None and memory is None:
                hosts.append(
                    {
                        "id": host,
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
                    "id": host,
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

    def _blocked_sources(self):
        sources = []
        lightgbm_url = (self.config.get("LIGHTGBM_BLOCKED_API_URL") or "").strip()
        if lightgbm_url:
            token = (
                self.config.get("LIGHTGBM_API_TOKEN")
                or self.config.get("FLOW_FEATURES_LIGHTGBM_TOKEN")
            )
            sources.append({"name": "LightGBM", "url": lightgbm_url, "token": token})

        random_forest_url = (
            self.config.get("RANDOM_FOREST_BLOCKED_API_URL") or ""
        ).strip()
        if random_forest_url:
            token = (
                self.config.get("RANDOM_FOREST_API_TOKEN")
                or self.config.get("FLOW_FEATURES_RANDOM_FOREST_TOKEN")
                or self.config.get("ATTACK_HISTORY_API_TOKEN")
            )
            sources.append(
                {
                    "name": "Random Forest",
                    "url": random_forest_url,
                    "token": token,
                }
            )

        fail2ban_url = (self.config.get("FAIL2BAN_API_URL") or "").strip()
        if fail2ban_url:
            sources.append(
                {
                    "name": "Fail2Ban",
                    "url": fail2ban_url,
                    "token": self.config.get("FAIL2BAN_API_TOKEN"),
                }
            )
        return sources

    @staticmethod
    def _seconds_until(timestamp):
        parsed = parse_iso(timestamp)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((parsed - utc_now()).total_seconds()))

    def _normalize_blocked_item(self, raw, source_name):
        if not isinstance(raw, dict):
            return None
        ip = raw.get("ip") or raw.get("source_ip") or raw.get("address")
        if not ip:
            return None
        status = str(raw.get("status", "blocked")).lower()
        if status not in {"blocked", "banned", "active"}:
            return None

        unblock_at = (
            raw.get("unblock_at")
            or raw.get("blocked_until")
            or raw.get("unblock_time")
        )
        remaining = raw.get("remaining_seconds")
        if remaining is not None:
            try:
                remaining = max(0, int(remaining))
            except (TypeError, ValueError):
                remaining = None
        if remaining is None and unblock_at:
            remaining = self._seconds_until(unblock_at)

        return {
            "ip": ip,
            "blocked_at": raw.get("blocked_at") or raw.get("timestamp") or raw.get("time"),
            "unblock_at": unblock_at,
            "remaining_seconds": remaining,
            "jail": raw.get("jail") or raw.get("source") or "sshd",
            "status": "blocked",
            "source": source_name,
        }

    def _merge_blocked_item(self, merged, item):
        existing = merged.get(item["ip"])
        if existing is None:
            item["_sources"] = [item.pop("source")]
            merged[item["ip"]] = item
            return

        source = item["source"]
        if source not in existing["_sources"]:
            existing["_sources"].append(source)

        if item.get("blocked_at") and (
            not existing.get("blocked_at") or item["blocked_at"] > existing["blocked_at"]
        ):
            existing["blocked_at"] = item["blocked_at"]

        if item.get("jail"):
            existing["jail"] = item["jail"]

        if not item.get("unblock_at") or not existing.get("unblock_at"):
            existing["unblock_at"] = None
            existing["remaining_seconds"] = None
        elif item["unblock_at"] > existing["unblock_at"]:
            existing["unblock_at"] = item["unblock_at"]

    def _load_blocked(self):
        sources = self._blocked_sources()
        if not sources:
            return {
                "status": "unavailable",
                "source": "Blocked IP",
                "error": "Endpoint blocked IP belum dikonfigurasi.",
                "items": [],
                "total": 0,
                "truncated": False,
            }

        merged = {}
        names = []
        warnings = []
        for source in sources:
            payload, error = self._get_json(source["url"], source["token"])
            if error:
                warnings.append({"url": source["url"], "message": error})
                continue

            raw_items = payload.get("items") if isinstance(payload, dict) else payload
            if not isinstance(raw_items, list):
                warnings.append(
                    {
                        "url": source["url"],
                        "message": f"Format daftar IP dari {source['name']} tidak dikenali.",
                    }
                )
                continue
            if source["name"] not in names:
                names.append(source["name"])
            for raw in raw_items:
                item = self._normalize_blocked_item(raw, source["name"])
                if item is not None:
                    self._merge_blocked_item(merged, item)

        if not names and warnings:
            return {
                "status": "error",
                "source": "Blocked IP",
                "error": warnings[0]["message"],
                "items": [],
                "total": 0,
                "truncated": False,
                "warnings": warnings,
            }

        items = list(merged.values())
        for item in items:
            source_names = item.pop("_sources", [item.get("source") or "Blocked IP"])
            item["source"] = " + ".join(source_names)
            if item.get("unblock_at"):
                remaining = self._seconds_until(item["unblock_at"])
                if remaining is not None:
                    item["remaining_seconds"] = remaining
            else:
                item["remaining_seconds"] = None

        items.sort(key=lambda item: item.get("blocked_at") or "", reverse=True)
        label = " + ".join(names) if names else "Blocked IP"
        if warnings:
            label = f"{label} · {len(warnings)} sumber gagal"

        total = len(items)
        return {
            "status": "ok" if items else "empty",
            "source": label,
            "error": None,
            "items": items[:50],
            "total": total,
            "truncated": total > 50,
            "warnings": warnings,
        }

    def _attack_sources(self):
        """Return the configured attack history endpoints with their tokens."""
        sources = []
        seen_urls = set()

        def add_source(url, token):
            url = (url or "").strip()
            if not url or url in seen_urls:
                return
            seen_urls.add(url)
            sources.append({"url": url, "token": token})

        primary_url = (self.config.get("ATTACK_HISTORY_API_URL") or "").strip()
        primary_token = self.config.get("ATTACK_HISTORY_API_TOKEN")
        add_source(primary_url, primary_token)

        extra_urls = [
            url.strip()
            for url in (self.config.get("ATTACK_HISTORY_EXTRA_API_URLS") or "").split(",")
            if url.strip()
        ]
        extra_tokens = [
            token.strip()
            for token in (self.config.get("ATTACK_HISTORY_EXTRA_API_TOKENS") or "").split(",")
            if token.strip()
        ]
        for index, url in enumerate(extra_urls):
            token = extra_tokens[index] if index < len(extra_tokens) else primary_token
            add_source(url, token)

        add_source(
            self.config.get("FAIL2BAN_ATTACKS_API_URL"),
            self.config.get("FAIL2BAN_API_TOKEN"),
        )
        return sources

    @staticmethod
    def _select_attack_items(groups, limit=50):
        """Ambil event terbaru dengan satu slot minimal per sumber."""
        groups = [
            sorted(group, key=lambda item: item.get("detected_at") or "", reverse=True)
            for group in groups
            if group
        ]
        if not groups or limit <= 0:
            return []

        quota = max(1, limit // len(groups))
        selected = []
        selected_ids = set()
        for group in groups:
            for item in group[:quota]:
                if len(selected) >= limit:
                    break
                selected.append(item)
                selected_ids.add(id(item))

        remaining = sorted(
            (
                item
                for group in groups
                for item in group
                if id(item) not in selected_ids
            ),
            key=lambda item: item.get("detected_at") or "",
            reverse=True,
        )
        for item in remaining:
            if len(selected) >= limit:
                break
            selected.append(item)

        selected.sort(key=lambda item: item.get("detected_at") or "", reverse=True)
        return selected

    def _load_attacks(self):
        sources = self._attack_sources()
        if not sources:
            return {
                "status": "unavailable",
                "source": "API deteksi",
                "error": "Endpoint attack history belum dikonfigurasi.",
                "items": [],
            }

        groups = []
        names = []
        warnings = []
        for source in sources:
            payload, error = self._get_json(source["url"], source["token"])
            if error:
                warnings.append({"url": source["url"], "message": error})
                continue
            raw_items = payload.get("items") if isinstance(payload, dict) else payload
            label = payload.get("source") if isinstance(payload, dict) else None
            if not isinstance(raw_items, list):
                warnings.append(
                    {"url": source["url"], "message": "Format attack history tidak dikenali."}
                )
                continue
            if label and str(label) not in names:
                names.append(str(label))
            group = []
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                group.append(
                    {
                        "detected_at": raw.get("detected_at") or raw.get("timestamp") or raw.get("time"),
                        "source_ip": raw.get("source_ip") or raw.get("ip"),
                        "target": raw.get("target"),
                        "attack_type": raw.get("attack_type") or raw.get("type") or "SSH Brute Force",
                        "detection": raw.get("detection") or raw.get("result") or raw.get("prediction"),
                        "model": raw.get("model"),
                        "blocking_status": (
                            raw.get("blocking_status")
                            if raw.get("blocking_status") is not None
                            else raw.get("blocked")
                        ),
                    }
                )
            groups.append(group)

        if not names and warnings:
            return {
                "status": "error",
                "source": "API deteksi",
                "error": warnings[0]["message"],
                "items": [],
                "warnings": warnings,
            }

        items = self._select_attack_items(groups)
        label = " + ".join(names) if names else "API deteksi"
        if warnings:
            label = f"{label} · {len(warnings)} sumber gagal"

        return {
            "status": "ok" if items else "empty",
            "source": label,
            "error": None,
            "items": items,
            "warnings": warnings,
        }

    def _flow_token_for(self, vm):
        specific = (self.config.get(FLOW_TOKEN_KEYS.get(vm, "")) or "").strip()
        return (
            specific
            or self.config.get("FLOW_FEATURES_API_TOKEN")
            or self.config.get("ATTACK_HISTORY_API_TOKEN")
        )

    @staticmethod
    def _flow_event(item):
        if not isinstance(item, dict):
            return None
        timestamp = item.get("detected_at")
        values = item.get("features")
        if not timestamp or not isinstance(values, dict):
            return None
        if parse_iso(timestamp) is None:
            return None

        clean = {}
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value):
                continue
            clean[str(name)] = round(float(value), 6)
        if not clean:
            return None
        return {
            "detected_at": timestamp,
            "source_ip": item.get("source_ip"),
            "target": item.get("target"),
            "auth_result": item.get("auth_result"),
            "features": clean,
        }

    @staticmethod
    def _flow_key(item):
        features = item.get("features") or {}
        return (
            item.get("detected_at"),
            item.get("source_ip"),
            item.get("target"),
            item.get("auth_result"),
            tuple(sorted((str(key), str(value)) for key, value in features.items())),
        )

    def _merge_flow_history(self, vm, raw_items):
        events = [self._flow_event(item) for item in raw_items]
        events = [item for item in events if item is not None]
        if not events:
            return

        with self.lock:
            buffer = self.flow_history.setdefault(vm, [])
            keys = {self._flow_key(item) for item in buffer}
            for item in events:
                key = self._flow_key(item)
                if key in keys:
                    continue
                buffer.append(item)
                keys.add(key)
            buffer.sort(key=lambda item: parse_iso(item["detected_at"]).timestamp())
            if len(buffer) > FLOW_HISTORY_MAX_POINTS:
                decimated = buffer[::2]
                if decimated and decimated[-1] is not buffer[-1]:
                    decimated.append(buffer[-1])
                buffer[:] = decimated

    @staticmethod
    def _downsample_flow(items, max_points):
        if len(items) <= max_points:
            return items
        last = len(items) - 1
        indexes = {
            round(index * last / (max_points - 1))
            for index in range(max_points)
        }
        return [items[index] for index in sorted(indexes)]

    def _load_traffic(self, vm, window_seconds=None):
        """Build the flow feature monitor for one VM."""
        url = self._flow_url_for(vm)
        label = self._vm_label(vm)
        source = f"Flow features · {label}"
        if not url:
            return {
                "status": "unavailable",
                "source": source,
                "error": f"Endpoint flow features untuk {label} belum dikonfigurasi.",
                "features": [],
            }

        token = self._flow_token_for(vm)
        payload, error = self._get_json(
            self._with_query(url, limit=FLOW_SAMPLE_LIMIT), token
        )
        if error:
            return {
                "status": "error",
                "source": source,
                "error": error,
                "features": [],
            }

        raw_items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return {
                "status": "error",
                "source": source,
                "error": "Format flow features tidak dikenali.",
                "features": [],
            }

        self._merge_flow_history(vm, raw_items)
        with self.lock:
            buffered = list(self.flow_history.get(vm) or [])

        names = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(names, list) or not names:
            names = []
            for item in buffered:
                for name in item["features"]:
                    if name not in names:
                        names.append(name)

        seconds = self.window_seconds if window_seconds is None else int(window_seconds)
        cutoff = utc_now() - timedelta(seconds=seconds)
        ordered = [
            item
            for item in buffered
            if parse_iso(item["detected_at"]) >= cutoff
        ]
        range_empty = not ordered
        fallback = range_empty and bool(buffered)
        if fallback:
            latest_at = parse_iso(buffered[-1]["detected_at"])
            fallback_cutoff = latest_at - timedelta(seconds=seconds)
            ordered = [
                item
                for item in buffered
                if parse_iso(item["detected_at"]) >= fallback_cutoff
            ][-FLOW_FALLBACK_MAX_POINTS:]
        plot_items = self._downsample_flow(ordered, FLOW_SERIES_MAX_POINTS)

        def collect(items):
            series = {name: [] for name in names}
            for item in items:
                timestamp = item.get("detected_at")
                values = item.get("features") or {}
                for name in names:
                    value = values.get(name)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    if not math.isfinite(value):
                        continue
                    series[name].append(
                        {"t": timestamp, "value": round(float(value), 6)}
                    )
            return series

        full_series = collect(ordered)
        plot_series = collect(plot_items)

        features = []
        for name in names:
            points = full_series.get(name) or []
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
                    "series": plot_series.get(name) or [],
                }
            )

        latest = ordered[-1] if ordered else {}
        status = "ok" if any(feature["series"] for feature in features) else "empty"
        source_label = (payload.get("source") if isinstance(payload, dict) else None) or source
        if fallback:
            source_label = f"{source_label} · event terakhir di luar rentang"
        return {
            "status": status,
            "source": source_label,
            "error": None if status == "ok" else "Belum ada sampel fitur flow.",
            "feature_count": len(features),
            "range_empty": range_empty,
            "fallback_used": fallback,
            "sample": {
                "detected_at": latest.get("detected_at"),
                "source_ip": latest.get("source_ip"),
                "target": latest.get("target"),
                "auth_result": latest.get("auth_result"),
            },
            "features": features,
        }

    def _auto_status(self):
        scheduler = getattr(self, "qos_scheduler", None)
        base = {
            "enabled": False,
            "interval_seconds": None,
            "metrics": [],
            "running": False,
            "last_tick": None,
            "last_error": None,
            "active_vm": None,
            "vms": sorted(self.qos_targets),
        }
        if scheduler is None:
            return base
        status = dict(scheduler.status())
        status["vms"] = sorted(self.qos_targets)
        return status

    def get_overview(self, vm=None, window_seconds=None):
        selected = self._resolve_vm(vm)
        window = self.window_seconds if window_seconds is None else int(window_seconds)
        scheduler = getattr(self, "qos_scheduler", None)
        if scheduler is not None and vm:
            # VM yang sedang dibuka -> profil UDP (jitter & packet loss) jalan untuk VM ini.
            scheduler.set_active_vm(selected)
        qos_active = selected in self.qos_targets

        vm_qos = None
        if qos_active:
            self._load_iperf(selected)
            delay_error = self._load_delay(selected)
            series_map = self._qos_series(selected, window)
            if self._qos_source_mode() == "vm":
                vm_qos = self._load_vm_qos(selected)
                series_map = self._merge_vm_series(series_map, vm_qos, selected, window)
        else:
            delay_error = None
            series_map = {key: [] for key in QOS_KEYS}
        iperf_state = self.iperf_state.get(selected, {})
        iperf_error = iperf_state.get("error")
        qos_source = (
            f"iperf3 / ICMP ping \u00b7 {self._vm_label(selected)}"
            if qos_active
            else "iperf3 / delay probe"
        )
        loss_source = (
            "probe in-VM (ICMP ping)"
            if self._qos_source_mode() == "vm"
            else "iperf3 UDP"
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

            if not qos_active:
                error = (
                    f"QoS untuk {self._vm_label(selected)} belum dikonfigurasi. "
                    "Tambahkan VM ini ke QOS_VMS dan lengkapi targetnya."
                )
            elif key == "delay":
                error = delay_error or "Belum ada sampel pengukuran delay."
            elif key == "throughput":
                error = iperf_error or "Belum ada sampel pengukuran iperf3."
            elif key == "packet_loss" and self._qos_source_mode() == "vm":
                error = "Belum ada sampel pengukuran packet loss (ICMP ping)."
            elif self._qos_protocol(selected) != "udp":
                error = f"{key.replace('_', ' ').title()} hanya tersedia dari hasil iperf3 UDP."
            else:
                error = iperf_error or "Belum ada sampel pengukuran iperf3."
            metrics[key] = build_metric(
                series, unit, qos_source, status="unavailable", error=error
            )

        qos_status = "ok" if any(metrics[key]["series"] for key in metrics) else "unavailable"
        if not qos_active:
            qos_error = (
                f"QoS untuk {self._vm_label(selected)} belum dikonfigurasi. "
                "Tambahkan VM ini ke QOS_VMS agar pengukurannya dijalankan."
            )
        else:
            qos_error = None if qos_status == "ok" else (
                iperf_error or delay_error or "Belum ada hasil pengukuran QoS."
            )

        qos_test = iperf_state.get("meta") if qos_active else None
        if not qos_test:
            qos_test = {
                "protocol": self.config.get("IPERF3_TEST_PROTOCOL", "udp").upper(),
                "direction": "upload",
                "client": self.config.get("IPERF3_CLIENT_HOST") or None,
                "server": self.qos_targets.get(selected)
                or (self.config.get("IPERF3_SERVER_HOST") or None),
                "duration_seconds": self.config.get("IPERF3_TEST_DURATION_SECONDS"),
                "status": "unavailable",
                "timestamp": None,
            }

        if VM_TRAFFIC.get(selected, True):
            traffic = self._load_traffic(selected, window)
        else:
            traffic = {
                "status": "unavailable",
                "source": f"Flow features · {self._vm_label(selected)}",
                "error": "Network flow tidak tersedia untuk VM ini.",
                "features": [],
                "disabled": True,
            }
        resources = self._load_resources(selected if vm is not None else None, window)
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
            "vm": selected,
            "traffic": traffic,
            "qos": {
                "status": qos_status,
                "source": qos_source,
                "error": qos_error,
                "metrics": metrics,
                "sources": {
                    "delay": "probe in-VM (ICMP ping)",
                    "throughput": "probe in-VM (iperf3 TCP)",
                    "jitter": "probe in-VM (iperf3 UDP)",
                    "packet_loss": loss_source,
                },
                "vm_status": self._vm_status_detail(vm_qos),
                "test": qos_test,
                "delay_test": self.delay_state.get(selected, {}).get("meta")
                if qos_active
                else None,
                "auto": self._auto_status(),
            },
            "resources": resources,
            "blocked_ips": blocked,
            "attacks": attacks,
            "telegram": telegram,
            "errors": [],
        }
