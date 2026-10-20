from __future__ import annotations

import secrets
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
REQUIRED = [
    ROOT / "app.py",
    ROOT / "config.py",
    ROOT / "api" / "routes.py",
    ROOT / "services" / "providers" / "live.py",
]
if any(not path.exists() for path in REQUIRED):
    missing = [str(path) for path in REQUIRED if not path.exists()]
    raise SystemExit(
        "Jalankan script dari root proyek Dashboard. File tidak ditemukan: " + ", ".join(missing)
    )

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup_dir = ROOT / f".qos-integration-backup-{stamp}"
backup_dir.mkdir()
for path in REQUIRED:
    backup_target = backup_dir / path.relative_to(ROOT)
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_target)

def replace_once(path: Path, old: str, new: str, description: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Tidak bisa menerapkan perubahan '{description}': ditemukan {count} anchor, harus 1. "
            f"File belum diubah oleh langkah ini: {path.relative_to(ROOT)}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")

# Install module first (and include it in the rollback backup if it already existed).
module_target = ROOT / "services" / "remote_metrics.py"
module_source = Path(__file__).with_name("remote_metrics.py")
if not module_source.exists():
    raise SystemExit("File remote_metrics.py tidak ditemukan di sebelah script patch.")
if module_target.exists():
    module_backup = backup_dir / "services" / "remote_metrics.py"
    module_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(module_target, module_backup)
module_target.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(module_source, module_target)

config_path = ROOT / "config.py"
replace_once(
    config_path,
    '    QOS_HISTORY_POINTS = _int("QOS_HISTORY_POINTS", 240)\n',
    '    QOS_HISTORY_POINTS = _int("QOS_HISTORY_POINTS", 240)\n'
    '    REMOTE_METRICS_TOKEN = _text("REMOTE_METRICS_TOKEN")\n'
    '    REMOTE_METRICS_DB_PATH = _text("REMOTE_METRICS_DB_PATH", str(BASE_DIR / "instance" / "remote_metrics.db"))\n'
    '    REMOTE_METRICS_HOST_ID = _text("REMOTE_METRICS_HOST_ID", "qos-vm")\n'
    '    REMOTE_METRICS_HOST_LABEL = _text("REMOTE_METRICS_HOST_LABEL", "qos-vm (10.207.241.187)")\n',
    "konfigurasi remote metrics",
)

routes_path = ROOT / "api" / "routes.py"
replace_once(
    routes_path,
    'from flask import Blueprint, current_app, jsonify\n',
    'from hmac import compare_digest\n\n'
    'from flask import Blueprint, current_app, jsonify, request\n',
    "import autentikasi dan request API",
)
replace_once(
    routes_path,
    'from utils import iso, utc_now\n',
    'from utils import iso, utc_now\nfrom services.remote_metrics import RemoteMetricsStore\n',
    "import store remote metrics",
)
route_block = '''\n\n@bp.post("/metrics")
def receive_remote_metrics():
    """Receive signed QoS/resource samples from the VM agent (machine-to-machine)."""
    expected_token = str(current_app.config.get("REMOTE_METRICS_TOKEN") or "")
    if len(expected_token) < 24:
        return jsonify(error="metrics_receiver_not_configured", message="Token penerima metrik belum dikonfigurasi."), 503

    auth = request.headers.get("Authorization", "")
    scheme, separator, presented_token = auth.partition(" ")
    if not separator or scheme.lower() != "bearer" or not compare_digest(presented_token.strip(), expected_token):
        return jsonify(error="unauthorized", message="Token tidak valid."), 401

    if request.content_length is not None and request.content_length > 16 * 1024:
        return jsonify(error="payload_too_large", message="Payload metrik terlalu besar."), 413
    if not request.is_json:
        return jsonify(error="json_required", message="Content-Type harus application/json."), 415

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid_json", message="Body harus berupa objek JSON."), 400

    try:
        store = current_app.extensions.get("remote_metrics_store")
        if store is None:
            store = RemoteMetricsStore(current_app.config.get("REMOTE_METRICS_DB_PATH"))
            current_app.extensions["remote_metrics_store"] = store
        result = store.add_sample(
            payload,
            host_id=current_app.config.get("REMOTE_METRICS_HOST_ID", "qos-vm"),
        )
    except ValueError as exc:
        return jsonify(error="invalid_metrics", message=str(exc)), 400
    except Exception:
        current_app.logger.exception("Gagal menyimpan metrik dari agen VM")
        return jsonify(error="metrics_store_failed", message="Gagal menyimpan metrik. Periksa log backend."), 500

    return jsonify(ok=True, **result), 202
'''
with routes_path.open("r", encoding="utf-8") as f:
    routes_text = f.read()
if '@bp.post("/metrics")' in routes_text:
    raise SystemExit("Endpoint /api/metrics tampaknya sudah ada; patch dibatalkan untuk menghindari duplikasi.")
with routes_path.open("a", encoding="utf-8", newline="") as f:
    f.write(route_block)

