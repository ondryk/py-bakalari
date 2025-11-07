"""Komens client for Bakaláři API.

Provides helpers to list messages (received, sent, noticeboard), fetch message detail,
mark a message as read and get unread counts. Uses the token file saved by `api/login.py`.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Dict, Any

import requests

from api.login import LoginClient, TokenSet, LoginError


class KomensError(Exception):
    pass


class KomensClient:
    def __init__(self, base_url: str, token_path: Optional[str] = None, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        # Reuse same default token path as LoginClient when not provided
        default_path = token_path or os.path.join(os.getcwd(), "py_bakalari_tokens.json")
        self.login_client = LoginClient(base_url, token_path=default_path, session=session)

    def _auth_headers(self) -> Dict[str, str]:
        token = self.login_client.load_tokens()
        if token is None:
            raise KomensError("No tokens found - please login first")
        if token.is_expired():
            try:
                token = self.login_client.refresh(token.refresh_token)
            except LoginError as e:
                raise KomensError(f"Failed to refresh token: {e}")
        return {"Authorization": f"Bearer {token.access_token}", "Content-Type": "application/x-www-form-urlencoded"}

    def _post_list(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/3/komens/{path}"
        headers = self._auth_headers()
        resp = self.login_client.session.post(url, data=params or {}, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        if resp.status_code == 405:
            raise KomensError(f"Method not allowed: {resp.text}")
        try:
            return resp.json()
        except Exception:
            raise KomensError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def received(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list("messages/received", params=params)

    def sent(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list("messages/sent", params=params)

    def noticeboard(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._post_list("messages/noticeboard", params=params)

    def get_message(self, category: str, message_id: str) -> Dict[str, Any]:
        # category should be 'received' or 'sent'
        url = f"{self.base_url}/api/3/komens/messages/{category}/{message_id}"
        headers = self._auth_headers()
        resp = self.login_client.session.get(url, headers=headers, timeout=30)
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        try:
            return resp.json()
        except Exception:
            raise KomensError(f"Invalid JSON response: {resp.status_code} {resp.text}")

    def mark_as_read(self, message_id: str) -> None:
        url = f"{self.base_url}/api/3/komens/message/{message_id}/mark-as-read"
        headers = self._auth_headers()
        resp = self.login_client.session.put(url, headers=headers, data={}, timeout=30)
        if resp.status_code == 204:
            return
        if resp.status_code == 401:
            raise KomensError("Unauthorized - invalid or expired access token")
        raise KomensError(f"Failed to mark as read: {resp.status_code} {resp.text}")

    def unread_count(self, list_name: str = "received") -> int:
        # list_name: 'received' or 'noticeboard'
        url = f"{self.base_url}/api/3/komens/messages/{list_name}/unread"
        headers = self._auth_headers()
        resp = self.login_client.session.get(url, headers=headers, timeout=30)
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
