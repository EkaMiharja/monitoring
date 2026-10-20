from app import create_app


def test_overview_contract(auth_client):
    response = auth_client.get("/api/overview")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["data_mode"] == "demo"
    assert payload["poll_interval_ms"] == 5000
    assert set(
        ["traffic", "qos", "resources", "blocked_ips", "attacks", "telegram", "generated_at"]
    ).issubset(payload.keys())

    assert payload["traffic"]["status"] == "ok"
    assert payload["traffic"]["unit"] == "Mbps"
    assert len(payload["traffic"]["series"]) > 0

    for key in ("delay", "jitter", "packet_loss", "throughput"):
        metric = payload["qos"]["metrics"][key]
        assert metric["stats"]["count"] == len(metric["series"])
        values = [point["value"] for point in metric["series"]]
        if values:
            assert metric["stats"]["min"] == min(values)
            assert metric["stats"]["max"] == max(values)
            assert metric["stats"]["avg"] == round(sum(values) / len(values), 3)

    assert len(payload["resources"]["hosts"]) == 3
    for host in payload["resources"]["hosts"]:
        assert host["host"]
        assert host["cpu"]["stats"]["count"] == len(host["cpu"]["series"])
        assert host["memory"]["stats"]["count"] == len(host["memory"]["series"])

    assert payload["blocked_ips"]["items"]
    assert all(item["status"] == "blocked" for item in payload["blocked_ips"]["items"])
    assert payload["attacks"]["items"]
    assert payload["telegram"]["items"]


def test_overview_rejects_missing_auth(client):
    assert client.get("/api/overview").status_code == 401


def test_overview_filters_telemetry_by_vm(auth_client):
    payload = auth_client.get("/api/overview?vm=fail2ban-vm").get_json()

    assert payload["vm"] == {"id": "fail2ban-vm", "label": "fail2ban-vm"}
    assert payload["resources"]["status"] == "ok"
    assert [host["host"] for host in payload["resources"]["hosts"]] == ["fail2ban-vm"]
    assert payload["traffic"]["status"] == "ok"
    assert payload["traffic"]["source"].endswith("fail2ban-vm")
    assert payload["qos"]["status"] == "ok"
    assert set(payload["qos"]["metrics"]) == {"delay", "jitter", "packet_loss", "throughput"}


def test_overview_rejects_unknown_vm(auth_client):
    response = auth_client.get("/api/overview?vm=unknown-vm")
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_vm"
    assert "fail2ban-vm" in body["available_vms"]


def test_overview_legacy_without_vm_keeps_all_hosts(auth_client):
    payload = auth_client.get("/api/overview").get_json()
    assert payload["vm"]["id"] == "randomforest-vm"
    assert len(payload["resources"]["hosts"]) == 3


def test_telegram_test_endpoint_demo(auth_client):
    before = auth_client.get("/api/overview").get_json()["telegram"]["items"]
    response = auth_client.post("/api/telegram/test")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["record"]["status"] == "delivered"

    after = auth_client.get("/api/overview").get_json()["telegram"]["items"]
    assert len(after) == len(before) + 1


def test_live_mode_reports_unavailable_sources(tmp_path, client):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_RESULT_URL": "",
            "IPERF3_ENABLED": False,
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()
    assert payload["data_mode"] == "live"
    assert payload["traffic"]["status"] == "unavailable"
    assert payload["blocked_ips"]["status"] == "unavailable"
    assert payload["attacks"]["status"] == "unavailable"
    assert payload["qos"]["status"] == "unavailable"
    assert all(host["status"] == "unavailable" for host in payload["resources"]["hosts"])
    assert payload["errors"]


def test_live_mode_filters_one_vm_and_reports_missing_flow_source(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-vm.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "FLOW_FEATURES_LIGHTGBM_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_VM": "randomforest-vm",
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview?vm=lightgbm-vm").get_json()

    assert payload["vm"]["id"] == "lightgbm-vm"
    assert [host["host"] for host in payload["resources"]["hosts"]] == ["lightgbm-vm"]
    assert payload["traffic"]["status"] == "unavailable"
    assert "lightgbm-vm" in payload["traffic"]["error"]
    assert payload["qos"]["status"] == "unavailable"
    assert all(
        metric["status"] == "unavailable"
        for metric in payload["qos"]["metrics"].values()
    )
    assert payload["blocked_ips"]["status"] == "unavailable"


def test_live_attacks_sends_token_and_maps_rf_payload(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "source": "Random Forest (RF)",
                "items": [
                    {
                        "detected_at": "2026-10-20T04:36:01Z",
                        "source_ip": "192.168.56.1",
                        "target": "192.168.56.103:22",
                        "attack_type": "SSH Brute Force",
                        "detection": "Malicious",
                        "model": "RandomForestClassifier",
                        "blocking_status": None,
                    }
                ],
            }

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        return FakeResponse()

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-attacks.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "FLOW_FEATURES_API_URL": "",
            "ATTACK_HISTORY_API_TOKEN": "token-123",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    assert calls == [("http://rf.test/api/attacks", {"Accept": "application/json", "Authorization": "Bearer token-123"})]
    attacks = payload["attacks"]
    assert attacks["status"] == "ok"
    assert attacks["source"] == "Random Forest (RF)"
    assert attacks["items"] == [
        {
            "detected_at": "2026-10-20T04:36:01Z",
            "source_ip": "192.168.56.1",
            "target": "192.168.56.103:22",
            "attack_type": "SSH Brute Force",
            "detection": "Malicious",
            "model": "RandomForestClassifier",
            "blocking_status": None,
        }
    ]


def test_live_flow_features_uses_token_and_builds_feature_series(monkeypatch, tmp_path):
    from services.providers import live as live_module

    names = [f"Feature {index}" for index in range(1, 15)]
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    feature_payload = {
        "source": "Random Forest flow features",
        "features": names,
        "items": [
            {
                "detected_at": "2026-10-20T04:36:01Z",
                "source_ip": "192.168.56.1",
                "target": "192.168.56.103:22",
                "auth_result": "FAILED",
                "features": {name: 2.0 for name in names},
            },
            {
                "detected_at": "2026-10-20T04:35:29Z",
                "source_ip": "192.168.56.101",
                "target": "192.168.56.103:22",
                "auth_result": "FAILED",
                "features": {name: 1.0 for name in names},
            },
        ],
    }
    attack_payload = {
        "source": "Random Forest (RF)",
        "items": [
            {
                "detected_at": "2026-10-20T04:36:01Z",
                "source_ip": "192.168.56.1",
                "target": "192.168.56.103:22",
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": "RandomForestClassifier",
                "blocking_status": None,
            }
        ],
    }

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        if url.endswith("/api/features"):
            return FakeResponse(feature_payload)
        return FakeResponse(attack_payload)

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-features.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_API_TOKEN": "token-123",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    assert (
        "http://rf.test/api/features",
        {"Accept": "application/json", "Authorization": "Bearer token-123"},
    ) in calls
    traffic = payload["traffic"]
    assert traffic["status"] == "ok"
    assert traffic["source"] == "Random Forest flow features"
    assert traffic["feature_count"] == 14
    assert [feature["name"] for feature in traffic["features"]] == names
    assert traffic["sample"]["source_ip"] == "192.168.56.1"
    first = traffic["features"][0]
    assert first["current"] == 2.0
    assert first["previous"] == 1.0
    assert first["delta"] == 1.0
    assert [point["value"] for point in first["series"]] == [1.0, 2.0]
