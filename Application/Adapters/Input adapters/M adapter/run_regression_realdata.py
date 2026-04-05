#!/usr/bin/env python3
"""Quick regression: M example templates + authorised_anon only.

This is the fast regression path for small changes. For large changes
(rule changes, new NCAs, adapter modifications), run both this script
and run_regression_synthetic.py.

Equivalent to:
    python run_regression_suite.py --scope realdata
"""
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MAIN_SCRIPT = _SCRIPT_DIR / "run_regression_suite.py"

sys.exit(subprocess.call(
    [sys.executable, str(_MAIN_SCRIPT), "--scope", "realdata"] + sys.argv[1:]
))
