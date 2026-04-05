# Local LEI enrichment test — runs against your PostgreSQL database.
#
# Simulates a SourceCanonical with entities that match your GLEIF cache
# (the 10 BlackRock records + any others you've fetched).
#
# Run:  python Application\reference_data\test_enrichment_local.py

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    from reference_data.config import get_store
    from canonical.aifmd_source_entities import (
        SourceCanonical, ManagerStatic, FundStatic,
        Counterparty, Position,
    )
    from canonical.provenance import SourcePriority
    from shared.lei_enrichment import enrich_lei_fields, apply_user_choice

    store = get_store()

    # Show what's in the GLEIF cache
    print("=" * 70)
    print("GLEIF cache contents:")
    print("=" * 70)
    with store._cursor() as cur:
        cur.execute(f"""
            SELECT lei, legal_name, normalized_name, country
            FROM {store._t('gleif_lei_cache')}
            ORDER BY legal_name
        """)
        for row in cur.fetchall():
            print(f"  {row[0].strip():22s}  {row[3].strip():4s}  {row[2]:30s}  {row[1]}")

    print(f"\nTotal: {store.get_lei_count()} records")

    # Build a synthetic SourceCanonical
    print("\n" + "=" * 70)
    print("Building test SourceCanonical...")
    print("=" * 70)

    sc = SourceCanonical()

    # Manager — name matches "BlackRock, Inc." (US)
    # Since there are multiple "BLACKROCK" entries, this should be PENDING
    manager = ManagerStatic()
    manager.set("name", "BlackRock", source="test", priority=SourcePriority.IMPORTED)
    manager.set("jurisdiction", "US", source="test", priority=SourcePriority.IMPORTED)
    sc.manager = manager
    print("  Manager: name='BlackRock', jurisdiction='US', lei=<empty>")

    # Fund — name that won't match anything
    fund = FundStatic()
    fund.set("name", "Eagle Test Fund Alpha", source="test", priority=SourcePriority.IMPORTED)
    fund.set("domicile", "NL", source="test", priority=SourcePriority.IMPORTED)
    sc.fund_static = fund
    print("  Fund: name='Eagle Test Fund Alpha', domicile='NL', lei=<empty>")

    # Counterparty 0 — "Blackrock College" (unique in cache, IE)
    cp0 = Counterparty()
    cp0.set("name", "Blackrock College", source="test", priority=SourcePriority.IMPORTED)
    sc.counterparties.append(cp0)
    print("  Counterparty[0]: name='Blackrock College', lei=<empty>")

    # Counterparty 1 — "BLACKROCK FRANCE" (unique in cache, FR)
    cp1 = Counterparty()
    cp1.set("name", "Blackrock France", source="test", priority=SourcePriority.IMPORTED)
    sc.counterparties.append(cp1)
    print("  Counterparty[1]: name='Blackrock France', lei=<empty>")

    # Counterparty 2 — already has LEI (should be SKIPPED)
    cp2 = Counterparty()
    cp2.set("name", "BlackRock, Inc.", source="test", priority=SourcePriority.IMPORTED)
    cp2.set("lei", "529900VBK42Y5HHRMD23", source="test", priority=SourcePriority.IMPORTED)
    sc.counterparties.append(cp2)
    print("  Counterparty[2]: name='BlackRock, Inc.', lei='529900VBK42Y5HHRMD23' (pre-filled)")

    # Position — counterparty name "BEST BLACKROCK" (unique in cache, LU)
    pos = Position()
    pos.set("counterparty_name", "Best Blackrock", source="test", priority=SourcePriority.IMPORTED)
    sc.positions.append(pos)
    print("  Position[0]: counterparty_name='Best Blackrock', counterparty_lei=<empty>")

    # Run enrichment
    print("\n" + "=" * 70)
    print("Running LEI enrichment...")
    print("=" * 70)

    log = enrich_lei_fields(sc, store)

    # Print results
    print("\n" + "=" * 70)
    print("Enrichment Results")
    print("=" * 70)
    for action in log.actions:
        status_icon = {
            "ENRICHED": "V",
            "PENDING_USER_CHOICE": "?",
            "NO_MATCH": "X",
            "SKIPPED": "-",
            "ERROR": "!",
        }.get(action.status.value, " ")

        print(f"\n  [{status_icon}] {action.entity_type}[{action.entity_index}].{action.lei_field}")
        print(f"      Name: '{action.entity_name}'")
        print(f"      Normalized: '{action.normalized_name}'")
        print(f"      Status: {action.status.value}")

        if action.status.value == "ENRICHED":
            print(f"      Enriched LEI: {action.enriched_lei}")
            fv = None
            if action.entity_type == "ManagerStatic":
                fv = sc.manager.get_field(action.lei_field)
            elif action.entity_type == "FundStatic":
                fv = sc.fund_static.get_field(action.lei_field)
            elif action.entity_type == "Counterparty":
                fv = sc.counterparties[action.entity_index].get_field(action.lei_field)
            elif action.entity_type == "Position":
                fv = sc.positions[action.entity_index].get_field(action.lei_field)
            if fv:
                print(f"      Provenance: source='{fv.source}', priority={fv.priority.name}")
                print(f"      Note: {fv.note}")

        elif action.status.value == "PENDING_USER_CHOICE":
            print(f"      Candidates ({len(action.candidates)}):")
            for i, c in enumerate(action.candidates):
                print(f"        [{i+1}] {c['lei']}  {c['country']}  '{c['legal_name']}'")

        elif action.status.value == "SKIPPED":
            print(f"      Original LEI: {action.original_lei}")

        print(f"      Message: {action.message}")

    # Summary
    print("\n" + "=" * 70)
    print(log.summary())
    print("=" * 70)

    # Demo: apply_user_choice for the first PENDING action
    pending = log.get_pending_actions()
    if pending:
        print(f"\nDemo: auto-resolving first PENDING action...")
        first_pending = pending[0]
        if first_pending.candidates:
            chosen = first_pending.candidates[0]
            print(f"  Choosing: {chosen['lei']} ({chosen['legal_name']}, {chosen['country']})")
            apply_user_choice(sc, first_pending, chosen["lei"])
            print(f"  Result: status={first_pending.status.value}, lei={first_pending.enriched_lei}")
            fv = None
            if first_pending.entity_type == "ManagerStatic":
                fv = sc.manager.get_field(first_pending.lei_field)
            if fv:
                print(f"  Provenance: source='{fv.source}', priority={fv.priority.name}")

    # UI flagging data
    print("\n" + "=" * 70)
    print("Fields flagged as enriched (for review UI):")
    print("=" * 70)
    for ef in log.get_enriched_fields():
        print(f"  {ef['entity_type']}[{ef['entity_index']}].{ef['lei_field']} = {ef['enriched_lei']}  (basis: '{ef['basis']}')")

    store.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
