"""One-off sanity check: reload the saved session and read real data."""

from __future__ import annotations

import json

from xplor_mcp import XplorClient
from xplor_mcp.store import device_id, load


def main() -> None:
    tokens = load()
    if tokens is None:
        raise SystemExit("No saved session — run `uv run xplor-login` first.")

    with XplorClient(device_id=device_id()) as client:
        client.load_tokens(tokens)

        me = client.me()
        print(f"Logged in as: {me['givenName']} {me['familyName']} <{me['email']}>")

        account = me["accounts"][0]
        print(f"Club: {account['club']['name']} (user_account_id={account['id']})")

        bookings = client.upcoming_bookings(account["id"])
        print(f"Upcoming bookings: {len(bookings)}")
        print(json.dumps(bookings, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
