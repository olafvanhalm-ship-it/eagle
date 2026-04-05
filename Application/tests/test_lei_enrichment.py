"""End-to-end tests for LEI enrichment engine.

Tests against a synthetic SourceCanonical with a fresh SQLite GLEIF cache.
Verifies:
  - Single match → auto-enriched (DERIVED priority)
  - Multiple matches → PENDING_USER_CHOICE with candidates
  - No match → NO_MATCH
  - LEI already present → SKIPPED
  - Empty name → NO_MATCH
  - apply_user_choice() resolves PENDING actions
  - Provenance metadata (source, priority, note) is correct
  - EnrichmentLog summary and serialization
  - Only populated entities are processed (no phantom enrichments)
"""

import sys
from pathlib import Path

app_root = Path(__file__).resolve().parent / "mnt" / "Mijn Drive (olaf.van.halm@maxxmanagement.nl)--Project Eagle" / "Application"
sys.path.insert(0, str(app_root))

from canonical.aifmd_source_entities import (
    SourceCanonical, ManagerStatic, FundStatic,
    Counterparty, Position, BorrowingSource,
    ControlledCompany, ControlledStructure,
)
from canonical.provenance import SourcePriority
from shared.reference_store import ReferenceStore
from shared.lei_enrichment import (
    enrich_lei_fields, apply_user_choice,
    EnrichmentStatus, EnrichmentLog,
)


# ── Setup ────────────────────────────────────────────────────────────

def create_test_store() -> ReferenceStore:
    """Create an in-memory SQLite store with synthetic GLEIF records."""
    store = ReferenceStore.sqlite(":memory:")
    store.upsert_lei([
        # Unique match — "BNPPARIBAS" only appears once
        {
            "lei": "R0MUWSFPU8MPRO8K5P83",
            "legal_name": "BNP Paribas SA",
            "entity_status": "ACTIVE",
            "country": "FR",
            "expires_at": "2099-12-31T00:00:00",
        },
        # Multiple matches for "BLACKROCK" — three countries
        {
            "lei": "529900VBK42Y5HHRMD23",
            "legal_name": "BlackRock, Inc.",
            "entity_status": "ACTIVE",
            "country": "US",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "7437007P21315U21VF14",
            "legal_name": "Blackrock Oy",
            "entity_status": "ACTIVE",
            "country": "FI",
            "expires_at": "2099-12-31T00:00:00",
        },
        {
            "lei": "8156001FAF5D93FA9218",
            "legal_name": "BLACKROCK S.R.L.",
            "entity_status": "ACTIVE",
            "country": "IT",
            "expires_at": "2099-12-31T00:00:00",
        },
        # Unique: Deutsche Bank
        {
            "lei": "529900HNOAA1KXQJUQ27",
            "legal_name": "Deutsche Bank Aktiengesellschaft",
            "entity_status": "ACTIVE",
            "country": "DE",
            "expires_at": "2099-12-31T00:00:00",
        },
        # Unique: Goldman Sachs
        {
            "lei": "HWUPKR0MPOU8FGXBT394",
            "legal_name": "The Goldman Sachs Group, Inc.",
            "entity_status": "ACTIVE",
            "country": "US",
            "expires_at": "2099-12-31T00:00:00",
        },
    ])
    return store


