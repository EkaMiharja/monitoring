from datetime import datetime, timedelta, timezone

from services.blocked_notifier import BlockedIpNotifier
from services.providers.live import LiveProvider


def _item(ip, source="LightGBM", **extra):
    item = {
        "ip": ip,
        "source": source,
        "jail": "sshd",
        "blocked_at": "2026-10-23T07:33:31Z",
        "unblock_at": None,
    }
    item.update(extra)
    return item


def _section(items, status="ok", warnings=None, truncated=False):
    return {
        "status": status,
        "items": items,
        "warnings": warnings or [],
        "truncated": truncated,
    }


def _actions(events):
    return [(event["action"], event["item"]["ip"]) for event in events]


def test_first_snapshot_is_baseline_and_new_ip_is_reported():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)

    assert notifier.observe(_section([_item("192.0.2.10")]), send=False) == []

    events = notifier.observe(
        _section([_item("192.0.2.10"), _item("192.0.2.11", source="Fail2Ban")]),
        send=False,
    )

    assert _actions(events) == [("blocked", "192.0.2.11")]
    assert events[0]["item"]["source"] == "Fail2Ban"


def test_unblock_is_reported_when_ip_leaves_all_sources():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)
    source = "LightGBM + Random Forest + Fail2Ban"
    notifier.observe(_section([_item("192.0.2.10", source=source)]), send=False)

    events = notifier.observe(_section([]), send=False)

    assert _actions(events) == [("unblocked", "192.0.2.10")]
    assert events[0]["item"]["source"] == source


def test_source_change_does_not_report_unblock():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)
    notifier.observe(_section([_item("192.0.2.10", source="LightGBM")]), send=False)

    assert (
        notifier.observe(
            _section([_item("192.0.2.10", source="LightGBM + Fail2Ban")]),
            send=False,
        )
        == []
    )

    events = notifier.observe(_section([]), send=False)
    assert _actions(events) == [("unblocked", "192.0.2.10")]
    assert events[0]["item"]["source"] == "LightGBM + Fail2Ban"


def test_failed_or_unavailable_snapshot_does_not_reset_state():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)
    notifier.observe(_section([_item("192.0.2.10")]), send=False)

    assert notifier.observe(_section([], status="error"), send=False) == []
    assert notifier.observe(_section([], status="unavailable"), send=False) == []
    assert notifier.observe(_section([_item("192.0.2.10")]), send=False) == []

    events = notifier.observe(_section([]), send=False)
    assert _actions(events) == [("unblocked", "192.0.2.10")]


def test_partial_source_warning_holds_unblock_but_allows_new_block():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)
    notifier.observe(
        _section([_item("192.0.2.10"), _item("192.0.2.11")]),
        send=False,
    )

    events = notifier.observe(
        _section(
            [_item("192.0.2.10"), _item("192.0.2.12")],
            warnings=[{"url": "http://source.test/api/blocked", "message": "timeout"}],
        ),
        send=False,
    )
    assert _actions(events) == [("blocked", "192.0.2.12")]

    assert (
        notifier.observe(
            _section([_item("192.0.2.10"), _item("192.0.2.11"), _item("192.0.2.12")]),
            send=False,
        )
        == []
    )

    events = notifier.observe(_section([]), send=False)
    assert set(_actions(events)) == {
        ("unblocked", "192.0.2.10"),
        ("unblocked", "192.0.2.11"),
        ("unblocked", "192.0.2.12"),
    }


def test_truncated_snapshot_holds_unblock_until_a_complete_payload():
    notifier = BlockedIpNotifier(object(), enabled=True, grace_seconds=0)
    notifier.observe(
        _section([_item("192.0.2.10"), _item("192.0.2.11")]),
        send=False,
    )

    assert (
        notifier.observe(
            _section([_item("192.0.2.10")], truncated=True),
            send=False,
        )
        == []
    )

    events = notifier.observe(_section([]), send=False)
    assert set(_actions(events)) == {
        ("unblocked", "192.0.2.10"),
        ("unblocked", "192.0.2.11"),
    }


