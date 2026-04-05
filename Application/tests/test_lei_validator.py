"""End-to-end tests for LEI validator (Path 1 + Path 2).

Runs against a fresh SQLite database with synthetic GLEIF records.
"""

import sys
from pathlib import Path

# Add Application root to sys.path
app_root = Path(__file__).resolve().parent / "mnt" / "Mijn Drive (olaf.van.halm@maxxmanagement.nl)--Project Eagle" / "Application"
sys.path.insert(0, str(app_root))

from shared.reference_store import ReferenceStore
from shared.lei_validator import (
    normalize_entity_name,
    validate_lei_format,
    validate_lei_with_gleif,
    validate_name_without_lei,
    validate_lei,
    _name_similarity,
    LEIValidationResult,
)

# ── Setup: in-memory SQLite with test data ────────────────────────────

def create_test_store() -> ReferenceStore:
    """Create an in-memory SQLite store with test LEI records."""
    store = ReferenceStore.sqlite(":memory:")

    # Insert test GLEIF records
    test_records = [
        {
            "lei": "549300MLUDYVRQOOXS22",  # Valid LEI (BlackRock Fund Advisors)
            "legal_name": "BlackRock Fund Advisors",
            "entity_status": "ACTIVE",
            "country": "US",
            "registration_authority": "RA000665",
            "last_update": "2024-06-15",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "5493001KJTIIGC8Y1R12",  # Valid LEI (BlackRock, Inc.)
            "legal_name": "BlackRock, Inc.",
            "entity_status": "ACTIVE",
            "country": "US",
            "registration_authority": "RA000665",
            "last_update": "2024-06-15",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "HWUPKR0MPOU8FGXBT394",  # Valid LEI (Goldman Sachs)
            "legal_name": "The Goldman Sachs Group, Inc.",
            "entity_status": "ACTIVE",
            "country": "US",
            "registration_authority": "RA000665",
            "last_update": "2024-08-01",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "R0MUWSFPU8MPRO8K5P83",  # Valid LEI (BNP Paribas)
            "legal_name": "BNP Paribas SA",
            "entity_status": "ACTIVE",
            "country": "FR",
            "registration_authority": "RA000525",
            "last_update": "2024-07-01",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "529900HNOAA1KXQJUQ27",  # Valid LEI (Deutsche Bank)
            "legal_name": "Deutsche Bank Aktiengesellschaft",
            "entity_status": "ACTIVE",
            "country": "DE",
            "registration_authority": "RA000342",
            "last_update": "2024-09-01",
            "expires_at": "2099-12-31T00:00:00",
        },
    ]
    store.upsert_lei(test_records)
    return store


# ── Test: Name Normalization ──────────────────────────────────────────

def test_name_normalization():
    print("\n=== Test: Name Normalization ===")
    tests = [
        ("BlackRock, Inc.", "BLACKROCK"),
        ("BNP Paribas SA", "BNPPARIBAS"),
        ("Deutsche Bank Aktiengesellschaft", "DEUTSCHEBANK"),
        ("The Goldman Sachs Group, Inc.", "GOLDMANSACHS"),
        ("HSBC Holdings plc", "HSBC"),
        ("Société Générale S.A.", "SOCIETEGENERALE"),
        ("  ABC  Limited  ", "ABC"),
        ("", ""),
        ("LLC", "LLC"),  # Edge: name IS a suffix — fallback to full alphanumeric
    ]
    passed = 0
    for name, expected in tests:
        result = normalize_entity_name(name)
        ok = result == expected
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] normalize('{name}') = '{result}' (expected '{expected}')")

    print(f"  → {passed}/{len(tests)} passed")
    return passed == len(tests)


# ── Test: LEI Format Validation ──────────────────────────────────────

def test_lei_format():
    print("\n=== Test: LEI Format Validation ===")
    tests = [
        # (lei, expected_valid, description)
        ("549300MLUDYVRQOOXS22", True, "Valid LEI (BlackRock Fund Advisors)"),
        ("5493001KJTIIGC8Y1R12", True, "Valid LEI (BlackRock Inc)"),
        ("HWUPKR0MPOU8FGXBT394", True, "Valid LEI (Goldman Sachs)"),
        ("R0MUWSFPU8MPRO8K5P83", True, "Valid LEI (BNP Paribas)"),
        ("529900HNOAA1KXQJUQ27", True, "Valid LEI (Deutsche Bank)"),
        ("", False, "Empty string"),
        ("1234567890", False, "Too short"),
        ("12345678901234567890123", False, "Too long"),
        ("549300MLUDYVRQOOXS99", False, "Wrong check digits"),
        ("549300MLUDYVRQOOX$22", False, "Invalid characters"),
    ]
    passed = 0
    for lei, expected_valid, desc in tests:
        is_valid, error = validate_lei_format(lei)
        ok = is_valid == expected_valid
        passed += ok
        status = "PASS" if ok else "FAIL"
        extra = f" ({error})" if error else ""
        print(f"  [{status}] {desc}: valid={is_valid}{extra}")

    print(f"  → {passed}/{len(tests)} passed")
    return passed == len(tests)


