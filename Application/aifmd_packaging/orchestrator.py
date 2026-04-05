"""Multi-NCA orchestration and packaging mixin.

Also provides a standalone `build_from_canonical()` entry point that
generates XML + NCA packaging from canonical reports without requiring
a direct MAdapter import (Phase 4 — canonical-to-XML path).
"""

import gzip
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from shared.formatting import _str, _reporting_period_dates
from aifmd_packaging.aifmd_nca_packaging import NCA_PACKAGING_CONFIG

if TYPE_CHECKING:
    from canonical.model import CanonicalAIFMReport, CanonicalAIFReport


# ── Standalone canonical-to-XML entry point (Phase 4) ─────────────────────

def build_from_canonical(
    aifm_report: "CanonicalAIFMReport",
    aif_reports: list["CanonicalAIFReport"],
    output_dir: str,
    reporting_member_state: Optional[str] = None,
) -> dict:
    """Generate AIFMD XML files and NCA packaging from canonical reports.

    This is the recommended entry point for the platform pipeline (L6).
    It wraps the MAdapter.from_canonical() round-trip, using the packaging
    mixins without exposing the adapter's internal structure.

    Args:
        aifm_report: CanonicalAIFMReport with all AIFM-level data.
        aif_reports: List of CanonicalAIFReport, one per AIF.
        output_dir: Directory to write generated files to.
        reporting_member_state: Optional NCA filter (e.g., "NL", "DE", "GB").
            If omitted, generates for all NCAs found in the canonical data.

    Returns:
        Dict with keys: aifm_xmls, aif_xmls, aif_zips, gz_files — same
        format as OrchestratorMixin.generate_all().
    """
    # Lazy import to avoid circular dependency (MAdapter imports this module)
    import importlib
    import sys
    from pathlib import Path as _P

    _app_root = _P(__file__).resolve().parent.parent
    if str(_app_root) not in sys.path:
        sys.path.insert(0, str(_app_root))

    _adapter_dir = _app_root / "Adapters" / "Input adapters" / "M adapter"
    if str(_adapter_dir) not in sys.path:
        sys.path.insert(0, str(_adapter_dir))

    m_mod = importlib.import_module("m_adapter")
    MAdapter = m_mod.MAdapter

    adapter = MAdapter.from_canonical(aifm_report, aif_reports)
    return adapter.generate_all(output_dir, reporting_member_state)