live_path = ROOT / "services" / "providers" / "live.py"
replace_once(
    live_path,
    'from services.providers.base import MonitoringProvider\n',
    'from services.providers.base import MonitoringProvider\nfrom services.remote_metrics import RemoteMetricsStore\n',
    "import store pada LiveProvider",
)
replace_once(
    live_path,
    '        self.max_points = config.get("HISTORY_MAX_POINTS", 120)\n        self.lock = threading.Lock()\n',
    '        self.max_points = config.get("HISTORY_MAX_POINTS", 120)\n'
    '        self.remote_host_id = str(config.get("REMOTE_METRICS_HOST_ID") or "qos-vm")\n'
    '        self.remote_host_label = str(config.get("REMOTE_METRICS_HOST_LABEL") or self.remote_host_id)\n'
    '        self.remote_metrics = RemoteMetricsStore(config.get("REMOTE_METRICS_DB_PATH"))\n'
    '        self.lock = threading.Lock()\n',
    "inisialisasi remote metrics",
)
old_series_return = '''        return {
            "delay": delay,
            "jitter": jitter,
            "packet_loss": packet_loss,
            "throughput": throughput,
        }
'''
new_series_return = '''        combined = {
            "delay": delay,
            "jitter": jitter,
            "packet_loss": packet_loss,
            "throughput": throughput,
        }
        remote_series = self.remote_metrics.qos_series(
            self.remote_host_id, self.window_seconds, self.max_points
        )
        # Prefer the remote VM agent series for metrics it supplies; fall back to
        # the dashboard's existing local runners for metrics not yet received.
        for key, series in remote_series.items():
            if series:
                combined[key] = series
        return combined
'''
replace_once(live_path, old_series_return, new_series_return, "gabungkan seri QoS remote")

resource_anchor = '''        status = "ok" if any_ok else "unavailable"
        return {
            "status": status,
            "source": "Glances",
'''
resource_insert = '''        remote = self.remote_metrics.resource_series(
            self.remote_host_id, self.window_seconds, self.max_points
        )
        remote_cpu = remote["cpu"]
        remote_memory = remote["memory"]
        if remote_cpu or remote_memory:
            remote_complete = bool(remote_cpu and remote_memory)
            resource_source = "VM QoS Agent / Glances"
            hosts.append(
                {
                    "host": self.remote_host_label,
                    "status": "ok" if remote_complete else "unavailable",
                    "source": resource_source,
                    "error": None if remote_complete else "Sebagian metrik CPU/RAM dari VM belum tersedia.",
                    "cpu": build_metric(
                        remote_cpu, "%", resource_source,
                        status="ok" if remote_cpu else "unavailable",
                        error=None if remote_cpu else "Sampel CPU belum tersedia.",
                    ),
                    "memory": build_metric(
                        remote_memory, "%", resource_source,
                        status="ok" if remote_memory else "unavailable",
                        error=None if remote_memory else "Sampel RAM belum tersedia.",
                    ),
                }
            )
            any_ok = any_ok or remote_complete

        status = "ok" if any_ok else "unavailable"
        return {
            "status": status,
            "source": "Glances + VM QoS Agent",
'''
replace_once(live_path, resource_anchor, resource_insert, "tambahkan host resource dari VM agent")

old_getoverview = '''        series_map = self._qos_series()
        qos_source = (
            "iperf3 / ICMP ping"
            if (self.iperf_runner.configured() or self.delay_runner.configured())
            else "iperf3 / delay probe"
        )
'''
new_getoverview = '''        remote_series = self.remote_metrics.qos_series(
            self.remote_host_id, self.window_seconds, self.max_points
        )
        series_map = self._qos_series()
        remote_active = any(remote_series.values())
        qos_source = (
            "VM QoS Agent (ICMP ping / iPerf3)"
            if remote_active
            else (
                "iperf3 / ICMP ping"
                if (self.iperf_runner.configured() or self.delay_runner.configured())
                else "iperf3 / delay probe"
            )
        )
'''
replace_once(live_path, old_getoverview, new_getoverview, "sumber data QoS remote")

# Back up .env too, then ensure a machine-to-machine token exists without printing it.
env_path = ROOT / ".env"
if env_path.exists():
    shutil.copy2(env_path, backup_dir / ".env")
    env_text = env_path.read_text(encoding="utf-8")
else:
    env_text = ""
lines = env_text.splitlines()
token_index = next((i for i, line in enumerate(lines) if line.strip().startswith("REMOTE_METRICS_TOKEN=")), None)
new_token = secrets.token_urlsafe(32)
if token_index is None:
    lines.append("REMOTE_METRICS_TOKEN=" + new_token)
    changed_env = True
elif not lines[token_index].split("=", 1)[1].strip():
    lines[token_index] = "REMOTE_METRICS_TOKEN=" + new_token
    changed_env = True
else:
    changed_env = False
if changed_env:
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="")

print("Patch QoS berhasil diterapkan.")
print(f"Backup file asli: {backup_dir}")
print(f"Database metrik: {ROOT / 'instance' / 'remote_metrics.db'} (akan dibuat saat endpoint/provider pertama kali dipakai)")
print("Token REMOTE_METRICS_TOKEN dibuat/ditambahkan ke .env." if changed_env else "REMOTE_METRICS_TOKEN yang sudah ada dipertahankan.")
print("Jangan bagikan token di .env. Salin nilainya ke agent.env di VM secara langsung.")
print("Berikutnya: jalankan tes unit, lalu atur DATA_MODE=live dan restart aplikasi saat siap.")
