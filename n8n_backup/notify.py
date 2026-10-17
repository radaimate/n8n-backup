"""Értesítés küldése Telegramon a Bot API-n keresztül."""

import http.client
import logging
import urllib.parse
import urllib.request

from n8n_backup.config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

# -------------Telegram-értesítés küldése-------------


def send_telegram(text: str) -> None:
    if not TELEGRAM_CHAT_ID or not TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        message_parameters = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        # dict -> string: urllib.parse.urlencode(message_parameters)
        # string -> bájtok: az .encode() által ez lesz az üzenet törzse
        body = urllib.parse.urlencode(message_parameters).encode()
        # még nem küldi el, csak elkészíti, mint egy megcímzett, lezárt borítékot
        request = urllib.request.Request(url, data=body)

        with urllib.request.urlopen(request, timeout=10):
            pass
    except (OSError, http.client.HTTPException) as e:
        logger.warning("Telegram-üzenet küldése sikertelen: %s", e)