def create_test_canonical() -> SourceCanonical:
    """Create a synthetic SourceCanonical mimicking a parsed M template.

    Simulates:
    - Manager: name=BNP Paribas, lei=empty (should ENRICH, single match)
    - Fund: name=BlackRock Fund, lei=empty (should NO_MATCH, "BLACKROCKFUND" not in DB)
    - Counterparty 0: name=Goldman Sachs, lei=empty (should ENRICH, single match)
    - Counterparty 1: name=BlackRock, lei=empty (should PENDING, multiple matches)
    - Counterparty 2: name=Deutsche Bank, lei=529900HNOAA1KXQJUQ27 (should SKIP)
    - Position 0: counterparty_name=BNP Paribas, lei=empty (should ENRICH)
    - Controlled company: name=Totally Unknown Inc., lei=empty (should NO_MATCH)
    """
    sc = SourceCanonical()

    # Manager — empty LEI, known name
    manager = ManagerStatic()
    manager.set("name", "BNP Paribas", source="m_adapter", priority=SourcePriority.IMPORTED)
    manager.set("jurisdiction", "FR", source="m_adapter", priority=SourcePriority.IMPORTED)
    sc.manager = manager

    # Fund — name won't match exactly
    fund = FundStatic()
    fund.set("name", "BlackRock Fund", source="m_adapter", priority=SourcePriority.IMPORTED)
    fund.set("domicile", "LU", source="m_adapter", priority=SourcePriority.IMPORTED)
    sc.fund_static = fund

    # Counterparties
    cp0 = Counterparty()
    cp0.set("name", "Goldman Sachs Group", source="m_adapter", priority=SourcePriority.IMPORTED)
    # No LEI → should enrich (single match for GOLDMANSACHS)

    cp1 = Counterparty()
    cp1.set("name", "BlackRock", source="m_adapter", priority=SourcePriority.IMPORTED)
    # No LEI → should be PENDING (3 matches for BLACKROCK)

    cp2 = Counterparty()
    cp2.set("name", "Deutsche Bank AG", source="m_adapter", priority=SourcePriority.IMPORTED)
    cp2.set("lei", "529900HNOAA1KXQJUQ27", source="m_adapter", priority=SourcePriority.IMPORTED)
    # LEI already present → should SKIP

    sc.counterparties = [cp0, cp1, cp2]

    # Positions
    pos0 = Position()
    pos0.set("counterparty_name", "BNP Paribas S.A.", source="m_adapter", priority=SourcePriority.IMPORTED)
    # Empty counterparty_lei → should enrich

    sc.positions = [pos0]

    # Controlled company with unknown name
    cc = ControlledCompany()
    cc.set("company_name", "Totally Unknown Inc.", source="m_adapter", priority=SourcePriority.IMPORTED)
    sc.controlled_companies = [cc]

    # Deliberately leave these empty — no borrowing sources, no controlled structures
    # Enrichment should produce zero actions for empty collections

    return sc


# ── Tests ────────────────────────────────────────────────────────────

def test_enrichment_decisions():
    """Verify correct enrichment status for each entity."""
    print("\n=== Test: Enrichment Decisions ===")
    store = create_test_store()
    sc = create_test_canonical()

    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # Helper: find action by entity type + index + lei_field
    def find(entity_type, index=0, lei_field="lei"):
        return next(
            (a for a in log.actions
             if a.entity_type == entity_type
             and a.entity_index == index
             and a.lei_field == lei_field),
            None,
        )

    # Manager: BNP Paribas → single match → ENRICHED
    total += 1
    a = find("ManagerStatic")
    ok = a and a.status == EnrichmentStatus.ENRICHED and a.enriched_lei == "R0MUWSFPU8MPRO8K5P83"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Manager (BNP Paribas): {a.status.value if a else 'NOT FOUND'}, lei={a.enriched_lei if a else ''}")

    # Fund: BlackRock Fund → "Fund" stripped → "BLACKROCK" → 3 matches → PENDING
    total += 1
    a = find("FundStatic")
    ok = a and a.status == EnrichmentStatus.PENDING_USER_CHOICE
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Fund (BlackRock Fund → BLACKROCK): {a.status.value if a else 'NOT FOUND'}, candidates={len(a.candidates) if a else 0}")

    # Counterparty 0: Goldman Sachs → single match → ENRICHED
    total += 1
    a = find("Counterparty", 0)
    ok = a and a.status == EnrichmentStatus.ENRICHED and a.enriched_lei == "HWUPKR0MPOU8FGXBT394"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[0] (Goldman Sachs): {a.status.value if a else 'NOT FOUND'}, lei={a.enriched_lei if a else ''}")

    # Counterparty 1: BlackRock → multiple matches → PENDING
    total += 1
    a = find("Counterparty", 1)
    ok = a and a.status == EnrichmentStatus.PENDING_USER_CHOICE and len(a.candidates) == 3
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[1] (BlackRock): {a.status.value if a else 'NOT FOUND'}, candidates={len(a.candidates) if a else 0}")

    # Counterparty 2: Deutsche Bank → LEI already present → SKIPPED
    total += 1
    a = find("Counterparty", 2)
    ok = a and a.status == EnrichmentStatus.SKIPPED
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[2] (Deutsche Bank): {a.status.value if a else 'NOT FOUND'}")

    # Position 0: BNP Paribas → single match → ENRICHED
    total += 1
    a = find("Position", 0, "counterparty_lei")
    ok = a and a.status == EnrichmentStatus.ENRICHED and a.enriched_lei == "R0MUWSFPU8MPRO8K5P83"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Position[0] counterparty_lei: {a.status.value if a else 'NOT FOUND'}, lei={a.enriched_lei if a else ''}")

    # Controlled company: Unknown → NO_MATCH
    total += 1
    a = find("ControlledCompany", 0)
    ok = a and a.status == EnrichmentStatus.NO_MATCH
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] ControlledCompany[0] (Unknown): {a.status.value if a else 'NOT FOUND'}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


