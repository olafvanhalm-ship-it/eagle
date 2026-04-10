#!/usr/bin/env python3
"""
Project Eagle — Master Regression Runner
==========================================
Runs all adapter regression suites and collects results into a single
consolidated report under Testing/Test results/.

Currently registered adapters:
  1. M adapter          (E2E: template → generate → validate → compare)
  2. ESMA 1.2 adapter   (hash-based: parse golden set → compare hashes)
  3. FCA 2.0 adapter     (hash-based: parse golden set → compare hashes)

Adding a new adapter:
  - Add an entry to ADAPTERS below with name, script path, and flags.
  - The script must return exit code 0 on success, non-zero on failure.
  - Evidence YAML is copied from each adapter's own evidence/ directory.

Usage:
    python run_all_regressions.py                     # Run all adapters
    python run_all_regressions.py --adapter m          # Run one adapter
    python run_all_regressions.py --compliance         # Include Excel compliance report
    python run_all_regressions.py --list               # List registered adapters

Output:
    Testing/Test results/YYYYMMDD_HHMMSS/
        summary.yaml              — consolidated results
        m_adapter/                — M adapter evidence (YAML + optional XLSX)
        esma_adapter/             — ESMA 1.2 adapter evidence
        fca_adapter/              — FCA 2.0 adapter evidence
"""

import argparse
import os
import shutil
import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_TESTING_DIR = _SCRIPT_DIR
_RESULTS_DIR = _TESTING_DIR / "Test results"

# Auto-detect project root (directory containing Blueprint/)
_PROJECT_ROOT = _SCRIPT_DIR
for _p in [_SCRIPT_DIR] + [_SCRIPT_DIR.parents[i] for i in range(5)]:
    if (_p / "Blueprint").is_dir():
        _PROJECT_ROOT = _p
        break

_APP_ROOT = _PROJECT_ROOT / "Application"
_ADAPTERS_ROOT = _APP_ROOT / "Adapters" / "Input adapters"


# ── Adapter Registry ─────────────────────────────────────────────────────────
# Each adapter has:
#   name:        short identifier (used for --adapter filter)
#   description: human-readable description
#   script:      path to the regression script (relative to project root)
#   cwd:         working directory for the script
#   args:        default arguments
#   compliance_args: extra arguments when --compliance is used
#   evidence_dir: where the script writes its evidence files

ADAPTERS = [
    {
        "name": "m",
        "description": "M adapter — E2E (template → generate → validate → baseline compare)",
        "script": _ADAPTERS_ROOT / "M adapter" / "run_regression_suite.py",
        "cwd": _ADAPTERS_ROOT / "M adapter",
        "args": [],
        "compliance_args": ["--compliance-report"],
        "evidence_dir": _ADAPTERS_ROOT / "M adapter" / "golden_set" / "evidence",
    },
    {
        "name": "esma",
        "description": "ESMA 1.2 adapter — hash-based parse regression",
        "script": _ADAPTERS_ROOT / "ESMA 1.2 adapter" / "test_regression.py",
        "cwd": _ADAPTERS_ROOT / "ESMA 1.2 adapter",
        "args": [],
        "compliance_args": [],
        "evidence_dir": _ADAPTERS_ROOT / "ESMA 1.2 adapter" / "golden_set" / "evidence",
    },
    {
        "name": "fca",
        "description": "FCA 2.0 adapter — hash-based parse regression",
        "script": _ADAPTERS_ROOT / "FCA 2.0 adapter" / "test_regression.py",
        "cwd": _ADAPTERS_ROOT / "FCA 2.0 adapter",
        "args": [],
        "compliance_args": [],
        "evidence_dir": _ADAPTERS_ROOT / "FCA 2.0 adapter" / "golden_set" / "evidence",
    },
]


# ── Runner ───────────────────────────────────────────────────────────────────

def run_adapter(adapter: dict, run_dir: Path, compliance: bool = False) -> dict:
    """Run a single adapter's regression suite.

    Returns a result dict with status, duration, output, and evidence paths.
    """
    script = adapter["script"]
    if not script.exists():
        return {
            "status": "SKIPPED",
            "reason": f"Script not found: {script}",
            "duration_s": 0,
            "evidence_files": [],
        }

    args = list(adapter["args"])
    if compliance:
        args.extend(adapter["compliance_args"])

    cmd = [sys.executable, str(script)] + args

    # Snapshot evidence dir before run (to identify new files after)
    evidence_dir = adapter["evidence_dir"]
    if evidence_dir.is_dir():
        before = set(f.name for f in evidence_dir.iterdir())
    else:
        before = set()

    start = datetime.now()
    try:
        # Stream output live so the user sees progress, while also
        # capturing it for the log file.
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,           # line-buffered
            cwd=str(adapter["cwd"]),
            env=env,
        )
        output_lines = []
        for line in proc.stdout:
            print(f"    {line}", end="", flush=True)
            output_lines.append(line)
        proc.wait(timeout=600)
        duration = (datetime.now() - start).total_seconds()
        output = "".join(output_lines)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        duration = 600
        output = "TIMEOUT: regression suite exceeded 10 minute limit"
        exit_code = -1
    except Exception as e:
        duration = (datetime.now() - start).total_seconds()
        output = f"ERROR: {e}"
        exit_code = -2

    # Determine status from exit code
    if exit_code == 0:
        status = "PASS"
    elif exit_code == -1:
        status = "TIMEOUT"
    elif exit_code == -2:
        status = "ERROR"
    else:
        status = "FAIL"

    # Copy new evidence files to run directory
    adapter_dir = run_dir / f"{adapter['name']}_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    evidence_files = []

    if evidence_dir.is_dir():
        after = set(f.name for f in evidence_dir.iterdir())
        new_files = after - before
        for fname in sorted(new_files):
            src = evidence_dir / fname
            dst = adapter_dir / fname
            shutil.copy2(str(src), str(dst))
            evidence_files.append(fname)

    # Save raw console output
    log_path = adapter_dir / "console_output.txt"
    with open(str(log_path), "w", encoding="utf-8") as f:
        f.write(output)

    return {
        "status": status,
        "exit_code": exit_code,
        "duration_s": round(duration, 1),
        "evidence_files": evidence_files,
        "output_lines": len(output.strip().split("\n")),
    }


