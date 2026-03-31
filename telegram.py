# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# -*- coding: utf-8 -*-

"""
Telegram
~~~~~~~~

Interface for the PBOTS Telegram bot.

:copyright: (c) 2021 Paolo Paolo Bernardi.
:license: GNU AGPL version 3, see LICENSE for more details.
"""

import requests

from settings import TELEGRAM_BOT_TOKEN, TELEGRAM_USER


def send_telegram(message: str):
    """
    Send a Telegram message to the default recipient.
    :param message: The message to be sent
    """
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": TELEGRAM_USER,
            "text": message,
            "parse_mode": "Markdown",
        },
    )
