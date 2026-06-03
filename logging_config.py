from __future__ import annotations

import logging
from typing import Any


RAW_FIELD_NAMES = {"prompt", "raw_prompt", "output", "raw_output", "response", "raw_response"}


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> logging.Logger:
    level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s qicompute:%(name)s: %(message)s", force=True)
    return logging.getLogger("qicompute")


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: "[REDACTED]" if key in RAW_FIELD_NAMES else redact_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(value) for value in payload]
    return payload


def log_event(logger: logging.Logger, event: str, **metadata: Any) -> None:
    logger.info("%s %s", event, redact_payload(metadata))
