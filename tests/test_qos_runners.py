from datetime import datetime, timedelta, timezone

from app import create_app
from services.delay import PingRunner
from services.iperf3 import Iperf3Runner


def make_iperf(**overrides):
    config = {"IPERF3_ENABLED": True, "IPERF3_SERVER_HOST": "192.0.2.1"}
    config.update(overrides)
    return Iperf3Runner(config)


def make_ping(**overrides):
    config = {"PING_TARGET_HOST": "192.0.2.1"}
    config.update(overrides)
    return PingRunner(config)


def test_iperf_parse_tcp():
    parsed = make_iperf().parse(
        {"end": {"sum_received": {"bits_per_second": 94_500_000}}}
    )
    assert parsed["throughput"] == 94.5
    assert parsed["jitter"] is None
    assert parsed["packet_loss"] is None


def test_iperf_parse_udp():
    parsed = make_iperf().parse(
        {
            "end": {
                "sum": {
                    "bits_per_second": 10_000_000,
                    "jitter_ms": 1.234,
                    "lost_percent": 2.5,
                },
                "sum_received": {"bits_per_second": 9_800_000},
            }
        }
    )
    assert parsed["throughput"] == 9.8
    assert parsed["jitter"] == 1.234
    assert parsed["packet_loss"] == 2.5


def test_iperf_command_builds_udp_bandwidth_and_duration():
    runner = make_iperf(
        IPERF3_TEST_PROTOCOL="udp",
        IPERF3_BANDWIDTH="50M",
        IPERF3_TEST_DURATION_SECONDS=5,
        IPERF3_OMIT_SECONDS=1,
    )
    command = runner._build_command()
    assert "-u" in command
    assert command[command.index("-b") + 1] == "50M"
    assert command[command.index("-t") + 1] == "5"
    assert command[command.index("-O") + 1] == "1"


def test_iperf_requires_enabled_and_server():
    assert not Iperf3Runner({"IPERF3_ENABLED": False, "IPERF3_SERVER_HOST": "192.0.2.1"}).configured()
    assert not Iperf3Runner({"IPERF3_ENABLED": True, "IPERF3_SERVER_HOST": ""}).configured()
    assert make_iperf().configured()


def test_ping_parse_windows_locale_en():
    stats = make_ping().parse(
        "Minimum = 10ms, Maximum = 14ms, Average = 12ms\n"
        "Packets: Sent = 4, Received = 3, Lost = 1 (25% loss),"
    )
    assert stats == {"avg": 12.0, "min": 10.0, "max": 14.0, "loss": 25.0}


def test_ping_parse_windows_locale_id():
    stats = make_ping().parse(
        "Minimum = 10ms, Maksimum = 14ms, Rata-rata = 12ms\n"
        "Paket: Dikirim = 4, Diterima = 4, Hilang = 0 (0% hilang),"
    )
    assert stats["avg"] == 12.0
    assert stats["loss"] == 0.0


def test_ping_parse_linux():
    stats = make_ping().parse(
        "rtt min/avg/max/mdev = 10.1/12.4/14.0/1.1 ms\n"
        "4 packets transmitted, 4 received, 0% packet loss"
    )
    assert stats["avg"] == 12.4
    assert stats["min"] == 10.1
    assert stats["max"] == 14.0


def test_ping_parse_unreachable():
    stats = make_ping().parse("Destination host unreachable.")
    assert stats["avg"] is None


def test_qos_run_endpoints_unavailable_in_demo(auth_client):
    assert auth_client.post("/api/iperf3/run").status_code == 409
    assert auth_client.post("/api/delay/run").status_code == 409


