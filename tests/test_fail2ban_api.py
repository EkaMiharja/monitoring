import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fail2ban_api", ROOT / "deploy" / "fail2ban_api.py"
)
fail2ban_api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fail2ban_api)


def test_list_jails():
    output = """Status
|- Number of jail:\t2
`- Jail list:\tsshd, recidive
"""
    assert fail2ban_api.list_jails(output) == ["sshd", "recidive"]


def test_parse_banned_ips_empty_and_filled():
    empty = """Status for the jail: sshd
`- Actions
   |- Currently banned:\t0
   `- Banned IP list:\t
"""
    filled = """Status for the jail: sshd
`- Actions
   |- Currently banned:\t2
   `- Banned IP list:\t192.0.2.10 192.0.2.11
"""
    assert fail2ban_api.parse_banned_ips(empty) == []
    assert fail2ban_api.parse_banned_ips(filled) == ["192.0.2.10", "192.0.2.11"]


def test_read_ban_times_uses_latest_ban(tmp_path):
    log = tmp_path / "fail2ban.log"
    log.write_text(
        "2026-10-23 04:24:23,082 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n"
        "2026-10-23 04:27:47,359 fail2ban.actions [17084]: NOTICE  [sshd] Unban 192.0.2.10\n"
        "2026-10-23 07:33:31,043 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n"
        "2026-10-23 07:34:31,043 fail2ban.actions [17084]: NOTICE  [recidive] Ban 192.0.2.11\n",
        encoding="utf-8",
    )

    assert fail2ban_api.read_ban_times(log) == {
        "192.0.2.10": ("sshd", "2026-10-23T07:33:31Z"),
        "192.0.2.11": ("recidive", "2026-10-23T07:34:31Z"),
    }


def test_read_log_events_parses_bans_and_unbans(tmp_path):
    log = tmp_path / "fail2ban.log"
    log.write_text(
        "2026-10-23 04:24:23,082 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n"
        "2026-10-23 04:24:33,082 fail2ban.actions [17084]: NOTICE  [sshd] Unban 192.0.2.10\n"
        "bukan baris fail2ban\n",
        encoding="utf-8",
    )

    assert fail2ban_api.read_log_events(log) == [
        {
            "detected_at": "2026-10-23T04:24:23Z",
            "jail": "sshd",
            "ip": "192.0.2.10",
            "action": "Ban",
        },
        {
            "detected_at": "2026-10-23T04:24:33Z",
            "jail": "sshd",
            "ip": "192.0.2.10",
            "action": "Unban",
        },
    ]


def test_collect_attacks_marks_latest_status_and_honors_limit(tmp_path):
    log = tmp_path / "fail2ban.log"
    log.write_text(
        "2026-10-23 04:24:23,082 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n"
        "2026-10-23 04:24:33,082 fail2ban.actions [17084]: NOTICE  [sshd] Unban 192.0.2.10\n"
        "2026-10-23 05:00:00,000 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.11\n"
        "2026-10-23 06:00:00,000 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n"
        "2026-10-23 06:01:00,000 fail2ban.actions [17084]: NOTICE  [recidive] Ban 192.0.2.12\n"
        "2026-10-23 06:02:00,000 fail2ban.actions [17084]: NOTICE  [recidive] Unban 192.0.2.12\n",
        encoding="utf-8",
    )

    items = fail2ban_api.collect_attacks(log, limit=3)

    assert [item["source_ip"] for item in items] == [
        "192.0.2.12",
        "192.0.2.10",
        "192.0.2.11",
    ]
    assert items[0]["model"] == "Fail2Ban"
    assert items[0]["blocking_status"] is False
    assert items[1]["blocking_status"] is True
    assert items[2]["jail"] == "sshd"


def test_collect_attacks_reports_unreadable_log(tmp_path):
    with pytest.raises(RuntimeError):
        fail2ban_api.collect_attacks(tmp_path / "missing.log")


def test_parse_limit():
    assert fail2ban_api.parse_limit(None) == 50
    assert fail2ban_api.parse_limit("1") == 1
    assert fail2ban_api.parse_limit("200") == 200
    assert fail2ban_api.parse_limit("0") is None
    assert fail2ban_api.parse_limit("201") is None
    assert fail2ban_api.parse_limit("abc") is None


def test_collect_blocked_uses_jail_and_log(monkeypatch, tmp_path):
    responses = {
        ("status",): "Status\n`- Jail list:\tsshd\n",
        ("status", "sshd"): (
            "Status for the jail: sshd\n"
            "`- Actions\n"
            "   `- Banned IP list:\t192.0.2.10\n"
        ),
    }

    def fake_run(_client, arguments, timeout=5):
        return responses.get(tuple(arguments)), None

    log = tmp_path / "fail2ban.log"
    log.write_text(
        "2026-10-23 07:33:31,043 fail2ban.actions [17084]: NOTICE  [sshd] Ban 192.0.2.10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fail2ban_api, "run_client", fake_run)

    assert fail2ban_api.collect_blocked("/usr/bin/fail2ban-client", log) == [
        {
            "ip": "192.0.2.10",
            "blocked_at": "2026-10-23T07:33:31Z",
            "jail": "sshd",
            "status": "blocked",
            "source": "Fail2Ban",
        }
    ]


def test_is_authorized():
    assert fail2ban_api.is_authorized("Bearer secret-token", "secret-token")
    assert not fail2ban_api.is_authorized("Bearer wrong", "secret-token")
    assert not fail2ban_api.is_authorized("Basic secret-token", "secret-token")
    assert not fail2ban_api.is_authorized("", "secret-token")


def test_collect_qos_reads_probe_and_history(tmp_path):
    (tmp_path / "last.json").write_text('{"delay_ms": 1.2}', encoding="utf-8")
    (tmp_path / "history.json").write_text(
        '[{"t": "2026-10-23T07:00:00Z", "delay_ms": 1.2}, "bad"]',
        encoding="utf-8",
    )

    payload = fail2ban_api.collect_qos(tmp_path)

    assert payload["probe"] == {"delay_ms": 1.2}
    assert payload["history"] == [{"t": "2026-10-23T07:00:00Z", "delay_ms": 1.2}]
