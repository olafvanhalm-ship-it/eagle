"""
Extract ESMA Annex IV field values from generated AIFM/AIF XML.

The XML builders (aifm_builder, aif_builder) produce fully-populated XML with
all derived, aggregated and ranking data.  This module walks the XML tree and
maps every element back to its ESMA field ID using the XSD structure context
(parent element names) to disambiguate shared element names like <Ranking>,
<SubAssetType>, <EntityName>, etc.

The output is a (fields_json, groups_json) tuple ready for storage in the
ReviewReport rows.

Usage:
    from canonical.aifmd_xml_field_extractor import extract_aif_fields, extract_aifm_fields

    fields, groups = extract_aif_fields(xml_path_or_string)
    fields, groups = extract_aifm_fields(xml_path_or_string)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)


# ============================================================================
# AIF XML → field extraction
# ============================================================================

# Scalar root attributes → field_id
_AIF_ROOT_ATTRS = {
    "ReportingMemberState": "1",
    "Version": "2",
    "CreationDateAndTime": "3",
}

# Scalar elements directly under <AIFRecordInfo>
_AIF_RECORD_SCALARS = {
    "FilingType": "4",
    "AIFContentType": "5",
    "ReportingPeriodStartDate": "6",
    "ReportingPeriodEndDate": "7",
    "ReportingPeriodType": "8",
    "ReportingPeriodYear": "9",
    "AIFReportingObligationChangeFrequencyCode": "10",
    "AIFReportingObligationChangeContentsCode": "11",
    "AIFReportingObligationChangeQuarter": "12",
    "LastReportingFlag": "13",
    # 14, 15 are inside Assumptions (handled separately)
    "AIFMNationalCode": "16",
    "AIFNationalCode": "17",
    "AIFName": "18",
    "AIFEEAFlag": "19",
    "AIFReportingCode": "20",
    "AIFDomicile": "21",
    "InceptionDate": "22",
    "AIFNoReportingFlag": "23",
}

# Elements under AIFIdentification
_AIF_IDENTIFICATION = {
    "AIFIdentifierLEI": "24",
    "AIFIdentifierISIN": "25",
    "AIFIdentifierCUSIP": "26",
    "AIFIdentifierSEDOL": "27",
    "AIFIdentifierTicker": "28",
    "AIFIdentifierRIC": "29",
    "AIFIdentifierECB": "30",
}

# ShareClassFlag + share class identifiers
_AIF_SHARE_CLASS = {
    "ShareClassFlag": "33",
    "ShareClassNationalCode": "34",
    "ShareClassIdentifierISIN": "35",
    "ShareClassIdentifierSEDOL": "36",
    "ShareClassIdentifierCUSIP": "37",
    "ShareClassIdentifierTicker": "38",
    "ShareClassIdentifierRIC": "39",
    "ShareClassName": "40",
}

# AIFDescription scalars
_AIF_DESCRIPTION = {
    "AIFMasterFeederStatus": "41",
    "PredominantAIFType": "57",
    "HFTTransactionNumber": "62",
    "HFTBuySellMarketValue": "63",
}

# AIFBaseCurrencyDescription
_AIF_CURRENCY = {
    "AUMAmountInBaseCurrency": "48",
    "BaseCurrency": "49",
    "FXEURRate": "50",
    "FXEURReferenceRateType": "51",
    "FXEUROtherReferenceRateDescription": "52",
}

# Net asset value (direct child of AIFDescription)
_AIF_NAV = {
    "AIFNetAssetValue": "53",
}

# Funding sources
_AIF_FUNDING = {
    "FirstFundingSourceCountry": "54",
    "SecondFundingSourceCountry": "55",
    "ThirdFundingSourceCountry": "56",
}

# NAV Geographical Focus
_NAV_GEO = {
    "AfricaNAVRate": "78",
    "AsiaPacificNAVRate": "79",
    "EuropeNAVRate": "80",
    "EEANAVRate": "81",
    "MiddleEastNAVRate": "82",
    "NorthAmericaNAVRate": "83",
    "SouthAmericaNAVRate": "84",
    "SupraNationalNAVRate": "85",
}

# AUM Geographical Focus
_AUM_GEO = {
    "AfricaAUMRate": "86",
    "AsiaPacificAUMRate": "87",
    "EuropeAUMRate": "88",
    "EEAAUMRate": "89",
    "MiddleEastAUMRate": "90",
    "NorthAmericaAUMRate": "91",
    "SouthAmericaAUMRate": "92",
    "SupraNationalAUMRate": "93",
}

# Investor concentration
_INVESTOR_CONC = {
    "MainBeneficialOwnersRate": "118",
    "ProfessionalInvestorConcentrationRate": "119",
    "RetailInvestorConcentrationRate": "120",
}

# Risk profile – market risk
_MARKET_RISK = {
    "AnnualInvestmentReturnRate": "137",
}

# Portfolio liquidity profile
_PORTFOLIO_LIQUIDITY = {
    "PortfolioLiquidityInDays0to1Rate": "178",
    "PortfolioLiquidityInDays2to7Rate": "179",
    "PortfolioLiquidityInDays8to30Rate": "180",
    "PortfolioLiquidityInDays31to90Rate": "181",
    "PortfolioLiquidityInDays91to180Rate": "182",
    "PortfolioLiquidityInDays181to365Rate": "183",
    "PortfolioLiquidityInDays365MoreRate": "184",
    "UnencumberedCash": "185",
}

# Investor liquidity profile
_INVESTOR_LIQUIDITY = {
    "InvestorLiquidityInDays0to1Rate": "186",
    "InvestorLiquidityInDays2to7Rate": "187",
    "InvestorLiquidityInDays8to30Rate": "188",
    "InvestorLiquidityInDays31to90Rate": "189",
    "InvestorLiquidityInDays91to180Rate": "190",
    "InvestorLiquidityInDays181to365Rate": "191",
    "InvestorLiquidityInDays365MoreRate": "192",
}

# Investor redemption
_INVESTOR_REDEMPTION = {
    "ProvideWithdrawalRightsFlag": "193",
    "InvestorRedemptionFrequency": "194",
    "InvestorRedemptionNoticePeriod": "195",
    "InvestorRedemptionLockUpPeriod": "196",
}

# Special arrangements (under FinancingLiquidityProfile or SpecialArrangements)
_SPECIAL_ARRANGEMENTS = {
    "SidePocketRate": "197",
    "GatesRate": "198",
    "DealingSuspensionRate": "199",
    "OtherArrangementType": "200",
    "OtherArrangementRate": "201",
    "TotalArrangementRate": "202",
}

# Preferential treatment
_PREFERENTIAL = {
    "InvestorPreferentialTreatmentFlag": "203",
    "DisclosureTermsPreferentialTreatmentFlag": "204",
    "LiquidityTermsPreferentialTreatmentFlag": "205",
    "FeeTermsPreferentialTreatmentFlag": "206",
    "OtherTermsPreferentialTreatmentFlag": "207",
}

# Financing liquidity
_FINANCING = {
    "TotalFinancingAmount": "210",
    "TotalFinancingInDays0to1Rate": "211",
    "TotalFinancingInDays2to7Rate": "212",
    "TotalFinancingInDays8to30Rate": "213",
    "TotalFinancingInDays31to90Rate": "214",
    "TotalFinancingInDays91to180Rate": "215",
    "TotalFinancingInDays181to365Rate": "216",
    "TotalFinancingInDays365MoreRate": "217",
}

# Operational risk
_OPERATIONAL = {
    "TotalOpenPositions": "218",
}

# Counterparty risk – clearing flags + collateral
_COUNTERPARTY_MISC = {
    "ClearTransactionsThroughCCPFlag": "172",
    "AllCounterpartyCollateralCash": "157",
    "AllCounterpartyCollateralSecurities": "158",
    "AllCounterpartyOtherCollateralPosted": "159",
}

# Trading venue percentages
# These are disambiguated by parent context further down

# Stress tests
_STRESS_TESTS = {
    "StressTestsResultArticle15": "279",
    "StressTestsResultArticle16": "280",
}

# Leverage Article 24-2
_LEVERAGE_ART24 = {
    "AllCounterpartyCollateralRehypothecationFlag": "281",
    "AllCounterpartyCollateralRehypothecatedRate": "282",
    "ExchangedTradedDerivativesExposureValue": "287",
    "OTCDerivativesAmount": "288",
    "ShortPositionBorrowedSecuritiesValue": "289",
}

# Securities cash borrowing
_BORROWING = {
    "UnsecuredBorrowingAmount": "283",
    "SecuredBorrowingPrimeBrokerageAmount": "284",
    "SecuredBorrowingReverseRepoAmount": "285",
    "SecuredBorrowingOtherAmount": "286",
}

# Leverage ratios
_LEVERAGE = {
    "GrossMethodRate": "294",
    "CommitmentMethodRate": "295",
}

# Cancellation fields
_AIF_CANCELLATION = {
    "CancelledAIFNationalCode": "CANC-AIF-1",
    "CancelledAIFMNationalCode": "CANC-AIF-2",
    "CancelledReportingPeriodType": "CANC-AIF-3",
    "CancelledReportingPeriodYear": "CANC-AIF-4",
    "CancelledRecordFlag": "CANC-AIF-5",
}


# ---------------------------------------------------------------------------
# Monthly rates: GrossInvestmentReturnsRate, NetInvestmentReturnsRate,
# NAVChangeRate, Subscription, Redemption
# ---------------------------------------------------------------------------

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# parent element name → (element_prefix, starting field_id)
_MONTHLY_RATE_PARENTS = {
    "GrossInvestmentReturnsRate": ("Rate", 219),
    "NetInvestmentReturnsRate": ("Rate", 231),
    "NAVChangeRate": ("Rate", 243),
    "Subscription": ("Quantity", 255),
    "Redemption": ("Quantity", 267),
}

# Repeating group configurations
# parent_tag → list of (child_element, field_id) tuples per ranked item
_MAIN_INSTRUMENTS = [
    ("Ranking", "64"), ("SubAssetType", "65"), ("InstrumentCodeType", "66"),
    ("InstrumentName", "67"), ("ISINInstrumentIdentification", "68"),
    ("AIIExchangeCode", "69"), ("AIIProductCode", "70"),
    ("AIIDerivativeType", "71"), ("AIIPutCallIdentifier", "72"),
    ("AIIExpiryDate", "73"), ("AIIStrikePrice", "74"),
    ("PositionType", "75"), ("PositionValue", "76"),
    ("ShortPositionHedgingRate", "77"),
]

_PRINCIPAL_EXPOSURES = [
    ("Ranking", "94"), ("AssetMacroType", "95"), ("SubAssetType", "96"),
    ("PositionType", "97"), ("AggregatedValueAmount", "98"),
    ("AggregatedValueRate", "99"), ("EntityName", "100"),
    ("EntityIdentificationLEI", "101"), ("EntityIdentificationBIC", "102"),
]

_PORTFOLIO_CONCENTRATIONS = [
    ("Ranking", "103"), ("AssetType", "104"), ("PositionType", "105"),
    ("MarketCodeType", "106"), ("MarketCode", "107"),
    ("AggregatedValueAmount", "108"), ("AggregatedValueRate", "109"),
    ("EntityName", "110"), ("EntityIdentificationLEI", "111"),
    ("EntityIdentificationBIC", "112"),
]

_AIF_PRINCIPAL_MARKETS = [
    ("Ranking", "114"), ("MarketCodeType", "115"), ("MarketCode", "116"),
    ("AggregatedValueAmount", "117"),
]

_FUND_TO_COUNTERPARTY = [
    ("Ranking", "160"), ("CounterpartyExposureFlag", "161"),
    ("EntityName", "162"), ("EntityIdentificationLEI", "163"),
    ("EntityIdentificationBIC", "164"), ("CounterpartyTotalExposureRate", "165"),
]

_COUNTERPARTY_TO_FUND = [
    ("Ranking", "166"), ("CounterpartyExposureFlag", "167"),
    ("EntityName", "168"), ("EntityIdentificationLEI", "169"),
    ("EntityIdentificationBIC", "170"), ("CounterpartyTotalExposureRate", "171"),
]

_CCP_EXPOSURES = [
    ("Ranking", "173"), ("EntityName", "174"),
    ("EntityIdentificationLEI", "175"), ("EntityIdentificationBIC", "176"),
    ("CCPExposureValue", "177"),
]

_INVESTOR_GROUPS = [
    ("InvestorGroupType", "208"), ("InvestorGroupRate", "209"),
]

_CONTROLLED_STRUCTURES = [
    ("EntityName", "290"), ("EntityIdentificationLEI", "291"),
    ("EntityIdentificationBIC", "292"), ("ControlledStructureExposureValue", "293"),
]

_BORROWING_SOURCES = [
    ("Ranking", "296"), ("BorrowingSourceFlag", "297"),
    ("EntityName", "298"), ("EntityIdentificationLEI", "299"),
    ("EntityIdentificationBIC", "300"), ("LeverageAmount", "301"),
]

# Strategy fields (under various *InvestmentStrategies containers)
_STRATEGY_FIELDS = [
    ("PrimaryStrategyFlag", "59"), ("StrategyNAVRate", "60"),
    ("StrategyTypeOtherDescription", "61"),
]
# The strategy type element varies by predominant type
_STRATEGY_TYPE_ELEMENTS = {
    "HedgeFundStrategyType", "PrivateEquityFundStrategyType",
    "FundOfFundsStrategyType", "OtherFundStrategyType",
    "RealEstateFundStrategyType",
}

# Individual exposures – asset type
_ASSET_TYPE_EXPOSURES = [
    ("SubAssetType", "121"), ("GrossValue", "122"),
    ("LongValue", "123"), ("ShortValue", "124"),
]

# Individual exposures – turnover
_ASSET_TYPE_TURNOVERS = [
    ("TurnoverSubAssetType", "125"), ("MarketValue", "126"),
    ("NotionalValue", "127"),
]

# Individual exposures – currency
_CURRENCY_EXPOSURES = [
    ("ExposureCurrency", "128"), ("LongPositionValue", "129"),
    ("ShortPositionValue", "130"),
]

# Dominant influence
_DOMINANT_INFLUENCE = [
    ("EntityName", "131"), ("EntityIdentificationLEI", "132"),
    ("EntityIdentificationBIC", "133"), ("TransactionType", "134"),
    ("OtherTransactionTypeDescription", "135"), ("VotingRightsRate", "136"),
]

# Market risk measures (repeating)
_MARKET_RISK_MEASURES = [
    ("RiskMeasureType", "138"), ("RiskMeasureValue", "139"),
    ("LessFiveYearsRiskMeasureValue", "140"),
    ("FifthteenYearsRiskMeasureValue", "141"),
    ("MoreFifthteenYearsRiskMeasureValue", "142"),
    ("CurrentMarketRiskMeasureValue", "143"),
    ("LowerMarketRiskMeasureValue", "144"),
    ("HigherMarketRiskMeasureValue", "145"),
    ("VARCalculationMethodCodeType", "146"),
    ("RiskMeasureDescription", "147"),
]


# ============================================================================
# Helper: tag stripping
# ============================================================================

def _tag(el: ET.Element) -> str:
    """Strip namespace from tag."""
    t = el.tag
    return t.split("}")[-1] if "}" in t else t


def _text(el: ET.Element) -> str | None:
    """Get stripped text or None."""
    return el.text.strip() if el.text and el.text.strip() else None


def _find(parent: ET.Element, tag_name: str) -> ET.Element | None:
    """Find first child element with given (namespace-stripped) tag."""
    for child in parent:
        if _tag(child) == tag_name:
            return child
    return None


def _find_deep(root: ET.Element, tag_name: str) -> ET.Element | None:
    """Find element anywhere in tree."""
    for el in root.iter():
        if _tag(el) == tag_name:
            return el
    return None


def _findall_deep(root: ET.Element, tag_name: str) -> list[ET.Element]:
    """Find all elements anywhere in tree with given tag."""
    return [el for el in root.iter() if _tag(el) == tag_name]


def _set_field(fields: dict, fid: str, value: str | None, provenance: str = "Derived from source data"):
    """Store a scalar field value."""
    if value is not None:
        fields[fid] = {"value": value, "source": provenance, "priority": "IMPORTED"}


def _extract_scalars(parent: ET.Element, mapping: dict, fields: dict,
                     provenance: str = "Derived from source data"):
    """Walk direct children of parent and extract scalar fields."""
    for child in parent:
        tag = _tag(child)
        if tag in mapping:
            val = _text(child)
            _set_field(fields, mapping[tag], val, provenance)


def _extract_scalars_deep(root: ET.Element, mapping: dict, fields: dict,
                          provenance: str = "Derived from source data"):
    """Find elements anywhere in tree and extract scalar fields."""
    for el in root.iter():
        tag = _tag(el)
        if tag in mapping:
            val = _text(el)
            _set_field(fields, mapping[tag], val, provenance)


def _extract_repeating_group(
    root: ET.Element,
    container_tag: str,
    item_tag: str,
    field_defs: list[tuple[str, str]],
    fields: dict,
    groups: dict,
    group_name: str,
    provenance: str = "Derived from source data",
):
    """Extract a repeating group (e.g. MainInstrumentTraded ranked 1..N).

    - Stores the FIRST item's values in fields_json (for completeness counting)
    - Stores ALL items in groups_json[group_name] as a list of dicts
    """
    container = _find_deep(root, container_tag)
    if container is None:
        return

    items = [ch for ch in container if _tag(ch) == item_tag]
    if not items:
        return

    group_list = []
    for idx, item in enumerate(items):
        row = {}
        for elem_tag, fid in field_defs:
            # Search in item and its children (for nested elements like MarketIdentification/MarketCodeType)
            val = None
            el = _find(item, elem_tag)
            if el is not None:
                val = _text(el)
            else:
                # Try deeper search within item
                el = _find_deep(item, elem_tag)
                if el is not None:
                    val = _text(el)

            row[fid] = val

            # Store first item's values in fields_json
            if idx == 0 and val is not None:
                _set_field(fields, fid, val, provenance)

        group_list.append(row)

    groups[group_name] = group_list


def _extract_monthly_rates(root: ET.Element, fields: dict,
                           provenance: str = "Derived from source data"):
    """Extract monthly rate/quantity fields from HistoricalRiskProfile."""
    for parent_tag, (prefix, start_fid) in _MONTHLY_RATE_PARENTS.items():
        parent = _find_deep(root, parent_tag)
        if parent is None:
            continue

        for i, month in enumerate(_MONTHS):
            elem_name = f"{prefix}{month}"
            el = _find(parent, elem_name)
            if el is not None:
                val = _text(el)
                fid = str(start_fid + i)
                _set_field(fields, fid, val, provenance)


def _extract_risk_measures(root: ET.Element, fields: dict, groups: dict,
                           provenance: str = "Derived from source data"):
    """Extract market risk measures (repeating group with nested sub-structures)."""
    measures_container = _find_deep(root, "MarketRiskMeasures")
    if measures_container is None:
        return

    items = [ch for ch in measures_container if _tag(ch) == "MarketRiskMeasure"]
    if not items:
        return

    group_list = []
    for idx, item in enumerate(items):
        row = {}
        for elem_tag, fid in _MARKET_RISK_MEASURES:
            el = _find_deep(item, elem_tag)
            val = _text(el) if el is not None else None
            row[fid] = val
            if idx == 0 and val is not None:
                _set_field(fields, fid, val, provenance)
        group_list.append(row)

    # Also extract VARValue from VARRiskMeasureValues (field 302)
    var_container = _find_deep(root, "VARRiskMeasureValues")
    if var_container is not None:
        var_el = _find(var_container, "VARValue")
        if var_el is not None:
            _set_field(fields, "302", _text(var_el), provenance)

    groups["market_risk_measures"] = group_list


def _extract_strategies(root: ET.Element, fields: dict, groups: dict,
                        provenance: str = "Derived from source data"):
    """Extract investment strategy fields.

    Strategy type elements vary by predominant type:
    HedgeFundStrategyType, RealEstateFundStrategyType, etc.
    """
    # Find any strategy container (various names)
    strategy_containers = [
        "HedgeFundInvestmentStrategies", "PrivateEquityFundInvestmentStrategies",
        "FundOfFundsInvestmentStrategies", "OtherFundInvestmentStrategies",
        "RealEstateFundInvestmentStrategies",
    ]
    container = None
    for name in strategy_containers:
        container = _find_deep(root, name)
        if container is not None:
            break

    if container is None:
        return

    # Find strategy items (HedgeFundStrategy, RealEstateFundStrategy, etc.)
    strategy_items = []
    for child in container:
        tag = _tag(child)
        if "Strategy" in tag and "Strategies" not in tag:
            strategy_items.append(child)

    group_list = []
    for idx, item in enumerate(strategy_items):
        row = {}
        # Extract strategy type (variable element name)
        for child in item:
            tag = _tag(child)
            if tag in _STRATEGY_TYPE_ELEMENTS:
                val = _text(child)
                row["58"] = val
                if idx == 0 and val is not None:
                    _set_field(fields, "58", val, provenance)
                break

        # Extract other strategy fields
        for elem_tag, fid in _STRATEGY_FIELDS:
            el = _find(item, elem_tag)
            val = _text(el) if el is not None else None
            row[fid] = val
            if idx == 0 and val is not None:
                _set_field(fields, fid, val, provenance)

        group_list.append(row)

    groups["strategies"] = group_list


def _extract_trading_venues(root: ET.Element, fields: dict,
                            provenance: str = "Derived from source data"):
    """Extract trading venue percentages, disambiguated by parent context.

    The element names RegulatedMarketRate, OTCRate, CCPRate, BilateralClearingRate
    appear under different parent elements for different field IDs.
    """
    # Securities market (fields 148-149)
    sec = _find_deep(root, "SecuritiesMarket")
    if sec is not None:
        for child in sec:
            tag = _tag(child)
            if tag == "RegulatedMarketRate":
                _set_field(fields, "148", _text(child), provenance)
            elif tag == "OTCRate":
                _set_field(fields, "149", _text(child), provenance)

    # Derivatives market (fields 150-151)
    der = _find_deep(root, "DerivativesMarket")
    if der is not None:
        for child in der:
            tag = _tag(child)
            if tag == "RegulatedMarketRate":
                _set_field(fields, "150", _text(child), provenance)
            elif tag == "OTCRate":
                _set_field(fields, "151", _text(child), provenance)

    # Derivatives clearing (fields 152-153)
    dclear = _find_deep(root, "DerivativesClearingMethod")
    if dclear is None:
        dclear = _find_deep(root, "ClearingMethodRate")
    if dclear is not None:
        for child in dclear:
            tag = _tag(child)
            if tag == "CCPRate":
                _set_field(fields, "152", _text(child), provenance)
            elif tag == "BilateralClearingRate":
                _set_field(fields, "153", _text(child), provenance)

    # Repos clearing (fields 154-156)
    repos = _find_deep(root, "ReposClearingMethod")
    if repos is None:
        repos = _find_deep(root, "RepoClearingMethodRate")
    if repos is not None:
        for child in repos:
            tag = _tag(child)
            if tag == "CCPRate":
                _set_field(fields, "154", _text(child), provenance)
            elif tag == "BilateralClearingRate":
                _set_field(fields, "155", _text(child), provenance)
            elif tag == "TriPartyRepoClearingRate":
                _set_field(fields, "156", _text(child), provenance)


def _extract_assumptions(root: ET.Element, fields: dict,
                         provenance: str = "Derived from source data"):
    """Extract Assumptions (question number + description) — fields 14, 15.

    Handles both ESMA format (QuestionNumber / AssumptionDescription)
    and FCA format (FCAFieldReference / AssumptionDetails).
    """
    assumptions = _find_deep(root, "Assumptions")
    if assumptions is None:
        return
    first = _find(assumptions, "Assumption")
    if first is None:
        return
    # ESMA: QuestionNumber, FCA: FCAFieldReference
    qn = _find(first, "QuestionNumber") or _find(first, "FCAFieldReference")
    if qn is not None:
        _set_field(fields, "14", _text(qn), provenance)
    # ESMA: AssumptionDescription, FCA: AssumptionDetails
    ad = _find(first, "AssumptionDescription") or _find(first, "AssumptionDetails")
    if ad is not None:
        _set_field(fields, "15", _text(ad), provenance)


def _extract_old_identifier(root: ET.Element, fields: dict,
                            provenance: str = "Derived from source data"):
    """Extract old AIF identifier (fields 31-32)."""
    old_id = _find_deep(root, "OldAIFIdentifierNCA")
    if old_id is None:
        return
    rms = _find(old_id, "ReportingMemberState")
    if rms is not None:
        _set_field(fields, "31", _text(rms), provenance)
    nc = _find(old_id, "AIFNationalCode")
    if nc is not None:
        _set_field(fields, "32", _text(nc), provenance)


def _extract_master_aif(root: ET.Element, fields: dict,
                        provenance: str = "Derived from source data"):
    """Extract master AIF info (fields 42-44)."""
    master = _find_deep(root, "MasterAIFIdentification")
    if master is None:
        return
    name = _find(master, "AIFName")
    if name is not None:
        _set_field(fields, "42", _text(name), provenance)
    rms = _find_deep(master, "ReportingMemberState")
    if rms is not None:
        _set_field(fields, "43", _text(rms), provenance)
    nc = _find_deep(master, "AIFNationalCode")
    if nc is not None:
        _set_field(fields, "44", _text(nc), provenance)


def _extract_prime_brokers(root: ET.Element, fields: dict, groups: dict,
                           provenance: str = "Derived from source data"):
    """Extract prime broker info (fields 45-47)."""
    pb = _find_deep(root, "PrimeBrokers")
    if pb is None:
        return
    first = None
    for child in pb:
        if _tag(child) in ("PrimeBroker", "PrimeBrokerIdentification"):
            first = child
            break
    if first is None:
        return
    name = _find_deep(first, "EntityName")
    if name is not None:
        _set_field(fields, "45", _text(name), provenance)
    lei = _find_deep(first, "EntityIdentificationLEI")
    if lei is not None:
        _set_field(fields, "46", _text(lei), provenance)
    bic = _find_deep(first, "EntityIdentificationBIC")
    if bic is not None:
        _set_field(fields, "47", _text(bic), provenance)


def _extract_typical_position_size(root: ET.Element, fields: dict,
                                   provenance: str = "Derived from source data"):
    """Extract TypicalPositionSize (field 113)."""
    el = _find_deep(root, "TypicalPositionSize")
    if el is not None:
        _set_field(fields, "113", _text(el), provenance)


# ============================================================================
# Main extraction functions
# ============================================================================

def extract_aif_fields(xml_source: Union[str, Path, ET.Element]) -> tuple[dict, dict]:
    """Extract all AIF field values from generated XML.

    Args:
        xml_source: Path to XML file, XML string, or pre-parsed root element.

    Returns:
        (fields_json, groups_json) — ready for storage in ReviewReport.
    """
    if isinstance(xml_source, ET.Element):
        root = xml_source
    elif isinstance(xml_source, Path) or (isinstance(xml_source, str) and not xml_source.strip().startswith("<")):
        tree = ET.parse(str(xml_source))
        root = tree.getroot()
    else:
        root = ET.fromstring(xml_source)

    fields: dict[str, dict] = {}
    groups: dict[str, list] = {}
    prov = "Derived from source data"

    # 1. Root attributes (fields 1-3)
    for attr_name, fid in _AIF_ROOT_ATTRS.items():
        val = root.get(attr_name)
        if val is None:
            for k, v in root.attrib.items():
                if k.split("}")[-1] == attr_name:
                    val = v
                    break
        _set_field(fields, fid, val, prov)

    # 2. Record-level scalars (fields 4-23)
    record = _find_deep(root, "AIFRecordInfo")
    if record is None:
        record = root  # fallback
    _extract_scalars(record, _AIF_RECORD_SCALARS, fields, prov)

    # 3. Assumptions (fields 14-15)
    _extract_assumptions(root, fields, prov)

    # 4. AIF Identification (fields 24-30)
    ident = _find_deep(root, "AIFIdentification")
    if ident is not None:
        _extract_scalars_deep(ident, _AIF_IDENTIFICATION, fields, prov)

    # 5. Old identifier (31-32)
    _extract_old_identifier(root, fields, prov)

    # 6. Share class (33-40)
    _extract_scalars_deep(root, _AIF_SHARE_CLASS, fields, prov)

    # 7. AIFDescription scalars (41, 57, 62-63)
    desc = _find_deep(root, "AIFDescription")
    if desc is not None:
        _extract_scalars(desc, _AIF_DESCRIPTION, fields, prov)
        # NAV is direct child of AIFDescription
        nav_el = _find(desc, "AIFNetAssetValue")
        if nav_el is not None:
            _set_field(fields, "53", _text(nav_el), prov)

    # 8. Master AIF (42-44)
    _extract_master_aif(root, fields, prov)

    # 9. Prime brokers (45-47)
    _extract_prime_brokers(root, fields, groups, prov)

    # 10. Currency description (48-52)
    curr_desc = _find_deep(root, "AIFBaseCurrencyDescription")
    if curr_desc is not None:
        _extract_scalars(curr_desc, _AIF_CURRENCY, fields, prov)

    # 11. Funding sources (54-56)
    _extract_scalars_deep(root, _AIF_FUNDING, fields, prov)

    # 12. Strategies (58-61)
    _extract_strategies(root, fields, groups, prov)

    # 13. Main instruments traded (64-77) — repeating, ranked 1..5
    _extract_repeating_group(
        root, "MainInstrumentsTraded", "MainInstrumentTraded",
        _MAIN_INSTRUMENTS, fields, groups, "main_instruments", prov,
    )

    # 14. NAV geographical focus (78-85)
    nav_geo = _find_deep(root, "NAVGeographicalFocus")
    if nav_geo is not None:
        _extract_scalars(nav_geo, _NAV_GEO, fields, prov)

    # 15. AUM geographical focus (86-93)
    aum_geo = _find_deep(root, "AUMGeographicalFocus")
    if aum_geo is not None:
        _extract_scalars(aum_geo, _AUM_GEO, fields, prov)

    # 16. Principal exposures (94-102) — repeating, ranked 1..10
    _extract_repeating_group(
        root, "PrincipalExposures", "PrincipalExposure",
        _PRINCIPAL_EXPOSURES, fields, groups, "principal_exposures", prov,
    )

    # 17. Portfolio concentrations (103-112)
    _extract_repeating_group(
        root, "PortfolioConcentrations", "PortfolioConcentration",
        _PORTFOLIO_CONCENTRATIONS, fields, groups, "portfolio_concentrations", prov,
    )

    # 18. Typical position size (113)
    _extract_typical_position_size(root, fields, prov)

    # 19. AIF Principal Markets (114-117)
    _extract_repeating_group(
        root, "AIFPrincipalMarkets", "AIFPrincipalMarket",
        _AIF_PRINCIPAL_MARKETS, fields, groups, "aif_principal_markets", prov,
    )

    # 20. Investor concentration (118-120)
    inv_conc = _find_deep(root, "InvestorConcentration")
    if inv_conc is not None:
        _extract_scalars(inv_conc, _INVESTOR_CONC, fields, prov)

    # 21. Individual exposure – asset types (121-124)
    _extract_repeating_group(
        root, "AssetTypeExposures", "AssetTypeExposure",
        _ASSET_TYPE_EXPOSURES, fields, groups, "asset_type_exposures", prov,
    )

    # 22. Individual exposure – turnovers (125-127)
    _extract_repeating_group(
        root, "AssetTypeTurnovers", "AssetTypeTurnover",
        _ASSET_TYPE_TURNOVERS, fields, groups, "asset_type_turnovers", prov,
    )

    # 23. Individual exposure – currencies (128-130)
    _extract_repeating_group(
        root, "CurrencyExposures", "CurrencyExposure",
        _CURRENCY_EXPOSURES, fields, groups, "currency_exposures", prov,
    )

    # 24. Dominant influence (131-136)
    _extract_repeating_group(
        root, "CompanyDominantInfluence", "CompanyDominantInfluenceIdentification",
        _DOMINANT_INFLUENCE, fields, groups, "dominant_influence", prov,
    )

    # 25. Market risk (137)
    mrp = _find_deep(root, "MarketRiskProfile")
    if mrp is not None:
        _extract_scalars_deep(mrp, _MARKET_RISK, fields, prov)

    # 26. Market risk measures (138-147, 302) — repeating
    _extract_risk_measures(root, fields, groups, prov)

    # 27. Trading venues (148-156)
    _extract_trading_venues(root, fields, prov)

    # 28. Collateral posted (157-159)
    _extract_scalars_deep(root, _COUNTERPARTY_MISC, fields, prov)

    # 29. Fund-to-counterparty exposures (160-165) — repeating, ranked 1..5
    _extract_repeating_group(
        root, "FundToCounterpartyExposures", "FundToCounterpartyExposure",
        _FUND_TO_COUNTERPARTY, fields, groups, "fund_to_counterparty", prov,
    )

    # 30. Counterparty-to-fund exposures (166-171) — repeating, ranked 1..5
    _extract_repeating_group(
        root, "CounterpartyToFundExposures", "CounterpartyToFundExposure",
        _COUNTERPARTY_TO_FUND, fields, groups, "counterparty_to_fund", prov,
    )

    # 31. CCP exposures (173-177)
    _extract_repeating_group(
        root, "CCPExposures", "CCPExposure",
        _CCP_EXPOSURES, fields, groups, "ccp_exposures", prov,
    )

    # 32. Portfolio liquidity (178-185)
    plp = _find_deep(root, "PortfolioLiquidityProfile")
    if plp is not None:
        _extract_scalars(plp, _PORTFOLIO_LIQUIDITY, fields, prov)

    # 33. Investor liquidity (186-192)
    ilp = _find_deep(root, "InvestorLiquidityProfile")
    if ilp is not None:
        _extract_scalars(ilp, _INVESTOR_LIQUIDITY, fields, prov)

    # 34. Investor redemption (193-196)
    ired = _find_deep(root, "InvestorRedemption")
    if ired is not None:
        _extract_scalars_deep(ired, _INVESTOR_REDEMPTION, fields, prov)

    # 35. Special arrangements (197-202)
    _extract_scalars_deep(root, _SPECIAL_ARRANGEMENTS, fields, prov)

    # 36. Preferential treatment (203-207)
    _extract_scalars_deep(root, _PREFERENTIAL, fields, prov)

    # 37. Investor groups (208-209) — repeating
    _extract_repeating_group(
        root, "InvestorGroups", "InvestorGroup",
        _INVESTOR_GROUPS, fields, groups, "investor_groups", prov,
    )

    # 38. Financing liquidity (210-217)
    _extract_scalars_deep(root, _FINANCING, fields, prov)

    # 39. Operational risk – total open positions (218)
    _extract_scalars_deep(root, _OPERATIONAL, fields, prov)

    # 40. Monthly rates (219-278)
    _extract_monthly_rates(root, fields, prov)

    # 41. Stress tests (279-280)
    _extract_scalars_deep(root, _STRESS_TESTS, fields, prov)

    # 42. Leverage article 24-2 (281-282, 287-289)
    _extract_scalars_deep(root, _LEVERAGE_ART24, fields, prov)

    # 43. Securities cash borrowing (283-286)
    _extract_scalars_deep(root, _BORROWING, fields, prov)

    # 44. Controlled structures (290-293)
    _extract_repeating_group(
        root, "ControlledStructures", "ControlledStructure",
        _CONTROLLED_STRUCTURES, fields, groups, "controlled_structures", prov,
    )

    # 45. Leverage ratios (294-295)
    lev = _find_deep(root, "LeverageAIF")
    if lev is not None:
        _extract_scalars(lev, _LEVERAGE, fields, prov)

    # 46. Borrowing sources (296-301)
    _extract_repeating_group(
        root, "BorrowingSources", "BorrowingSource",
        _BORROWING_SOURCES, fields, groups, "borrowing_sources", prov,
    )

    # 47. Cancellation fields
    _extract_scalars_deep(root, _AIF_CANCELLATION, fields, prov)

    log.info("AIF XML extraction: %d scalar fields, %d groups (%s)",
             len(fields), len(groups),
             ", ".join(f"{k}={len(v)}" for k, v in groups.items()))

    return fields, groups


# ============================================================================
# AIFM XML → field extraction
# ============================================================================

_AIFM_ROOT_ATTRS = {
    "ReportingMemberState": "1",
    "Version": "2",
    "CreationDateAndTime": "3",
}

_AIFM_RECORD_SCALARS = {
    "FilingType": "4",
    "AIFMContentType": "5",
    "ReportingPeriodStartDate": "6",
    "ReportingPeriodEndDate": "7",
    "ReportingPeriodType": "8",
    "ReportingPeriodYear": "9",
    "AIFMReportingObligationChangeFrequencyCode": "10",
    "AIFMReportingObligationChangeContentsCode": "11",
    "AIFMReportingObligationChangeQuarter": "12",
    "LastReportingFlag": "13",
    # 14, 15: Assumptions (handled separately)
    "AIFMReportingCode": "16",
    "AIFMJurisdiction": "17",
    "AIFMNationalCode": "18",
    "AIFMName": "19",
    "AIFMEEAFlag": "20",
    "AIFMNoReportingFlag": "21",
}

_AIFM_IDENTIFICATION = {
    "AIFMIdentifierLEI": "22",
    "AIFMIdentifierBIC": "23",
}

_AIFM_CURRENCY = {
    "AUMAmountInEuro": "24",
    "BaseCurrency": "26",
    "AUMAmountInBaseCurrency": "27",
    "FXEURReferenceRateType": "28",
    "FXEURRate": "29",
    "FXEUROtherReferenceRateDescription": "30",
}

_AIFM_PRINCIPAL_MARKETS = [
    ("Ranking", "31"), ("MarketCodeType", "32"), ("MarketCode", "33"),
    ("AggregatedValueAmount", "34"),
]

_AIFM_PRINCIPAL_INSTRUMENTS = [
    ("Ranking", "35"), ("SubAssetType", "36"),
    ("AggregatedValueAmount", "37"),
]

_AIFM_CANCELLATION = {
    "CancelledAIFMNationalCode": "CANC-AIFM-1",
    "CancelledReportingPeriodType": "CANC-AIFM-2",
    "CancelledReportingPeriodYear": "CANC-AIFM-3",
    "CancelledRecordFlag": "CANC-AIFM-4",
}


def extract_aifm_fields(xml_source: Union[str, Path, ET.Element]) -> tuple[dict, dict]:
    """Extract all AIFM field values from generated XML.

    Args:
        xml_source: Path to XML file, XML string, or pre-parsed root element.

    Returns:
        (fields_json, groups_json) — ready for storage in ReviewReport.
    """
    if isinstance(xml_source, ET.Element):
        root = xml_source
    elif isinstance(xml_source, Path) or (isinstance(xml_source, str) and not xml_source.strip().startswith("<")):
        tree = ET.parse(str(xml_source))
        root = tree.getroot()
    else:
        root = ET.fromstring(xml_source)

    fields: dict[str, dict] = {}
    groups: dict[str, list] = {}
    prov = "Derived from source data"

    # 1. Root attributes (1-3)
    for attr_name, fid in _AIFM_ROOT_ATTRS.items():
        val = root.get(attr_name)
        if val is None:
            for k, v in root.attrib.items():
                if k.split("}")[-1] == attr_name:
                    val = v
                    break
        _set_field(fields, fid, val, prov)

    # 2. Record scalars (4-21)
    record = _find_deep(root, "AIFMRecordInfo")
    if record is None:
        record = root
    _extract_scalars(record, _AIFM_RECORD_SCALARS, fields, prov)

    # 3. Assumptions (14-15)
    _extract_assumptions(root, fields, prov)

    # 4. AIFM identification (22-23)
    ident = _find_deep(root, "AIFMIdentifier")
    if ident is not None:
        _extract_scalars(ident, _AIFM_IDENTIFICATION, fields, prov)

    # 5. AUM in Euro (field 24) — direct child of AIFMCompleteDescription
    _extract_scalars_deep(root, {"AUMAmountInEuro": "24"}, fields, prov)

    # 6. Currency description (26-30)
    curr = _find_deep(root, "AIFMBaseCurrencyDescription")
    if curr is not None:
        _extract_scalars(curr, _AIFM_CURRENCY, fields, prov)

    # 7. Principal markets (31-34) — repeating, ranked 1..5
    _extract_repeating_group(
        root, "AIFMPrincipalMarkets", "AIFMFivePrincipalMarket",
        _AIFM_PRINCIPAL_MARKETS, fields, groups, "aifm_principal_markets", prov,
    )

    # 8. Principal instruments (35-37) — repeating, ranked 1..5
    _extract_repeating_group(
        root, "AIFMPrincipalInstruments", "AIFMPrincipalInstrument",
        _AIFM_PRINCIPAL_INSTRUMENTS, fields, groups, "aifm_principal_instruments", prov,
    )

    # 9. Cancellation fields
    _extract_scalars_deep(root, _AIFM_CANCELLATION, fields, prov)

    log.info("AIFM XML extraction: %d scalar fields, %d groups (%s)",
             len(fields), len(groups),
             ", ".join(f"{k}={len(v)}" for k, v in groups.items()))

    return fields, groups
