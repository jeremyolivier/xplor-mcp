# xplor-mcp

Unofficial Python client for the Xplor Active API (used by CrossFit Valence
and other gyms running on the same platform). Each user logs in with their
own account — nothing here is tied to a specific club or person.

**Work in progress.** No MCP server yet — just the auth flow and a sync
client covering read + booking/cancellation.

Not affiliated with or endorsed by Xplor. Use at your own risk, against
your own account only.

## Setup

```bash
uv sync
uv run xplor-login
```

Enter your email, grab the one-time code from your inbox, paste it in.
Tokens are saved to `~/.xplor-mcp/` (never in this repo) and reused
automatically after that.

## Usage

```python
from xplor_mcp import XplorClient
from xplor_mcp.store import device_id, load

tokens = load()  # None if you haven't run `uv run xplor-login` yet
client = XplorClient(device_id=device_id())
client.load_tokens(tokens)

me = client.me()
account_id = me["accounts"][0]["id"]
slots = client.list_slots(account_id, from_date="2026-10-20")
```

## Dev

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
```
