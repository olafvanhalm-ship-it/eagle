"""
FCA 2.0 Input Adapter — AIFMD Annex IV XML Reader (UK FCA format)
==================================================================
Reads UK FCA AIFMD Annex IV XML files (Version 2.0) and extracts all data
into canonical Python dicts suitable for validation, transformation, or
re-packaging.

Key differences from ESMA 1.2:
  - Uses XML namespace: urn:fsa-gov-uk:MER:AIF001:2 (AIFM) or AIF002:2 (AIF)
  - No xsi:noNamespaceSchemaLocation
  - Assumptions use FCAFieldReference instead of QuestionNumber
  - Geographic focus uses UK/EuropeNonUK instead of Europe/EEA
  - No AIFMEEAFlag / AIFEEAFlag fields
  - ReportingPeriodType typically H1/H2 (semi-annual)

Handles:
  - Plain .xml files
  - Both AIFM-level and AIF-level reports
  - Multi-record files (multiple AIFMRecordInfo / AIFRecordInfo)

Usage:
    from fca_adapter import FCAAdapter

    adapter = FCAAdapter("AIFM_GB_992806_20241231.xml")
    records = adapter.records
    adapter.report_type                # "AIFM" or "AIF"
    adapter.reporting_member_state     # "GB"
    adapter.version                    # "2.0"
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
_Path = Path  # alias for sys.path setup below
from typing import Any, Optional
from xml.etree import ElementTree as ET

# Set up application root for canonical imports
_app_root = _Path(__file__).resolve().parent.parent.parent.parent  # Application/
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from canonical.model import CanonicalAIFMReport, CanonicalAIFReport
from canonical.provenance import SourcePriority
from canonical.aifmd_source_entities import SourceCanonical
from canonical.aifmd_projection import reverse_lift_aifm, reverse_lift_aif

log = logging.getLogger(__name__)

# FCA namespaces
FCA_AIFM_NS = "urn:fsa-gov-uk:MER:AIF001:2"
FCA_AIF_NS = "urn:fsa-gov-uk:MER:AIF002:2"


# ── Anonymization support ───────────────────────────────────────────────────

_IDENTITY_ELEMENTS = {
    "AIFMName", "AIFMNationalCode", "AIFMIdentifierLEI",
    "AIFName", "AIFNationalCode", "AIFIdentifierLEI",
    "InstrumentName", "AssumptionDetails",
}

_ANON_COUNTERS: dict[str, int] = {}


def _anon_value(tag: str, original: str) -> str:
    """Generate a deterministic anonymised replacement value."""
    if not original or not original.strip():
        return original
    key = f"{tag}"
    _ANON_COUNTERS.setdefault(key, 0)
    idx = _ANON_COUNTERS[key]
    _ANON_COUNTERS[key] += 1

    if tag in ("AIFMNationalCode", "AIFNationalCode"):
        return f"ANON_{idx:06d}"
    if tag in ("AIFMIdentifierLEI", "AIFIdentifierLEI"):
        return f"{'0' * 4}ANON{'X' * 8}{idx:02d}"
    if tag == "AIFMName":
        names = ["Acme Capital", "Blue Ridge Partners", "Cedar Point Advisors",
                 "Delta Wave Capital", "Evergreen Management"]
        return names[idx % len(names)]
    if tag == "AIFName":
        names = ["Alpha Growth Fund", "Beta Income Fund", "Gamma Opportunity Fund",
                 "Delta Value Fund", "Epsilon Balanced Fund"]
        return names[idx % len(names)]
    if tag == "InstrumentName":
        generics = ["cash", "other", "not applicable", "n/a", "none",
                     "money market", "bank deposit"]
        if any(g in original.lower() for g in generics):
            return original
        names = ["Listed equity position", "Corporate bond holding",
                 "Government bond allocation", "Real estate investment",
                 "Private equity commitment"]
        return names[idx % len(names)]
    if tag == "AssumptionDetails":
        return ("The presented data of this AIFMD reporting is based on "
                "the last official calculated NAV of the fund.")
    return f"ANON_{tag}_{idx}"


# ── XML Parsing Helpers (namespace-aware) ────────────────────────────────────

def _local(tag: str) -> str:
    """Strip namespace from an XML tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _text(elem: Optional[ET.Element]) -> Optional[str]:
    """Get stripped text content of an element, or None."""
    if elem is not None and elem.text is not None:
        return elem.text.strip()
    return None


def _find(parent: ET.Element, tag: str) -> Optional[ET.Element]:
    """Namespace-agnostic find: search by local tag name."""
    for child in parent:
        if _local(child.tag) == tag:
            return child
    return None


def _findall(parent: ET.Element, tag: str) -> list[ET.Element]:
    """Namespace-agnostic findall: search by local tag name."""
    return [child for child in parent if _local(child.tag) == tag]


def _find_recursive(parent: ET.Element, tag: str) -> Optional[ET.Element]:
    """Recursively find first element with matching local tag."""
    for elem in parent.iter():
        if _local(elem.tag) == tag:
            return elem
    return None


def _findall_recursive(parent: ET.Element, tag: str) -> list[ET.Element]:
    """Recursively find all elements with matching local tag."""
    return [elem for elem in parent.iter() if _local(elem.tag) == tag]


def _child_text(parent: ET.Element, tag: str) -> Optional[str]:
    """Get text of a direct child element by local tag name."""
    elem = _find(parent, tag)
    return _text(elem)


def _child_int(parent: ET.Element, tag: str) -> Optional[int]:
    """Get integer value of a direct child element."""
    val = _child_text(parent, tag)
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _child_float(parent: ET.Element, tag: str) -> Optional[float]:
    """Get float value of a direct child element."""
    val = _child_text(parent, tag)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _child_bool(parent: ET.Element, tag: str) -> Optional[bool]:
    """Get boolean value of a direct child element."""
    val = _child_text(parent, tag)
    if val is None:
        return None
    return val.lower() == "true"


