#!/usr/bin/env python3
"""
Regression test for the FCA 2.0 Input Adapter.
Parses golden set XML files and compares extracted canonical dicts
against a saved baseline (SHA-256 hashes of JSON-serialised records).

Usage:
    python test_regression.py                  # Run tests
    python test_regression.py --save-baseline  # Save current output as baseline
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_GOLDEN_SET = _SCRIPT_DIR / "golden_set"
_EVIDENCE_DIR = _GOLDEN_SET / "evidence"
_BASELINE_FILE = _SCRIPT_DIR / "refactor_baseline.json"

# Import the adapter
sys.path.insert(0, str(_SCRIPT_DIR))
from fca_adapter import FCAAdapter


def _discover_test_cases() -> list[dict]:
    """Auto-discover test cases from the golden_set directory."""
    cases = []
    if not _GOLDEN_SET.exists():
        return cases

    for f in sorted(_GOLDEN_SET.iterdir()):
        if f.name.startswith(".") or f.is_dir():
            continue
        if f.suffix.lower() != ".xml":
            continue

        name_upper = f.name.upper()
        if name_upper.startswith("AIFM_"):
            expected_type = "AIFM"
        elif name_upper.startswith("AIF_"):
            expected_type = "AIF"
        else:
            expected_type = "UNKNOWN"

        parts = f.stem.split("_")
        expected_rms = parts[1] if len(parts) >= 3 else "UNKNOWN"

        cases.append({
            "name": f.stem,
            "path": str(f),
            "expected_report_type": expected_type,
            "expected_rms": expected_rms,
        })
    return cases


def _normalize_record(record: dict) -> str:
    """Serialize a record to a stable JSON string for hashing."""
    clean = dict(record)
    clean.pop("_source_file", None)
    return json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)


def _compute_hash(record: dict) -> str:
    """Compute SHA-256 hash of a normalized record."""
    normalized = _normalize_record(record)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_test_case(case: dict) -> dict:
    """Run a single test case and return results."""
    try:
        adapter = FCAAdapter(case["path"])
        record_hashes = {}
        for i, rec in enumerate(adapter.records):
            key = f"record_{i}"
            record_hashes[key] = _compute_hash(rec)

        checks = []
        if case["expected_report_type"] != "UNKNOWN":
            match = adapter.report_type == case["expected_report_type"]
            checks.append({
                "check": "report_type",
                "expected": case["expected_report_type"],
                "actual": adapter.report_type,
                "pass": match,
            })
        if case["expected_rms"] != "UNKNOWN":
            match = adapter.reporting_member_state == case["expected_rms"]
            checks.append({
                "check": "reporting_member_state",
                "expected": case["expected_rms"],
                "actual": adapter.reporting_member_state,
                "pass": match,
            })
        checks.append({
            "check": "version",
            "expected": "2.0",
            "actual": adapter.version,
            "pass": adapter.version == "2.0",
        })
        checks.append({
            "check": "has_records",
            "expected": True,
            "actual": len(adapter.records) > 0,
            "pass": len(adapter.records) > 0,
        })
        # FCA-specific: namespace must be present
        checks.append({
            "check": "has_fca_namespace",
            "expected": True,
            "actual": "fsa-gov-uk" in (adapter._namespace or ""),
            "pass": "fsa-gov-uk" in (adapter._namespace or ""),
        })

        for i, rec in enumerate(adapter.records):
            rt = rec.get("_report_type", "")
            if rt == "AIFM":
                required = ["FilingType", "AIFMContentType", "ReportingPeriodType",
                           "AIFMNationalCode", "AIFMName"]
            elif rt == "AIF":
                required = ["FilingType", "AIFContentType", "ReportingPeriodType",
                           "AIFNationalCode", "AIFName"]
            else:
                required = []
            for field in required:
                has_field = rec.get(field) is not None
                checks.append({
                    "check": f"record_{i}.{field}_present",
                    "pass": has_field,
                })

            # FCA-specific: assumptions use FCAFieldReference (not QuestionNumber)
            for assumption in rec.get("Assumptions", []):
                checks.append({
                    "check": f"record_{i}.assumption_uses_FCAFieldReference",
                    "pass": "FCAFieldReference" in assumption,
                })

            # FCA-specific: geographic focus uses UK/EuropeNonUK
            nav_geo = rec.get("NAVGeographicalFocus", {})
            if nav_geo:
                has_uk = any("UK" in k for k in nav_geo)
                checks.append({
                    "check": f"record_{i}.geo_focus_uk_centric",
                    "pass": has_uk,
                })

        all_pass = all(c["pass"] for c in checks)
        return {
            "status": "OK" if all_pass else "WARN",
            "hashes": record_hashes,
            "record_count": len(adapter.records),
            "checks": checks,
            "summary": adapter.summary(),
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "hashes": {},
            "record_count": 0,
            "checks": [],
        }


def save_baseline():
    """Run all test cases and save results as baseline."""
    cases = _discover_test_cases()
    if not cases:
        print("No test cases found in golden_set/")
        sys.exit(1)

    baseline = {}
    print(f"\n{'='*60}")
    print(f"  FCA Adapter — Saving Baseline")
    print(f"{'='*60}\n")

    for case in cases:
        result = run_test_case(case)
        if result["status"] in ("OK", "WARN"):
            baseline[case["name"]] = {
                "hashes": result["hashes"],
                "record_count": result["record_count"],
            }
            status = "✅" if result["status"] == "OK" else "⚠️"
            print(f"  {status} {case['name']}: {result['record_count']} records")
        else:
            print(f"  ❌ {case['name']}: {result.get('error', 'unknown error')}")

    with open(_BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2, sort_keys=True)
    print(f"\nBaseline saved: {_BASELINE_FILE.name} ({len(baseline)} test cases)")


def run_tests():
    """Run all test cases and compare against baseline."""
    cases = _discover_test_cases()
    if not cases:
        print("No test cases found in golden_set/")
        sys.exit(1)

    has_baseline = _BASELINE_FILE.exists()
    if has_baseline:
        with open(_BASELINE_FILE) as f:
            baseline = json.load(f)
    else:
        baseline = {}
        print("  ⚠  No baseline found — running in discovery mode")

    total = 0
    passed = 0
    failed = 0
    errors = 0
    all_checks_passed = 0
    all_checks_failed = 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\n{'='*60}")
    print(f"  FCA 2.0 Input Adapter — Regression Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    evidence_records = []

    for case in cases:
        total += 1
        result = run_test_case(case)

        if result["status"] == "ERROR":
            print(f"  ❌ {case['name']}: ERROR — {result.get('error')}")
            errors += 1
            evidence_records.append({
                "suite": case["name"],
                "status": "ERROR",
                "error": result.get("error"),
            })
            continue

        check_failures = [c for c in result["checks"] if not c["pass"]]
        for c in result["checks"]:
            if c["pass"]:
                all_checks_passed += 1
            else:
                all_checks_failed += 1

        hash_diffs = []
        if case["name"] in baseline:
            expected = baseline[case["name"]]["hashes"]
            actual = result["hashes"]
            all_keys = sorted(set(list(expected.keys()) + list(actual.keys())))
            for key in all_keys:
                exp = expected.get(key)
                act = actual.get(key)
                if exp is None:
                    hash_diffs.append(f"    NEW: {key}")
                elif act is None:
                    hash_diffs.append(f"    MISSING: {key}")
                elif exp != act:
                    hash_diffs.append(f"    CHANGED: {key}")

        suite_pass = len(check_failures) == 0 and len(hash_diffs) == 0
        if suite_pass:
            status_icon = "✅"
            passed += 1
        else:
            status_icon = "❌"
            failed += 1

        detail = f"{result['record_count']} records, {len(result['checks'])} checks"
        if hash_diffs:
            detail += f", {len(hash_diffs)} hash diff(s)"
        print(f"  {status_icon} {case['name']}: {detail}")
        for d in hash_diffs:
            print(d)
        for c in check_failures:
            print(f"    FAIL: {c['check']} (expected={c.get('expected')}, actual={c.get('actual')})")

        evidence_records.append({
            "suite": case["name"],
            "status": "PASS" if suite_pass else "FAIL",
            "records": result["record_count"],
            "checks_passed": len(result["checks"]) - len(check_failures),
            "checks_failed": len(check_failures),
            "hash_diffs": len(hash_diffs),
            "summary": result.get("summary"),
        })

    overall = "PASS" if failed == 0 and errors == 0 else "FAIL"

    print(f"\n{'='*60}")
    print(f"  Total: {total} | Pass: {passed} | Fail: {failed} | Error: {errors}")
    print(f"  Checks: {all_checks_passed} passed, {all_checks_failed} failed")
    print(f"  Overall: {'✅ ALL PASS' if overall == 'PASS' else '❌ REGRESSIONS DETECTED'}")
    print(f"{'='*60}\n")

    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence = {
        "adapter": "FCA 2.0 Input Adapter",
        "timestamp": datetime.now().isoformat(),
        "overall": overall,
        "summary": {
            "total_suites": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "checks_passed": all_checks_passed,
            "checks_failed": all_checks_failed,
        },
        "suites": evidence_records,
    }
    evidence_path = _EVIDENCE_DIR / f"regression_{timestamp}.yaml"
    with open(evidence_path, "w") as f:
        yaml.dump(evidence, f, default_flow_style=False, sort_keys=False)
    print(f"  Evidence: {evidence_path.name}")

    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    if "--save-baseline" in sys.argv:
        print("Saving baseline...")
        save_baseline()
    else:
        run_tests()
