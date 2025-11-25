"""Example: use LoginClient to login and save tokens to file.

Credentials are read from `login_example_credentials.json` in the project root if present.
The file should contain JSON with keys: base_url, username, password.
If the file is missing or incomplete the script falls back to interactive prompts.
"""

import argparse
import json
import os
from datetime import date as _date
from api.login import LoginClient
from api.komens import KomensClient
from api.timetable import TimetableClient
from py_bakalari.logging_config import configure_logging
import logging


def load_credentials(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="Example client for bakalari API")
    parser.add_argument("--output", choices=["timetable", "komens"], default="timetable",
                        help="Which API output to fetch and print")
    parser.add_argument("--date", help="Date for timetable in YYYY-MM-dd format. If omitted, uses start of current week (Monday).")
    parser.add_argument("--format", choices=["text"], default="text", help="Output format to use (currently only 'text')")
    args, unknown = parser.parse_known_args()

    cred_path = os.path.join(os.path.dirname(__file__) or ".", "./credentials.json")
    cred_path = os.path.normpath(cred_path)
    creds = load_credentials(cred_path)

    base_url = creds.get("base_url") or input("Base URL (https://...): ")
    username = creds.get("username") or input("Username: ")
    password = creds.get("password") or input("Password: ")

    client = LoginClient(base_url)

    # Authenticate: prefer saved valid tokens, try refresh, fall back to credentials login
    try:
        token = client.authenticate(username=username if username else None, password=password if password else None)
        logger = logging.getLogger(__name__)
        logger.debug("Access token saved to: %s", client.token_path)
        logger.debug("Expires at: %s", token.expires_at.isoformat())
    except Exception as e:
        logging.getLogger(__name__).error("Authentication failed: %s", e)
        return

    # Configure logging early so all clients use the chosen level
    debug = bool(creds.get("debug", False))
    configure_logging("DEBUG" if debug else "INFO")

    # Branch based on requested output and format
    fmt = args.format or "text"
    if args.output == "timetable":
        tt = TimetableClient(client, debug=debug)
        # Determine date to request: --date -> creds['date'] -> start of current week (Monday)
        if args.date:
            d = args.date
        elif creds.get("date"):
            d = creds.get("date")
        else:
            today = _date.today()
            delta_days = today.weekday()
            monday = today.replace(day=today.day) - __import__("datetime").timedelta(days=delta_days)
            d = monday.isoformat()

        try:
            out = tt.get_output(fmt, date=d)
            # Timetable text output should be printed directly
            if fmt == "text":
                print(out)
            else:
                logging.getLogger(__name__).info("%s", out)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to fetch timetable: %s", e)
            return

    else:
        km = KomensClient(client)
        try:
            out = km.get_output(fmt)
            # Komens output continues to use logger
            logging.getLogger(__name__).info("%s", out)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to fetch komens messages: %s", e)
            return



if __name__ == "__main__":
    main()
