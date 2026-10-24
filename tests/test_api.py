from datetime import datetime, timedelta, timezone

from app import create_app


def _recent_iso(seconds_ago=0):
    moment = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_overview_contract(auth_client):
    response = auth_client.get("/api/overview")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["data_mode"] == "demo"
    assert payload["poll_interval_ms"] == 5000
    assert payload["range"] == "5m"
    assert payload["stats_window_seconds"] == 300
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


def test_overview_range_expands_history(auth_client):
    five = auth_client.get("/api/overview?range=5m").get_json()
    hour = auth_client.get("/api/overview?range=1h").get_json()

    assert five["range"] == "5m"
    assert five["stats_window_seconds"] == 300
    assert hour["range"] == "1h"
    assert hour["stats_window_seconds"] == 3600
    assert len(hour["qos"]["metrics"]["delay"]["series"]) > len(
        five["qos"]["metrics"]["delay"]["series"]
    )
    assert len(hour["resources"]["hosts"][0]["cpu"]["series"]) > len(
        five["resources"]["hosts"][0]["cpu"]["series"]
    )


def test_overview_rejects_invalid_range(auth_client):
    response = auth_client.get("/api/overview?range=2h")
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_range"
    assert set(body["available_ranges"]) == {"5m", "30m", "1h"}


def test_overview_rejects_missing_auth(client):
    assert client.get("/api/overview").status_code == 401


def test_overview_filters_telemetry_by_vm(auth_client):
    payload = auth_client.get("/api/overview?vm=fail2ban-vm").get_json()

    assert payload["vm"] == {"id": "fail2ban-vm", "label": "fail2ban-vm"}
    assert payload["resources"]["status"] == "ok"
    assert [host["host"] for host in payload["resources"]["hosts"]] == ["fail2ban-vm"]
    assert payload["traffic"]["status"] == "unavailable"
    assert payload["traffic"]["disabled"] is True
    assert payload["traffic"]["source"].endswith("fail2ban-vm")
    assert payload["qos"]["status"] == "ok"
    assert set(payload["qos"]["metrics"]) == {"delay", "jitter", "packet_loss", "throughput"}


def test_dashboard_hides_network_flow_for_fail2ban(auth_client):
    body = auth_client.get("/dashboard?vm=fail2ban-vm").get_data(as_text=True)

    assert "Network Flow" not in body
    assert "System Resource" in body
    assert "QoS Monitoring" in body


def test_dashboard_shows_network_flow_for_ml_vm(auth_client):
    body = auth_client.get("/dashboard?vm=lightgbm-vm").get_data(as_text=True)

    assert "Network Flow" in body
    assert "System Resource" in body
    assert "QoS Monitoring" in body


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


def test_overview_feeds_blocked_snapshot_to_notifier(auth_client):
    calls = []

    class FakeNotifier:
        def observe(self, section):
            calls.append(section)

    auth_client.application.extensions["blocked_notifier"] = FakeNotifier()
    response = auth_client.get("/api/overview")

    assert response.status_code == 200
    assert calls
    assert calls[0]["status"] == "ok"
    assert calls[0]["items"]


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
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
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
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "FLOW_FEATURES_LIGHTGBM_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
            "QOS_VM": "randomforest-vm",
            "QOS_AUTO_ENABLED": False,
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
                        "blocking_status": False,
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
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "",
            "ATTACK_HISTORY_API_TOKEN": "token-123",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
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
            "blocking_status": False,
        }
    ]


