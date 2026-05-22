"""
Hero list manager for the Want-A-Hero bot.

Hero names are persisted to data/heroes.json so additions and removals
survive bot restarts.  The file is created automatically on first use,
seeded with a starter list of Age of Empires Mobile heroes.

All public functions are synchronous and safe to call from async context.
"""

import json
import os
from pathlib import Path
from typing import Optional

import config

_HEROES_FILE = os.path.join(os.path.dirname(config.DB_PATH), "heroes.json")

# Starter list — edit freely via /hero_manage add / remove
DEFAULT_HEROES: list[str] = [
    "Alexander the Great",
    "Cao Cao",
    "Charlemagne",
    "El Cid",
    "Genghis Khan",
    "Hannibal Barca",
    "Joan of Arc",
    "Julius Caesar",
    "Richard I",
    "Saladin",
]

MAX_HERO_NAME_LEN = 50


# ── Internal helpers ──────────────────────────────────────────────────────────


def _path() -> Path:
    return Path(_HEROES_FILE)


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
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(sorted(names, key=str.casefold), fh, indent=2, ensure_ascii=False)
    tmp.replace(p)


# ── Public API ────────────────────────────────────────────────────────────────


def get_all() -> list[str]:
    """Return the current hero list, sorted alphabetically (case-insensitive).

    If the file doesn't exist yet the default list is saved and returned.
    """
    names = _load_raw()
    if not names:
        _save(DEFAULT_HEROES)
        return sorted(DEFAULT_HEROES, key=str.casefold)
    return names  # already sorted by _save()


def add(name: str) -> tuple[bool, str]:
    """Add a hero name.

    Returns (True, "") on success.
    Returns (False, reason) if the name is invalid or already exists.
    """
    name = name.strip()
    if not name:
        return False, "Hero name cannot be empty."
    if len(name) > MAX_HERO_NAME_LEN:
        return False, f"Hero name must be {MAX_HERO_NAME_LEN} characters or fewer."

    names = get_all()
    if name.casefold() in [n.casefold() for n in names]:
        return False, f"**{name}** is already in the hero list."

    names.append(name)
    _save(names)
    return True, ""


def remove(name: str) -> tuple[bool, str]:
    """Remove a hero by name (case-insensitive match).

    Returns (True, matched_name) on success.
    Returns (False, reason) if not found.
    """
    name = name.strip()
    names = get_all()
    match: Optional[str] = next(
        (n for n in names if n.casefold() == name.casefold()), None
    )
    if match is None:
        return False, f"**{name}** was not found in the hero list."

    names.remove(match)
    _save(names)
    return True, match


def exists(name: str) -> bool:
    """Return True if `name` matches a hero in the list (case-insensitive)."""
    return any(n.casefold() == name.strip().casefold() for n in get_all())