# ── FCA-specific Parsers ────────────────────────────────────────────────────

def _parse_assumptions_fca(record_elem: ET.Element) -> list[dict]:
    """Parse Assumptions block (FCA uses FCAFieldReference + AssumptionDetails)."""
    assumptions_elem = _find(record_elem, "Assumptions")
    if assumptions_elem is None:
        return []
    result = []
    for assumption in _findall(assumptions_elem, "Assumption"):
        result.append({
            "FCAFieldReference": _child_text(assumption, "FCAFieldReference"),
            "AssumptionDetails": _child_text(assumption, "AssumptionDetails"),
        })
    return result


def _parse_market_identification(market_elem: ET.Element) -> dict:
    """Parse a MarketIdentification sub-element."""
    mi = _find(market_elem, "MarketIdentification")
    if mi is None:
        return {}
    result = {}
    code_type = _child_text(mi, "MarketCodeType")
    if code_type:
        result["MarketCodeType"] = code_type
    market_code = _child_text(mi, "MarketCode")
    if market_code:
        result["MarketCode"] = market_code
    return result


def _parse_principal_markets(container: ET.Element, market_tag: str) -> list[dict]:
    """Parse ranked principal markets list."""
    result = []
    for market in _findall(container, market_tag):
        entry = {
            "Ranking": _child_int(market, "Ranking"),
            "MarketIdentification": _parse_market_identification(market),
        }
        agg = _child_int(market, "AggregatedValueAmount")
        if agg is not None:
            entry["AggregatedValueAmount"] = agg
        result.append(entry)
    return result


def _parse_principal_instruments(container: ET.Element, instrument_tag: str) -> list[dict]:
    """Parse ranked principal instruments list."""
    result = []
    for instr in _findall(container, instrument_tag):
        entry = {
            "Ranking": _child_int(instr, "Ranking"),
            "SubAssetType": _child_text(instr, "SubAssetType"),
        }
        agg = _child_int(instr, "AggregatedValueAmount")
        if agg is not None:
            entry["AggregatedValueAmount"] = agg
        result.append(entry)
    return result


def _parse_base_currency_desc(container: ET.Element) -> dict:
    """Parse AIFMBaseCurrencyDescription or AIFBaseCurrencyDescription."""
    bcd = (_find(container, "AIFMBaseCurrencyDescription") or
           _find(container, "AIFBaseCurrencyDescription"))
    if bcd is None:
        return {}
    return {
        "BaseCurrency": _child_text(bcd, "BaseCurrency"),
        "AUMAmountInBaseCurrency": _child_int(bcd, "AUMAmountInBaseCurrency"),
        "FXEURReferenceRateType": _child_text(bcd, "FXEURReferenceRateType"),
        "FXEURRate": _child_float(bcd, "FXEURRate"),
    }


def _parse_geographical_focus_fca(container: ET.Element, prefix: str) -> dict:
    """Parse NAVGeographicalFocus or AUMGeographicalFocus (FCA variant).

    FCA uses UK/EuropeNonUK instead of ESMA's Europe/EEA.
    """
    geo = _find(container, f"{prefix}GeographicalFocus")
    if geo is None:
        return {}
    result = {}
    for child in geo:
        tag = _local(child.tag)
        result[tag] = _child_float(geo, tag) if child.text else None
        if result[tag] is None and child.text:
            result[tag] = child.text.strip()
    return result


def _parse_main_instruments_traded(container: ET.Element) -> list[dict]:
    """Parse MainInstrumentsTraded section."""
    mit = _find(container, "MainInstrumentsTraded")
    if mit is None:
        return []
    result = []
    for instr in _findall(mit, "MainInstrumentTraded"):
        entry = {
            "Ranking": _child_int(instr, "Ranking"),
            "SubAssetType": _child_text(instr, "SubAssetType"),
            "InstrumentCodeType": _child_text(instr, "InstrumentCodeType"),
        }
        isin = _child_text(instr, "InstrumentCode")
        if isin:
            entry["InstrumentCode"] = isin
        name = _child_text(instr, "InstrumentName")
        if name:
            entry["InstrumentName"] = name
        val = _child_int(instr, "PositionValue")
        if val is not None:
            entry["PositionValue"] = val
        pt = _child_text(instr, "PositionType")
        if pt:
            entry["PositionType"] = pt
        result.append(entry)
    return result


def _parse_principal_exposures(container: ET.Element) -> list[dict]:
    """Parse PrincipalExposures section."""
    pe_container = _find(container, "PrincipalExposures")
    if pe_container is None:
        return []
    result = []
    for pe in _findall(pe_container, "PrincipalExposure"):
        entry = {
            "Ranking": _child_int(pe, "Ranking"),
            "AssetMacroType": _child_text(pe, "AssetMacroType"),
        }
        sub = _child_text(pe, "SubAssetType")
        if sub:
            entry["SubAssetType"] = sub
        pt = _child_text(pe, "PositionType")
        if pt:
            entry["PositionType"] = pt
        agg_val = _child_int(pe, "AggregatedValueAmount")
        if agg_val is not None:
            entry["AggregatedValueAmount"] = agg_val
        agg_rate = _child_float(pe, "AggregatedValueRate")
        if agg_rate is not None:
            entry["AggregatedValueRate"] = agg_rate
        result.append(entry)
    return result


def _parse_portfolio_concentrations(container: ET.Element) -> list[dict]:
    """Parse PortfolioConcentrations section."""
    mic = _find(container, "MostImportantConcentration")
    if mic is None:
        return []
    pc_container = _find(mic, "PortfolioConcentrations")
    if pc_container is None:
        return []
    result = []
    for pc in _findall(pc_container, "PortfolioConcentration"):
        entry = {
            "Ranking": _child_int(pc, "Ranking"),
            "AssetType": _child_text(pc, "AssetType"),
        }
        pt = _child_text(pc, "PositionType")
        if pt:
            entry["PositionType"] = pt
        mi = _parse_market_identification(pc)
        if mi:
            entry["MarketIdentification"] = mi
        agg_val = _child_int(pc, "AggregatedValueAmount")
        if agg_val is not None:
            entry["AggregatedValueAmount"] = agg_val
        agg_rate = _child_float(pc, "AggregatedValueRate")
        if agg_rate is not None:
            entry["AggregatedValueRate"] = agg_rate
        result.append(entry)
    return result


