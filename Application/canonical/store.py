"""File-based JSON storage for canonical reports.

Provides save/load of CanonicalReport instances as JSON files. Designed
as a lightweight Phase 5 implementation that can be replaced with a
PostgreSQL-backed store (canonical_records / canonical_fields tables)
in Phase 6 without changing the CanonicalReport API.

Storage layout:
    {store_root}/
        {report_id}.json          — full report with provenance
        index.json                — index of all reports with summary metadata

Each JSON file contains the full serialized CanonicalReport including
field values, repeating groups, and provenance history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .field_registry import FieldRegistry, ReportType, get_registry
from .model import CanonicalReport, CanonicalAIFMReport, CanonicalAIFReport

log = logging.getLogger(__name__)


class CanonicalStore:
    """File-based storage for canonical reports."""

    def __init__(self, store_root: Path, registry: Optional[FieldRegistry] = None):
        """Initialize the store.

        Args:
            store_root: Directory where report JSON files are stored.
            registry:   Optional field registry (uses global singleton if None).
        """
        self._root = Path(store_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._registry = registry or get_registry()
        self._index_path = self._root / "index.json"
        self._index: dict = self._load_index()

    def _load_index(self) -> dict:
        """Load or create the report index."""
        if self._index_path.exists():
            with open(self._index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"reports": {}}

    def _save_index(self) -> None:
        """Persist the report index to disk."""
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2, ensure_ascii=False)

    def save(self, report: CanonicalReport) -> Path:
        """Save a canonical report to disk.

        Creates or overwrites the JSON file for this report. Updates
        the index with summary metadata.

        Returns the path to the saved JSON file.
        """
        report_id = report.metadata.report_id
        file_path = self._root / f"{report_id}.json"

        data = report.to_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        # Update index
        self._index["reports"][report_id] = {
            "report_type": report.metadata.report_type.value,
            "status": report.metadata.status,
            "created_at": report.metadata.created_at.isoformat(),
            "updated_at": report.metadata.updated_at.isoformat(),
            "sources": report.metadata.sources,
            "completeness_pct": report.completeness_pct(),
            "field_count": len(report.fields),
            "file": file_path.name,
        }
        self._save_index()

        log.info("Saved report %s to %s (%.1f%% complete)",
                 report_id, file_path, report.completeness_pct())
        return file_path

    def load(self, report_id: str) -> Optional[CanonicalReport]:
        """Load a canonical report from disk.

        Returns None if the report does not exist.
        """
        file_path = self._root / f"{report_id}.json"
        if not file_path.exists():
            log.warning("Report %s not found at %s", report_id, file_path)
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        report = CanonicalReport.from_dict(data, registry=self._registry)
        log.info("Loaded report %s from %s", report_id, file_path)
        return report

    def delete(self, report_id: str) -> bool:
        """Delete a report from disk and index.

        Returns True if the report was found and deleted.
        """
        file_path = self._root / f"{report_id}.json"
        if file_path.exists():
            file_path.unlink()
        self._index["reports"].pop(report_id, None)
        self._save_index()
        return True

    def list_reports(self, report_type: Optional[ReportType] = None,
                     status: Optional[str] = None) -> list[dict]:
        """List all reports in the store, optionally filtered.

        Returns list of index entries with summary metadata.
        """
        results = []
        for rid, meta in self._index.get("reports", {}).items():
            if report_type and meta.get("report_type") != report_type.value:
                continue
            if status and meta.get("status") != status:
                continue
            results.append({"report_id": rid, **meta})
        return results

    def find_by_field(self, field_id: str, value: str) -> list[str]:
        """Find report IDs where a specific field has a specific value.

        Useful for lookups like "find all reports for AIFM national code X".
        Note: this is a scan — fine for file-based store, would be indexed in DB.
        """
        results = []
        for rid in self._index.get("reports", {}):
            report = self.load(rid)
            if report:
                fv = report.get_field(field_id)
                if fv and str(fv.value) == str(value):
                    results.append(rid)
        return results
