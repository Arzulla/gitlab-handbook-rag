"""Structured logging: one JSON object per line to stdout, with a per-request id.

Java analogy: SLF4J + MDC -> stdlib `logging` + `contextvars`.

Usage:
    logger = logging.getLogger(__name__)
    logger.info("retrieval.completed", extra={"source": "bm25", "k": 5, "latency_ms": 12})

The log message IS the `event` name (`noun.verb_past`); all other data goes in `extra`.
This module must not import `config.py`: callers pass values in explicitly.
"""

import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal, TextIO

LogFormat = Literal["json", "console"]

# Fields that may carry user/document text. Redacted unless `log_payloads=True` (§7).
PAYLOAD_FIELDS = frozenset({"question", "rewritten_query", "prompt", "completion", "chunk_text"})
REDACTED = "<redacted>"

_HANDLER_NAME = "handbook_rag"

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_RECORD_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Bind a request id to every log line emitted inside the block (like MDC.put/remove)."""
    rid = request_id or uuid.uuid4().hex
    token = request_id_var.set(rid)
    try:
        yield rid
    finally:
        request_id_var.reset(token)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _RECORD_ATTRS and k != "request_id"}


class _ContextFilter(logging.Filter):
    """Attaches `request_id` and redacts payload fields. Never drops records."""

    def __init__(self, log_payloads: bool) -> None:
        super().__init__()
        self._log_payloads = log_payloads

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        if not self._log_payloads:
            for name in PAYLOAD_FIELDS.intersection(vars(record)):
                setattr(record, name, REDACTED)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            **_extra_fields(record),
        }
        if record.exc_info:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable dev format: `ts LEVEL logger [request_id] event key=value ...`."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S.%f")[:-3]
        rid = getattr(record, "request_id", None) or "-"
        extras = " ".join(f"{k}={v}" for k, v in _extra_fields(record).items())
        line = f"{ts} {record.levelname:<7} {record.name} [{rid}] {record.getMessage()}"
        if extras:
            line = f"{line} {extras}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(
    level: str,
    fmt: LogFormat,
    log_payloads: bool,
    stream: TextIO | None = None,
) -> None:
    """Install a single stdout handler on the root logger. Safe to call more than once."""
    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.name == _HANDLER_NAME]:
        root.removeHandler(existing)

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())
    handler.addFilter(_ContextFilter(log_payloads))

    root.addHandler(handler)
    root.setLevel(level.upper())
