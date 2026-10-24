#!/usr/bin/env python3
"""Read-only HTTP API for Fail2Ban blocked IPs, attack history, and in-VM QoS.

The API only reads current Fail2Ban jail state, the Fail2Ban log, and the QoS
probe files written by ``qos_probe.py``. It never bans or unbans an IP.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = BASE_DIR / ".fail2ban-api.env"
DEFAULT_CLIENT = "/usr/bin/fail2ban-client"
DEFAULT_LOG_PATH = "/var/log/fail2ban.log"
DEFAULT_QOS_DIR = BASE_DIR / "qos"
DEFAULT_ATTACKS_LIMIT = 50
MAX_ATTACKS_LIMIT = 200
CACHE_SECONDS = 5
SUBPROCESS_TIMEOUT = 5
LOG_ACTION_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+"
    r"fail2ban\.actions\s+\[\d+\]:\s+NOTICE\s+"
    r"\[(?P<jail>[^\]]+)\]\s+(?P<action>Ban|Unban)\s+(?P<ip>\S+)"
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


def is_authorized(header, expected_token):
    if not expected_token:
        return False
    scheme, separator, presented = (header or "").partition(" ")
    if not separator or scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(presented.strip(), expected_token)


def run_client(client_path, arguments, timeout=SUBPROCESS_TIMEOUT):
    """Run fail2ban-client and return (stdout, error)."""
    try:
        result = subprocess.run(
            [client_path, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return None, f"fail2ban-client gagal: {exc.__class__.__name__}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return None, detail or "fail2ban-client keluar dengan kode gagal."
    return result.stdout, None


def list_jails(status_output):
    """Extract jail names from ``fail2ban-client status`` output."""
    for line in (status_output or "").splitlines():
        if "Jail list:" not in line:
            continue
        raw = line.split("Jail list:", 1)[1]
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def parse_banned_ips(status_output):
    """Extract IPs from one ``fail2ban-client status <jail>`` response."""
    for line in (status_output or "").splitlines():
        if "Banned IP list:" not in line:
            continue
        raw = line.split("Banned IP list:", 1)[1]
        return [part for part in raw.replace(",", " ").split() if part]
    return []


def read_log_events(path, tail_lines=20000):
    """Return recent Ban/Unban events parsed from the Fail2Ban log."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-tail_lines:]
    except OSError as exc:
        raise RuntimeError("log Fail2Ban tidak terbaca.") from exc

    events = []
    for line in lines:
        match = LOG_ACTION_RE.search(line)
        if not match:
            continue
        try:
            timestamp = datetime.strptime(
                match.group("timestamp"), "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        events.append(
            {
                "detected_at": timestamp.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                ),
                "jail": match.group("jail"),
                "ip": match.group("ip"),
                "action": match.group("action"),
            }
        )
    return events


def read_ban_times(path, tail_lines=5000):
    """Map IP -> (jail, blocked_at) using the latest Ban line in the log."""
    try:
        events = read_log_events(path, tail_lines)
    except RuntimeError:
        return {}

    result = {}
    for event in events:
        if event["action"] != "Ban":
            continue
        result[event["ip"]] = (event["jail"], event["detected_at"])
    return result


def collect_attacks(log_path=DEFAULT_LOG_PATH, limit=DEFAULT_ATTACKS_LIMIT):
    """Return recent Ban events as attack history rows."""
    events = read_log_events(log_path)
    latest_action = {}
    for event in events:
        latest_action[event["ip"]] = event["action"]

    items = []
    for event in reversed(events):
        if event["action"] != "Ban":
            continue
        if len(items) >= limit:
            break
        items.append(
            {
                "detected_at": event["detected_at"],
                "source_ip": event["ip"],
                "target": None,
                "attack_type": "SSH Brute Force",
                "detection": "Malicious",
                "model": "Fail2Ban",
                "blocking_status": latest_action.get(event["ip"]) == "Ban",
                "jail": event["jail"],
            }
        )
    return items


def collect_blocked(client_path=DEFAULT_CLIENT, log_path=DEFAULT_LOG_PATH):
    """Return currently banned IPs across all jails."""
    status_output, error = run_client(client_path, ["status"])
    if error:
        raise RuntimeError(error)

    ban_times = read_ban_times(log_path)
    items = []
    for jail in list_jails(status_output):
        jail_output, jail_error = run_client(client_path, ["status", jail])
        if jail_error:
            continue
        for ip in parse_banned_ips(jail_output):
            ban_jail, blocked_at = ban_times.get(ip, (jail, None))
            items.append(
                {
                    "ip": ip,
                    "blocked_at": blocked_at,
                    "jail": ban_jail or jail,
                    "status": "blocked",
                    "source": "Fail2Ban",
                }
            )

    items.sort(key=lambda item: (item.get("blocked_at") or "", item["ip"]), reverse=True)
    return items


def read_json_file(path, default):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return default
    return payload


def collect_qos(qos_dir=DEFAULT_QOS_DIR):
    """Read the latest QoS probe and its in-memory history."""
    directory = Path(qos_dir)
    history = read_json_file(directory / "history.json", [])
    if not isinstance(history, list):
        history = []
    return {
        "generated_at": utc_now_iso(),
        "probe": read_json_file(directory / "last.json", None),
        "history": [item for item in history if isinstance(item, dict)],
    }


_BLOCKED_CACHE = {"at": 0.0, "items": None}
_BLOCKED_LOCK = threading.Lock()
_ATTACKS_CACHE = {"at": 0.0, "key": None, "items": None}
_ATTACKS_LOCK = threading.Lock()


