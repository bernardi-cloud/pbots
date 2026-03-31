# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# -*- coding: utf-8 -*-

"""
main
~~~~

PBOTS main program.

:copyright: (c) 2020 Paolo Paolo Bernardi.
:license: GNU AGPL version 3, see LICENSE for more details.
"""

import json
import logging
import logging.handlers as handlers
import os
import shlex
import smtplib
import sqlite3
import ssl  # noqa
import subprocess
import sys
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List

import jinja2

# Check whether the settings are in place
try:
    import settings
except ModuleNotFoundError:
    print(
        "Please create a settings.py configuration file prior to running PBOTS."
    )
    print("You may use settings.py-sample as reference.")
    sys.exit(1)


SOURCES = [
    {
        "id": 1,
        "name": "Albo Pretorio del Comune di Acquasparta",
        "varname": "albo_pretorio_acquasparta",
        "scraper": "python scraper/albopretorio-comune-acquasparta.py",
    },
    {
        "id": 2,
        "name": "Albo Pretorio del Comune di Montecastrilli",
        "varname": "albo_pretorio_montecastrilli",
        "scraper": "python scraper/albopretorio-comune-montecastrilli.py",
    },
    {
        "id": 3,
        "name": "Bollettino della Regione Umbria, serie generale",
        "varname": "bollettino_umbria_generale",
        "scraper": f"{settings.PHANTOMJS} scraper/bollettino-regione-umbria.js 1",
    },
    {
        "id": 4,
        "name": "Bollettino della Regione Umbria, serie avvisi e concorsi",
        "varname": "bollettino_umbria_concorsi",
        "scraper": f"{settings.PHANTOMJS} scraper/bollettino-regione-umbria.js 2",
    },
    {
        "id": 5,
        "name": "Bollettino della Regione Umbria, serie informazioni e comunicazione",
        "varname": "bollettino_umbria_comunicazione",
        "scraper": f"{settings.PHANTOMJS} scraper/bollettino-regione-umbria.js 3",
    },
    {
        "id": 6,
        "name": "Albo Pretorio dell''I. C. \"A. De Filis\", Terni",
        "varname": "albo_pretorio_de_filis",
        "scraper": f"{settings.CASPERJS} scraper/albopretorio-ic-defilis.js",
    },
    {
        "id": 7,
        "name": "Matrimoni del Comune di Montecastrilli",
        "varname": "matrimoni_montecastrilli",
        "scraper": "python scraper/matrimoni-comune-montecastrilli.py",
    },
    {
        "id": 8,
        "name": "Albo Pretorio USR Umbria",
        "varname": "albo_pretorio_usr_umbria",
        "scraper": "python scraper/albopretorio-usr-umbria.py",
    },
    {
        "id": 9,
        "name": "Albo Pretorio UST Terni",
        "varname": "albo_pretorio_ust_terni",
        "scraper": "python scraper/albopretorio-ust-terni.py",
    },
    {
        "id": 10,
        "name": "Albo Pretorio USR Lazio",
        "varname": "albo_pretorio_usr_lazio",
        "scraper": "python scraper/albopretorio-usr-lazio.py",
    },
    {
        "id": 11,
        "name": "Albo Pretorio IIS Casagrande-Cesi",
        "varname": "albo_pretorio_iis_casagrandecesi",
        "scraper": "python scraper/albopretorio-iis-casagrandecesi.py",
    },
    {
        "id": 12,
        "name": "Amministrazione Trasparente IIS Casagrande-Cesi",
        "varname": "amministrazione_trasparente_iis_casagrandecesi",
        "scraper": "python scraper/amministrazionetrasparente-iis-casagrandecesi.py",
    },
    {
        "id": 13,
        "name": "Notizie IIS Casagrande-Cesi",
        "varname": "notizie_iis_casagrandecesi",
        "scraper": "python scraper/notizie-iis-casagrandecesi.py",
    },
    {
        "id": 14,
        "name": "Notizie DD Mazzini",
        "varname": "notizie_dd_mazzini",
        "scraper": "python scraper/notizie-dd-mazzini.py",
    },
    {
        "id": 15,
        "name": "Bacheca Nuvola",
        "varname": "bacheca_nuvola",
        "scraper": "python scraper/bacheca-nuvola.py",
    },
]


def create_logger(name: str) -> logging.Logger:
    """
    Create a rotating logger.
    """
    if not os.path.exists("logs"):
        os.mkdir("logs")
    logger = logging.getLogger(name)
    logger.setLevel(
        logging.INFO
    )  # Set to debug to view the output of the scrapers
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    logHandler = handlers.RotatingFileHandler(
        f"logs/{name}.log",
        maxBytes=2**20,
        backupCount=4,
    )
    logHandler.setLevel(logging.INFO)
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    return logger


# Create the main logger and source-specific loggers
loggers = {0: create_logger("main")}
for source in SOURCES:
    loggers[source["id"]] = create_logger(source["varname"])  # type: ignore