def test_live_qos_configured_but_not_run(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_SERVER_HOST": "192.0.2.1",
            "IPERF3_RESULT_URL": "",
            "PING_TARGET_HOST": "192.0.2.1",
            "DELAY_API_URL": "",
            "QOS_VMS": "randomforest-vm",
            "QOS_TARGETS": {"randomforest-vm": "192.0.2.1"},
            "FLOW_FEATURES_API_URL": "",
            "QOS_SOURCE_MODE": "laptop",
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    assert "iperf3_runner" in app.extensions
    assert "delay_runner" in app.extensions

    payload = client.get("/api/overview").get_json()
    assert payload["qos"]["status"] == "unavailable"
    assert payload["qos"]["source"] == "iperf3 / ICMP ping \u00b7 randomforest-vm"
    assert payload["qos"]["test"]["status"] == "unavailable"
    assert payload["qos"]["delay_test"] is None
    assert payload["qos"]["metrics"]["throughput"]["stats"]["count"] == 0


def test_live_qos_measured_per_vm(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        return FakeResponse({"items": [], "features": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-vm.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "QOS_VMS": "lightgbm-vm,randomforest-vm",
            "QOS_TARGETS": {
                "lightgbm-vm": "192.0.2.10",
                "randomforest-vm": "192.0.2.11",
            },
            "FLOW_FEATURES_API_URL": "",
            "QOS_SOURCE_MODE": "laptop",
        }
    )
    provider = app.extensions["monitoring_provider"]
    assert provider.qos_targets == {
        "lightgbm-vm": "192.0.2.10",
        "randomforest-vm": "192.0.2.11",
    }

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    payload = client.get("/api/overview?vm=randomforest-vm").get_json()
    assert payload["qos_vms"] == ["lightgbm-vm", "randomforest-vm"]
    assert payload["qos"]["source"] == "iperf3 / ICMP ping \u00b7 randomforest-vm"
    assert payload["qos"]["status"] == "unavailable"

    payload = client.get("/api/overview?vm=fail2ban-vm").get_json()
    assert payload["qos"]["status"] == "unavailable"
    assert "belum dikonfigurasi" in payload["qos"]["error"]


def test_manual_qos_actions_use_selected_vm(monkeypatch, tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-action.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "QOS_VMS": "lightgbm-vm,randomforest-vm",
            "QOS_TARGETS": {
                "lightgbm-vm": "192.0.2.10",
                "randomforest-vm": "192.0.2.11",
            },
            "FLOW_FEATURES_API_URL": "",
            "QOS_SOURCE_MODE": "laptop",
        }
    )
    provider = app.extensions["monitoring_provider"]
    started = []
    monkeypatch.setattr(
        provider.qos_runners["randomforest-vm"]["iperf3"],
        "start",
        lambda **kwargs: started.append("rf-iperf") or True,
    )
    monkeypatch.setattr(
        provider.qos_runners["randomforest-vm"]["ping"],
        "start",
        lambda **kwargs: started.append("rf-ping") or True,
    )
    monkeypatch.setattr(
        provider.qos_runners["lightgbm-vm"]["iperf3"],
        "start",
        lambda **kwargs: started.append("lgbm-iperf") or True,
    )

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    response = client.post("/api/iperf3/run?vm=randomforest-vm")
    assert response.status_code == 202
    response = client.post("/api/delay/run?vm=randomforest-vm")
    assert response.status_code == 202
    response = client.post("/api/iperf3/run?vm=fail2ban-vm")
    assert response.status_code == 409

    assert started == ["rf-iperf", "rf-ping"]


def test_overview_marks_active_vm_without_vm_param(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-active.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "QOS_VMS": "lightgbm-vm,randomforest-vm",
            "QOS_TARGETS": {
                "lightgbm-vm": "192.0.2.10",
                "randomforest-vm": "192.0.2.11",
            },
            "FLOW_FEATURES_API_URL": "",
            "QOS_SOURCE_MODE": "laptop",
        }
    )
    scheduler = app.extensions["qos_scheduler"]
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    payload = client.get("/api/overview?vm=randomforest-vm").get_json()
    assert payload["qos"]["auto"]["active_vm"] == "randomforest-vm"
    assert scheduler.active_vm == "randomforest-vm"

    # Halaman Security poll tanpa ?vm= -> VM aktif tidak boleh berubah.
    payload = client.get("/api/overview").get_json()
    assert payload["qos"]["auto"]["active_vm"] == "randomforest-vm"
    assert scheduler.active_vm == "randomforest-vm"

    payload = client.get("/api/overview?vm=lightgbm-vm").get_json()
    assert payload["qos"]["auto"]["active_vm"] == "lightgbm-vm"


