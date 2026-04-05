"""
Projection layer for canonical reporting models.

This module projects from the Source Canonical (domain entities) to the existing
Report Canonical (ESMA AIFMD 340 fields). It also supports "reverse-lift" —
extracting entity fields from a Report Canonical back into Source Canonical
entities when importing ESMA/FCA XML.

Design principle:
- Forward projection (Source → Report): straightforward field copying
- Reverse-lift (Report → Source): only copies entity-classified fields
  (not composite or report fields), as composite fields in ESMA/FCA imports
  have no lineage to source data.
"""

from __future__ import annotations
from typing import Optional
from .model import CanonicalAIFMReport, CanonicalAIFReport, CanonicalReport
from .provenance import FieldValue, SourcePriority
from .aifmd_source_entities import (
    SourceCanonical, SourceEntity, ManagerStatic, FundStatic, FundDynamic,
    Position, Transaction, Instrument, ShareClass, Counterparty,
    Strategy, Investor, RiskMeasure, MonthlyData, BorrowingSource,
    ControlledCompany, ControlledStructure,
)


# =============================================================================
# FIELD MAPPING TABLES
# =============================================================================

# Maps AIFM report field_id → (entity_attr_on_source_canonical, field_name_on_entity)
# These fields are classified as "entity" in aifmd_field_source_classification.yaml
# and can be reverse-lifted from ESMA/FCA XML imports.
AIFM_ENTITY_MAP = {
    "17": ("manager", "jurisdiction"),
    "18": ("manager", "national_code"),
    "19": ("manager", "name"),
    "20": ("manager", "eea_flag"),
    "22": ("manager", "lei"),
    "23": ("manager", "bic"),
    "35": ("manager", "base_currency"),
}

