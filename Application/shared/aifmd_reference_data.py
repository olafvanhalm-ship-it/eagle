"""AIFMD-specific reference data — position-to-turnover sub-asset type mapping."""

from .reference_data import _COUNTRY_TO_REGION  # noqa: F401 — re-export for convenience

# Complete Position SubAssetType → Turnover SubAssetType mapping
# from ESMA Annex II Table 2 (via M adapter FAQs).
# Most follow the pattern part1_part2_part2, but several are exceptions.
_SUBASSET_TO_TURNOVER = {
    # Securities - Cash
    "SEC_CSH_CODP": "SEC_CSH_CSH", "SEC_CSH_COMP": "SEC_CSH_CSH",
    "SEC_CSH_OTHD": "SEC_CSH_CSH", "SEC_CSH_OTHC": "SEC_CSH_CSH",
    # Securities - Listed equities
    "SEC_LEQ_IFIN": "SEC_LEQ_LEQ", "SEC_LEQ_OTHR": "SEC_LEQ_LEQ",
    # Securities - Unlisted equities
    "SEC_UEQ_UEQY": "SEC_UEQ_UEQ",
    # Securities - Corporate bonds (non-financial)  ← exception: IVG / NIG
    "SEC_CPN_INVG": "SEC_CPN_IVG", "SEC_CPN_NIVG": "SEC_CPN_NIG",
    # Securities - Corporate bonds (financial)  ← exception: maps to CPI
    "SEC_CPI_INVG": "SEC_CPI_CPI", "SEC_CPI_NIVG": "SEC_CPI_CPI",
    # Securities - Sovereign bonds
    "SEC_SBD_EUBY": "SEC_SBD_EUB", "SEC_SBD_EUBM": "SEC_SBD_EUB",
    "SEC_SBD_NOGY": "SEC_SBD_NEU", "SEC_SBD_NOGM": "SEC_SBD_NEU",
    "SEC_SBD_EUGY": "SEC_SBD_NEU", "SEC_SBD_EUGM": "SEC_SBD_NEU",
    # Securities - Municipal bonds  ← exception: MBN→MUN
    "SEC_MBN_MNPL": "SEC_MUN_MUN",
    # Securities - Convertible bonds  ← exception: CBN/CBI → CBD
    "SEC_CBN_INVG": "SEC_CBD_CBD", "SEC_CBN_NIVG": "SEC_CBD_CBD",
    "SEC_CBI_INVG": "SEC_CBD_CBD", "SEC_CBI_NIVG": "SEC_CBD_CBD",
    # Securities - Loans
    "SEC_LON_LEVL": "SEC_LON_LON", "SEC_LON_OTHL": "SEC_LON_LON",
    # Securities - Structured/securitised products
    "SEC_SSP_SABS": "SEC_SSP_SSP", "SEC_SSP_RMBS": "SEC_SSP_SSP",
    "SEC_SSP_CMBS": "SEC_SSP_SSP", "SEC_SSP_AMBS": "SEC_SSP_SSP",
    "SEC_SSP_ABCP": "SEC_SSP_SSP", "SEC_SSP_CDOC": "SEC_SSP_SSP",
    "SEC_SSP_STRC": "SEC_SSP_SSP", "SEC_SSP_SETP": "SEC_SSP_SSP",
    "SEC_SSP_OTHS": "SEC_SSP_SSP",
    # Derivatives - Equity
    "DER_EQD_FINI": "DER_EQD_EQD", "DER_EQD_OTHD": "DER_EQD_EQD",
    # Derivatives - Fixed income
    "DER_FID_FIXI": "DER_FID_FID",
    # Derivatives - CDS
    "DER_CDS_SNFI": "DER_CDS_CDS", "DER_CDS_SNSO": "DER_CDS_CDS",
    "DER_CDS_SNOT": "DER_CDS_CDS", "DER_CDS_INDX": "DER_CDS_CDS",
    "DER_CDS_EXOT": "DER_CDS_CDS", "DER_CDS_OTHR": "DER_CDS_CDS",
    # Derivatives - Foreign exchange  ← exception: INV / HED
    "DER_FEX_INVT": "DER_FEX_INV", "DER_FEX_HEDG": "DER_FEX_HED",
    # Derivatives - Interest rate
    "DER_IRD_INTR": "DER_IRD_IRD",
    # Derivatives - Commodity
    "DER_CTY_ECOL": "DER_CTY_CTY", "DER_CTY_ENNG": "DER_CTY_CTY",
    "DER_CTY_ENPW": "DER_CTY_CTY", "DER_CTY_ENOT": "DER_CTY_CTY",
    "DER_CTY_PMGD": "DER_CTY_CTY", "DER_CTY_PMOT": "DER_CTY_CTY",
    "DER_CTY_OTIM": "DER_CTY_CTY", "DER_CTY_OTLS": "DER_CTY_CTY",
    "DER_CTY_OTAP": "DER_CTY_CTY", "DER_CTY_OTHR": "DER_CTY_CTY",
    # Derivatives - Other
    "DER_OTH_OTHR": "DER_OTH_OTH",
    # Physical assets
    "PHY_RES_RESL": "PHY_RES_RES", "PHY_RES_COML": "PHY_RES_RES",
    "PHY_RES_OTHR": "PHY_RES_RES",
    "PHY_CTY_PCTY": "PHY_CTY_CTY", "PHY_TIM_PTIM": "PHY_TIM_TIM",
    "PHY_ART_PART": "PHY_ART_ART", "PHY_TPT_PTPT": "PHY_TPT_TPT",
    "PHY_OTH_OTHR": "PHY_OTH_OTH",
    # Collective Investment Undertakings
    "CIU_OAM_MMFC": "CIU_CIU_CIU", "CIU_OAM_AETF": "CIU_CIU_CIU",
    "CIU_OAM_OTHR": "CIU_CIU_CIU",
    "CIU_NAM_MMFC": "CIU_CIU_CIU", "CIU_NAM_AETF": "CIU_CIU_CIU",
    "CIU_NAM_OTHR": "CIU_CIU_CIU",
    # Other
    "OTH_OTH_OTHR": "OTH_OTH_OTH",
    # No-turnover-applicable
    "NTA_NTA_NOTA": "NTA_NTA_NOTA",
    # ── Identity mappings for turnover codes themselves ──────────────────
    # When the adapter receives explicit TURNOVER records (not positions),
    # the codes are already valid turnover sub-asset types. Adding them
    # as identity mappings prevents the fallback pattern (part1_part2_part2)
    # from corrupting valid codes like SEC_SBD_EUB → SEC_SBD_SBD.
    "SEC_CSH_CSH": "SEC_CSH_CSH",
    "SEC_LEQ_LEQ": "SEC_LEQ_LEQ",
    "SEC_UEQ_UEQ": "SEC_UEQ_UEQ",
    "SEC_CPN_IVG": "SEC_CPN_IVG",
    "SEC_CPN_NIG": "SEC_CPN_NIG",
    "SEC_CPI_CPI": "SEC_CPI_CPI",
    "SEC_SBD_EUB": "SEC_SBD_EUB",
    "SEC_SBD_NEU": "SEC_SBD_NEU",
    "SEC_MUN_MUN": "SEC_MUN_MUN",
    "SEC_CBD_CBD": "SEC_CBD_CBD",
    "SEC_LON_LON": "SEC_LON_LON",
    "SEC_SSP_SSP": "SEC_SSP_SSP",
    "DER_EQD_EQD": "DER_EQD_EQD",
    "DER_FID_FID": "DER_FID_FID",
    "DER_CDS_CDS": "DER_CDS_CDS",
    "DER_FEX_INV": "DER_FEX_INV",
    "DER_FEX_HED": "DER_FEX_HED",
    "DER_IRD_IRD": "DER_IRD_IRD",
    "DER_CTY_CTY": "DER_CTY_CTY",
    "DER_OTH_OTH": "DER_OTH_OTH",
    "PHY_RES_RES": "PHY_RES_RES",
    "PHY_CTY_CTY": "PHY_CTY_CTY",
    "PHY_TIM_TIM": "PHY_TIM_TIM",
    "PHY_ART_ART": "PHY_ART_ART",
    "PHY_TPT_TPT": "PHY_TPT_TPT",
    "PHY_OTH_OTH": "PHY_OTH_OTH",
    "CIU_CIU_CIU": "CIU_CIU_CIU",
    "OTH_OTH_OTH": "OTH_OTH_OTH",
}
