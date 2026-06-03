from __future__ import annotations

from typing import Any

from runtime import (
    BaseRuntime,
    LlamaCppPlaceholderRuntime,
    OllamaRuntime,
    OllamaPlaceholderRuntime,
    RuntimeResult,
    SimulatedRuntime,
    SubprocessRuntime,
)


class SimulatedRunner(SimulatedRuntime):
    pass


class SubprocessRunner(SubprocessRuntime):
    pass


class OllamaRunner(OllamaRuntime):
    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        return super().run(job, config)


class OllamaPlaceholderRunner(OllamaPlaceholderRuntime):
    pass


class LlamaCppRunner(LlamaCppPlaceholderRuntime):
    def run(self, job: dict[str, Any], config: dict[str, Any]) -> RuntimeResult:
        if not config.get("runtime", {}).get("llama_cpp_command"):
            return super().run(job, config)
        return super().run(job, config)


def runner_for_type(runtime_type: str) -> BaseRuntime:
    runners: dict[str, BaseRuntime] = {
        "simulated": SimulatedRunner(),
        "subprocess": SubprocessRunner(),
        "ollama": OllamaRunner(),
        "ollama_placeholder": OllamaPlaceholderRunner(),
        "llama_cpp_placeholder": LlamaCppRunner(),
    }
    if runtime_type not in runners:
        raise ValueError(f"Unsupported runner type: {runtime_type}")
    return runners[runtime_type]