def test_provenance_metadata():
    """Verify enriched fields have correct provenance (source, priority, note)."""
    print("\n=== Test: Provenance Metadata ===")
    store = create_test_store()
    sc = create_test_canonical()
    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # Manager LEI should now have a FieldValue with DERIVED priority
    total += 1
    fv = sc.manager.get_field("lei")
    ok = (
        fv is not None
        and fv.value == "R0MUWSFPU8MPRO8K5P83"
        and fv.priority == SourcePriority.DERIVED
        and fv.source == "lei_enrichment"
        and "Auto-enriched" in (fv.note or "")
    )
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Manager.lei provenance: "
          f"value={fv.value if fv else 'None'}, "
          f"priority={fv.priority.name if fv else 'None'}, "
          f"source={fv.source if fv else 'None'}")

    # Counterparty[0] LEI: Goldman Sachs → DERIVED
    total += 1
    fv = sc.counterparties[0].get_field("lei")
    ok = fv is not None and fv.priority == SourcePriority.DERIVED
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[0].lei priority: {fv.priority.name if fv else 'None'}")

    # Counterparty[1] LEI: BlackRock → should NOT be set (PENDING)
    total += 1
    fv = sc.counterparties[1].get_field("lei")
    ok = fv is None  # Not enriched — pending user choice
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[1].lei not set (PENDING): {fv is None}")

    # Counterparty[2] LEI: still IMPORTED priority (not overwritten)
    total += 1
    fv = sc.counterparties[2].get_field("lei")
    ok = fv is not None and fv.priority == SourcePriority.IMPORTED
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Counterparty[2].lei still IMPORTED: {fv.priority.name if fv else 'None'}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


def test_apply_user_choice():
    """Verify that apply_user_choice resolves a PENDING action."""
    print("\n=== Test: Apply User Choice ===")
    store = create_test_store()
    sc = create_test_canonical()
    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # Find the PENDING action for Counterparty[1] (BlackRock)
    pending = next(
        a for a in log.actions
        if a.status == EnrichmentStatus.PENDING_USER_CHOICE
        and a.entity_type == "Counterparty"
    )

    # User picks the US BlackRock
    apply_user_choice(sc, pending, "529900VBK42Y5HHRMD23")

    # The action should now be ENRICHED
    total += 1
    ok = pending.status == EnrichmentStatus.ENRICHED and pending.enriched_lei == "529900VBK42Y5HHRMD23"
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Action updated: status={pending.status.value}, lei={pending.enriched_lei}")

    # The entity should have the LEI set with MANUALLY_OVERRIDDEN priority
    total += 1
    fv = sc.counterparties[1].get_field("lei")
    ok = (
        fv is not None
        and fv.value == "529900VBK42Y5HHRMD23"
        and fv.priority == SourcePriority.MANUALLY_OVERRIDDEN
        and fv.source == "lei_enrichment_user_choice"
    )
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Entity updated: "
          f"value={fv.value if fv else 'None'}, "
          f"priority={fv.priority.name if fv else 'None'}, "
          f"source={fv.source if fv else 'None'}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


def test_empty_collections_no_phantom():
    """Verify no enrichment actions for empty collections (e.g., no borrowing sources)."""
    print("\n=== Test: No Phantom Enrichment ===")
    store = create_test_store()
    sc = create_test_canonical()
    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # BorrowingSource: empty collection → no actions
    total += 1
    bs_actions = [a for a in log.actions if a.entity_type == "BorrowingSource"]
    ok = len(bs_actions) == 0
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] BorrowingSource: {len(bs_actions)} actions (expected 0)")

    # ControlledStructure: empty collection → no actions
    total += 1
    cs_actions = [a for a in log.actions if a.entity_type == "ControlledStructure"]
    ok = len(cs_actions) == 0
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] ControlledStructure: {len(cs_actions)} actions (expected 0)")

    # Instrument: empty collection → no actions
    total += 1
    inst_actions = [a for a in log.actions if a.entity_type == "Instrument"]
    ok = len(inst_actions) == 0
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Instrument: {len(inst_actions)} actions (expected 0)")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