def _parse_aif_principal_markets(container: ET.Element) -> list[dict]:
    """Parse AIFPrincipalMarkets within MostImportantConcentration."""
    mic = _find(container, "MostImportantConcentration")
    if mic is None:
        return []
    apm = _find(mic, "AIFPrincipalMarkets")
    if apm is None:
        return []
    return _parse_principal_markets(apm, "AIFPrincipalMarket")


def _parse_investor_concentration(container: ET.Element) -> dict:
    """Parse InvestorConcentration section."""
    mic = _find(container, "MostImportantConcentration")
    if mic is None:
        return {}
    ic = _find(mic, "InvestorConcentration")
    if ic is None:
        return {}
    return {
        "MainBeneficialOwnersRate": _child_float(ic, "MainBeneficialOwnersRate"),
        "ProfessionalInvestorConcentrationRate": _child_float(ic, "ProfessionalInvestorConcentrationRate"),
        "RetailInvestorConcentrationRate": _child_float(ic, "RetailInvestorConcentrationRate"),
    }


def _parse_individual_exposure(container: ET.Element) -> dict:
    """Parse AIFIndividualInfo → IndividualExposure."""
    ind_info = _find(container, "AIFIndividualInfo")
    if ind_info is None:
        return {}
    ind_exp = _find(ind_info, "IndividualExposure")
    if ind_exp is None:
        return {}
    result = {}

    # AssetTypeExposures
    ate_container = _find(ind_exp, "AssetTypeExposures")
    if ate_container is not None:
        exposures = []
        for ate in _findall(ate_container, "AssetTypeExposure"):
            entry = {"SubAssetType": _child_text(ate, "SubAssetType")}
            lv = _child_int(ate, "LongValue")
            if lv is not None:
                entry["LongValue"] = lv
            sv = _child_int(ate, "ShortValue")
            if sv is not None:
                entry["ShortValue"] = sv
            exposures.append(entry)
        result["AssetTypeExposures"] = exposures

    # AssetTypeTurnovers
    att_container = _find(ind_exp, "AssetTypeTurnovers")
    if att_container is not None:
        turnovers = []
        for att in _findall(att_container, "AssetTypeTurnover"):
            turnovers.append({
                "TurnoverSubAssetType": _child_text(att, "TurnoverSubAssetType"),
                "MarketValue": _child_int(att, "MarketValue"),
            })
        result["AssetTypeTurnovers"] = turnovers

    # CurrencyExposures
    ce_container = _find(ind_exp, "CurrencyExposures")
    if ce_container is not None:
        currencies = []
        for ce in _findall(ce_container, "CurrencyExposure"):
            currencies.append({
                "ExposureCurrency": _child_text(ce, "ExposureCurrency"),
                "LongPositionValue": _child_int(ce, "LongPositionValue"),
                "ShortPositionValue": _child_int(ce, "ShortPositionValue"),
            })
        result["CurrencyExposures"] = currencies

    return result


