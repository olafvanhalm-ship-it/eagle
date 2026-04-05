"""
AIFMD Annex IV Anonymizer
=========================
Anonymizes client-identifiable data in AIFMD XML files while preserving
structural validity for regression testing.

Handles:
  - XML element content (names, national codes, LEIs, etc.)
  - Filenames (which contain national codes and dates)
  - M adapter Excel templates (source data)
  - Consistent mapping across all files in a batch

Usage:
    python anonymize_aifmd.py input_dir/ --output anonymized/
    python anonymize_aifmd.py file1.xml file2.xml --output anonymized/
    python anonymize_aifmd.py template.xlsx --output anonymized/

The script produces:
  - Anonymized copies of all input files
  - anonymization_map.yaml: the full mapping (CONFIDENTIAL — do not commit)
"""

import argparse
import hashlib
import os
import random
import re
import shutil
import string
import sys
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET

import yaml

# ── Configuration: fields to anonymize ──────────────────────────────────────

# XML elements whose text content is client-identifiable
IDENTITY_ELEMENTS = {
    # Manager-level identifiers
    "AIFMName",
    "AIFMNationalCode",
    "AIFMIdentifierLEI",
    # Fund-level identifiers
    "AIFName",
    "AIFNationalCode",
    "AIFIdentifierLEI",
    # Instrument names (can reveal portfolio strategy)
    "InstrumentName",
    # FCA-specific
    "AssumptionDetails",
}

# Elements where the value is a code that appears in filenames/cross-references
# These need consistent replacement across all files in a batch
CROSS_REFERENCE_ELEMENTS = {
    "AIFMNationalCode",
    "AIFNationalCode",
}

# Elements that are codes/IDs (replaced with synthetic equivalents)
CODE_ELEMENTS = {
    "AIFMNationalCode": "national_code",
    "AIFNationalCode": "national_code",
    "AIFMIdentifierLEI": "lei",
    "AIFIdentifierLEI": "lei",
}

# Elements that are free text (replaced with generic labels)
TEXT_ELEMENTS = {
    "AIFMName": "manager_name",
    "AIFName": "fund_name",
    "InstrumentName": "instrument_name",
    "AssumptionDetails": "assumption_text",
}

# ── Synthetic data generators ───────────────────────────────────────────────

_MANAGER_NAMES = [
    "Acme Capital Management",
    "Blue Ridge Partners",
    "Cedar Point Advisors",
    "Delta Wave Capital",
    "Evergreen Fund Management",
    "Falcon Bridge Investments",
    "Granite Peak Capital",
    "Harbour View Management",
    "Iron Gate Partners",
    "Jade Mountain Advisors",
]

_FUND_NAMES = [
    "Alpha Growth Fund",
    "Beta Income Fund",
    "Gamma Opportunity Fund",
    "Delta Value Fund",
    "Epsilon Balanced Fund",
    "Zeta Infrastructure Fund",
    "Eta Credit Fund",
    "Theta Real Estate Fund",
    "Iota Private Debt Fund",
    "Kappa Venture Fund",
    "Lambda Multi-Strategy Fund",
    "Mu Emerging Markets Fund",
    "Nu Technology Fund",
    "Xi Healthcare Fund",
    "Omicron Energy Fund",
    "Pi Climate Fund",
    "Rho Small-Cap Fund",
    "Sigma Long-Short Fund",
    "Tau Global Macro Fund",
    "Upsilon Distressed Fund",
]

_INSTRUMENT_NAMES = [
    "Listed equity position",
    "Corporate bond holding",
    "Government bond allocation",
    "Real estate investment",
    "Private equity commitment",
    "Cash and cash equivalents",
    "Money market instrument",
    "Derivative position",
    "Fund of funds allocation",
    "Infrastructure investment",
    "Commodity position",
    "Structured product",
    "Convertible bond",
    "Bank deposit",
    "Other asset",
]


