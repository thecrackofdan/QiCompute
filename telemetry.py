from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any


NVIDIA_SMI_FIELDS = [
    "index",
    "name",
    "power.draw",
    "temperature.gpu",
    "utilization.gpu",
    "utilization.memory",
]


class GPUTelemetry:
    def __init__(self, nvidia_smi_path: str = "nvidia-smi", fallback_watts: float = 250):
        self.nvidia_smi_path = nvidia_smi_path
        self.fallback_watts = float(fallback_watts)

    def sample(self) -> list[dict[str, Any]]:
        query = ",".join(NVIDIA_SMI_FIELDS)
        cmd = [
            self.nvidia_smi_path,
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return [self._fallback_sample(str(exc))]

        samples = []
        for line in result.stdout.splitlines():
            if line.strip():
                samples.append(self._parse_nvidia_smi_line(line))
        return samples or [self._fallback_sample("nvidia-smi returned no GPU rows")]

    def average_watts(self) -> float:
        samples = self.sample()
        watts = [s["power_watts"] for s in samples if s.get("power_watts") is not None]
        return sum(watts) / len(watts) if watts else self.fallback_watts

    def _parse_nvidia_smi_line(self, line: str) -> dict[str, Any]:
        parts = [part.strip() for part in line.split(",")]
        return {
            "ts": _utc_now_iso(),
            "gpu_index": _to_int(parts[0]),
            "name": parts[1] if len(parts) > 1 else None,
            "power_watts": _to_float(parts[2]) if len(parts) > 2 else None,
            "temperature_c": _to_float(parts[3]) if len(parts) > 3 else None,
            "utilization_gpu_percent": _to_float(parts[4]) if len(parts) > 4 else None,
            "utilization_memory_percent": _to_float(parts[5]) if len(parts) > 5 else None,
            "source": "nvidia-smi",
        }

    def _fallback_sample(self, reason: str) -> dict[str, Any]:
        return {
            "ts": _utc_now_iso(),
            "gpu_index": None,
            "name": None,
            "power_watts": self.fallback_watts,
            "temperature_c": None,
            "utilization_gpu_percent": None,
            "utilization_memory_percent": None,
            "source": "fallback",
            "reason": reason,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