# Maps AIF report field_id → (entity_attr_on_source_canonical, field_name_on_entity)
# These fields are classified as "entity" in aifmd_field_source_classification.yaml.
# For FundStatic fields:
AIF_ENTITY_MAP = {
    # Fund identification
    "18": ("fund_static", "name"),
    "19": ("fund_static", "eea_flag"),
    "21": ("fund_static", "domicile"),
    "22": ("fund_static", "inception_date"),
    "24": ("fund_static", "lei"),
    "25": ("fund_static", "isin"),
    "26": ("fund_static", "cusip"),
    "27": ("fund_static", "sedol"),
    "28": ("fund_static", "bloomberg"),
    "29": ("fund_static", "reuters"),
    "30": ("fund_static", "ecb_code"),
    "33": ("fund_static", "has_share_classes"),
    # Master feeder
    "41": ("fund_static", "master_feeder_status"),
    "42": ("fund_static", "master_aif_name"),
    "43": ("fund_static", "master_aif_rms"),
    "44": ("fund_static", "master_aif_national_code"),
    # Base currency and funding sources
    "49": ("fund_static", "base_currency"),
    "54": ("fund_static", "funding_source_1"),
    "55": ("fund_static", "funding_source_2"),
    "56": ("fund_static", "funding_source_3"),
    # Strategy and dynamic fields (mapped to fund_dynamic)
    "57": ("fund_dynamic", "predominant_type"),
    "62": ("fund_dynamic", "hft_transaction_count"),
    "63": ("fund_dynamic", "hft_market_value"),
    "113": ("fund_dynamic", "position_size_type"),
    "118": ("fund_dynamic", "top5_beneficial_pct"),
    "137": ("fund_dynamic", "expected_return"),
    "148": ("fund_dynamic", "pct_securities_exchange"),
    "149": ("fund_dynamic", "pct_securities_otc"),
    "150": ("fund_dynamic", "pct_derivatives_exchange"),
    "151": ("fund_dynamic", "pct_derivatives_otc"),
    "152": ("fund_dynamic", "pct_derivatives_ccp"),
    "153": ("fund_dynamic", "pct_derivatives_bilateral"),
    "154": ("fund_dynamic", "pct_repos_ccp"),
    "155": ("fund_dynamic", "pct_repos_bilateral"),
    "156": ("fund_dynamic", "pct_repos_triparty"),
    "157": ("fund_dynamic", "collateral_cash"),
    "158": ("fund_dynamic", "collateral_securities"),
    "159": ("fund_dynamic", "collateral_other"),
    "172": ("fund_dynamic", "direct_clearing_flag"),
    "178": ("fund_dynamic", "portfolio_liq_0_1d"),
    "179": ("fund_dynamic", "portfolio_liq_2_7d"),
    "180": ("fund_dynamic", "portfolio_liq_8_30d"),
    "181": ("fund_dynamic", "portfolio_liq_31_90d"),
    "182": ("fund_dynamic", "portfolio_liq_91_180d"),
    "183": ("fund_dynamic", "portfolio_liq_181_365d"),
    "184": ("fund_dynamic", "portfolio_liq_gt_365d"),
    "185": ("fund_dynamic", "unencumbered_cash"),
    "186": ("fund_dynamic", "investor_liq_0_1d"),
    "187": ("fund_dynamic", "investor_liq_2_7d"),
    "188": ("fund_dynamic", "investor_liq_8_30d"),
    "189": ("fund_dynamic", "investor_liq_31_90d"),
    "190": ("fund_dynamic", "investor_liq_91_180d"),
    "191": ("fund_dynamic", "investor_liq_181_365d"),
    "192": ("fund_dynamic", "investor_liq_gt_365d"),
    "193": ("fund_dynamic", "withdrawal_rights_flag"),
    "194": ("fund_dynamic", "redemption_frequency"),
    "195": ("fund_dynamic", "redemption_notice_period"),
    "196": ("fund_dynamic", "redemption_lock_up_period"),
    "197": ("fund_dynamic", "side_pocket_pct"),
    "198": ("fund_dynamic", "gates_pct"),
    "199": ("fund_dynamic", "dealing_suspension_pct"),
    "200": ("fund_dynamic", "other_arrangement_type"),
    "201": ("fund_dynamic", "other_arrangement_pct"),
    "202": ("fund_dynamic", "total_arrangement_pct"),
    "203": ("fund_dynamic", "preferential_treatment_flag"),
    "204": ("fund_dynamic", "disclosure_pref_flag"),
    "205": ("fund_dynamic", "liquidity_pref_flag"),
    "206": ("fund_dynamic", "fee_pref_flag"),
    "207": ("fund_dynamic", "other_pref_flag"),
    "210": ("fund_dynamic", "available_financing"),
    "211": ("fund_dynamic", "financing_liq_0_1d"),
    "212": ("fund_dynamic", "financing_liq_2_7d"),
    "213": ("fund_dynamic", "financing_liq_8_30d"),
    "214": ("fund_dynamic", "financing_liq_31_90d"),
    "215": ("fund_dynamic", "financing_liq_91_180d"),
    "216": ("fund_dynamic", "financing_liq_181_365d"),
    "217": ("fund_dynamic", "financing_liq_gt_365d"),
    "279": ("fund_dynamic", "stress_test_art15"),
    "280": ("fund_dynamic", "stress_test_art16"),
    "281": ("fund_dynamic", "rehypothecation_flag"),
    "282": ("fund_dynamic", "rehypothecation_pct"),
    "283": ("fund_dynamic", "unsecured_borrowing"),
    "284": ("fund_dynamic", "secured_prime_broker"),
    "285": ("fund_dynamic", "secured_reverse_repo"),
    "286": ("fund_dynamic", "secured_other"),
    "287": ("fund_dynamic", "etd_exposure"),
    "288": ("fund_dynamic", "otc_exposure"),
    "289": ("fund_dynamic", "short_position_value"),
    # Share class fields (repeating group)
    "34": ("share_class", "national_code"),
    "35": ("share_class", "isin"),
    "36": ("share_class", "sedol"),
    "37": ("share_class", "cusip"),
    "38": ("share_class", "bloomberg"),
    "39": ("share_class", "reuters"),
    "40": ("share_class", "name"),
    # Prime broker fields (counterparty)
    "45": ("counterparty", "name"),
    "46": ("counterparty", "lei"),
    "47": ("counterparty", "bic"),
}