def _parse_risk_profile(container: ET.Element) -> dict:
    """Parse RiskProfile section from AIFIndividualInfo."""
    ind_info = _find(container, "AIFIndividualInfo")
    if ind_info is None:
        return {}
    rp = _find(ind_info, "RiskProfile")
    if rp is None:
        return {}
    result = {}

    # MarketRiskProfile
    mrp = _find(rp, "MarketRiskProfile")
    if mrp is not None:
        market_risk = {
            "AnnualInvestmentReturnRate": _child_text(mrp, "AnnualInvestmentReturnRate"),
        }
        measures = []
        mrm_container = _find(mrp, "MarketRiskMeasures")
        if mrm_container is not None:
            for mrm in _findall(mrm_container, "MarketRiskMeasure"):
                measure = {
                    "RiskMeasureType": _child_text(mrm, "RiskMeasureType"),
                    "RiskMeasureDescription": _child_text(mrm, "RiskMeasureDescription"),
                }
                rmv = _child_float(mrm, "RiskMeasureValue")
                if rmv is not None:
                    measure["RiskMeasureValue"] = rmv
                bucket = _find(mrm, "BucketRiskMeasureValues")
                if bucket is not None:
                    measure["BucketRiskMeasureValues"] = {
                        "LessFiveYearsRiskMeasureValue": _child_float(bucket, "LessFiveYearsRiskMeasureValue"),
                        "FifthteenYearsRiskMeasureValue": _child_float(bucket, "FifthteenYearsRiskMeasureValue"),
                        "MoreFifthteenYearsRiskMeasureValue": _child_float(bucket, "MoreFifthteenYearsRiskMeasureValue"),
                    }
                var_vals = _find(mrm, "VARRiskMeasureValues")
                if var_vals is not None:
                    measure["VARRiskMeasureValues"] = {
                        "VARValue": _child_float(var_vals, "VARValue"),
                        "VARCalculationMethodCodeType": _child_text(var_vals, "VARCalculationMethodCodeType"),
                    }
                measures.append(measure)
        market_risk["MarketRiskMeasures"] = measures
        result["MarketRiskProfile"] = market_risk

    # CounterpartyRiskProfile
    crp = _find(rp, "CounterpartyRiskProfile")
    if crp is not None:
        cp_result = {}
        for direction in ("FundToCounterpartyExposures", "CounterpartyToFundExposures"):
            dir_elem = _find(crp, direction)
            if dir_elem is not None:
                items = []
                child_tag = direction.replace("Exposures", "Exposure")
                for item in _findall(dir_elem, child_tag):
                    entry = {
                        "Ranking": _child_int(item, "Ranking"),
                        "CounterpartyExposureFlag": _child_bool(item, "CounterpartyExposureFlag"),
                    }
                    lei = _child_text(item, "CounterpartyLEICode")
                    if lei:
                        entry["CounterpartyLEICode"] = lei
                    name = _child_text(item, "EntityName")
                    if name:
                        entry["EntityName"] = name
                    val = _child_float(item, "CounterpartyTotalExposureRate")
                    if val is not None:
                        entry["CounterpartyTotalExposureRate"] = val
                    items.append(entry)
                cp_result[direction] = items
        cp_result["ClearTransactionsThroughCCPFlag"] = _child_bool(crp, "ClearTransactionsThroughCCPFlag")
        ccpv = _child_float(crp, "CCPExposureValue")
        if ccpv is not None:
            cp_result["CCPExposureValue"] = ccpv
        result["CounterpartyRiskProfile"] = cp_result

    # LiquidityRiskProfile
    lrp = _find(rp, "LiquidityRiskProfile")
    if lrp is not None:
        liq_result = {}
        plp = _find(lrp, "PortfolioLiquidityProfile")
        if plp is not None:
            profile = {}
            for child in plp:
                tag = _local(child.tag)
                if "Rate" in tag:
                    profile[tag] = _child_float(plp, tag)
                else:
                    profile[tag] = _child_int(plp, tag) or _child_text(plp, tag)
            liq_result["PortfolioLiquidityProfile"] = profile
        ilp = _find(lrp, "InvestorLiquidityProfile")
        if ilp is not None:
            profile = {}
            for child in ilp:
                tag = _local(child.tag)
                profile[tag] = _child_float(ilp, tag)
            liq_result["InvestorLiquidityProfile"] = profile
        ir = _find(lrp, "InvestorRedemption")
        if ir is not None:
            liq_result["ProvideWithdrawalRightsFlag"] = _child_bool(ir, "ProvideWithdrawalRightsFlag")
            freq = _child_text(ir, "InvestorRedemptionFrequency")
            if freq:
                liq_result["InvestorRedemptionFrequency"] = freq
            notice = _child_int(ir, "InvestorRedemptionNoticePeriod")
            if notice is not None:
                liq_result["InvestorRedemptionNoticePeriod"] = notice
            lockup = _child_int(ir, "InvestorRedemptionLockUpPeriod")
            if lockup is not None:
                liq_result["InvestorRedemptionLockUpPeriod"] = lockup
        ig_container = _find(lrp, "InvestorGroups")
        if ig_container is not None:
            groups = []
            for ig in _findall(ig_container, "InvestorGroup"):
                groups.append({
                    "InvestorGroupType": _child_text(ig, "InvestorGroupType"),
                    "InvestorGroupRate": _child_float(ig, "InvestorGroupRate"),
                })
            liq_result["InvestorGroups"] = groups
        result["LiquidityRiskProfile"] = liq_result

    # OperationalRisk
    op = _find(rp, "OperationalRisk")
    if op is not None:
        op_result = {
            "TotalOpenPositions": _child_int(op, "TotalOpenPositions"),
        }
        hrp = _find(op, "HistoricalRiskProfile")
        if hrp is not None:
            historical = {}
            for section in hrp:
                section_tag = _local(section.tag)
                values = {}
                for child in section:
                    tag = _local(child.tag)
                    if "Quantity" in tag:
                        values[tag] = _child_int(section, tag)
                    elif "Rate" in tag:
                        values[tag] = _child_float(section, tag)
                    else:
                        values[tag] = _child_text(section, tag)
                historical[section_tag] = values
            op_result["HistoricalRiskProfile"] = historical
        result["OperationalRisk"] = op_result

    return result


def _parse_stress_tests(container: ET.Element) -> dict:
    """Parse StressTests section."""
    ind_info = _find(container, "AIFIndividualInfo")
    if ind_info is None:
        return {}
    st = _find(ind_info, "StressTests")
    if st is None:
        return {}
    return {
        "StressTestsResultArticle15": _child_text(st, "StressTestsResultArticle15"),
        "StressTestsResultArticle16": _child_text(st, "StressTestsResultArticle16"),
    }


def _parse_leverage_info(container: ET.Element) -> dict:
    """Parse AIFLeverageInfo section."""
    li = _find(container, "AIFLeverageInfo")
    if li is None:
        return {}
    art242 = _find(li, "AIFLeverageArticle24-2")
    if art242 is None:
        return {}
    result = {
        "AllCounterpartyCollateralRehypothecationFlag":
            _child_bool(art242, "AllCounterpartyCollateralRehypothecationFlag"),
    }
    scb = _find(art242, "SecuritiesCashBorrowing")
    if scb is not None:
        result["SecuritiesCashBorrowing"] = {
            "UnsecuredBorrowingAmount": _child_int(scb, "UnsecuredBorrowingAmount"),
            "SecuredBorrowingPrimeBrokerageAmount": _child_int(scb, "SecuredBorrowingPrimeBrokerageAmount"),
            "SecuredBorrowingReverseRepoAmount": _child_int(scb, "SecuredBorrowingReverseRepoAmount"),
            "SecuredBorrowingOtherAmount": _child_int(scb, "SecuredBorrowingOtherAmount"),
        }
    spbsv = _child_int(art242, "ShortPositionBorrowedSecuritiesValue")
    if spbsv is not None:
        result["ShortPositionBorrowedSecuritiesValue"] = spbsv
    lev = _find(art242, "LeverageAIF")
    if lev is not None:
        result["LeverageAIF"] = {
            "GrossMethodRate": _child_float(lev, "GrossMethodRate"),
            "CommitmentMethodRate": _child_float(lev, "CommitmentMethodRate"),
        }
    return result


