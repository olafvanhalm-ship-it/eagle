"""AIFMD-specific constants — XSD, FCA, strategy mappings, and thresholds."""

from .constants import EEA_COUNTRIES, REGION_MAP  # noqa: F401 — re-export for convenience

# Strategy code → PredominantAIFType
STRATEGY_TO_AIF_TYPE = {
    "EQTY": "HFND", "RELV": "HFND", "EVDR": "HFND", "CRED": "HFND",
    "MACR": "HFND", "MANF": "HFND", "MULT_HFND": "HFND", "OTHR_HFND": "HFND",
    "RESL": "REST", "COML": "REST", "INDL": "REST", "MULT_REST": "REST",
    "OTHR_REST": "REST",
    "VENT": "PEQF", "GRTH": "PEQF", "MZNE": "PEQF", "MULT_PEQF": "PEQF",
    "OTHR_PEQF": "PEQF",
    "FOFS": "FOFS", "OTHR_FOFS": "FOFS",
    "OTHR_COMF": "OTHR", "OTHR_EQYF": "OTHR", "OTHR_FXIF": "OTHR",
    "OTHR_INFF": "OTHR", "OTHR_OTHF": "OTHR",
}

# PredominantAIFType → XML strategy element names
STRATEGY_ELEMENT_MAP = {
    "HFND": ("HedgeFundInvestmentStrategies", "HedgeFundStrategy", "HedgeFundStrategyType"),
    "REST": ("RealEstateFundInvestmentStrategies", "RealEstateFundStrategy", "RealEstateFundStrategyType"),
    "PEQF": ("PrivateEquityFundInvestmentStrategies", "PrivateEquityFundInvestmentStrategy", "PrivateEquityFundStrategyType"),
    "FOFS": ("FundOfFundsInvestmentStrategies", "FundOfFundsStrategy", "FundOfFundsStrategyType"),
    "OTHR": ("OtherFundInvestmentStrategies", "OtherFundStrategy", "OtherFundStrategyType"),
}

XSD_VERSION = "1.2"
AIFM_XSD = "AIFMD_DATMAN_V1.2.xsd"
AIF_XSD = "AIFMD_DATAIF_V1.2.xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# FCA (UK) format constants
FCA_VERSION = "2.0"
FCA_AIFM_NS = "urn:fsa-gov-uk:MER:AIF001:2"
FCA_AIF_NS = "urn:fsa-gov-uk:MER:AIF002:2"

# FCA geographic region mapping — UK-centric instead of EEA-centric
FCA_REGION_MAP = {
    "AFRICA": "Africa",
    "ASIAPACIFIC": "AsiaPacific",
    "UK": "UK",
    "EUROPENONUK": "EuropeNonUK",
    "MIDDLEEAST": "MiddleEast",
    "NORTHAMERICA": "NorthAmerica",
    "SOUTHAMERICA": "SouthAmerica",
    "SUPRANATIONAL": "SupraNational",
}

# ESMA Question Number → FCA Field Reference mapping
# Source: M adapter FAQ, FCA RegData field numbering
_ESMA_TO_FCA_FIELD = {
    "7": "18A",   # AIFM Assumptions
    "8": "19A",   # AIF Assumptions
}

# FCA aggregated value percentage threshold (FAQ: 0.5% of AUM)
# Positions below this threshold cause RegData rounding-error rejections.
# Replace with NTA/NTA_NTA entries per M adapter FAQ.
FCA_AGG_VALUE_MIN_PCT = 0.5

# FCA sovereign bond sub-asset type conversion (ESMA → FCA)
# Source: FCA XSD V2 changelog + M adapter FAQ "straightforward heuristics"
# Key: ESMA XSD has SEC_SBD_EUBY/EUBM (EU bonds). FCA XSD replaces these with
#      SEC_SBD_UKBY/UKBM (UK bonds) and keeps SEC_SBD_EUGY/EUGM (G10 non-UK bonds).
# Heuristic: use position currency to determine if the bond is UK (GBP) or not.
#   - GBP currency → SEC_SBD_EUBY → SEC_SBD_UKBY, SEC_SBD_EUBM → SEC_SBD_UKBM
#   - Non-GBP      → SEC_SBD_EUBY → SEC_SBD_EUGY, SEC_SBD_EUBM → SEC_SBD_EUGM
# Turnover mapping is simpler:
#   - SEC_SBD_EUB → SEC_SBD_UKB (UK bonds), SEC_SBD_NEU → SEC_SBD_NUK (non-UK)
FCA_SOVEREIGN_TURNOVER_MAP = {
    "SEC_SBD_EUB": "SEC_SBD_UKB",    # EU member state bonds → UK bonds
    "SEC_SBD_NEU": "SEC_SBD_NUK",    # Non-EU bonds → Non-UK bonds
}
