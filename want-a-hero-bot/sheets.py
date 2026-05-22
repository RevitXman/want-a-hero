"""
Google Sheets integration for the Want-A-Hero bot.

Each tab corresponds to one MGE week (Monday – Sunday UTC).
Tab names follow the pattern:  "Week 2026-05-18"

Column layout:
  A: Request ID
  B: Discord User
  C: Game Name
  D: Alliance
  E: Hero
  F: Medals Needed
  G: Selected for MGE  ← filled in manually by admins
  H: Submitted At (UTC)

The spreadsheet is identified by GOOGLE_SPREADSHEET_ID in the env.
Authentication uses a Google service-account JSON key file.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials


# Scopes required for reading/writing Sheets
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Header row written at the top of each new weekly tab
_HEADERS = [
    "Request ID",
    "Discord User",
    "Game Name",
    "Alliance",
    "Hero",
    "Medals Needed",
    "Selected for MGE",
    "Submitted At (UTC)",
]

# Column widths (pixels) set on new tabs to improve readability
_COLUMN_WIDTHS = [100, 180, 180, 130, 200, 130, 140, 190]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _monday_of_week(dt: datetime) -> datetime:
    """Return the Monday 00:00 UTC of the MGE week that `dt` falls in."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_tab_name(week_offset: int = 0) -> str:
    """Return the sheet tab name for the given week offset (0 = current)."""
    now = _utcnow()
    monday = _monday_of_week(now) + timedelta(weeks=week_offset)
    return f"Week {monday.strftime('%Y-%m-%d')}"


class SheetsManager:
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        """
        Args:
            credentials_path: Path to the Google service-account JSON key file.
            spreadsheet_id:   The ID portion of the Google Sheets URL.
        """
        creds = Credentials.from_service_account_file(
            credentials_path, scopes=_SCOPES
        )
        self._client = gspread.authorize(creds)
        self._spreadsheet_id = spreadsheet_id
        self._sheet = self._client.open_by_key(spreadsheet_id)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_or_create_tab(self, tab_name: str) -> gspread.Worksheet:
        """Return the worksheet named `tab_name`, creating it if it doesn't exist."""
        try:
            ws = self._sheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self._sheet.add_worksheet(title=tab_name, rows=500, cols=len(_HEADERS))
            self._setup_new_tab(ws)
        return ws

    def _setup_new_tab(self, ws: gspread.Worksheet) -> None:
        """Write headers and apply basic formatting to a brand-new tab."""
        # Write header row
        ws.append_row(_HEADERS, value_input_option="USER_ENTERED")

        # Bold + freeze the header row via the Sheets API (batchUpdate)
        spreadsheet = self._client.open_by_key(self._spreadsheet_id)
        sheet_id = ws.id

        requests = [
            # Bold header row
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.204,
                                "green": 0.196,
                                "blue": 0.294,
                            },
                            "foregroundColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor,foregroundColor)",
                }
            },
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]

        # Set column widths
        for col_idx, width in enumerate(_COLUMN_WIDTHS):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        spreadsheet.batch_update({"requests": requests})

    # ── Public API ────────────────────────────────────────────────────────────

    def add_request(
        self,
        request_id: int,
        discord_username: str,
        game_name: str,
        alliance: str,
        medals_needed: int,
        hero: str = "",
    ) -> None:
        """Append a hero request row to the current week's tab.

        The 'Selected for MGE' column is left blank — admins fill it manually.
        """
        tab_name = _week_tab_name()
        ws = self._get_or_create_tab(tab_name)

        now_str = _utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [
            request_id,
            discord_username,
            game_name,
            alliance,
            hero,
            medals_needed,
            "",          # Selected for MGE — filled manually by admins
            now_str,
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def get_requests_for_week(self, week_offset: int = 0) -> list[dict]:
        """Read all request rows from a weekly tab.

        Returns a list of normalised dicts with these keys (matching the DB
        schema so bot.py can use the same embed-building code for both sources):
            id, discord_username, game_name, alliance, hero,
            medals_needed, selected_for_mge, created_at

        Rows where Game Name is blank are skipped (empty / header-only rows).
        Returns [] if the tab doesn't exist yet.
        """
        tab_name = _week_tab_name(week_offset)
        try:
            ws = self._sheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            return []

        # get_all_records() uses the first row as keys and skips it automatically
        raw_rows = ws.get_all_records(
            expected_headers=_HEADERS,
            value_render_option="UNFORMATTED_VALUE",
        )

        results = []
        for row in raw_rows:
            game_name = str(row.get("Game Name", "")).strip()
            if not game_name:
                continue  # skip blank rows

            mge_val = str(row.get("Selected for MGE", "")).strip()
            results.append({
                "id":               row.get("Request ID", "—"),
                "discord_username": str(row.get("Discord User", "")).strip(),
                "game_name":        game_name,
                "alliance":         str(row.get("Alliance", "")).strip(),
                "hero":             str(row.get("Hero", "")).strip(),
                "medals_needed":    row.get("Medals Needed", 0),
                "selected_for_mge": mge_val if mge_val else None,
                "created_at":       str(row.get("Submitted At (UTC)", "")).strip(),
            })
        return results

    def ensure_next_week_tab(self) -> str:
        """
        Pre-create the tab for next week if it doesn't exist yet.
        Returns the tab name.  Call this via a scheduled task or on-demand.
        """
        tab_name = _week_tab_name(week_offset=1)
        self._get_or_create_tab(tab_name)
        return tab_name

    def get_current_week_tab_name(self) -> str:
        """Return the tab name for the current MGE week."""
        return _week_tab_name()