def test_deliver_groups_events_by_action():
    calls = []

    class FakeTelegram:
        def send_blocked_batch(self, action, items):
            calls.append((action, [item["ip"] for item in items]))
            return True, []

    notifier = BlockedIpNotifier(FakeTelegram(), enabled=True, grace_seconds=0)
    notifier.deliver(
        [
            {"action": "blocked", "item": _item("192.0.2.10")},
            {"action": "unblocked", "item": _item("192.0.2.11")},
            {"action": "blocked", "item": _item("192.0.2.12")},
        ]
    )

    assert calls == [
        ("blocked", ["192.0.2.10", "192.0.2.12"]),
        ("unblocked", ["192.0.2.11"]),
    ]


def test_worker_delivers_transitions_through_the_queue():
    calls = []

    class FakeTelegram:
        def send_blocked_batch(self, action, items):
            calls.append((action, [item["ip"] for item in items]))

    notifier = BlockedIpNotifier(FakeTelegram(), enabled=True, grace_seconds=0)
    notifier.observe(_section([_item("192.0.2.10")]))
    notifier.observe(
        _section([_item("192.0.2.10"), _item("192.0.2.11")]),
    )
    notifier.observe(_section([_item("192.0.2.11")]))
    notifier.stop()

    assert calls == [
        ("blocked", ["192.0.2.11"]),
        ("unblocked", ["192.0.2.10"]),
    ]


def test_disabled_notifier_ignores_snapshots():
    notifier = BlockedIpNotifier(object(), enabled=False)

    assert notifier.observe(_section([_item("192.0.2.10")])) == []
    assert notifier.start() is False


def test_reblock_within_grace_is_suppressed_and_final_has_summary(monkeypatch):
    from services import blocked_notifier as module

    times = [datetime(2026, 11, 4, 3, 0, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(module, "utc_now", lambda: times[0])
    calls = []
    counted = []

    class FakeTelegram:
        def send_blocked_batch(self, action, items):
            calls.append((action, items))

    def counter(ip, since):
        counted.append((ip, since))
        return {
            "count": 46,
            "sources": {"LightGBM": 24, "Random Forest": 22},
            "warnings": [],
        }

    notifier = BlockedIpNotifier(
        FakeTelegram(),
        enabled=True,
        grace_seconds=60,
        counter=counter,
    )
    notifier.observe(_section([]), send=False)

    first = notifier.observe(_section([_item("192.0.2.10")]), send=False)
    assert _actions(first) == [("blocked", "192.0.2.10")]
    assert first[0]["item"]["first_seen"] == "2026-11-04T03:00:00Z"

    times[0] += timedelta(seconds=5)
    assert notifier.observe(_section([]), send=False) == []

    times[0] += timedelta(seconds=5)
    assert notifier.observe(_section([_item("192.0.2.10")]), send=False) == []

    times[0] += timedelta(seconds=30)
    assert notifier.observe(_section([]), send=False) == []

    times[0] += timedelta(seconds=61)
    events = notifier.observe(_section([]), send=False)
    assert _actions(events) == [("unblocked", "192.0.2.10")]
    item = events[0]["item"]
    assert item["block_events"] == 2
    assert item["first_seen"] == "2026-11-04T03:00:00Z"
    assert item["last_seen"] == "2026-11-04T03:00:10Z"

    notifier.deliver(events)

    assert counted == [("192.0.2.10", "2026-11-04T03:00:00Z")]
    assert item["attack_count"] == 46
    assert item["attack_sources"] == {"LightGBM": 24, "Random Forest": 22}
    assert calls == [("unblocked", [item])]

    new_episode = notifier.observe(_section([_item("192.0.2.10")]), send=False)
    assert _actions(new_episode) == [("blocked", "192.0.2.10")]


def test_blocked_provider_reports_total_and_truncation(monkeypatch):
    provider = LiveProvider(
        {"LIGHTGBM_BLOCKED_API_URL": "http://lightgbm.test/api/blocked"},
        None,
    )
    items = [
        {
            "ip": f"192.0.2.{index}",
            "blocked_at": f"2026-10-23T07:{index:02d}:00Z",
            "status": "blocked",
        }
        for index in range(1, 56)
    ]
    monkeypatch.setattr(
        provider,
        "_get_json",
        lambda url, token: ({"items": items}, None),
    )

    section = provider._load_blocked()

    assert section["status"] == "ok"
    assert section["total"] == 55
    assert len(section["items"]) == 50
    assert section["truncated"] is True
