# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# -*- coding: utf-8 -*-

"""
Bacheca Nuvola
~~~~~~~~~~~~~~

Scraper for the bulletin board of "Nuvola" online register.

:copyright: (c) 2021 Paolo Paolo Bernardi.
:license: GNU AGPL version 3, see LICENSE for more details.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import dateutil
import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.join(os.path.dirname(__file__)))
from shared import date_ita_text_to_iso, download_soup  # noqa

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import settings
import telegram

SOURCE = "Bacheca Nuvola"

PUBLISHER = "DD Mazzini"
PUB_TYPE = "News"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0"
)


class Nuvola:
    def __init__(self, username: str, password: str, now: datetime):
        """
        Create a new instance of the Nuvola scraper.
        :param username: Nuvola user name
        :param password: Nuvola password
        :return: a list of dictionaries of publications and events
        """
        self.now = now
        self.session = requests.session()
        res = self.session.get("https://nuvola.madisoft.it/")
        csrf_token = (
            BeautifulSoup(res.text, "html.parser")
            .find_all("input")[0]
            .attrs["value"]
        )
        res.raise_for_status()
        res = self.session.post(
            "https://nuvola.madisoft.it/login_check",
            headers={
                "User-Agent": USER_AGENT,
            },
            data={
                "_username": username,
                "_password": password,
                "_csrf_token": csrf_token,
            },
            allow_redirects=False,
        )
        res.raise_for_status()
        res = self.session.get(
            "https://nuvola.madisoft.it/api-studente/v1/login-from-web",
            headers={
                "User-Agent": USER_AGENT,
            },
            allow_redirects=False,
        )
        res.raise_for_status()
        res_json = res.json()
        self.bearer_token = res_json["token"]
        credentials_expiration = dateutil.parser.parse(
            res_json["dataScadenzaCredenziali"]
        )
        if credentials_expiration <= self.now:
            telegram.send_telegram("Your NUVOLA credentials have *expired*!")
        res = self.session.get(
            "https://nuvola.madisoft.it/api-studente/v1/alunni",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": USER_AGENT,
            },
        )
        res.raise_for_status()
        students = res.json()
        self.id_student = students["valori"][0]["id"]

    def logout(self):
        """
        Logout from the Nuvola register.
        """
        self.session.get("https://nuvola.madisoft.it/logout")

    def get_id_student(self):
        res = self.session.get(
            "https://nuvola.madisoft.it/api-studente/v1/alunni",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": USER_AGENT,
            },
        )
        res.raise_for_status()
        students = res.json()
        for s in students:
            return s["id"]

    def get_bulletin_board(self) -> List[Dict[str, str]]:
        """
        Returns all bulletin board items.
        :return: a list of dictionaries of publications
        """
        id_board = "6"
        res = self.session.get(
            f"https://nuvola.madisoft.it/api-studente/v1/bacheche-digitali/{id_board}/documenti?contextAlunno={self.id_student}&fields=id%2CadesioneRichiesta%2CdataScadenzaAdesione%2Cmetadata%7BisRead%7D%2Coggetto%2CnomeVoceTitolario%2CdataPubblicazione%2CdataArchiviazione%2Cnote%2CnumeroRegistro%2CdataNumeroRegistro&metadata=count&limit=25&orderBy%5Bid%5D=desc&enumSerializationMethod=object",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": USER_AGENT,
            },
        )
        res.raise_for_status()
        bulletin_raw = res.json()
        bulletin = [
            {
                "url": f"https://nuvola.madisoft.it/area-tutore/bacheche/{id_board}/documenti/{b['id']}",
                "subject": b["oggetto"],
                "source": SOURCE,
                "publisher": SOURCE,
                "pub_type": PUB_TYPE,
                "date_start": b["dataPubblicazione"].split("T")[0],
                "number": b["id"],
                "attachments": [],
            }
            for b in bulletin_raw["data"]
        ]
        return bulletin

    def get_events(self) -> List[Dict[str, str]]:
        """
        Returns all events.
        :return: a list of dictionaries of events
        """
        res = self.session.get(
            f"https://nuvola.madisoft.it/api-studente/v1/alunno/{self.id_student}/eventi-classe?contextAlunno={self.id_student}&filter%5Bordinamento%5D=data_inizio_desc&page=1&limit=25",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": USER_AGENT,
            },
        )
        res.raise_for_status()
        events_raw = res.json()
        events = []

        for b in events_raw["valori"]:
            e = {
                "url": "https://nuvola.madisoft.it/",
                "subject": f"{b['nome'].upper()} - {b['descrizione']} ",
                "source": SOURCE,
                "publisher": SOURCE,
                "pub_type": PUB_TYPE,
                "date_start": b["dataInizio"].split("T")[0],
                "number": b["id"],
                "attachments": [],
            }
            # Warn about meetings within an hour from their publication
            if "colloqui" in e["subject"].lower():
                event_date = dateutil.parser.parse(b["dataInizio"])
                delta = self.now - event_date
                if delta.total_seconds() < 60 * 60:
                    telegram.send_telegram(f"*ALERT NUVOLA*\n\n{e['subject']}")
            events.append(e)
        return events


def scrape() -> List[Dict[str, str]]:
    """
    Scrape the register.
    :return: a list of dictionaries of publications and events
    """
    now = datetime.now().replace(tzinfo=ZoneInfo("Europe/Rome"))
    # Between 7 and 8 AM check every 5 minutes, otherwise every 10
    if now.hour == 7 or now.minute % 10 < 3:
        nuvola = Nuvola(settings.NUVOLA_USER, settings.NUVOLA_PASSWORD, now)
        bulletin = nuvola.get_bulletin_board()
        events = nuvola.get_events()
        nuvola.logout()
        return events + bulletin
    else:
        return []


if __name__ == "__main__":
    print(json.dumps(scrape(), indent=2))
