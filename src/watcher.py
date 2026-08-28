"""Kontinuerlig bevakning av inboxen.

Använder enkel polling (ingen extra dependency krävs). Kör tills processen
avbryts med Ctrl+C. Lämpligt att köra i en egen terminal, tmux-session
eller som en systemd-tjänst/scheduled task lokalt.
"""
from __future__ import annotations

import logging
import time

from .config import Config
from .pipeline import Pipeline

logger = logging.getLogger(__name__)


def watch(config: Config, interval_seconds: int = 10) -> None:
    """Skannar inboxen om och om igen med `interval_seconds` mellanrum."""
    pipeline = Pipeline(config)
    logger.info(
        "Bevakar %s (var %ds). Avbryt med Ctrl+C.",
        config.paths.inbox, interval_seconds,
    )
    try:
        while True:
            stats = pipeline.process_all()
            if stats["processed"] or stats["errors"]:
                logger.info("Bearbetade: %s", stats)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("Avbryter bevakning.")
    finally:
        pipeline.close()
