"""AIFMD Annex IV XML generation and NCA packaging.

Provides both mixin-based builders (for MAdapter integration) and the
standalone `build_from_canonical()` entry point for the platform pipeline.
"""

from aifmd_packaging.orchestrator import build_from_canonical

__all__ = ["build_from_canonical"]
