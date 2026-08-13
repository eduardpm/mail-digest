import tempfile
from datetime import date
from pathlib import Path
from unittest import TestCase

from maildigest.database import Database
from maildigest.web import render_calendar, render_day


class DatabaseAndWebTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "digest.sqlite3")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_dashboard_escapes_email_data_and_does_not_store_body(self) -> None:
        run_id = self.database.begin_run(date(2026, 8, 12))
        message = {
            "uid": "7",
            "message_id": "m7",
            "received_at": "2026-08-12T10:00:00+02:00",
            "sender": "<script>alert(1)</script>",
            "subject": "Budget <review>",
            "body": "raw private body",
        }
        result = {
            "summary": "Review quarterly budget.",
            "category": "Finance",
            "priority": "high",
            "action_items": ["Approve budget"],
        }
        self.database.save_message(run_id, message, result)
        self.database.save_digest(
            run_id,
            {
                "overview": "One important item.",
                "highlights": ["Budget review"],
                "action_items": ["Approve budget"],
                "categories": [{"name": "Finance", "count": 1, "summary": "Budget"}],
            },
        )
        self.database.complete_run(run_id, 1)

        page = render_calendar(self.database, "2026-08")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("raw private body", page)
        self.assertEqual(self.database.latest_dashboard()["run"]["email_count"], 1)  # type: ignore[index]

        detail = render_day(self.database, date(2026, 8, 12))
        self.assertIsNotNone(detail)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", detail)
        self.assertNotIn("<script>alert(1)</script>", detail)
        self.assertNotIn("raw private body", detail)
        self.assertIn("Source newsletters", detail)
        self.assertIn("Approve budget", detail)

    def test_empty_database_renders_welcome_state(self) -> None:
        self.assertIn("First edition pending", render_calendar(self.database))
