"""
ESMA 1.2 Input Adapter — AIFMD Annex IV XML Reader
====================================================
Reads ESMA AIFMD Annex IV XML files (Version 1.2) and extracts all data
into canonical Python dicts suitable for validation, transformation, or
re-packaging.

Handles:
  - Plain .xml files
  - Gzip-compressed .gz files
  - Zip archives containing .xml files
  - Both AIFM-level and AIF-level reports
  - Multi-record files (multiple AIFMRecordInfo / AIFRecordInfo)

Usage:
    from esma_adapter import ESMAAdapter

    adapter = ESMAAdapter("AIFM_NL_12345_20241231.xml")
    records = adapter.records          # list of parsed dicts
    adapter.report_type                # "AIFM" or "AIF"
    adapter.reporting_member_state     # "NL"
    adapter.version                    # "1.2"

    # Or from compressed:
    adapter = ESMAAdapter("AIFM_DE_40031432_20241231.gz")
    adapter = ESMAAdapter("AIF_BE_02694-0001_20241231.zip")
"""

import gzip
import logging
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

# Set up module path for canonical imports
_app_root = Path(__file__).resolve().parent.parent.parent.parent  # Application/
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from canonical.model import CanonicalAIFMReport, CanonicalAIFReport
from canonical.provenance import SourcePriority, FieldValue
from canonical.aifmd_source_entities import SourceCanonical
from canonical.aifmd_projection import reverse_lift_aifm, reverse_lift_aif

log = logging.getLogger(__name__)


# ── Anonymization support ───────────────────────────────────────────────────

