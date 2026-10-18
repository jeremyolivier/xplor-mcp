"""Local persistence for members' Xplor tokens and registered OAuth clients.

Backed by a single SQLite database (stdlib, no extra dependency) instead of
one JSON file per member, mainly for atomic writes — a `.write_text()` killed
mid-way corrupts a JSON file, SQLite's transactions don't have that failure
mode.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from fastmcp.server.auth.auth import OAuthClientInformationFull

from xplor_mcp.client import TokenSet

CONFIG_DIR = Path.home() / ".xplor-mcp"
DB_PATH = CONFIG_DIR / "xplor-mcp.db"
DEVICE_ID_PATH = CONFIG_DIR / "device_id"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    try:
        os.chmod(DB_PATH, 0o600)  # no-op on Windows, meaningful on POSIX
    except OSError:
        pass
    return conn


def save(tokens: TokenSet) -> None:
    """Upsert a member's token pair, keyed by their Xplor user id."""
    conn = _connect()
    with closing(conn), conn:
        conn.execute(
            """
            INSERT INTO users (user_id, access_token, refresh_token, expires_at)
            VALUES (:user_id, :access_token, :refresh_token, :expires_at)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at
            """,
            asdict(tokens),
        )


def load(user_id: str) -> TokenSet | None:
    """Read a previously saved token pair for this Xplor user id, or None."""
    conn = _connect()
    with closing(conn):
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    access_token, refresh_token, expires_at = row
    return TokenSet(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user_id,
        expires_at=expires_at,
    )


def clear(user_id: str) -> None:
    """Delete a member's saved token pair, e.g. to force a fresh login."""
    conn = _connect()
    with closing(conn), conn:
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))


def save_client(client: OAuthClientInformationFull) -> None:
    """Upsert a single DCR-registered client."""
    conn = _connect()
    with closing(conn), conn:
        conn.execute(
            """
            INSERT INTO clients (client_id, data) VALUES (?, ?)
            ON CONFLICT(client_id) DO UPDATE SET data = excluded.data
            """,
            (client.client_id, client.model_dump_json()),
        )


def load_clients() -> dict[str, OAuthClientInformationFull]:
    """Read all previously registered DCR clients, keyed by client id."""
    conn = _connect()
    with closing(conn):
        rows = conn.execute("SELECT client_id, data FROM clients").fetchall()
    return {
        client_id: OAuthClientInformationFull.model_validate_json(data) for client_id, data in rows
    }


def device_id(path: Path = DEVICE_ID_PATH) -> str:
    """Return this installation's device id, generating one on first use."""
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_id = uuid.uuid4().hex
    path.write_text(new_id)
    return new_id