def _parse_strategy(container: ET.Element) -> dict:
    """Parse fund investment strategy (varies by predominant AIF type)."""
    strategy_containers = [
        ("HedgeFundInvestmentStrategies", "HedgeFundStrategy", "HedgeFundStrategyType"),
        ("RealEstateFundInvestmentStrategies", "RealEstateFundStrategy", "RealEstateFundStrategyType"),
        ("PrivateEquityFundInvestmentStrategies", "PrivateEquityFundInvestmentStrategy", "PrivateEquityFundStrategyType"),
        ("FundOfFundsInvestmentStrategies", "FundOfFundsStrategy", "FundOfFundsStrategyType"),
        ("OtherFundInvestmentStrategies", "OtherFundStrategy", "OtherFundStrategyType"),
    ]
    for container_tag, strategy_tag, type_tag in strategy_containers:
        sc = _find_recursive(container, container_tag)
        if sc is not None:
            strategies = []
            for strat in _findall(sc, strategy_tag):
                entry = {
                    "StrategyType": _child_text(strat, type_tag),
                    "PrimaryStrategyFlag": _child_bool(strat, "PrimaryStrategyFlag"),
                    "StrategyNAVRate": _child_float(strat, "StrategyNAVRate"),
                }
                strategies.append(entry)
            return {
                "StrategyContainer": container_tag,
                "Strategies": strategies,
            }
    return {}


def _parse_share_classes(container: ET.Element) -> list[dict]:
    """Parse ShareClassIdentification elements if present."""
    result = []
    for sci in _findall_recursive(container, "ShareClassIdentification"):
        entry = {}
        nc = _child_text(sci, "ShareClassNationalCode")
        if nc:
            entry["ShareClassNationalCode"] = nc
        name = _child_text(sci, "ShareClassName")
        if name:
            entry["ShareClassName"] = name
        isin = _child_text(sci, "ShareClassIdentifierISIN")
        if isin:
            entry["ShareClassIdentifierISIN"] = isin
        result.append(entry)
    return result


# ── Main Adapter ────────────────────────────────────────────────────────────