def test_enrichment_log_summary():
    """Verify EnrichmentLog summary and serialization."""
    print("\n=== Test: Enrichment Log ===")
    store = create_test_store()
    sc = create_test_canonical()
    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # Summary counts
    total += 1
    ok = log.enriched_count == 3  # Manager, Counterparty[0], Position[0]
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] enriched_count={log.enriched_count} (expected 3)")

    total += 1
    ok = log.pending_count == 2  # Fund (BLACKROCK) + Counterparty[1]
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] pending_count={log.pending_count} (expected 2)")

    total += 1
    ok = log.no_match_count == 1  # ControlledCompany only
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] no_match_count={log.no_match_count} (expected 1)")

    total += 1
    ok = log.skipped_count == 1  # Counterparty[2]
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] skipped_count={log.skipped_count} (expected 1)")

    # Serialization
    total += 1
    d = log.to_dict()
    ok = "actions" in d and "summary" in d and d["summary"]["enriched"] == 3
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] to_dict() has {len(d.get('actions', []))} actions, summary.enriched={d.get('summary', {}).get('enriched')}")

    # get_pending_actions
    total += 1
    pending = log.get_pending_actions()
    ok = len(pending) == 2  # Fund + Counterparty[1]
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] get_pending_actions(): {len(pending)} actions (expected 2)")

    # get_enriched_fields (for UI flagging)
    total += 1
    enriched = log.get_enriched_fields()
    ok = len(enriched) == 3
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] get_enriched_fields(): {len(enriched)} fields")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


def test_light_manager_minimal():
    """Simulate a LIGHT manager report — only manager LEI, no counterparties."""
    print("\n=== Test: Light Manager (Minimal) ===")
    store = create_test_store()

    sc = SourceCanonical()
    manager = ManagerStatic()
    manager.set("name", "Deutsche Bank", source="m_adapter", priority=SourcePriority.IMPORTED)
    manager.set("jurisdiction", "DE", source="m_adapter", priority=SourcePriority.IMPORTED)
    sc.manager = manager
    # No fund, no counterparties, no positions — light report

    log = enrich_lei_fields(sc, store)

    passed = 0
    total = 0

    # Should only have actions for manager + fund_static (both are scalar)
    total += 1
    ok = len(log.actions) == 2  # ManagerStatic + FundStatic
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Total actions: {len(log.actions)} (expected 2: manager + fund)")

    # Manager should be enriched
    total += 1
    mgr_action = next((a for a in log.actions if a.entity_type == "ManagerStatic"), None)
    ok = mgr_action and mgr_action.status == EnrichmentStatus.ENRICHED
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Manager enriched: {mgr_action.status.value if mgr_action else 'NOT FOUND'}")

    # Fund should be NO_MATCH (empty name)
    total += 1
    fund_action = next((a for a in log.actions if a.entity_type == "FundStatic"), None)
    ok = fund_action and fund_action.status == EnrichmentStatus.NO_MATCH
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] Fund (no name): {fund_action.status.value if fund_action else 'NOT FOUND'}")

    # No counterparty or other collection actions
    total += 1
    collection_actions = [a for a in log.actions if a.entity_type in ("Counterparty", "Position", "Instrument", "BorrowingSource")]
    ok = len(collection_actions) == 0
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] No collection actions: {len(collection_actions)}")

    store.close()
    print(f"  → {passed}/{total} passed")
    return passed == total


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("LEI Enrichment Engine — End-to-End Tests")
    print("=" * 60)

    all_pass = True
    all_pass &= test_enrichment_decisions()
    all_pass &= test_provenance_metadata()
    all_pass &= test_apply_user_choice()
    all_pass &= test_empty_collections_no_phantom()
    all_pass &= test_enrichment_log_summary()
    all_pass &= test_light_manager_minimal()

    print("\n" + "=" * 60)
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — review output above")
    print("=" * 60)
    sys.exit(0 if all_pass else 1)