# ── Test: Name Similarity Scoring ────────────────────────────────────

def test_name_similarity():
    print("\n=== Test: Name Similarity ===")
    tests = [
        # (name_a, name_b, min_score, max_score, description)
        ("BlackRock, Inc.", "BlackRock, Inc.", 1.0, 1.0, "Exact match"),
        ("BlackRock Inc", "BLACKROCK INC.", 1.0, 1.0, "Case/punctuation difference"),
        ("BlackRock Fund Advisors", "BlackRock", 0.85, 1.0, "Prefix/exact after suffix strip"),
        ("Goldman Sachs", "Deutsche Bank", 0.0, 0.5, "Different entities"),
        ("", "BlackRock", 0.0, 0.0, "Empty name"),
        ("BNP Paribas SA", "BNP Paribas S.A.", 0.9, 1.0, "Same after suffix strip"),
    ]
    passed = 0
    for name_a, name_b, min_s, max_s, desc in tests:
        score = _name_similarity(name_a, name_b)
        ok = min_s <= score <= max_s
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {desc}: score={score:.2f} (expected {min_s:.1f}–{max_s:.1f})")

    print(f"  → {passed}/{len(tests)} passed")
    return passed == len(tests)


# ── Test: Path 1 — LEI Provided ─────────────────────────────────────

def test_path1_lei_provided():
    print("\n=== Test: Path 1 — LEI Provided ===")
    store = create_test_store()
    passed = 0
    total = 0

    # 1a: Valid LEI, matching name
    total += 1
    r = validate_lei_with_gleif("549300MLUDYVRQOOXS22", "BlackRock Fund Advisors", store)
    ok = r.is_valid_format and r.gleif_found and r.name_match_status == "MATCH" and r.severity == "PASS"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Valid LEI + matching name: severity={r.severity}, status={r.name_match_status}, score={r.name_match_score:.2f}")

    # 1b: Valid LEI, slightly different name (should still match)
    total += 1
    r = validate_lei_with_gleif("5493001KJTIIGC8Y1R12", "Blackrock Inc", store)
    ok = r.is_valid_format and r.gleif_found and r.name_match_status == "MATCH" and r.severity == "PASS"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Valid LEI + similar name: severity={r.severity}, status={r.name_match_status}, score={r.name_match_score:.2f}")

    # 1c: Valid LEI, completely wrong name
    total += 1
    r = validate_lei_with_gleif("549300MLUDYVRQOOXS22", "Deutsche Bank AG", store)
    ok = r.is_valid_format and r.gleif_found and r.name_match_status == "MISMATCH" and r.severity == "WARNING"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Valid LEI + wrong name: severity={r.severity}, status={r.name_match_status}, score={r.name_match_score:.2f}")

    # 1d: Invalid format
    total += 1
    r = validate_lei_with_gleif("INVALID", "BlackRock", store)
    ok = not r.is_valid_format and r.severity == "ERROR"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Invalid format: severity={r.severity}, error='{r.format_error}'")

    # 1e: Valid format but not in our test store
    # Note: In production, API fallback would attempt GLEIF lookup.
    # Here we test with an LEI not in our test store. API fallback may or may not find it.
    total += 1
    r = validate_lei_with_gleif("529900T8BM49AURSDO55", "Some Entity", store)
    ok = r.is_valid_format  # Format is valid regardless of GLEIF lookup
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Valid format, not in test store: severity={r.severity}, found={r.gleif_found}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


# ── Test: Path 2 — No LEI, Name Search ──────────────────────────────

