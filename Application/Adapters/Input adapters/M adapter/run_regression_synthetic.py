#!/usr/bin/env python3
"""Synthetic regression: all synthetic test suites (65 suites, 31 NCAs).

This is the thorough regression path for large changes. For small
changes, run_regression_realdata.py is sufficient.

Equivalent to:
    python run_regression_suite.py --scope synthetic
"""
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MAIN_SCRIPT = _SCRIPT_DIR / "run_regression_suite.py"

sys.exit(subprocess.call(
    [sys.executable, str(_MAIN_SCRIPT), "--scope", "synthetic"] + sys.argv[1:]
))