class AnonymizationMap:
    """Maintains consistent anonymization mappings across a batch."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.map: Dict[str, Dict[str, str]] = {
            "national_code": {},
            "lei": {},
            "manager_name": {},
            "fund_name": {},
            "instrument_name": {},
            "assumption_text": {},
            "filename": {},
        }
        self._manager_idx = 0
        self._fund_idx = 0
        self._instrument_idx = 0
        self._code_counters: Dict[str, int] = {}

    def _generate_national_code(self, original: str) -> str:
        """Generate a synthetic national code preserving format."""
        # Detect format: alpha prefix + numeric, or pure numeric, etc.
        if re.match(r'^[A-Z]{2,4}\d+$', original):
            # Alphanumeric like BJF094 → XYZ + digits
            prefix_len = len(re.match(r'^[A-Z]+', original).group())
            num_len = len(original) - prefix_len
            prefix = ''.join(self.rng.choices(string.ascii_uppercase, k=prefix_len))
            num = str(self.rng.randint(10**(num_len-1), 10**num_len - 1))
            return prefix + num
        elif re.match(r'^\d+$', original):
            # Pure numeric like 50033846 → random digits same length
            return str(self.rng.randint(10**(len(original)-1), 10**len(original) - 1))
        elif re.match(r'^\d+-\d+$', original):
            # Format like 02694-0001
            parts = original.split('-')
            new_parts = [str(self.rng.randint(10**(len(p)-1), 10**len(p) - 1)) for p in parts]
            return '-'.join(new_parts)
        else:
            # Fallback: random alphanumeric same length
            return ''.join(self.rng.choices(string.ascii_uppercase + string.digits, k=len(original)))

    def _generate_lei(self, original: str) -> str:
        """Generate a synthetic LEI (20 characters: 4 alpha + 14 alnum + 2 check digits)."""
        prefix = ''.join(self.rng.choices(string.digits, k=4))
        middle = ''.join(self.rng.choices(string.ascii_uppercase + string.digits, k=14))
        check = str(self.rng.randint(10, 99))
        return prefix + middle + check

    def get_replacement(self, category: str, original: str) -> str:
        """Get or create a consistent replacement for a value."""
        if not original or not original.strip():
            return original

        original_clean = original.strip()

        if original_clean in self.map[category]:
            return self.map[category][original_clean]

        if category == "national_code":
            replacement = self._generate_national_code(original_clean)
        elif category == "lei":
            replacement = self._generate_lei(original_clean)
        elif category == "manager_name":
            replacement = _MANAGER_NAMES[self._manager_idx % len(_MANAGER_NAMES)]
            self._manager_idx += 1
        elif category == "fund_name":
            replacement = _FUND_NAMES[self._fund_idx % len(_FUND_NAMES)]
            self._fund_idx += 1
        elif category == "instrument_name":
            # Some generic instrument names don't need anonymization
            generic_patterns = [
                "cash", "other", "not applicable", "n/a", "none",
                "money market", "bank deposit",
            ]
            if any(p in original_clean.lower() for p in generic_patterns):
                replacement = original_clean  # Keep generic names
            else:
                replacement = _INSTRUMENT_NAMES[self._instrument_idx % len(_INSTRUMENT_NAMES)]
                self._instrument_idx += 1
        elif category == "assumption_text":
            replacement = (
                "The presented data of this AIFMD reporting is based on "
                "the last official calculated NAV of the fund."
            )
        else:
            replacement = f"ANON_{category}_{len(self.map[category])}"

        self.map[category][original_clean] = replacement
        return replacement

    def save(self, path: Path):
        """Save the anonymization map to YAML."""
        output = {}
        for category, mappings in self.map.items():
            if mappings:
                output[category] = {k: v for k, v in mappings.items() if k != v}
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(output, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)


def anonymize_xml(xml_path: Path, anon_map: AnonymizationMap) -> Tuple[str, str]:
    """
    Anonymize an AIFMD XML file.

    Returns:
        Tuple of (anonymized_xml_content, new_filename)
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    # Strip namespace for element matching
    ns_match = re.match(r'\{(.+)\}', root.tag)
    ns = ns_match.group(1) if ns_match else ''
    ns_prefix = f'{{{ns}}}' if ns else ''

    def find_all_recursive(element, tag):
        """Find all elements with given tag, namespace-aware."""
        results = []
        for child in element.iter():
            local_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local_tag == tag:
                results.append(child)
        return results

    # Anonymize identity elements
    for elem_name in IDENTITY_ELEMENTS:
        category = CODE_ELEMENTS.get(elem_name) or TEXT_ELEMENTS.get(elem_name)
        if not category:
            continue
        for elem in find_all_recursive(root, elem_name):
            if elem.text and elem.text.strip():
                elem.text = anon_map.get_replacement(category, elem.text.strip())

    # Build new filename based on anonymized national codes
    old_name = xml_path.stem  # e.g., AIFM_NL_BJF094_20241231
    new_name = old_name

    # Replace national codes in filename
    for original, replacement in anon_map.map["national_code"].items():
        if original in new_name:
            new_name = new_name.replace(original, replacement)

    # Also check if any code from this file wasn't yet in the map
    # Parse filename pattern: TYPE_RMS_CODE_DATE
    fname_match = re.match(r'^(AIFM?_[A-Z]{2})_(.+?)_(\d{8})$', old_name)
    if fname_match:
        prefix, code, date = fname_match.groups()
        # Determine category based on prefix
        if code in anon_map.map["national_code"]:
            new_code = anon_map.map["national_code"][code]
        else:
            # This code should already have been anonymized in XML processing
            new_code = code
        new_name = f"{prefix}_{new_code}_{date}"

    new_filename = new_name + xml_path.suffix

    # Serialize
    xml_content = ET.tostring(root, encoding='unicode', xml_declaration=False)

    # Preserve original XML declaration and comments
    with open(str(xml_path), 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Extract XML declaration
    decl_match = re.match(r'(<\?xml[^?]*\?>)', original_content)
    xml_decl = decl_match.group(1) if decl_match else '<?xml version="1.0" encoding="UTF-8"?>'

    # Extract comments before root element
    comments = re.findall(r'(<!--.*?-->)', original_content[:500], re.DOTALL)
    comment_str = '\n'.join(comments)
    if comment_str:
        comment_str = '\n' + comment_str

    full_content = xml_decl + comment_str + '\n' + xml_content

    return full_content, new_filename


def anonymize_excel(xlsx_path: Path, anon_map: AnonymizationMap) -> str:
    """
    Anonymize a M adapter Excel template.

    Returns new filename.
    """
    try:
        import openpyxl
    except ImportError:
        print("WARNING: openpyxl not installed, skipping Excel anonymization")
        return xlsx_path.name

    wb = openpyxl.load_workbook(str(xlsx_path))

    # Patterns to detect client-identifiable content in cells
    # We anonymize based on what's already in the map + known field positions
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str):
                    val = cell.value.strip()
                    # Check if this value is in any of our maps
                    for category in ["manager_name", "fund_name", "national_code",
                                     "lei", "instrument_name"]:
                        if val in anon_map.map[category]:
                            cell.value = anon_map.map[category][val]
                            break

    # Generate anonymized filename
    old_name = xlsx_path.stem
    new_name = old_name

    # Replace known names in filename
    for original, replacement in anon_map.map["manager_name"].items():
        # Try various filename patterns
        for pattern in [original, original.replace(" ", "-"), original.replace(" ", "_")]:
            if pattern.lower() in new_name.lower():
                new_name = re.sub(re.escape(pattern), replacement.replace(" ", "-"),
                                  new_name, flags=re.IGNORECASE)

    new_filename = new_name + xlsx_path.suffix
    anon_map.map["filename"][xlsx_path.name] = new_filename

    # Save
    return new_filename, wb


