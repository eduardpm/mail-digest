from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    digest_date TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    email_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    imap_uid TEXT NOT NULL,
    message_id TEXT,
    received_at TEXT,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    summary TEXT NOT NULL,
    action_items_json TEXT NOT NULL DEFAULT '[]',
    links_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(run_id, imap_uid)
);

CREATE TABLE IF NOT EXISTS digests (
    run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    overview TEXT NOT NULL,
    highlights_json TEXT NOT NULL DEFAULT '[]',
    action_items_json TEXT NOT NULL DEFAULT '[]',
    categories_json TEXT NOT NULL DEFAULT '[]',
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_run_id_idx ON messages(run_id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "links_json" not in columns:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN links_json TEXT NOT NULL DEFAULT '[]'"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def begin_run(self, digest_date: date) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO runs(digest_date, status, started_at)
                VALUES (?, 'running', ?)
                ON CONFLICT(digest_date) DO UPDATE SET
                    status='running', attempts=runs.attempts + 1,
                    started_at=excluded.started_at, finished_at=NULL, error=NULL
                """,
                (digest_date.isoformat(), now),
            )
            row = db.execute(
                "SELECT id FROM runs WHERE digest_date=?", (digest_date.isoformat(),)
            ).fetchone()
            assert row is not None
            run_id = int(row["id"])
            db.execute("DELETE FROM messages WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM digests WHERE run_id=?", (run_id,))
            return run_id

    def complete_run(self, run_id: int, email_count: int) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status='completed', finished_at=?, email_count=?, error=NULL WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), email_count, run_id),
            )

    def fail_run(self, run_id: int, error: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), error[:2000], run_id),
            )

    def save_message(self, run_id: int, message: dict[str, Any], result: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO messages(
                    run_id, imap_uid, message_id, received_at, sender, subject,
                    category, priority, summary, action_items_json, links_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    message["uid"],
                    message.get("message_id"),
                    message.get("received_at"),
                    message["sender"],
                    message["subject"],
                    result["category"],
                    result["priority"],
                    result["summary"],
                    json.dumps(result["action_items"], ensure_ascii=False),
                    json.dumps(message.get("links", []), ensure_ascii=False),
                ),
            )

    def save_digest(self, run_id: int, digest: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO digests(
                    run_id, overview, highlights_json, action_items_json,
                    categories_json, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    digest["overview"],
                    json.dumps(digest["highlights"], ensure_ascii=False),
                    json.dumps(digest["action_items"], ensure_ascii=False),
                    json.dumps(digest["categories"], ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def update_links(self, digest_date: date, messages: list[dict[str, Any]]) -> int:
        with self.connect() as db:
            run = db.execute(
                "SELECT id FROM runs WHERE digest_date=? AND status='completed'",
                (digest_date.isoformat(),),
            ).fetchone()
            if run is None:
                raise RuntimeError(f"No completed digest exists for {digest_date}")
            updated = 0
            for message in messages:
                cursor = db.execute(
                    "UPDATE messages SET links_json=? WHERE run_id=? AND imap_uid=?",
                    (
                        json.dumps(message.get("links", []), ensure_ascii=False),
                        run["id"],
                        message["uid"],
                    ),
                )
                updated += cursor.rowcount
            return updated

    def run_for_date(self, digest_date: date) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM runs WHERE digest_date=?", (digest_date.isoformat(),)
            ).fetchone()
            return dict(row) if row else None

    def latest_dashboard(self) -> dict[str, Any] | None:
        with self.connect() as db:
            run = db.execute(
                "SELECT * FROM runs WHERE status='completed' ORDER BY digest_date DESC LIMIT 1"
            ).fetchone()
            if run is None:
                return None
            return self._dashboard_from_run(db, run)

    def dashboard_for_date(self, digest_date: date) -> dict[str, Any] | None:
        with self.connect() as db:
            run = db.execute(
                "SELECT * FROM runs WHERE status='completed' AND digest_date=?",
                (digest_date.isoformat(),),
            ).fetchone()
            if run is None:
                return None
            return self._dashboard_from_run(db, run)

    @staticmethod
    def _dashboard_from_run(
        db: sqlite3.Connection, run: sqlite3.Row
    ) -> dict[str, Any]:
        digest = db.execute("SELECT * FROM digests WHERE run_id=?", (run["id"],)).fetchone()
        messages = db.execute(
            """SELECT * FROM messages WHERE run_id=?
               ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id""",
            (run["id"],),
        ).fetchall()
        return {
            "run": dict(run),
            "digest": {
                **dict(digest),
                "highlights": json.loads(digest["highlights_json"]),
                "action_items": json.loads(digest["action_items_json"]),
                "categories": json.loads(digest["categories_json"]),
            } if digest else None,
            "messages": [
                {
                    **dict(row),
                    "action_items": json.loads(row["action_items_json"]),
                    "links": json.loads(row["links_json"]),
                }
                for row in messages
            ],
        }

    def calendar_month(self, year: int, month: int) -> list[dict[str, Any]]:
        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT r.digest_date, r.status, r.email_count, d.overview, d.highlights_json
                FROM runs r LEFT JOIN digests d ON d.run_id=r.id
                WHERE r.digest_date >= ? AND r.digest_date < ?
                ORDER BY r.digest_date
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "highlights": json.loads(row["highlights_json"]) if row["highlights_json"] else [],
                }
                for row in rows
            ]

    def adjacent_completed_dates(self, digest_date: date) -> tuple[str | None, str | None]:
        value = digest_date.isoformat()
        with self.connect() as db:
            previous = db.execute(
                "SELECT MAX(digest_date) AS value FROM runs WHERE status='completed' AND digest_date < ?",
                (value,),
            ).fetchone()["value"]
            following = db.execute(
                "SELECT MIN(digest_date) AS value FROM runs WHERE status='completed' AND digest_date > ?",
                (value,),
            ).fetchone()["value"]
            return previous, following

    def recent_runs(self, limit: int = 14) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM runs ORDER BY digest_date DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
