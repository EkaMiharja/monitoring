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
    assert payload["qos"]["source"] == "iperf3 / ICMP ping"
    assert payload["qos"]["test"]["status"] == "unavailable"
    assert payload["qos"]["delay_test"] is None
    assert payload["qos"]["metrics"]["throughput"]["stats"]["count"] == 0
