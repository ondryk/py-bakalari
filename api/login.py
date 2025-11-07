"""Login client for Bakaláři API (newer API version)

Provides LoginClient supporting password and refresh_token grants.
Tokens are stored in a JSON file (default: ~/.py_bakalari_tokens.json).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import requests


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    id_token: Optional[str]
    token_type: str
    expires_in: int
    obtained_at: datetime
    extra: Dict[str, Any]

    @property
    def expires_at(self) -> datetime:
        return self.obtained_at + timedelta(seconds=self.expires_in)

    def is_expired(self, margin_seconds: int = 10) -> bool:
        return datetime.utcnow() + timedelta(seconds=margin_seconds) >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "obtained_at": int(self.obtained_at.timestamp()),
        }
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenSet":
        obtained = datetime.utcfromtimestamp(int(data.get("obtained_at", datetime.utcnow().timestamp())))
        extra = {k: v for k, v in data.items() if k not in {"access_token", "refresh_token", "id_token", "token_type", "expires_in", "obtained_at"}}
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            id_token=data.get("id_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 0)),
            obtained_at=obtained,
            extra=extra,
        )


class LoginError(Exception):
    pass


class LoginClient:
    def __init__(self, base_url: str, token_path: Optional[str] = None, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        # Default token file placed in repository root to make examples and tools share it.
        default_path = os.path.join(os.getcwd(), "py_bakalari_tokens.json")
        self.token_path = token_path or default_path
        self.session = session or requests.Session()

    def _login_request(self, data: Dict[str, str]) -> TokenSet:
        url = f"{self.base_url}/api/login"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.session.post(url, data=data, headers=headers, timeout=30)
        try:
            body = resp.json()
        except Exception:
            raise LoginError(f"Invalid response from server: {resp.status_code} {resp.text}")

        if resp.status_code != 200:
            # Expected error structure as per docs
            err = body.get("error_description") or body.get("error") or resp.text
            raise LoginError(f"Login failed: {err}")

        # Map fields robustly (older API variants may differ)
        at = body.get("access_token")
        rt = body.get("refresh_token")
        if not at or not rt:
            raise LoginError("Login response missing tokens")

        token = TokenSet(
            access_token=at,
            refresh_token=rt,
            id_token=body.get("id_token"),
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 0)),
            obtained_at=datetime.utcnow(),
            extra={k: v for k, v in body.items() if k not in {"access_token", "refresh_token", "id_token", "token_type", "expires_in"}},
        )
        return token

    def login_with_password(self, username: str, password: str, client_id: str = "ANDR") -> TokenSet:
        data = {
            "client_id": client_id,
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        token = self._login_request(data)
        self.save_tokens(token)
        return token

    def refresh(self, refresh_token: str, client_id: str = "ANDR") -> TokenSet:
        data = {"client_id": client_id, "grant_type": "refresh_token", "refresh_token": refresh_token}
        token = self._login_request(data)
        self.save_tokens(token)
        return token

    def save_tokens(self, token: TokenSet) -> None:
        obj = token.to_dict()
        # Ensure directory exists
        d = os.path.dirname(self.token_path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)

    def load_tokens(self) -> Optional[TokenSet]:
        if not os.path.exists(self.token_path):
            return None
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return TokenSet.from_dict(data)
        except Exception:
            return None

    def get_valid_access_token(self) -> Optional[str]:
        token = self.load_tokens()
        if token is None:
            return None
        if token.is_expired():
            # try refreshing
            try:
                new = self.refresh(token.refresh_token)
                return new.access_token
            except LoginError:
                return None
        return token.access_token
