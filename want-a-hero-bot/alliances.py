"""
Alliance list manager for the Want-A-Hero bot.

Alliance names are persisted in data/alliances.json so that additions and
removals survive bot restarts.  The file is created automatically on first use,
seeded with the default alliance list.

All public functions are synchronous and safe to call from the async bot
context because file I/O on a list this small (< 1 KB) is effectively instant.
"""

import json
import os
from pathlib import Path
from typing import Optional

import config

_ALLIANCES_FILE = os.path.join(os.path.dirname(config.DB_PATH), "alliances.json")

# Shipped defaults — shown in the dropdown before any admin customisation
DEFAULT_ALLIANCES: list[str] = ["K27", "S27", "T27", "T2P"]

# Maximum length of a single alliance name
MAX_ALLIANCE_NAME_LEN = 20


# ── Internal helpers ──────────────────────────────────────────────────────────


def _path() -> Path:
    return Path(_ALLIANCES_FILE)


def _load_raw() -> list[str]:
    p = _path()
    if not p.exists():
        return []
    try:
        with p.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save(names: list[str]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename — atomic on Linux, avoids corruption
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(sorted(names), fh, indent=2, ensure_ascii=False)
    tmp.replace(p)


# ── Public API ────────────────────────────────────────────────────────────────


def get_all() -> list[str]:
    """Return the current alliance list, sorted alphabetically.

    If the file doesn't exist yet, the default list is saved and returned.
    """
    names = _load_raw()
    if not names:
        _save(DEFAULT_ALLIANCES)
        return sorted(DEFAULT_ALLIANCES)
    return names  # already sorted by _save()


def add(name: str) -> tuple[bool, str]:
    """Add an alliance name.

    Returns (True, "") on success.
    Returns (False, reason) if the name is invalid or already exists.
    """
    name = name.strip()
    if not name:
        return False, "Alliance name cannot be empty."
    if len(name) > MAX_ALLIANCE_NAME_LEN:
        return False, f"Alliance name must be {MAX_ALLIANCE_NAME_LEN} characters or fewer."

    names = get_all()
    if name.upper() in [n.upper() for n in names]:
        return False, f"**{name}** is already in the list."

    names.append(name)
    _save(names)
    return True, ""


def remove(name: str) -> tuple[bool, str]:
    """Remove an alliance by name (case-insensitive match).

    Returns (True, matched_name) on success.
    Returns (False, reason) if not found.
    """
    name = name.strip()
    names = get_all()
    match: Optional[str] = next(
        (n for n in names if n.upper() == name.upper()), None
    )
    if match is None:
        return False, f"**{name}** was not found in the list."

    names.remove(match)
    _save(names)
    return True, match


def exists(name: str) -> bool:
    """Return True if `name` is in the alliance list (case-insensitive)."""
    return any(n.upper() == name.strip().upper() for n in get_all())
