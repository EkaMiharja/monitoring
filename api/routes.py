from flask import Blueprint, current_app, jsonify, request

from auth.decorators import login_required
from config import CHART_RANGES, DEFAULT_CHART_RANGE, VM_SPECS
from security import csrf_protect
from utils import iso, utc_now

bp = Blueprint("api", __name__, url_prefix="/api")

SECTIONS = ("traffic", "qos", "resources", "blocked_ips", "attacks", "telegram")
VM_LABEL_KEYS = {spec["id"]: spec["label_key"] for spec in VM_SPECS}


def _collect_errors(payload):
    errors = []
    for key in SECTIONS:
        section = payload.get(key) or {}
        if section.get("disabled"):
            continue
        status = section.get("status")
        if status in {"error", "unavailable"}:
            errors.append(
                {
                    "section": key,
                    "status": status,
                    "message": section.get("error") or "Sumber data tidak tersedia.",
                }
            )
    for host in (payload.get("resources") or {}).get("hosts", []):
        if host.get("status") in {"error", "unavailable"}:
            errors.append(
                {
                    "section": "resources",
                    "host": host.get("host"),
                    "status": host.get("status"),
                    "message": host.get("error") or "Host tidak dapat diakses.",
                }
            )
    return errors


@bp.get("/overview")
@login_required
def overview():
    provider = current_app.extensions["monitoring_provider"]
    vm = (request.args.get("vm") or "").strip() or None
    if vm is not None and vm not in provider.vm_ids:
        return (
            jsonify(
                error="invalid_vm",
                message=f"VM tidak dikenal: {vm}",
                available_vms=list(provider.vm_ids),
            ),
            400,
        )

    range_key = (request.args.get("range") or DEFAULT_CHART_RANGE).strip().lower()
    if range_key not in CHART_RANGES:
        return (
            jsonify(
                error="invalid_range",
                message=f"Rentang grafik tidak dikenal: {range_key}",
                available_ranges=list(CHART_RANGES),
            ),
            400,
        )
    window_seconds = CHART_RANGES[range_key]

    try:
        payload = provider.get_overview(vm=vm, window_seconds=window_seconds)
    except Exception:
        current_app.logger.exception("Gagal membangun data overview")
        return (
            jsonify(
                error="overview_failed",
                message="Gagal membangun data monitoring. Periksa log backend.",
            ),
            500,
        )

    selected = payload.get("vm") or provider.default_vm
    qos_vm = current_app.config.get("QOS_VM") or provider.default_vm
    if qos_vm not in provider.vm_ids:
        qos_vm = provider.default_vm
    payload["vm"] = {
        "id": selected,
        "label": current_app.config.get(VM_LABEL_KEYS.get(selected, ""), selected),
    }
    payload["qos_vm"] = {
        "id": qos_vm,
        "label": current_app.config.get(VM_LABEL_KEYS.get(qos_vm, ""), qos_vm),
    }
    payload["qos_vms"] = sorted(getattr(provider, "qos_targets", {}) or {})
    payload["generated_at"] = iso(utc_now())
    payload["data_mode"] = provider.data_mode
    payload["poll_interval_ms"] = current_app.config["POLL_INTERVAL_MS"]
    payload["range"] = range_key
    payload["stats_window_seconds"] = window_seconds
    payload["errors"] = _collect_errors(payload)
    notifier = current_app.extensions.get("blocked_notifier")
    if notifier is not None:
        notifier.observe(payload.get("blocked_ips") or {})
    return jsonify(payload)


@bp.post("/telegram/test")
@login_required
def telegram_test():
    csrf_protect()
    service = current_app.extensions["telegram_service"]
    try:
        ok, record = service.send_test_alert()
    except Exception:
        current_app.logger.exception("Gagal mengirim test alert Telegram")
        return jsonify(ok=False, message="Gagal mengirim test alert. Periksa log backend."), 500

    if ok:
        return jsonify(ok=True, record=record, message="Test alert diproses.")
    return jsonify(ok=False, record=record, message=record.get("detail", "Test alert gagal.")), 502


def _qos_runners_for(vm):
    """Return the runner pair of one VM (primary QoS VM bila vm tidak diisi)."""
    runners = current_app.extensions.get("qos_runners") or {}
    if vm:
        return runners.get(vm)
    for pair in runners.values():
        return pair
    return None


@bp.post("/iperf3/run")
@login_required
def iperf3_run():
    csrf_protect()
    vm = (request.args.get("vm") or "").strip()
    pair = _qos_runners_for(vm)
    runner = pair["iperf3"] if pair else None
    if runner is None:
        return jsonify(ok=False, message="QoS belum dikonfigurasi untuk VM ini."), 409
    if not runner.start():
        if runner.running:
            return jsonify(ok=False, running=True, message="Pengujian iperf3 masih berjalan."), 409
        return (
            jsonify(ok=False, message=runner.status_error() or "Pengujian iperf3 tidak dapat dimulai."),
            400,
        )
    return (
        jsonify(
            ok=True,
            running=True,
            estimated_seconds=runner.duration + 5,
            message="Pengujian iperf3 dimulai.",
        ),
        202,
    )


@bp.post("/delay/run")
@login_required
def delay_run():
    csrf_protect()
    vm = (request.args.get("vm") or "").strip()
    pair = _qos_runners_for(vm)
    if pair is None:
        return jsonify(ok=False, message="QoS belum dikonfigurasi untuk VM ini."), 409
    runner = pair["ping"]
    if not runner.start():
        if runner.running:
            return jsonify(ok=False, running=True, message="Pengukuran delay masih berjalan."), 409
        return (
            jsonify(ok=False, message=runner.status_error() or "Pengukuran delay tidak dapat dimulai."),
            400,
        )
    return (
        jsonify(
            ok=True,
            running=True,
            estimated_seconds=runner.count + 3,
            message="Pengukuran delay dimulai.",
        ),
        202,
    )
