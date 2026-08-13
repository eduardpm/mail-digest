from __future__ import annotations

import logging
import threading
from datetime import date

from .config import Config
from .database import Database
from .llm import OllamaSession
from .mail import ProtonBridgeReader

LOG = logging.getLogger(__name__)


class DigestPipeline:
    def __init__(self, config: Config, database: Database):
        self.config = config
        self.database = database
        self._lock = threading.Lock()

    def run(self, target: date) -> int:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("A digest job is already running")
        run_id = self.database.begin_run(target)
        try:
            LOG.info("Fetching email for %s", target)
            messages = ProtonBridgeReader(self.config).fetch_day(target)
            LOG.info("Fetched %d messages", len(messages))
            summaries: list[dict[str, object]] = []
            with OllamaSession(self.config) as model:
                for index, message in enumerate(messages, start=1):
                    LOG.info("Summarizing message %d/%d", index, len(messages))
                    result = model.summarize_email(message)
                    self.database.save_message(run_id, message, result)
                    summaries.append({**message, **result})
                digest = model.summarize_digest(summaries)
                self.database.save_digest(run_id, digest)
            self.database.complete_run(run_id, len(messages))
            LOG.info("Digest for %s completed", target)
            return run_id
        except Exception as error:
            LOG.exception("Digest for %s failed", target)
            self.database.fail_run(run_id, f"{type(error).__name__}: {error}")
            raise
        finally:
            self._lock.release()
