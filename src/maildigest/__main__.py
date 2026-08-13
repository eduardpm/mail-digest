from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import date, datetime, timedelta

from .config import Config, load_env_file
from .database import Database
from .llm import OllamaSession
from .mail import ProtonBridgeReader
from .pipeline import DigestPipeline
from .scheduler import Scheduler
from .web import create_server


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Local private email digest")
    result.add_argument("--env-file", help="Load configuration from this KEY=VALUE file")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Run the dashboard and daily scheduler")
    run = sub.add_parser("run", help="Run one digest immediately")
    run.add_argument("--date", help="Email date in YYYY-MM-DD; defaults to yesterday")
    sub.add_parser("check", help="Check configuration and Ollama connectivity")
    sub.add_parser("mailboxes", help="List mailbox names exposed by Proton Mail Bridge")
    links = sub.add_parser("refresh-links", help="Refresh saved article links without rerunning the LLM")
    links.add_argument("--date", required=True, help="Digest date in YYYY-MM-DD")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.from_env()
    database = Database(config.database_path)

    if args.command == "run":
        target = date.fromisoformat(args.date) if args.date else yesterday(config)
        DigestPipeline(config, database).run(target)
        return
    if args.command == "check":
        config.require_job_secrets()
        ProtonBridgeReader(config).check_connection()
        print("Proton Mail Bridge IMAP connection is OK")
        with OllamaSession(config) as model:
            if not model.available():
                raise RuntimeError("Ollama did not become available")
        print(f"Ollama model {config.ollama_model} is OK")
        return
    if args.command == "mailboxes":
        for mailbox in ProtonBridgeReader(config).list_mailboxes():
            print(mailbox)
        return
    if args.command == "refresh-links":
        target = date.fromisoformat(args.date)
        messages = ProtonBridgeReader(config).fetch_day(target)
        updated = database.update_links(target, messages)
        print(f"Updated article links for {updated} source messages")
        return

    pipeline = DigestPipeline(config, database)
    scheduler = Scheduler(config, database, pipeline)
    server = create_server(config, database)
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        if not stopping:
            stopping = True
            scheduler.stop()
            threading.Thread(target=server.shutdown, name="maildigest-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    scheduler.start()
    logging.info("Dashboard listening at http://%s:%d", config.host, config.port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        scheduler.stop()
        scheduler.join(timeout=5)
        server.server_close()


def yesterday(config: Config) -> date:
    return datetime.now(config.timezone).date() - timedelta(days=1)


if __name__ == "__main__":
    main()
