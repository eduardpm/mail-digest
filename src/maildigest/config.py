from __future__ import annotations

import os
import shlex
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def load_env_file(path: str | Path) -> None:
    """Load a small systemd-style KEY=VALUE file without overriding the shell."""
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(env_path)
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    database_path: Path
    timezone: ZoneInfo
    run_hour: int
    run_minute: int
    retry_minutes: int
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    imap_mailbox: str
    imap_security: str
    imap_verify_tls: bool
    ollama_url: str
    ollama_model: str
    ollama_command: tuple[str, ...]
    ollama_start_timeout: int
    llm_timeout: int
    max_emails: int
    max_body_chars: int
    max_digest_chars: int

    @classmethod
    def from_env(cls) -> "Config":
        root = Path(os.getenv("MAILDIGEST_ROOT", Path.cwd())).resolve()
        config = cls(
            host=os.getenv("MAILDIGEST_HOST", "127.0.0.1"),
            port=_int("MAILDIGEST_PORT", 8765),
            database_path=Path(
                os.getenv("MAILDIGEST_DATABASE", root / "data" / "maildigest.sqlite3")
            ).expanduser().resolve(),
            timezone=ZoneInfo(os.getenv("MAILDIGEST_TIMEZONE", "Europe/Brussels")),
            run_hour=_int("MAILDIGEST_RUN_HOUR", 5),
            run_minute=_int("MAILDIGEST_RUN_MINUTE", 0),
            retry_minutes=_int("MAILDIGEST_RETRY_MINUTES", 30),
            imap_host=os.getenv("MAILDIGEST_IMAP_HOST", "127.0.0.1"),
            imap_port=_int("MAILDIGEST_IMAP_PORT", 1143),
            imap_username=os.getenv("MAILDIGEST_IMAP_USERNAME", ""),
            imap_password=os.getenv("MAILDIGEST_IMAP_PASSWORD", ""),
            imap_mailbox=os.getenv("MAILDIGEST_IMAP_MAILBOX", "INBOX"),
            imap_security=os.getenv("MAILDIGEST_IMAP_SECURITY", "starttls").lower(),
            imap_verify_tls=_bool("MAILDIGEST_IMAP_VERIFY_TLS", False),
            ollama_url=os.getenv("MAILDIGEST_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("MAILDIGEST_OLLAMA_MODEL", "qwen3:4b"),
            ollama_command=tuple(shlex.split(os.getenv("MAILDIGEST_OLLAMA_COMMAND", "ollama serve"))),
            ollama_start_timeout=_int("MAILDIGEST_OLLAMA_START_TIMEOUT", 180),
            llm_timeout=_int("MAILDIGEST_LLM_TIMEOUT", 600),
            max_emails=_int("MAILDIGEST_MAX_EMAILS", 200),
            max_body_chars=_int("MAILDIGEST_MAX_BODY_CHARS", 12_000),
            max_digest_chars=_int("MAILDIGEST_MAX_DIGEST_CHARS", 24_000),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("MAILDIGEST_PORT must be between 1 and 65535")
        if not 0 <= self.run_hour <= 23 or not 0 <= self.run_minute <= 59:
            raise ValueError("The configured run time is invalid")
        if self.imap_security not in {"starttls", "ssl", "plain"}:
            raise ValueError("MAILDIGEST_IMAP_SECURITY must be starttls, ssl, or plain")
        parsed = urlparse(self.ollama_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MAILDIGEST_OLLAMA_URL must be an HTTP(S) URL")
        if not self.ollama_command:
            raise ValueError("MAILDIGEST_OLLAMA_COMMAND cannot be empty")
        if not self.imap_verify_tls:
            try:
                is_loopback = ipaddress.ip_address(self.imap_host).is_loopback
            except ValueError:
                is_loopback = self.imap_host == "localhost"
            if not is_loopback:
                raise ValueError("TLS verification may only be disabled for a loopback IMAP host")

    def require_job_secrets(self) -> None:
        missing = []
        if not self.imap_username:
            missing.append("MAILDIGEST_IMAP_USERNAME")
        if not self.imap_password:
            missing.append("MAILDIGEST_IMAP_PASSWORD")
        if missing:
            raise RuntimeError("Missing job configuration: " + ", ".join(missing))
