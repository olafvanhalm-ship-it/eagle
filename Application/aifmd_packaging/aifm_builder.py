"""AIFM XML generation mixin."""

from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement

from shared.aifmd_constants import (
    XSD_VERSION, AIFM_XSD, XSI_NS,
    FCA_VERSION, FCA_AIFM_NS,
    _ESMA_TO_FCA_FIELD,
)
from shared.formatting import (
    _str, _int_round, _bool_str, _is_eea, _sub, _rate_fmt,
    _reporting_period_dates, _pretty_xml,
)


class AifmBuilderMixin:
    """Mixin for AIFM XML generation methods."""

    def generate_aifm_xml(self, output_path: str = None,
                         reporting_member_state: str = None) -> str:
        rms = reporting_member_state or self.reporting_member_state

        # For full template, look up the national code for this reporting member state
        aifm_nc = self.aifm_national_code
        if self.template_type == "FULL" and rms and self.aifm_national_codes:
            for nc_rec in self.aifm_national_codes:
                nc_rms = _str(nc_rec.get("AIFM Reporting Member State", "") or
                              nc_rec.get("Reporting Member State", ""))
                if nc_rms == rms:
                    aifm_nc = _str(nc_rec.get("AIFM National Code", ""))
                    break

        is_fca = (rms == "GB")

        root = Element("AIFMReportingInfo")
        if is_fca:
            root.set("xmlns", FCA_AIFM_NS)
        root.set("CreationDateAndTime", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        root.set("ReportingMemberState", rms)
        root.set("Version", FCA_VERSION if is_fca else XSD_VERSION)
        if not is_fca:
            root.set("xsi:noNamespaceSchemaLocation", AIFM_XSD)
            root.set("xmlns:xsi", XSI_NS)

        # ── CANCEL filing → CancellationAIFMRecordInfo (ESMA-compliant) ──
        if self.filing_type.upper() == "CANCEL":
            crec = _sub(root, "CancellationAIFMRecordInfo")
            _sub(crec, "CancelledAIFMNationalCode", aifm_nc)
            _sub(crec, "CancelledReportingPeriodType", self.reporting_period_type)
            _sub(crec, "CancelledReportingPeriodYear", str(self.reporting_year))
            _sub(crec, "CancelledRecordFlag", "C")
        else:
            # ── INIT / AMND → normal AIFMRecordInfo ──
            rec = _sub(root, "AIFMRecordInfo")
            _sub(rec, "FilingType", self.filing_type)

            # ContentType:
            #   1 = Art. 24(1) for all AIFs managed (authorised AIFM, home NCA)
            #   2 = Art. 3(3)(d) for all AIFs managed (registered AIFM)
            #   3 = Art. 24(1) for all AIFs marketed in the Member State (non-home NCA)
            if self.template_type != "FULL":
                content_type = "2"  # registered
            elif rms == self.aifm_jurisdiction:
                content_type = "1"  # authorised, home NCA
            else:
                content_type = "3"  # authorised, marketing NCA
            _sub(rec, "AIFMContentType", content_type)

            # Reporting period
            period_start, period_end = _reporting_period_dates(self.reporting_period_type,
                                                               self.reporting_year)
            _sub(rec, "ReportingPeriodStartDate", period_start)
            _sub(rec, "ReportingPeriodEndDate", period_end)
            _sub(rec, "ReportingPeriodType", self.reporting_period_type)
            _sub(rec, "ReportingPeriodYear", str(self.reporting_year))

            # Obligation change codes (optional, typically AMND only)
            aifm_obl_freq = _str(self.aifm.get("Change in AIFM Reporting Obligation Frequency Code", ""))
            aifm_obl_cont = _str(self.aifm.get("Change in AIFM Reporting Obligation contents Code",
                                  self.aifm.get("Change in AIFM Reporting Obligation Contents Code", "")))
            aifm_obl_qtr = _str(self.aifm.get("Change in AIFM Reporting Obligation Quarter", ""))
            if aifm_obl_freq and aifm_obl_freq.lower() not in ("none", "n/a", ""):
                _sub(rec, "AIFMReportingObligationChangeFrequencyCode", aifm_obl_freq)
            if aifm_obl_cont and aifm_obl_cont.lower() not in ("none", "n/a", ""):
                _sub(rec, "AIFMReportingObligationChangeContentsCode", aifm_obl_cont)
            if aifm_obl_qtr and aifm_obl_qtr.lower() not in ("none", "n/a", ""):
                _sub(rec, "AIFMReportingObligationChangeQuarter", aifm_obl_qtr)

            _sub(rec, "LastReportingFlag", _bool_str(self.aifm.get("Last Reporting Flag")))

            # Assumptions (if any AIFM_ASSUMPTION records exist)
            if self.aifm_assumptions:
                assumptions = _sub(rec, "Assumptions")
                for a_rec in self.aifm_assumptions:
                    a_elem = _sub(assumptions, "Assumption")
                    q_num = _str(a_rec.get("Question Number", ""))
                    a_desc = _str(a_rec.get("Assumption Description", ""))
                    if is_fca:
                        fca_ref = _ESMA_TO_FCA_FIELD.get(q_num, q_num)
                        _sub(a_elem, "FCAFieldReference", fca_ref)
                        _sub(a_elem, "AssumptionDetails", a_desc)
                    else:
                        _sub(a_elem, "QuestionNumber", q_num)
                        _sub(a_elem, "AssumptionDescription", a_desc)

            # Reporting code from AIFM record or default
            reporting_code = _str(self.aifm.get("AIFM Reporting Code", "")) or "1"
            _sub(rec, "AIFMReportingCode", reporting_code)
            _sub(rec, "AIFMJurisdiction", self.aifm_jurisdiction)
            _sub(rec, "AIFMNationalCode", aifm_nc)
            _sub(rec, "AIFMName", self.aifm_name)
            if not is_fca:
                _sub(rec, "AIFMEEAFlag", str(_is_eea(self.aifm_jurisdiction)).lower())
            _sub(rec, "AIFMNoReportingFlag",
                 _bool_str(self.aifm.get("AIFM no reporting flag (Nothing to report)")))

            # Complete description
            if _bool_str(self.aifm.get("AIFM no reporting flag (Nothing to report)")) == "false":
                self._build_aifm_complete_description(rec, reporting_member_state=rms)

        xml_str = _pretty_xml(root)

        # Add comment
        lines = xml_str.split("\n")
        nca_label = "FCA" if is_fca else "ESMA"
        comment = f"<!-- {nca_label} AIFM. Created by Eagle Platform (M adapter). -->"
        xml_str = lines[0] + "\n" + comment + "\n" + "\n".join(lines[1:])

        if output_path:
            Path(output_path).write_text(xml_str, encoding="utf-8")
        return xml_str

    def _build_aifm_complete_description(self, rec: Element,
                                         reporting_member_state: str = ""):
        desc = _sub(rec, "AIFMCompleteDescription")

        # Identifier
        aifm_bic = getattr(self, "aifm_bic", "")
        if self.aifm_lei or aifm_bic:
            ident = _sub(desc, "AIFMIdentifier")
            if self.aifm_lei:
                _sub(ident, "AIFMIdentifierLEI", self.aifm_lei)
            if aifm_bic:
                _sub(ident, "AIFMIdentifierBIC", aifm_bic)

        # Gather positions — filtered by NCA region to avoid cross-counting
        # ESMA: positions from funds reported to any ESMA NCA (not FCA), de-duplicated
        # FCA:  positions from funds reported to the FCA only
        allowed_aifs = self._aif_ids_for_region(reporting_member_state)
        all_positions = []
        for aif in self.aifs:
            aif_id = _str(aif.get("Custom AIF Identification", "") or aif.get("AIF ID", ""))
            if allowed_aifs is not None and aif_id not in allowed_aifs:
                continue
            all_positions.extend(self._positions_for_aif(aif_id))

        total_aum = self._total_aum_all_aifs(reporting_member_state)

        # ── EUR conversion ──────────────────────────────────────────────
        # AIFM-level monetary amounts (AggregatedValueAmount, AUMAmountInEuro)
        # must always be expressed in EUR.  When the fund base currency is not
        # EUR we convert using the FX rate from the AIF record / template /
        # ECB lookup.  We resolve the rate once and apply it consistently to
        # the total AUM, principal-market amounts and principal-instrument
        # amounts.
        first_aif_id = (
            _str(self.aifs[0].get("Custom AIF Identification", "")
                 or self.aifs[0].get("AIF ID", ""))
            if self.aifs else ""
        )
        fx_rate = self._get_fx_rate(first_aif_id)

        def _to_eur(amount):
            """Convert a base-currency amount to EUR."""
            if fx_rate and fx_rate != 1.0:
                return _int_round(amount / fx_rate)
            return _int_round(amount)

        total_aum_eur = _to_eur(total_aum)

        # Principal Markets
        markets = _sub(desc, "AIFMPrincipalMarkets")
        for rank in range(1, 6):
            mkt = _sub(markets, "AIFMFivePrincipalMarket")
            _sub(mkt, "Ranking", str(rank))
            mid = _sub(mkt, "MarketIdentification")
            if rank == 1:
                _sub(mid, "MarketCodeType", "XXX")
                _sub(mkt, "AggregatedValueAmount", str(total_aum_eur))
            else:
                _sub(mid, "MarketCodeType", "NOT")

        # Principal Instruments
        instruments = _sub(desc, "AIFMPrincipalInstruments")
        agg = self._aggregate_by_sub_asset(all_positions,
                                           reporting_member_state=reporting_member_state)[:5]
        for rank in range(1, 6):
            inst = _sub(instruments, "AIFMPrincipalInstrument")
            _sub(inst, "Ranking", str(rank))
            if rank <= len(agg):
                a = agg[rank - 1]
                _sub(inst, "SubAssetType", a["sub_asset"])
                _sub(inst, "AggregatedValueAmount", str(_to_eur(a["amount"])))
            else:
                _sub(inst, "SubAssetType", "NTA_NTA_NOTA")

        # AUM in EUR
        _sub(desc, "AUMAmountInEuro", str(total_aum_eur))

        # Base currency description (full only)
        if self.template_type == "FULL":
            # Get base currency from the first AIF
            base_ccy = self._get_base_currency(
                _str(self.aifs[0].get("Custom AIF Identification", "") or self.aifs[0].get("AIF ID", "")) if self.aifs else ""
            )
            fx_rate = self._get_fx_rate(
                _str(self.aifs[0].get("Custom AIF Identification", "") or self.aifs[0].get("AIF ID", "")) if self.aifs else ""
            )
            ccy_desc = _sub(desc, "AIFMBaseCurrencyDescription")
            _sub(ccy_desc, "BaseCurrency", base_ccy)
            _sub(ccy_desc, "AUMAmountInBaseCurrency", str(total_aum))
            _sub(ccy_desc, "FXEURReferenceRateType", "ECB")
            _sub(ccy_desc, "FXEURRate", _rate_fmt(fx_rate, 4))
