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

    # Branch based on requested output
    if args.output == "timetable":
        tt = TimetableClient(client, debug=debug)
        # Determine date to request: --date -> creds['date'] -> start of current week (Monday)
        if args.date:
            d = args.date
        elif creds.get("date"):
            d = creds.get("date")
        else:
            # compute monday of current week
            today = _date.today()
            # weekday(): Monday is 0
            delta_days = today.weekday()
            monday = today.replace(day=today.day) - __import__("datetime").timedelta(days=delta_days)
            d = monday.isoformat()
        try:
            data = tt.actual(d)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to fetch timetable: %s", e)
            return

        # Pretty-print basic timetable: Days -> Hours
        days_root = data.get("Days") or []
        if not days_root:
            logging.getLogger(__name__).warning("No timetable data returned.")
            return

        # Build a mapping of HourId -> (BeginTime, EndTime) if available
        hours_list = data.get("Hours") or []
        hour_map = {}
        for hh in hours_list:
            try:
                hour_map[int(hh.get("Id"))] = (hh.get("BeginTime", ""), hh.get("EndTime", ""))
            except Exception:
                pass

        # Build subject id -> name map
        subjects_list = data.get("Subjects") or []
        subject_map = {}
        for s in subjects_list:
            sid = (s.get("Id") or "").strip()
            # prefer abbreviation for compact display
            name = s.get("Abbrev") or s.get("Name") or sid
            subject_map[sid] = name

        for day in days_root:
                day_name = day.get("DayName") or day.get("Date") or "Day"
                day_type = day.get("DayType")
                # If this is a Celebration, print the DayDescription
                if day_type == "Celebration":
                    dd = day.get("DayDescription") or ""
                    if dd:
                        logging.getLogger(__name__).info("** Celebration: %s **", dd)

                # Prepare one-line summary of all atoms in the day
                atom_entries = []
                for atom in day.get("Atoms", []) or []:
                    hid = atom.get("HourId")
                    subj_id = (atom.get("SubjectId") or "").strip()
                    subj = subject_map.get(subj_id, subj_id)
                    if hid is None:
                        entry = f"{subj}"
                    else:
                        try:
                            hid_int = int(hid)
                        except Exception:
                            hid_int = hid
                        bt, et = hour_map.get(hid_int, ("", ""))
                        time_range = f"{bt}-{et}" if bt or et else str(hid)
                        entry = f"{time_range} {subj}"
                    # If there's a Change object, print its description
                    change = atom.get("Change")
                    if change:
                        desc = change.get("Description") or change.get("ChangeType") or ""
                        if desc:
                            entry = f"{entry} (CHANGE: {desc})"
                    atom_entries.append(entry)
                line = " | ".join(atom_entries) if atom_entries else "(no hours)"
                logging.getLogger(__name__).info("-- %s (%s) --\n%s\n", day_name, day_type, line)

    else:
        # Komens listing
        km = KomensClient(client)
        try:
            res = km.received()
        except Exception as e:
            logging.getLogger(__name__).error("Failed to fetch komens messages: %s", e)
            return

        # Expect the response to contain a list under 'Messages' or similar
        messages = res.get("Messages") or res.get("data") or res
        logger = logging.getLogger(__name__)
        if not messages:
            logger.info("No komens messages returned.")
            return

        # Print a compact list: id | from | subject | date
        for m in messages:
            mid = m.get("Id") or m.get("MessageId") or "?"
            sender = m.get("From") or m.get("Sender") or m.get("FromName") or ""
            subject = m.get("Subject") or m.get("Title") or "(no subject)"
            dt = m.get("Date") or m.get("SentAt") or ""
            logger.info("%s | %s | %s | %s", mid, sender, subject, dt)



if __name__ == "__main__":
    main()
