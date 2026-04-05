"""NCA-specific packaging configuration for AIFMD Annex IV XML submissions.

This module defines the packaging requirements for all 31 AIFMD jurisdictions
(30 ESMA + 1 FCA). It is the single source of truth used by:
  - orchestrator.py (to produce the correct packaging)
  - run_regression_suite.py (to validate packaging in tests)
  - validate_aifmd_xml.py (for packaging format checks)

Packaging types:
  "xml"         - Plain XML files, no compression.  ZIP only when multi-AIF
                  delivery requires bundling (convenience, not NCA-mandated).
  "gzip"        - Each XML individually GZIP-compressed (.gz).
  "zip"         - All XMLs bundled in a single ZIP archive.
  "zip-per-file"- Each XML wrapped in its own ZIP (rarely used).
  "zip-in-zip"  - Per-AIF ZIPs bundled inside a master ZIP (LU/CSSF).

Sources:
  - ESMA AIFMD Annex IV reporting IT guidance (2014/869)
  - NCA-specific technical guidance documents (BaFin, FSMA, CSSF, etc.)
  - NCA override rules in regulation/aifmd/annex_iv/nca_overrides/
"""

from typing import TypedDict


class NCAPackagingSpec(TypedDict, total=False):
    """Packaging specification for a single NCA."""
    nca_name: str           # Full NCA name
    packaging: str          # "xml", "gzip", "zip", "zip-per-file", "zip-in-zip"
    pack_desc: str          # Human-readable description
    zip_when_multi: bool    # If packaging="xml", ZIP when multiple AIFs? (default True)
    notes: str              # Implementation notes


NCA_PACKAGING_CONFIG: dict[str, NCAPackagingSpec] = {
    # ── GZIP packaging ──────────────────────────────────────────────────
    "DE": {
        "nca_name": "BaFin",
        "packaging": "gzip",
        "pack_desc": "Each XML individually GZIP-compressed (.gz)",
        "notes": "BaFin MVP portal requires individual .gz files",
    },

    # ── ZIP packaging (mandatory, regardless of file count) ─────────────
    "BE": {
        "nca_name": "FSMA",
        "packaging": "zip",
        "pack_desc": "All XMLs bundled in ZIP",
        "notes": "FSMA eCorporate portal requires ZIP upload",
    },
    "ES": {
        "nca_name": "CNMV",
        "packaging": "zip",
        "pack_desc": "All XMLs bundled in ZIP",
        "notes": "CNMV CIFRADOC/AIFMD portal requires ZIP",
    },
    "PT": {
        "nca_name": "CMVM",
        "packaging": "zip",
        "pack_desc": "All XMLs bundled in ZIP",
        "notes": "CMVM requires ZIP submission",
    },
    "SE": {
        "nca_name": "Finansinspektionen",
        "packaging": "zip",
        "pack_desc": "All XMLs bundled in ZIP",
        "notes": "FI (Sweden) requires ZIP packaging",
    },
    "CZ": {
        "nca_name": "CNB",
        "packaging": "zip",
        "pack_desc": "All XMLs bundled in ZIP",
        "notes": "CNB SDAT system requires ZIP upload",
    },
    "MT": {
        "nca_name": "MFSA",
        "packaging": "zip",
        "pack_desc": "AIFM + AIF XMLs bundled in ZIP",
        "notes": "MFSA LH Portal requires ZIP bundle (DATMAN + DATAIF)",
    },

    # ── ZIP-in-ZIP packaging ────────────────────────────────────────────
    "LU": {
        "nca_name": "CSSF",
        "packaging": "zip-in-zip",
        "pack_desc": "Per-AIF ZIPs bundled in master ZIP",
        "notes": "CSSF SOFIE portal: each AIF XML in own ZIP, all bundled in master ZIP",
    },

    # ── Plain XML packaging (ZIP only when multi-AIF for convenience) ───
    "NL": {
        "nca_name": "AFM",
        "packaging": "xml",
        "pack_desc": "Plain XML (ZIP when multiple AIFs)",
        "zip_when_multi": True,
        "notes": "AFM portal accepts individual XML uploads",
    },
    "GB": {
        "nca_name": "FCA",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "FCA RegData portal accepts individual XML; FCA v2 XSD",
    },
    "FR": {
        "nca_name": "AMF",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "AMF ROSA portal accepts XML uploads",
    },
    "IE": {
        "nca_name": "CBI",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "CBI ONR system accepts individual XML",
    },
    "IT": {
        "nca_name": "CONSOB",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "CONSOB accepts XML via SFTP/portal",
    },
    "AT": {
        "nca_name": "FMA",
        "packaging": "xml",
        "pack_desc": "Plain XML (ZIP when multiple AIFs)",
        "zip_when_multi": True,
        "notes": "FMA reporting portal accepts individual XML",
    },
    "CY": {
        "nca_name": "CySEC",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "CySEC TRS portal; digital signature may be required separately",
    },
    "DK": {
        "nca_name": "Finanstilsynet",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Danish FSA accepts individual XML via portal",
    },
    "FI": {
        "nca_name": "FIN-FSA",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "FIN-FSA reporting system accepts XML",
    },
    "NO": {
        "nca_name": "Finanstilsynet",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Norwegian FSA Altinn portal accepts XML",
    },
    "GR": {
        "nca_name": "HCMC",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "HCMC accepts XML via portal",
    },
    "PL": {
        "nca_name": "KNF",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "KNF reporting portal accepts XML",
    },
    "BG": {
        "nca_name": "FSC",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "FSC Bulgaria accepts XML via portal",
    },
    "HR": {
        "nca_name": "HANFA",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "HANFA reporting portal accepts XML",
    },
    "HU": {
        "nca_name": "MNB",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "MNB CAP/ERA portal — packaging not fully confirmed (out of scope)",
    },
    "EE": {
        "nca_name": "FSA",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Estonian FSA accepts XML",
    },
    "LV": {
        "nca_name": "FKTK",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Latvian FKTK accepts XML",
    },
    "LT": {
        "nca_name": "BoL",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Bank of Lithuania accepts XML",
    },
    "LI": {
        "nca_name": "FMA",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Liechtenstein FMA accepts XML (uses ESMA standard)",
    },
    "RO": {
        "nca_name": "ASF",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Romanian ASF accepts XML",
    },
    "SI": {
        "nca_name": "ATVP",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Slovenian SMA accepts XML",
    },
    "SK": {
        "nca_name": "NBS",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Slovak NBS accepts XML",
    },
    "IS": {
        "nca_name": "FME",
        "packaging": "xml",
        "pack_desc": "Plain XML",
        "zip_when_multi": True,
        "notes": "Icelandic FME (EEA member) accepts XML",
    },
}


def get_expected_extensions(nca: str, num_aifs: int) -> list[str]:
    """Return the list of file extensions expected for a given NCA and AIF count.

    Used by regression suite to predict what packaging artifacts should exist.

    Returns:
        List of expected extensions, e.g. ["gz"], ["zip"], or [] for plain XML.
    """
    spec = NCA_PACKAGING_CONFIG.get(nca, {})
    pkg = spec.get("packaging", "xml")

    if pkg == "gzip":
        return ["gz"]
    elif pkg in ("zip", "zip-per-file", "zip-in-zip"):
        return ["zip"]
    elif pkg == "xml":
        # Plain XML — ZIP only when multi-AIF and zip_when_multi is True
        if num_aifs > 1 and spec.get("zip_when_multi", True):
            return ["zip"]
        return []
    return []
