from __future__ import annotations

from typing import Any

from runtime import (
    BaseRuntime,
    LlamaCppPlaceholderRuntime,
    OllamaPlaceholderRuntime,
    RuntimeResult,
    SimulatedRuntime,
    SubprocessRuntime,
)


class SimulatedRunner(SimulatedRuntime):
    pass


class SubprocessRunner(SubprocessRuntime):
    pass


class OllamaRunner(OllamaPlaceholderRuntime):
    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        if not config.get("runtime", {}).get("ollama_endpoint"):
            return super().run(job, config)
        return super().run(job, config)


class LlamaCppRunner(LlamaCppPlaceholderRuntime):
    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        if not config.get("runtime", {}).get("llama_cpp_command"):
            return super().run(job, config)
        return super().run(job, config)


def runner_for_type(runtime_type: str) -> BaseRuntime:
    runners: dict[str, BaseRuntime] = {
        "simulated": SimulatedRunner(),
        "subprocess": SubprocessRunner(),
        "ollama_placeholder": OllamaRunner(),
        "llama_cpp_placeholder": LlamaCppRunner(),
    }
    if runtime_type not in runners:
        raise ValueError(f"Unsupported runner type: {runtime_type}")
    return runners[runtime_type]
