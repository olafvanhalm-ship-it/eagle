#!/usr/bin/env python3
"""
Integration test for M adapter ↔ Canonical model roundtrip.

Tests that:
1. Loading an M template and calling to_canonical_aifm() / to_canonical_aifs() produces
   canonical reports with reasonable field counts
2. Reconstructing via from_canonical() and generating XML produces identical output
   (after normalizing timestamps)

Usage:
    python test_canonical_roundtrip.py
"""

import hashlib
import logging
import re
import sys
import tempfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GOLDEN_SET = _SCRIPT_DIR / "golden_set"
_TEST_TEMPLATE = (
    _GOLDEN_SET / "m_multi_nca" / "Granite_Peak_Capital_AIFMD_Q3_2024.xlsx"
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def normalize_xml(content: bytes) -> bytes:
    """Remove non-deterministic parts from XML for stable comparison."""
    text = content.decode("utf-8")
    # Strip CreationDateAndTime attribute (changes every run)
    text = re.sub(r'CreationDateAndTime="[^"]*"', 'CreationDateAndTime="NORMALIZED"', text)
    return text.encode("utf-8")


def compute_xml_hash(content: bytes) -> str:
    """Compute SHA-256 hash of normalized XML."""
    normalized = normalize_xml(content)
    return hashlib.sha256(normalized).hexdigest()


def test_roundtrip():
    """Run the full roundtrip test."""
    from m_adapter import MAdapter

    if not _TEST_TEMPLATE.exists():
        log.error(f"Test template not found: {_TEST_TEMPLATE}")
        return False

    log.info(f"Loading template: {_TEST_TEMPLATE}")
    adapter_original = MAdapter(str(_TEST_TEMPLATE))

    # Step 1: Convert to canonical
    log.info("Converting to canonical...")
    aifm_canonical = adapter_original.to_canonical_aifm()
    aif_canonicals = adapter_original.to_canonical_aifs()

    log.info(f"AIFM canonical: {len(aifm_canonical.fields)} scalar fields, "
             f"{sum(len(items) for items in aifm_canonical.groups.values())} group items")
    log.info(f"AIF canonicals: {len(aif_canonicals)} AIFs")

    # Verify field counts
    if len(aifm_canonical.fields) < 10:
        log.error(f"AIFM has too few fields: {len(aifm_canonical.fields)} (expected > 10)")
        return False

    for i, aif_report in enumerate(aif_canonicals):
        if len(aif_report.fields) < 20:
            log.warning(f"AIF #{i} has only {len(aif_report.fields)} fields (expected > 20)")
            # Don't fail on this — some templates may have fewer fields

    # Step 2: Reconstruct from canonical
    log.info("Reconstructing from canonical...")
    adapter_reconstructed = MAdapter.from_canonical(aifm_canonical, aif_canonicals)

    # Step 3: Generate XML from both adapters
    log.info("Generating XML from original adapter...")
    with tempfile.TemporaryDirectory() as tmpdir1:
        adapter_original.generate_all(output_dir=tmpdir1)
        original_files = sorted(Path(tmpdir1).glob("*.xml"))
        original_hashes = {
            f.name: compute_xml_hash(f.read_bytes()) for f in original_files
        }

    log.info("Generating XML from reconstructed adapter...")
    with tempfile.TemporaryDirectory() as tmpdir2:
        adapter_reconstructed.generate_all(output_dir=tmpdir2)
        reconstructed_files = sorted(Path(tmpdir2).glob("*.xml"))
        reconstructed_hashes = {
            f.name: compute_xml_hash(f.read_bytes()) for f in reconstructed_files
        }

    # Step 4: Compare
    log.info("\n=== Roundtrip Comparison ===")
    all_match = True

    if set(original_hashes.keys()) != set(reconstructed_hashes.keys()):
        log.error("File set mismatch!")
        log.error(f"  Original: {sorted(original_hashes.keys())}")
        log.error(f"  Reconstructed: {sorted(reconstructed_hashes.keys())}")
        all_match = False

    for fname in sorted(set(original_hashes.keys()) | set(reconstructed_hashes.keys())):
        orig_hash = original_hashes.get(fname, "MISSING")
        recon_hash = reconstructed_hashes.get(fname, "MISSING")

        if orig_hash == recon_hash:
            log.info(f"✅ {fname}: MATCH")
        else:
            log.error(f"❌ {fname}: MISMATCH")
            log.error(f"   Original:      {orig_hash}")
            log.error(f"   Reconstructed: {recon_hash}")
            all_match = False

    if all_match:
        log.info("\n✅ Roundtrip test PASSED")
        return True
    else:
        log.error("\n❌ Roundtrip test FAILED")
        return False


if __name__ == "__main__":
    try:
        success = test_roundtrip()
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error(f"Test error: {e}", exc_info=True)
        sys.exit(1)
