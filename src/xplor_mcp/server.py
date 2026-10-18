"""MCP server exposing the Xplor Active API."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from fastmcp import FastMCP
from starlette.requests import Request

from xplor_mcp.client import XplorClient, XplorError
from xplor_mcp.oauth import XplorOAuthProvider
from xplor_mcp.store import device_id, load, save

BASE_URL = os.environ.get("XPLOR_MCP_BASE_URL", "http://127.0.0.1:8000")

oauth_provider = XplorOAuthProvider(base_url=BASE_URL)
mcp = FastMCP("xplor", auth=oauth_provider)


@mcp.custom_route("/xplor/login", methods=["GET"])
async def _login_page(request: Request):
    return await oauth_provider.login_page(request)


@mcp.custom_route("/xplor/login/start", methods=["POST"])
async def _login_start(request: Request):
    return await oauth_provider.login_start(request)


@mcp.custom_route("/xplor/login/confirm", methods=["POST"])
async def _login_confirm(request: Request):
    return await oauth_provider.login_confirm(request)


@contextmanager
def _session() -> Generator[XplorClient]:
    tokens = load()
    if tokens is None:
        raise XplorError("not logged in — complete the OAuth connection flow first")
    with XplorClient(device_id=device_id()) as client:
        client.load_tokens(tokens)
        try:
            yield client
        finally:
            save(client.tokens)  # persist any refreshed access/refresh token


def _account_id(client: XplorClient) -> str:
    return client.me()["accounts"][0]["id"]


@mcp.tool
def whoami() -> str:
    """Return the logged-in user's name and club."""
    with _session() as client:
        me = client.me()
    account = me["accounts"][0]
    return f"{me['givenName']} {me['familyName']} — {account['club']['name']}"


@mcp.tool
def list_slots(from_date: str) -> list[dict[str, object]]:
    """List bookable class slots from `from_date` (YYYY-MM-DD) onward."""
    with _session() as client:
        slots = client.list_slots(_account_id(client), from_date)
    return [
        {
            "id": slot.id,
            "start": slot.start,
            "end": slot.end,
            "activity": slot.activity,
            "location": slot.location,
            "bookable": slot.bookable,
            "cancellable": slot.cancellable,
        }
        for slot in slots
    ]


@mcp.tool
def upcoming_bookings() -> list[dict[str, object]]:
    """List the member's upcoming bookings."""
    with _session() as client:
        return client.upcoming_bookings(_account_id(client))


@mcp.tool
def book(slot_id: str) -> str:
    """Book a class slot by its id, as returned by list_slots."""
    with _session() as client:
        client.book(_account_id(client), slot_id)
    return "booked"


@mcp.tool
def cancel(slot_id: str) -> str:
    """Cancel a previously booked class slot by its id."""
    with _session() as client:
        client.cancel(_account_id(client), slot_id)
    return "cancelled"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