def test_path2_no_lei():
    print("\n=== Test: Path 2 — No LEI ===")
    store = create_test_store()
    passed = 0
    total = 0

    # 2a: Name matches a GLEIF record (both BlackRock entities normalize to BLACKROCK)
    total += 1
    r = validate_name_without_lei("BlackRock, Inc.", store)
    ok = r.suggested_lei in ("5493001KJTIIGC8Y1R12", "549300MLUDYVRQOOXS22") and r.severity == "WARNING" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'BlackRock, Inc.' → suggested LEI={r.suggested_lei} (any BlackRock LEI)")

    # 2b: Name matches after normalization (different punctuation/case)
    total += 1
    r = validate_name_without_lei("blackrock inc", store)
    ok = r.suggested_lei in ("5493001KJTIIGC8Y1R12", "549300MLUDYVRQOOXS22") and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'blackrock inc' → suggested LEI={r.suggested_lei}")

    # 2c: Deutsche Bank name normalization
    total += 1
    r = validate_name_without_lei("Deutsche Bank AG", store)
    # "Deutsche Bank Aktiengesellschaft" → DEUTSCHEBANK
    # "Deutsche Bank AG" → DEUTSCHEBANK  (AG is stripped)
    ok = r.suggested_lei == "529900HNOAA1KXQJUQ27" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'Deutsche Bank AG' → suggested LEI={r.suggested_lei} (expected 529900HNOAA1KXQJUQ27)")

    # 2d: BNP Paribas with different suffix
    total += 1
    r = validate_name_without_lei("BNP Paribas S.A.", store)
    ok = r.suggested_lei == "R0MUWSFPU8MPRO8K5P83" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'BNP Paribas S.A.' → suggested LEI={r.suggested_lei} (expected R0MUWSFPU8MPRO8K5P83)")

    # 2e: Unknown entity — no match
    total += 1
    r = validate_name_without_lei("Totally Unknown Corp", store)
    ok = not r.gleif_found and r.suggested_lei == "" and r.severity == "WARNING"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Unknown entity: found={r.gleif_found}, suggested='{r.suggested_lei}'")

    # 2f: Empty name
    total += 1
    r = validate_name_without_lei("", store)
    ok = not r.gleif_found and r.severity == "WARNING"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Empty name: severity={r.severity}")

    # 2g: Country filter narrows results — BNP Paribas with country=FR
    total += 1
    r = validate_name_without_lei("BNP Paribas", store, country="FR")
    ok = r.suggested_lei == "R0MUWSFPU8MPRO8K5P83" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'BNP Paribas' + country=FR → suggested LEI={r.suggested_lei}")

    # 2h: Country filter with Deutsche Bank + country=DE
    total += 1
    r = validate_name_without_lei("Deutsche Bank AG", store, country="DE")
    ok = r.suggested_lei == "529900HNOAA1KXQJUQ27" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'Deutsche Bank AG' + country=DE → suggested LEI={r.suggested_lei}")

    # 2i: Wrong country should fall back to name-only match
    total += 1
    r = validate_name_without_lei("BNP Paribas", store, country="JP")
    ok = r.suggested_lei == "R0MUWSFPU8MPRO8K5P83" and r.gleif_found  # Falls back to name-only
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] 'BNP Paribas' + country=JP (fallback) → suggested LEI={r.suggested_lei}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


# ── Test: Unified dispatcher ─────────────────────────────────────────

def test_unified_dispatch():
    print("\n=== Test: Unified Dispatch ===")
    store = create_test_store()
    passed = 0
    total = 0

    # LEI provided → Path 1
    total += 1
    r = validate_lei("549300MLUDYVRQOOXS22", "BlackRock Fund Advisors", store)
    ok = r.is_valid_format and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] With LEI → Path 1: valid={r.is_valid_format}, found={r.gleif_found}")

    # No LEI → Path 2
    total += 1
    r = validate_lei("", "BlackRock, Inc.", store)
    ok = not r.is_valid_format and r.suggested_lei != ""
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] No LEI → Path 2: suggested={r.suggested_lei}")

    # None LEI → Path 2 (Goldman Sachs should match after "The" and "Group, Inc." stripped)
    total += 1
    r = validate_lei(None, "Goldman Sachs", store)
    ok = r.suggested_lei == "HWUPKR0MPOU8FGXBT394" and r.gleif_found
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] None LEI → Path 2: suggested='{r.suggested_lei}', found={r.gleif_found}")

    # Whitespace-only LEI → Path 2
    total += 1
    r = validate_lei("   ", "BNP Paribas", store)
    ok = not r.is_valid_format
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Whitespace LEI → Path 2: valid={r.is_valid_format}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


# ── Test: Normalized name stored in DB ───────────────────────────────

def test_normalized_name_in_db():
    print("\n=== Test: Normalized Name Storage ===")
    store = create_test_store()
    passed = 0
    total = 0

    # Check that upsert_lei computed and stored normalized_name
    total += 1
    record = store.get_lei("5493001KJTIIGC8Y1R12")
    ok = record is not None and record.normalized_name == "BLACKROCK"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] BlackRock Inc normalized_name = '{record.normalized_name if record else 'N/A'}' (expected 'BLACKROCK')")

    total += 1
    record = store.get_lei("529900HNOAA1KXQJUQ27")
    ok = record is not None and record.normalized_name == "DEUTSCHEBANK"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Deutsche Bank normalized_name = '{record.normalized_name if record else 'N/A'}' (expected 'DEUTSCHEBANK')")

    total += 1
    record = store.get_lei("R0MUWSFPU8MPRO8K5P83")
    ok = record is not None and record.normalized_name == "BNPPARIBAS"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] BNP Paribas normalized_name = '{record.normalized_name if record else 'N/A'}' (expected 'BNPPARIBAS')")

    # Verify search by normalized name works
    total += 1
    results = store.search_lei_by_normalized_name("BLACKROCK")
    ok = len(results) >= 1 and any(r.lei == "5493001KJTIIGC8Y1R12" for r in results)
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Search 'BLACKROCK': found {len(results)} results, includes 5493001KJTIIGC8Y1R12={any(r.lei == '5493001KJTIIGC8Y1R12' for r in results)}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("LEI Validator — End-to-End Tests")
    print("=" * 60)

    all_pass = True
    all_pass &= test_name_normalization()
    all_pass &= test_lei_format()
    all_pass &= test_name_similarity()
    all_pass &= test_path1_lei_provided()
    all_pass &= test_path2_no_lei()
    all_pass &= test_unified_dispatch()
    all_pass &= test_normalized_name_in_db()

    print("\n" + "=" * 60)
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — review output above")
    print("=" * 60)
    sys.exit(0 if all_pass else 1)
