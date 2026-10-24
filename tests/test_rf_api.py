import importlib.util
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rf_api", ROOT / "deploy" / "rf_api.py")
rf_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rf_api)


def make_db(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE detection_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            src_ip TEXT,
            dst_ip TEXT,
            src_port INTEGER,
            dst_port INTEGER,
            protocol TEXT,
            prediction TEXT NOT NULL,
            raw_prediction INTEGER,
            attack_probability REAL,
            confidence REAL,
            model TEXT,
            action TEXT,
            status TEXT
        )
        """
    )
    rows = [
        (
            "2026-10-20 04:36:01",
            "192.168.56.1",
            "192.168.56.103",
            55000,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            0.9875,
            0.9875,
            "RandomForestClassifier",
            "WOULD_BLOCK",
            "DETECTED",
        ),
        (
            "2026-10-20 04:35:29",
            "192.168.56.101",
            "192.168.56.103",
            55001,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            1.0,
            1.0,
            "RandomForestClassifier",
            "WOULD_BLOCK",
            "DETECTED",
        ),
        (
            "2026-10-20 04:35:00",
            "192.168.56.50",
            "192.168.56.103",
            55002,
            22,
            "6.0",
            "Benign",
            0,
            0.01,
            0.99,
            "RandomForestClassifier",
            "NONE",
            "DETECTED",
        ),
        (
            "2026-10-20 04:34:00",
            "192.168.56.1",
            "192.168.56.103",
            55003,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            0.9,
            0.9,
            "LightGBM",
            "WOULD_BLOCK",
            "DETECTED",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO detection_logs (
            timestamp, src_ip, dst_ip, src_port, dst_port, protocol,
            prediction, raw_prediction, attack_probability, confidence,
            model, action, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    connection.close()


def make_feature_file(path, rows):
    header = list(rf_api.FEATURE_NAMES) + [
        "src_ip",
        "dst_ip",
        "src_port",
        "dst_port",
        "protocol",
        "flow_start_time",
        "flow_end_time",
        "ssh_auth_result",
        "ssh_auth_timestamp",
    ]
    lines = [",".join(header)]
    for index, (auth_epoch, source_ip) in enumerate(rows):
        values = [str(index + 1)] * len(rf_api.FEATURE_NAMES)
        values += [
            source_ip,
            "192.168.56.103",
            "55000",
            "22",
            "TCP",
            str(auth_epoch - 2),
            str(auth_epoch - 1),
            "FAILED",
            str(auth_epoch),
        ]
        lines.append(",".join(values))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_fetch_features_returns_14_ordered_features(tmp_path):
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    make_feature_file(
        features_dir / "traffic-20261020-071900_features.csv",
        [(1792480776.0, "192.168.56.1")],
    )
    make_feature_file(
        features_dir / "traffic-20261020-072000_features.csv",
        [(1792480780.0, "192.168.56.2")],
    )

    items = rf_api.fetch_features(features_dir, 1)

    assert len(items) == 1
    assert items[0]["source_ip"] == "192.168.56.2"
    assert items[0]["target"] == "192.168.56.103:22"
    assert items[0]["auth_result"] == "FAILED"
    assert items[0]["detected_at"] == "2026-10-20T07:19:40Z"
    assert list(items[0]["features"]) == list(rf_api.FEATURE_NAMES)
    assert len(items[0]["features"]) == 17


def test_features_http_endpoint_requires_token(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    make_feature_file(
        features_dir / "traffic-20261020-071900_features.csv",
        [(1792480776.0, "192.168.56.1")],
    )
    token = "test-token-abcdefghijklmnopqrstuvwxyz"

    server = rf_api.build_server(
        "127.0.0.1",
        0,
        db_path,
        token,
        features_dir=features_dir,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/features", timeout=3)
        assert exc_info.value.code == 401

        request = urllib.request.Request(
            f"{base_url}/api/features?limit=5",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["feature_count"] == 17
        assert payload["features"] == list(rf_api.FEATURE_NAMES)
        assert len(payload["items"]) == 1
        assert len(payload["items"][0]["features"]) == 17
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_fetch_attacks_returns_only_verified_rf_attacks(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)

    items = rf_api.fetch_attacks(db_path, 50)

    assert len(items) == 2
    assert all(item["model"] == "RandomForestClassifier" for item in items)
    assert all(item["prediction"] == "SSH-Bruteforce" for item in items)
    assert all(item["blocking_status"] is None for item in items)
    assert items[0]["detected_at"] == "2026-10-20T04:36:01Z"
    assert items[0]["source_ip"] == "192.168.56.1"
    assert items[0]["target"] == "192.168.56.103:22"
    assert items[0]["attack_type"] == "SSH Brute Force"
    assert items[0]["detection"] == "Malicious"


def test_fetch_attacks_accepts_runtime_model_alias(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        INSERT INTO detection_logs (
            timestamp, src_ip, dst_ip, src_port, dst_port, protocol,
            prediction, raw_prediction, attack_probability, confidence,
            model, action, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-10-23 09:27:06",
            "192.168.56.101",
            "192.168.56.103",
            55000,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            1.0,
            1.0,
            "RandomForest",
            "BLOCKED",
            "BLOCKED",
        ),
    )
    connection.commit()
    connection.close()

    items = rf_api.fetch_attacks(db_path, 1)
    assert len(items) == 1
    assert items[0]["source_ip"] == "192.168.56.101"
    assert items[0]["model"] == "RandomForest"
    assert items[0]["blocking_status"] is None


def test_fetch_attacks_honours_limit(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)

    items = rf_api.fetch_attacks(db_path, 1)

    assert len(items) == 1
    assert items[0]["id"] == 1


@pytest.mark.parametrize("value", ["0", "201", "-1", "abc"])
def test_parse_limit_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        rf_api.parse_limit(value)


def test_authorization_header():
    token = "test-token-abcdefghijklmnopqrstuvwxyz"
    assert rf_api.is_authorized(f"Bearer {token}", token) is True
    assert rf_api.is_authorized(f"bearer {token}", token) is True
    assert rf_api.is_authorized("Bearer wrong", token) is False
    assert rf_api.is_authorized("", token) is False
    assert rf_api.is_authorized(f"Bearer {token}", "") is False


def test_http_endpoint_requires_token_and_returns_rf_items(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    token = "test-token-abcdefghijklmnopqrstuvwxyz"

    server = rf_api.build_server("127.0.0.1", 0, db_path, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/attacks", timeout=3)
        assert exc_info.value.code == 401

        request = urllib.request.Request(
            f"{base_url}/api/attacks?limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["source"] == "Random Forest (RF)"
        assert len(payload["items"]) == 1
        assert payload["items"][0]["model"] == "RandomForestClassifier"
        assert payload["items"][0]["blocking_status"] is None

        with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8"))["ok"] is True

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"{base_url}/api/attacks?limit=0",
                timeout=3,
            )
        assert exc_info.value.code in {400, 401}

        bad_limit = urllib.request.Request(
            f"{base_url}/api/attacks?limit=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(bad_limit, timeout=3)
        assert exc_info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _add_blocked_table(db_path, unblock_at):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE blocked_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL UNIQUE,
            first_blocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            model TEXT,
            status TEXT DEFAULT 'BLOCKED',
            unblock_at DATETIME
        )
        """
    )
    connection.execute(
        """
        INSERT INTO blocked_ips (
            ip_address, reason, model, status, unblock_at
        ) VALUES (?, ?, ?, 'BLOCKED', ?)
        """,
        (
            "192.168.56.1",
            "SSH-Bruteforce detected by Random Forest",
            "RandomForestClassifier",
            unblock_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO blocked_ips (
            ip_address, reason, model, status, unblock_at
        ) VALUES (?, ?, ?, 'UNBLOCKED', NULL)
        """,
        (
            "192.168.56.101",
            "SSH-Bruteforce detected by Random Forest",
            "RandomForestClassifier",
        ),
    )
    connection.commit()
    connection.close()


def test_fetch_blocked_and_blocking_status(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    unblock_at = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    _add_blocked_table(db_path, unblock_at)

    items = rf_api.fetch_blocked(db_path, 50)
    assert len(items) == 1
    assert items[0]["ip"] == "192.168.56.1"
    assert items[0]["status"] == "blocked"
    assert items[0]["source"] == "Random Forest"
    assert 0 < items[0]["remaining_seconds"] <= 60

    attacks = rf_api.fetch_attacks(db_path, 50)
    blocked_attack = next(item for item in attacks if item["source_ip"] == "192.168.56.1")
    unblocked_attack = next(
        item for item in attacks if item["source_ip"] == "192.168.56.101"
    )
    assert blocked_attack["blocking_status"] is True
    assert blocked_attack["unblock_at"] == items[0]["unblock_at"]
    assert unblocked_attack["blocking_status"] is False
    assert unblocked_attack["unblock_at"] is None


def test_fetch_blocked_without_unblock_column(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE blocked_ips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            first_blocked_at DATETIME,
            last_seen_at DATETIME,
            reason TEXT,
            model TEXT,
            status TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO blocked_ips (ip_address, status) VALUES (?, 'BLOCKED')",
        ("192.0.2.9",),
    )
    connection.commit()
    connection.close()

    items = rf_api.fetch_blocked(db_path)
    assert len(items) == 1
    assert items[0]["unblock_at"] is None
    assert items[0]["remaining_seconds"] is None


def test_http_blocked_endpoint_requires_token_and_returns_items(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    _add_blocked_table(
        db_path,
        (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )
    token = "test-token-abcdefghijklmnopqrstuvwxyz"

    server = rf_api.build_server("127.0.0.1", 0, db_path, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/api/blocked", timeout=3)
        assert exc_info.value.code == 401

        request = urllib.request.Request(
            f"{base_url}/api/blocked",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["source"] == "Random Forest"
        assert len(payload["items"]) == 1
        assert payload["items"][0]["ip"] == "192.168.56.1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
