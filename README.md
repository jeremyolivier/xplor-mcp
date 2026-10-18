# xplor-mcp

Unofficial MCP server (and Python client) for the Xplor Active API — the
platform behind the booking app used by CrossFit Valence and other gyms
running on the same system. Each member authenticates with their **own**
Xplor account; nothing here is tied to a specific club or person.

Not affiliated with or endorsed by Xplor. Use at your own risk.

## Connect your gym account to Claude (or any MCP client)

A hosted instance is already running — no setup needed:

```
https://xplor-mcp.tail4724e6.ts.net/mcp
```

**In Claude.ai / Claude Desktop**: Settings → Connectors → Add custom
connector → paste the URL above → you'll land on a login page: enter your
email, then the one-time code Xplor sends you. That's it.

Any other client that supports remote MCP servers (Streamable HTTP + OAuth
2.1) should work the same way — paste the URL, log in with your own Xplor
email and code.

You authenticate with your **own** Xplor credentials — no one else can see
your bookings or act on your account, and I (the person running this
server) never see your password, only Xplor's own one-time login code
exchange.

### Available tools

| Tool | What it does |
|---|---|
| `whoami` | Your name and club |
| `list_slots(from_date)` | Bookable classes from a given date (`YYYY-MM-DD`) |
| `upcoming_bookings()` | Your upcoming bookings |
| `book(slot_id)` | Book a class (id from `list_slots`) |
| `cancel(slot_id)` | Cancel a booked class |

## Prefer to run your own instance?

```bash
uv sync
XPLOR_MCP_BASE_URL=https://your-public-domain \
  uv run fastmcp run src/xplor_mcp/server.py --transport http --host 0.0.0.0 --port 8000
```

`XPLOR_MCP_BASE_URL` must be a real public HTTPS URL (OAuth requires it).
[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) is a free way to
get one without a static IP or port forwarding.

## Use the Python client directly, without MCP

```bash
uv sync
uv run xplor-login   # prompts for email, then the one-time code
```

```python
from xplor_mcp import XplorClient
from xplor_mcp.store import device_id, load

# user_id is printed by `uv run xplor-login`, or TokenSet.user_id after login
tokens = load(user_id)
client = XplorClient(device_id=device_id())
client.load_tokens(tokens)

me = client.me()
account_id = me["accounts"][0]["id"]
slots = client.list_slots(account_id, from_date="2026-10-20")
```

Tokens are stored in a local SQLite database at `~/.xplor-mcp/xplor-mcp.db`
(never in this repo), keyed by Xplor user id, and reused automatically.

## Dev

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
```
