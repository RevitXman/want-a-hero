"""
Input sanitization helpers for the Want-A-Hero bot.

Why bother when we use parameterised SQL queries?
  • Parameterised queries already prevent SQL injection at the DB layer.
  • These helpers address a different threat surface: malformed Unicode,
    invisible control characters, and excessively long strings that could
    cause Discord embed rendering issues or abuse the Google Sheets API.
  • They also give consistent, user-friendly error messages.

Usage:
    cleaned, err = sanitize.game_name(raw_input)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return
"""

import re
from typing import Optional

# ── Length limits ─────────────────────────────────────────────────────────────

MAX_GAME_NAME_LEN = 50       # AoE Mobile display names cap around 16, be generous
MAX_ALLIANCE_NAME_LEN = 20   # Kept short — alliance tags are brief by convention
MAX_GENERIC_LEN = 100        # Fallback for any other field

# ── Patterns ──────────────────────────────────────────────────────────────────

# Control characters: C0 (0x00–0x1F), DEL (0x7F), C1 (0x80–0x9F)
# These are invisible/non-printable and have no place in a display name.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f\x80-\x9f]")

# Repeated whitespace collapser
_MULTI_SPACE = re.compile(r"\s{2,}")

# Alliance names: alphanumeric + a few safe punctuation chars only.
# No spaces — alliance tags are compact identifiers like "T2P", "K-27".
_ALLIANCE_SAFE = re.compile(r"[^A-Za-z0-9\-_]")

# Hero names: allow letters (including accented), numbers, spaces, hyphens,
# apostrophes, and periods — covers names like "Joan of Arc", "El Cid",
# "Genghis Khan", "Richard I".
_HERO_SAFE = re.compile(r"[^A-Za-z0-9À-ɏ\s\-\'\.]")

MAX_HERO_NAME_LEN = 50

# Discord mention / role ping injection — prevents @everyone, @here, <@123>
_DISCORD_MENTION = re.compile(r"@(everyone|here)|<[@#&!][0-9]+>", re.IGNORECASE)


# ── Core cleaner ──────────────────────────────────────────────────────────────


def _base_clean(text: str, max_len: int) -> str:
    """Strip control chars, normalise whitespace, and truncate."""
    text = _CONTROL_CHARS.sub("", text)
    text = _DISCORD_MENTION.sub("[filtered]", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


# ── Public validators ─────────────────────────────────────────────────────────


def game_name(raw: str) -> tuple[str, Optional[str]]:
    """Sanitize a player's in-game name.

    Returns:
        (cleaned_name, None)          — valid input
        ("", error_message)           — invalid; show error to user
    """
    if not raw or not raw.strip():
        return "", "❌ **Game name** cannot be empty."

    cleaned = _base_clean(raw, MAX_GAME_NAME_LEN)

    if not cleaned:
        return "", "❌ **Game name** contains only invalid characters. Please use a standard display name."

    # Warn if heavily truncated (more than 5 chars lost)
    # We just silently truncate — the user will see their name in the embed.
    return cleaned, None


def alliance_name(raw: str) -> tuple[str, Optional[str]]:
    """Sanitize an alliance name submitted by an admin via /hero_alliance add.

    Alliance names are short identifiers (e.g. "T2P", "K-27"); spaces and
    special characters beyond hyphens/underscores are not allowed.

    Returns:
        (cleaned_name, None)    — valid
        ("", error_message)     — invalid
    """
    if not raw or not raw.strip():
        return "", "❌ **Alliance name** cannot be empty."

    cleaned = _base_clean(raw, MAX_ALLIANCE_NAME_LEN)
    # Remove characters outside the safe set
    cleaned = _ALLIANCE_SAFE.sub("", cleaned).strip()

    if not cleaned:
        return "", (
            "❌ **Alliance name** may only contain letters, numbers, hyphens, "
            "and underscores (e.g. `S27`, `T2P`, `K-27`)."
        )
    if len(cleaned) < 2:
        return "", "❌ **Alliance name** must be at least 2 characters."

    return cleaned, None


def hero_name(raw: str) -> tuple[str, Optional[str]]:
    """Sanitize a hero name submitted by an admin via /hero_manage add.

    Hero names are proper nouns that may include spaces, accented characters,
    apostrophes, hyphens, and periods (e.g. "Joan of Arc", "El Cid").

    Returns:
        (cleaned_name, None)    — valid
        ("", error_message)     — invalid
    """
    if not raw or not raw.strip():
        return "", "❌ **Hero name** cannot be empty."

    cleaned = _base_clean(raw, MAX_HERO_NAME_LEN)
    cleaned = _HERO_SAFE.sub("", cleaned).strip()
    # Collapse any spaces left after stripping
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()

    if not cleaned:
        return "", (
            "❌ **Hero name** may only contain letters, numbers, spaces, "
            "hyphens, apostrophes, and periods."
        )
    if len(cleaned) < 2:
        return "", "❌ **Hero name** must be at least 2 characters."

    return cleaned, None


def universal_medals(value: Optional[int]) -> tuple[Optional[int], Optional[str]]:
    """Validate the optional Universal Medals count.

    Returns:
        (value_or_None, None)    — valid (None is acceptable — field is optional)
        (None, error_message)    — invalid
    """
    if value is None:
        return None, None
    if value < 0:
        return None, "❌ **Universal Medals** cannot be negative."
    if value > 99_999:
        return None, "❌ **Universal Medals** value seems unrealistically large. Please double-check."
    return value, None
