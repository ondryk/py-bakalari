"""Komens client for Bakaláři API.

Provides helpers to list messages (received, sent, noticeboard), fetch message detail,
mark a message as read and get unread counts. Uses the token file saved by `api/login.py`.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Dict, Any
from enum import Enum

import requests

from api.login import LoginClient, TokenSet, LoginError


class KomensError(Exception):
    pass


class MessageList(Enum):
    RECEIVED = "received"
    SENT = "sent"
    NOTICEBOARD = "noticeboard"


class MessageCategory(Enum):
    RECEIVED = "received"
    SENT = "sent"


class KomensClient:
    def __init__(self, login_client: LoginClient):
        # KomensClient uses the base_url from the provided LoginClient
        self.login_client = login_client
        self.base_url = self.login_client.base_url

    def _auth_headers(self) -> Dict[str, str]:
        try:
            access = self.login_client.get_access_token()
        except LoginError as e:
            raise KomensError(str(e))
        return {"Authorization": f"Bearer {access}", "Content-Type": "application/x-www-form-urlencoded"}

    def _post_list(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/3/komens/{path}"
        headers = self._auth_headers()
        resp = requests.post(url, data=params or {}, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        if resp.status_code == 405:
            raise KomensError(f"Method not allowed: {resp.text}")
        try:
            return resp.json()
        except Exception:
            raise KomensError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def received(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list(f"messages/{MessageList.RECEIVED.value}", params=params)

    def sent(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list(f"messages/{MessageList.SENT.value}", params=params)

    def noticeboard(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list(f"messages/{MessageList.NOTICEBOARD.value}", params=params)

    def get_message(self, category: MessageCategory, message_id: str) -> Dict[str, Any]:
        # category should be MessageCategory.RECEIVED or MessageCategory.SENT
        url = f"{self.base_url}/api/3/komens/messages/{category.value}/{message_id}"
        headers = self._auth_headers()
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        try:
            return resp.json()
        except Exception:
            raise KomensError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def mark_as_read(self, message_id: str) -> None:
        url = f"{self.base_url}/api/3/komens/message/{message_id}/mark-as-read"
        headers = self._auth_headers()
        resp = requests.put(url, headers=headers, data={}, timeout=30)
        if resp.status_code == 204:
            return
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        raise KomensError(f"Failed to mark as read: {resp.status_code} {resp.text}")

    def unread_count(self, list_name: MessageList = MessageList.RECEIVED) -> int:
        # list_name: MessageList.RECEIVED or MessageList.NOTICEBOARD
        url = f"{self.base_url}/api/3/komens/messages/{list_name.value}/unread"
        headers = self._auth_headers()
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        if resp.status_code != 200:
            raise KomensError(f"Failed to get unread count: {resp.status_code} {resp.text}")
        try:
            # API returns a bare number (e.g. 0) or JSON number
            data = resp.json()
            if isinstance(data, int):
                return data
            # Some servers may wrap in JSON structure, attempt to coerce
            if isinstance(data, dict):
                # find a numeric value
                for v in data.values():
                    if isinstance(v, int):
                        return v
            raise KomensError(f"Unexpected unread response: {data}")
        except ValueError:
            # Fallback: parse text
            try:
                return int(resp.text.strip())
            except Exception:
                raise KomensError(f"Invalid response for unread count: {resp.text}")

    def format_text(self, data: Dict[str, Any]) -> str:
        """Format komens list response into a compact plain-text listing.

        Expects `data` to be the JSON returned by `received()` or similar.
        """
        # data may be a dict with Messages, or a list directly
        messages = data.get("Messages") if isinstance(data, dict) else None
        if messages is None:
            messages = data.get("data") if isinstance(data, dict) else None
        if messages is None and isinstance(data, list):
            messages = data
        if not messages:
            return "No komens messages returned."

        lines = []
        for m in messages:
            mid = m.get("Id") or m.get("MessageId") or "?"
            sender = m.get("From") or m.get("Sender") or m.get("FromName") or ""
            subject = m.get("Subject") or m.get("Title") or "(no subject)"
            dt = m.get("Date") or m.get("SentAt") or ""
            lines.append(f"{mid} | {sender} | {subject} | {dt}")
        return "\n".join(lines)

    def get_text(self, params: Optional[Dict[str, Any]] = None) -> str:
        data = self.received(params=params)
        return self.format_text(data)

    def get_output(self, fmt: str, params: Optional[Dict[str, Any]] = None) -> str:
        fmt = (fmt or "text").lower()
        if fmt == "text":
            return self.get_text(params=params)
        raise KomensError(f"Unsupported format: {fmt}")
