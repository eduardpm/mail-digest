from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from maildigest.config import Config


def config_for(path: Path, **overrides: object) -> Config:
    values: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8765,
        "database_path": path,
        "timezone": ZoneInfo("Europe/Brussels"),
        "run_hour": 5,
        "run_minute": 0,
        "retry_minutes": 30,
        "imap_host": "127.0.0.1",
        "imap_port": 1143,
        "imap_username": "bridge-user",
        "imap_password": "bridge-password",
        "imap_mailbox": "INBOX",
        "imap_security": "starttls",
        "imap_verify_tls": False,
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "qwen3:4b",
        "ollama_command": ("ollama", "serve"),
        "ollama_start_timeout": 2,
        "llm_timeout": 2,
        "max_emails": 200,
        "max_body_chars": 12_000,
        "max_digest_chars": 24_000,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]
