from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any


SENSITIVE_FIELD_NAMES = {
    "prompt",
    "raw_prompt",
    "output",
    "raw_output",
    "response",
    "raw_response",
    "decrypted_payload",
    "private_key",
    "ephemeral_key",
    "ephemeral_job_key",
    "payload_key",
    "shared_secret",
    "worker_secret",
    "secret",
    "stderr",
    "stdout",
}


def privacy_defaults() -> dict[str, Any]:
    return {
        "mode": "strict",
        "store_raw_prompts": False,
        "store_raw_outputs": False,
        "encrypt_job_payloads": True,
        "controller_blind_prompts": True,
        "zero_retention_runtime": True,
        "allow_debug_prompt_logging": False,
    }


def effective_privacy_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = privacy_defaults()
    if config:
        cfg.update(config.get("privacy", config))
    if cfg.get("mode", "strict") == "strict":
        cfg.setdefault("store_raw_prompts", False)
        cfg.setdefault("store_raw_outputs", False)
        cfg.setdefault("encrypt_job_payloads", True)
        cfg.setdefault("controller_blind_prompts", True)
        cfg.setdefault("zero_retention_runtime", True)
        cfg.setdefault("allow_debug_prompt_logging", False)
    return cfg


def make_private_job_payload(prompt: str, metadata: dict[str, Any] | None, privacy_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a local prototype encrypted payload envelope.

    This is intentionally standard-library-only placeholder encryption for local
    architecture testing. It is not audited cryptography and should be replaced
    before WAN or production use.
    """
    cfg = effective_privacy_config(privacy_config)
    nonce = secrets.token_urlsafe(16)
    key = secrets.token_urlsafe(32)
    clear_payload = {"prompt": prompt, "metadata": redact_sensitive_fields(metadata or {})}
    encoded = json.dumps(clear_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = _xor_stream(encoded, key, nonce) if cfg.get("encrypt_job_payloads", True) else encoded
    encrypted_payload = base64.urlsafe_b64encode(ciphertext).decode("ascii")
    return {
        "encrypted_payload": encrypted_payload,
        "payload_nonce": nonce,
        "payload_hash": payload_hash({"encrypted_payload": encrypted_payload, "payload_nonce": nonce}),
        "privacy_mode": cfg.get("mode", "strict"),
        "payload_key": key,
        "encryption": "local-prototype-xor-sha256",
    }


def decrypt_private_job_payload(payload: dict[str, Any], key: str, privacy_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = effective_privacy_config(privacy_config)
    encrypted = payload.get("encrypted_payload")
    nonce = payload.get("payload_nonce")
    if not encrypted or not nonce:
        raise ValueError("private payload requires encrypted_payload and payload_nonce")
    ciphertext = base64.urlsafe_b64decode(str(encrypted).encode("ascii"))
    clear = _xor_stream(ciphertext, key, str(nonce)) if cfg.get("encrypt_job_payloads", True) else ciphertext
    decoded = json.loads(clear.decode("utf-8"))
    return {"prompt": decoded.get("prompt", ""), "metadata": decoded.get("metadata", {})}


def redact_private_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clone = redact_sensitive_fields(payload)
    for key in ("payload_key", "ephemeral_key", "ephemeral_job_key", "private_key"):
        clone.pop(key, None)
    return clone


def payload_hash(payload: Any) -> str:
    redacted = redact_private_payload(payload) if isinstance(payload, dict) else payload
    encoded = json.dumps(redacted, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_sensitive_fields(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: redact_sensitive_fields(value) for key, value in obj.items() if not _is_sensitive_field(key)}
    if isinstance(obj, list):
        return [redact_sensitive_fields(value) for value in obj]
    return obj


def extract_runtime_prompt(job: dict[str, Any], config: dict[str, Any]) -> str:
    privacy_cfg = effective_privacy_config(config)
    if job.get("prompt"):
        return str(job.get("prompt", ""))
    key = job.get("payload_key") or job.get("metadata", {}).get("payload_key")
    if key and job.get("encrypted_payload"):
        return str(decrypt_private_job_payload(job, str(key), privacy_cfg).get("prompt", ""))
    if job.get("prompt") and not privacy_cfg.get("controller_blind_prompts", True):
        return str(job.get("prompt", ""))
    return ""


def _is_sensitive_field(key: str) -> bool:
    normalized = key.lower()
    return normalized in SENSITIVE_FIELD_NAMES or normalized.endswith("_secret")


def _xor_stream(data: bytes, key: str, nonce: str) -> bytes:
    key_bytes = str(key).encode("utf-8")
    nonce_bytes = str(nonce).encode("utf-8")
    output = bytearray()
    counter = 0
    while len(output) < len(data):
        block = hashlib.sha256(key_bytes + nonce_bytes + counter.to_bytes(8, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(value ^ mask for value, mask in zip(data, output))
