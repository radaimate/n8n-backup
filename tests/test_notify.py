"""Tesztek a notify.py modulhoz"""

import http.client
import urllib.error
import urllib.request

import pytest

from n8n_backup import notify


def test_send_telegram_no_token(monkeypatch):
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append(args[0])

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(notify, "TELEGRAM_TOKEN", "")

    notify.send_telegram("test")
    assert calls == []


# Az OSError és a HTTPException ágat is lefedjük: a BadStatusLine csak
# HTTPException, a többi OSError (a RemoteDisconnected mindkettő)
@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("nincs net"),
        TimeoutError(),
        ConnectionResetError(),
        http.client.RemoteDisconnected("bontott"),
        http.client.BadStatusLine("hibás válasz"),
    ],
)
def test_send_telegram_network_error(monkeypatch, caplog, error):
    def fake_urlopen(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(notify, "TELEGRAM_TOKEN", "rossz")
    monkeypatch.setattr(notify, "TELEGRAM_CHAT_ID", "rossz")

    notify.send_telegram("test")
    assert "sikertelen" in caplog.text
