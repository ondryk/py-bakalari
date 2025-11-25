"""Timetable client for Bakaláři API.

Provides helpers for current timetable (`actual`), permanent timetable (`permanent`)
and a convenience `holidays` helper to extract holiday/day-type info for a date.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
import re
import requests
import logging
from datetime import date as _date, datetime
import json as _json

from api.login import LoginClient, LoginError


class TimetableError(Exception):
    pass


class TimetableClient:
    def __init__(self, login_client: LoginClient, debug: bool = False):
        self.login_client = login_client
        self.base_url = self.login_client.base_url
        self.debug = bool(debug)
        self._logger = logging.getLogger(__name__)

    def _auth_headers(self) -> Dict[str, str]:
        try:
            access = self.login_client.get_access_token()
        except LoginError as e:
            raise TimetableError(str(e))
        return {"Authorization": f"Bearer {access}", "Content-Type": "application/x-www-form-urlencoded"}

    def actual(self, date: str) -> Dict[str, Any]:
        """GET /api/3/timetable/actual?date=YYYY-MM-dd

        Returns the timetable for the requested date.
        """
        url = f"{self.base_url}/api/3/timetable/actual"
        headers = self._auth_headers()
        params = {"date": date}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if self.debug:
            self._logger.debug("[TimetableClient] raw response: %s", resp.text)
        if resp.status_code == 401:
            raise TimetableError("Unauthorized - invalid or expired access token")
        if resp.status_code == 400:
            raise TimetableError(f"Bad request: {resp.text}")
        try:
            return resp.json()
        except Exception:
            raise TimetableError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def permanent(self) -> Dict[str, Any]:
        """GET /api/3/timetable/permanent

        Returns the permanent timetable.
        """
        url = f"{self.base_url}/api/3/timetable/permanent"
        headers = self._auth_headers()
        resp = requests.get(url, headers=headers, timeout=30)
        if self.debug:
            self._logger.debug("[TimetableClient] raw response: %s", resp.text)
        if resp.status_code == 401:
            raise TimetableError("Unauthorized - invalid or expired access token")
        try:
            return resp.json()
        except Exception:
            raise TimetableError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def format_text(self, data: Dict[str, Any]) -> str:
        """Format timetable response into a human-readable plain-text string.

        Returns a multi-line string similar to the previous example output.
        """
        lines = []
        days_root = data.get("Days") or []
        if not days_root:
            return "No timetable data returned."

        # Build a mapping of HourId -> (BeginTime, EndTime)
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
            name = s.get("Abbrev") or s.get("Name") or sid
            subject_map[sid] = name

        # Weekday names in Czech (two-letter abbreviations with accents)
        weekday_names = [
            "Po",
            "Út",
            "St",
            "Čt",
            "Pá",
            "So",
            "Ne",
        ]

        

        for day in days_root:
            # Attempt to extract a date string from the day entry
            raw_date = day.get("Date") or day.get("DayName") or None
            day_type = day.get("DayType")
            day_type = day.get("DayType")
            # Parse ISO datetime if possible
            date_short = ""
            weekday = ""
            if raw_date:
                try:
                    # Some responses include full ISO timestamp with offset
                    dt = datetime.fromisoformat(raw_date)
                    date_short = f"{dt.day:02d}.{dt.month:02d}.{dt.year}"
                    weekday = weekday_names[dt.weekday()]
                except Exception:
                    # Fallback: try to parse just the date part
                    try:
                        ds = raw_date.split("T", 1)[0]
                        dt2 = datetime.fromisoformat(ds)
                        date_short = f"{dt2.day:02d}.{dt2.month:02d}.{dt2.year}"
                        weekday = weekday_names[dt2.weekday()]
                    except Exception:
                        # Last resort: use raw string
                        date_short = raw_date
                        weekday = day.get("DayName") or ""

            # Prepare entries for the day (one-line)
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
                change = atom.get("Change")
                if change:
                    # When there's a change, attempt to detect subject-change patterns
                    desc = (change.get("Description") or change.get("ChangeType") or "").strip()
                    # Patterns like: "Změna předmětu: Pr (VV)" -> NEW (OLD)
                    subj_map = None
                    try:
                        # Try several patterns. Common Czech pattern: "Změna předmětu: NEW (OLD)"
                        patterns = [
                            r"zm[eě]na\s+předm[iě]tu[:\s]+([^\(]+)\s*\(([^\)]+)\)",
                            r"zm[eě]na[:\s]+([^\(]+)\s*\(([^\)]+)\)",
                            r"change\s+of\s+subject[:\s]+([^\(]+)\s*\(([^\)]+)\)",
                            r"subject\s+change[:\s]+([^\(]+)\s*\(([^\)]+)\)",
                        ]
                        m = None
                        for pat in patterns:
                            m = re.search(pat, desc, re.IGNORECASE)
                            if m:
                                break
                        if m:
                            # Normalize: group(1) is likely NEW, group(2) OLD
                            new_subj = re.sub(r"\s+", " ", m.group(1)).strip()
                            old_subj = re.sub(r"\s+", " ", m.group(2)).strip()
                            subj_map = (old_subj, new_subj)
                    except Exception:
                        subj_map = None

                    if subj_map:
                        old_subj, new_subj = subj_map
                        if hid is None:
                            entry = f"{old_subj} -> {new_subj}"
                        else:
                            entry = f"{time_range} {old_subj} -> {new_subj}"
                    else:
                        # Detect substitution (suplování) and show subject + teacher info
                        ldesc = desc.lower()
                        if "supl" in ldesc or "substitut" in ldesc:
                            # try to extract teacher name after colon, fallback to whole desc
                            teacher_raw = None
                            if ":" in desc:
                                teacher_raw = desc.split(":", 1)[1].strip()
                            else:
                                teacher_raw = desc
                            teacher = re.sub(r"\s+", " ", teacher_raw).strip()
                            label = "Suplování"
                            if hid is None:
                                entry = f"{subj} ({label}: {teacher})"
                            else:
                                entry = f"{time_range} {subj} ({label}: {teacher})"
                        else:
                            # Generic fallback: show only the change description
                            if desc:
                                if hid is None:
                                    entry = f"{desc}"
                                else:
                                    entry = f"{time_range} {desc}"
                atom_entries.append(entry)
            line = " | ".join(atom_entries) if atom_entries else "(no hours)"

            header = f"{date_short} - {weekday}"
            # If celebration, include description inline before entries
            if day_type == "Celebration":
                dd = day.get("DayDescription") or ""
                if dd:
                    header = f"** Celebration: {dd} ** {header}"

            lines.append(f"{header} -- {line}")

        return "\n".join(lines)

    def format_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format timetable response into a structured JSON-friendly dict.

                Output structure:
                {
                    "days": [
                        {
                            "date": "YYYY-MM-DD",
                            "day_abbrev": "Po|Út|...",
                            "hours": [
                                {"time_range": "HH:MM-HH:MM", "subject": "ČJ", "change": true, "change_text": "..."},
                                ...
                            ]
                        }, ...
                    ]
                }
        """
        days_root = data.get("Days") or []
        if not days_root:
            return {"days": []}

        # build hour map and subject map as in format_text
        hours_list = data.get("Hours") or []
        hour_map = {}
        for hh in hours_list:
            try:
                hour_map[int(hh.get("Id"))] = (hh.get("BeginTime", ""), hh.get("EndTime", ""))
            except Exception:
                pass

        subjects_list = data.get("Subjects") or []
        subject_map = {}
        for s in subjects_list:
            sid = (s.get("Id") or "").strip()
            subject_map[sid] = s.get("Abbrev") or s.get("Name") or sid

        days_out = []
        
        for day in days_root:
            raw_date = day.get("Date") or day.get("DayName") or None
            date_iso = raw_date
            day_abbrev = ""
            day_type = day.get("DayType")
            if raw_date:
                try:
                    dt = datetime.fromisoformat(raw_date.split("T", 1)[0])
                    date_iso = dt.date().isoformat()
                    # weekday mapping
                    weekday_names = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
                    day_abbrev = weekday_names[dt.weekday()]
                except Exception:
                    date_iso = raw_date
                    day_abbrev = day.get("DayName") or ""

            hours_out = []
            # collect hour entries and sort them by begin time when available
            raw_atoms = day.get("Atoms", []) or []
            atom_entries = []

            # If this day is a celebration, add a synthetic full-day hour first
            # Use 8:00-13:30 time range for celebrations and mark hours_count as 8 later
            if day_type == "Celebration":
                dd = day.get("DayDescription") or ""
                if dd:
                    # celebration time range (school half-day)
                    atom_entries.append({
                        "time_range": "8:00-13:30",
                        "subject": dd,
                        "change": False,
                        "change_text": None,
                        "_sort_key": (8, 0),
                    })
            for atom in raw_atoms:
                hid = atom.get("HourId")
                subj_id = (atom.get("SubjectId") or "").strip()
                subj = subject_map.get(subj_id, subj_id)
                bt, et = ("", "")
                if hid is not None:
                    try:
                        hid_int = int(hid)
                    except Exception:
                        hid_int = hid
                    bt, et = hour_map.get(hid_int, ("", ""))
                time_range = f"{bt}-{et}" if bt or et else ""

                non_standard = False
                change = atom.get("Change")
                change_text = None
                if change:
                    desc = (change.get("Description") or change.get("ChangeType") or "").strip()
                    change_text = desc
                    # heuristics: if subject replacement or substitution, mark non_standard
                    ldesc = desc.lower()
                    if desc:
                        non_standard = True

                # compute sortable key from begin time (bt) like '08:00' or '8:00'
                def _parse_time_key(t: str):
                    if not t:
                        return (99, 99)
                    try:
                        parts = t.split(":")
                        h = int(parts[0])
                        m = int(parts[1]) if len(parts) > 1 else 0
                        return (h, m)
                    except Exception:
                        return (99, 99)

                atom_entries.append({
                    "time_range": time_range,
                    "subject": subj,
                    "change": bool(non_standard),
                    "change_text": change_text,
                    "_sort_key": _parse_time_key(bt if bt is not None else ""),
                })

            # sort by sort_key (begin time) if available
            atom_entries.sort(key=lambda x: x.get("_sort_key") or "")
            for ae in atom_entries:
                ae.pop("_sort_key", None)
                hours_out.append(ae)

            # compute hours_count: normally number of hours, but celebrations count as 6
            hours_count = len(hours_out)
            if day_type == "Celebration":
                hours_count = 6

            days_out.append({"date": date_iso, "day_abbrev": day_abbrev, "hours": hours_out, "hours_count": hours_count})

        return {"days": days_out}

    def get_text(self, date: str) -> str:
        data = self.actual(date)
        return self.format_text(data)

    def get_output(self, fmt: str, date: str | None = None) -> str:
        """Unified output entrypoint. fmt currently supports 'text'.

        If date is required for the format, .date must be provided (for timetable it's required).
        """
        fmt = (fmt or "text").lower()
        if not date:
            raise TimetableError("Date is required for timetable output")

        if fmt == "text":
            return self.get_text(date)
        if fmt == "json":
            data = self.actual(date)
            json_out = _json.dumps(self.format_json(data), ensure_ascii=False)
            return json_out
        raise TimetableError(f"Unsupported format: {fmt}")

    def holidays(self, date: str) -> Dict[str, Any]:
        """Convenience: fetch actual timetable for date and return day information related to holidays.

        The API returns DayType and DayDescription in the day entries; this helper extracts them.
        """
        data = self.actual(date)
        # The structure can vary; attempt to find day entries and return DayType/DayDescription
        # Return the raw day object(s) for the requested date.
        # Typical response has top-level Weeks -> Days
        days = []
        try:
            weeks = data.get("Weeks") or []
            for w in weeks:
                for d in w.get("Days", []) or []:
                    # Day typically has "Day" or date; include if matches provided date
                    # We can't reliably match timezone formats here; return all days and let caller pick
                    days.append(d)
        except Exception:
            pass
        return {"Days": days}
