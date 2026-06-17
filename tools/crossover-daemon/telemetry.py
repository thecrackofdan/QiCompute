"""Thin re-export: delegates to the root telemetry module.

The root QiCompute/telemetry.py is the single source of truth for GPU
telemetry. This shim allows tools/crossover-daemon/ to import GPUTelemetry
without duplicating the implementation. If you need to run the daemon
standalone (outside the repo root), copy the root telemetry.py here.
"""
import importlib.util
import os

# Load the root telemetry.py by absolute path to avoid circular import
# (this file is also named telemetry.py, so a sys.path insert would shadow itself).
_root_telemetry = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "telemetry.py")
)
_spec = importlib.util.spec_from_file_location("_root_telemetry", _root_telemetry)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

GPUTelemetry = _mod.GPUTelemetry

__all__ = ["GPUTelemetry"]
