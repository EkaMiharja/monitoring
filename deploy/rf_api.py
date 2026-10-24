#!/usr/bin/env python3
"""Read-only HTTP API for Random Forest SSH brute-force detections.

This module only reads the existing IDS SQLite database (``detection_logs``
and ``blocked_ips``). It never writes to the database and never infers a
blocked state from a prediction.
"""

from __future__ import annotations

import csv
import hmac
import json
import math
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BASE_DIR / ".rf-api.env"
DEFAULT_DB_PATH = BASE_DIR / "database" / "ids.db"
DEFAULT_MODEL = "RandomForestClassifier"
RF_MODEL_NAMES = ("RandomForestClassifier", "RandomForest")
ATTACK_PREDICTION = "SSH-Bruteforce"
ATTACK_LABEL = "SSH Brute Force"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
DEFAULT_FEATURES_DIR = BASE_DIR / "capture" / "processed"
FEATURE_NAMES = (
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


def load_env_file(path):
    """Load simple KEY=VALUE lines without overriding real environment vars."""
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def utc_now_iso():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def iso_utc(value):
    """Convert a SQLite timestamp to an ISO-8601 UTC string."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_limit(value, default=DEFAULT_LIMIT, maximum=MAX_LIMIT):
    if value is None or value == "":
        return default
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit harus berupa bilangan bulat.") from exc
    if limit < 1 or limit > maximum:
        raise ValueError(f"limit harus antara 1 dan {maximum}.")
    return limit


def epoch_iso(value):
    """Convert a Unix timestamp to an ISO-8601 UTC string."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    try:
        return (
            datetime.fromtimestamp(number, timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return None


def _feature_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def read_feature_rows(path):
    """Read the 17 model inputs from one processed feature CSV."""
    path = Path(path)
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return rows
        exact = {}
        normalized = {}
        for raw_name in reader.fieldnames:
            if raw_name is None:
                continue
            name = str(raw_name).strip()
            exact.setdefault(name, raw_name)
            normalized.setdefault(name.lower(), raw_name)

        def column(name):
            return exact.get(name) or normalized.get(name.strip().lower())

        feature_columns = {name: column(name) for name in FEATURE_NAMES}
        if any(value is None for value in feature_columns.values()):
            return rows
        meta = {
            key: column(key)
            for key in (
                "src_ip",
                "dst_ip",
                "dst_port",
                "ssh_auth_result",
                "ssh_auth_timestamp",
                "flow_end_time",
                "protocol",
            )
        }

        for raw in reader:
            values = {}
            for name, raw_name in feature_columns.items():
                value = _feature_float(raw.get(raw_name))
                if value is None:
                    values = None
                    break
                values[name] = round(value, 6)
            if values is None:
                continue

            auth_epoch = _feature_float(
                raw.get(meta["ssh_auth_timestamp"]) if meta["ssh_auth_timestamp"] else None
            )
            flow_epoch = _feature_float(
                raw.get(meta["flow_end_time"]) if meta["flow_end_time"] else None
            )
            sort_value = auth_epoch if auth_epoch is not None else flow_epoch
            detected_at = epoch_iso(sort_value)
            if detected_at is None:
                sort_value = path.stat().st_mtime
                detected_at = epoch_iso(sort_value)

            dst_ip = raw.get(meta["dst_ip"]) if meta["dst_ip"] else None
            dst_port = raw.get(meta["dst_port"]) if meta["dst_port"] else None
            target = dst_ip or None
            if target and dst_port:
                target = f"{target}:{dst_port}"

            rows.append(
                {
                    "detected_at": detected_at,
                    "source_ip": (raw.get(meta["src_ip"]) if meta["src_ip"] else None)
                    or None,
                    "target": target,
                    "auth_result": (
                        raw.get(meta["ssh_auth_result"])
                        if meta["ssh_auth_result"]
                        else None
                    )
                    or None,
                    "protocol": (raw.get(meta["protocol"]) if meta["protocol"] else None)
                    or None,
                    "features": values,
                    "_sort": sort_value,
                }
            )
    return rows


def fetch_features(features_dir, limit=DEFAULT_LIMIT):
    """Return recent feature snapshots from the processed feature CSV files."""
    limit = parse_limit(limit)
    directory = Path(features_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Direktori fitur tidak ditemukan: {directory}")

    files = sorted(directory.glob("*.csv"), key=lambda item: item.name)
    max_files = min(400, max(20, limit))
    rows = []
    for path in files[-max_files:]:
        try:
            rows.extend(read_feature_rows(path))
        except (OSError, UnicodeError, csv.Error):
            continue

    rows.sort(key=lambda item: item["_sort"], reverse=True)
    items = rows[:limit]
    for item in items:
        item.pop("_sort", None)
    return items


def is_authorized(header, expected_token):
    if not expected_token:
        return False
    scheme, separator, presented = (header or "").partition(" ")
    if not separator or scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(presented.strip(), expected_token)


def remaining_seconds(unblock_at, now):
    if not unblock_at:
        return None
    try:
        parsed = datetime.fromisoformat(str(unblock_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((parsed.astimezone(timezone.utc) - now).total_seconds()))


def fetch_attacks(db_path, limit=DEFAULT_LIMIT, model=DEFAULT_MODEL):
    """Return recent SSH brute-force detections from the verified RF model."""
    limit = parse_limit(limit)
    if model != DEFAULT_MODEL:
        raise ValueError(f"Model tidak diizinkan: {model}")
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database tidak ditemukan: {path}")

    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """
            SELECT
                id,
                timestamp,
                src_ip,
                dst_ip,
                src_port,
                dst_port,
                protocol,
                prediction,
                attack_probability,
                confidence,
                model,
                action,
                status
            FROM detection_logs
            WHERE model IN (?, ?) AND prediction = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (*RF_MODEL_NAMES, ATTACK_PREDICTION, limit),
        ).fetchall()
        try:
            blocked_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(blocked_ips)"
                ).fetchall()
            }
            unblock_column = (
                "unblock_at"
                if "unblock_at" in blocked_columns
                else "NULL AS unblock_at"
            )
            blocked_rows = connection.execute(
                f"""
                SELECT ip_address, status, {unblock_column}
                FROM blocked_ips
                """
            ).fetchall()
        except sqlite3.OperationalError:
            blocked_rows = []
    finally:
        connection.close()

    blocked_ips = {
        str(row["ip_address"]): {
            "status": str(row["status"] or "").upper(),
            "unblock_at": iso_utc(row["unblock_at"]),
        }
        for row in blocked_rows
    }

    items = []
    for row in rows:
        target = row["dst_ip"]
        if target and row["dst_port"] is not None:
            target = f"{target}:{row['dst_port']}"
        blocked = blocked_ips.get(str(row["src_ip"]))
        blocking_status = None
        if blocked is not None:
            blocking_status = blocked["status"] == "BLOCKED"
        items.append(
            {
                "id": row["id"],
                "detected_at": iso_utc(row["timestamp"]),
                "source_ip": row["src_ip"],
                "target": target,
                "attack_type": ATTACK_LABEL,
                "detection": "Malicious",
                "model": row["model"],
                "prediction": row["prediction"],
                "attack_probability": row["attack_probability"],
                "confidence": row["confidence"],
                "action": row["action"],
                "status": row["status"],
                "blocking_status": blocking_status,
                "unblock_at": blocked["unblock_at"] if blocked else None,
            }
        )
    return items


def fetch_blocked(db_path, limit=DEFAULT_LIMIT):
    """Return currently blocked IPs with their scheduled auto-unblock time."""
    limit = parse_limit(limit)
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database tidak ditemukan: {path}")

    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(blocked_ips)"
            ).fetchall()
        }
        unblock_column = (
            "unblock_at" if "unblock_at" in columns else "NULL AS unblock_at"
        )
        rows = connection.execute(
            f"""
            SELECT
                id,
                ip_address,
                first_blocked_at,
                last_seen_at,
                reason,
                model,
                status,
                {unblock_column}
            FROM blocked_ips
            WHERE UPPER(status) = 'BLOCKED'
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        unblock_at = iso_utc(row["unblock_at"])
        items.append(
            {
                "id": row["id"],
                "ip": row["ip_address"],
                "blocked_at": iso_utc(row["first_blocked_at"]),
                "last_seen_at": iso_utc(row["last_seen_at"]),
                "unblock_at": unblock_at,
                "remaining_seconds": remaining_seconds(unblock_at, now),
                "jail": "sshd",
                "reason": row["reason"],
                "model": row["model"],
                "status": "blocked",
                "source": "Random Forest",
            }
        )
    return items



# ============================================================
# QOS PROBE (READ-ONLY)
# ============================================================

QOS_RESULT_PATH = BASE_DIR / "qos" / "last.json"
QOS_CACHE_SECONDS = 5
QOS_HISTORY_PATH = BASE_DIR / "qos" / "history.json"
_QOS_CACHE_LOCK = threading.Lock()
QOS_NET_INTERFACES = ("enp0s8", "enp0s3")
QOS_CAPTURE_DIR = BASE_DIR / "capture" / "raw"


def read_qos_probe():
    """Baca hasil probe QoS in-VM (satu file JSON kecil)."""
    try:
        with QOS_RESULT_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def read_loadavg():
    """Rata-rata beban 1/5/15 menit."""
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as handle:
            fields = handle.read().split()
    except OSError:
        return None
    if not fields:
        return None
    try:
        return {
            "load_1m": float(fields[0]),
            "load_5m": float(fields[1]),
            "load_15m": float(fields[2]),
        }
    except (IndexError, ValueError):
        return None


def read_network_counters():
    """Counter per interface (rx/tx byte, error, drop)."""
    result = {}
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return result
    for line in lines[2:]:
        if ":" not in line:
            continue
        name, _, values = line.partition(":")
        name = name.strip()
        if name not in QOS_NET_INTERFACES:
            continue
        parts = values.split()
        if len(parts) < 16:
            continue
        try:
            result[name] = {
                "rx_bytes": int(parts[0]),
                "rx_packets": int(parts[1]),
                "rx_errors": int(parts[2]),
                "rx_dropped": int(parts[3]),
                "tx_bytes": int(parts[8]),
                "tx_packets": int(parts[9]),
                "tx_errors": int(parts[10]),
                "tx_dropped": int(parts[11]),
            }
        except ValueError:
            continue
    return result


def read_capture_backlog():
    """Jumlah dan umur file PCAP yang menunggu diproses pipeline ML."""
    try:
        files = list(QOS_CAPTURE_DIR.glob("*.pcap"))
    except OSError:
        return {"files": 0, "oldest_age_seconds": None}
    if not files:
        return {"files": 0, "oldest_age_seconds": None}
    oldest = 0.0
    now = datetime.now(timezone.utc).timestamp()
    for path in files:
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age > oldest:
            oldest = age
    return {"files": len(files), "oldest_age_seconds": round(oldest, 1)}



def read_qos_history():
    """Baca histori probe QoS in-VM (array of dict, read-only)."""
    try:
        with QOS_HISTORY_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]

# Cache status QoS: /api/qos tidak perlu membaca file & /proc setiap request.
_QOS_CACHE = {"at": 0.0, "payload": None}


def collect_qos_status():
    """Kumpulkan status pipeline & beban server (ringan, tanpa query berat)."""
    now = time.monotonic()
    with _QOS_CACHE_LOCK:
        cached = _QOS_CACHE["payload"]
        if cached is not None and (now - _QOS_CACHE["at"]) < QOS_CACHE_SECONDS:
            return cached
    payload = {
        "probe": read_qos_probe(),
        "history": read_qos_history(),
        "load": read_loadavg(),
        "network": read_network_counters(),
        "capture_backlog": read_capture_backlog(),
    }
    with _QOS_CACHE_LOCK:
        _QOS_CACHE["at"] = now
        _QOS_CACHE["payload"] = payload
    return payload

class RFRequestHandler(BaseHTTPRequestHandler):
    server_version = "RFReadOnlyAPI/1.0"
    sys_version = ""

    def _send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        return is_authorized(
            self.headers.get("Authorization"),
            self.server.expected_token,
        )

    def _health(self):
        try:
            path = Path(self.server.db_path)
            if not path.is_file():
                raise FileNotFoundError
            uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=3)
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("SELECT 1").fetchone()
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            self._send_json(
                503,
                {"ok": False, "error": "database_unavailable"},
            )
            return
        self._send_json(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._health()
            return
        if parsed.path == "/api/qos":
            if not self._authorized():
                self._send_json(
                    401,
                    {"error": "unauthorized"},
                    {"WWW-Authenticate": 'Bearer realm="qos-api"'},
                )
                return
            self._send_json(200, collect_qos_status())
            return
        if parsed.path not in {"/api/attacks", "/api/features", "/api/blocked"}:
            self._send_json(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(
                401,
                {"error": "unauthorized"},
                {"WWW-Authenticate": 'Bearer realm="rf-api"'},
            )
            return

        raw_limit = parse_qs(parsed.query).get("limit", [None])[0]
        try:
            limit = parse_limit(raw_limit)
        except ValueError as exc:
            self._send_json(
                400,
                {"error": "invalid_limit", "message": str(exc)},
            )
            return

        if parsed.path == "/api/blocked":
            try:
                items = fetch_blocked(self.server.db_path, limit)
            except FileNotFoundError:
                self._send_json(
                    503,
                    {"error": "database_unavailable", "message": "Database tidak ditemukan."},
                )
                return
            except sqlite3.Error:
                self.log_error("database error while reading blocked IPs")
                self._send_json(
                    500,
                    {"error": "database_error", "message": "Gagal membaca database."},
                )
                return

            self._send_json(
                200,
                {
                    "generated_at": utc_now_iso(),
                    "source": "Random Forest",
                    "model": self.server.model,
                    "items": items,
                },
            )
            return

        if parsed.path == "/api/features":
            try:
                items = fetch_features(self.server.features_dir, limit)
            except FileNotFoundError:
                self._send_json(
                    503,
                    {
                        "error": "features_unavailable",
                        "message": "Direktori fitur tidak ditemukan.",
                    },
                )
                return
            except OSError:
                self.log_error("file error while reading features")
                self._send_json(
                    500,
                    {"error": "features_error", "message": "Gagal membaca fitur."},
                )
                return

            self._send_json(
                200,
                {
                    "generated_at": utc_now_iso(),
                    "source": "Random Forest flow features",
                    "model": self.server.model,
                    "feature_count": len(FEATURE_NAMES),
                    "features": list(FEATURE_NAMES),
                    "items": items,
                },
            )
            return

        try:
            items = fetch_attacks(
                self.server.db_path,
                limit,
                self.server.model,
            )
        except FileNotFoundError:
            self._send_json(
                503,
                {"error": "database_unavailable", "message": "Database tidak ditemukan."},
            )
            return
        except sqlite3.Error:
            self.log_error("database error while reading attacks")
            self._send_json(
                500,
                {"error": "database_error", "message": "Gagal membaca database."},
            )
            return

        self._send_json(
            200,
            {
                "generated_at": utc_now_iso(),
                "source": "Random Forest (RF)",
                "model": self.server.model,
                "items": items,
            },
        )

    def do_POST(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})

    def do_PUT(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})

    def do_DELETE(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})


def build_server(
    host,
    port,
    db_path,
    token,
    model=DEFAULT_MODEL,
    features_dir=DEFAULT_FEATURES_DIR,
):
    server = ThreadingHTTPServer((host, int(port)), RFRequestHandler)
    server.daemon_threads = True
    server.db_path = str(db_path)
    server.expected_token = token
    server.model = model
    server.features_dir = str(features_dir)
    return server


def main():
    load_env_file(os.environ.get("RF_API_ENV_FILE", str(DEFAULT_ENV_PATH)))

    token = (os.environ.get("RF_API_TOKEN") or "").strip()
    if len(token) < 24:
        print(
            "RF_API_TOKEN belum diatur dengan benar (minimal 24 karakter).",
            file=sys.stderr,
        )
        return 2

    model = (os.environ.get("RF_API_MODEL") or DEFAULT_MODEL).strip()
    if model != DEFAULT_MODEL:
        print(
            f"RF_API_MODEL harus {DEFAULT_MODEL!r}; ditemukan {model!r}.",
            file=sys.stderr,
        )
        return 2

    db_path = Path(
        os.environ.get("RF_API_DB_PATH") or DEFAULT_DB_PATH
    ).expanduser()
    if not db_path.is_file():
        print(f"Database tidak ditemukan: {db_path}", file=sys.stderr)
        return 2

    features_dir = Path(
        os.environ.get("RF_API_FEATURES_DIR") or DEFAULT_FEATURES_DIR
    ).expanduser()

    host = (os.environ.get("RF_API_BIND") or "127.0.0.1").strip()
    try:
        port = int(os.environ.get("RF_API_PORT") or "8080")
    except ValueError:
        print("RF_API_PORT harus berupa angka.", file=sys.stderr)
        return 2
    if not 1 <= port <= 65535:
        print("RF_API_PORT di luar rentang 1-65535.", file=sys.stderr)
        return 2

    try:
        server = build_server(
            host,
            port,
            db_path,
            token,
            model,
            features_dir,
        )
    except OSError as exc:
        print(f"Gagal membuka {host}:{port}: {exc}", file=sys.stderr)
        return 1

    print(f"RF read-only API listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