# =============================================================================
# FORWARD PROJECTION FUNCTIONS
# =============================================================================

def _project_entity_fields(entity, entity_map: dict, entity_attr_name: str,
                           report: CanonicalReport, source_name: str = "projection") -> None:
    """Helper: project fields from a SourceEntity into a CanonicalReport.

    Uses the entity's .get_field() to preserve original provenance.
    """
    for field_id, (attr_name, field_name) in entity_map.items():
        if attr_name != entity_attr_name:
            continue
        fv = entity.get_field(field_name)
        if fv is not None and fv.value is not None:
            report.set_field(
                field_id, fv.value,
                source=fv.source or source_name,
                priority=fv.priority,
                confidence=fv.confidence,
                source_ref=fv.source_ref,
                note=fv.note,
            )


def project_aifm(
    source: SourceCanonical,
    report_fields: Optional[dict] = None,
) -> CanonicalAIFMReport:
    """Project source entities to an AIFM report.

    For entity fields, reads from source.manager and writes to the report.
    For report-specific fields (Q1-Q16 etc.), uses the report_fields dict.
    """
    report = CanonicalAIFMReport()
    report_fields = report_fields or {}

    # Project entity fields from manager via mapping table
    if source.manager:
        _project_entity_fields(source.manager, AIFM_ENTITY_MAP, "manager",
                               report, "projection")

    # Project report-specific and composite fields from report_fields dict
    for field_id, value in report_fields.items():
        if value is not None:
            report.set_field(field_id, value, source="projection",
                           priority=SourcePriority.IMPORTED)

    return report


def project_aif(
    source: SourceCanonical,
    report_fields: Optional[dict] = None,
) -> CanonicalAIFReport:
    """Project source entities to an AIF report.

    For entity fields, reads from source.fund_static and source.fund_dynamic.
    For composite and report fields, uses report_fields dict.
    Also projects collection entities into repeating groups.
    """
    report = CanonicalAIFReport()
    report_fields = report_fields or {}

    # Project entity fields from fund_static and fund_dynamic via mapping table
    if source.fund_static:
        _project_entity_fields(source.fund_static, AIF_ENTITY_MAP, "fund_static",
                               report, "projection")
    if source.fund_dynamic:
        _project_entity_fields(source.fund_dynamic, AIF_ENTITY_MAP, "fund_dynamic",
                               report, "projection")

    # Project report-specific and composite fields from report_fields dict
    for field_id, value in report_fields.items():
        if value is not None:
            report.set_field(field_id, value, source="projection",
                           priority=SourcePriority.IMPORTED)

    # Project collection entities into repeating groups
    project_groups(source, report)

    return report


# =============================================================================
# REVERSE-LIFT FUNCTIONS
# =============================================================================

def reverse_lift_aifm(report: CanonicalAIFMReport) -> SourceCanonical:
    """
    Reverse-lift entity fields from an AIFM report into a new SourceCanonical.

    Only lifts fields classified as "entity" in AIFM_ENTITY_MAP. Report-specific
    and composite fields stay on the report only, as they have no lineage to
    source data in ESMA/FCA imports.

    Args:
        report: CanonicalAIFMReport to extract entity fields from.

    Returns:
        New SourceCanonical with lifted manager entity.
    """
    source = SourceCanonical()
    source.manager = ManagerStatic()

    for field_id, (entity_attr, field_name) in AIFM_ENTITY_MAP.items():
        if field_id not in report.fields:
            continue

        field_value = report.fields[field_id]
        if field_value.value is None:
            continue

        # All AIFM entity fields map to manager
        if entity_attr == "manager":
            source.manager.set(
                field_name, field_value.value,
                source=field_value.source,
                priority=field_value.priority,
                confidence=field_value.confidence,
                source_ref=field_value.source_ref,
                note=f"Reverse-lifted from AIFM report field Q{field_id}",
            )

    return source