# Elements whose text content is client-identifiable
_IDENTITY_ELEMENTS = {
    "AIFMName", "AIFMNationalCode", "AIFMIdentifierLEI",
    "AIFName", "AIFNationalCode", "AIFIdentifierLEI",
    "InstrumentName", "AssumptionDescription",
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
    if tag == "AssumptionDescription":
        return ("The presented data of this AIFMD reporting is based on "
                "the last official calculated NAV of the fund.")
    return f"ANON_{tag}_{idx}"


# ── XML Parsing Helpers ─────────────────────────────────────────────────────

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


# ── ESMA-specific Parsers ───────────────────────────────────────────────────

def _parse_assumptions(record_elem: ET.Element) -> list[dict]:
    """Parse Assumptions block (ESMA uses QuestionNumber)."""
    assumptions_elem = _find(record_elem, "Assumptions")
    if assumptions_elem is None:
        return []
    result = []
    for assumption in _findall(assumptions_elem, "Assumption"):
        result.append({
            "QuestionNumber": _child_text(assumption, "QuestionNumber"),
            "AssumptionDescription": _child_text(assumption, "AssumptionDescription"),
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


def _parse_geographical_focus(container: ET.Element, prefix: str) -> dict:
    """Parse NAVGeographicalFocus or AUMGeographicalFocus."""
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
                # BucketRiskMeasureValues
                bucket = _find(mrm, "BucketRiskMeasureValues")
                if bucket is not None:
                    measure["BucketRiskMeasureValues"] = {
                        "LessFiveYearsRiskMeasureValue": _child_float(bucket, "LessFiveYearsRiskMeasureValue"),
                        "FifthteenYearsRiskMeasureValue": _child_float(bucket, "FifthteenYearsRiskMeasureValue"),
                        "MoreFifthteenYearsRiskMeasureValue": _child_float(bucket, "MoreFifthteenYearsRiskMeasureValue"),
                    }
                # VARRiskMeasureValues
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
        # Portfolio liquidity
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
        # Investor liquidity
        ilp = _find(lrp, "InvestorLiquidityProfile")
        if ilp is not None:
            profile = {}
            for child in ilp:
                tag = _local(child.tag)
                profile[tag] = _child_float(ilp, tag)
            liq_result["InvestorLiquidityProfile"] = profile
        # Investor redemption
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
        # Investor groups
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
    # Securities/Cash borrowing
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
    # Leverage ratios
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

class ESMAAdapter:
    """Reads ESMA 1.2 AIFMD Annex IV XML and extracts canonical records."""

    FORMAT = "ESMA"
    SUPPORTED_VERSION = "1.2"

    def __init__(self, path: str, *, anonymize: bool = False):
        """Load and parse an ESMA 1.2 XML file.

        Args:
            path: Path to .xml, .gz, or .zip file.
            anonymize: If True, replace client-identifiable data with
                       synthetic values before returning records.
        """
        self.path = Path(path)
        self.anonymize = anonymize
        self._raw_xml: bytes = b""
        self._root: Optional[ET.Element] = None

        # Metadata (set after parsing)
        self.report_type: str = ""          # "AIFM" or "AIF"
        self.reporting_member_state: str = ""
        self.version: str = ""
        self.creation_datetime: str = ""
        self.schema_location: str = ""
        self.source_filename: str = self.path.name
        self.source_format: str = ""        # "xml", "gz", "zip"

        # Parsed records
        self.records: list[dict] = []

        # Reset anonymization counters per adapter instance
        global _ANON_COUNTERS
        _ANON_COUNTERS = {}

        self._load_and_parse()

    def _load_and_parse(self):
        """Load XML content from file (handling compression) and parse."""
        suffix = self.path.suffix.lower()

        if suffix == ".xml":
            self.source_format = "xml"
            with open(self.path, "rb") as f:
                self._raw_xml = f.read()
        elif suffix == ".gz":
            self.source_format = "gz"
            with gzip.open(str(self.path), "rb") as f:
                self._raw_xml = f.read()
        elif suffix == ".zip":
            self.source_format = "zip"
            with zipfile.ZipFile(str(self.path), "r") as zf:
                xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not xml_names:
                    raise ValueError(f"No XML files found in {self.path}")
                self._raw_xml = zf.read(xml_names[0])
                self.source_filename = xml_names[0]
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

        self._root = ET.fromstring(self._raw_xml)
        self._parse_root()

    def _parse_root(self):
        """Parse root element attributes and dispatch to AIFM or AIF parser."""
        root = self._root
        root_tag = _local(root.tag)

        # Root attributes
        self.reporting_member_state = root.get("ReportingMemberState", "")
        self.version = root.get("Version", "")
        self.creation_datetime = root.get("CreationDateAndTime", "")

        # Schema location (ESMA uses noNamespaceSchemaLocation)
        xsi_ns = "http://www.w3.org/2001/XMLSchema-instance"
        self.schema_location = root.get(f"{{{xsi_ns}}}noNamespaceSchemaLocation", "")

        # Validate format
        if self.version != self.SUPPORTED_VERSION:
            log.warning("Expected ESMA version %s, got %s", self.SUPPORTED_VERSION, self.version)

        # Check for namespace — ESMA 1.2 should have NO default namespace
        ns_match = re.match(r'\{(.+)\}', root.tag)
        if ns_match:
            ns = ns_match.group(1)
            if "fsa-gov-uk" in ns:
                raise ValueError(
                    f"This file uses FCA namespace ({ns}). Use FCAAdapter instead."
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
            # Header fields
            "FilingType": _child_text(rec, "FilingType"),
            "AIFMContentType": _child_int(rec, "AIFMContentType"),
            "ReportingPeriodStartDate": _child_text(rec, "ReportingPeriodStartDate"),
            "ReportingPeriodEndDate": _child_text(rec, "ReportingPeriodEndDate"),
            "ReportingPeriodType": _child_text(rec, "ReportingPeriodType"),
            "ReportingPeriodYear": _child_int(rec, "ReportingPeriodYear"),
            "LastReportingFlag": _child_bool(rec, "LastReportingFlag"),
            "Assumptions": _parse_assumptions(rec),
            "AIFMReportingCode": _child_text(rec, "AIFMReportingCode"),
            "AIFMJurisdiction": _child_text(rec, "AIFMJurisdiction"),
            "AIFMNationalCode": _child_text(rec, "AIFMNationalCode"),
            "AIFMName": _child_text(rec, "AIFMName"),
            "AIFMEEAFlag": _child_bool(rec, "AIFMEEAFlag"),
            "AIFMNoReportingFlag": _child_bool(rec, "AIFMNoReportingFlag"),
        }

        # AIFM Complete Description
        desc = _find(rec, "AIFMCompleteDescription")
        if desc is not None:
            # AIFM Identifier
            ident = _find(desc, "AIFMIdentifier")
            if ident is not None:
                result["AIFMIdentifierLEI"] = _child_text(ident, "AIFMIdentifierLEI")

            # Principal Markets
            pm = _find(desc, "AIFMPrincipalMarkets")
            if pm is not None:
                result["AIFMPrincipalMarkets"] = _parse_principal_markets(pm, "AIFMFivePrincipalMarket")

            # Principal Instruments
            pi = _find(desc, "AIFMPrincipalInstruments")
            if pi is not None:
                result["AIFMPrincipalInstruments"] = _parse_principal_instruments(pi, "AIFMPrincipalInstrument")

            # AUM
            result["AUMAmountInEuro"] = _child_int(desc, "AUMAmountInEuro")

            # Base Currency Description
            result["BaseCurrencyDescription"] = _parse_base_currency_desc(desc)

        # Anonymize if requested
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
            "AIFEEAFlag": _child_bool(rec, "AIFEEAFlag"),
            "AIFReportingCode": _child_text(rec, "AIFReportingCode"),
            "AIFDomicile": _child_text(rec, "AIFDomicile"),
            "InceptionDate": _child_text(rec, "InceptionDate"),
            "AIFNoReportingFlag": _child_bool(rec, "AIFNoReportingFlag"),
        }

        # AIF Complete Description
        desc = _find(rec, "AIFCompleteDescription")
        if desc is None:
            if self.anonymize:
                self._anonymize_record(result)
            return result

        # AIFPrincipalInfo
        pi = _find(desc, "AIFPrincipalInfo")
        if pi is not None:
            # Identification
            ident_container = _find(pi, "AIFIdentification")
            if ident_container is not None:
                result["AIFIdentifierLEI"] = _child_text(ident_container, "AIFIdentifierLEI")

            # Share classes
            result["ShareClassFlag"] = _child_bool(pi, "ShareClassFlag")
            share_classes = _parse_share_classes(pi)
            if share_classes:
                result["ShareClasses"] = share_classes

            # AIF Description
            aif_desc = _find(pi, "AIFDescription")
            if aif_desc is not None:
                result["AIFMasterFeederStatus"] = _child_text(aif_desc, "AIFMasterFeederStatus")
                result["BaseCurrencyDescription"] = _parse_base_currency_desc(aif_desc)
                result["AIFNetAssetValue"] = _child_int(aif_desc, "AIFNetAssetValue")
                result["PredominantAIFType"] = _child_text(aif_desc, "PredominantAIFType")
                result["InvestmentStrategy"] = _parse_strategy(aif_desc)

            # Main instruments
            result["MainInstrumentsTraded"] = _parse_main_instruments_traded(pi)

            # Geographic focus
            result["NAVGeographicalFocus"] = _parse_geographical_focus(pi, "NAV")
            result["AUMGeographicalFocus"] = _parse_geographical_focus(pi, "AUM")

            # Principal exposures
            result["PrincipalExposures"] = _parse_principal_exposures(pi)

            # Portfolio concentrations
            result["PortfolioConcentrations"] = _parse_portfolio_concentrations(pi)

            # AIF principal markets (within MostImportantConcentration)
            result["AIFPrincipalMarkets"] = _parse_aif_principal_markets(pi)

            # Investor concentration
            result["InvestorConcentration"] = _parse_investor_concentration(pi)

        # Individual exposure, risk, stress tests, leverage
        result["IndividualExposure"] = _parse_individual_exposure(desc)
        result["RiskProfile"] = _parse_risk_profile(desc)
        result["StressTests"] = _parse_stress_tests(desc)
        result["LeverageInfo"] = _parse_leverage_info(desc)

        # Anonymize if requested
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

        # Anonymize instrument names in MainInstrumentsTraded
        for instr in record.get("MainInstrumentsTraded", []):
            if "InstrumentName" in instr:
                instr["InstrumentName"] = _anon_value("InstrumentName", instr["InstrumentName"])

        # Anonymize assumption descriptions
        for assumption in record.get("Assumptions", []):
            if "AssumptionDescription" in assumption:
                assumption["AssumptionDescription"] = _anon_value(
                    "AssumptionDescription", assumption["AssumptionDescription"]
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
            "source_format": self.source_format,
            "record_count": len(self.records),
            "schema_location": self.schema_location,
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
                    continue  # skip nested
                row[k] = v
            flat.append(row)
        return flat

    def _record_to_aifm_canonical(self, record: dict) -> CanonicalAIFMReport:
        """Convert a parsed AIFM record dict to CanonicalAIFMReport.

        Maps ESMA field names from the parsed record to ESMA field IDs (Q1-Q38).
        """
        report = CanonicalAIFMReport()

        # Field mappings: ESMA question number -> record key
        # Uses official ESMA Annex IV question numbering (Q1-Q38 for AIFM)
        field_map = {
            # Report metadata (Q1-Q13)
            "1": "_reporting_member_state",
            "4": "FilingType",
            "5": "AIFMContentType",
            "6": "ReportingPeriodStartDate",
            "7": "ReportingPeriodEndDate",
            "8": "ReportingPeriodType",
            "9": "ReportingPeriodYear",
            "13": "LastReportingFlag",
            # AIFM entity fields (Q16-Q25)
            "16": "AIFMReportingCode",
            "17": "AIFMJurisdiction",
            "18": "AIFMNationalCode",
            "19": "AIFMName",
            "20": "AIFMEEAFlag",
            "21": "AIFMNoReportingFlag",
            "22": "AIFMIdentifierLEI",
            "23": "AIFMBICCode",
        }

        # Set scalar fields
        for field_id, key in field_map.items():
            if key in record and record[key] is not None:
                report.set_field(
                    field_id,
                    record[key],
                    source="esma_adapter",
                    priority=SourcePriority.IMPORTED,
                    source_ref=self.source_filename
                )

        # Handle Assumptions as repeating group
        if "Assumptions" in record and record["Assumptions"]:
            for assumption in record["Assumptions"]:
                item_values = {}
                if assumption.get("QuestionNumber"):
                    item_values["QuestionNumber"] = assumption["QuestionNumber"]
                if assumption.get("AssumptionDescription"):
                    item_values["AssumptionDescription"] = assumption["AssumptionDescription"]
                if item_values:
                    report.add_group_item(
                        "assumptions", item_values,
                        source="esma_adapter",
                        priority=SourcePriority.IMPORTED,
                    )

        # Handle BaseCurrencyDescription
        if "BaseCurrencyDescription" in record and record["BaseCurrencyDescription"]:
            bcd = record["BaseCurrencyDescription"]
            bcd_values = {}
            for key in ("BaseCurrency", "AUMAmountInBaseCurrency",
                        "FXEURReferenceRateType", "FXEURRate"):
                if bcd.get(key):
                    bcd_values[key] = bcd[key]
            if bcd_values:
                report.add_group_item(
                    "base_currency_description", bcd_values,
                    source="esma_adapter",
                    priority=SourcePriority.IMPORTED,
                )

        # Handle AUMAmountInEuro
        if "AUMAmountInEuro" in record and record["AUMAmountInEuro"] is not None:
            report.set_field(
                "15",
                record["AUMAmountInEuro"],
                source="esma_adapter",
                priority=SourcePriority.IMPORTED,
                source_ref=self.source_filename
            )

        return report

    def _record_to_aif_canonical(self, record: dict) -> CanonicalAIFReport:
        """Convert a parsed AIF record dict to CanonicalAIFReport.

        Maps ESMA field names from the parsed record to ESMA field IDs.
        """
        report = CanonicalAIFReport()

        # Field mappings: ESMA question number -> record key
        # Uses official ESMA Annex IV question numbering for AIF
        field_map = {
            # AIF identification and structure
            "18": "AIFName",
            "19": "AIFEEAFlag",
            "21": "AIFDomicile",
            "22": "InceptionDate",
            "24": "AIFIdentifierLEI",
            # Report metadata
            "4": "FilingType",
            "5": "AIFContentType",
            "6": "ReportingPeriodStartDate",
            "7": "ReportingPeriodEndDate",
            "8": "ReportingPeriodType",
            "9": "ReportingPeriodYear",
            "11": "AIFReportingCode",
            "13": "LastReportingFlag",
            "15": "AIFNoReportingFlag",
        }

        # Set scalar fields
        for field_id, key in field_map.items():
            if key in record and record[key] is not None:
                report.set_field(
                    field_id,
                    record[key],
                    source="esma_adapter",
                    priority=SourcePriority.IMPORTED,
                    source_ref=self.source_filename
                )

        # AIF national code
        if "AIFNationalCode" in record and record["AIFNationalCode"] is not None:
            report.set_field("1", record["AIFNationalCode"],
                           source="esma_adapter", priority=SourcePriority.IMPORTED)

        # AIFM national code (reference back to manager)
        if "AIFMNationalCode" in record and record["AIFMNationalCode"] is not None:
            report.set_field("2", record["AIFMNationalCode"],
                           source="esma_adapter", priority=SourcePriority.IMPORTED)

        # NAV
        if "AIFNetAssetValue" in record and record["AIFNetAssetValue"] is not None:
            report.set_field("10", record["AIFNetAssetValue"],
                           source="esma_adapter", priority=SourcePriority.IMPORTED)

        return report

    def to_canonical_aifm(self, record_index: int = 0) -> CanonicalAIFMReport:
        """Create a CanonicalAIFMReport from one parsed AIFM record.

        Args:
            record_index: Index of the record to convert (default: 0).

        Returns:
            CanonicalAIFMReport with fields populated from the parsed record.

        Raises:
            IndexError: If record_index is out of bounds.
            ValueError: If record is not an AIFM record.
        """
        if record_index >= len(self.records):
            raise IndexError(f"Record index {record_index} out of bounds (only {len(self.records)} records)")

        record = self.records[record_index]

        if record.get("_report_type") != "AIFM":
            raise ValueError(f"Record {record_index} is not an AIFM report (type: {record.get('_report_type')})")

        return self._record_to_aifm_canonical(record)

    def to_canonical_aifs(self) -> list[CanonicalAIFReport]:
        """Create CanonicalAIFReport instances from all parsed AIF records.

        Returns:
            List of CanonicalAIFReport objects, one per AIF record.

        Raises:
            ValueError: If any record is not an AIF record.
        """
        aif_reports = []
        for idx, record in enumerate(self.records):
            if record.get("_report_type") != "AIF":
                raise ValueError(f"Record {idx} is not an AIF report (type: {record.get('_report_type')})")
            aif_reports.append(self._record_to_aif_canonical(record))
        return aif_reports

    def to_source_canonical(self) -> tuple[SourceCanonical, list[SourceCanonical]]:
        """Export parsed ESMA data to Source Canonical via reverse-lift.

        Since ESMA XML only contains report-level data (no rich source data),
        only entity-classified fields are lifted into source entities.
        Composite and report-specific fields remain on the Report Canonical only.

        Returns:
            Tuple of (aifm_source, aif_sources) where:
            - aifm_source: SourceCanonical from AIFM record (if present), else empty
            - aif_sources: List of SourceCanonical from AIF records
        """
        aifm_source = SourceCanonical(source_adapter="esma_adapter")
        aif_sources = []

        if self.report_type == "AIFM":
            if self.records:
                record = self.records[0]  # Typically one AIFM record
                report = self._record_to_aifm_canonical(record)
                aifm_source = reverse_lift_aifm(report)

        elif self.report_type == "AIF":
            for record in self.records:
                report = self._record_to_aif_canonical(record)
                aif_source = reverse_lift_aif(report)
                aif_sources.append(aif_source)

        return aifm_source, aif_sources