def list_adapters():
    """Print all registered adapters."""
    print(f"\n{'='*60}")
    print(f"  Project Eagle — Registered Regression Adapters")
    print(f"{'='*60}\n")
    for adapter in ADAPTERS:
        exists = adapter["script"].exists()
        icon = "[OK]" if exists else "[--]"
        print(f"  {icon} {adapter['name']:8s}  {adapter['description']}")
        if not exists:
            print(f"              Script not found: {adapter['script'].name}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Project Eagle — Master Regression Runner")
    parser.add_argument("--adapter", default="",
                        help="Run only this adapter (e.g. m, esma, fca)")
    parser.add_argument("--compliance", action="store_true",
                        help="Generate compliance reports where supported")
    parser.add_argument("--list", action="store_true",
                        help="List all registered adapters")
    args = parser.parse_args()

    if args.list:
        list_adapters()
        return

    # Determine which adapters to run
    if args.adapter:
        adapters = [a for a in ADAPTERS if a["name"] == args.adapter]
        if not adapters:
            names = ", ".join(a["name"] for a in ADAPTERS)
            print(f"  ERROR: Adapter '{args.adapter}' not found. Available: {names}")
            sys.exit(1)
    else:
        adapters = ADAPTERS

    # Create timestamped output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _RESULTS_DIR / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  Project Eagle — Master Regression Runner")
    print(f"{'='*70}")
    print(f"  Timestamp : {datetime.now().isoformat()}")
    print(f"  Output    : Test results/{ts}/")
    print(f"  Adapters  : {len(adapters)}")
    if args.compliance:
        print(f"  Compliance: enabled")

    # Run each adapter
    all_results = {}
    total_pass = 0
    total_fail = 0

    for adapter in adapters:
        print(f"\n{'_'*60}")
        print(f"  Adapter: {adapter['name']}")
        print(f"  {adapter['description']}")
        print(f"  Running...", flush=True)

        result = run_adapter(adapter, run_dir, compliance=args.compliance)
        all_results[adapter["name"]] = result

        status = result["status"]
        icon = {
            "PASS": "[PASS]", "FAIL": "[FAIL]", "SKIPPED": "[SKIP]",
            "ERROR": "[ERR ]", "TIMEOUT": "[TIME]",
        }.get(status, "[????]")

        print(f"\n  {icon} {adapter['name']}  ({result['duration_s']}s)")

        if result.get("evidence_files"):
            print(f"     Evidence: {', '.join(result['evidence_files'])}")
        if result.get("reason"):
            print(f"     Reason: {result['reason']}")

        if status == "PASS":
            total_pass += 1
        else:
            total_fail += 1

    # Summary
    total = len(adapters)
    overall = "PASS" if total_fail == 0 else "FAIL"

    print(f"\n{'='*70}")
    print(f"  MASTER REGRESSION SUMMARY")
    print(f"{'='*70}")
    print(f"  Total adapters : {total}")
    print(f"  Passed         : {total_pass}")
    if total_fail:
        print(f"  Failed         : {total_fail}")
    print(f"  Overall        : {'ALL PASS' if overall == 'PASS' else 'FAILURES DETECTED'}")

    # Save consolidated summary
    summary = {
        "project": "Project Eagle",
        "timestamp": datetime.now().isoformat(),
        "overall": overall,
        "adapters_run": total,
        "adapters_passed": total_pass,
        "adapters_failed": total_fail,
        "compliance_mode": args.compliance,
        "results": {},
    }
    for name, result in all_results.items():
        adapter_info = next(a for a in ADAPTERS if a["name"] == name)
        summary["results"][name] = {
            "description": adapter_info["description"],
            "status": result["status"],
            "duration_s": result["duration_s"],
            "evidence_files": result.get("evidence_files", []),
        }

    summary_path = run_dir / "summary.yaml"
    with open(str(summary_path), "w", encoding="utf-8") as f:
        yaml.dump(summary, f, default_flow_style=False, sort_keys=False,
                  allow_unicode=True, width=120)

    print(f"\n  Results saved to: Test results/{ts}/")
    print(f"  Summary: {summary_path.name}")
    print(f"{'='*70}\n")

    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