def reverse_lift_aif(
    report: CanonicalAIFReport,
    source: Optional[SourceCanonical] = None,
) -> SourceCanonical:
    """
    Reverse-lift entity fields from an AIF report into a SourceCanonical.

    Only lifts fields classified as "entity" in AIF_ENTITY_MAP. Scalar entity
    fields are lifted into fund_static and fund_dynamic. Repeating group data
    (if present) is lifted into collection entities.

    Args:
        report: CanonicalAIFReport to extract entity fields from.
        source: Optional existing SourceCanonical to populate. If None, creates new.

    Returns:
        SourceCanonical with lifted fund_static, fund_dynamic, and collection entities.
    """
    if source is None:
        source = SourceCanonical()

    source.fund_static = FundStatic()
    source.fund_dynamic = FundDynamic()

    for field_id, (entity_attr, field_name) in AIF_ENTITY_MAP.items():
        if field_id not in report.fields:
            continue

        field_value = report.fields[field_id]
        if field_value.value is None:
            continue

        # Route to appropriate entity based on entity_attr
        _lift_note = f"Reverse-lifted from AIF report field Q{field_id}"
        if entity_attr == "fund_static":
            source.fund_static.set(
                field_name, field_value.value,
                source=field_value.source, priority=field_value.priority,
                confidence=field_value.confidence, source_ref=field_value.source_ref,
                note=_lift_note,
            )
        elif entity_attr == "fund_dynamic":
            source.fund_dynamic.set(
                field_name, field_value.value,
                source=field_value.source, priority=field_value.priority,
                confidence=field_value.confidence, source_ref=field_value.source_ref,
                note=_lift_note,
            )

    # Lift repeating group data from report into collection entities
    _reverse_lift_groups(report, source)

    return source


# =============================================================================
# REPEATING GROUP HELPERS
# =============================================================================

def project_groups(source: SourceCanonical, report: CanonicalAIFReport) -> None:
    """
    Project collection entities from source into report repeating groups.

    Maps:
    - source.positions → "positions" group
    - source.strategies → "strategies" group
    - source.share_classes → "share_classes" group
    - source.investors → "investor_groups" group
    - source.risk_measures → "risks" group
    - source.counterparties → "counterparty_risks" group
    - source.monthly_data → "historical_risk_profiles" group
    - source.borrowing_sources → "borrow_sources" group
    - source.controlled_companies → "dominant_influences" group
    - source.controlled_structures → "controlled_structures" group

    Args:
        source: Source canonical containing collection entities.
        report: CanonicalAIFReport to populate with repeating groups.
    """
    # NOTE: report.groups is a read-only property that returns a copy.
    # We must access report._groups directly to mutate the internal dict.
    if not hasattr(report, "_groups"):
        report._groups = {}

    # Project positions
    if source.positions:
        if "positions" not in report._groups:
            report._groups["positions"] = []
        for position in source.positions:
            report._groups["positions"].append(_position_to_dict(position))

    # Project strategies
    if source.strategies:
        if "strategies" not in report._groups:
            report._groups["strategies"] = []
        for strategy in source.strategies:
            report._groups["strategies"].append(_strategy_to_dict(strategy))

    # Project share classes
    if source.share_classes:
        if "share_classes" not in report._groups:
            report._groups["share_classes"] = []
        for share_class in source.share_classes:
            report._groups["share_classes"].append(_share_class_to_dict(share_class))

    # Project investors
    if source.investors:
        if "investor_groups" not in report._groups:
            report._groups["investor_groups"] = []
        for investor in source.investors:
            report._groups["investor_groups"].append(_investor_to_dict(investor))

    # Project risk measures
    if source.risk_measures:
        if "risks" not in report._groups:
            report._groups["risks"] = []
        for risk_measure in source.risk_measures:
            report._groups["risks"].append(_risk_measure_to_dict(risk_measure))

    # Project counterparties
    if source.counterparties:
        if "counterparty_risks" not in report._groups:
            report._groups["counterparty_risks"] = []
        for counterparty in source.counterparties:
            report._groups["counterparty_risks"].append(
                _counterparty_to_dict(counterparty)
            )

    # Project monthly data
    if source.monthly_data:
        if "historical_risk_profiles" not in report._groups:
            report._groups["historical_risk_profiles"] = []
        for monthly in source.monthly_data:
            report._groups["historical_risk_profiles"].append(
                _monthly_data_to_dict(monthly)
            )

    # Project borrowing sources
    if source.borrowing_sources:
        if "borrow_sources" not in report._groups:
            report._groups["borrow_sources"] = []
        for borrowing in source.borrowing_sources:
            report._groups["borrow_sources"].append(_borrowing_source_to_dict(borrowing))

    # Project controlled companies
    if source.controlled_companies:
        if "dominant_influences" not in report._groups:
            report._groups["dominant_influences"] = []
        for company in source.controlled_companies:
            report._groups["dominant_influences"].append(
                _controlled_company_to_dict(company)
            )

    # Project controlled structures
    if source.controlled_structures:
        if "controlled_structures" not in report._groups:
            report._groups["controlled_structures"] = []
        for structure in source.controlled_structures:
            report._groups["controlled_structures"].append(
                _controlled_structure_to_dict(structure)
            )


