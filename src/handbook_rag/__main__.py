"""Entry point: load settings, configure logging. Pipeline wiring comes in later phases."""

import logging

from handbook_rag.config import load_settings
from handbook_rag.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    configure_logging(
        level=settings.logging.level,
        fmt=settings.logging.format,
        log_payloads=settings.logging.log_payloads,
    )
    logger.info("app.started", extra={"log_level": settings.logging.level})


if __name__ == "__main__":
    main()