def parse_limit(raw):
    if raw is None:
        return DEFAULT_ATTACKS_LIMIT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if not 1 <= value <= MAX_ATTACKS_LIMIT:
        return None
    return value


def cached_blocked(client_path=DEFAULT_CLIENT, log_path=DEFAULT_LOG_PATH):
    now = time.monotonic()
    with _BLOCKED_LOCK:
        if (
            _BLOCKED_CACHE["items"] is not None
            and (now - _BLOCKED_CACHE["at"]) < CACHE_SECONDS
        ):
            return list(_BLOCKED_CACHE["items"])
    items = collect_blocked(client_path, log_path)
    with _BLOCKED_LOCK:
        _BLOCKED_CACHE["at"] = time.monotonic()
        _BLOCKED_CACHE["items"] = list(items)
    return items


def cached_attacks(log_path=DEFAULT_LOG_PATH, limit=DEFAULT_ATTACKS_LIMIT):
    key = (str(log_path), limit)
    now = time.monotonic()
    with _ATTACKS_LOCK:
        if (
            _ATTACKS_CACHE["items"] is not None
            and _ATTACKS_CACHE["key"] == key
            and (now - _ATTACKS_CACHE["at"]) < CACHE_SECONDS
        ):
            return list(_ATTACKS_CACHE["items"])
    items = collect_attacks(log_path, limit)
    with _ATTACKS_LOCK:
        _ATTACKS_CACHE["at"] = time.monotonic()
        _ATTACKS_CACHE["key"] = key
        _ATTACKS_CACHE["items"] = list(items)
    return items


class Fail2BanRequestHandler(BaseHTTPRequestHandler):
    server_version = "Fail2BanReadOnlyAPI/1.1"
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

    def _unauthorized(self, realm):
        self._send_json(
            401,
            {"error": "unauthorized"},
            {"WWW-Authenticate": f'Bearer realm="{realm}"'},
        )

    def _health(self):
        _, error = run_client(self.server.client_path, ["status"])
        if error:
            self._send_json(
                503,
                {"ok": False, "error": "fail2ban_unavailable"},
            )
            return
        self._send_json(200, {"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._health()
            return
        if parsed.path == "/api/attacks":
            if not self._authorized():
                self._unauthorized("fail2ban-attacks-api")
                return
            limit = parse_limit(parse_qs(parsed.query).get("limit", [None])[0])
            if limit is None:
                self._send_json(400, {"error": "invalid_limit"})
                return
            try:
                items = cached_attacks(self.server.log_path, limit)
            except RuntimeError:
                self._send_json(
                    503,
                    {"error": "fail2ban_log_unavailable", "items": []},
                )
                return
            self._send_json(
                200,
                {
                    "generated_at": utc_now_iso(),
                    "source": "Fail2Ban",
                    "items": items,
                },
            )
            return
        if parsed.path == "/api/blocked":
            if not self._authorized():
                self._unauthorized("fail2ban-api")
                return
            try:
                items = cached_blocked(
                    self.server.client_path,
                    self.server.log_path,
                )
            except RuntimeError:
                self._send_json(
                    503,
                    {"error": "fail2ban_unavailable", "items": []},
                )
                return
            self._send_json(
                200,
                {
                    "generated_at": utc_now_iso(),
                    "source": "Fail2Ban",
                    "items": items,
                },
            )
            return
        if parsed.path == "/api/qos":
            if not self._authorized():
                self._unauthorized("fail2ban-qos-api")
                return
            self._send_json(200, collect_qos(self.server.qos_dir))
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})

    def do_PUT(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})

    def do_DELETE(self):
        self._send_json(405, {"error": "method_not_allowed"}, {"Allow": "GET"})


def build_server(
    host,
    port,
    token,
    client_path=DEFAULT_CLIENT,
    log_path=DEFAULT_LOG_PATH,
    qos_dir=DEFAULT_QOS_DIR,
):
    server = ThreadingHTTPServer((host, int(port)), Fail2BanRequestHandler)
    server.daemon_threads = True
    server.expected_token = token
    server.client_path = str(client_path)
    server.log_path = str(log_path)
    server.qos_dir = str(qos_dir)
    return server


def main():
    load_env_file(os.environ.get("FAIL2BAN_API_ENV_FILE", str(DEFAULT_ENV_PATH)))

    token = (os.environ.get("FAIL2BAN_API_TOKEN") or "").strip()
    if len(token) < 24:
        print(
            "FAIL2BAN_API_TOKEN belum diatur dengan benar (minimal 24 karakter).",
            file=sys.stderr,
        )
        return 2

    host = (os.environ.get("FAIL2BAN_API_BIND") or "0.0.0.0").strip()
    try:
        port = int(os.environ.get("FAIL2BAN_API_PORT") or "8080")
    except ValueError:
        print("FAIL2BAN_API_PORT harus berupa angka.", file=sys.stderr)
        return 2
    if not 1 <= port <= 65535:
        print("FAIL2BAN_API_PORT di luar rentang 1-65535.", file=sys.stderr)
        return 2

    client_path = (os.environ.get("FAIL2BAN_API_CLIENT") or DEFAULT_CLIENT).strip()
    log_path = os.environ.get("FAIL2BAN_API_LOG") or DEFAULT_LOG_PATH
    qos_dir = os.environ.get("FAIL2BAN_API_QOS_DIR") or DEFAULT_QOS_DIR

    try:
        server = build_server(
            host,
            port,
            token,
            client_path=client_path,
            log_path=log_path,
            qos_dir=qos_dir,
        )
    except OSError as exc:
        print(f"Gagal membuka {host}:{port}: {exc}", file=sys.stderr)
        return 1

    print(f"Fail2Ban read-only API listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
