"""Detect blocked-IP transitions while the dashboard is polling.

The notifier has no polling loop of its own. ``api.routes.overview`` feeds every
fresh ``blocked_ips`` section into ``observe``; a small sender thread only drains
the queue so Telegram latency never blocks the dashboard response.
"""

from __future__ import annotations

import logging
import queue
import threading

ACTIONS = ("blocked", "unblocked")


class BlockedIpNotifier:
    def __init__(self, telegram, *, enabled=False, logger=None):
        self.telegram = telegram
        self.enabled = bool(enabled)
        self.logger = logger or logging.getLogger(__name__)
        self._state = {}
        self._seeded = False
        self._lock = threading.Lock()
        self._thread_lock = threading.Lock()
        self._queue = queue.Queue()
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        with self._thread_lock:
            if not self.enabled or self._thread is not None:
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="blocked-ip-notifier",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self):
        with self._thread_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop.set()
            self._queue.put(None)
            self._thread = None
        thread.join(timeout=2)

    def _loop(self):
        while True:
            events = self._queue.get()
            try:
                if events is None:
                    return
                self.deliver(events)
            except Exception:  # noqa: BLE001 - sender must survive Telegram errors
                self.logger.exception("Gagal mengirim notifikasi IP terblokir ke Telegram")
            finally:
                self._queue.task_done()

    def observe(self, section, *, send=True):
        if not self.enabled:
            return []
        try:
            snapshot = self._snapshot(section)
            if snapshot is None:
                return []
            events = self._transitions(snapshot)
        except Exception:  # noqa: BLE001 - polling must not break on notifier errors
            self.logger.exception("Gagal memproses transisi blocked IP")
            return []
        if events and send:
            self.start()
            self._queue.put(events)
        return events

    def deliver(self, events):
        grouped = {action: [] for action in ACTIONS}
        for event in events:
            action = event.get("action")
            if action in grouped:
                grouped[action].append(event["item"])
        for action in ACTIONS:
            if grouped[action]:
                self.telegram.send_blocked_batch(action, grouped[action])

    @staticmethod
    def _snapshot(section):
        section = section or {}
        status = str(section.get("status") or "").strip().lower()
        if status not in {"ok", "empty"}:
            return None

        raw_items = section.get("items")
        if not isinstance(raw_items, list):
            return None

        items = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            ip = str(raw.get("ip") or "").strip()
            if not ip:
                continue
            items[ip] = dict(raw)

        return {
            "items": items,
            "partial": bool(section.get("warnings")),
            "truncated": bool(section.get("truncated")),
        }

    def _transitions(self, snapshot):
        current = snapshot["items"]
        partial = snapshot["partial"]
        truncated = snapshot["truncated"]

        with self._lock:
            if not self._seeded:
                self._state = dict(current)
                self._seeded = True
                return []

            previous = dict(self._state)
            events = [
                {"action": "blocked", "item": item}
                for ip, item in current.items()
                if ip not in previous
            ]

            if not partial and not truncated:
                events.extend(
                    {"action": "unblocked", "item": item}
                    for ip, item in previous.items()
                    if ip not in current
                )

            if partial or truncated:
                merged = dict(previous)
                for ip, item in current.items():
                    if partial and ip in merged:
                        continue
                    merged[ip] = item
                self._state = merged
            else:
                self._state = dict(current)

            return events
