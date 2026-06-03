from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

import failures
from receipts import utc_now_iso


@dataclass(frozen=True)
class RuntimeResult:
    job_id: str
    worker_id: str
    model: str
    started_at: str
    ended_at: str
    duration_seconds: float
    input_tokens: float
    output_tokens: float
    output_hash: str
    exit_code: int | None
    accepted: bool
    error_code: str | None
    error_message: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BaseRuntime:
    runtime_type = "base"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        raise NotImplementedError

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        raise NotImplementedError


class SimulatedRuntime(BaseRuntime):
    runtime_type = "simulated"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        return job.get("model") in worker.get("supported_models", [job.get("model")])

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        started = utc_now_iso()
        start_time = time.monotonic()
        seconds = float(job.get("seconds", config.get("runtime", {}).get("simulated_seconds", 0.001)))
        if seconds > 0:
            time.sleep(seconds)
        output_tokens = float(job.get("expected_output_tokens", job.get("output_tokens", 0)) or 0)
        output_hash = _hash_text(_stable_output(job, output_tokens))
        duration = time.monotonic() - start_time
        return _runtime_result(
            job=job,
            config=config,
            started_at=started,
            duration_seconds=duration,
            output_tokens=output_tokens,
            output_hash=output_hash,
            exit_code=0,
            accepted=True,
            error_code=None,
            error_message=None,
            metadata={"simulated": True},
        )


