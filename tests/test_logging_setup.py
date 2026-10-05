"""configure_logging is tested with explicit arguments only: no config.yaml, no env."""

import io
import json
import logging
from collections.abc import Iterator

import pytest

from handbook_rag.logging_setup import REDACTED, configure_logging, request_context

logger = logging.getLogger("handbook_rag.test")


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    yield buf
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _lines(buf: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buf.getvalue().splitlines()]


def test_json_line_has_base_fields_and_extras(stream: io.StringIO) -> None:
    configure_logging(level="INFO", fmt="json", log_payloads=False, stream=stream)

    logger.info("retrieval.completed", extra={"source": "bm25", "k": 5, "latency_ms": 12})

    [line] = _lines(stream)
    assert line["level"] == "INFO"
    assert line["logger"] == "handbook_rag.test"
    assert line["event"] == "retrieval.completed"
    assert line["request_id"] is None
    assert str(line["ts"]).endswith("Z")
    assert (line["source"], line["k"], line["latency_ms"]) == ("bm25", 5, 12)


def test_request_id_is_bound_inside_context_only(stream: io.StringIO) -> None:
    configure_logging(level="INFO", fmt="json", log_payloads=False, stream=stream)

    with request_context("req-123"):
        logger.info("request.received")
    logger.info("request.completed")

    first, second = _lines(stream)
    assert first["request_id"] == "req-123"
    assert second["request_id"] is None


def test_payload_fields_redacted_unless_enabled(stream: io.StringIO) -> None:
    configure_logging(level="DEBUG", fmt="json", log_payloads=False, stream=stream)
    logger.debug("query.rewritten", extra={"question": "salary?", "rewritten_chars": 7})

    configure_logging(level="DEBUG", fmt="json", log_payloads=True, stream=stream)
    logger.debug("query.rewritten", extra={"question": "salary?", "rewritten_chars": 7})

    redacted, visible = _lines(stream)
    assert redacted["question"] == REDACTED
    assert redacted["rewritten_chars"] == 7
    assert visible["question"] == "salary?"


def test_level_filters_records(stream: io.StringIO) -> None:
    configure_logging(level="WARNING", fmt="json", log_payloads=False, stream=stream)

    logger.info("dropped")
    logger.warning("llm.retry", extra={"attempt": 2})

    assert [line["event"] for line in _lines(stream)] == ["llm.retry"]


def test_reconfigure_does_not_duplicate_handlers(stream: io.StringIO) -> None:
    configure_logging(level="INFO", fmt="json", log_payloads=False, stream=stream)
    configure_logging(level="INFO", fmt="json", log_payloads=False, stream=stream)

    logger.info("once")

    assert len(_lines(stream)) == 1


def test_exception_adds_stack_trace(stream: io.StringIO) -> None:
    configure_logging(level="INFO", fmt="json", log_payloads=False, stream=stream)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("request.failed", extra={"stage": "retrieval"})

    [line] = _lines(stream)
    assert line["level"] == "ERROR"
    assert "ValueError: boom" in str(line["stack_trace"])


def test_console_format_is_readable(stream: io.StringIO) -> None:
    configure_logging(level="INFO", fmt="console", log_payloads=False, stream=stream)

    with request_context("req-9"):
        logger.info("rerank.completed", extra={"output_n": 3})

    out = stream.getvalue()
    assert "INFO" in out
    assert "[req-9] rerank.completed output_n=3" in out
