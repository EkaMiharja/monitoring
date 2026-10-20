import threading
from collections import deque
from datetime import timedelta

import requests

from utils import iso, utc_now


class TelegramService:
    def __init__(self, config):
        self.demo = config.get("DATA_MODE", "demo") == "demo"
        self.token = config.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = config.get("TELEGRAM_CHAT_ID", "")
        self.api_base = config.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
        self.timeout = config.get("API_TIMEOUT_SECONDS", 4)
        self._history = deque(maxlen=60)
        self._lock = threading.Lock()
        self._next_id = 1
        if self.demo:
            self._seed_demo_history()

    def configured(self):
        return bool(self.token and self.chat_id)

    def _record(self, *, timestamp, event, source_ip, status, detail):
        with self._lock:
            record = {
                "id": self._next_id,
                "timestamp": timestamp,
                "event": event,
                "source_ip": source_ip,
                "status": status,
                "detail": detail,
                "mode": "demo" if self.demo else "live",
            }
            self._next_id += 1
            self._history.appendleft(record)
            return record

    def _seed_demo_history(self):
        now = utc_now()
        seeded = [
            (now - timedelta(minutes=37), "203.0.113.45", "delivered", "Alert diterima Telegram (DEMO)."),
            (now - timedelta(hours=2, minutes=12), "198.51.100.23", "failed", "Telegram timeout saat pengiriman (DEMO)."),
            (now - timedelta(hours=5, minutes=4), "192.0.2.77", "delivered", "Alert diterima Telegram (DEMO)."),
        ]
        for timestamp, source_ip, status, detail in reversed(seeded):
            self._record(
                timestamp=iso(timestamp),
                event="SSH Brute Force",
                source_ip=source_ip,
                status=status,
                detail=detail,
            )

    def history(self):
        with self._lock:
            return list(self._history)

    def _message_text(self, payload):
        lines = [
            "🚨 SSH Brute Force Detected",
            "",
            f"IP: {payload.get('source_ip', 'unknown')}",
            f"Attack: {payload.get('event', 'SSH Brute Force')}",
            f"Detection Time: {payload.get('timestamp', iso())}",
            f"Detection: {payload.get('detection', 'Malicious')}",
        ]
        blocking = payload.get("blocking_status")
        if blocking:
            lines.append(f"Blocking Status: {blocking}")
        return "\n".join(lines)

    def send_alert(self, payload):
        timestamp = payload.get("timestamp") or iso()
        source_ip = payload.get("source_ip")

        if self.demo:
            record = self._record(
                timestamp=timestamp,
                event=payload.get("event", "SSH Brute Force"),
                source_ip=source_ip,
                status="delivered",
                detail="Alert simulasi diterima Telegram (DEMO).",
            )
            return True, record

        if not self.configured():
            record = self._record(
                timestamp=timestamp,
                event=payload.get("event", "SSH Brute Force"),
                source_ip=source_ip,
                status="unavailable",
                detail="Token atau chat ID Telegram belum dikonfigurasi di backend.",
            )
            return False, record

        url = f"{self.api_base}/bot{self.token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": self._message_text(payload)},
                timeout=self.timeout,
            )
            body = {}
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.ok and body.get("ok"):
                record = self._record(
                    timestamp=timestamp,
                    event=payload.get("event", "SSH Brute Force"),
                    source_ip=source_ip,
                    status="delivered",
                    detail=f"Terkirim ke Telegram (message_id={body.get('result', {}).get('message_id', '-')}).",
                )
                return True, record
            description = str(body.get("description") or f"HTTP {response.status_code}")[:180]
            record = self._record(
                timestamp=timestamp,
                event=payload.get("event", "SSH Brute Force"),
                source_ip=source_ip,
                status="failed",
                detail=f"Telegram menolak pengiriman: {description}",
            )
            return False, record
        except requests.RequestException as exc:
            record = self._record(
                timestamp=timestamp,
                event=payload.get("event", "SSH Brute Force"),
                source_ip=source_ip,
                status="failed",
                detail=f"Gagal menghubungi Telegram: {exc.__class__.__name__}.",
            )
            return False, record

    def send_test_alert(self):
        payload = {
            "timestamp": iso(),
            "source_ip": "203.0.113.45",
            "event": "SSH Brute Force",
            "detection": "Malicious",
            "blocking_status": "Blocked by Fail2Ban (DEMO)" if self.demo else "Tidak tersedia",
        }
        return self.send_alert(payload)
