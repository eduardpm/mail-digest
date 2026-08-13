from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta, timezone

from .config import Config
from .database import Database
from .pipeline import DigestPipeline

LOG = logging.getLogger(__name__)


def target_if_due(config: Config, database: Database, now: datetime | None = None) -> date | None:
    local_now = now.astimezone(config.timezone) if now else datetime.now(config.timezone)
    scheduled = datetime.combine(
        local_now.date(), time(config.run_hour, config.run_minute), config.timezone
    )
    if local_now < scheduled:
        return None
    target = local_now.date() - timedelta(days=1)
    run = database.run_for_date(target)
    if run is None:
        return target
    if run["status"] == "completed":
        return None
    if run["status"] == "running":
        started = datetime.fromisoformat(run["started_at"]).astimezone(timezone.utc)
        if local_now.astimezone(timezone.utc) - started < timedelta(hours=3):
            return None
        LOG.warning("Retrying stale job for %s", target)
        return target
    finished_at = run.get("finished_at")
    if not finished_at:
        return target
    finished = datetime.fromisoformat(finished_at).astimezone(timezone.utc)
    current_utc = local_now.astimezone(timezone.utc)
    if current_utc - finished >= timedelta(minutes=config.retry_minutes):
        return target
    return None


class Scheduler(threading.Thread):
    def __init__(self, config: Config, database: Database, pipeline: DigestPipeline):
        super().__init__(name="maildigest-scheduler", daemon=True)
        self.config = config
        self.database = database
        self.pipeline = pipeline
        self.stop_event = threading.Event()

    def run(self) -> None:
        LOG.info(
            "Scheduler active for %02d:%02d %s",
            self.config.run_hour,
            self.config.run_minute,
            self.config.timezone.key,
        )
        while not self.stop_event.is_set():
            try:
                target = target_if_due(self.config, self.database)
                if target:
                    self.pipeline.run(target)
            except Exception:
                LOG.exception("Scheduled job failed; it will be retried later")
            self.stop_event.wait(30)

    def stop(self) -> None:
        self.stop_event.set()