class OrchestratorMixin:
    """Mixin for generate_all() and summary() methods."""

    def generate_all(self, output_dir: Optional[str] = None,
                    reporting_member_state: Optional[str] = None) -> dict:
        """Generate AIFM XML + per-AIF XML files.

        For full templates with multiple NCAs, optionally filter by reporting_member_state.
        """
        out = Path(output_dir) if output_dir else self.path.parent
        out.mkdir(parents=True, exist_ok=True)

        # For multi-NCA scenarios, iterate over reporting member states
        rms_list = [reporting_member_state] if reporting_member_state else [self.reporting_member_state]

        if self.template_type == "FULL" and not reporting_member_state and self.aifm_national_codes:
            rms_list = list(set(
                _str(nc.get("AIFM Reporting Member State", "") or
                     nc.get("Reporting Member State", ""))
                for nc in self.aifm_national_codes
                if _str(nc.get("AIFM Reporting Member State", "") or
                        nc.get("Reporting Member State", ""))
            ))

        results = {
            "aifm_xmls": [],
            "aif_xmls": [],
            "aif_zips": [],
            "gz_files": [],
        }

        for rms in rms_list:
            _, pe_date = _reporting_period_dates(
                self.reporting_period_type, self.reporting_year)
            period_end = pe_date.replace("-", "")  # YYYYMMDD

            # ── AIFM XML ───────────────────────────────────────────────────
            # Get AIFM national code for this RMS
            aifm_nc = self.aifm_national_code
            if self.template_type == "FULL" and self.aifm_national_codes:
                for nc_rec in self.aifm_national_codes:
                    nc_rms = _str(nc_rec.get("AIFM Reporting Member State", "") or
                                  nc_rec.get("Reporting Member State", ""))
                    if nc_rms == rms:
                        aifm_nc = _str(nc_rec.get("AIFM National Code", ""))
                        break

            aifm_file = out / f"AIFM_{rms}_{aifm_nc}_{period_end}.xml"
            self.generate_aifm_xml(str(aifm_file), reporting_member_state=rms)
            results["aifm_xmls"].append(str(aifm_file))

            # ── Per-AIF XMLs ───────────────────────────────────────────────
            # FCA (GB): consolidated multi-AIF in a single XML file
            # ESMA: separate XML per AIF
            aif_files = []
            is_fca = (rms == "GB")

            if is_fca and len(self.aifs) > 0:
                # FCA consolidated: AIF_REPORTS_GB_{AIFM_NC}_{YYYYMMDD}.xml
                consolidated_file = out / f"AIF_REPORTS_{rms}_{aifm_nc}_{period_end}.xml"
                self.generate_fca_consolidated_aif_xml(
                    str(consolidated_file),
                    reporting_member_state=rms)
                aif_files.append(str(consolidated_file))
                results["aif_xmls"].append(str(consolidated_file))
            else:
                # ESMA: separate XML per AIF
                # Build set of AIF IDs registered for this RMS
                aif_ids_for_rms = None
                if self.template_type == "FULL" and self.aif_national_codes:
                    aif_ids_for_rms = set()
                    for nc_rec in self.aif_national_codes:
                        nc_rms = _str(nc_rec.get("AIF Reporting Member State", "") or
                                      nc_rec.get("Reporting Member State", ""))
                        if nc_rms == rms:
                            nc_aif_id = _str(nc_rec.get("Custom AIF Identification", "") or
                                             nc_rec.get("AIF ID", ""))
                            aif_ids_for_rms.add(nc_aif_id)

                for idx, aif in enumerate(self.aifs):
                    aif_id = _str(aif.get("Custom AIF Identification", "") or
                                  aif.get("AIF Name", ""))

                    # Skip this AIF if it's not registered for this NCA
                    if aif_ids_for_rms is not None and aif_id not in aif_ids_for_rms:
                        continue

                    # Collect ALL national codes for this AIF + RMS (multi-code support)
                    aif_ncs = []
                    if self.template_type == "FULL" and self.aif_national_codes:
                        for nc_rec in self.aif_national_codes:
                            nc_rms = _str(nc_rec.get("AIF Reporting Member State", "") or
                                          nc_rec.get("Reporting Member State", ""))
                            nc_aif_id = _str(nc_rec.get("Custom AIF Identification", "") or
                                             nc_rec.get("AIF ID", ""))
                            if nc_rms == rms and nc_aif_id == aif_id:
                                nc_val = _str(nc_rec.get("AIF National Code", "") or
                                              nc_rec.get("AIF national code", ""))
                                if nc_val and nc_val not in aif_ncs:
                                    aif_ncs.append(nc_val)
                    if not aif_ncs:
                        aif_ncs = [_str(aif.get("AIF National Code", ""))]

                    for aif_nc in aif_ncs:
                        aif_file = out / f"AIF_{rms}_{aif_nc}_{period_end}.xml"
                        self.generate_aif_xml(str(aif_file), aif_index=idx,
                                             reporting_member_state=rms,
                                             override_national_code=aif_nc)
                        aif_files.append(str(aif_file))
                        results["aif_xmls"].append(str(aif_file))

            # ── NCA-specific packaging ────────────────────────────────────
            nca_spec = NCA_PACKAGING_CONFIG.get(rms, {})
            pkg_type = nca_spec.get("packaging", "xml")

            if pkg_type == "gzip":
                # BaFin (DE): each XML compressed individually as .gz
                gz_aifm = str(aifm_file).replace(".xml", ".gz")
                with open(str(aifm_file), "rb") as f_in:
                    with gzip.open(gz_aifm, "wb") as f_out:
                        f_out.write(f_in.read())
                results["gz_files"].append(gz_aifm)
                for af in aif_files:
                    gz_aif = af.replace(".xml", ".gz")
                    with open(af, "rb") as f_in:
                        with gzip.open(gz_aif, "wb") as f_out:
                            f_out.write(f_in.read())
                    results["gz_files"].append(gz_aif)

            elif pkg_type == "zip":
                # BE, ES, PT, SE, CZ, MT: all XMLs bundled in single ZIP
                all_xmls = [str(aifm_file)] + aif_files
                zip_name = out / f"AIFMD_{rms}_{aifm_nc}_{period_end}.zip"
                with zipfile.ZipFile(str(zip_name), "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    for xf in all_xmls:
                        zf.write(xf, Path(xf).name)
                results["aif_zips"].append(str(zip_name))

            elif pkg_type == "zip-in-zip":
                # LU/CSSF: each AIF XML in own ZIP, all bundled in master ZIP
                inner_zips = []
                for af in aif_files:
                    inner_zip = str(af).replace(".xml", ".zip")
                    with zipfile.ZipFile(inner_zip, "w",
                                         zipfile.ZIP_DEFLATED) as zf:
                        zf.write(af, Path(af).name)
                    inner_zips.append(inner_zip)
                # AIFM also in its own inner ZIP
                aifm_inner_zip = str(aifm_file).replace(".xml", ".zip")
                with zipfile.ZipFile(aifm_inner_zip, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    zf.write(str(aifm_file), Path(str(aifm_file)).name)
                inner_zips.insert(0, aifm_inner_zip)
                # Master ZIP containing all inner ZIPs
                master_zip = out / f"AIFMD_{rms}_{aifm_nc}_{period_end}_master.zip"
                with zipfile.ZipFile(str(master_zip), "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    for iz in inner_zips:
                        zf.write(iz, Path(iz).name)
                results["aif_zips"].append(str(master_zip))
                # Clean up inner ZIPs (they're inside the master now)
                for iz in inner_zips:
                    Path(iz).unlink(missing_ok=True)

            else:
                # "xml" — plain XML; ZIP only when multi-AIF for convenience
                zip_when_multi = nca_spec.get("zip_when_multi", True)
                if len(aif_files) > 1 and zip_when_multi:
                    zip_name = out / f"AIF_{rms}_{aifm_nc}_{period_end}.zip"
                    with zipfile.ZipFile(str(zip_name), "w",
                                         zipfile.ZIP_DEFLATED) as zf:
                        for af in aif_files:
                            zf.write(af, Path(af).name)
                    results["aif_zips"].append(str(zip_name))

        return results

    def generate_and_validate(
        self,
        output_dir: Optional[str] = None,
        reporting_member_state: Optional[str] = None,
    ) -> dict:
        """Generate XML + NCA packaging, then validate all generated files.

        This is the pipeline-integrated entry point that combines L6 (packaging)
        with L3+L4 (validation) in a single call. Returns the standard
        generate_all() result dict with an additional 'validation' key containing
        the PipelineValidationResult.

        Usage:
            result = adapter.generate_and_validate(output_dir="./output", reporting_member_state="NL")
            if result["validation"].has_critical_failures:
                # Block submission at L7
                ...
        """
        results = self.generate_all(output_dir, reporting_member_state)

        # Collect all generated XML files for validation
        all_xml = results.get("aifm_xmls", []) + results.get("aif_xmls", [])

        if not all_xml:
            results["validation"] = None
            return results

        # Determine NCA code for validation
        nca = reporting_member_state or self.reporting_member_state

        # Lazy import to avoid circular dependency
        import sys as _sys
        from pathlib import Path as _P
        _val_dir = _P(__file__).resolve().parent.parent / "validation"
        if str(_val_dir) not in _sys.path:
            _sys.path.insert(0, str(_val_dir))
        if str(_val_dir.parent) not in _sys.path:
            _sys.path.insert(0, str(_val_dir.parent))

        from validation.aifmd_validation_engine import validate_pipeline_output

        results["validation"] = validate_pipeline_output(
            xml_files=all_xml,
            nca_code=nca,
        )

        return results

    def summary(self) -> dict:
        all_positions = []
        aif_summaries = []
        for aif in self.aifs:
            aif_id = _str(aif.get("Custom AIF Identification", "") or aif.get("AIF ID", ""))
            pos = self._positions_for_aif(aif_id)
            all_positions.extend(pos)
            aif_summaries.append({
                "name": _str(aif.get("AIF Name", "")),
                "national_code": _str(aif.get("AIF National Code", "")),
                "aum": self._calc_aum(pos),
                "nav": self._calc_nav(pos),
                "positions": len(pos),
                "strategy": _str(aif.get("Investment strategy code", "")),
            })

        return {
            "template_type": self.template_type,
            "aifm_name": self.aifm_name,
            "aifm_national_code": self.aifm_national_code,
            "reporting_member_state": self.reporting_member_state,
            "reporting_year": self.reporting_year,
            "reporting_period_type": self.reporting_period_type,
            "total_aum": self._total_aum_all_aifs(),
            "num_aifs": len(self.aifs),
            "aifs": aif_summaries,
            "total_positions": len(all_positions),
        }