def test_live_blocked_sends_token_and_maps_items(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "source": "Fail2Ban",
                "items": [
                    {
                        "ip": "192.0.2.50",
                        "blocked_at": "2026-10-23T07:33:31Z",
                        "jail": "sshd",
                        "status": "blocked",
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
            "DATABASE": str(tmp_path / "live-blocked.db"),
            "SECRET_KEY": "live-blocked-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "http://fail2ban.test/api/blocked",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "FAIL2BAN_API_TOKEN": "fail2ban-token-123",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_VMS": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview?vm=fail2ban-vm").get_json()

    assert calls == [
        (
            "http://fail2ban.test/api/blocked",
            {
                "Accept": "application/json",
                "Authorization": "Bearer fail2ban-token-123",
            },
        )
    ]
    assert payload["blocked_ips"]["status"] == "ok"
    assert payload["blocked_ips"]["total"] == 1
    assert payload["blocked_ips"]["truncated"] is False
    assert payload["blocked_ips"]["items"] == [
        {
            "ip": "192.0.2.50",
            "blocked_at": "2026-10-23T07:33:31Z",
            "unblock_at": None,
            "remaining_seconds": None,
            "jail": "sshd",
            "status": "blocked",
            "source": "Fail2Ban",
        }
    ]


def test_live_blocked_merges_lightgbm_and_fail2ban(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    def response(items):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"items": items}

        return FakeResponse()

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        if url == "http://lightgbm.test/api/blocked":
            return response(
                [
                    {
                        "ip": "192.0.2.50",
                        "blocked_at": "2026-10-23T07:33:31Z",
                        "unblock_at": "2030-01-01T00:00:00Z",
                        "status": "blocked",
                        "jail": "sshd",
                    },
                    {
                        "ip": "192.0.2.60",
                        "blocked_at": "2026-10-23T07:34:00Z",
                        "unblock_at": "2030-01-01T00:00:00Z",
                        "status": "blocked",
                        "jail": "sshd",
                    },
                ]
            )
        if url == "http://random-forest.test/api/blocked":
            return response(
                [
                    {
                        "ip": "192.0.2.50",
                        "blocked_at": "2026-10-23T07:33:31Z",
                        "unblock_at": "2030-01-01T00:00:00Z",
                        "status": "blocked",
                        "jail": "sshd",
                    },
                    {
                        "ip": "192.0.2.90",
                        "blocked_at": "2026-10-23T07:36:00Z",
                        "status": "blocked",
                        "jail": "sshd",
                    },
                ]
            )
        return response(
            [
                {
                    "ip": "192.0.2.50",
                    "blocked_at": "2026-10-23T07:33:31Z",
                    "status": "blocked",
                    "jail": "sshd",
                },
                {
                    "ip": "192.0.2.70",
                    "blocked_at": "2026-10-23T07:35:00Z",
                    "status": "blocked",
                    "jail": "sshd",
                },
            ]
        )

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-blocked-merge.db"),
            "SECRET_KEY": "live-blocked-merge-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "LIGHTGBM_BLOCKED_API_URL": "http://lightgbm.test/api/blocked",
            "LIGHTGBM_API_TOKEN": "lightgbm-token-123",
            "RANDOM_FOREST_BLOCKED_API_URL": "http://random-forest.test/api/blocked",
            "RANDOM_FOREST_API_TOKEN": "random-forest-token-123",
            "FAIL2BAN_API_URL": "http://fail2ban.test/api/blocked",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "FAIL2BAN_API_TOKEN": "fail2ban-token-123",
            "ATTACK_HISTORY_API_URL": "",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_VMS": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview?vm=fail2ban-vm").get_json()

    assert calls == [
        (
            "http://lightgbm.test/api/blocked",
            {
                "Accept": "application/json",
                "Authorization": "Bearer lightgbm-token-123",
            },
        ),
        (
            "http://random-forest.test/api/blocked",
            {
                "Accept": "application/json",
                "Authorization": "Bearer random-forest-token-123",
            },
        ),
        (
            "http://fail2ban.test/api/blocked",
            {
                "Accept": "application/json",
                "Authorization": "Bearer fail2ban-token-123",
            },
        ),
    ]
    blocked = payload["blocked_ips"]
    assert blocked["status"] == "ok"
    assert blocked["source"] == "LightGBM + Random Forest + Fail2Ban"
    assert blocked["warnings"] == []
    assert blocked["total"] == 4
    assert blocked["truncated"] is False
    by_ip = {item["ip"]: item for item in blocked["items"]}
    assert set(by_ip) == {"192.0.2.50", "192.0.2.60", "192.0.2.70", "192.0.2.90"}
    assert by_ip["192.0.2.50"]["source"] == "LightGBM + Random Forest + Fail2Ban"
    assert by_ip["192.0.2.50"]["unblock_at"] is None
    assert by_ip["192.0.2.50"]["remaining_seconds"] is None
    assert by_ip["192.0.2.60"]["source"] == "LightGBM"
    assert by_ip["192.0.2.60"]["remaining_seconds"] > 0
    assert by_ip["192.0.2.70"]["source"] == "Fail2Ban"
    assert by_ip["192.0.2.70"]["unblock_at"] is None
    assert by_ip["192.0.2.90"]["source"] == "Random Forest"
    assert by_ip["192.0.2.90"]["remaining_seconds"] is None


def test_live_blocked_keeps_working_source_when_other_fails(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "ip": "192.0.2.80",
                        "blocked_at": "2026-10-23T07:36:00Z",
                        "status": "blocked",
                        "jail": "sshd",
                    }
                ]
            }

    def fake_get(url, timeout, headers):
        if url == "http://lightgbm.test/api/blocked":
            raise live_module.requests.RequestException("connection refused")
        return FakeResponse()

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-blocked-warning.db"),
            "SECRET_KEY": "live-blocked-warning-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "LIGHTGBM_BLOCKED_API_URL": "http://lightgbm.test/api/blocked",
            "LIGHTGBM_API_TOKEN": "lightgbm-token-123",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "FAIL2BAN_API_URL": "http://fail2ban.test/api/blocked",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "FAIL2BAN_API_TOKEN": "fail2ban-token-123",
            "ATTACK_HISTORY_API_URL": "",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_VMS": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    blocked = live_client.get("/api/overview?vm=fail2ban-vm").get_json()["blocked_ips"]

    assert blocked["status"] == "ok"
    assert blocked["source"] == "Fail2Ban · 1 sumber gagal"
    assert blocked["items"][0]["ip"] == "192.0.2.80"
    assert len(blocked["warnings"]) == 1
    assert blocked["warnings"][0]["url"] == "http://lightgbm.test/api/blocked"


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
                "detected_at": _recent_iso(10),
                "source_ip": "192.168.56.1",
                "target": "192.168.56.103:22",
                "auth_result": "FAILED",
                "features": {name: 2.0 for name in names},
            },
            {
                "detected_at": _recent_iso(42),
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
        if url.split("?")[0].endswith("/api/features"):
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
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "ATTACK_HISTORY_API_TOKEN": "token-123",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    assert (
        "http://rf.test/api/features?limit=200",
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


def test_live_flow_features_use_per_vm_token(monkeypatch, tmp_path):
    from services.providers import live as live_module

    names = [f"Feature {index}" for index in range(1, 18)]
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    feature_payload = {
        "source": "LightGBM flow features",
        "features": names,
        "items": [
            {
                "detected_at": _recent_iso(10),
                "source_ip": "192.168.56.1",
                "target": "192.168.56.103:22",
                "auth_result": "FAILED",
                "features": {name: 3.0 for name in names},
            }
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
        if url.split("?")[0].endswith("/api/features"):
            return FakeResponse(feature_payload)
        return FakeResponse(attack_payload)

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-features-vm.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_URLS": "",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "",
            "ATTACK_HISTORY_API_TOKEN": "token-rf",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "FLOW_FEATURES_LIGHTGBM_URL": "http://lgbm.test/api/features",
            "FLOW_FEATURES_LIGHTGBM_TOKEN": "token-lgbm",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview?vm=lightgbm-vm").get_json()

    assert (
        "http://lgbm.test/api/features?limit=200",
        {"Accept": "application/json", "Authorization": "Bearer token-lgbm"},
    ) in calls
    traffic = payload["traffic"]
    assert traffic["status"] == "ok"
    assert traffic["feature_count"] == 17
    assert [feature["name"] for feature in traffic["features"]] == names


def test_live_attacks_merges_multiple_sources(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    rf_payload = {
        "source": "Random Forest (RF)",
        "items": [
            {
                "detected_at": "2026-10-22T04:36:01Z",
                "source_ip": "192.168.56.1",
                "target": "192.168.56.103:22",
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": "RandomForestClassifier",
                "blocking_status": None,
            }
        ],
    }
    lgbm_payload = {
        "source": "LightGBM",
        "items": [
            {
                "detected_at": "2026-10-22T05:10:29Z",
                "source_ip": "192.168.56.101",
                "target": "192.168.56.102:22",
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": "LightGBM",
                "blocking_status": None,
            }
        ],
    }

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        if url.endswith("/api/attacks") and "lgbm.test" in url:
            return FakeResponse(lgbm_payload)
        return FakeResponse(rf_payload)

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-attacks-multi.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_API_TOKEN": "token-rf",
            "ATTACK_HISTORY_EXTRA_API_URLS": "http://lgbm.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "token-lgbm",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    assert (
        "http://rf.test/api/attacks",
        {"Accept": "application/json", "Authorization": "Bearer token-rf"},
    ) in calls
    assert (
        "http://lgbm.test/api/attacks",
        {"Accept": "application/json", "Authorization": "Bearer token-lgbm"},
    ) in calls

    attacks = payload["attacks"]
    assert attacks["status"] == "ok"
    assert attacks["source"] == "Random Forest (RF) + LightGBM"
    assert [item["model"] for item in attacks["items"]] == ["LightGBM", "RandomForestClassifier"]
    assert attacks["items"][0]["detected_at"] == "2026-10-22T05:10:29Z"
    assert attacks["warnings"] == []


def test_live_attacks_includes_fail2ban_source(monkeypatch, tmp_path):
    from services.providers import live as live_module

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    rf_items = [
        {
            "detected_at": f"2026-10-22T05:00:{index:02d}Z",
            "source_ip": "192.168.56.1",
            "target": "192.168.56.103:22",
            "attack_type": "SSH Brute Force",
            "detection": "Malicious",
            "model": "RandomForestClassifier",
            "blocking_status": None,
        }
        for index in range(60)
    ]
    payloads = {
        "http://rf.test/api/attacks": {
            "source": "Random Forest (RF)",
            "items": rf_items,
        },
        "http://lgbm.test/api/attacks": {
            "source": "LightGBM",
            "items": [
                {
                    "detected_at": "2026-10-22T03:00:00Z",
                    "source_ip": "192.168.56.101",
                    "target": "192.168.56.102:22",
                    "attack_type": "SSH Brute Force",
                    "detection": "Malicious",
                    "model": "LightGBM",
                    "blocking_status": None,
                }
            ],
        },
        "http://f2b.test/api/attacks": {
            "source": "Fail2Ban",
            "items": [
                {
                    "detected_at": "2026-10-22T04:00:00Z",
                    "source_ip": "192.168.56.111",
                    "target": None,
                    "attack_type": "SSH Brute Force",
                    "detection": "Malicious",
                    "model": "Fail2Ban",
                    "blocking_status": False,
                }
            ],
        },
    }

    def fake_get(url, timeout, headers):
        calls.append((url, headers))
        return FakeResponse(payloads[url])

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-attacks-f2b.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "FAIL2BAN_ATTACKS_API_URL": "http://f2b.test/api/attacks",
            "FAIL2BAN_API_TOKEN": "token-f2b",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_API_TOKEN": "token-rf",
            "ATTACK_HISTORY_EXTRA_API_URLS": "http://lgbm.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "token-lgbm",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    assert (
        "http://f2b.test/api/attacks",
        {"Accept": "application/json", "Authorization": "Bearer token-f2b"},
    ) in calls
    attacks = payload["attacks"]
    assert attacks["status"] == "ok"
    assert attacks["source"] == "Random Forest (RF) + LightGBM + Fail2Ban"
    assert len(attacks["items"]) == 50
    models = [item["model"] for item in attacks["items"]]
    assert models.count("RandomForestClassifier") == 48
    assert models.count("LightGBM") == 1
    assert models.count("Fail2Ban") == 1
    assert models[-2:] == ["Fail2Ban", "LightGBM"]
    f2b_item = next(item for item in attacks["items"] if item["model"] == "Fail2Ban")
    assert f2b_item["source_ip"] == "192.168.56.111"
    assert f2b_item["blocking_status"] is False


def test_live_attacks_reports_partial_source_failure(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    lgbm_payload = {
        "source": "LightGBM",
        "items": [
            {
                "detected_at": "2026-10-22T05:10:29Z",
                "source_ip": "192.168.56.101",
                "target": "192.168.56.102:22",
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": "LightGBM",
                "blocking_status": None,
            }
        ],
    }

    def fake_get(url, timeout, headers):
        if "rf.test" in url:
            raise live_module.requests.ConnectionError("tunnel mati")
        return FakeResponse(lgbm_payload)

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-attacks-partial.db"),
            "SECRET_KEY": "live-test",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "IPERF3_SERVER_HOST": "",
            "FAIL2BAN_API_URL": "",
            "FAIL2BAN_ATTACKS_API_URL": "",
            "LIGHTGBM_BLOCKED_API_URL": "",
            "RANDOM_FOREST_BLOCKED_API_URL": "",
            "ATTACK_HISTORY_API_URL": "http://rf.test/api/attacks",
            "ATTACK_HISTORY_API_TOKEN": "token-rf",
            "ATTACK_HISTORY_EXTRA_API_URLS": "http://lgbm.test/api/attacks",
            "ATTACK_HISTORY_EXTRA_API_TOKENS": "token-lgbm",
            "FLOW_FEATURES_API_URL": "",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "DELAY_API_URL": "",
            "PING_TARGET_HOST": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    live_client = app.test_client()
    with live_client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "live-tester"

    payload = live_client.get("/api/overview").get_json()

    attacks = payload["attacks"]
    assert attacks["status"] == "ok"
    assert attacks["source"] == "LightGBM · 1 sumber gagal"
    assert [item["model"] for item in attacks["items"]] == ["LightGBM"]
    assert len(attacks["warnings"]) == 1
    assert attacks["warnings"][0]["url"] == "http://rf.test/api/attacks"


def test_live_qos_range_filters_vm_history(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    history = []
    for index in range(720):
        history.append(
            {
                "t": _recent_iso((719 - index) * 10),
                "delay_ms": 10.0 + index,
                "jitter_ms": 1.0,
                "packet_loss_percent": 0.0,
                "throughput_mbps": 100.0,
            }
        )

    def fake_get(url, timeout, headers):
        if url.split("?")[0].endswith("/api/qos"):
            return FakeResponse(
                {
                    "probe": history[-1] | {"timestamp": history[-1]["t"]},
                    "history": history,
                    "load": {"load_1m": 0.5},
                    "capture_backlog": {"files": 0, "oldest_age_seconds": None},
                }
            )
        return FakeResponse({"items": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-qos-range.db"),
            "SECRET_KEY": "live-range-test",
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
        session["username"] = "range-tester"

    five = client.get("/api/overview?vm=randomforest-vm&range=5m").get_json()
    hour = client.get("/api/overview?vm=randomforest-vm&range=1h").get_json()

    five_delay = five["qos"]["metrics"]["delay"]
    hour_delay = hour["qos"]["metrics"]["delay"]
    assert hour_delay["stats"]["count"] == len(hour_delay["series"])
    assert 25 <= len(five_delay["series"]) <= 31
    assert 355 <= len(hour_delay["series"]) <= 361
    assert len(hour_delay["series"]) > len(five_delay["series"])


def test_live_flow_range_filters_buffered_events(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    feature_payload = {
        "source": "Flow test",
        "features": ["Feature 1"],
        "items": [
            {
                "detected_at": _recent_iso(10),
                "source_ip": "192.0.2.1",
                "target": "192.0.2.2:22",
                "auth_result": "FAILED",
                "features": {"Feature 1": 2.0},
            },
            {
                "detected_at": _recent_iso(600),
                "source_ip": "192.0.2.3",
                "target": "192.0.2.2:22",
                "auth_result": "FAILED",
                "features": {"Feature 1": 1.0},
            },
        ],
    }

    def fake_get(url, timeout, headers):
        if url.split("?")[0].endswith("/api/features"):
            return FakeResponse(feature_payload)
        return FakeResponse({"items": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-flow-range.db"),
            "SECRET_KEY": "live-flow-range",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "flow-range-tester"

    five = client.get("/api/overview?range=5m").get_json()["traffic"]
    hour = client.get("/api/overview?range=1h").get_json()["traffic"]

    five_series = five["features"][0]["series"]
    hour_series = hour["features"][0]["series"]
    assert [point["value"] for point in five_series] == [2.0]
    assert [point["value"] for point in hour_series] == [1.0, 2.0]


def test_live_flow_falls_back_when_range_has_no_events(monkeypatch, tmp_path):
    from services.providers import live as live_module

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    feature_payload = {
        "source": "LightGBM flow features",
        "features": ["Feature 1"],
        "items": [
            {
                "detected_at": _recent_iso(600),
                "source_ip": "192.0.2.1",
                "target": "192.0.2.2:22",
                "auth_result": "FAILED",
                "features": {"Feature 1": 3.0},
            },
            {
                "detected_at": _recent_iso(7200),
                "source_ip": "192.0.2.3",
                "target": "192.0.2.2:22",
                "auth_result": "FAILED",
                "features": {"Feature 1": 1.0},
            },
        ],
    }

    def fake_get(url, timeout, headers):
        if url.split("?")[0].endswith("/api/features"):
            return FakeResponse(feature_payload)
        return FakeResponse({"items": []})

    monkeypatch.setattr(live_module.requests, "get", fake_get)

    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "live-flow-fallback.db"),
            "SECRET_KEY": "live-flow-fallback",
            "CSRF_ENABLED": False,
            "DATA_MODE": "live",
            "IPERF3_ENABLED": False,
            "IPERF3_RESULT_URL": "",
            "DELAY_API_URL": "",
            "ATTACK_HISTORY_API_URL": "",
            "FLOW_FEATURES_API_URL": "http://rf.test/api/features",
            "GLANCES_LIGHTGBM_URL": "",
            "GLANCES_RANDOM_FOREST_URL": "",
            "GLANCES_FAIL2BAN_URL": "",
            "QOS_AUTO_ENABLED": False,
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["username"] = "flow-fallback-tester"

    five = client.get("/api/overview?range=5m").get_json()["traffic"]
    assert five["status"] == "ok"
    assert five["range_empty"] is True
    assert five["fallback_used"] is True
    assert "event terakhir di luar rentang" in five["source"]
    assert [point["value"] for point in five["features"][0]["series"]] == [3.0]

    half_hour = client.get("/api/overview?range=30m").get_json()["traffic"]
    assert half_hour["range_empty"] is False
    assert half_hour["fallback_used"] is False
    assert [point["value"] for point in half_hour["features"][0]["series"]] == [3.0]
    assert "event terakhir di luar rentang" not in half_hour["source"]
