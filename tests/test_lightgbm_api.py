import importlib.util
import json
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lightgbm_api", ROOT / "deploy" / "lightgbm_api.py"
)
lightgbm_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lightgbm_api)


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
            "2026-10-22 04:36:01",
            "192.168.56.1",
            "192.168.56.103",
            55000,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            0.9875,
            0.9875,
            "LightGBM",
            "WOULD_BLOCK",
            "DETECTED",
        ),
        (
            "2026-10-22 04:35:29",
            "192.168.56.101",
            "192.168.56.103",
            55001,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            1.0,
            1.0,
            "LightGBM",
            "WOULD_BLOCK",
            "DETECTED",
        ),
        (
            "2026-10-22 04:35:00",
            "192.168.56.50",
            "192.168.56.103",
            55002,
            22,
            "6.0",
            "Benign",
            0,
            0.01,
            0.99,
            "LightGBM",
            "NONE",
            "DETECTED",
        ),
        (
            "2026-10-22 04:34:00",
            "192.168.56.1",
            "192.168.56.103",
            55003,
            22,
            "6.0",
            "SSH-Bruteforce",
            1,
            0.9,
            0.9,
            "RandomForestClassifier",
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
    header = list(lightgbm_api.FEATURE_NAMES) + [
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
        values = [str(index + 1)] * len(lightgbm_api.FEATURE_NAMES)
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


def test_feature_names_match_lightgbm_model_inputs():
    assert lightgbm_api.FEATURE_NAMES == (
        "Protocol",
        "Flow Duration",
        "Tot Fwd Pkts",
        "Tot Bwd Pkts",
        "TotLen Fwd Pkts",
        "TotLen Bwd Pkts",
        "Flow Pkts/s",
        "Flow IAT Mean",
        "Flow IAT Std",
        "Fwd IAT Mean",
        "Bwd IAT Mean",
        "Fwd Pkts/s",
        "Bwd Pkts/s",
        "ACK Flag Cnt",
        "Init Fwd Win Byts",
        "Init Bwd Win Byts",
        "Fwd Seg Size Min",
    )
    assert lightgbm_api.DEFAULT_MODEL == "LightGBM"


def test_fetch_features_returns_17_ordered_features(tmp_path):
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    make_feature_file(
        features_dir / "traffic-20261022-071900_features.csv",
        [(1792480776.0, "192.168.56.1")],
    )
    make_feature_file(
        features_dir / "traffic-20261022-072000_features.csv",
        [(1792480780.0, "192.168.56.2")],
    )

    items = lightgbm_api.fetch_features(features_dir, 1)

    assert len(items) == 1
    assert items[0]["source_ip"] == "192.168.56.2"
    assert items[0]["target"] == "192.168.56.103:22"
    assert items[0]["auth_result"] == "FAILED"
    assert items[0]["detected_at"] == "2026-10-20T07:19:40Z"
    assert list(items[0]["features"]) == list(lightgbm_api.FEATURE_NAMES)
    assert len(items[0]["features"]) == 17


def test_features_http_endpoint_requires_token(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    make_feature_file(
        features_dir / "traffic-20261022-071900_features.csv",
        [(1792480776.0, "192.168.56.1")],
    )
    token = "test-token-abcdefghijklmnopqrstuvwxyz"

    server = lightgbm_api.build_server(
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
        assert payload["features"] == list(lightgbm_api.FEATURE_NAMES)
        assert payload["source"] == "LightGBM flow features"
        assert len(payload["items"]) == 1
        assert len(payload["items"][0]["features"]) == 17
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_fetch_attacks_returns_only_lightgbm_attacks(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)

    items = lightgbm_api.fetch_attacks(db_path, 50)

    assert len(items) == 2
    assert all(item["model"] == "LightGBM" for item in items)
    assert all(item["prediction"] == "SSH-Bruteforce" for item in items)
    assert all(item["blocking_status"] is None for item in items)
    assert items[0]["detected_at"] == "2026-10-22T04:36:01Z"
    assert items[0]["source_ip"] == "192.168.56.1"
    assert items[0]["target"] == "192.168.56.103:22"
    assert items[0]["attack_type"] == "SSH Brute Force"
    assert items[0]["detection"] == "Malicious"


def test_fetch_attacks_rejects_other_model(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)

    with pytest.raises(ValueError):
        lightgbm_api.fetch_attacks(db_path, 50, model="RandomForestClassifier")


def test_authorization_header():
    token = "test-token-abcdefghijklmnopqrstuvwxyz"
    assert lightgbm_api.is_authorized(f"Bearer {token}", token) is True
    assert lightgbm_api.is_authorized(f"bearer {token}", token) is True
    assert lightgbm_api.is_authorized("Bearer wrong", token) is False
    assert lightgbm_api.is_authorized("", token) is False
    assert lightgbm_api.is_authorized(f"Bearer {token}", "") is False


def test_http_endpoint_requires_token_and_returns_lightgbm_items(tmp_path):
    db_path = tmp_path / "ids.db"
    make_db(db_path)
    token = "test-token-abcdefghijklmnopqrstuvwxyz"

    server = lightgbm_api.build_server("127.0.0.1", 0, db_path, token)
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
        assert payload["source"] == "LightGBM"
        assert payload["model"] == "LightGBM"
        assert len(payload["items"]) == 1
        assert payload["items"][0]["model"] == "LightGBM"
        assert payload["items"][0]["blocking_status"] is None

        with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8"))["ok"] is True

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
