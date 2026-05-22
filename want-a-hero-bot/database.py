"""
Database layer — SQLite-backed storage for hero requests.

Schema (hero_requests):
  id                INTEGER  PRIMARY KEY AUTOINCREMENT
  discord_user_id   TEXT     NOT NULL
  discord_username  TEXT     NOT NULL
  game_name         TEXT     NOT NULL
  alliance          TEXT     NOT NULL
  hero              TEXT     NOT NULL DEFAULT ''
  medals_needed     INTEGER  NOT NULL
  universal_medals  INTEGER  (nullable)
  week_start        TEXT     NOT NULL   -- ISO date of Monday (UTC) for that MGE week
  created_at        TEXT     NOT NULL   -- ISO datetime (UTC)
  updated_at        TEXT     NOT NULL   -- ISO datetime (UTC)

Migration note:
  If the database was created before the `hero` column was added, _init_db()
  runs a safe ALTER TABLE to add it rather than requiring a manual migration.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _monday_of_week(dt: datetime) -> datetime:
    """Return the Monday 00:00 UTC of the week that `dt` falls in."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


class Database:
    def __init__(self, db_path: str = "hero_requests.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            # Create table if it doesn't exist yet
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hero_requests (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_user_id  TEXT    NOT NULL,
                    discord_username TEXT    NOT NULL,
                    game_name        TEXT    NOT NULL,
                    alliance         TEXT    NOT NULL,
                    hero             TEXT    NOT NULL DEFAULT '',
                    medals_needed    INTEGER NOT NULL,
                    universal_medals INTEGER,
                    week_start       TEXT    NOT NULL,
                    created_at       TEXT    NOT NULL,
                    updated_at       TEXT    NOT NULL
                )
                """
            )

            # Safe migration: add `hero` column to existing databases that
            # were created before this column existed.
            existing_cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(hero_requests)")
            }
            if "hero" not in existing_cols:
                conn.execute(
                    "ALTER TABLE hero_requests ADD COLUMN hero TEXT NOT NULL DEFAULT ''"
                )

            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return dict(row)

    # ── Week helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _week_start_iso(week_offset: int = 0) -> str:
        """ISO date string for the Monday of (current week + week_offset)."""
        now = _utcnow()
        monday = _monday_of_week(now) + timedelta(weeks=week_offset)
        return monday.date().isoformat()

    @staticmethod
    def get_week_label(week_offset: int = 0) -> str:
        """Human-readable label like 'Week of 2026-05-18 (Mon – Sun)'."""
        now = _utcnow()
        monday = _monday_of_week(now) + timedelta(weeks=week_offset)
        sunday = monday + timedelta(days=6)
        return (
            f"Week of {monday.strftime('%Y-%m-%d')} "
            f"({monday.strftime('%b %d')} – {sunday.strftime('%b %d')})"
        )

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_request(
        self,
        discord_user_id: str,
        discord_username: str,
        game_name: str,
        alliance: str,
        medals_needed: int,
        hero: str = "",
    ) -> int:
        """Insert a new request and return its auto-incremented ID."""
        now = _utcnow().strftime("%Y-%m-%d %H:%M:%S")
        week_start = self._week_start_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO hero_requests
                    (discord_user_id, discord_username, game_name, alliance,
                     hero, medals_needed, universal_medals,
                     week_start, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    discord_user_id,
                    discord_username,
                    game_name,
                    alliance,
                    hero,
                    medals_needed,
                    week_start,
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_request(self, request_id: int) -> Optional[dict]:
        """Return a single request by ID, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hero_requests WHERE id = ?", (request_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all_requests(self) -> list[dict]:
        """Return every request, ordered by id ascending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hero_requests ORDER BY id ASC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_requests_for_week(self, week_offset: int = 0) -> list[dict]:
        """Return requests whose week_start matches the target week."""
        week_start = self._week_start_iso(week_offset)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM hero_requests WHERE week_start = ? ORDER BY id ASC",
                (week_start,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_request(
        self,
        request_id: int,
        game_name: str,
        alliance: str,
        medals_needed: int,
        hero: str = "",
    ) -> bool:
        """Update an existing request. Returns True if a row was changed."""
        now = _utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE hero_requests
                SET game_name = ?, alliance = ?, hero = ?,
                    medals_needed = ?, updated_at = ?
                WHERE id = ?
                """,
                (game_name, alliance, hero, medals_needed, now, request_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_request(self, request_id: int) -> bool:
        """Delete a single request by ID. Returns True if deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM hero_requests WHERE id = ?", (request_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_all_requests(self) -> int:
        """Delete every request. Returns count of deleted rows."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM hero_requests")
            conn.commit()
            return cursor.rowcount