def _reverse_lift_groups(report: CanonicalAIFReport, source: SourceCanonical) -> None:
    """
    Reverse-lift repeating group data from report into source collection entities.

    Args:
        report: CanonicalAIFReport containing repeating groups.
        source: SourceCanonical to populate with collection entities.
    """
    if not hasattr(report, "groups"):
        return

    groups = report.groups

    # Lift positions
    if "positions" in groups:
        source.positions = []
        for pos_dict in groups["positions"]:
            source.positions.append(_dict_to_position(pos_dict))

    # Lift strategies
    if "strategies" in groups:
        source.strategies = []
        for strat_dict in groups["strategies"]:
            source.strategies.append(_dict_to_strategy(strat_dict))

    # Lift share classes
    if "share_classes" in groups:
        source.share_classes = []
        for sc_dict in groups["share_classes"]:
            source.share_classes.append(_dict_to_share_class(sc_dict))

    # Lift investors
    if "investor_groups" in groups:
        source.investors = []
        for inv_dict in groups["investor_groups"]:
            source.investors.append(_dict_to_investor(inv_dict))

    # Lift risk measures
    if "risks" in groups:
        source.risk_measures = []
        for risk_dict in groups["risks"]:
            source.risk_measures.append(_dict_to_risk_measure(risk_dict))

    # Lift counterparties
    if "counterparty_risks" in groups:
        source.counterparties = []
        for cp_dict in groups["counterparty_risks"]:
            source.counterparties.append(_dict_to_counterparty(cp_dict))

    # Lift monthly data
    if "historical_risk_profiles" in groups:
        source.monthly_data = []
        for monthly_dict in groups["historical_risk_profiles"]:
            source.monthly_data.append(_dict_to_monthly_data(monthly_dict))

    # Lift borrowing sources
    if "borrow_sources" in groups:
        source.borrowing_sources = []
        for borrow_dict in groups["borrow_sources"]:
            source.borrowing_sources.append(_dict_to_borrowing_source(borrow_dict))

    # Lift controlled companies
    if "dominant_influences" in groups:
        source.controlled_companies = []
        for company_dict in groups["dominant_influences"]:
            source.controlled_companies.append(_dict_to_controlled_company(company_dict))

    # Lift controlled structures
    if "controlled_structures" in groups:
        source.controlled_structures = []
        for struct_dict in groups["controlled_structures"]:
            source.controlled_structures.append(
                _dict_to_controlled_structure(struct_dict)
            )


# =============================================================================
# ENTITY-TO-DICT CONVERTERS (for forward projection)
# =============================================================================

def _entity_to_dict(entity: SourceEntity) -> dict:
    """Convert any SourceEntity to a dict of {field_name: FieldValue}.

    Extracts all fields that have been set on the entity, preserving
    provenance metadata by storing the full FieldValue objects.
    """
    result = {}
    for field_name in entity._FIELD_NAMES:
        fv = entity.get_field(field_name)
        if fv is not None:
            result[field_name] = fv
    return result