class FCAAdapter:
    """Reads FCA 2.0 AIFMD Annex IV XML and extracts canonical records."""

    FORMAT = "FCA"
    SUPPORTED_VERSION = "2.0"

    def __init__(self, path: str, *, anonymize: bool = False):
        """Load and parse an FCA 2.0 XML file.

        Args:
            path: Path to .xml file.
            anonymize: If True, replace client-identifiable data with
                       synthetic values before returning records.
        """
        self.path = Path(path)
        self.anonymize = anonymize
        self._raw_xml: bytes = b""
        self._root: Optional[ET.Element] = None
        self._namespace: str = ""

        # Metadata (set after parsing)
        self.report_type: str = ""          # "AIFM" or "AIF"
        self.reporting_member_state: str = ""
        self.version: str = ""
        self.creation_datetime: str = ""
        self.source_filename: str = self.path.name

        # Parsed records
        self.records: list[dict] = []

        # Reset anonymization counters per adapter instance
        global _ANON_COUNTERS
        _ANON_COUNTERS = {}

        self._load_and_parse()

    def _load_and_parse(self):
        """Load XML content from file and parse."""
        with open(self.path, "rb") as f:
            self._raw_xml = f.read()

        self._root = ET.fromstring(self._raw_xml)
        self._parse_root()

    def _parse_root(self):
        """Parse root element attributes and dispatch to AIFM or AIF parser."""
        root = self._root
        root_tag = _local(root.tag)

        # Detect namespace
        ns_match = re.match(r'\{(.+)\}', root.tag)
        if ns_match:
            self._namespace = ns_match.group(1)
        else:
            log.warning("No namespace found — this may not be an FCA file")

        # Root attributes
        self.reporting_member_state = root.get("ReportingMemberState", "")
        self.version = root.get("Version", "")
        self.creation_datetime = root.get("CreationDateAndTime", "")

        # Validate
        if self.version != self.SUPPORTED_VERSION:
            log.warning("Expected FCA version %s, got %s", self.SUPPORTED_VERSION, self.version)

        if self._namespace and "fsa-gov-uk" not in self._namespace:
            raise ValueError(
                f"This file does not use FCA namespace ({self._namespace}). "
                "Use ESMAAdapter instead."
            )

        # Determine report type
        if root_tag == "AIFMReportingInfo":
            self.report_type = "AIFM"
            for record_elem in _findall(root, "AIFMRecordInfo"):
                self.records.append(self._parse_aifm_record(record_elem))
        elif root_tag == "AIFReportingInfo":
            self.report_type = "AIF"
            for record_elem in _findall(root, "AIFRecordInfo"):
                self.records.append(self._parse_aif_record(record_elem))
        else:
            raise ValueError(f"Unexpected root element: {root_tag}")

    def _parse_aifm_record(self, rec: ET.Element) -> dict:
        """Parse a single AIFMRecordInfo element into a canonical dict."""
        result = {
            "_source_format": self.FORMAT,
            "_source_version": self.version,
            "_source_file": self.source_filename,
            "_report_type": "AIFM",
            "_reporting_member_state": self.reporting_member_state,
            "_namespace": self._namespace,
            # Header fields
            "FilingType": _child_text(rec, "FilingType"),
            "AIFMContentType": _child_int(rec, "AIFMContentType"),
            "ReportingPeriodStartDate": _child_text(rec, "ReportingPeriodStartDate"),
            "ReportingPeriodEndDate": _child_text(rec, "ReportingPeriodEndDate"),
            "ReportingPeriodType": _child_text(rec, "ReportingPeriodType"),
            "ReportingPeriodYear": _child_int(rec, "ReportingPeriodYear"),
            "LastReportingFlag": _child_bool(rec, "LastReportingFlag"),
            "Assumptions": _parse_assumptions_fca(rec),
            "AIFMReportingCode": _child_text(rec, "AIFMReportingCode"),
            "AIFMJurisdiction": _child_text(rec, "AIFMJurisdiction"),
            "AIFMNationalCode": _child_text(rec, "AIFMNationalCode"),
            "AIFMName": _child_text(rec, "AIFMName"),
            # FCA has no AIFMEEAFlag
            "AIFMNoReportingFlag": _child_bool(rec, "AIFMNoReportingFlag"),
        }

        # AIFM Complete Description
        desc = _find(rec, "AIFMCompleteDescription")
        if desc is not None:
            ident = _find(desc, "AIFMIdentifier")
            if ident is not None:
                result["AIFMIdentifierLEI"] = _child_text(ident, "AIFMIdentifierLEI")

            pm = _find(desc, "AIFMPrincipalMarkets")
            if pm is not None:
                result["AIFMPrincipalMarkets"] = _parse_principal_markets(pm, "AIFMFivePrincipalMarket")

            pi = _find(desc, "AIFMPrincipalInstruments")
            if pi is not None:
                result["AIFMPrincipalInstruments"] = _parse_principal_instruments(pi, "AIFMPrincipalInstrument")

            result["AUMAmountInEuro"] = _child_int(desc, "AUMAmountInEuro")
            result["BaseCurrencyDescription"] = _parse_base_currency_desc(desc)

        if self.anonymize:
            self._anonymize_record(result)

        return result

    def _parse_aif_record(self, rec: ET.Element) -> dict:
        """Parse a single AIFRecordInfo element into a canonical dict."""
        result = {
            "_source_format": self.FORMAT,
            "_source_version": self.version,
            "_source_file": self.source_filename,
            "_report_type": "AIF",
            "_reporting_member_state": self.reporting_member_state,
            "_namespace": self._namespace,
            # Header fields
            "FilingType": _child_text(rec, "FilingType"),
            "AIFContentType": _child_int(rec, "AIFContentType"),
            "ReportingPeriodStartDate": _child_text(rec, "ReportingPeriodStartDate"),
            "ReportingPeriodEndDate": _child_text(rec, "ReportingPeriodEndDate"),
            "ReportingPeriodType": _child_text(rec, "ReportingPeriodType"),
            "ReportingPeriodYear": _child_int(rec, "ReportingPeriodYear"),
            "LastReportingFlag": _child_bool(rec, "LastReportingFlag"),
            "AIFMNationalCode": _child_text(rec, "AIFMNationalCode"),
            "AIFNationalCode": _child_text(rec, "AIFNationalCode"),
            "AIFName": _child_text(rec, "AIFName"),
            # FCA has no AIFEEAFlag
            "AIFReportingCode": _child_text(rec, "AIFReportingCode"),
            "AIFDomicile": _child_text(rec, "AIFDomicile"),
            "InceptionDate": _child_text(rec, "InceptionDate"),
            "AIFNoReportingFlag": _child_bool(rec, "AIFNoReportingFlag"),
        }

        desc = _find(rec, "AIFCompleteDescription")
        if desc is None:
            if self.anonymize:
                self._anonymize_record(result)
            return result

        pi = _find(desc, "AIFPrincipalInfo")
        if pi is not None:
            ident_container = _find(pi, "AIFIdentification")
            if ident_container is not None:
                result["AIFIdentifierLEI"] = _child_text(ident_container, "AIFIdentifierLEI")

            result["ShareClassFlag"] = _child_bool(pi, "ShareClassFlag")
            share_classes = _parse_share_classes(pi)
            if share_classes:
                result["ShareClasses"] = share_classes

            aif_desc = _find(pi, "AIFDescription")
            if aif_desc is not None:
                result["AIFMasterFeederStatus"] = _child_text(aif_desc, "AIFMasterFeederStatus")
                result["BaseCurrencyDescription"] = _parse_base_currency_desc(aif_desc)
                result["AIFNetAssetValue"] = _child_int(aif_desc, "AIFNetAssetValue")
                result["PredominantAIFType"] = _child_text(aif_desc, "PredominantAIFType")
                result["InvestmentStrategy"] = _parse_strategy(aif_desc)

            result["MainInstrumentsTraded"] = _parse_main_instruments_traded(pi)

            # FCA uses UK/EuropeNonUK instead of Europe/EEA
            result["NAVGeographicalFocus"] = _parse_geographical_focus_fca(pi, "NAV")
            result["AUMGeographicalFocus"] = _parse_geographical_focus_fca(pi, "AUM")

            result["PrincipalExposures"] = _parse_principal_exposures(pi)
            result["PortfolioConcentrations"] = _parse_portfolio_concentrations(pi)
            result["AIFPrincipalMarkets"] = _parse_aif_principal_markets(pi)
            result["InvestorConcentration"] = _parse_investor_concentration(pi)

        result["IndividualExposure"] = _parse_individual_exposure(desc)
        result["RiskProfile"] = _parse_risk_profile(desc)
        result["StressTests"] = _parse_stress_tests(desc)
        result["LeverageInfo"] = _parse_leverage_info(desc)

        if self.anonymize:
            self._anonymize_record(result)

        return result

    def _anonymize_record(self, record: dict):
        """Anonymize client-identifiable fields in a parsed record."""
        anon_fields = {
            "AIFMName": "AIFMName",
            "AIFMNationalCode": "AIFMNationalCode",
            "AIFMIdentifierLEI": "AIFMIdentifierLEI",
            "AIFName": "AIFName",
            "AIFNationalCode": "AIFNationalCode",
            "AIFIdentifierLEI": "AIFIdentifierLEI",
        }
        for field, tag in anon_fields.items():
            if field in record and record[field]:
                record[field] = _anon_value(tag, record[field])

        for instr in record.get("MainInstrumentsTraded", []):
            if "InstrumentName" in instr:
                instr["InstrumentName"] = _anon_value("InstrumentName", instr["InstrumentName"])

        for assumption in record.get("Assumptions", []):
            if "AssumptionDetails" in assumption:
                assumption["AssumptionDetails"] = _anon_value(
                    "AssumptionDetails", assumption["AssumptionDetails"]
                )

    # ── Public API ──────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a summary of the parsed file."""
        return {
            "format": self.FORMAT,
            "version": self.version,
            "report_type": self.report_type,
            "reporting_member_state": self.reporting_member_state,
            "creation_datetime": self.creation_datetime,
            "source_file": self.source_filename,
            "namespace": self._namespace,
            "record_count": len(self.records),
        }

    def to_flat_dicts(self) -> list[dict]:
        """Return records as flat dicts (no nested structures).

        Useful for CSV export or DataFrame construction.
        """
        flat = []
        for rec in self.records:
            row = {}
            for k, v in rec.items():
                if isinstance(v, (dict, list)):
                    continue
                row[k] = v
            flat.append(row)
        return flat

    # ── Canonical Conversion Methods ────────────────────────────────────────

    def to_canonical_aifm(self, record_index: int = 0) -> CanonicalAIFMReport:
        """Convert an AIFM record to CanonicalAIFMReport (ESMA field IDs).

        Maps FCA AIFM record fields to ESMA field IDs (question numbers).
        FCA reporting member state is always "GB" and has no EEA flag.

        Args:
            record_index: Index of record to convert (default: 0, first record).

        Returns:
            CanonicalAIFMReport with all mapped AIFM fields.

        Raises:
            ValueError: If record_index is out of range.
            ValueError: If report_type is not "AIFM".
        """
        if self.report_type != "AIFM":
            raise ValueError(f"Expected AIFM report, got {self.report_type}")
        if record_index >= len(self.records):
            raise ValueError(f"Record index {record_index} out of range (max: {len(self.records)-1})")

        record = self.records[record_index]
        report = CanonicalAIFMReport()

        # Q1: Reporting Member State (always GB for FCA)
        rms = record.get("_reporting_member_state") or "GB"
        report.set_field("1", rms, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q2: Version (FCA version maps to ESMA XSD 1.2)
        report.set_field("2", "1.2", source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q3: Creation Date
        creation_date = record.get("_creation_datetime", "")
        if creation_date:
            # Extract just the date part if datetime string
            date_part = creation_date.split("T")[0] if "T" in creation_date else creation_date
            report.set_field("3", date_part, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q4: Filing Type
        filing_type = record.get("FilingType")
        if filing_type:
            report.set_field("4", filing_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q5: AIFM Content Type
        content_type = record.get("AIFMContentType")
        if content_type is not None:
            report.set_field("5", str(content_type), source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q6: Reporting Period Start Date
        period_start = record.get("ReportingPeriodStartDate")
        if period_start:
            report.set_field("6", period_start, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q7: Reporting Period End Date
        period_end = record.get("ReportingPeriodEndDate")
        if period_end:
            report.set_field("7", period_end, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q8: Reporting Period Type
        period_type = record.get("ReportingPeriodType")
        if period_type:
            report.set_field("8", period_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q9: Reporting Year
        year = record.get("ReportingPeriodYear")
        if year is not None:
            report.set_field("9", str(year), source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q13: Last Reporting Flag
        last_reporting = record.get("LastReportingFlag")
        if last_reporting is not None:
            report.set_field("13", "true" if last_reporting else "false",
                           source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q14-Q15: Assumptions (FCA uses FCAFieldReference instead of QuestionNumber)
        assumptions = record.get("Assumptions", [])
        for assumption in assumptions:
            fca_field_ref = assumption.get("FCAFieldReference")
            assumption_details = assumption.get("AssumptionDetails")
            if fca_field_ref or assumption_details:
                report.add_group_item("assumptions", {
                    "question": fca_field_ref or "",
                    "description": assumption_details or "",
                }, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q17: AIFM Jurisdiction
        jurisdiction = record.get("AIFMJurisdiction")
        if jurisdiction:
            report.set_field("17", jurisdiction, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q19: AIFM Name
        aifm_name = record.get("AIFMName")
        if aifm_name:
            report.set_field("19", aifm_name, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q20: AIFM EEA Flag (FCA has no EEA flag; derive from jurisdiction)
        # For FCA (GB), always false
        report.set_field("20", "false", source="fca_adapter", priority=SourcePriority.DERIVED)

        # Q18: AIFM National Code
        national_code = record.get("AIFMNationalCode")
        if national_code:
            report.set_field("18", national_code, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q22: AIFM LEI
        lei = record.get("AIFMIdentifierLEI")
        if lei:
            report.set_field("22", lei, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q23: AIFM BIC Code
        bic = record.get("AIFMBICCode")
        if bic:
            report.set_field("23", bic, source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q26: AIFM No Reporting Flag
        no_reporting = record.get("AIFMNoReportingFlag")
        if no_reporting is not None:
            report.set_field("26", "true" if no_reporting else "false",
                           source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q32: AUM Amount in Euro
        aum_euro = record.get("AUMAmountInEuro")
        if aum_euro is not None:
            report.set_field("32", str(aum_euro), source="fca_adapter", priority=SourcePriority.IMPORTED)

        # Q33: Base Currency Description
        bcd = record.get("BaseCurrencyDescription", {})
        if bcd:
            base_currency = bcd.get("BaseCurrency")
            if base_currency:
                report.set_field("35", base_currency, source="fca_adapter", priority=SourcePriority.IMPORTED)

            aum_in_base = bcd.get("AUMAmountInBaseCurrency")
            if aum_in_base is not None:
                report.set_field("36", str(aum_in_base), source="fca_adapter", priority=SourcePriority.IMPORTED)

            fx_rate_type = bcd.get("FXEURReferenceRateType")
            if fx_rate_type:
                report.set_field("37", fx_rate_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

            fx_rate = bcd.get("FXEURRate")
            if fx_rate is not None:
                report.set_field("38", str(fx_rate), source="fca_adapter", priority=SourcePriority.IMPORTED)

        return report

    def to_canonical_aifs(self) -> list[CanonicalAIFReport]:
        """Convert all AIF records to CanonicalAIFReport list (ESMA field IDs).

        Maps FCA AIF record fields to ESMA field IDs. FCA has no EEA flag;
        this is derived as false for GB-domiciled funds.

        Returns:
            List of CanonicalAIFReport objects, one per AIF record in self.records.

        Raises:
            ValueError: If report_type is not "AIF".
        """
        if self.report_type != "AIF":
            raise ValueError(f"Expected AIF report, got {self.report_type}")

        aif_reports = []
        for record in self.records:
            report = CanonicalAIFReport()

            # Q1: Reporting Member State (always GB for FCA)
            rms = record.get("_reporting_member_state") or "GB"
            report.set_field("1", rms, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q2: Version
            report.set_field("2", "1.2", source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q3: Creation Date
            creation_date = record.get("_creation_datetime", "")
            if creation_date:
                date_part = creation_date.split("T")[0] if "T" in creation_date else creation_date
                report.set_field("3", date_part, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q4: Filing Type
            filing_type = record.get("FilingType")
            if filing_type:
                report.set_field("4", filing_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q5: AIF Content Type
            content_type = record.get("AIFContentType")
            if content_type is not None:
                report.set_field("5", str(content_type), source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q6: Reporting Period Start Date
            period_start = record.get("ReportingPeriodStartDate")
            if period_start:
                report.set_field("6", period_start, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q7: Reporting Period End Date
            period_end = record.get("ReportingPeriodEndDate")
            if period_end:
                report.set_field("7", period_end, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q8: Reporting Period Type
            period_type = record.get("ReportingPeriodType")
            if period_type:
                report.set_field("8", period_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q9: Year
            year = record.get("ReportingPeriodYear")
            if year is not None:
                report.set_field("9", str(year), source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q13: Last Reporting Flag
            last_reporting = record.get("LastReportingFlag")
            if last_reporting is not None:
                report.set_field("13", "true" if last_reporting else "false",
                               source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q18: AIF Name
            aif_name = record.get("AIFName")
            if aif_name:
                report.set_field("18", aif_name, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q19: AIF EEA Flag (FCA has no EEA flag; derive as false for GB)
            report.set_field("19", "false", source="fca_adapter", priority=SourcePriority.DERIVED)

            # Q21: AIF Domicile
            domicile = record.get("AIFDomicile")
            if domicile:
                report.set_field("21", domicile, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q22: Inception Date
            inception = record.get("InceptionDate")
            if inception:
                report.set_field("22", inception, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q24: AIF LEI
            lei = record.get("AIFIdentifierLEI")
            if lei:
                report.set_field("24", lei, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q28: AIF National Code
            national_code = record.get("AIFNationalCode")
            if national_code:
                report.set_field("28", national_code, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q31: Share Class Flag
            share_class_flag = record.get("ShareClassFlag")
            if share_class_flag is not None:
                report.set_field("31", "true" if share_class_flag else "false",
                               source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q32: AIFM National Code
            aifm_national_code = record.get("AIFMNationalCode")
            if aifm_national_code:
                report.set_field("32", aifm_national_code, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q34: AIF No Reporting Flag
            no_reporting = record.get("AIFNoReportingFlag")
            if no_reporting is not None:
                report.set_field("34", "true" if no_reporting else "false",
                               source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q41: Master/Feeder Status
            mf_status = record.get("AIFMasterFeederStatus")
            if mf_status:
                report.set_field("41", mf_status, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q49: Base Currency
            bcd = record.get("BaseCurrencyDescription", {})
            if bcd:
                base_currency = bcd.get("BaseCurrency")
                if base_currency:
                    report.set_field("49", base_currency, source="fca_adapter", priority=SourcePriority.IMPORTED)

                aum_in_base = bcd.get("AUMAmountInBaseCurrency")
                if aum_in_base is not None:
                    report.set_field("50", str(aum_in_base), source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q57: Predominant AIF Type
            predominant_type = record.get("PredominantAIFType")
            if predominant_type:
                report.set_field("57", predominant_type, source="fca_adapter", priority=SourcePriority.IMPORTED)

            # Q58: AIF Net Asset Value
            nav = record.get("AIFNetAssetValue")
            if nav is not None:
                report.set_field("58", str(nav), source="fca_adapter", priority=SourcePriority.IMPORTED)

            aif_reports.append(report)

        return aif_reports

    def to_source_canonical(self) -> tuple[SourceCanonical, list[SourceCanonical]]:
        """Convert parsed FCA records to Source Canonical entities.

        For AIFM reports: creates one SourceCanonical with AIFM manager entity.
        For AIF reports: creates one SourceCanonical per AIF record with fund entities.

        Uses reverse_lift to extract entity-classified fields from the canonical
        report representation, ensuring proper lineage and source tracking.

        Returns:
            Tuple of (aifm_source, aif_sources) where:
            - aifm_source: SourceCanonical with AIFM data (AIFM only)
            - aif_sources: List of SourceCanonical with AIF data (empty for AIFM reports)

        Raises:
            ValueError: If report_type is neither "AIFM" nor "AIF".
        """
        if self.report_type == "AIFM":
            # Create AIFM canonical report and reverse-lift
            aifm_report = self.to_canonical_aifm(record_index=0)
            aifm_source = reverse_lift_aifm(aifm_report)
            return (aifm_source, [])

        elif self.report_type == "AIF":
            # Create AIF canonical reports and reverse-lift each
            aif_reports = self.to_canonical_aifs()
            aif_sources = [reverse_lift_aif(report) for report in aif_reports]
            # Return empty AIFM source for AIF-only reports
            empty_aifm = SourceCanonical()
            return (empty_aifm, aif_sources)

        else:
            raise ValueError(f"Unknown report type: {self.report_type}")
