"""Local persistence for a user's Xplor token pair."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path

from xplor_mcp.client import TokenSet

CONFIG_DIR = Path.home() / ".xplor-mcp"
TOKENS_PATH = CONFIG_DIR / "tokens.json"
DEVICE_ID_PATH = CONFIG_DIR / "device_id"


def save(tokens: TokenSet, path: Path = TOKENS_PATH) -> None:
    """Write the token pair to disk, creating the dotfolder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(tokens), indent=2))
    try:
        os.chmod(path, 0o600)  # no-op on Windows, meaningful on POSIX
    except OSError:
        pass


def load(path: Path = TOKENS_PATH) -> TokenSet | None:
    """Read a previously saved token pair, or None if there isn't one."""
    if not path.exists():
        return None
    return TokenSet(**json.loads(path.read_text()))


def clear(path: Path = TOKENS_PATH) -> None:
    """Delete the saved token pair, e.g. to force a fresh login."""
    path.unlink(missing_ok=True)


def device_id(path: Path = DEVICE_ID_PATH) -> str:
    """Return this installation's device id, generating one on first use."""
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_id = uuid.uuid4().hex
    path.write_text(new_id)
    return new_id
