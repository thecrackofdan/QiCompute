from __future__ import annotations

from typing import Any

import failures


DEFAULT_RETRYABLE_FAILURE_CODES = {
    failures.WORKER_TIMEOUT,
    failures.WORKER_OFFLINE,
    failures.WORKER_OVERLOADED,
    failures.TIMEOUT,
    failures.COMMAND_FAILED,
}

NON_RETRYABLE_FAILURE_CODES = {
    failures.DUPLICATE_JOB,
    failures.INVALID_ENVELOPE,
    failures.INVALID_CAPABILITY_CLAIM,
    failures.MODEL_NOT_SUPPORTED,
}


def should_retry(job: dict[str, Any], failure_code: str, config: dict[str, Any] | None = None) -> bool:
    retry_cfg = (config or {}).get("retry", {})
    max_retries = int(retry_cfg.get("max_retries", 2))
    retryable = set(retry_cfg.get("retryable_failure_codes", DEFAULT_RETRYABLE_FAILURE_CODES))
    retry_count = int(job.get("retry_count", 0) or 0)
    if failure_code in NON_RETRYABLE_FAILURE_CODES:
        return False
    return failure_code in retryable and retry_count < max_retries


def next_retry_status(job: dict[str, Any], failure_code: str, config: dict[str, Any] | None = None) -> str:
    return "retrying" if should_retry(job, failure_code, config) else "failed"