def show_help():
    """
    Show the help message.
    """
    print("usage: run.sh SOURCE_ID")
    print("\nThe following sources are supported:")
    for source in SOURCES:
        print(f"   {source['id']:2}: {source['name']}")


def ensure_db():
    """
    Ensure that the SQLite db is in place with the required
    tables and initial data.
    """
    logger = loggers[0]
    if not os.path.exists("pbots.db"):
        logger.info("pbots.db not found, creating default database...")
        conn = sqlite3.connect("pbots.db")
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE pbots_source (
            id INTEGER PRIMARY KEY,
            last_pub_id INTEGER DEFAULT NULL);
            """
        )
        cur.execute(
            """
            CREATE TABLE pbots_publication (
            id INTEGER PRIMARY KEY,
            url TEXT DEFAULT NULL,
            number TEXT DEFAULT NULL,
            publisher TEXT DEFAULT NULL,
            pub_type TEXT DEFAULT NULL,
            subject TEXT DEFAULT NULL,
            date_start TEXT DEFAULT NULL,
            date_end TEXT DEFAULT NULL,
            source_id INTEGER NOT NULL);
            """
        )
        cur.execute(
            """
            CREATE TABLE pbots_publicationattachment (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            publication_id INTEGER NOT NULL);
            """
        )
        cur.execute(
            """
            CREATE TABLE pbots_mailinglistmember (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            source_id INTEGER NOT NULL);
            """
        )
        conn.commit()
        conn.close()
    logger.info(
        "Ensuring that all sources are present in the database and that all mailing lists have at least one subscriber..."
    )
    conn = sqlite3.connect("pbots.db")
    cur = conn.cursor()
    for source in SOURCES:
        cur.execute("SELECT id FROM pbots_source WHERE id = :id", source)
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO pbots_source (id, last_pub_id) VALUES (:id, 0)",
                source,
            )
        cur.execute(
            "SELECT source_id FROM pbots_mailinglistmember WHERE source_id = :id",
            source,
        )
        if not cur.fetchone():
            cur.execute(
                f"""
                INSERT INTO pbots_mailinglistmember (name, email, source_id)
                VALUES ('{settings.DEFAULT_SUBSCRIBER_NAME}', '{settings.DEFAULT_SUBSCRIBER_EMAIL}', :id);
                """,
                source,
            )
    conn.commit()
    conn.close()


def publication_exists(cur: sqlite3.Cursor, pub: Dict[str, Any]):
    """
    Check whether the specified publication is already in the database.
    """
    query = ["SELECT * FROM pbots_publication WHERE 1=1"]
    for column in [
        "url",
        "number",
        "publisher",
        "pub_type",
        "subject",
        "date_start",
        "date_end",
        "source_id",
    ]:
        if pub[column] is None:
            query.append(f"{column} IS NULL")
        else:
            query.append(f"{column} = :{column}")
    cur.execute(" AND ".join(query), pub)
    return cur.fetchone()


def insert_publications(source_id: int, pubs: List[Dict[str, Any]]):
    """
    Store the specified publications in the database.
    """
    conn = sqlite3.connect("pbots.db")
    cur = conn.cursor()
    for pub in pubs:
        pub["source_id"] = source_id
        if publication_exists(cur, pub):
            continue
        cur.execute(
            """
            INSERT INTO pbots_publication (url, number, publisher, pub_type, subject, date_start, date_end, source_id)
            VALUES (:url, :number, :publisher, :pub_type, :subject, :date_start, :date_end, :source_id)
            """,
            pub,
        )
        if pub["attachments"]:
            pub_id = cur.lastrowid
            for att in pub["attachments"]:
                att["pub_id"] = pub_id
                cur.execute(
                    """
                    INSERT INTO pbots_publicationattachment (name, url, publication_id)
                    VALUES(:name, :url, :pub_id)
                    """,
                    att,
                )
    conn.commit()
    conn.close()


def get_new_publications(
    cur: sqlite3.Cursor, source_id: int
) -> List[Dict[str, Any]]:
    """
    Return the publications for the specified source that havn't still been used in a newsletter.
    """
    cur.execute(
        "SELECT last_pub_id FROM pbots_source WHERE id = ?", (source_id,)
    )
    last_pub_id = cur.fetchone()[0]
    cur.execute(
        "SELECT * FROM pbots_publication WHERE id > ? AND source_id = ?",
        (last_pub_id, source_id),
    )
    pubs = []
    for row in cur.fetchall():
        row_as_dict = {
            "id": row[0],
            "url": row[1],
            "number": row[2],
            "publisher": row[3],
            "pub_type": row[4],
            "subject": row[5],
            "date_start": row[6],
            "date_end": row[7],
            "source_id": row[8],
            "attachments": [],
        }
        cur.execute(
            "SELECT name, url FROM pbots_publicationattachment WHERE publication_id = :id",
            row_as_dict,
        )
        for att in cur.fetchall():
            row_as_dict["attachments"].append({"name": att[0], "url": att[1]})
        pubs.append(row_as_dict)
    return pubs


def send_newsletter(source_id: int, title: str):
    """
    Send the newsletter for the specified source id.
    The newsletter will contain every new publication after pbots_source.last_pub_id.
    """
    logger = loggers[source_id]
    conn = sqlite3.connect("pbots.db")
    cur = conn.cursor()
    # Verify whether there are publications to be sent
    publications = get_new_publications(cur, source_id)
    if not publications:
        logger.info("There are no new publications, nothing to do.")
        return
    logger.info(f"{len(publications)} new publications found.")
    # Prepare the email body
    context = {
        "title": title,
        "publications": publications,
    }
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            os.path.join(os.path.dirname(__file__), "template")
        ),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
    )
    template_plaintext = env.get_template("publications.txt")
    body_plaintext = template_plaintext.render(context)
    template_html = env.get_template("publications.html")
    body_html = template_html.render(context)
    # Send the email
    cur.execute(
        "SELECT name, email FROM pbots_mailinglistmember WHERE source_id = ?",
        (source_id,),
    )
    recipients = [{"name": row[0], "email": row[1]} for row in cur.fetchall()]
    if settings.EMAIL_USE_TLS:
        smtp = smtplib.SMTP_SSL
    else:
        smtp = smtplib.SMTP  # type: ignore
    with smtp(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        message = MIMEMultipart("alternative")
        message["Subject"] = "Newsletter {}".format(title)
        message["From"] = settings.EMAIL_FROM
        message["Reply-To"] = settings.EMAIL_REPLY_TO
        # Email clients will try to render the last part first
        message.attach(MIMEText(body_plaintext, "plain"))
        with open("template/pbsw-192x32.png", "rb") as logo:
            logo_mime = MIMEImage(logo.read())
        logo_mime.add_header("Content-ID", "<logo>")
        message.attach(logo_mime)
        message.attach(MIMEText(body_html, "html"))
        for rec in recipients:
            logger.info(
                f"Sending {title} to {rec['name']} <{rec['email']}>..."
            )
            message["To"] = f"{rec['name']} <{rec['email']}>"
            server.sendmail(
                settings.EMAIL_FROM, rec["email"], message.as_string()
            )
    # Keep track of the publications that were just sent
    last_pub_id = max(pub["id"] for pub in publications)
    logger.info(f"Updating last publication ID to {last_pub_id}")
    cur.execute(
        """
        UPDATE pbots_source
        SET last_pub_id = ?
        WHERE id = ?
        """,
        (last_pub_id, source_id),
    )
    conn.commit()
    conn.close()


def parse_json_pubs(output: str) -> List[Dict[str, Any]]:
    """
    Parse the JSON publications into a list of dictionaries.
    Empty fields are filled with default values.
    """
    pubs = json.loads(output)
    for i in range(len(pubs)):
        for key in [
            "url",
            "number",
            "publisher",
            "pub_type",
            "subject",
            "date_start",
            "date_end",
        ]:
            if key not in pubs[i]:
                pubs[i][key] = ""
    return pubs


def run_source(source_id: int):
    """
    Run the scraping and mailing processes for the specified source.
    """
    logger = loggers[source_id]
    source = next(
        s for s in SOURCES if s["id"] == source_id
    )  # type: Dict[str, Any]
    logger.info(f"Running scraper for {source_id}: {source['varname']}...")
    scraper = source["scraper"]
    process = subprocess.Popen(
        shlex.split(scraper), stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    output_bytes, err_bytes = process.communicate()
    exit_code = process.wait()
    logger.info(f"Exit code: {exit_code}")
    output = output_bytes.decode("utf-8")
    err = err_bytes.decode("utf-8")
    if exit_code != 0:
        logger.error(f"Error while running scraper for source {source_id}")
        print(f"Error while running scraper for source {source_id}")
        print(f"\n\nSTDOUT: {output}\n\nSTDERR: {err}\n\n")
    else:
        logger.debug(f"STDOUT: {output}\n\nSTDERR: {err}")
    # This is ugly, I should address the actual underlying problems...
    output = output[output.find("[") : output.rfind("]") + 1]
    pubs = parse_json_pubs(output)
    logger.info("Storing publications in the DB...")
    insert_publications(source_id, pubs)
    logger.info("Sending emails...")
    send_newsletter(source_id, source["name"])
    logger.info("Done.")


if __name__ == "__main__":
    ensure_db()
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)
    source_id = int(sys.argv[1])
    logger = loggers[0]
    logger.info(f"Running source {source_id}")
    try:
        run_source(source_id)
    except:  # noqa
        logger.error(
            "Uncaught error, see the source-specific log for for details"
        )
        loggers[source_id].error("Uncaught error", exc_info=True)
