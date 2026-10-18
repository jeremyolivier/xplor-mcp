"""Interactive one-time login, saving the resulting tokens to disk."""

from __future__ import annotations

from xplor_mcp.client import XplorClient
from xplor_mcp.store import DB_PATH, device_id, save


def main() -> None:
    email = input("Email: ").strip()
    with XplorClient(device_id=device_id()) as client:
        request_id, secret = client.request_login_code(email)
        print(f"Code sent to {email}, check your inbox.")
        code = input("Code: ").strip()
        tokens = client.confirm_login_code(request_id, secret, code, email)
        save(tokens)
    print(f"Logged in (user_id={tokens.user_id}). Tokens saved to {DB_PATH}.")


if __name__ == "__main__":
    main()
