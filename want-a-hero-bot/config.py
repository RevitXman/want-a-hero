"""
Central configuration for the Want-A-Hero bot.
All values are read from environment variables (loaded via python-dotenv).
"""

import os


# ── Discord ───────────────────────────────────────────────────────────────────

# The Discord role name that grants admin access to hero commands.
ADMIN_ROLE_NAME: str = os.getenv("ADMIN_ROLE_NAME", "Hero Admin")


# ── Database ──────────────────────────────────────────────────────────────────

# Path to the SQLite database file on disk.
DB_PATH: str = os.getenv("DB_PATH", "data/hero_requests.db")


# ── Logging ───────────────────────────────────────────────────────────────────

# Directory where rotating log files are stored.
LOG_DIR: str = os.getenv("LOG_DIR", "logs")

# Maximum size (bytes) of a single log file before it rotates.
LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB

# Number of rotated backup files to keep.
LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "7"))


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
