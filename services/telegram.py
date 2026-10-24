import threading
from collections import deque
from datetime import timedelta

import requests

from utils import iso, utc_now

BLOCKED_BATCH_LIMIT = 10
BLOCKED_TEXT_LIMIT = 3500


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

    def _deliver_text(self, text):
        if self.demo:
            return "delivered", "Alert simulasi diterima Telegram (DEMO)."

        if not self.configured():
            return "unavailable", "Token atau chat ID Telegram belum dikonfigurasi di backend."

        url = f"{self.api_base}/bot{self.token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=self.timeout,
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.ok and body.get("ok"):
                result = body.get("result")
                if not isinstance(result, dict):
                    result = {}
                return (
                    "delivered",
                    f"Terkirim ke Telegram (message_id={result.get('message_id', '-')}).",
                )
            description = str(body.get("description") or f"HTTP {response.status_code}")[:180]
            return "failed", f"Telegram menolak pengiriman: {description}"
        except requests.RequestException as exc:
            return "failed", f"Gagal menghubungi Telegram: {exc.__class__.__name__}."

    def send_alert(self, payload):
        timestamp = payload.get("timestamp") or iso()
        source_ip = payload.get("source_ip")
        event = payload.get("event", "SSH Brute Force")
        status, detail = self._deliver_text(self._message_text(payload))
        record = self._record(
            timestamp=timestamp,
            event=event,
            source_ip=source_ip,
            status=status,
            detail=detail,
        )
        return status == "delivered", record

    @staticmethod
    def _blocked_model(item):
        return str(item.get("source") or item.get("model") or "Tidak diketahui").strip()

    def _blocked_text(self, action, items):
        unblocked = action == "unblocked"
        multi = len(items) > 1
        lines = ["IP TERUNBLOCK" if unblocked else "IP TERBLOKIR"]
        if multi:
            lines.append(f"Total: {len(items)} IP")

        for index, item in enumerate(items, 1):
            ip = item.get("ip") or "unknown"
            jail = str(item.get("jail") or "-").strip() or "-"
            lines.append("")
            if multi:
                lines.append(f"{index}. {ip}")
                indent = "   "
            else:
                lines.append(f"IP: {ip}")
                indent = ""

            lines.append(f"{indent}Model: {self._blocked_model(item)}")
            lines.append(f"{indent}Jail: {jail}")
            lines.append(f"{indent}Waktu blokir: {item.get('blocked_at') or '-'}")
            if unblocked:
                lines.append(f"{indent}Status: tidak diblokir oleh model mana pun")
            else:
                lines.append(f"{indent}Auto unblock: {item.get('unblock_at') or 'Manual'}")

        return "\n".join(lines)

    def _blocked_chunks(self, action, items):
        chunks = []
        current = []
        for item in items:
            candidate = current + [item]
            too_many = len(candidate) > BLOCKED_BATCH_LIMIT
            too_long = bool(current) and len(self._blocked_text(action, candidate)) > BLOCKED_TEXT_LIMIT
            if current and (too_many or too_long):
                chunks.append(current)
                current = [item]
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def send_blocked_batch(self, action, items):
        normalized = "unblocked" if str(action).strip().lower() == "unblocked" else "blocked"
        records = []
        if not items:
            return True, records

        all_ok = True
        event = "IP Terunblock" if normalized == "unblocked" else "IP Terblokir"
        for chunk in self._blocked_chunks(normalized, items):
            status, delivery_detail = self._deliver_text(self._blocked_text(normalized, chunk))
            all_ok = all_ok and status == "delivered"
            for item in chunk:
                detail = f"Model: {self._blocked_model(item)}"
                jail = str(item.get("jail") or "").strip()
                if jail:
                    detail += f" · Jail: {jail}"
                detail += f". {delivery_detail}"
                records.append(
                    self._record(
                        timestamp=iso(),
                        event=event,
                        source_ip=item.get("ip"),
                        status=status,
                        detail=detail,
                    )
                )
        return all_ok, records

    def send_test_alert(self):
        payload = {
            "timestamp": iso(),
            "source_ip": "203.0.113.45",
            "event": "SSH Brute Force",
            "detection": "Malicious",
            "blocking_status": "Blocked by Fail2Ban (DEMO)" if self.demo else "Tidak tersedia",
        }
        return self.send_alert(payload)
