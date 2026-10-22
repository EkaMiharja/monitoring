from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import db
from api.routes import bp as api_bp
from auth.decorators import login_required
from auth.routes import bp as auth_bp
from config import DEFAULT_VM, VM_IDS, Config, VM_SPECS
from security import get_csrf_token
from services.providers.live import LiveProvider
from services.providers.mock import MockProvider
from services.qos_scheduler import QosScheduler
from services.telegram import TelegramService


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if app.config["DATA_MODE"] not in {"demo", "live"}:
        app.config["DATA_MODE"] = "demo"

    if app.config["SECRET_KEY"] == "dev-only-change-me":
        app.logger.warning("SECRET_KEY belum diatur. Gunakan .env untuk konfigurasi produksi.")

    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    telegram_service = TelegramService(app.config)
    provider_class = MockProvider if app.config["DATA_MODE"] == "demo" else LiveProvider
    app.extensions["telegram_service"] = telegram_service
    provider = provider_class(app.config, telegram_service)
    app.extensions["monitoring_provider"] = provider
    for attribute, name in (("iperf_runner", "iperf3_runner"), ("delay_runner", "delay_runner")):
        runner = getattr(provider, attribute, None)
        if runner is not None:
            app.extensions[name] = runner

    scheduler = QosScheduler(
        app.config,
        runners_by_vm=getattr(provider, "qos_runners", {}) or {},
    )
    app.extensions["qos_scheduler"] = scheduler
    app.extensions["qos_runners"] = getattr(provider, "qos_runners", {}) or {}
    provider.qos_scheduler = scheduler
    if (
        app.config["DATA_MODE"] == "live"
        and scheduler.enabled
        and app.config.get("QOS_LOCAL_PROBE", False)
        and not app.config.get("TESTING")
    ):
        scheduler.start()

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_csrf_token,
            "app_name": "Dashboard",
            "data_mode": app.config["DATA_MODE"],
        }

    @app.get("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("auth.login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        vm_options = [
            {
                "id": spec["id"],
                "label": app.config.get(spec["label_key"]) or spec["id"],
                "role": spec["role"],
            }
            for spec in VM_SPECS
        ]
        requested_vm = (request.args.get("vm") or "").strip()
        active_vm = requested_vm if requested_vm in VM_IDS else DEFAULT_VM
        qos_vm = app.config.get("QOS_VM") or DEFAULT_VM
        if qos_vm not in VM_IDS:
            qos_vm = DEFAULT_VM
        provider = app.extensions["monitoring_provider"]
        qos_vms = list(getattr(provider, "qos_targets", {}) or {})
        return render_template(
            "dashboard/index.html",
            username=session.get("username", "User"),
            poll_interval_ms=app.config["POLL_INTERVAL_MS"],
            vm_options=vm_options,
            default_vm=active_vm,
            qos_vm=qos_vm,
            qos_vms=qos_vms,
            active_page="overview",
            page_name="Overview",
            overview_url=url_for("dashboard", vm=active_vm),
        )

    @app.get("/security")
    @login_required
    def security_feed():
        return render_template(
            "dashboard/security.html",
            username=session.get("username", "User"),
            poll_interval_ms=app.config["POLL_INTERVAL_MS"],
            active_page="security",
            page_name="Security Feed",
            overview_url=url_for("dashboard"),
        )

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'",
        )
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", "Permintaan tidak valid.")
        if wants_json():
            return jsonify(error="bad_request", message=message), 400
        return render_template("errors/error.html", code=400, message=message), 400

    @app.errorhandler(404)
    def not_found(_error):
        if wants_json():
            return jsonify(error="not_found", message="Endpoint tidak ditemukan."), 404
        return (
            render_template(
                "errors/error.html",
                code=404,
                message="Halaman yang Anda cari tidak ditemukan.",
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(_error):
        if wants_json():
            return jsonify(error="internal_error", message="Terjadi kesalahan pada server."), 500
        return (
            render_template(
                "errors/error.html",
                code=500,
                message="Terjadi kesalahan pada server. Coba lagi beberapa saat.",
            ),
            500,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
