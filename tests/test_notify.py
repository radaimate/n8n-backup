"""Tesztek a notify.py modulhoz"""

import urllib.error
import urllib.request

from n8n_backup import notify


def test_send_telegram_no_token(monkeypatch):
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append(args[0])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(notify, "TELEGRAM_TOKEN", "")

    notify.send_telegram("test")
    assert calls == []


def test_send_telegram_network_error(monkeypatch, caplog):
    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("nincs net")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(notify, "TELEGRAM_TOKEN", "rossz")
    monkeypatch.setattr(notify, "TELEGRAM_CHAT_ID", "rossz")

    notify.send_telegram("test")
    assert "sikertelen" in caplog.text
