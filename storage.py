import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "blowout_bot.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS alerted_games (
                game_pk INTEGER PRIMARY KEY,
                game_date TEXT,
                leading_team TEXT,
                trailing_team TEXT,
                lead_at_alert INTEGER,
                alerted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)


def already_alerted(game_pk: int) -> bool:
    with _conn() as c:
        row = c.execute("SELECT 1 FROM alerted_games WHERE game_pk = ?", (game_pk,)).fetchone()
        return row is not None


def mark_alerted(game_pk: int, game_date: str, leading_team: str, trailing_team: str, lead: int):
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO alerted_games "
            "(game_pk, game_date, leading_team, trailing_team, lead_at_alert) VALUES (?,?,?,?,?)",
            (game_pk, game_date, leading_team, trailing_team, lead),
        )


def set_config(key: str, value: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_config(key: str):
    with _conn() as c:
        row = c.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
