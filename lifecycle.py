QUEUED = "queued"
ROUTED = "routed"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
REJECTED = "rejected"
EXPIRED = "expired"
RETRYING = "retrying"

TERMINAL_STATES = {COMPLETED, REJECTED, EXPIRED}

VALID_TRANSITIONS = {
    QUEUED: {ROUTED, REJECTED, EXPIRED},
    ROUTED: {RUNNING, EXPIRED, FAILED},
    RUNNING: {COMPLETED, FAILED, EXPIRED},
    FAILED: {RETRYING},
    RETRYING: {ROUTED, FAILED, EXPIRED},
    COMPLETED: set(),
    REJECTED: set(),
    EXPIRED: set(),
}


def transition_job_status(current_status: str, next_status: str) -> bool:
    return next_status in VALID_TRANSITIONS.get(current_status, set())
