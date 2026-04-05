"""AIF XML generation mixin."""

from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement

from shared.aifmd_constants import (
    XSD_VERSION, AIF_XSD, XSI_NS,
    FCA_VERSION, FCA_AIF_NS,
    REGION_MAP, STRATEGY_ELEMENT_MAP,
    FCA_REGION_MAP, FCA_AGG_VALUE_MIN_PCT, FCA_SOVEREIGN_TURNOVER_MAP,
    _ESMA_TO_FCA_FIELD,
)
from shared.formatting import (
    _str, _int_round, _float_val, _rate_fmt, _bool_str, _date_str,
    _is_eea, _sub, _macro_type, _asset_type, _turnover_sub_asset_type,
    _predominant_type, _pretty_xml, _reporting_period_dates, _fca_sovereign_sub_asset,
)

from derivation.aifmd_period import _derive_aif_period


class AifBuilderMixin:
    """Mixin for AIF XML generation methods."""

    def generate_aif_xml(self, output_path: str = None,
                         aif_index: int = None,
                         reporting_member_state: str = None,
                         override_national_code: str = None) -> str:
        rms = reporting_member_state or self.reporting_member_state
        is_fca = (rms == "GB")

        root = Element("AIFReportingInfo")
        if is_fca:
            root.set("xmlns", FCA_AIF_NS)
        root.set("CreationDateAndTime", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        root.set("ReportingMemberState", rms)
        root.set("Version", FCA_VERSION if is_fca else XSD_VERSION)
        if not is_fca:
            root.set("xsi:noNamespaceSchemaLocation", AIF_XSD)
            root.set("xmlns:xsi", XSI_NS)

        if aif_index is not None:
            self._build_aif_record(root, self.aifs[aif_index], rms,
                                   override_national_code=override_national_code)
        else:
            for aif in self.aifs:
                self._build_aif_record(root, aif, rms)

        xml_str = _pretty_xml(root)

        lines = xml_str.split("\n")
        nca_label = "FCA" if is_fca else "ESMA"
        comment = f"<!-- {nca_label} AIF. Created by Eagle Platform (M adapter). -->"
        xml_str = lines[0] + "\n" + comment + "\n" + "\n".join(lines[1:])

        if output_path:
            Path(output_path).write_text(xml_str, encoding="utf-8")
        return xml_str

    def generate_fca_consolidated_aif_xml(
        self, output_path: str = None,
        reporting_member_state: str = "GB",
    ) -> str:
        """Generate a single consolidated FCA AIF XML with all AIFs.

        FCA allows (and expects) all AIFs for one AIFM to be submitted in a
        single XML file with multiple <AIFRecordInfo> elements under one
        <AIFReportingInfo> root.  This is different from the ESMA convention
        where each AIF gets its own XML file.

        Naming convention: AIF_REPORTS_GB_{AIFM_NC}_{YYYYMMDD}.xml
        """
        rms = reporting_member_state
        root = Element("AIFReportingInfo")
        root.set("xmlns", FCA_AIF_NS)
        root.set("CreationDateAndTime", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        root.set("ReportingMemberState", rms)
        root.set("Version", FCA_VERSION)

        # Add ALL AIFs as separate AIFRecordInfo blocks inside the same file
        for aif in self.aifs:
            self._build_aif_record(root, aif, rms)

        xml_str = _pretty_xml(root)
        lines = xml_str.split("\n")
        comment = "<!-- FCA AIF. Created by Eagle Platform (M adapter). -->"
        xml_str = lines[0] + "\n" + comment + "\n" + "\n".join(lines[1:])

        if output_path:
            Path(output_path).write_text(xml_str, encoding="utf-8")
        return xml_str

    # ── Per-AIF content type logic ─────────────────────────────────────

    @staticmethod
    def _aif_content_type(aif: dict) -> int:
        """Return the AIF Content Type (field 5) as an integer.

        Content types per ESMA:
          1 → 24(1) only
          2 → 24(1) + 24(2)
          3 → 3(3)(d) registered
          4 → 24(1) + 24(2) + 24(4)
          5 → 24(1) + 24(4)
        Returns 0 if not set.
        """
        ct = aif.get("AIF Content Type") or aif.get("AIF content type")
        try:
            return int(ct)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_registered_aif(aif: dict) -> bool:
        """Return True if this AIF uses registered/light (3(3)(d)) reporting."""
        ct = aif.get("AIF Content Type") or aif.get("AIF content type")
        try:
            return int(ct) == 3
        except (TypeError, ValueError):
            return False

    def _aif_is_full(self, aif: dict) -> bool:
        """Return True if this AIF should get full-template XML sections.

        An AIF gets full sections when the overall template is FULL
        and the AIF is NOT a registered (3(3)(d)) fund.
        """
        if self._is_registered_aif(aif):
            return False
        return self.template_type == "FULL"

    @staticmethod
    def _aif_needs_individual_info(aif: dict) -> bool:
        """Return True if this AIF needs AIFIndividualInfo (24(2) contents).

        Required when AIF Content Type ∈ {2, 4} per CAF-002.
        """
        ct = aif.get("AIF Content Type") or aif.get("AIF content type")
        try:
            return int(ct) in (2, 4)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _aif_needs_leverage_24_4(aif: dict) -> bool:
        """Return True if this AIF needs AIFLeverageArticle24-4.

        Required when AIF Content Type ∈ {4, 5} per CAF-002.
        """
        ct = aif.get("AIF Content Type") or aif.get("AIF content type")
        try:
            return int(ct) in (4, 5)
        except (TypeError, ValueError):
            return False

    def _build_aif_record(self, root: Element, aif: dict,
                          reporting_member_state: str = "",
                          override_national_code: str = None):
        aif_id = _str(aif.get("Custom AIF Identification", "") or aif.get("AIF ID", ""))
        positions = self._positions_for_aif(aif_id)
        is_full = self._aif_is_full(aif)

        # For full/authorised AIFs, use AIF-level AUM/NAV; for registered, calculate from positions
        if is_full:
            aum_val = aif.get("Total AuM amount of the AIF in base currency")
            nav_val = aif.get("Total Net Asset Value of the AIF (NAV)")
            aum = _int_round(aum_val) if aum_val else self._calc_aum(positions)
            nav = _int_round(nav_val) if nav_val else self._calc_nav(positions)
        else:
            aum = self._calc_aum(positions)
            nav = self._calc_nav(positions)

        domicile = (_str(aif.get("Domicile of the AIF", "")) or
                    _str(aif.get("AIF Domicile", "")) or
                    _str(aif.get("Domicile", "")) or
                    self.aifm_jurisdiction or
                    self.reporting_member_state)
        strategy_code = _str(aif.get("Investment strategy code", ""))
        aif_lei = _str(aif.get("AIF LEI code", ""))

        # For full/authorised AIFs, get national code for this reporting member state
        if override_national_code:
            aif_nc = override_national_code
        else:
            aif_nc = _str(aif.get("AIF National Code", ""))
            if is_full and reporting_member_state and self.aif_national_codes:
                for nc_rec in self.aif_national_codes:
                    nc_rms = _str(nc_rec.get("AIF Reporting Member State", "") or
                                  nc_rec.get("Reporting Member State", ""))
                    nc_aif_id = _str(nc_rec.get("Custom AIF Identification", "") or
                                     nc_rec.get("AIF ID", ""))
                    if nc_rms == reporting_member_state and nc_aif_id == aif_id:
                        aif_nc = _str(nc_rec.get("AIF National Code", "") or
                                      nc_rec.get("AIF national code", ""))
                        break

        # Get AIFM national code (always look up for CANCEL filings too)
        aifm_nc = self.aifm_national_code
        if reporting_member_state and self.aifm_national_codes:
            for nc_rec in self.aifm_national_codes:
                nc_rms = _str(nc_rec.get("AIFM Reporting Member State", "") or
                              nc_rec.get("Reporting Member State", ""))
                if nc_rms == reporting_member_state:
                    aifm_nc = _str(nc_rec.get("AIFM National Code", ""))
                    break

        # ── CANCEL filing → CancellationAIFRecordInfo (ESMA-compliant) ──
        aif_filing_type = _str(aif.get("Filing Type", "")) or self.filing_type
        if aif_filing_type.upper() == "CANCEL":
            crec = _sub(root, "CancellationAIFRecordInfo")
            _sub(crec, "CancelledAIFNationalCode", aif_nc)
            _sub(crec, "CancelledAIFMNationalCode", aifm_nc)
            _sub(crec, "CancelledReportingPeriodType", self.reporting_period_type)
            _sub(crec, "CancelledReportingPeriodYear", str(self.reporting_year))
            _sub(crec, "CancelledRecordFlag", "C")
            return  # Cancellation records have no further content

        # ── INIT / AMND → normal AIFRecordInfo ──
        rec = _sub(root, "AIFRecordInfo")
        _sub(rec, "FilingType", aif_filing_type)

        # ContentType: use value from AIF record (field 5), fallback to derived value
        content_type_raw = aif.get("AIF Content Type") or aif.get("AIF content type")
        if content_type_raw is not None:
            content_type = str(int(content_type_raw))
        else:
            content_type = "3" if self._is_registered_aif(aif) else "2"
        _sub(rec, "AIFContentType", content_type)

        # Reporting period — AIF may have its own period type; if empty, derive
        # from AIFM period + inception date (new funds start next quarter).
        inception_date_raw = aif.get("Inception Date of AIF")
        inception_date_str = _date_str(inception_date_raw)

        aif_period_type_raw = _str(aif.get("Reporting Period Type", ""))
        if aif_period_type_raw:
            # Explicit AIF period type
            aif_period_type = aif_period_type_raw
            period_start, period_end = _reporting_period_dates(
                aif_period_type, self.reporting_year)
        else:
            # Derive from AIFM period + inception date
            aif_period_type, period_start, period_end = _derive_aif_period(
                self.reporting_period_type, self.reporting_year, inception_date_str)

        # Store for use in sub-methods (e.g. HRP month range)
        self._current_aif_period_type = aif_period_type
        _sub(rec, "ReportingPeriodStartDate", period_start)
        _sub(rec, "ReportingPeriodEndDate", period_end)
        _sub(rec, "ReportingPeriodType", aif_period_type)
        _sub(rec, "ReportingPeriodYear", str(self.reporting_year))

        # Obligation change codes (optional, typically AMND only)
        aif_obl_freq = _str(aif.get("Change in AIF Reporting Obligation Frequency Code", ""))
        aif_obl_cont = _str(aif.get("Change in AIF Reporting Obligation contents Code",
                            aif.get("Change in AIF Reporting Obligation Contents Code", "")))
        aif_obl_qtr = _str(aif.get("Change in AIF Reporting Obligation Quarter", ""))
        if aif_obl_freq and aif_obl_freq.lower() not in ("none", "n/a", ""):
            _sub(rec, "AIFReportingObligationChangeFrequencyCode", aif_obl_freq)
        if aif_obl_cont and aif_obl_cont.lower() not in ("none", "n/a", ""):
            _sub(rec, "AIFReportingObligationChangeContentsCode", aif_obl_cont)
        if aif_obl_qtr and aif_obl_qtr.lower() not in ("none", "n/a", ""):
            _sub(rec, "AIFReportingObligationChangeQuarter", aif_obl_qtr)

        _sub(rec, "LastReportingFlag", _bool_str(aif.get("Last reporting flag")))

        # AIF-level Assumptions (XSD: after LastReportingFlag, before AIFMNationalCode)
        if hasattr(self, 'aif_assumptions') and self.aif_assumptions:
            assumptions = _sub(rec, "Assumptions")
            for a_rec in self.aif_assumptions:
                a_elem = _sub(assumptions, "Assumption")
                q_num = _str(a_rec.get("Question Number", ""))
                a_desc = _str(a_rec.get("Assumption Description", ""))
                if reporting_member_state == "GB":
                    fca_ref = _ESMA_TO_FCA_FIELD.get(q_num, q_num)
                    _sub(a_elem, "FCAFieldReference", fca_ref)
                    _sub(a_elem, "AssumptionDetails", a_desc)
                else:
                    _sub(a_elem, "QuestionNumber", q_num)
                    _sub(a_elem, "AssumptionDescription", a_desc)

        _sub(rec, "AIFMNationalCode", aifm_nc)
        _sub(rec, "AIFNationalCode", aif_nc)
        _sub(rec, "AIFName", _str(aif.get("AIF Name", "")))
        if reporting_member_state != "GB":
            _sub(rec, "AIFEEAFlag", str(_is_eea(domicile)).lower())

        # Reporting code: from AIF record, default "1"
        reporting_code = _str(aif.get("AIF reporting code", "")) or "1"
        _sub(rec, "AIFReportingCode", reporting_code)
        _sub(rec, "AIFDomicile", domicile)
        _sub(rec, "InceptionDate", inception_date_str)

        # BaFin inception date validation: must be strictly before period start
        if reporting_member_state == "DE" and inception_date_str:
            period_start, _ = _reporting_period_dates(
                self.reporting_period_type, self.reporting_year)
            if period_start and inception_date_str >= period_start:
                import warnings
                warnings.warn(
                    f"BaFin validation: InceptionDate ({inception_date_str}) must be "
                    f"strictly before reporting period start ({period_start}). "
                    f"ESMA allows equal, BaFin does not.",
                    stacklevel=2)

        no_reporting = _bool_str(
            aif.get("AIF No Reporting Flag") or
            aif.get("AIF No Reporting Flag (Nothing to report)"))
        _sub(rec, "AIFNoReportingFlag", no_reporting)

        if no_reporting == "false":
            self._build_aif_complete_description(rec, aif, positions, aum, nav,
                                                  strategy_code, aif_lei, aif_id, is_full,
                                                  reporting_member_state=reporting_member_state)

    def _build_aif_complete_description(self, rec: Element, aif: dict,
                                         positions: list, aum: int, nav: int,
                                         strategy_code: str, aif_lei: str, aif_id: str,
                                         is_full: bool = True,
                                         reporting_member_state: str = ""):
        """Build AIFCompleteDescription section."""
        desc = _sub(rec, "AIFCompleteDescription")
        info = _sub(desc, "AIFPrincipalInfo")

        # AIF Identification (XSD order: LEI, ISIN, CUSIP, SEDOL, Ticker, RIC, ECB)
        aif_isin = _str(aif.get("AIF ISIN Code", ""))
        aif_cusip = _str(aif.get("AIF CUSIP Code", ""))
        aif_sedol = _str(aif.get("AIF Sedol Code", aif.get("AIF SEDOL Code", "")))
        aif_bloomberg = _str(aif.get("AIF Bloomberg Code", ""))
        aif_reuters = _str(aif.get("AIF Reuters Code", ""))
        aif_ecb = _str(aif.get("AIF ECB Code", ""))
        has_any_id = any([aif_lei, aif_isin, aif_cusip, aif_sedol,
                          aif_bloomberg, aif_reuters, aif_ecb])
        if has_any_id:
            ident = _sub(info, "AIFIdentification")
            if aif_lei and aif_lei.lower() not in ("n/a", "na", "-", ""):
                _sub(ident, "AIFIdentifierLEI", aif_lei)
            if aif_isin:
                _sub(ident, "AIFIdentifierISIN", aif_isin)
            if aif_cusip:
                _sub(ident, "AIFIdentifierCUSIP", aif_cusip)
            if aif_sedol:
                _sub(ident, "AIFIdentifierSEDOL", aif_sedol)
            if aif_bloomberg:
                _sub(ident, "AIFIdentifierTicker", aif_bloomberg)
            if aif_reuters:
                _sub(ident, "AIFIdentifierRIC", aif_reuters)
            if aif_ecb and reporting_member_state != "GB":
                _sub(ident, "AIFIdentifierECB", aif_ecb)  # FCA v2 removed ECB code

        # Share classes (full/authorised AIFs)
        is_fca_aif = (reporting_member_state == "GB")
        if is_full:
            share_classes_for_aif = [
                sc for sc in self.share_classes
                if _str(sc.get("Custom AIF Identification", "") or
                        sc.get("AIF ID", "")) == aif_id
            ]
            if share_classes_for_aif:
                _sub(info, "ShareClassFlag", "true")
                scs = _sub(info, "ShareClassIdentification")
                for idx, sc in enumerate(share_classes_for_aif, 1):
                    sci = _sub(scs, "ShareClassIdentifier")
                    nc = _str(sc.get("Share class national code",
                              sc.get("Share Class National Code", "")))
                    isin = _str(sc.get("Share class ISIN code",
                               sc.get("Share Class ISIN Code", "")))
                    sedol = _str(sc.get("Share class SEDOL code",
                                sc.get("Share Class SEDOL Code", "")))
                    cusip = _str(sc.get("Share class CUSIP code",
                                sc.get("Share Class CUSIP Code", "")))
                    bloomberg = _str(sc.get("Share class Bloomberg code",
                                   sc.get("Share Class Bloomberg Code", "")))
                    reuters = _str(sc.get("Share class Reuters code",
                                  sc.get("Share Class Reuters Code", "")))
                    # FCA RegData: at least one identification code required
                    # Auto-insert dummy national code when all codes are empty
                    has_any_code = any([nc, isin, sedol, cusip, bloomberg, reuters])
                    if is_fca_aif and not has_any_code:
                        nc = f"No Code Available {idx}"
                    _sub(sci, "ShareClassNationalCode", nc)
                    if isin:
                        _sub(sci, "ShareClassIdentifierISIN", isin)
                    if cusip:
                        _sub(sci, "ShareClassIdentifierCUSIP", cusip)
                    if sedol:
                        _sub(sci, "ShareClassIdentifierSEDOL", sedol)
                    if bloomberg:
                        _sub(sci, "ShareClassIdentifierTicker", bloomberg)
                    if reuters:
                        _sub(sci, "ShareClassIdentifierRIC", reuters)
                    _sub(sci, "ShareClassName",
                         _str(sc.get("Share class name",
                              sc.get("Share Class Name", ""))))
            else:
                _sub(info, "ShareClassFlag", "false")
        else:
            has_share_classes = any(
                _str(sc.get("Custom AIF Identification", "") or sc.get("AIF ID", "")) == aif_id
                for sc in self.share_classes
            )
            _sub(info, "ShareClassFlag", str(has_share_classes).lower())

        # AIF Description
        aif_desc = _sub(info, "AIFDescription")

        # Master-Feeder status
        # Check AIF record field first (e.g. "Master feeder status" = MASTER/FEEDER/NONE)
        mf_status = _str(aif.get("Master feeder status", "") or
                         aif.get("Master-Feeder Status", "")).upper()
        masters_for_aif = [
            m for m in self.master_records
            if _str(m.get("Custom AIF Identification", "") or m.get("AIF ID", "")) == aif_id
        ]
        if masters_for_aif or mf_status == "FEEDER":
            _sub(aif_desc, "AIFMasterFeederStatus", "FEEDER")
            if masters_for_aif:
                master_ids = _sub(aif_desc, "MasterAIFsIdentification")
                for mr in masters_for_aif:
                    master_id_node = _sub(master_ids, "MasterAIFIdentification")
                    m_name = _str(mr.get("Master AIF Name", ""))
                    m_state = _str(mr.get("Master AIF national identifier - Reporting Member State", ""))
                    m_code = _str(mr.get("Master AIF national identifier - National code", ""))
                    if m_name:
                        _sub(master_id_node, "AIFName", m_name)
                    # XSD: AIFIdentifierNCA wraps ReportingMemberState + AIFNationalCode
                    if m_state or m_code:
                        nca_node = _sub(master_id_node, "AIFIdentifierNCA")
                        if m_state:
                            _sub(nca_node, "ReportingMemberState", m_state)
                        if m_code:
                            _sub(nca_node, "AIFNationalCode", m_code)
        elif mf_status == "MASTER":
            _sub(aif_desc, "AIFMasterFeederStatus", "MASTER")
        else:
            _sub(aif_desc, "AIFMasterFeederStatus", "NONE")

        # Currency & AUM
        base_ccy = _str(aif.get("Base currency of the AIF", "")) or "EUR"
        ccy_desc = _sub(aif_desc, "AIFBaseCurrencyDescription")
        _sub(ccy_desc, "BaseCurrency", base_ccy)

        if is_full:
            fx_rate = self._get_fx_rate(aif_id)
            aum_eur = _int_round(aum / fx_rate) if fx_rate and fx_rate != 1.0 else aum
            _sub(ccy_desc, "AUMAmountInBaseCurrency", str(aum))
            _sub(ccy_desc, "FXEURReferenceRateType", "ECB")
            _sub(ccy_desc, "FXEURRate", _rate_fmt(fx_rate, 4))
        else:
            _sub(ccy_desc, "AUMAmountInBaseCurrency", str(aum))

        _sub(aif_desc, "AIFNetAssetValue", str(nav))

        # Funding source countries (items 54-56)
        fsc1 = _str(aif.get("First funding source country",
                    aif.get("Funding Source Country 1", "")))
        fsc2 = _str(aif.get("Second funding source country",
                    aif.get("Funding Source Country 2", "")))
        fsc3 = _str(aif.get("Third funding source country",
                    aif.get("Funding Source Country 3", "")))
        if fsc1:
            _sub(aif_desc, "FirstFundingSourceCountry", fsc1)
        if fsc2:
            _sub(aif_desc, "SecondFundingSourceCountry", fsc2)
        if fsc3:
            _sub(aif_desc, "ThirdFundingSourceCountry", fsc3)

        # Strategy
        if is_full:
            strategies_for_aif = [
                s for s in self.strategies
                if _str(s.get("Custom AIF Identification", "") or s.get("AIF ID", "")) == aif_id
            ]
            # Determine predominant type from strategies
            if strategies_for_aif:
                # Use first strategy to determine predominant type, or find a primary
                first_code = _str(strategies_for_aif[0].get("Investment strategy code", ""))
                predominant = _predominant_type(first_code)
            else:
                predominant = _predominant_type(strategy_code)

            _sub(aif_desc, "PredominantAIFType", predominant)

            if predominant in STRATEGY_ELEMENT_MAP:
                container_tag, item_tag, type_tag = STRATEGY_ELEMENT_MAP[predominant]
                container = _sub(aif_desc, container_tag)

                if strategies_for_aif:
                    for strat in strategies_for_aif:
                        item = _sub(container, item_tag)
                        strat_code = _str(strat.get("Investment strategy code", ""))
                        _sub(item, type_tag, strat_code)
                        # Primary flag logic:
                        # 1. If explicit value provided → use it
                        # 2. If field exists in header but empty → false
                        # 3. If field not in header at all → true when 1 strategy
                        is_primary_raw = strat.get(
                            "Indicate whether the sub strategy best describes the AIF's strategy",
                            strat.get("Primary strategy flag"))
                        if is_primary_raw is not None:
                            is_primary = _bool_str(is_primary_raw)
                        elif ("Primary strategy flag" in strat or
                              "Indicate whether the sub strategy best describes the AIF's strategy" in strat):
                            # Field exists in template header but value is empty → false
                            is_primary = "false"
                        else:
                            # Field not in template → true when single strategy
                            is_primary = "true" if len(strategies_for_aif) == 1 else "false"
                        _sub(item, "PrimaryStrategyFlag", is_primary)
                        nav_rate = strat.get("Share in NAV (%)", strat.get("NAV Rate"))
                        if nav_rate is not None:
                            _sub(item, "StrategyNAVRate", _rate_fmt(float(nav_rate)))
                        # StrategyTypeOtherDescription — only for true "other" types
                        # (predominant OTHF, or strategy suffix _OTHF/_OTHR)
                        if predominant == "OTHF" or strat_code.endswith(("_OTHF", "_OTHR")):
                            other_desc = _str(strat.get("Description for strategy type Other", "") or
                                              strat.get("Strategy type other description", ""))
                            if other_desc:
                                _sub(item, "StrategyTypeOtherDescription", other_desc)
                else:
                    # No STRATEGY records — single strategy from AIF record → primary
                    item = _sub(container, item_tag)
                    _sub(item, type_tag, strategy_code)
                    _sub(item, "PrimaryStrategyFlag", "true")
                    _sub(item, "StrategyNAVRate", "100.00")

                # Add the predominant/primary strategy entry if we had sub-strategies
                if len(strategies_for_aif) > 1:
                    # MULT_ prefix only valid for HFND/REST/PEQF;
                    # FOFS and OTHR use their "other" variant instead
                    _MULTI_STRATEGY_CODES = {
                        "HFND": "MULT_HFND",
                        "REST": "MULT_REST",
                        "PEQF": "MULT_PEQF",
                        "FOFS": "OTHR_FOFS",
                        "OTHR": "OTHR_OTHF",
                    }
                    mult_code = _MULTI_STRATEGY_CODES.get(
                        predominant, f"MULT_{predominant}")
                    item = _sub(container, item_tag)
                    _sub(item, type_tag, mult_code)
                    _sub(item, "PrimaryStrategyFlag", "true")
        else:
            predominant = _predominant_type(strategy_code)
            _sub(aif_desc, "PredominantAIFType", predominant)

            if predominant in STRATEGY_ELEMENT_MAP:
                container_tag, item_tag, type_tag = STRATEGY_ELEMENT_MAP[predominant]
                container = _sub(aif_desc, container_tag)
                item = _sub(container, item_tag)
                _sub(item, type_tag, strategy_code)
                _sub(item, "PrimaryStrategyFlag", "true")
                _sub(item, "StrategyNAVRate", "100.00")

        # HFT fields — optional per ESMA; always emit when data is present
        rms = reporting_member_state
        hft_num = aif.get("HFT Transaction number") or aif.get("HFT transaction number") or 0
        hft_val = aif.get("HFT Buy/Sell market value") or aif.get("HFT buy/sell market value") or 0
        nca_de = (rms == "DE")  # DE/BaFin explicitly omits HFT
        if not nca_de:
            _sub(aif_desc, "HFTTransactionNumber", str(_int_round(hft_num)))
            _sub(aif_desc, "HFTBuySellMarketValue", str(_int_round(hft_val)))

        # Main Instruments Traded
        top = self._long_positions_sorted(positions)[:5]
        traded = _sub(info, "MainInstrumentsTraded")
        for rank in range(1, 6):
            inst = _sub(traded, "MainInstrumentTraded")
            _sub(inst, "Ranking", str(rank))
            if rank <= len(top):
                p = top[rank - 1]
                mit_sat = _str(
                    p.get("Sub-Asset Type of Position", "") or p.get("Sub-Asset Type", ""))
                # FCA: convert ESMA sovereign bond codes (currency-aware)
                if rms == "GB" and mit_sat.startswith("SEC_SBD_EU"):
                    mit_ccy = _str(p.get("Currency of the exposure", "") or
                                   p.get("Instrument Currency", ""))
                    mit_sat = _fca_sovereign_sub_asset(mit_sat, mit_ccy)
                _sub(inst, "SubAssetType", mit_sat)
                _sub(inst, "InstrumentCodeType", "NONE")
                _sub(inst, "InstrumentName", _str(p.get("Instrument Name", "")))
                _sub(inst, "PositionValue", str(_int_round(self._pos_val(p))))
                _sub(inst, "PositionType", _str(p.get("Long / Short", "L")))
                # ShortPositionHedgingRate (item 77) — for short positions
                ls = _str(p.get("Long / Short", "L"))
                if ls == "S":
                    hedge_rate = _float_val(p.get("Hedging % for short position",
                                  p.get("Short position hedging percentage",
                                  p.get("ShortPositionHedgingRate", 0)))) or 0
                    _sub(inst, "ShortPositionHedgingRate", _rate_fmt(hedge_rate, 4))
            else:
                _sub(inst, "SubAssetType", "NTA_NTA_NOTA")

        # Geographical focus
        nca_gb = (reporting_member_state == "GB")
        geo_aum = self._geo_focus(positions, aum)
        geo_nav_raw = getattr(self, "_last_geo_nav", {})
        nav_geo = _sub(info, "NAVGeographicalFocus")
        aum_geo = _sub(info, "AUMGeographicalFocus")

        if nca_gb:
            # FCA regions: UK + EuropeNonUK instead of Europe + EEA
            aum_raw = getattr(self, "_last_geo_aum_raw", {})
            uk_nav_raw = getattr(self, "_last_uk_nav", 0.0)
            uk_aum_raw = getattr(self, "_last_uk_aum", 0.0)
            # EuropeNonUK = Europe (non-EEA minus GB) + EEA
            europe_nonuk_nav = (geo_nav_raw.get("Europe", 0.0) - uk_nav_raw +
                                geo_nav_raw.get("EEA", 0.0))
            europe_nonuk_aum = (aum_raw.get("Europe", 0.0) - uk_aum_raw +
                                aum_raw.get("EEA", 0.0))
            fca_nav = {
                "Africa": geo_nav_raw.get("Africa", 0.0),
                "AsiaPacific": geo_nav_raw.get("AsiaPacific", 0.0),
                "UK": uk_nav_raw,
                "EuropeNonUK": europe_nonuk_nav,
                "MiddleEast": geo_nav_raw.get("MiddleEast", 0.0),
                "NorthAmerica": geo_nav_raw.get("NorthAmerica", 0.0),
                "SouthAmerica": geo_nav_raw.get("SouthAmerica", 0.0),
                "SupraNational": geo_nav_raw.get("SupraNational", 0.0),
            }
            fca_aum = {
                "Africa": aum_raw.get("Africa", 0.0),
                "AsiaPacific": aum_raw.get("AsiaPacific", 0.0),
                "UK": uk_aum_raw,
                "EuropeNonUK": europe_nonuk_aum,
                "MiddleEast": aum_raw.get("MiddleEast", 0.0),
                "NorthAmerica": aum_raw.get("NorthAmerica", 0.0),
                "SouthAmerica": aum_raw.get("SouthAmerica", 0.0),
                "SupraNational": aum_raw.get("SupraNational", 0.0),
            }
            for label in FCA_REGION_MAP.values():
                if nav and geo_nav_raw:
                    nav_rate = round(fca_nav.get(label, 0.0) / nav * 100, 2)
                else:
                    nav_rate = round(fca_aum.get(label, 0.0) / aum * 100, 2) if aum else 0.0
                aum_rate = round(fca_aum.get(label, 0.0) / aum * 100, 2) if aum else 0.0
                _sub(nav_geo, f"{label}NAVRate", _rate_fmt(nav_rate))
                _sub(aum_geo, f"{label}AUMRate", _rate_fmt(aum_rate))
        else:
            # ESMA regions: Europe + EEA
            for region_key, label in REGION_MAP.items():
                if nav and geo_nav_raw:
                    nav_rate = round(geo_nav_raw.get(label, 0.0) / nav * 100, 2)
                else:
                    nav_rate = geo_aum.get(label, 0.0)
                _sub(nav_geo, f"{label}NAVRate", _rate_fmt(nav_rate))
                _sub(aum_geo, f"{label}AUMRate", _rate_fmt(geo_aum.get(label, 0.0)))

        # Principal Exposures
        # FCA RegData: omit entries < 0.5% of AUM to avoid rounding-error rejection
        is_fca_aif = (reporting_member_state == "GB")
        exposures_container = _sub(info, "PrincipalExposures")
        agg_sub = self._aggregate_by_sub_asset(positions,
                                              reporting_member_state=reporting_member_state)
        if is_fca_aif and aum > 0:
            agg_sub = [a for a in agg_sub
                       if (a["amount"] / aum * 100) >= FCA_AGG_VALUE_MIN_PCT]
        for rank in range(1, 11):
            exp = _sub(exposures_container, "PrincipalExposure")
            _sub(exp, "Ranking", str(rank))
            if rank <= len(agg_sub):
                a = agg_sub[rank - 1]
                _sub(exp, "AssetMacroType", a["macro"])
                _sub(exp, "SubAssetType", a["sub_asset"])
                _sub(exp, "PositionType", a["direction"])
                _sub(exp, "AggregatedValueAmount", str(_int_round(a["amount"])))
                _sub(exp, "AggregatedValueRate",
                     _rate_fmt(a["amount"] / aum * 100 if aum > 0 else 0))
            else:
                _sub(exp, "AssetMacroType", "NTA")

        # Most Important Concentration
        conc = _sub(info, "MostImportantConcentration")

        # Portfolio Concentrations
        # FCA RegData: same 0.5% threshold applies
        pc_container = _sub(conc, "PortfolioConcentrations")
        agg_at = self._aggregate_by_asset_type(positions,
                                             reporting_member_state=reporting_member_state)
        if is_fca_aif and aum > 0:
            agg_at = [a for a in agg_at
                      if (a["amount"] / aum * 100) >= FCA_AGG_VALUE_MIN_PCT]
        for rank in range(1, 6):
            pc = _sub(pc_container, "PortfolioConcentration")
            _sub(pc, "Ranking", str(rank))
            if rank <= len(agg_at):
                a = agg_at[rank - 1]
                _sub(pc, "AssetType", a["asset_type"])
                _sub(pc, "PositionType", a["direction"])
                mid = _sub(pc, "MarketIdentification")
                _sub(mid, "MarketCodeType", "XXX")
                _sub(pc, "AggregatedValueAmount", str(_int_round(a["amount"])))
                _sub(pc, "AggregatedValueRate",
                     _rate_fmt(a["amount"] / aum * 100 if aum > 0 else 0))
            else:
                _sub(pc, "AssetType", "NTA_NTA")

        # AIF Principal Markets
        markets = _sub(conc, "AIFPrincipalMarkets")
        for rank in range(1, 4):
            mkt = _sub(markets, "AIFPrincipalMarket")
            _sub(mkt, "Ranking", str(rank))
            mid = _sub(mkt, "MarketIdentification")
            if rank == 1:
                _sub(mid, "MarketCodeType", "XXX")
                _sub(mkt, "AggregatedValueAmount", str(aum))
            else:
                _sub(mid, "MarketCodeType", "NOT")

        # Investor Concentration
        inv = _sub(conc, "InvestorConcentration")
        beneficial_pct = _float_val(aif.get(
            "Beneficially owned percentage by top 5 beneficial owners") or 0)
        retail_pct = aif.get("Investor Concentration percentage by retail investors")
        if retail_pct is None:
            retail_pct = aif.get("Investor Concentration percentage by retail investors ")
        retail_pct = float(retail_pct or 0)
        professional_pct = round(100 - retail_pct, 2)
        _sub(inv, "MainBeneficialOwnersRate", _rate_fmt(beneficial_pct))
        _sub(inv, "ProfessionalInvestorConcentrationRate", _rate_fmt(professional_pct))
        _sub(inv, "RetailInvestorConcentrationRate", _rate_fmt(retail_pct))

        # Content-type-driven sections (per ESMA CAF-002):
        #   CT 2   → AIFIndividualInfo + AIFLeverageArticle24-2
        #   CT 4   → AIFIndividualInfo + AIFLeverageArticle24-2 + AIFLeverageArticle24-4
        #   CT 5   → AIFLeverageArticle24-4
        #   CT 1,3 → neither
        if self._aif_needs_individual_info(aif):
            self._build_aif_individual_info(desc, aif_id, positions, aum,
                                            reporting_member_state=reporting_member_state)
        if self._aif_needs_individual_info(aif) or self._aif_needs_leverage_24_4(aif):
            self._build_aif_leverage_info(desc, aif_id, aif,
                                          positions=positions, aum=aum, nav=nav)

    def _build_aif_individual_info(self, desc: Element, aif_id: str,
                                    positions: list, aum: int,
                                    reporting_member_state: str = ""):
        """Build AIFIndividualInfo section (full template only).

        This is a very long method (400+ lines); it's included here
        for completeness but continues below...
        """
        rms = reporting_member_state
        nca_be = (rms == "BE")
        nca_de = (rms == "DE")
        nca_lu = (rms == "LU")
        info = _sub(desc, "AIFIndividualInfo")

        # Individual Exposure
        exp = _sub(info, "IndividualExposure")

        # Asset Type Exposures
        is_fca_indiv = (rms == "GB")
        agg = {}
        for p in positions:
            val = self._pos_val(p)
            sat = _str(p.get("Sub-Asset Type of Position", "") or p.get("Sub-Asset Type", ""))
            # FCA: convert ESMA sovereign bond codes to FCA equivalents (currency-aware)
            if is_fca_indiv and sat.startswith("SEC_SBD_EU"):
                ccy = _str(p.get("Currency of the exposure", "") or
                           p.get("Instrument Currency", ""))
                sat = _fca_sovereign_sub_asset(sat, ccy)
            direction = _str(p.get("Long / Short", "L"))
            if val > 0 and sat:
                if sat not in agg:
                    agg[sat] = {"long": 0.0, "short": 0.0}
                if direction.upper() == "L" or direction.upper() == "LONG":
                    agg[sat]["long"] += val
                else:
                    agg[sat]["short"] += val

        # Use template/insertion order (M adapter convention), not value-sorted
        ate = _sub(exp, "AssetTypeExposures")
        if not agg:
            # XSD requires ≥1 AssetTypeExposure child — fallback to NTA_NTA_NOTA
            ate_item = _sub(ate, "AssetTypeExposure")
            _sub(ate_item, "SubAssetType", "NTA_NTA_NOTA")
            _sub(ate_item, "GrossValue", "0")
        for sat, vals in agg.items():
            ate_item = _sub(ate, "AssetTypeExposure")
            _sub(ate_item, "SubAssetType", sat)
            if vals["long"] > 0:
                _sub(ate_item, "LongValue", str(_int_round(vals["long"])))
            # ShortValue: BE/FSMA requires it always; DE/BaFin omits when zero
            if vals["short"] > 0:
                _sub(ate_item, "ShortValue", str(_int_round(vals["short"])))
            elif nca_be:
                _sub(ate_item, "ShortValue", "0")

        # Asset Type Turnovers
        att = _sub(exp, "AssetTypeTurnovers")
        turnover_count = 0
        for turnover in self.turnovers:
            if _str(turnover.get("Custom AIF Identification", "") or turnover.get("AIF ID", "")) == aif_id:
                tur = _sub(att, "AssetTypeTurnover")
                raw_turnover_code = _str(turnover.get("Sub-Asset Type of Turnover", "") or
                                        turnover.get("Turnover Sub-Asset Type", ""))
                turnover_code = _turnover_sub_asset_type(raw_turnover_code)
                # FCA: convert ESMA sovereign bond turnover codes to FCA equivalents
                if is_fca_indiv:
                    turnover_code = FCA_SOVEREIGN_TURNOVER_MAP.get(turnover_code, turnover_code)
                _sub(tur, "TurnoverSubAssetType", turnover_code)
                _sub(tur, "MarketValue",
                     str(_int_round(turnover.get("Market Value of Turnover", 0) or
                                    turnover.get("Turnover market value", 0))))
                turnover_count += 1
        # Fallback: OTH_OTH_OTH with value 0 when no turnover records exist
        if turnover_count == 0:
            tur = _sub(att, "AssetTypeTurnover")
            _sub(tur, "TurnoverSubAssetType", "OTH_OTH_OTH")
            _sub(tur, "MarketValue", "0")

        # Currency Exposures
        ccy_exp = {}
        for p in positions:
            val = self._pos_val(p)
            ccy = _str(p.get("Currency of the exposure", "") or
                       p.get("Instrument Currency", "") or "USD")
            direction = _str(p.get("Long / Short", "L"))
            if val > 0 and ccy:
                if ccy not in ccy_exp:
                    ccy_exp[ccy] = {"long": 0.0, "short": 0.0}
                if direction.upper() == "L" or direction.upper() == "LONG":
                    ccy_exp[ccy]["long"] += val
                else:
                    ccy_exp[ccy]["short"] += val

        # Only create CurrencyExposures if there are actual exposures
        # (XSD requires ≥1 child CurrencyExposure)
        if ccy_exp:
            ce = _sub(exp, "CurrencyExposures")
        for ccy, vals in sorted(ccy_exp.items()):
            ce_item = _sub(ce, "CurrencyExposure")
            _sub(ce_item, "ExposureCurrency", ccy)
            _sub(ce_item, "LongPositionValue", str(_int_round(vals["long"])))
            _sub(ce_item, "ShortPositionValue", str(_int_round(vals["short"])))

        # Companies Dominant Influence (AIF Questions 131-136)
        # Required for PEQF funds; FCA RegData rejects PEQF without at least one record
        is_fca_indiv = (rms == "GB")
        dom_infl_for_aif = [
            d for d in self.dominant_influences
            if _str(d.get("Custom AIF Identification", "") or
                    d.get("AIF ID", "")) == aif_id
        ]
        # Determine predominant AIF type for this fund
        strats_for_aif = [
            s for s in self.strategies
            if _str(s.get("Custom AIF Identification", "") or
                    s.get("AIF ID", "")) == aif_id
        ]
        predominant = ""
        if strats_for_aif:
            predominant = _predominant_type(
                _str(strats_for_aif[0].get("Investment strategy code", "")))

        if dom_infl_for_aif:
            cdi = _sub(exp, "CompaniesDominantInfluence")
            for d in dom_infl_for_aif:
                di = _sub(cdi, "CompanyDominantInfluence")
                ci = _sub(di, "CompanyIdentification")
                _sub(ci, "EntityName",
                     _str(d.get("Dominant influence company name", "")))
                bic = _str(d.get("Dominant influence company BIC code", ""))
                if bic:
                    _sub(ci, "EntityIdentificationBIC", bic)
                lei = _str(d.get("Dominant influence company LEI code", ""))
                if lei:
                    _sub(ci, "EntityIdentificationLEI", lei)
                tx_type = _str(d.get("Transaction Type", "OTHR"))
                _sub(di, "TransactionType", tx_type)
                if tx_type == "OTHR":
                    _sub(di, "OtherTransactionTypeDescription",
                         _str(d.get("Description of other transaction type", "Other")))
                vr = _float_val(d.get("% Voting Rights",
                               d.get("Voting Rights Percentage", 0)))
                _sub(di, "VotingRightsRate", _rate_fmt(vr))
        elif is_fca_indiv and predominant == "PEQF":
            # FCA RegData: PEQF funds must have ≥1 dominant influence record
            # Auto-insert dummy "Not Applicable" per M adapter FAQ
            cdi = _sub(exp, "CompaniesDominantInfluence")
            di = _sub(cdi, "CompanyDominantInfluence")
            ci = _sub(di, "CompanyIdentification")
            _sub(ci, "EntityName", "Not Applicable")
            _sub(di, "TransactionType", "OTHR")
            _sub(di, "OtherTransactionTypeDescription", "Not Applicable")
            _sub(di, "VotingRightsRate", "0.00")

        # Risk Profile
        rp = _sub(info, "RiskProfile")

        # Market Risk Profile
        mrp = _sub(rp, "MarketRiskProfile")
        _sub(mrp, "AnnualInvestmentReturnRate", "NA")

        # Market Risk Measures
        mrs = _sub(mrp, "MarketRiskMeasures")

        # Get risk records for this AIF
        risk_recs = [r for r in self.risks
                    if _str(r.get("Custom AIF Identification", "") or r.get("AIF ID", "")) == aif_id]

        # NET_EQTY_DELTA
        net_eqty = next((r for r in risk_recs
                        if _str(r.get("Risk Measure Type", "")) == "NET_EQTY_DELTA"), None)
        mrm = _sub(mrs, "MarketRiskMeasure")
        _sub(mrm, "RiskMeasureType", "NET_EQTY_DELTA")
        if net_eqty:
            _sub(mrm, "RiskMeasureValue",
                 _rate_fmt(_float_val(net_eqty.get("Risk Measure Value"))))
            desc = _str(net_eqty.get("Risk Measure Description", "")) or ""
            if desc:
                _sub(mrm, "RiskMeasureDescription", desc)
        else:
            # No RISK record for NET_EQTY_DELTA: auto-calc from equity positions
            # Formula: -0.01 × total equity exposure (SEC_LEQ_* + SEC_UEQ_*)
            eq_total = 0.0
            for p in positions:
                sat = _str(p.get("Sub-Asset Type of Position", "") or
                           p.get("Sub-Asset Type", "") or p.get("SubAssetType", ""))
                if sat.startswith("SEC_LEQ_") or sat.startswith("SEC_UEQ_"):
                    eq_total += abs(float(self._pos_val(p) or 0))
            if eq_total > 0:
                net_eqty_val = round(-0.01 * eq_total, 2)
                _sub(mrm, "RiskMeasureValue", _rate_fmt(net_eqty_val))
            else:
                _sub(mrm, "RiskMeasureValue", "0.00")
                _sub(mrm, "RiskMeasureDescription",
                     "Not applicable given AIF's predominant type.")

        # NET_FX_DELTA — BE/FSMA and LU/CSSF
        if nca_be or nca_lu:
            net_fx = next((r for r in risk_recs
                          if _str(r.get("Risk Measure Type", "")) == "NET_FX_DELTA"), None)
            mrm = _sub(mrs, "MarketRiskMeasure")
            _sub(mrm, "RiskMeasureType", "NET_FX_DELTA")
            if net_fx:
                _sub(mrm, "RiskMeasureValue",
                     _rate_fmt(_float_val(net_fx.get("Risk Measure Value"))))
                desc = _str(net_fx.get("Risk Measure Description", "")) or ""
                if desc:
                    _sub(mrm, "RiskMeasureDescription", desc)
            else:
                # No RISK record for NET_FX_DELTA: auto-calc from FX exposure.
                # Per M adapter FAQ: applicable when any position has a currency
                # of exposure different from the AIF base currency, AND no FX
                # derivatives (DER_FEX_*) are present.  In that case, the FX
                # delta equals -0.01 × total value of foreign-currency positions.
                base_ccy = _str(self._get_base_currency(aif_id) or "").upper()
                has_fx_der = False
                fx_exposure = 0.0
                for p in positions:
                    sat = _str(p.get("Sub-Asset Type of Position", "") or
                               p.get("Sub-Asset Type", "") or
                               p.get("SubAssetType", ""))
                    if sat.startswith("DER_FEX_"):
                        has_fx_der = True
                        break
                if not has_fx_der and base_ccy:
                    for p in positions:
                        ccy = _str(p.get("Currency of the exposure", "") or
                                   p.get("Instrument Currency", "")).upper()
                        if ccy and ccy != base_ccy:
                            fx_exposure += abs(float(self._pos_val(p) or 0))
                if has_fx_der:
                    # FX derivatives present — cannot auto-calc; user must supply
                    _sub(mrm, "RiskMeasureValue", "0.00")
                    _sub(mrm, "RiskMeasureDescription",
                         "Not applicable given AIF's positions.")
                elif fx_exposure > 0:
                    net_fx_val = round(-0.01 * fx_exposure, 2)
                    _sub(mrm, "RiskMeasureValue", _rate_fmt(net_fx_val))
                else:
                    _sub(mrm, "RiskMeasureValue", "0.00")
                    _sub(mrm, "RiskMeasureDescription",
                         "Not applicable given AIF's positions.")

        # NET_CTY_DELTA — BE/FSMA and LU/CSSF
        if nca_be or nca_lu:
            net_cty = next((r for r in risk_recs
                           if _str(r.get("Risk Measure Type", "")) == "NET_CTY_DELTA"), None)
            mrm = _sub(mrs, "MarketRiskMeasure")
            _sub(mrm, "RiskMeasureType", "NET_CTY_DELTA")
            if net_cty:
                _sub(mrm, "RiskMeasureValue",
                     _rate_fmt(_float_val(net_cty.get("Risk Measure Value"))))
            else:
                _sub(mrm, "RiskMeasureValue", "0.00")
            _sub(mrm, "RiskMeasureDescription",
                 _str(net_cty.get("Risk Measure Description", "")) if net_cty
                 else "Not applicable given AIF's predominant type.")

        # NET_DV01
        net_dv01 = next((r for r in risk_recs
                        if _str(r.get("Risk Measure Type", "")) == "NET_DV01"), None)
        mrm = _sub(mrs, "MarketRiskMeasure")
        _sub(mrm, "RiskMeasureType", "NET_DV01")
        brm = _sub(mrm, "BucketRiskMeasureValues")
        if net_dv01:
            _sub(brm, "LessFiveYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_dv01.get("Less than 5 years"))))
            _sub(brm, "FifthteenYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_dv01.get("5 to 15 years"))))
            _sub(brm, "MoreFifthteenYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_dv01.get("More than 15 years"))))
        else:
            _sub(brm, "LessFiveYearsRiskMeasureValue", "0.00")
            _sub(brm, "FifthteenYearsRiskMeasureValue", "0.00")
            _sub(brm, "MoreFifthteenYearsRiskMeasureValue", "0.00")
        _sub(mrm, "RiskMeasureDescription",
             "Not applicable given AIF's predominant type.")

        # NET_CS01
        net_cs01 = next((r for r in risk_recs
                        if _str(r.get("Risk Measure Type", "")) == "NET_CS01"), None)
        mrm = _sub(mrs, "MarketRiskMeasure")
        _sub(mrm, "RiskMeasureType", "NET_CS01")
        brm = _sub(mrm, "BucketRiskMeasureValues")
        if net_cs01:
            _sub(brm, "LessFiveYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_cs01.get("Less than 5 years"))))
            _sub(brm, "FifthteenYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_cs01.get("5 to 15 years"))))
            _sub(brm, "MoreFifthteenYearsRiskMeasureValue",
                 _rate_fmt(_float_val(net_cs01.get("More than 15 years"))))
        else:
            _sub(brm, "LessFiveYearsRiskMeasureValue", "0.00")
            _sub(brm, "FifthteenYearsRiskMeasureValue", "0.00")
            _sub(brm, "MoreFifthteenYearsRiskMeasureValue", "0.00")
        _sub(mrm, "RiskMeasureDescription",
             "Not applicable given AIF's predominant type.")

        # VEGA_EXPO — BE/FSMA only
        if nca_be:
            vega_rec = next((r for r in risk_recs
                            if _str(r.get("Risk Measure Type", "")) == "VEGA_EXPO"), None)
            mrm = _sub(mrs, "MarketRiskMeasure")
            _sub(mrm, "RiskMeasureType", "VEGA_EXPO")
            vrm_vega = _sub(mrm, "VegaRiskMeasureValues")
            if vega_rec:
                _sub(vrm_vega, "CurrentMarketRiskMeasureValue",
                     _rate_fmt(_float_val(vega_rec.get("Current Market Risk Measure Value"))))
                _sub(vrm_vega, "LowerMarketRiskMeasureValue",
                     _rate_fmt(_float_val(vega_rec.get("Lower Market Risk Measure Value"))))
                _sub(vrm_vega, "HigherMarketRiskMeasureValue",
                     _rate_fmt(_float_val(vega_rec.get("Higher Market Risk Measure Value"))))
            else:
                _sub(vrm_vega, "CurrentMarketRiskMeasureValue", "0.00")
                _sub(vrm_vega, "LowerMarketRiskMeasureValue", "0.00")
                _sub(vrm_vega, "HigherMarketRiskMeasureValue", "0.00")
            _sub(mrm, "RiskMeasureDescription",
                 _str(vega_rec.get("Risk Measure Description", "")) if vega_rec
                 else "Not applicable given AIF's predominant type.")

        # VAR
        var_rec = next((r for r in risk_recs
                       if _str(r.get("Risk Measure Type", "")) == "VAR"), None)
        mrm = _sub(mrs, "MarketRiskMeasure")
        _sub(mrm, "RiskMeasureType", "VAR")
        vrm = _sub(mrm, "VARRiskMeasureValues")
        if var_rec:
            _sub(vrm, "VARValue",
                 _rate_fmt(_float_val(var_rec.get("VAR Value"))))
        else:
            _sub(vrm, "VARValue", "0.00")
        _sub(vrm, "VARCalculationMethodCodeType", "HISTO")
        _sub(mrm, "RiskMeasureDescription",
             "Not applicable given AIF's predominant type.")

        # Counterparty Risk Profile
        crp = _sub(rp, "CounterpartyRiskProfile")

        # Trading and Clearing Mechanisms (items 148-156)
        crp_rec = next((c for c in getattr(self, "counterparty_risks", [])
                       if _str(c.get("Custom AIF Identification", "")) == aif_id
                       or _str(c.get("AIF ID", "")) == aif_id), None)
        if crp_rec:
            tcm = _sub(crp, "TradingClearingMechanism")
            # TradedSecurities (items 148-149)
            ts = _sub(tcm, "TradedSecurities")
            sec_reg = _float_val(crp_rec.get(
                "Percentage of market value for securities traded on regulated exchanges (non-OTC)",
                crp_rec.get("Regulated market rate for securities", 0))) or 0
            _sub(ts, "RegulatedMarketRate", _rate_fmt(sec_reg, 2))
            _sub(ts, "OTCRate", _rate_fmt(100.0 - sec_reg, 2))
            # TradedDerivatives (items 150-151)
            td = _sub(tcm, "TradedDerivatives")
            der_reg = _float_val(crp_rec.get(
                "Percentage of trade volumes for derivatives traded on regulated exchanges (non-OTC)",
                crp_rec.get("Regulated market rate for derivatives", 0))) or 0
            _sub(td, "RegulatedMarketRate", _rate_fmt(der_reg, 2))
            _sub(td, "OTCRate", _rate_fmt(100.0 - der_reg, 2))
            # ClearedDerivativesRate (items 152-153)
            cdr = _sub(tcm, "ClearedDerivativesRate")
            der_ccp = _float_val(crp_rec.get(
                "Percentage of trade volumes for derivatives cleared by a CCP",
                crp_rec.get("CCP rate for derivatives", 0))) or 0
            _sub(cdr, "CCPRate", _rate_fmt(der_ccp, 2))
            _sub(cdr, "BilateralClearingRate", _rate_fmt(100.0 - der_ccp, 2))
            # ClearedReposRate (items 154-156)
            crr = _sub(tcm, "ClearedReposRate")
            repo_ccp = _float_val(crp_rec.get(
                "Percentage of market value for repos trades cleared by a CCP",
                crp_rec.get("CCP rate for repos", 0))) or 0
            repo_bi = _float_val(crp_rec.get(
                "Percentage of market value for repos trades cleared bilaterally",
                crp_rec.get("Bilateral clearing rate for repos", 0))) or 0
            repo_tri = _float_val(crp_rec.get(
                "Percentage of market value for repos trades cleared with triparty repos",
                crp_rec.get("Tri-party repo clearing rate", 0))) or 0
            _sub(crr, "CCPRate", _rate_fmt(repo_ccp, 2))
            _sub(crr, "BilateralClearingRate", _rate_fmt(repo_bi, 2))
            _sub(crr, "TriPartyRepoClearingRate", _rate_fmt(repo_tri, 2))

        # All Counterparty Collateral (items 157-159)
        if crp_rec:
            acc = _sub(crp, "AllCounterpartyCollateral")
            _sub(acc, "AllCounterpartyCollateralCash",
                 str(_int_round(crp_rec.get("Collateral Cash amount posted to all counterparties", 0) or 0)))
            _sub(acc, "AllCounterpartyCollateralSecurities",
                 str(_int_round(crp_rec.get("Collateral Securities amount posted to all counterparties", 0) or 0)))
            _sub(acc, "AllCounterpartyOtherCollateralPosted",
                 str(_int_round(crp_rec.get("Other Collateral amount posted to all counterparties", 0) or 0)))

        # Fund to Counterparty Exposures
        ftc = _sub(crp, "FundToCounterpartyExposures")
        for rank in range(1, 6):
            ftc_item = _sub(ftc, "FundToCounterpartyExposure")
            _sub(ftc_item, "Ranking", str(rank))
            _sub(ftc_item, "CounterpartyExposureFlag", "false")

        # Counterparty to Fund Exposures
        ctf = _sub(crp, "CounterpartyToFundExposures")
        for rank in range(1, 6):
            ctf_item = _sub(ctf, "CounterpartyToFundExposure")
            _sub(ctf_item, "Ranking", str(rank))
            _sub(ctf_item, "CounterpartyExposureFlag", "false")

        _sub(crp, "ClearTransactionsThroughCCPFlag", "false")

        # Liquidity Risk Profile
        lrp = _sub(rp, "LiquidityRiskProfile")

        # Portfolio Liquidity Profile
        plp_rec = next((p for p in self.portfolio_liquidity_profiles
                       if _str(p.get("Custom AIF Identification", "")) == aif_id
                       or _str(p.get("AIF ID", "")) == aif_id), None)

        plp = _sub(lrp, "PortfolioLiquidityProfile")
        if plp_rec:
            _sub(plp, "PortfolioLiquidityInDays0to1Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 0 to 1 day")), 4))
            _sub(plp, "PortfolioLiquidityInDays2to7Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 2 to 7 days")), 4))
            _sub(plp, "PortfolioLiquidityInDays8to30Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 8 to 30 days")), 4))
            _sub(plp, "PortfolioLiquidityInDays31to90Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 31 to 90 days")), 4))
            _sub(plp, "PortfolioLiquidityInDays91to180Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 91 to 180 days")), 4))
            _sub(plp, "PortfolioLiquidityInDays181to365Rate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in 181 to 365 days")), 4))
            _sub(plp, "PortfolioLiquidityInDays365MoreRate",
                 _rate_fmt(_float_val(plp_rec.get("Percentage of portfolio liquidity in more than 365 days")), 4))
            _sub(plp, "UnencumberedCash",
                 str(_int_round(plp_rec.get("Unencumbered cash amount", 0))))
        else:
            # No PORTFOLIO_LIQUIDITY_PROFILE record: auto-calc per M adapter FAQ
            ue_cash = self._calc_unencumbered_cash(aif_id, positions)
            liq = self._calc_portfolio_liquidity(aif_id, positions, ue_cash)
            _sub(plp, "PortfolioLiquidityInDays0to1Rate", _rate_fmt(liq.get("0to1", 0.0), 4))
            _sub(plp, "PortfolioLiquidityInDays2to7Rate", "0.0000")
            _sub(plp, "PortfolioLiquidityInDays8to30Rate", "0.0000")
            _sub(plp, "PortfolioLiquidityInDays31to90Rate", "0.0000")
            _sub(plp, "PortfolioLiquidityInDays91to180Rate", "0.0000")
            _sub(plp, "PortfolioLiquidityInDays181to365Rate", "0.0000")
            _sub(plp, "PortfolioLiquidityInDays365MoreRate", _rate_fmt(liq.get("365more", 0.0), 4))
            _sub(plp, "UnencumberedCash", str(liq.get("cash", 0)))

        # Investor Liquidity Profile
        ilp_rec = next((i for i in self.investor_liquidity_profiles
                       if _str(i.get("Custom AIF Identification", "")) == aif_id
                       or _str(i.get("AIF ID", "")) == aif_id), None)

        ilp = _sub(lrp, "InvestorLiquidityProfile")
        if ilp_rec:
            _sub(ilp, "InvestorLiquidityInDays0to1Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 0 to 1 day",
                                ilp_rec.get("Investor liquidity in 0 to 1 day"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays2to7Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 2 to 7 days",
                                ilp_rec.get("Investor liquidity in 2 to 7 days"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays8to30Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 8 to 30 days",
                                ilp_rec.get("Investor liquidity in 8 to 30 days"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays31to90Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 31 to 90 days",
                                ilp_rec.get("Investor liquidity in 31 to 90 days"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays91to180Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 91 to 180 days",
                                ilp_rec.get("Investor liquidity in 91 to 180 days"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays181to365Rate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in 181 to 365 days",
                                ilp_rec.get("Investor liquidity in 181 to 365 days"))) or 0, 4))
            _sub(ilp, "InvestorLiquidityInDays365MoreRate",
                 _rate_fmt(_float_val(ilp_rec.get("Percentage of investor liquidity in more than 365 days",
                                ilp_rec.get("Investor liquidity in more than 365 days"))) or 0, 4))
        else:
            # No ILP record: default to 100% in 365More bucket
            _sub(ilp, "InvestorLiquidityInDays0to1Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays2to7Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays8to30Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays31to90Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays91to180Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays181to365Rate", "0.0000")
            _sub(ilp, "InvestorLiquidityInDays365MoreRate", "100.0000")

        # Investor Redemption
        ired = next((i for i in self.investor_redemptions
                    if _str(i.get("Custom AIF Identification", "")) == aif_id
                    or _str(i.get("AIF ID", "")) == aif_id), None)

        irec = _sub(lrp, "InvestorRedemption")
        if ired:
            withdraw_raw = (ired.get("(Legacy) Withdrawal redemption rights flag", "") or
                           ired.get("Provide withdrawal rights flag", ""))
            withdraw_flag = _bool_str(withdraw_raw) if withdraw_raw else "false"
            _sub(irec, "ProvideWithdrawalRightsFlag", withdraw_flag)
            # Only include frequency/period when withdrawal rights are provided
            if withdraw_flag == "true":
                freq = _str(ired.get("Investor Redemption Frequency", "") or
                            ired.get("Investor redemption frequency code", ""))
                if freq:
                    _sub(irec, "InvestorRedemptionFrequency", freq)
                period = ired.get("Investor Redemption Notice Period in days",
                         ired.get("Investor redemption notice period"))
                if period is not None:
                    _sub(irec, "InvestorRedemptionNoticePeriod", str(_int_round(period)))
        else:
            # No INVESTOR_REDEMPTION record: only output withdrawal flag
            _sub(irec, "ProvideWithdrawalRightsFlag", "false")

        # Investor Arrangement (from SPECIAL_ARRANGEMENT records)
        sa_rec = next((s for s in self.special_arrangements
                      if _str(s.get("Custom AIF Identification", "") or
                              s.get("AIF ID", "")) == aif_id), None)
        if sa_rec:
            ia = _sub(lrp, "InvestorArrangement")
            # InvestorIlliquidAssetArrangement (items 197-202) — must come before InvestorPreferentialTreatment per XSD
            iiaa = _sub(ia, "InvestorIlliquidAssetArrangement")
            _sub(iiaa, "SidePocketRate",
                 _rate_fmt(_float_val(sa_rec.get("Side pocket percentage",
                          sa_rec.get("Side pocket rate", 0))) or 0, 2))
            _sub(iiaa, "GatesRate",
                 _rate_fmt(_float_val(sa_rec.get("Gates percentage",
                          sa_rec.get("Gates rate", 0))) or 0, 2))
            _sub(iiaa, "DealingSuspensionRate",
                 _rate_fmt(_float_val(sa_rec.get("Dealing suspension percentage",
                          sa_rec.get("Dealing suspension rate", 0))) or 0, 2))
            _sub(iiaa, "TotalArrangementRate",
                 _rate_fmt(_float_val(sa_rec.get("Total arrangement percentage",
                          sa_rec.get("Total arrangement rate", 0))) or 0, 2))
            ipt = _sub(ia, "InvestorPreferentialTreatment")
            _sub(ipt, "InvestorPreferentialTreatmentFlag",
                 _bool_str(sa_rec.get("(Legacy) Investor preferential treatment Flag") or
                          sa_rec.get("Investor preferential treatment Flag") or
                          sa_rec.get("Investor preferential treatment")))
            _sub(ipt, "DisclosureTermsPreferentialTreatmentFlag",
                 _bool_str(sa_rec.get("Disclosure Terms Preferential Treatment Flag") or
                          sa_rec.get("Disclosure Terms Preferential Treatment") or
                          sa_rec.get("Disclosure terms")))
            _sub(ipt, "LiquidityTermsPreferentialTreatmentFlag",
                 _bool_str(sa_rec.get("Liquidity Terms Preferential Treatment Flag") or
                          sa_rec.get("Liquidity Terms Preferential Treatment") or
                          sa_rec.get("Liquidity terms")))
            _sub(ipt, "FeeTermsPreferentialTreatmentFlag",
                 _bool_str(sa_rec.get("Fee Terms Preferential Treatment Flag") or
                          sa_rec.get("Fee Terms Preferential Treatment") or
                          sa_rec.get("Fee terms")))
            _sub(ipt, "OtherTermsPreferentialTreatmentFlag",
                 _bool_str(sa_rec.get("Other Terms Preferential Treatment Flag") or
                          sa_rec.get("Other Terms Preferential Treatment") or
                          sa_rec.get("Other terms")))

        # Investor Groups
        ig_container = _sub(lrp, "InvestorGroups")
        investor_recs = [i for i in self.investor_groups
                        if _str(i.get("Custom AIF Identification", "")) == aif_id
                        or _str(i.get("AIF ID", "")) == aif_id]

        for inv_rec in investor_recs:
            ig = _sub(ig_container, "InvestorGroup")
            _sub(ig, "InvestorGroupType", _str(inv_rec.get("Investor Group Type", "")))
            nav_pct = _float_val(inv_rec.get("Investor group NAV percentage") or
                           inv_rec.get("NAV %")) or 0
            _sub(ig, "InvestorGroupRate", _rate_fmt(nav_pct))

        # Financing Liquidity Profile (items 210-218)
        fl_rec = next((f for f in getattr(self, "financing_liquidity", [])
                      if _str(f.get("Custom AIF Identification", "") or
                              f.get("AIF ID", "")) == aif_id), None)
        if fl_rec:
            flp = _sub(lrp, "FinancingLiquidityProfile")
            _sub(flp, "TotalFinancingAmount",
                 str(_int_round(fl_rec.get("Available financing amount", 0) or 0)))
            pct_fields = [
                ("TotalFinancingInDays0to1Rate", "Percentage of financing amount in 0 to 1 day"),
                ("TotalFinancingInDays2to7Rate", "Percentage of financing amount in 2 to 7 days"),
                ("TotalFinancingInDays8to30Rate", "Percentage of financing amount in 8 to 30 days"),
                ("TotalFinancingInDays31to90Rate", "Percentage of financing amount in 31 to 90 days"),
                ("TotalFinancingInDays91to180Rate", "Percentage of financing amount in 91 to 180 days"),
                ("TotalFinancingInDays181to365Rate", "Percentage of financing amount in 181 to 365 days"),
                ("TotalFinancingInDays365MoreRate", "Percentage of financing amount longer than 365 days"),
            ]
            for xml_el, col_name in pct_fields:
                val = _float_val(fl_rec.get(col_name, 0)) or 0
                _sub(flp, xml_el, _rate_fmt(val, 4))

        # Operational Risk
        or_sec = _sub(rp, "OperationalRisk")
        _sub(or_sec, "TotalOpenPositions",
             str(sum(1 for p in positions if float(self._pos_val(p) or 0) != 0)))

        # Historical Risk Profile
        hrp_recs = [h for h in self.historical_risk_profiles
                   if _str(h.get("Custom AIF Identification", "")) == aif_id
                   or _str(h.get("AIF ID", "")) == aif_id]

        # Build month-to-data mapping from records
        hrp_by_month = {}
        for hrp_rec in hrp_recs:
            month_num = int(hrp_rec.get("Month", 0) or 0)
            if month_num:
                hrp_by_month[month_num] = hrp_rec

        # Determine quarter months from reporting period
        period_months_map = {
            "Q1": [("January", 1), ("February", 2), ("March", 3)],
            "Q2": [("April", 4), ("May", 5), ("June", 6)],
            "Q3": [("July", 7), ("August", 8), ("September", 9)],
            "Q4": [("October", 10), ("November", 11), ("December", 12)],
            "H1": [("January", 1), ("February", 2), ("March", 3),
                    ("April", 4), ("May", 5), ("June", 6)],
            "H2": [("July", 7), ("August", 8), ("September", 9),
                    ("October", 10), ("November", 11), ("December", 12)],
            "Y1": [("January", 1), ("February", 2), ("March", 3),
                    ("April", 4), ("May", 5), ("June", 6),
                    ("July", 7), ("August", 8), ("September", 9),
                    ("October", 10), ("November", 11), ("December", 12)],
            "X1": [("January", 1), ("February", 2), ("March", 3),
                    ("April", 4), ("May", 5), ("June", 6),
                    ("July", 7), ("August", 8), ("September", 9)],
            "X2": [("April", 4), ("May", 5), ("June", 6),
                    ("July", 7), ("August", 8), ("September", 9),
                    ("October", 10), ("November", 11), ("December", 12)],
        }
        rpt = getattr(self, '_current_aif_period_type', None) or _str(self.aifm.get("Reporting Period Type", "Q4"))
        # If HRP records exist but none have a Month field, they represent
        # only the last quarter of the period (M adapter convention).
        # The single record's data goes into the LAST month of the quarter.
        # Always use full period month range for HRP output
        quarter_months = period_months_map.get(rpt, period_months_map["Q4"])
        if hrp_recs and not hrp_by_month:
            # Records exist but none have a Month field — place data into
            # the last month of the period; remaining months output as zero.
            last_month_num = quarter_months[-1][1] if quarter_months else 12
            hrp_by_month[last_month_num] = hrp_recs[0]

        hrp = _sub(or_sec, "HistoricalRiskProfile")

        # GrossInvestmentReturnsRate
        gross = _sub(hrp, "GrossInvestmentReturnsRate")
        for month_name, month_num in quarter_months:
            rec = hrp_by_month.get(month_num, {})
            val = _float_val(rec.get("Percentage of gross investment returns",
                       rec.get("Gross Return"))) or 0
            _sub(gross, f"Rate{month_name}", _rate_fmt(val))

        # NetInvestmentReturnsRate
        net = _sub(hrp, "NetInvestmentReturnsRate")
        for month_name, month_num in quarter_months:
            rec = hrp_by_month.get(month_num, {})
            val = _float_val(rec.get("Percentage of net investment returns",
                       rec.get("Net Return"))) or 0
            _sub(net, f"Rate{month_name}", _rate_fmt(val))

        # NAVChangeRate
        nav_chg = _sub(hrp, "NAVChangeRate")
        for month_name, month_num in quarter_months:
            rec = hrp_by_month.get(month_num, {})
            val = _float_val(rec.get("Percentage of NAV change",
                       rec.get("NAV Change"))) or 0
            _sub(nav_chg, f"Rate{month_name}", _rate_fmt(val))

        # Subscription
        sub_el = _sub(hrp, "Subscription")
        for month_name, month_num in quarter_months:
            rec = hrp_by_month.get(month_num, {})
            val = _int_round(rec.get("Subscriptions in base currency",
                            rec.get("Subscriptions", 0)) or 0)
            _sub(sub_el, f"Quantity{month_name}", str(val))

        # Redemption
        red_el = _sub(hrp, "Redemption")
        for month_name, month_num in quarter_months:
            rec = hrp_by_month.get(month_num, {})
            val = _int_round(rec.get("Redemptions  in base currency",
                            rec.get("Redemptions in base currency",
                            rec.get("Redemptions", 0))) or 0)
            _sub(red_el, f"Quantity{month_name}", str(val))

        # Stress Tests
        st_recs = [s for s in self.stress_tests
                  if _str(s.get("Custom AIF Identification", "")) == aif_id
                  or _str(s.get("AIF ID", "")) == aif_id]

        st = _sub(info, "StressTests")
        if st_recs:
            for st_rec in st_recs:
                art15 = _str(st_rec.get(
                    "Results of stress tests performed in accordance with point(b) of Article 15(3)", "") or
                    st_rec.get("Stress test result Article 15", ""))
                art16 = _str(st_rec.get(
                    "Results of stress tests performed in accordance with the second subparagraph of Article 16(1)", "") or
                    st_rec.get("Stress test result Article 16", ""))
                _sub(st, "StressTestsResultArticle15", art15)
                _sub(st, "StressTestsResultArticle16", art16)
        else:
            _sub(st, "StressTestsResultArticle15", "")
            _sub(st, "StressTestsResultArticle16", "")

    def _build_aif_leverage_info(self, desc: Element, aif_id: str,
                                 aif: dict = None, positions: list = None,
                                 aum: int = 0, nav: int = 0):
        """Build AIFLeverageInfo section.

        Content-type-driven per ESMA CAF-002:
          CT 1   → only AIFLeverageArticle24-2 (leverage ratios)
          CT 2   → AIFLeverageArticle24-2
          CT 4   → AIFLeverageArticle24-2 + AIFLeverageArticle24-4
          CT 5   → AIFLeverageArticle24-2 + AIFLeverageArticle24-4

        Leverage auto-calculation (M adapter FAQ):
          Gross    = (AuM - Cash_in_base_ccy) / NAV × 100
          Commit   = AuM / NAV × 100
        """
        needs_24_4 = self._aif_needs_leverage_24_4(aif) if aif else False

        lev = _sub(desc, "AIFLeverageInfo")
        lev_art = _sub(lev, "AIFLeverageArticle24-2")

        # Get FINANCE record for this AIF
        fin_rec = next((f for f in self.finance_records
                       if _str(f.get("Custom AIF Identification", "")) == aif_id
                       or _str(f.get("AIF ID", "")) == aif_id), None)

        # Gather controlled structures for this AIF (belongs in Art24-2 per XSD)
        controlled = [c for c in getattr(self, "controlled_structures", [])
                     if _str(c.get("Custom AIF Identification", "") or
                             c.get("AIF ID", "")) == aif_id]

        if fin_rec:
            _sub(lev_art, "AllCounterpartyCollateralRehypothecationFlag",
                 _bool_str(fin_rec.get("Rehypothecation flag",
                           fin_rec.get("All counterparty collateral rehypothecation flag", "false"))))
            rehyp_rate = fin_rec.get("Rehypothecated percentage of collateral amount posted to all counterparties",
                                     fin_rec.get("Rehypothecated rate"))
            if rehyp_rate is not None and str(rehyp_rate).strip():
                _sub(lev_art, "AllCounterpartyCollateralRehypothecatedRate",
                     _rate_fmt(float(rehyp_rate or 0), 2))

            scb = _sub(lev_art, "SecuritiesCashBorrowing")
            _sub(scb, "UnsecuredBorrowingAmount",
                 str(_int_round(fin_rec.get("Unsecured borrowing amount",
                               fin_rec.get("Unsecured cash borrowing amount", 0)))))
            _sub(scb, "SecuredBorrowingPrimeBrokerageAmount",
                 str(_int_round(fin_rec.get("Collaterised/secured cash borrowing prime broker amount",
                               fin_rec.get("Collaterised/secured cash borrowing via prime broker amount",
                               fin_rec.get("Secured borrowing prime brokerage amount", 0))))))
            _sub(scb, "SecuredBorrowingReverseRepoAmount",
                 str(_int_round(fin_rec.get("Collaterised/secured cash borrowing reverse repo amount",
                               fin_rec.get("Collaterised/secured cash borrowing via reverse repo amount",
                               fin_rec.get("Secured borrowing reverse repo amount", 0))))))
            _sub(scb, "SecuredBorrowingOtherAmount",
                 str(_int_round(fin_rec.get("Collaterised/secured cash borrowing other amount",
                               fin_rec.get("Collaterised/secured cash borrowing via other amount",
                               fin_rec.get("Secured borrowing other amount", 0))))))

            # FinancialInstrumentBorrowing (items 287, 288)
            etd_val = fin_rec.get("Exchange traded derivatives exposure amount", 0)
            otc_val = fin_rec.get("OTC derivatives exposure amount",
                      fin_rec.get("OTC derivatives amount", 0))
            if _int_round(etd_val) or _int_round(otc_val):
                fib = _sub(lev_art, "FinancialInstrumentBorrowing")
                _sub(fib, "ExchangedTradedDerivativesExposureValue",
                     str(_int_round(etd_val)))
                _sub(fib, "OTCDerivativesAmount",
                     str(_int_round(otc_val)))

            _sub(lev_art, "ShortPositionBorrowedSecuritiesValue",
                 str(_int_round(fin_rec.get("Short position borrowed securities value", 0))))

            # ControlledStructures (items 290-293) per XSD goes here
            if controlled:
                cs = _sub(lev_art, "ControlledStructures")
                for c_rec in controlled:
                    cs_item = _sub(cs, "ControlledStructure")
                    cs_ident = _sub(cs_item, "ControlledStructureIdentification")
                    name = _str(c_rec.get("Controlled structure Name", "") or
                                c_rec.get("Name", ""))
                    lei = _str(c_rec.get("Controlled structure LEI code", "") or
                               c_rec.get("LEI Code", ""))
                    bic = _str(c_rec.get("Controlled structure BIC code", "") or
                               c_rec.get("BIC Code", ""))
                    _sub(cs_ident, "EntityName", name)
                    if bic:
                        _sub(cs_ident, "EntityIdentificationBIC", bic)
                    if lei:
                        _sub(cs_ident, "EntityIdentificationLEI", lei)
                    exp_val = c_rec.get("Controlled structure Exposure value",
                                        c_rec.get("Exposure value", 0))
                    _sub(cs_item, "ControlledStructureExposureValue",
                         str(_int_round(exp_val)))

            lev_aif = _sub(lev_art, "LeverageAIF")
            gross_val = float(fin_rec.get("Leverage under gross method",
                             fin_rec.get("Gross method rate", 0)) or 0)
            commit_val = float(fin_rec.get("Leverage under commitment method",
                              fin_rec.get("Commitment method rate", 0)) or 0)
            # Auto-calculate per M adapter FAQ if not provided
            if gross_val == 0 or commit_val == 0:
                gross_calc, commit_calc = self._calc_leverage(
                    aif, positions or [], aum, nav)
                if gross_val == 0:
                    gross_val = gross_calc
                if commit_val == 0:
                    commit_val = commit_calc
            _sub(lev_aif, "GrossMethodRate", _rate_fmt(gross_val, 2))
            _sub(lev_aif, "CommitmentMethodRate", _rate_fmt(commit_val, 2))
        else:
            _sub(lev_art, "AllCounterpartyCollateralRehypothecationFlag", "false")
            scb = _sub(lev_art, "SecuritiesCashBorrowing")
            _sub(scb, "UnsecuredBorrowingAmount", "0")
            _sub(scb, "SecuredBorrowingPrimeBrokerageAmount", "0")
            _sub(scb, "SecuredBorrowingReverseRepoAmount", "0")
            _sub(scb, "SecuredBorrowingOtherAmount", "0")
            _sub(lev_art, "ShortPositionBorrowedSecuritiesValue", "0")

            # ControlledStructures even without FINANCE record
            if controlled:
                cs = _sub(lev_art, "ControlledStructures")
                for c_rec in controlled:
                    cs_item = _sub(cs, "ControlledStructure")
                    cs_ident = _sub(cs_item, "ControlledStructureIdentification")
                    name = _str(c_rec.get("Controlled structure Name", "") or
                                c_rec.get("Name", ""))
                    lei = _str(c_rec.get("Controlled structure LEI code", "") or
                               c_rec.get("LEI Code", ""))
                    bic = _str(c_rec.get("Controlled structure BIC code", "") or
                               c_rec.get("BIC Code", ""))
                    _sub(cs_ident, "EntityName", name)
                    if bic:
                        _sub(cs_ident, "EntityIdentificationBIC", bic)
                    if lei:
                        _sub(cs_ident, "EntityIdentificationLEI", lei)
                    exp_val = c_rec.get("Controlled structure Exposure value",
                                        c_rec.get("Exposure value", 0))
                    _sub(cs_item, "ControlledStructureExposureValue",
                         str(_int_round(exp_val)))

            lev_aif = _sub(lev_art, "LeverageAIF")
            # No FINANCE record: auto-calc per M adapter FAQ
            gross_calc, commit_calc = self._calc_leverage(
                aif, positions or [], aum, nav)
            _sub(lev_aif, "GrossMethodRate", _rate_fmt(gross_calc, 2))
            _sub(lev_aif, "CommitmentMethodRate", _rate_fmt(commit_calc, 2))

        # AIFLeverageArticle24-4: only for CT 4 and 5
        # XSD: exactly 5 BorrowingSource elements (minOccurs=5, maxOccurs=5)
        # directly inside AIFLeverageArticle24-4 (no wrapper element).
        # ControlledStructures belongs in AIFLeverageArticle24-2, handled above.
        if needs_24_4:
            borrows = [b for b in getattr(self, "borrow_sources", [])
                      if _str(b.get("Custom AIF Identification", "") or
                              b.get("AIF ID", "")) == aif_id]

            lev_art4 = _sub(lev, "AIFLeverageArticle24-4")
            # XSD: exactly 5 BorrowingSource, each with Ranking, BorrowingSourceFlag,
            # optional SourceIdentification (EntityName/LEI/BIC), optional LeverageAmount
            for rank in range(1, 6):
                b_rec = borrows[rank - 1] if rank <= len(borrows) else None
                bs = _sub(lev_art4, "BorrowingSource")
                _sub(bs, "Ranking", str(rank))
                if b_rec:
                    _sub(bs, "BorrowingSourceFlag", "true")
                    src = _sub(bs, "SourceIdentification")
                    name = _str(b_rec.get("Name of the source", "") or
                                b_rec.get("Name", ""))
                    _sub(src, "EntityName", name)
                    bic = _str(b_rec.get("BIC code of the source", "") or
                               b_rec.get("BIC Code", ""))
                    if bic:
                        _sub(src, "EntityIdentificationBIC", bic)
                    lei = _str(b_rec.get("LEI code of the source", "") or
                               b_rec.get("LEI Code", ""))
                    if lei:
                        _sub(src, "EntityIdentificationLEI", lei)
                    amt = b_rec.get("Received leverage amount", 0)
                    _sub(bs, "LeverageAmount", str(_int_round(amt)))
                else:
                    _sub(bs, "BorrowingSourceFlag", "false")

    # ── Auto-calculation methods (M adapter FAQ) ──────────────────────

    def _calc_leverage(self, aif: dict, positions: list, aum: int, nav: int
                       ) -> tuple:
        """Auto-calculate leverage per M adapter FAQ.

        Gross  = (AuM - Cash) / NAV × 100
        Commit = AuM / NAV × 100

        Cash = sum of POSITION values where SubAssetType=SEC_CSH_OTHC.
        All POSITION / POSITION_COMPACT amounts are denominated in the AIF
        base currency regardless of the currency column, so no currency
        filter is applied.
        Returns (gross_rate, commit_rate), defaulting to 100.00 if NAV is zero.
        """
        if nav == 0:
            return (100.0, 100.0)
        cash_base = 0.0
        for p in positions:
            sat = _str(p.get("Sub-Asset Type of Position", "") or
                       p.get("Sub-Asset Type", "") or p.get("SubAssetType", ""))
            if sat == "SEC_CSH_OTHC":
                cash_base += abs(float(self._pos_val(p) or 0))
        gross = (aum - cash_base) / nav * 100.0
        commit = aum / nav * 100.0
        return (round(gross, 2), round(commit, 2))

    def _calc_unencumbered_cash(self, aif_id: str, positions: list) -> int:
        """Auto-calculate unencumbered cash per M adapter FAQ.

        Sum of all POSITION records with SubAssetType=SEC_CSH_OTHC.
        Uses NAV field first, then position value. Min 0.
        """
        total = 0.0
        for p in positions:
            sat = _str(p.get("Sub-Asset Type of Position", "") or
                       p.get("Sub-Asset Type", "") or p.get("SubAssetType", ""))
            if sat == "SEC_CSH_OTHC":
                nav_val = p.get("Net Asset Value")
                if nav_val is not None and nav_val != "":
                    total += float(nav_val or 0)
                else:
                    total += float(self._pos_val(p) or 0)
        return max(0, _int_round(total))

    def _calc_portfolio_liquidity(self, aif_id: str, positions: list,
                                   unencumbered_cash: int) -> dict:
        """Auto-calculate portfolio liquidity per M adapter FAQ.

        '0to1' bucket = unencumbered cash + SEC_LEQ_IFIN + SEC_LEQ_OTHR
        Everything else → '365More' bucket.
        """
        liquid_types = {"SEC_LEQ_IFIN", "SEC_LEQ_OTHR"}
        liquid_val = float(unencumbered_cash)
        total_val = float(unencumbered_cash)  # start with cash
        for p in positions:
            sat = _str(p.get("Sub-Asset Type of Position", "") or
                       p.get("Sub-Asset Type", "") or p.get("SubAssetType", ""))
            val = abs(float(self._pos_val(p) or 0))
            if sat == "SEC_CSH_OTHC":
                continue  # already counted in unencumbered_cash
            total_val += val
            if sat in liquid_types:
                liquid_val += val
        if total_val == 0:
            return {"0to1": 0.0, "365more": 0.0, "cash": 0}
        rate_0to1 = liquid_val / total_val * 100.0
        rate_365 = 100.0 - rate_0to1
        return {
            "0to1": round(rate_0to1, 4),
            "365more": round(rate_365, 4),
            "cash": unencumbered_cash,
        }
