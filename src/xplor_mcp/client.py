"""Client for the Xplor Active (CrossFit club) member API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import quote

import httpx2

BASE_URL = "https://api.xplor-active.com"
APP_SPACE_ID = "xplor"

# Static OAuth client credentials baked into the Android app (not per-user).
CLIENT_ID = "5ced2ad22d554a3cd3412d66c7de149a"
CLIENT_SECRET = (
    "19c039e27ab7b77884019178f2309bedf31cc47eefa65b5919b6d07b622cc5b"
    "ae2f4c1bad9c1d1f28295dfd5bec899e8dbde7e99cd5a10b9c1e69a3f5875a581"
)


class XplorError(RuntimeError):
    """Raised when the Xplor API returns an error response."""


@dataclass(slots=True)
class TokenSet:
    access_token: str
    refresh_token: str
    user_id: str
    expires_at: float  # unix timestamp

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 30  # safety margin


@dataclass(slots=True)
class Slot:
    """A single bookable class, as returned by `list_slots`."""

    id: str  # opaque, base64 — pass back as-is to book()/cancel()
    start: str
    end: str
    activity: str
    location: str
    bookable: bool
    cancellable: bool

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Slot:
        return cls(
            id=data["id"],
            start=data["startDate"],
            end=data["endDate"],
            activity=data["activity"]["name"],
            location=data["locationName"],
            bookable=data["bookable"],
            cancellable=data["cancellable"],
        )


class XplorClient:
    """Sync client for the Xplor Active member API."""

    def __init__(self, device_id: str, app_version: str = "2026.10.5") -> None:
        self._tokens: TokenSet | None = None
        self._http = httpx2.Client(
            base_url=BASE_URL,
            headers={
                "x-appspace-id": APP_SPACE_ID,
                "x-app-name": "Xplor Active",
                "x-app-version": app_version,
                "x-app-platform": "android",
                "x-device-remoteid": device_id,
                "x-timezone": "GMT",
                "accept-language": "en",
                "user-agent": "xplor-mcp/0.1",
            },
            timeout=15.0,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- authentication ----------------------------------------------------

    def request_login_code(self, email: str) -> tuple[str, str]:
        """Start a login: triggers a one-time code email."""
        r = self._post(
            "/members/v2/auth/identity_requests",
            json={"email": email},
            authenticated=False,
        )
        return r["id"], r["secret"]

    def confirm_login_code(self, request_id: str, secret: str, code: str, email: str) -> TokenSet:
        """Confirm the emailed code and exchange it for a token pair."""
        confirm = self._post(
            f"/members/v2/auth/identity_requests/{request_id}/confirm",
            json={"code": code, "secret": secret},
            authenticated=False,
        )
        return self._exchange_token(
            {
                "grant_type": "identity_request",
                "identity_request": confirm["token"],
                "username": email,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )

    def refresh(self) -> TokenSet:
        """Refresh the access token using the stored refresh token."""
        return self._exchange_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": self.tokens.refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            }
        )

    def load_tokens(self, tokens: TokenSet) -> None:
        """Restore a previously saved token pair instead of logging in again."""
        self._tokens = tokens

    @property
    def tokens(self) -> TokenSet:
        if self._tokens is None:
            raise XplorError("not logged in")
        return self._tokens

    def _exchange_token(self, payload: dict[str, str]) -> TokenSet:
        r = self._post("/members/v2/auth/token", json=payload, authenticated=False)
        self._tokens = TokenSet(
            access_token=r["access_token"],
            refresh_token=r["refresh_token"],
            user_id=r["user_id"],
            expires_at=time.time() + r["expires_in"],
        )
        return self._tokens

    # -- member data ---------------------------------------------------------

    def me(self) -> dict[str, Any]:
        return self._get("/members/v2/me")

    def user_account(self, user_account_id: str) -> dict[str, Any]:
        return self._get(f"/members/v2/user_accounts/{user_account_id}")

    def upcoming_bookings(self, user_account_id: str, page_size: int = 10) -> list[dict[str, Any]]:
        r = self._get(
            f"/members/v2/user_accounts/{user_account_id}/bookings/upcoming",
            params={"pageSize": page_size},
        )
        return r["items"]

    def list_slots(self, user_account_id: str, from_date: str) -> list[Slot]:
        """List bookable class slots from `from_date` (YYYY-MM-DD) onward."""
        r = self._get(
            f"/members/v2/user_accounts/{user_account_id}/bookings/slots",
            params={"from": from_date},
        )
        return [Slot.from_json(item) for item in r["items"]]

    def book(self, user_account_id: str, slot_id: str) -> None:
        self._post(
            f"/members/v2/user_accounts/{user_account_id}/bookings/slots/"
            f"{quote(slot_id, safe='')}/book",
            json={"guests": []},
        )

    def cancel(self, user_account_id: str, slot_id: str) -> None:
        self._post(
            f"/members/v2/user_accounts/{user_account_id}/bookings/slots/"
            f"{quote(slot_id, safe='')}/cancel"
        )

    # -- plumbing --------------------------------------------------------

    def _auth_header(self, authenticated: bool) -> dict[str, str]:
        if not authenticated:
            return {}
        if self.tokens.expired:
            self.refresh()
        return {"authorization": f"Bearer {self.tokens.access_token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._http.get(path, params=params, headers=self._auth_header(True))
        return self._unwrap(r)

    def _post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        r = self._http.post(path, json=json, headers=self._auth_header(authenticated))
        return self._unwrap(r)

    @staticmethod
    def _unwrap(r: httpx2.Response) -> Any:
        if r.is_error:
            raise XplorError(f"{r.status_code} {r.request.method} {r.request.url}: {r.text}")
        return r.json() if r.content else None
