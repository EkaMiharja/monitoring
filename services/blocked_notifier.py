"""Detect blocked-IP episode transitions while the dashboard is polling.

The notifier has no polling loop of its own. ``api.routes.overview`` feeds every
fresh ``blocked_ips`` section into ``observe``; a small sender thread only drains
the queue so Telegram latency never blocks the dashboard response.

One IP is treated as one attack episode: the first block is reported once, and
the final unblock is reported only after the IP has been absent from every
source for ``grace_seconds``. Repeated block/unblock cycles inside that window
are suppressed.
"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import timedelta

from utils import iso, utc_now

ACTIONS = ("blocked", "unblocked")


class BlockedIpNotifier:
    def __init__(
        self,
        telegram,
        *,
        enabled=False,
        logger=None,
        grace_seconds=60,
        lookback_seconds=0,
        counter=None,
    ):
        self.telegram = telegram
        self.enabled = bool(enabled)
        self.logger = logger or logging.getLogger(__name__)
        try:
            self.grace_seconds = max(0.0, float(grace_seconds))
        except (TypeError, ValueError):
            self.grace_seconds = 60.0
        try:
            self.lookback_seconds = max(0.0, float(lookback_seconds))
        except (TypeError, ValueError):
            self.lookback_seconds = 0.0
        self.counter = counter
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

    def _episode_item(self, item, first_seen, last_seen, block_events):
        enriched = dict(item)
        enriched["first_seen"] = iso(first_seen)
        enriched["last_seen"] = iso(last_seen)
        enriched["duration_seconds"] = max(
            0,
            int((last_seen - first_seen).total_seconds()),
        )
        enriched["block_events"] = block_events
        enriched["episode_since"] = iso(
            first_seen - timedelta(seconds=self.lookback_seconds)
        )
        return enriched

    def _attach_attack_count(self, item):
        if not self.counter:
            item["attack_count"] = None
            return
        since = item.get("episode_since") or item.get("first_seen")
        try:
            result = self.counter(item.get("ip"), since)
        except Exception:  # noqa: BLE001 - final alert must still be sent
            self.logger.exception("Gagal menghitung total serangan untuk %s", item.get("ip"))
            result = None
        if not isinstance(result, dict):
            item["attack_count"] = None
            return
        item["attack_count"] = result.get("count")
        item["attack_sources"] = result.get("sources") or {}
        item["count_warnings"] = result.get("warnings") or []

    def deliver(self, events):
        for event in events:
            if event.get("action") == "unblocked":
                self._attach_attack_count(event["item"])
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
        now = utc_now()

        with self._lock:
            if not self._seeded:
                self._state = {
                    ip: {
                        "item": dict(item),
                        "first_seen": now,
                        "last_seen": now,
                        "block_events": 1,
                        "notified": False,
                        "missing_since": None,
                    }
                    for ip, item in current.items()
                }
                self._seeded = True
                return []

            previous = self._state
            next_state = {}
            events = []

            for ip, item in current.items():
                entry = previous.get(ip)
                if entry is None:
                    next_state[ip] = {
                        "item": dict(item),
                        "first_seen": now,
                        "last_seen": now,
                        "block_events": 1,
                        "notified": True,
                        "missing_since": None,
                    }
                    events.append(
                        {
                            "action": "blocked",
                            "item": self._episode_item(item, now, now, 1),
                        }
                    )
                    continue

                block_events = entry.get("block_events", 1)
                if entry.get("missing_since") is not None:
                    block_events += 1
                next_state[ip] = {
                    "item": dict(item),
                    "first_seen": entry["first_seen"],
                    "last_seen": now,
                    "block_events": block_events,
                    "notified": entry.get("notified", True),
                    "missing_since": None,
                }

            for ip, entry in previous.items():
                if ip in current:
                    continue
                if partial or truncated:
                    next_state[ip] = entry
                    continue

                missing_since = entry.get("missing_since") or now
                if (now - missing_since).total_seconds() >= self.grace_seconds:
                    events.append(
                        {
                            "action": "unblocked",
                            "item": self._episode_item(
                                entry["item"],
                                entry["first_seen"],
                                entry["last_seen"],
                                entry.get("block_events", 1),
                            ),
                        }
                    )
                    continue

                pending = dict(entry)
                pending["missing_since"] = missing_since
                next_state[ip] = pending

            self._state = next_state
            return events