def process_batch(input_paths: List[Path], output_dir: Path, seed: int = 42):
    """
    Anonymize a batch of AIFMD files with consistent mappings.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    anon_map = AnonymizationMap(seed=seed)

    # Phase 1: Process XML files first (to build up the code mappings)
    xml_files = [p for p in input_paths if p.suffix.lower() == '.xml']
    xlsx_files = [p for p in input_paths if p.suffix.lower() == '.xlsx']
    other_files = [p for p in input_paths if p.suffix.lower() not in ('.xml', '.xlsx')]

    # First pass: scan XML files for all identifiable values
    # (This ensures cross-references are consistent)
    print(f"\n{'='*70}")
    print(f"  AIFMD Anonymizer")
    print(f"{'='*70}\n")
    print(f"  Input files: {len(input_paths)}")
    print(f"    XML:  {len(xml_files)}")
    print(f"    XLSX: {len(xlsx_files)}")
    print(f"    Other: {len(other_files)}")
    print(f"  Output: {output_dir}\n")

    # Phase 1: Anonymize XML files
    for xml_path in xml_files:
        print(f"  Processing: {xml_path.name}")
        content, new_filename = anonymize_xml(xml_path, anon_map)
        anon_map.map["filename"][xml_path.name] = new_filename

        out_path = output_dir / new_filename
        with open(str(out_path), 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"    → {new_filename}")

    # Phase 2: Anonymize Excel templates
    for xlsx_path in xlsx_files:
        print(f"  Processing: {xlsx_path.name}")
        new_filename, wb = anonymize_excel(xlsx_path, anon_map)
        out_path = output_dir / new_filename
        wb.save(str(out_path))
        print(f"    → {new_filename}")

    # Phase 3: Handle packaged files (zip, gz)
    for other_path in other_files:
        if other_path.suffix.lower() == '.gz':
            import gzip as gz_mod
            # Read, decompress, anonymize XML inside, recompress
            print(f"  Processing: {other_path.name}")
            with gz_mod.open(str(other_path), 'rb') as f:
                xml_content = f.read()
            # Write temp XML, anonymize, repack
            temp_xml = output_dir / (other_path.stem + '.xml')
            with open(str(temp_xml), 'wb') as f:
                f.write(xml_content)
            content, new_xml_name = anonymize_xml(temp_xml, anon_map)
            temp_xml.unlink()
            new_gz_name = new_xml_name.replace('.xml', '.gz')
            anon_map.map["filename"][other_path.name] = new_gz_name
            out_path = output_dir / new_gz_name
            with gz_mod.open(str(out_path), 'wb') as f:
                f.write(content.encode('utf-8'))
            print(f"    → {new_gz_name}")

        elif other_path.suffix.lower() == '.zip':
            import zipfile
            print(f"  Processing: {other_path.name}")
            # Read ZIP, anonymize XML files inside, repackage
            new_zip_name = other_path.name
            for original, replacement in anon_map.map["national_code"].items():
                new_zip_name = new_zip_name.replace(original, replacement)
            anon_map.map["filename"][other_path.name] = new_zip_name
            out_path = output_dir / new_zip_name
            with zipfile.ZipFile(str(other_path), 'r') as zin:
                with zipfile.ZipFile(str(out_path), 'w', zipfile.ZIP_DEFLATED) as zout:
                    for info in zin.infolist():
                        data = zin.read(info.filename)
                        if info.filename.lower().endswith('.xml'):
                            # Anonymize the XML inside
                            temp_xml = output_dir / info.filename
                            with open(str(temp_xml), 'wb') as f:
                                f.write(data)
                            content, new_inner = anonymize_xml(temp_xml, anon_map)
                            temp_xml.unlink()
                            zout.writestr(new_inner, content.encode('utf-8'))
                        else:
                            zout.writestr(info.filename, data)
            print(f"    → {new_zip_name}")
        else:
            print(f"  Skipping: {other_path.name} (unsupported format)")

    # Save the anonymization map
    map_path = output_dir / "anonymization_map.yaml"
    anon_map.save(map_path)

    # Print summary
    print(f"\n{'─'*70}")
    print(f"  Anonymization complete")
    print(f"{'─'*70}")
    total_mappings = sum(len(v) for v in anon_map.map.values()
                         if isinstance(v, dict))
    print(f"  Total mappings: {total_mappings}")
    for cat, mappings in anon_map.map.items():
        effective = {k: v for k, v in mappings.items() if k != v}
        if effective:
            print(f"    {cat}: {len(effective)} replaced")
    print(f"\n  Map saved: {map_path}")
    print(f"  ⚠  anonymization_map.yaml is CONFIDENTIAL — do not commit to git\n")

    return anon_map


def main():
    parser = argparse.ArgumentParser(
        description="Anonymize AIFMD Annex IV files for regression testing"
    )
    parser.add_argument(
        "inputs", nargs="+",
        help="XML files, Excel templates, or directories to anonymize"
    )
    parser.add_argument(
        "--output", "-o", required=True,
        help="Output directory for anonymized files"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible anonymization (default: 42)"
    )
    args = parser.parse_args()

    # Collect all input files
    input_paths = []
    for inp in args.inputs:
        p = Path(inp)
        if p.is_dir():
            for ext in ('*.xml', '*.xlsx', '*.gz', '*.zip'):
                input_paths.extend(sorted(p.glob(ext)))
        elif p.is_file():
            input_paths.append(p)
        else:
            print(f"WARNING: {inp} not found, skipping")

    if not input_paths:
        print("ERROR: No input files found")
        sys.exit(1)

    output_dir = Path(args.output)
    process_batch(input_paths, output_dir, seed=args.seed)


if __name__ == "__main__":
    main()
