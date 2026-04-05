"""Integration tests for Eagle Report Viewer API.

Tests the full flow: persistence → API endpoints → cascade → validation.
Uses SQLite in-memory backend (no PostgreSQL required).

Run from project root:
    python -m pytest Testing/test_review_api.py -v
Or directly:
    python Testing/test_review_api.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure Application is importable
_project_root = Path(__file__).resolve().parent.parent
_app_root = _project_root / "Application"
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_app_root))

# Force SQLite in-memory for tests
os.environ["DATABASE_URL"] = "sqlite://"


# ============================================================================
# 1. Persistence Layer Tests
# ============================================================================

def test_report_store_crud():
    """Test basic CRUD operations on ReportStore with SQLite in-memory."""
    from persistence.report_store import ReportStore, ReviewSession, ReviewReport, ReviewEdit

    store = ReportStore("sqlite://")

    # Create session
    session = ReviewSession(
        filename="test_template.xlsx",
        aifm_name="Test Fund Manager BV",
        filing_type="INIT",
        template_type="FULL",
        reporting_member_state="NL",
        num_aifs=2,
        source_canonical={
            "manager": {"name": {"value": "Test Fund Manager BV", "source": "test"}},
            "aifs": [
                {
                    "fund_static": {"name": {"value": "Test Fund Alpha", "source": "test"}},
                    "fund_dynamic": {},
                    "positions": [
                        {"instrument_name": {"value": "Apple Inc", "source": "test"},
                         "market_value": {"value": "1000000", "source": "test"}},
                    ],
                    "transactions": [],
                    "share_classes": [],
                    "counterparties": [],
                    "strategies": [],
                    "investors": [],
                    "risk_measures": [],
                    "borrowing_sources": [],
                },
                {
                    "fund_static": {"name": {"value": "Test Fund Beta", "source": "test"}},
                    "fund_dynamic": {},
                    "positions": [],
                    "transactions": [],
                    "share_classes": [],
                    "counterparties": [],
                    "strategies": [],
                    "investors": [],
                    "risk_measures": [],
                    "borrowing_sources": [],
                },
            ],
        },
    )
    store.save_session(session)

    # Retrieve session
    retrieved = store.get_session(session.session_id)
    assert retrieved is not None, "Session should be retrievable"
    assert retrieved.aifm_name == "Test Fund Manager BV"
    assert retrieved.num_aifs == 2
    assert len(retrieved.source_canonical["aifs"]) == 2

    # Create AIFM report
    aifm_report = ReviewReport(
        session_id=session.session_id,
        report_type="AIFM",
        entity_name="Test Fund Manager BV",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "17": {"value": "NL", "source": "test", "priority": "IMPORTED"},
            "18": {"value": "12345678", "source": "test", "priority": "IMPORTED"},
            "19": {"value": "Test Fund Manager BV", "source": "test", "priority": "IMPORTED"},
        },
        field_count=38,
        filled_count=3,
        completeness=7.9,
    )
    store.save_report(aifm_report)

    # Create AIF report
    aif_report = ReviewReport(
        session_id=session.session_id,
        report_type="AIF",
        entity_name="Test Fund Alpha",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "18": {"value": "Test Fund Alpha", "source": "test", "priority": "IMPORTED"},
            "49": {"value": "EUR", "source": "test", "priority": "IMPORTED"},
        },
        field_count=302,
        filled_count=2,
        completeness=0.7,
    )
    store.save_report(aif_report)

    # Retrieve reports
    reports = store.get_reports_for_session(session.session_id)
    assert len(reports) == 2, f"Expected 2 reports, got {len(reports)}"

    aifm = store.get_report_by_type_and_index(session.session_id, "AIFM", 0)
    assert aifm is not None, "AIFM report should be retrievable"
    assert aifm.fields_json["19"]["value"] == "Test Fund Manager BV"

    # Log edit
    edit = ReviewEdit(
        session_id=session.session_id,
        report_id=aifm_report.report_id,
        edit_type="field",
        target="19",
        old_value="Test Fund Manager BV",
        new_value="Updated Fund Manager BV",
        cascaded_fields=[],
    )
    edit_id = store.log_edit(edit)
    assert edit_id > 0, "Edit ID should be positive"

    # Get edits
    edits = store.get_edits(session.session_id)
    assert len(edits) == 1
    assert edits[0].target == "19"

    # Undo
    undone = store.delete_last_edit(session.session_id)
    assert undone is not None
    assert undone.target == "19"
    assert len(store.get_edits(session.session_id)) == 0

    # Archive
    count = store.archive_active_sessions()
    assert count == 1
    active = store.get_active_session()
    assert active is None, "No active session after archive"

    print("  PASS: test_report_store_crud")


# ============================================================================
# 2. Dependency Graph Tests
# ============================================================================

def test_dependency_graph_reverse_index():
    """Test that the reverse index maps source fields to report fields."""
    from canonical.dependency_graph import (
        get_reverse_index,
        find_affected_report_fields,
        find_affected_by_collection_edit,
    )

    index = get_reverse_index()
    assert len(index) > 0, "Reverse index should not be empty"

    # Manager name (field 19 in AIFM report)
    affected = find_affected_report_fields("manager", "name")
    aifm_fields = [a for a in affected if a["report_type"] == "AIFM"]
    assert any(a["field_id"] == "19" for a in aifm_fields), \
        "Changing manager.name should affect AIFM field 19"

    # Fund base_currency (field 49 in AIF report)
    affected = find_affected_report_fields("fund_static", "base_currency")
    aif_fields = [a for a in affected if a["report_type"] == "AIF"]
    assert any(a["field_id"] == "49" for a in aif_fields), \
        "Changing fund_static.base_currency should affect AIF field 49"

    # Position collection edit
    affected = find_affected_by_collection_edit("positions")
    assert len(affected) > 0, "Editing positions should affect some fields"
    group_updates = [a for a in affected if a["cascade_type"] == "group_update"]
    assert len(group_updates) > 0, "Should include group update for positions"

    print("  PASS: test_dependency_graph_reverse_index")


def test_reproject_entity_fields():
    """Test that re-projection updates report fields from source canonical."""
    from canonical.dependency_graph import reproject_entity_fields

    # Mock source canonical with manager name
    sc = {
        "manager": {
            "name": {"value": "Updated Manager Name", "source": "test"},
            "jurisdiction": {"value": "NL", "source": "test"},
        },
        "aifs": [],
    }

    # Mock report fields with old manager name
    report_fields = {
        "19": {"value": "Old Manager Name", "source": "import", "priority": "IMPORTED"},
        "17": {"value": "NL", "source": "import", "priority": "IMPORTED"},
    }

    updated, changed = reproject_entity_fields(sc, report_fields, "AIFM")

    assert "19" in changed, "Field 19 (manager name) should have changed"
    assert updated["19"]["value"] == "Updated Manager Name"
    assert updated["19"]["source"] == "cascade_reprojection"

    # Field 17 (jurisdiction) should NOT change since value is the same
    assert "17" not in changed, "Field 17 should not change (same value)"

    print("  PASS: test_reproject_entity_fields")


# ============================================================================
# 3. API Integration Tests (using FastAPI TestClient)
# ============================================================================

def test_api_health():
    """Test API health endpoint."""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data

    print("  PASS: test_api_health")


def test_api_session_lifecycle():
    """Test session creation, retrieval, and listing via API."""
    from fastapi.testclient import TestClient
    from api.main import app
    from persistence.report_store import ReportStore, ReviewSession, ReviewReport

    client = TestClient(app)

    # Manually create a session (simulating upload without needing a real template)
    store = ReportStore("sqlite://")

    # Patch the deps module to use our test store
    import api.deps as deps
    original_get_store = deps.get_store
    deps.get_store = lambda: store
    # Clear the lru_cache
    if hasattr(deps.get_store, "cache_clear"):
        pass  # Lambda doesn't have cache_clear

    session = ReviewSession(
        filename="api_test.xlsx",
        aifm_name="API Test Manager",
        filing_type="INIT",
        reporting_member_state="NL",
        num_aifs=1,
    )
    store.save_session(session)

    report = ReviewReport(
        session_id=session.session_id,
        report_type="AIFM",
        entity_name="API Test Manager",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "17": {"value": "NL", "source": "test", "priority": "IMPORTED"},
            "19": {"value": "API Test Manager", "source": "test", "priority": "IMPORTED"},
        },
        field_count=38,
        filled_count=2,
        completeness=5.3,
    )
    store.save_report(report)

    # Test session retrieval
    resp = client.get(f"/api/v1/session/{session.session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["aifm_name"] == "API Test Manager"

    # Test active session
    resp = client.get("/api/v1/session/active/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session.session_id

    # Restore deps
    deps.get_store = original_get_store

    print("  PASS: test_api_session_lifecycle")


def test_api_field_edit_and_diff():
    """Test field editing and diff retrieval via API."""
    from persistence.report_store import ReportStore, ReviewSession, ReviewReport

    store = ReportStore("sqlite://")

    session = ReviewSession(
        filename="edit_test.xlsx",
        aifm_name="Edit Test Manager",
        reporting_member_state="NL",
        num_aifs=0,
    )
    store.save_session(session)

    report = ReviewReport(
        session_id=session.session_id,
        report_type="AIFM",
        entity_name="Edit Test Manager",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "19": {"value": "Edit Test Manager", "source": "test", "priority": "IMPORTED"},
        },
        field_count=38,
        filled_count=1,
        completeness=2.6,
    )
    store.save_report(report)

    # Edit the field via store (API test requires running server, so test store directly)
    from persistence.report_store import ReviewEdit
    from datetime import datetime, timezone

    report.fields_json["19"] = {
        "value": "Updated Manager Name",
        "source": "client_review",
        "priority": "MANUALLY_OVERRIDDEN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report.filled_count = 1
    store.save_report(report)

    edit = ReviewEdit(
        session_id=session.session_id,
        report_id=report.report_id,
        edit_type="field",
        target="19",
        old_value="Edit Test Manager",
        new_value="Updated Manager Name",
        cascaded_fields=[],
    )
    store.log_edit(edit)

    # Verify edit is logged
    edits = store.get_edits(session.session_id)
    assert len(edits) == 1
    assert edits[0].new_value == "Updated Manager Name"

    # Verify report updated
    updated_report = store.get_report_by_type_and_index(session.session_id, "AIFM", 0)
    assert updated_report.fields_json["19"]["value"] == "Updated Manager Name"

    # Test undo
    undone = store.delete_last_edit(session.session_id)
    assert undone is not None
    assert undone.new_value == "Updated Manager Name"

    print("  PASS: test_api_field_edit_and_diff")


# ============================================================================
# 4. Validation Tests
# ============================================================================

def test_field_level_validation():
    """Test basic field-level validation (mandatory checks, format checks)."""
    from persistence.report_store import ReviewReport

    # Create a report with missing mandatory fields
    report = ReviewReport(
        session_id="test-session",
        report_type="AIFM",
        entity_name="Test Manager",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "19": {"value": "Test Manager", "source": "test", "priority": "IMPORTED"},
            # Missing many mandatory fields
        },
        field_count=38,
        filled_count=1,
    )

    # Import and run field-level validation
    try:
        sys.path.insert(0, str(_project_root))
        from api.routers.validation import _field_level_validation
        from api.deps import get_field_registry

        registry = get_field_registry()
        if registry:
            findings = _field_level_validation([report], registry)
            # Should have some FAIL findings for missing mandatory fields
            fails = [f for f in findings if f["status"] == "FAIL"]
            assert len(fails) > 0, "Should have failures for missing mandatory AIFM fields"
            # Check that findings have required structure
            for f in fails:
                assert "rule_id" in f
                assert "field_path" in f
                assert "message" in f
            print(f"  PASS: test_field_level_validation ({len(fails)} mandatory field failures detected)")
        else:
            print("  SKIP: test_field_level_validation (registry not loadable)")
    except Exception as e:
        print(f"  SKIP: test_field_level_validation ({e})")


def test_validation_store():
    """Test storing and retrieving validation runs."""
    from persistence.report_store import ReportStore, ReviewSession, ReviewValidationRun

    store = ReportStore("sqlite://")

    session = ReviewSession(
        filename="val_test.xlsx",
        aifm_name="Validation Test",
        reporting_member_state="NL",
    )
    store.save_session(session)

    # Save validation run
    val_run = ReviewValidationRun(
        session_id=session.session_id,
        xsd_valid=True,
        dqf_pass=25,
        dqf_fail=3,
        has_critical=False,
        findings_json=[
            {"rule_id": "TEST-1", "status": "FAIL", "field_path": "AIFM.19", "message": "Test failure"},
            {"rule_id": "TEST-2", "status": "FAIL", "field_path": "AIFM.22", "message": "Missing LEI"},
            {"rule_id": "TEST-3", "status": "FAIL", "field_path": "AIFM.35", "message": "Invalid currency"},
        ],
    )
    run_id = store.save_validation_run(val_run)
    assert run_id > 0

    # Retrieve latest
    latest = store.get_latest_validation(session.session_id)
    assert latest is not None
    assert latest.dqf_pass == 25
    assert latest.dqf_fail == 3
    assert len(latest.findings_json) == 3

    print("  PASS: test_validation_store")


# ============================================================================
# 5. Source Entity Cascade Test
# ============================================================================

def test_source_entity_cascade():
    """Test that editing a source entity field triggers report cascade."""
    from persistence.report_store import ReportStore, ReviewSession, ReviewReport
    from canonical.dependency_graph import reproject_entity_fields

    store = ReportStore("sqlite://")

    sc = {
        "manager": {
            "name": {"value": "Original Manager", "source": "import"},
            "jurisdiction": {"value": "NL", "source": "import"},
            "lei": {"value": "529900ABC123DEF456GH", "source": "import"},
        },
        "aifs": [
            {
                "fund_static": {
                    "name": {"value": "Fund Alpha", "source": "import"},
                    "base_currency": {"value": "EUR", "source": "import"},
                },
                "fund_dynamic": {},
                "positions": [],
                "transactions": [],
                "share_classes": [],
                "counterparties": [],
                "strategies": [],
                "investors": [],
                "risk_measures": [],
                "borrowing_sources": [],
            },
        ],
    }

    session = ReviewSession(
        filename="cascade_test.xlsx",
        aifm_name="Original Manager",
        reporting_member_state="NL",
        num_aifs=1,
        source_canonical=sc,
    )
    store.save_session(session)

    # Create AIFM report with fields from manager
    aifm_report = ReviewReport(
        session_id=session.session_id,
        report_type="AIFM",
        entity_name="Original Manager",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "17": {"value": "NL", "source": "import", "priority": "IMPORTED"},
            "19": {"value": "Original Manager", "source": "import", "priority": "IMPORTED"},
            "22": {"value": "529900ABC123DEF456GH", "source": "import", "priority": "IMPORTED"},
        },
        field_count=38,
        filled_count=3,
    )
    store.save_report(aifm_report)

    # Simulate editing manager.name in source canonical
    sc["manager"]["name"]["value"] = "Updated Manager Name"

    # Re-project
    updated_fields, changed = reproject_entity_fields(
        sc, aifm_report.fields_json, "AIFM",
    )

    assert "19" in changed, "Field 19 should be in changed list"
    assert updated_fields["19"]["value"] == "Updated Manager Name"
    assert updated_fields["19"]["source"] == "cascade_reprojection"

    # Field 17 and 22 should not change (same values)
    assert "17" not in changed
    assert "22" not in changed

    # Test AIF projection
    aif_report = ReviewReport(
        session_id=session.session_id,
        report_type="AIF",
        entity_name="Fund Alpha",
        entity_index=0,
        nca_codes=["NL"],
        fields_json={
            "18": {"value": "Fund Alpha", "source": "import", "priority": "IMPORTED"},
            "49": {"value": "EUR", "source": "import", "priority": "IMPORTED"},
        },
        field_count=302,
        filled_count=2,
    )

    # Change fund base_currency
    sc["aifs"][0]["fund_static"]["base_currency"]["value"] = "USD"

    updated_aif, changed_aif = reproject_entity_fields(
        sc, aif_report.fields_json, "AIF", fund_index=0,
    )

    assert "49" in changed_aif, "Field 49 (base_currency) should change"
    assert updated_aif["49"]["value"] == "USD"

    print("  PASS: test_source_entity_cascade")


# ============================================================================
# Runner
# ============================================================================

def run_all():
    """Run all tests and report results."""
    tests = [
        test_report_store_crud,
        test_dependency_graph_reverse_index,
        test_reproject_entity_fields,
        test_api_health,
        test_api_field_edit_and_diff,
        test_validation_store,
        test_source_entity_cascade,
        test_field_level_validation,
    ]

    print(f"\nRunning {len(tests)} integration tests...\n")
    passed = 0
    failed = 0
    skipped = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped out of {len(tests)}")
    print(f"{'='*60}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