def _position_to_dict(position: Position) -> dict:
    """Convert a Position entity to a dict for report group."""
    return _entity_to_dict(position)


def _strategy_to_dict(strategy: Strategy) -> dict:
    """Convert a Strategy entity to a dict for report group."""
    return _entity_to_dict(strategy)


def _share_class_to_dict(share_class: ShareClass) -> dict:
    """Convert a ShareClass entity to a dict for report group."""
    return _entity_to_dict(share_class)


def _investor_to_dict(investor: Investor) -> dict:
    """Convert an Investor entity to a dict for report group."""
    return _entity_to_dict(investor)


def _risk_measure_to_dict(risk_measure: RiskMeasure) -> dict:
    """Convert a RiskMeasure entity to a dict for report group."""
    return _entity_to_dict(risk_measure)


def _counterparty_to_dict(counterparty: Counterparty) -> dict:
    """Convert a Counterparty entity to a dict for report group."""
    return _entity_to_dict(counterparty)


def _monthly_data_to_dict(monthly: MonthlyData) -> dict:
    """Convert a MonthlyData entity to a dict for report group."""
    return _entity_to_dict(monthly)


def _borrowing_source_to_dict(borrowing: BorrowingSource) -> dict:
    """Convert a BorrowingSource entity to a dict for report group."""
    return _entity_to_dict(borrowing)


def _controlled_company_to_dict(company: ControlledCompany) -> dict:
    """Convert a ControlledCompany entity to a dict for report group."""
    return _entity_to_dict(company)


def _controlled_structure_to_dict(structure: ControlledStructure) -> dict:
    """Convert a ControlledStructure entity to a dict for report group."""
    return _entity_to_dict(structure)


# =============================================================================
# DICT-TO-ENTITY CONVERTERS (for reverse-lift)
# =============================================================================

def _dict_to_entity(entity_cls, data_dict: dict, source: str = "reverse-lift"):
    """Generic converter: dict → SourceEntity using .set() API.

    Used by reverse-lift to reconstitute collection entities from report
    group dicts.  Each field gets IMPORTED priority so it can be
    overridden by manual corrections but ranks above derived values.

    Handles both raw values and FieldValue objects. When the dict
    contains FieldValue objects (from _entity_to_dict()), the original
    provenance metadata is preserved.
    """
    entity = entity_cls()
    for key, value in data_dict.items():
        if isinstance(value, FieldValue):
            # Preserve original provenance — store the FieldValue directly
            entity._fields[key] = value
        else:
            entity.set(key, value, source=source, priority=SourcePriority.IMPORTED)
    return entity


def _dict_to_position(pos_dict: dict) -> Position:
    return _dict_to_entity(Position, pos_dict)


def _dict_to_strategy(strat_dict: dict) -> Strategy:
    return _dict_to_entity(Strategy, strat_dict)


def _dict_to_share_class(sc_dict: dict) -> ShareClass:
    return _dict_to_entity(ShareClass, sc_dict)


def _dict_to_investor(inv_dict: dict) -> Investor:
    return _dict_to_entity(Investor, inv_dict)


def _dict_to_risk_measure(risk_dict: dict) -> RiskMeasure:
    return _dict_to_entity(RiskMeasure, risk_dict)


def _dict_to_counterparty(cp_dict: dict) -> Counterparty:
    return _dict_to_entity(Counterparty, cp_dict)


def _dict_to_monthly_data(monthly_dict: dict) -> MonthlyData:
    return _dict_to_entity(MonthlyData, monthly_dict)


def _dict_to_borrowing_source(borrow_dict: dict) -> BorrowingSource:
    return _dict_to_entity(BorrowingSource, borrow_dict)


def _dict_to_controlled_company(company_dict: dict) -> ControlledCompany:
    return _dict_to_entity(ControlledCompany, company_dict)


def _dict_to_controlled_structure(struct_dict: dict) -> ControlledStructure:
    return _dict_to_entity(ControlledStructure, struct_dict)
