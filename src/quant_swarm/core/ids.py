"""Id helpers — short, prefixed, roughly time-sortable identifiers."""

from __future__ import annotations

import secrets
import time


def new_id(prefix: str) -> str:
    """Return e.g. ``ord_1a2b3c4d5e6f7a8b``.

    Millisecond timestamp (hex) + 8 random hex chars; sortable by creation
    time within the same prefix, unique enough for a single-node system.
    """
    return f"{prefix}_{int(time.time() * 1000):x}{secrets.token_hex(4)}"