class SubprocessRuntime(BaseRuntime):
    runtime_type = "subprocess"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        return True

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        runtime_cfg = config.get("runtime", {})
        command = job.get("runtime_command") or runtime_cfg.get("command")
        if isinstance(command, str):
            raise ValueError("Runtime command must be an argument list, not a shell string")
        if not isinstance(command, list) or not command:
            raise ValueError("Runtime command must be a non-empty argument list")
        if not all(isinstance(part, str) for part in command):
            raise ValueError("Runtime command arguments must be strings")

        started = utc_now_iso()
        start_time = time.monotonic()
        timeout = float(job.get("timeout_seconds", runtime_cfg.get("timeout_seconds", 300)))
        try:
            completed = subprocess.run(
                command,
                shell=False,
                check=False,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            accepted = completed.returncode == 0
            error_code = None if accepted else failures.COMMAND_FAILED
            error_message = None if accepted else _redact_text(stderr or f"exit code {completed.returncode}")
            output_hash = _hash_text(stdout)
            output_tokens = float(job.get("expected_output_tokens", _count_tokens(stdout)))
            exit_code = completed.returncode
            metadata = {
                "stdout_bytes": len(stdout.encode("utf-8")),
                "stderr_bytes": len(stderr.encode("utf-8")),
            }
        except subprocess.TimeoutExpired as exc:
            accepted = False
            error_code = failures.WORKER_TIMEOUT
            error_message = f"runtime timed out after {timeout} seconds"
            output_hash = _hash_text(exc.stdout or "")
            output_tokens = 0.0
            exit_code = None
            metadata = {"timeout_seconds": timeout}

        duration = time.monotonic() - start_time
        return _runtime_result(
            job=job,
            config=config,
            started_at=started,
            duration_seconds=duration,
            output_tokens=output_tokens,
            output_hash=output_hash,
            exit_code=exit_code,
            accepted=accepted,
            error_code=error_code,
            error_message=error_message,
            metadata=metadata,
        )


class OllamaRuntime(BaseRuntime):
    runtime_type = "ollama"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        return True

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        runtime_cfg = config.get("runtime", {})
        url = runtime_cfg.get("ollama_url", "http://127.0.0.1:11434/api/generate")
        model = runtime_cfg.get("ollama_model") or job.get("model")
        prompt = job.get("prompt", "")
        timeout = float(job.get("timeout_seconds", runtime_cfg.get("timeout_seconds", 300)))
        started = utc_now_iso()
        start_time = time.monotonic()

        if not url or not model:
            return _runtime_result(
                job=job,
                config=config,
                started_at=started,
                duration_seconds=0.0,
                output_tokens=0.0,
                output_hash=_hash_text(""),
                exit_code=None,
                accepted=False,
                error_code=failures.RUNTIME_NOT_CONFIGURED,
                error_message="ollama url or model is not configured",
                metadata={"configured": False, "ollama_url_configured": bool(url), "ollama_model_configured": bool(model)},
            )

        body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            str(url),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            text = _ollama_response_text(payload)
            if text is None:
                return _ollama_failure(
                    job,
                    config,
                    started,
                    start_time,
                    failures.RUNTIME_INVALID_RESPONSE,
                    "ollama response missing response text",
                    {"response_bytes": len(raw)},
                )
            output_tokens = float(
                payload.get("eval_count")
                or payload.get("output_tokens")
                or _count_tokens(text)
            )
            return _runtime_result(
                job={**job, "model": str(model)},
                config=config,
                started_at=started,
                duration_seconds=time.monotonic() - start_time,
                output_tokens=output_tokens,
                output_hash=_hash_text(text),
                exit_code=0,
                accepted=True,
                error_code=None,
                error_message=None,
                metadata={
                    "ollama_url": str(url),
                    "ollama_model": str(model),
                    "response_bytes": len(raw),
                    "prompt_hash": _hash_text(str(prompt)),
                },
            )
        except TimeoutError:
            return _ollama_failure(
                job,
                config,
                started,
                start_time,
                failures.WORKER_TIMEOUT,
                f"ollama request timed out after {timeout} seconds",
                {"timeout_seconds": timeout},
            )
        except socket.timeout:
            return _ollama_failure(
                job,
                config,
                started,
                start_time,
                failures.WORKER_TIMEOUT,
                f"ollama request timed out after {timeout} seconds",
                {"timeout_seconds": timeout},
            )
        except urllib.error.URLError as exc:
            return _ollama_failure(
                job,
                config,
                started,
                start_time,
                failures.WORKER_OFFLINE,
                "local ollama endpoint is unavailable",
                {"error_type": type(exc.reason).__name__ if hasattr(exc, "reason") else type(exc).__name__},
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _ollama_failure(
                job,
                config,
                started,
                start_time,
                failures.RUNTIME_INVALID_RESPONSE,
                "ollama returned invalid JSON",
                {},
            )


class OllamaPlaceholderRuntime(BaseRuntime):
    runtime_type = "ollama_placeholder"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        return True

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        return _not_configured_result(job, config, self.runtime_type, "ollama endpoint is not configured")


class LlamaCppPlaceholderRuntime(BaseRuntime):
    runtime_type = "llama_cpp_placeholder"

    def can_run(self, job: dict[str, Any], worker: dict[str, Any]) -> bool:
        return True

    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        return _not_configured_result(job, config, self.runtime_type, "llama.cpp command is not configured")


def runtime_for_type(runtime_type: str) -> BaseRuntime:
    runtimes: dict[str, BaseRuntime] = {
        "simulated": SimulatedRuntime(),
        "subprocess": SubprocessRuntime(),
        "ollama": OllamaRuntime(),
        "ollama_placeholder": OllamaPlaceholderRuntime(),
        "llama_cpp_placeholder": LlamaCppPlaceholderRuntime(),
    }
    if runtime_type not in runtimes:
        raise ValueError(f"Unsupported runtime type: {runtime_type}")
    return runtimes[runtime_type]


def output_hash(output: str) -> str:
    return _hash_text(output)


def _runtime_result(
    *,
    job: dict[str, Any],
    config: dict[str, Any],
    started_at: str,
    duration_seconds: float,
    output_tokens: float,
    output_hash: str,
    exit_code: int | None,
    accepted: bool,
    error_code: str | None,
    error_message: str | None,
    metadata: dict[str, Any],
) -> RuntimeResult:
    runtime_cfg = config.get("runtime", {})
    worker_cfg = config.get("worker", {})
    total_watts = float(runtime_cfg.get("total_watts", worker_cfg.get("fallback_watts", 0)) or 0)
    energy_joules = total_watts * duration_seconds
    input_tokens = float(job.get("input_tokens", 0) or 0)
    tokens_per_second = output_tokens / duration_seconds if duration_seconds > 0 else 0.0
    enriched = {
        **metadata,
        "total_watts": total_watts,
        "energy_joules": energy_joules,
        "tokens_per_second": tokens_per_second,
        "qi_per_1k_tokens": runtime_cfg.get("qi_per_1k_tokens"),
        "runtime_type": runtime_cfg.get("type", "simulated"),
        "model_load_cold_start": runtime_cfg.get("model_load_cold_start", False),
        "cache_hit": runtime_cfg.get("cache_hit", False),
    }
    return RuntimeResult(
        job_id=str(job.get("job_id") or job.get("id") or ""),
        worker_id=str(worker_cfg.get("id") or job.get("assigned_worker_id") or ""),
        model=str(job.get("model") or ""),
        started_at=started_at,
        ended_at=utc_now_iso(),
        duration_seconds=round(duration_seconds, 6),
        input_tokens=input_tokens,
        output_tokens=float(output_tokens),
        output_hash=output_hash,
        exit_code=exit_code,
        accepted=accepted,
        error_code=error_code,
        error_message=error_message,
        metadata=enriched,
    )


def _not_configured_result(job: dict[str, Any], config: dict[str, Any], runtime_type: str, message: str) -> RuntimeResult:
    started = utc_now_iso()
    return _runtime_result(
        job=job,
        config={**config, "runtime": {**config.get("runtime", {}), "type": runtime_type}},
        started_at=started,
        duration_seconds=0.0,
        output_tokens=0.0,
        output_hash=_hash_text(""),
        exit_code=None,
        accepted=False,
        error_code=failures.RUNTIME_NOT_CONFIGURED,
        error_message=message,
        metadata={"configured": False},
    )


def _ollama_failure(
    job: dict[str, Any],
    config: dict[str, Any],
    started_at: str,
    start_time: float,
    error_code: str,
    error_message: str,
    metadata: dict[str, Any],
) -> RuntimeResult:
    return _runtime_result(
        job=job,
        config=config,
        started_at=started_at,
        duration_seconds=time.monotonic() - start_time,
        output_tokens=0.0,
        output_hash=_hash_text(""),
        exit_code=None,
        accepted=False,
        error_code=error_code,
        error_message=error_message,
        metadata=metadata,
    )


def _ollama_response_text(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("response")
    return value if isinstance(value, str) else None


def _stable_output(job: dict[str, Any], output_tokens: float) -> str:
    return f"{job.get('job_id') or job.get('id')}:{job.get('model')}:{output_tokens:.8f}"


def _hash_text(text: str | bytes) -> str:
    if isinstance(text, bytes):
        payload = text
    else:
        payload = text.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _count_tokens(text: str) -> int:
    return len(text.split()) if text else 0


def _redact_text(text: str) -> str:
    return text[:200]
