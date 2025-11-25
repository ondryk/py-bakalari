"""Timetable client for Bakaláři API.

Provides helpers for current timetable (`actual`), permanent timetable (`permanent`)
and a convenience `holidays` helper to extract holiday/day-type info for a date.
"""
from __future__ import annotations

from typing import Optional, Dict, Any
import requests
import logging

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
