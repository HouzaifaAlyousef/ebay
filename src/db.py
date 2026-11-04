"""SQLite-Speicher: merkt sich gesehene Anzeigen, damit nichts doppelt bearbeitet wird."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class DB:
    def __init__(self, path: str = "listings.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                ad_id       TEXT PRIMARY KEY,
                url         TEXT,
                title       TEXT,
                price       TEXT,
                location    TEXT,
                status      TEXT,        -- filtered_out | rejected | ready | sent | error
                score       INTEGER,
                reasons     TEXT,
                message     TEXT,
                created_at  TEXT
            )
            """
        )
        self.conn.commit()

    def seen(self, ad_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM listings WHERE ad_id = ?", (ad_id,))
        return cur.fetchone() is not None

    def save(self, ad_id, url, title, price, location, status,
             score=None, reasons="", message=""):
        self.conn.execute(
            """
            INSERT OR REPLACE INTO listings
            (ad_id, url, title, price, location, status, score, reasons, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ad_id, url, title, price, location, status, score, reasons, message,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def ready_messages(self):
        """Alle vorbereiteten (semi-auto) Nachrichten zum Abschicken."""
        cur = self.conn.execute(
            "SELECT * FROM listings WHERE status = 'ready' ORDER BY score DESC"
        )
        return cur.fetchall()

    def close(self):
        self.conn.close()
