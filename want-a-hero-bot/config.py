"""
Central configuration for the Want-A-Hero bot.
All values are read from environment variables (loaded via python-dotenv).
"""

import os


def _int_env(key: str, default: int) -> int:
    """Read an integer env var, safely stripping any trailing inline comments.

    python-dotenv does NOT strip inline comments, so a line like:
        LOG_MAX_BYTES=5242880   # 5 MB per file
    produces the raw string '5242880   # 5 MB per file'.
    This helper splits on '#' and strips whitespace before converting.
    """
    raw = os.getenv(key, str(default))
    return int(raw.split("#")[0].strip())


# ── Discord ───────────────────────────────────────────────────────────────────

# The Discord role name that grants admin access to hero commands.
ADMIN_ROLE_NAME: str = os.getenv("ADMIN_ROLE_NAME", "Hero Admin")

# Your Discord server (guild) ID — enables instant slash-command sync.
# Right-click your server icon in Discord → Copy Server ID (needs Developer Mode on).
# Leave blank to use slow global sync (up to 1 hour to appear).
_guild_id_raw = os.getenv("GUILD_ID", "").split("#")[0].strip()
GUILD_ID: int | None = int(_guild_id_raw) if _guild_id_raw else None


# ── Database ──────────────────────────────────────────────────────────────────

# Path to the SQLite database file on disk.
DB_PATH: str = os.getenv("DB_PATH", "data/hero_requests.db")


# ── Logging ───────────────────────────────────────────────────────────────────

# Directory where rotating log files are stored.
LOG_DIR: str = os.getenv("LOG_DIR", "logs")

# Maximum size (bytes) of a single log file before it rotates.
LOG_MAX_BYTES: int = _int_env("LOG_MAX_BYTES", 5 * 1024 * 1024)  # 5 MB

# Number of rotated backup files to keep.
LOG_BACKUP_COUNT: int = _int_env("LOG_BACKUP_COUNT", 7)


# ── Google Sheets ─────────────────────────────────────────────────────────────

# Set to "true" to enable Google Sheets sync; anything else disables it.
GOOGLE_SHEETS_ENABLED: bool = (
    os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
)

# Path to the downloaded service-account JSON key file.
GOOGLE_CREDENTIALS_PATH: str = os.getenv(
    "GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json"
)

# The long ID string from the Google Sheets URL:
#   https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
