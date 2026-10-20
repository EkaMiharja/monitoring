from flask import Blueprint, current_app, jsonify

from auth.decorators import login_required
from security import csrf_protect
from utils import iso, utc_now

bp = Blueprint("api", __name__, url_prefix="/api")

SECTIONS = ("traffic", "qos", "resources", "blocked_ips", "attacks", "telegram")


def _collect_errors(payload):
    errors = []
    for key in SECTIONS:
        section = payload.get(key) or {}
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
    try:
        payload = provider.get_overview()
    except Exception:
        current_app.logger.exception("Gagal membangun data overview")
        return (
            jsonify(
                error="overview_failed",
                message="Gagal membangun data monitoring. Periksa log backend.",
            ),
            500,
        )

    payload["generated_at"] = iso(utc_now())
    payload["data_mode"] = provider.data_mode
    payload["poll_interval_ms"] = current_app.config["POLL_INTERVAL_MS"]
    payload["stats_window_seconds"] = current_app.config["STATS_WINDOW_SECONDS"]
    payload["errors"] = _collect_errors(payload)
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


@bp.post("/iperf3/run")
@login_required
def iperf3_run():
    csrf_protect()
    runner = current_app.extensions.get("iperf3_runner")
    if runner is None:
        return jsonify(ok=False, message="Runner iperf3 tidak tersedia pada mode data ini."), 409
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
    runner = current_app.extensions.get("delay_runner")
    if runner is None:
        return jsonify(ok=False, message="Runner delay tidak tersedia pada mode data ini."), 409
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
