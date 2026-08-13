import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase

from maildigest.database import Database
from maildigest.scheduler import target_if_due

from .helpers import config_for


class SchedulerTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "digest.sqlite3"
        self.config = config_for(db_path)
        self.database = Database(db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_waits_until_five_and_targets_previous_day(self) -> None:
        before = datetime(2026, 8, 13, 4, 59, tzinfo=self.config.timezone)
        after = datetime(2026, 8, 13, 5, 0, tzinfo=self.config.timezone)
        self.assertIsNone(target_if_due(self.config, self.database, before))
        self.assertEqual(target_if_due(self.config, self.database, after), date(2026, 8, 12))

    def test_completed_job_is_not_repeated(self) -> None:
        target = date(2026, 8, 12)
        run_id = self.database.begin_run(target)
        self.database.complete_run(run_id, 0)
        now = datetime(2026, 8, 13, 6, 0, tzinfo=self.config.timezone)
        self.assertIsNone(target_if_due(self.config, self.database, now))

    def test_stale_running_job_is_retried(self) -> None:
        target = date(2026, 8, 12)
        self.database.begin_run(target)
        with self.database.connect() as db:
            db.execute(
                "UPDATE runs SET started_at=? WHERE digest_date=?",
                ((datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)).isoformat(), target.isoformat()),
            )
        now = datetime(2026, 8, 13, 6, 0, tzinfo=self.config.timezone)
        self.assertEqual(target_if_due(self.config, self.database, now), target)