def _iso(moment):
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_live_qos_uses_in_vm_probe_values(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    captured = []
    now = datetime.now(timezone.utc)

    def fake_get(url, timeout, headers):
        captured.append(url)
        if url.endswith("/api/qos"):
            return FakeResponse(
                {
                    "probe": {
                        "timestamp": _iso(now),
                        "target": "192.168.56.103",
                        "delay_ms": 12.5,
                        "jitter_ms": 3.25,
                        "packet_loss_percent": 1.5,
                        "throughput_mbps": 210.5,
                    },
                    "history": [],
                    "load": {"load_1m": 0.5},
                    "capture_backlog": {"files": 1, "oldest_age_seconds": 42.0},
                }
            )
        return FakeResponse({"items": [], "features": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-vmprobe.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "QOS_VMS": "randomforest-vm",
            "QOS_TARGETS": {"randomforest-vm": "192.0.2.11"},
            "FLOW_FEATURES_API_URL": "http://192.0.2.11:8080/api/features",
            "QOS_SOURCE_MODE": "vm",
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    payload = client.get("/api/overview?vm=randomforest-vm").get_json()
    qos = payload["qos"]

    assert "http://192.0.2.11:8080/api/qos" in captured
    assert qos["status"] == "ok"
    metrics = qos["metrics"]
    assert metrics["delay"]["series"][-1]["value"] == 12.5
    assert metrics["jitter"]["series"][-1]["value"] == 3.25
    assert metrics["packet_loss"]["series"][-1]["value"] == 1.5
    assert metrics["throughput"]["series"][-1]["value"] == 210.5
    assert qos["vm_status"]["load"]["load_1m"] == 0.5
    assert qos["vm_status"]["capture_backlog"]["files"] == 1


def test_live_qos_series_built_from_vm_history(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    now = datetime.now(timezone.utc)
    history = []
    for index in range(12):
        moment = now - timedelta(seconds=(11 - index) * 10)
        history.append(
            {
                "t": _iso(moment),
                "delay_ms": 1.0 + index,
                "jitter_ms": 0.5 + index * 0.1,
                "packet_loss_percent": 0.0,
                "throughput_mbps": 700.0 - index,
            }
        )

    def fake_get(url, timeout, headers):
        if url.endswith("/api/qos"):
            return FakeResponse(
                {
                    "probe": history[-1] | {"timestamp": history[-1]["t"]},
                    "history": history,
                    "load": {"load_1m": 1.0},
                    "capture_backlog": {"files": 0, "oldest_age_seconds": None},
                }
            )
        return FakeResponse({"items": [], "features": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-history.db"),
            "SECRET_KEY": "live-qos-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": True,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "QOS_VMS": "randomforest-vm",
            "QOS_TARGETS": {"randomforest-vm": "192.0.2.11"},
            "FLOW_FEATURES_API_URL": "http://192.0.2.11:8080/api/features",
            "QOS_SOURCE_MODE": "vm",
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "qos-tester"

    payload = client.get("/api/overview?vm=randomforest-vm").get_json()
    metrics = payload["qos"]["metrics"]

    for key in ("delay", "jitter", "packet_loss", "throughput"):
        series = metrics[key]["series"]
        assert len(series) == 12, key
    assert metrics["delay"]["series"][0]["value"] == 1.0
    assert metrics["delay"]["series"][-1]["value"] == 12.0
    assert metrics["throughput"]["series"][0]["value"] == 700.0
    assert metrics["throughput"]["series"][-1]["value"] == 689.0
    assert metrics["delay"]["stats"]["count"] == 12
    assert metrics["delay"]["stats"]["max"] == 12.0
