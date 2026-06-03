from __future__ import annotations

import logging
from typing import Any

from privacy import redact_sensitive_fields


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> logging.Logger:
    level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s qicompute:%(name)s: %(message)s", force=True)
    return logging.getLogger("qicompute")


def redact_payload(payload: Any) -> Any:
    return redact_sensitive_fields(payload)


def log_event(logger: logging.Logger, event: str, **metadata: Any) -> None:
    logger.info("%s %s", event, redact_payload(metadata))
