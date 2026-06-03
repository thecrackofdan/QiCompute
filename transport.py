from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4

import failures


TIMESTAMP_HEADER = "X-Qi-Timestamp"
NONCE_HEADER = "X-Qi-Nonce"
BODY_HASH_HEADER = "X-Qi-Body-Hash"
SIGNATURE_HEADER = "X-Qi-Signature"
USED_NONCES: set[str] = set()


def canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_request(payload: Any, secret: str, *, timestamp: str | None = None, nonce: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time()))
    request_nonce = nonce or str(uuid4())
    body_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
    signature = _signature(secret, ts, request_nonce, body_hash)
    return {
        TIMESTAMP_HEADER: ts,
        NONCE_HEADER: request_nonce,
        BODY_HASH_HEADER: body_hash,
        SIGNATURE_HEADER: signature,
    }


def verify_request_signature(
    payload: Any,
    headers: dict[str, str],
    secret: str,
    *,
    max_age_seconds: int = 300,
    nonce_cache: set[str] | None = None,
) -> dict[str, Any]:
    normalized = {key.lower(): value for key, value in headers.items()}
    timestamp = normalized.get(TIMESTAMP_HEADER.lower())
    nonce = normalized.get(NONCE_HEADER.lower())
    body_hash = normalized.get(BODY_HASH_HEADER.lower())
    signature = normalized.get(SIGNATURE_HEADER.lower())
    if not timestamp or not nonce or not body_hash or not signature:
        return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "missing signature headers"}
    try:
        ts = int(timestamp)
    except ValueError:
        return {"accepted": False, "failure_code": failures.REQUEST_EXPIRED, "reason": "invalid timestamp"}
    if abs(int(time.time()) - ts) > max_age_seconds:
        return {"accepted": False, "failure_code": failures.REQUEST_EXPIRED, "reason": "timestamp outside allowed window"}
    cache = USED_NONCES if nonce_cache is None else nonce_cache
    if nonce in cache:
        return {"accepted": False, "failure_code": failures.INVALID_NONCE, "reason": "nonce already used"}
    expected_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
    if not hmac.compare_digest(body_hash, expected_hash):
        return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "body hash mismatch"}
    expected_signature = _signature(secret, timestamp, nonce, body_hash)
    if not hmac.compare_digest(signature, expected_signature):
        return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "signature mismatch"}
    cache.add(nonce)
    return {"accepted": True, "failure_code": None, "reason": "signature accepted", "metadata": {"nonce": nonce}}


def post_json(url: str, payload: Any, secret: str, timeout: float = 5) -> dict[str, Any]:
    body = canonical_json(payload)
    headers = {"Content-Type": "application/json", **sign_request(payload, secret)}
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "failure_code": failures.TRANSPORT_ERROR, "reason": str(exc)}


def get_json(url: str, payload: Any, secret: str, timeout: float = 5) -> dict[str, Any]:
    headers = sign_request(payload, secret)
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"accepted": False, "failure_code": failures.TRANSPORT_ERROR, "reason": str(exc)}


def clear_nonce_cache() -> None:
    USED_NONCES.clear()


def _signature(secret: str, timestamp: str, nonce: str, body_hash: str) -> str:
    message = f"{timestamp}.{nonce}.{body_hash}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
