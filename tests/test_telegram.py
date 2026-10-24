from services.telegram import TelegramService


def _item(ip, source="LightGBM + Random Forest", **extra):
    item = {
        "ip": ip,
        "source": source,
        "jail": "sshd",
        "blocked_at": "2026-10-23T07:33:31Z",
        "unblock_at": None,
    }
    item.update(extra)
    return item


class FakeResponse:
    def __init__(self, ok=True, status_code=200, body=None):
        self.ok = ok
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def _service():
    return TelegramService(
        {
            "DATA_MODE": "live",
            "TELEGRAM_BOT_TOKEN": "bot-token",
            "TELEGRAM_CHAT_ID": "chat-id",
            "TELEGRAM_API_BASE": "https://telegram.test",
            "API_TIMEOUT_SECONDS": 3,
        }
    )


def test_blocked_batch_sends_model_and_splits_large_payload(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeResponse(
            body={"ok": True, "result": {"message_id": len(calls)}},
        )

    monkeypatch.setattr("services.telegram.requests.post", fake_post)
    service = _service()
    items = [_item(f"192.0.2.{index}") for index in range(1, 13)]

    ok, records = service.send_blocked_batch("blocked", items)

    assert ok is True
    assert len(calls) == 2
    assert calls[0][0] == "https://telegram.test/botbot-token/sendMessage"
    assert calls[0][1]["chat_id"] == "chat-id"
    assert calls[0][2] == 3

    first_text = calls[0][1]["text"]
    second_text = calls[1][1]["text"]
    assert first_text.startswith("IP TERBLOKIR")
    assert "Model: LightGBM + Random Forest" in first_text
    assert "Auto unblock: Manual" in first_text
    assert "Total: 2 IP" in second_text
    assert "2. 192.0.2.12" in second_text

    assert len(records) == 12
    assert records[0]["event"] == "IP Terblokir"
    assert records[0]["source_ip"] == "192.0.2.1"
    assert records[0]["status"] == "delivered"
    assert "Model: LightGBM + Random Forest" in records[0]["detail"]
    assert "message_id=1" in records[0]["detail"]


def test_unblocked_batch_keeps_last_blocking_model(monkeypatch):
    texts = []

    def fake_post(url, json, timeout):
        texts.append(json["text"])
        return FakeResponse(body={"ok": True, "result": {"message_id": 9}})

    monkeypatch.setattr("services.telegram.requests.post", fake_post)
    service = _service()

    ok, records = service.send_blocked_batch(
        "unblocked",
        [_item("192.0.2.50", source="Fail2Ban")],
    )

    assert ok is True
    assert texts[0].startswith("IP TERUNBLOCK")
    assert "Model: Fail2Ban" in texts[0]
    assert "Status: tidak diblokir oleh model mana pun" in texts[0]
    assert records[0]["event"] == "IP Terunblock"
    assert "Model: Fail2Ban" in records[0]["detail"]


def test_telegram_rejection_marks_batch_failed(monkeypatch):
    def fake_post(url, json, timeout):
        return FakeResponse(
            ok=False,
            status_code=400,
            body={"ok": False, "description": "Bad Request: chat not found"},
        )

    monkeypatch.setattr("services.telegram.requests.post", fake_post)
    service = _service()

    ok, records = service.send_blocked_batch("blocked", [_item("192.0.2.60")])

    assert ok is False
    assert records[0]["status"] == "failed"
    assert "chat not found" in records[0]["detail"]


def test_unconfigured_telegram_records_unavailable():
    service = TelegramService({"DATA_MODE": "live"})

    ok, records = service.send_blocked_batch("blocked", [_item("192.0.2.70")])

    assert ok is False
    assert records[0]["status"] == "unavailable"
    assert "belum dikonfigurasi" in records[0]["detail"]
