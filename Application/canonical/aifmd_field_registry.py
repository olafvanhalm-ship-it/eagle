"""AIFMD Annex IV Field Registry.

Loads the validation rules YAML and exposes a structured registry of all
ESMA fields (38 AIFM + 302 AIF) with their metadata: name, section,
data type, format, repetition, XSD element, mandatory/optional status, etc.

The validation rules YAML is the single source of truth — it already
contains all field definitions derived from ESMA Technical Guidance Rev.6.
This module parses it into a form suitable for the canonical model.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReportType(str, Enum):
    """AIFMD report level."""
    AIFM = "AIFM"
    AIF = "AIF"


class DataType(str, Enum):
    """ESMA data type codes."""
    ALPHA = "A"        # Alphanumeric
    NUMERIC = "N"      # Numeric
    DATE = "D"         # Date / datetime
    BOOLEAN = "B"      # Boolean (true/false)
    FREETEXT = "T"     # Free text


class Obligation(str, Enum):
    """Mandatory / Conditional / Optional / Forbidden."""
    MANDATORY = "M"
    CONDITIONAL = "C"
    OPTIONAL = "O"
    FORBIDDEN = "F"


# ---------------------------------------------------------------------------
# Field definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldDef:
    """Immutable definition of a single ESMA Annex IV field."""

    field_id: str                        # "1" .. "302", or "CANC-AIF-1" etc.
    field_name: str                      # Official ESMA field label
    report_type: ReportType              # AIFM or AIF
    section: str                         # Logical grouping
    data_type: DataType                  # A / N / D / B / T
    format: str                          # Regex or format description
    obligation: Obligation               # M / C / O / F
    mandatory: bool                      # Convenience: obligation == M
    repetition: str                      # "[1..1]", "[5..5]", "[0..n]", etc.
    xsd_element: str                     # XML element name
    xml_type: str                        # XSD type name
    severity: str                        # CRITICAL / HIGH / MEDIUM / LOW
    technical_guidance: str              # Full ESMA description
    esma_doc: str                        # Source document reference
    allowed_values_ref: Optional[str]    # Reference table name, if any
    esma_error_codes: list[str] = field(default_factory=list)
    gate_field: Optional[str] = None          # Field ID controlling conditional visibility
    gate_condition: Optional[str] = None      # Condition expression, e.g. not_equals(49, EUR)

    # Derived properties
    @property
    def is_numeric(self) -> bool:
        return self.data_type == DataType.NUMERIC

    @property
    def question_number(self) -> Optional[int]:
        """Return integer question number, or None for special fields."""
        try:
            return int(self.field_id)
        except ValueError:
            return None

    @property
    def max_repetitions(self) -> Optional[int]:
        """Parse repetition string to get max count.

        "[5..5]" → 5, "[0..n]" → None (unbounded), "[1..1]" → 1
        """
        if not self.repetition:
            return 1
        # Extract the upper bound
        parts = self.repetition.strip("[]").split("..")
        upper = parts[-1].strip()
        if upper in ("n", "N"):
            return None  # unbounded
        try:
            return int(upper)
        except ValueError:
            return 1

    @property
    def is_repeating(self) -> bool:
        """True if this field belongs to a repeating group."""
        mx = self.max_repetitions
        return mx is None or mx > 1


# ---------------------------------------------------------------------------
# Repeating group definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RepeatingGroup:
    """A group of fields that repeat together (e.g. 5 main instruments)."""

    name: str                 # Programmatic name: "main_instruments", "exposures_10"
    section: str              # ESMA section name
    report_type: ReportType
    field_ids: tuple[str, ...]  # Ordered list of field_ids in this group
    max_items: Optional[int]    # Max repetitions (None = unbounded)
    min_items: int              # Minimum required items


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class FieldRegistry:
    """Central registry of all AIFMD Annex IV fields.

    Loads from the validation rules YAML and provides fast lookup by
    field_id, section, report_type, or repeating group.
    """

    def __init__(self, rules_path: Optional[Path] = None):
        if rules_path is None:
            # Default: Application/regulation/aifmd/annex_iv/aifmd_validation_rules.yaml
            # This module is at: Application/canonical/field_registry.py
            _app_dir = Path(__file__).resolve().parent.parent
            _regulation_dir = _app_dir / "regulation" / "aifmd" / "annex_iv"
            if not _regulation_dir.is_dir():
                _regulation_dir = _app_dir / "regulation" / "aifmd annex iv"
                if not _regulation_dir.is_dir():
                    _regulation_dir = _app_dir.parent / "Blueprint"
            rules_path = _regulation_dir / "aifmd_validation_rules.yaml"
            if not rules_path.exists():
                rules_path = _regulation_dir / "aifmd_annex_iv_validation_rules.yaml"
        self._rules_path = rules_path
        self._aifm_fields: dict[str, FieldDef] = {}
        self._aif_fields: dict[str, FieldDef] = {}
        self._aifm_sections: dict[str, list[FieldDef]] = {}
        self._aif_sections: dict[str, list[FieldDef]] = {}
        self._repeating_groups: list[RepeatingGroup] = []
        self._reference_tables: dict[str, list] = {}
        self._load()

    def _load(self):
        """Parse the validation rules YAML into FieldDef instances."""
        if not self._rules_path.exists():
            log.warning("Validation rules not found at %s", self._rules_path)
            return

        with open(self._rules_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # Reference tables
        self._reference_tables = raw.get("reference_tables", {})

        # Parse AIFM rules — skip cross-field rules, they are NOT fields
        for rule in raw.get("aifm_rules", []):
            if self._is_cross_field_rule(rule):
                continue
            fdef = self._parse_rule(rule, ReportType.AIFM)
            self._aifm_fields[fdef.field_id] = fdef
            self._aifm_sections.setdefault(fdef.section, []).append(fdef)

        # Parse AIF rules — skip cross-field rules, they are NOT fields
        for rule in raw.get("aif_rules", []):
            if self._is_cross_field_rule(rule):
                continue
            fdef = self._parse_rule(rule, ReportType.AIF)
            self._aif_fields[fdef.field_id] = fdef
            self._aif_sections.setdefault(fdef.section, []).append(fdef)

        # Build repeating groups
        self._build_repeating_groups()

        log.info(
            "Field registry loaded: %d AIFM fields, %d AIF fields, %d repeating groups",
            len(self._aifm_fields), len(self._aif_fields), len(self._repeating_groups),
        )

    @staticmethod
    def _is_cross_field_rule(rule: dict) -> bool:
        """Cross-field rules validate a relationship between two or more
        XSD elements and do NOT correspond to a single renderable field.
        They are detected by ``field_id`` == "CROSS-FIELD" or by an
        ``xsd_element`` that contains "/" (multiple elements)."""
        fid = str(rule.get("field_id", "")).strip().upper()
        if fid.startswith("CROSS"):
            return True
        xsd = str(rule.get("xsd_element", "")).strip().strip("<>")
        if "/" in xsd:
            return True
        return False

    @staticmethod
    def _parse_rule(rule: dict, report_type: ReportType) -> FieldDef:
        """Convert a single YAML rule dict into a FieldDef."""
        dt_map = {"A": DataType.ALPHA, "N": DataType.NUMERIC,
                  "D": DataType.DATE, "B": DataType.BOOLEAN, "T": DataType.FREETEXT}
        ob_map = {"M": Obligation.MANDATORY, "C": Obligation.CONDITIONAL,
                  "O": Obligation.OPTIONAL, "F": Obligation.FORBIDDEN}

        raw_dt = rule.get("data_type", "A")
        raw_ob = rule.get("m_c_o_f", "O")

        error_codes = rule.get("esma_error_codes", [])
        if isinstance(error_codes, str):
            error_codes = [error_codes]

        return FieldDef(
            field_id=str(rule.get("field_id", "")),
            field_name=rule.get("field_name", ""),
            report_type=report_type,
            section=rule.get("section", ""),
            data_type=dt_map.get(raw_dt, DataType.ALPHA),
            format=rule.get("format", ""),
            obligation=ob_map.get(raw_ob, Obligation.OPTIONAL),
            mandatory=rule.get("mandatory", False),
            repetition=rule.get("repetition", "[1..1]"),
            xsd_element=rule.get("xsd_element", ""),
            xml_type=rule.get("xml_type", ""),
            severity=rule.get("severity", "MEDIUM"),
            technical_guidance=rule.get("technical_guidance", ""),
            esma_doc=rule.get("esma_doc", ""),
            allowed_values_ref=rule.get("allowed_values_ref"),
            esma_error_codes=error_codes,
            gate_field=rule.get("gate_field"),
            gate_condition=rule.get("gate_condition"),
        )

    def _build_repeating_groups(self):
        """Identify repeating groups from field repetition patterns."""
        # Define the known repeating groups with their programmatic names
        # Based on ESMA Annex IV structure
        group_defs = [
            # AIFM groups
            ("aifm_assumptions",        ReportType.AIFM, ("14", "15"),                                    None, 0),
            ("aifm_principal_markets",  ReportType.AIFM, ("26", "27", "28", "29"),                        5,    5),
            ("aifm_principal_instruments", ReportType.AIFM, ("30", "31", "32"),                           5,    5),
            # AIF groups
            ("aif_assumptions",         ReportType.AIF, ("14", "15"),                                     None, 0),
            ("share_classes",           ReportType.AIF, ("34", "35", "36", "37", "38", "39", "40"),       None, 0),
            ("master_aifs",             ReportType.AIF, ("42", "43", "44"),                               None, 0),
            ("prime_brokers",           ReportType.AIF, ("45", "46", "47"),                               None, 0),
            ("strategies",              ReportType.AIF, ("58", "59", "60", "61"),                         None, 1),
            ("main_instruments",        ReportType.AIF, ("64", "65", "66", "67", "68", "69", "70",
                                                         "71", "72", "73", "74", "75", "76", "77"),      5,    5),
            ("geo_nav",                 ReportType.AIF, ("78", "79", "80", "81", "82", "83", "84", "85"), 8,   8),
            ("geo_agg",                 ReportType.AIF, ("86", "87", "88", "89", "90", "91", "92", "93"), 8,   8),
            ("exposures_10",            ReportType.AIF, ("94", "95", "96", "97", "98", "99",
                                                         "100", "101", "102"),                           10,   10),
            ("portfolio_concentrations", ReportType.AIF, ("103", "104", "105", "106", "107",
                                                          "108", "109", "110", "111", "112"),            5,    5),
            ("principal_markets",       ReportType.AIF, ("114", "115", "116", "117"),                    3,    3),
            ("individual_exposures",    ReportType.AIF, ("121", "122", "123", "124"),                    None, 1),
            ("turnover",                ReportType.AIF, ("125", "126", "127"),                           None, 1),
            ("currency_exposures",      ReportType.AIF, ("128", "129", "130"),                           None, 0),
            ("dominant_influence",      ReportType.AIF, ("131", "132", "133", "134", "135", "136"),      None, 0),
            ("risk_measures",           ReportType.AIF, ("138", "139", "140", "141", "142", "143",
                                                         "144", "145", "302", "146", "147"),             None, 1),
            ("counterparty_aif_exposure", ReportType.AIF, ("160", "161", "162", "163", "164", "165"),    5,    5),
            ("counterparty_to_aif",     ReportType.AIF, ("166", "167", "168", "169", "170", "171"),      5,    5),
            ("ccps",                    ReportType.AIF, ("173", "174", "175", "176", "177"),              3,    0),
            ("investor_groups",         ReportType.AIF, ("208", "209"),                                  None, 1),
            ("controlled_structures",   ReportType.AIF, ("290", "291", "292", "293"),                    None, 0),
            ("borrowing_sources",       ReportType.AIF, ("296", "297", "298", "299", "300", "301"),      5,    5),
        ]

        for name, rtype, fids, max_items, min_items in group_defs:
            fields = self._aifm_fields if rtype == ReportType.AIFM else self._aif_fields
            # Only include field_ids that actually exist in the registry
            valid_fids = tuple(f for f in fids if f in fields)
            if valid_fids:
                section = fields[valid_fids[0]].section
                self._repeating_groups.append(RepeatingGroup(
                    name=name,
                    section=section,
                    report_type=rtype,
                    field_ids=valid_fids,
                    max_items=max_items,
                    min_items=min_items,
                ))

    # --- Public API ---

    def aifm_field(self, field_id: str) -> Optional[FieldDef]:
        """Look up an AIFM field by its ESMA question number."""
        return self._aifm_fields.get(str(field_id))

    def aif_field(self, field_id: str) -> Optional[FieldDef]:
        """Look up an AIF field by its ESMA question number."""
        return self._aif_fields.get(str(field_id))

    def get_field(self, report_type: ReportType, field_id: str) -> Optional[FieldDef]:
        """Look up a field by report type and ESMA question number."""
        if report_type == ReportType.AIFM:
            return self.aifm_field(field_id)
        return self.aif_field(field_id)

    def aifm_fields(self) -> dict[str, FieldDef]:
        """All AIFM field definitions."""
        return dict(self._aifm_fields)

    def aif_fields(self) -> dict[str, FieldDef]:
        """All AIF field definitions."""
        return dict(self._aif_fields)

    def sections(self, report_type: ReportType) -> dict[str, list[FieldDef]]:
        """Fields grouped by section for a given report type."""
        if report_type == ReportType.AIFM:
            return dict(self._aifm_sections)
        return dict(self._aif_sections)

    def repeating_groups(self, report_type: Optional[ReportType] = None) -> list[RepeatingGroup]:
        """All repeating group definitions, optionally filtered by report type."""
        if report_type is None:
            return list(self._repeating_groups)
        return [g for g in self._repeating_groups if g.report_type == report_type]

    def repeating_group(self, name: str) -> Optional[RepeatingGroup]:
        """Look up a repeating group by programmatic name."""
        for g in self._repeating_groups:
            if g.name == name:
                return g
        return None

    def repeating_group_for_field(self, report_type: ReportType, field_id: str) -> Optional[RepeatingGroup]:
        """Find the repeating group that contains a given field_id."""
        for g in self._repeating_groups:
            if g.report_type == report_type and field_id in g.field_ids:
                return g
        return None

    def reference_table(self, name: str) -> list:
        """Look up a reference table (e.g. 'asset_sub_types') by name."""
        return self._reference_tables.get(name, [])

    # ------------------------------------------------------------------
    # Content-type applicability (AIFMD Annex IV reporting obligations)
    # ------------------------------------------------------------------
    # AIF Content Types (Field 5) — field visibility per reporting obligation
    #
    # CT=1: Art 24(1)              fields 1-120
    # CT=2: Art 24(1) + 24(2)     fields 1-295 + Q302
    # CT=3: Art 3(3)(d)           fields 1-120  (same scope as CT1)
    # CT=4: Art 24(1) + 24(2) + 24(4)  fields 1-301 + Q302
    # CT=5: Art 24(1) + 24(4)    fields 1-120, 281-301
    #
    # Source: ESMA reporting obligation matrix (aifmd_validation_rules.yaml)
    # See also: reporting_obligations reference table in the base YAML

    _HEADER_SECTIONS = {
        "AIF - Header Section",
        "AIF - Header file",
        "AIF Cancellation Record",
    }

    # 24(1) sections: fields 1-120 → visible in CT {1,2,3,4,5}
    _SECTIONS_24_1 = {
        "AIF - Header Section",                          # Q4-Q23
        "AIF - Header file",                             # Q1-Q3
        "AIF Cancellation Record",                       # CANC fields
        "AIF type",                                      # Q57
        "Fund identification codes",                     # Q24-Q32
        "Share class identification codes",              # Q33-Q40
        "Base currency information",                     # Q48-Q53
        "Master feeder structure",                       # Q41-Q44
        "Breakdown of investment strategies",            # Q58-Q63
        "Principal markets in which AIF trades",         # Q114-Q117
        "Identification of prime broker(s) of the AIF",  # Q45-Q47
        "Geographical focus",                            # Q78-Q102
        "Main instruments in which the AIF is trading",  # Q64-Q77
        "Five most important portfolio concentrations",  # Q103-Q112
        "Typical deal/position size",                    # Q113
        "Investor Concentration",                        # Q118-Q120
        "Jurisdictions of the three main funding sources",  # Q54-Q56
    }

    # 24(2) sections: fields 121-295 + Q302 → visible in CT {2,4}
    _SECTIONS_24_2 = {
        "Individual Exposures in which it is trading and the main categories of assets in which the AIF invested as at the reporting date",  # Q121-Q124
        "Value of turnover in each asset class over the reporting months",  # Q125-Q127
        "Currency of Exposures",                         # Q128-Q130
        "Dominant Influence [see Article 1 of Directive 83/349/EEC]",  # Q131-Q136
        "Measure of risks",                              # Q137-Q302 (spans into 24(4) range)
        "Trading and clearing mechanisms",               # Q148-Q156
        "Value of collateral and other credit support that the AIF has posted to all counterparties",  # Q157-Q159
        "Top Five Counterparty Exposures (excluding CCPs)",  # Q160-Q171
        "Direct clearing through central clearing counterparties (CCPs)",  # Q172-Q177
        "Portfolio Liquidity Profile",                   # Q178-Q185
        "Investor Liquidity Profile",                    # Q186-Q192
        "Investor redemptions",                          # Q193-Q196
        "Special arrangements and preferential treatment",  # Q197-Q207
        "Breakdown of the ownership of units in the AIF by investor group",  # Q208-Q209
        "Financing liquidity",                           # Q210-Q217
        "Total number of open positions",                # Q218
        "Historical risk profile",                       # Q219-Q278
        "Results of stress tests",                       # Q279-Q280
        "Of the amount of collateral and other credit support that the reporting fund has posted to counterparties: what percentage has been re-hypothecated by counterparties?",  # Q281-Q282
        "Value of borrowings of cash or securities represented by:",  # Q283-Q286
        "Value of borrowing embedded in financial instruments",  # Q287-Q289
        "Gross exposure of financial and, as the case may be, or legal structures controlled by the AIF as defined in Recital 78 of the AIFMD",  # Q290-Q293
        "AIF - 24.2 - Item 30: Leverage of the AIF",    # Q294-Q295
    }

    # 24(4) sections: fields 281-301 → visible in CT {4,5}
    _SECTIONS_24_4 = {
        "Of the amount of collateral and other credit support that the reporting fund has posted to counterparties: what percentage has been re-hypothecated by counterparties?",  # Q281-Q282
        "Value of borrowings of cash or securities represented by:",  # Q283-Q286
        "Value of borrowing embedded in financial instruments",  # Q287-Q289
        "Gross exposure of financial and, as the case may be, or legal structures controlled by the AIF as defined in Recital 78 of the AIFMD",  # Q290-Q293
        "AIF - 24.2 - Item 30: Leverage of the AIF",    # Q294-Q295
        "Five largest sources of borrowed cash or securities (short positions)",  # Q296-Q301
    }

    @classmethod
    def section_applicable_cts(cls, section: str) -> set[int]:
        """Return AIF content types for which a section is applicable.

        CT1=24(1), CT2=24(1)+(2), CT3=3(3d)=same scope as 24(1),
        CT4=24(1)+(2)+(4), CT5=24(1)+(4).
        """
        cts: set[int] = set()
        if section in cls._HEADER_SECTIONS:
            cts = {1, 2, 3, 4, 5}
        if section in cls._SECTIONS_24_1:
            cts |= {1, 2, 3, 4, 5}      # CT1 and CT3 include 24(1) scope
        if section in cls._SECTIONS_24_2:
            cts |= {2, 4}                # only CT2 and CT4 include 24(2)
        if section in cls._SECTIONS_24_4:
            cts |= {4, 5}
        return cts

    @classmethod
    def is_section_applicable(cls, section: str, content_type: int) -> bool:
        """Check if a section applies to a given content type."""
        cts = cls.section_applicable_cts(section)
        if not cts:
            # Unknown section — default to applicable
            return True
        return content_type in cts

    @property
    def aifm_field_count(self) -> int:
        return len(self._aifm_fields)

    @property
    def aif_field_count(self) -> int:
        return len(self._aif_fields)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_REGISTRY: Optional[FieldRegistry] = None


def get_registry(rules_path: Optional[Path] = None) -> FieldRegistry:
    """Return the global field registry singleton, loading on first access."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = FieldRegistry(rules_path)
    return _REGISTRY
