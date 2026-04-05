"""AIFMD Annex IV Canonical Report Model.

Defines CanonicalAIFMReport (38 ESMA fields) and CanonicalAIFReport
(302 ESMA fields) as the universal in-memory representation.  Every
adapter writes to this model; every downstream stage reads from it.

Key design decisions:
- Scalar fields stored as dict[field_id → FieldValue]
- Repeating groups stored as list[dict[field_id → FieldValue]]
- Field IDs are always strings matching ESMA question numbers ("1" .. "302")
- The model is schema-aware via the FieldRegistry but does not enforce types
  at write time — that is the validation engine's job
- Full provenance per field via FieldValue
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .aifmd_field_registry import FieldRegistry, ReportType, RepeatingGroup, get_registry
from .provenance import FieldValue, SourcePriority

log = logging.getLogger(__name__)


@dataclass
class ReportMetadata:
    """Report-level metadata (not part of the ESMA field set)."""
    report_id: str = field(default_factory=lambda: str(uuid4()))
    report_type: ReportType = ReportType.AIF
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "draft"   # draft → validated → reviewed → approved → submitted
    sources: list[str] = field(default_factory=list)  # list of adapter names that contributed

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "report_type": self.report_type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "sources": self.sources,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReportMetadata":
        return cls(
            report_id=data.get("report_id", str(uuid4())),
            report_type=ReportType(data.get("report_type", "AIF")),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(timezone.utc),
            status=data.get("status", "draft"),
            sources=data.get("sources", []),
        )


class CanonicalReport:
    """Base class for AIFM and AIF canonical reports.

    Stores scalar fields and repeating groups with full provenance.
    """

    def __init__(self, report_type: ReportType, registry: Optional[FieldRegistry] = None):
        self.metadata = ReportMetadata(report_type=report_type)
        self._registry = registry or get_registry()
        self._report_type = report_type

        # Scalar fields: field_id → FieldValue
        self._fields: dict[str, FieldValue] = {}

        # Repeating groups: group_name → list of item dicts
        # Each item is dict[field_id → FieldValue]
        self._groups: dict[str, list[dict[str, FieldValue]]] = {}

        # Provenance history: field_id → list of all FieldValues ever set
        # (for audit trail — keeps overwritten values)
        self._history: dict[str, list[FieldValue]] = {}

    # --- Scalar field access ---

    def set_field(self, field_id: str, value: Any, source: str,
                  priority: SourcePriority = SourcePriority.IMPORTED,
                  confidence: float = 1.0,
                  source_ref: Optional[str] = None,
                  note: Optional[str] = None) -> None:
        """Set a scalar field value with provenance.

        If the field already has a value, the new value only replaces it
        if it has higher priority (or equal priority with higher confidence
        or newer timestamp). The old value is preserved in history.
        """
        fv = FieldValue(
            value=value, source=source, priority=priority,
            confidence=confidence, source_ref=source_ref, note=note,
        )
        existing = self._fields.get(field_id)
        if existing is not None:
            if not fv.beats(existing):
                # Keep existing, but still record in history
                self._history.setdefault(field_id, []).append(fv)
                return
            # Save old value to history
            self._history.setdefault(field_id, []).append(existing)

        self._fields[field_id] = fv
        self.metadata.updated_at = datetime.now(timezone.utc)
        if source not in self.metadata.sources:
            self.metadata.sources.append(source)

    def get_field(self, field_id: str) -> Optional[FieldValue]:
        """Get the current FieldValue for a scalar field."""
        return self._fields.get(str(field_id))

    def get_value(self, field_id: str, default: Any = None) -> Any:
        """Get just the raw value of a scalar field."""
        fv = self._fields.get(str(field_id))
        return fv.value if fv is not None else default

    def has_field(self, field_id: str) -> bool:
        """Check if a field has been set."""
        return str(field_id) in self._fields

    @property
    def fields(self) -> dict[str, FieldValue]:
        """All scalar field values (read-only view)."""
        return dict(self._fields)

    # --- Repeating group access ---

    def add_group_item(self, group_name: str,
                       values: dict[str, Any],
                       source: str,
                       priority: SourcePriority = SourcePriority.IMPORTED,
                       confidence: float = 1.0) -> int:
        """Add an item to a repeating group.

        Args:
            group_name: Programmatic group name (e.g. "main_instruments")
            values:     Dict of field_id → raw value for this item
            source:     Adapter/process identifier
            priority:   Source priority
            confidence: Confidence score

        Returns:
            The index of the newly added item.
        """
        group_def = self._registry.repeating_group(group_name)
        if group_def is None:
            log.warning("Unknown repeating group: %s", group_name)

        items = self._groups.setdefault(group_name, [])

        # Check max items
        if group_def and group_def.max_items is not None:
            if len(items) >= group_def.max_items:
                log.warning(
                    "Repeating group %s already has %d items (max %d)",
                    group_name, len(items), group_def.max_items,
                )

        item: dict[str, FieldValue] = {}
        for fid, val in values.items():
            item[str(fid)] = FieldValue(
                value=val, source=source, priority=priority,
                confidence=confidence,
            )
        items.append(item)
        self.metadata.updated_at = datetime.now(timezone.utc)
        if source not in self.metadata.sources:
            self.metadata.sources.append(source)
        return len(items) - 1

    def get_group(self, group_name: str) -> list[dict[str, FieldValue]]:
        """Get all items in a repeating group."""
        return self._groups.get(group_name, [])

    def get_group_values(self, group_name: str) -> list[dict[str, Any]]:
        """Get all items in a repeating group as plain dicts (values only)."""
        return [
            {fid: fv.value for fid, fv in item.items()}
            for item in self._groups.get(group_name, [])
        ]

    def clear_group(self, group_name: str) -> None:
        """Remove all items from a repeating group."""
        self._groups.pop(group_name, None)

    @property
    def groups(self) -> dict[str, list[dict[str, FieldValue]]]:
        """All repeating groups (read-only view)."""
        return dict(self._groups)

    # --- History / audit ---

    def field_history(self, field_id: str) -> list[FieldValue]:
        """Get the provenance history for a field (oldest first)."""
        return list(self._history.get(str(field_id), []))

    # --- Bulk operations ---

    def set_fields_bulk(self, values: dict[str, Any], source: str,
                        priority: SourcePriority = SourcePriority.IMPORTED,
                        confidence: float = 1.0) -> None:
        """Set multiple scalar fields at once from the same source."""
        for fid, val in values.items():
            self.set_field(str(fid), val, source=source,
                          priority=priority, confidence=confidence)

    # --- Completeness ---

    def missing_mandatory_fields(self) -> list[str]:
        """Return field_ids of mandatory fields that have no value."""
        all_fields = (self._registry.aifm_fields()
                      if self._report_type == ReportType.AIFM
                      else self._registry.aif_fields())
        missing = []
        for fid, fdef in all_fields.items():
            if fdef.mandatory and not fdef.is_repeating:
                if fid not in self._fields:
                    missing.append(fid)
        return missing

    def completeness_pct(self) -> float:
        """Percentage of mandatory fields that are filled."""
        all_fields = (self._registry.aifm_fields()
                      if self._report_type == ReportType.AIFM
                      else self._registry.aif_fields())
        mandatory = [f for f in all_fields.values()
                     if f.mandatory and not f.is_repeating]
        if not mandatory:
            return 100.0
        filled = sum(1 for f in mandatory if f.field_id in self._fields)
        return round(100.0 * filled / len(mandatory), 1)

    # --- Section-based access (for review screen / PDF rendering) ---

    def fields_by_section(self) -> dict[str, dict[str, FieldValue]]:
        """Group all scalar fields by their ESMA section.

        Returns dict of section_name → dict[field_id → FieldValue].
        Used by the review screen and PDF renderer.
        """
        sections = self._registry.sections(self._report_type)
        result: dict[str, dict[str, FieldValue]] = {}
        for section_name, field_defs in sections.items():
            section_values = {}
            for fdef in field_defs:
                fv = self._fields.get(fdef.field_id)
                if fv is not None:
                    section_values[fdef.field_id] = fv
            if section_values:
                result[section_name] = section_values
        return result

    # --- Serialization ---

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict (for file-based storage)."""
        return {
            "metadata": self.metadata.to_dict(),
            "fields": {
                fid: fv.to_dict() for fid, fv in self._fields.items()
            },
            "groups": {
                gname: [
                    {fid: fv.to_dict() for fid, fv in item.items()}
                    for item in items
                ]
                for gname, items in self._groups.items()
            },
            "history": {
                fid: [fv.to_dict() for fv in history]
                for fid, history in self._history.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, registry: Optional[FieldRegistry] = None) -> "CanonicalReport":
        """Deserialize from a JSON-compatible dict."""
        meta = ReportMetadata.from_dict(data.get("metadata", {}))
        report = cls(report_type=meta.report_type, registry=registry)
        report.metadata = meta

        # Restore fields
        for fid, fv_data in data.get("fields", {}).items():
            report._fields[fid] = FieldValue.from_dict(fv_data)

        # Restore groups
        for gname, items_data in data.get("groups", {}).items():
            report._groups[gname] = [
                {fid: FieldValue.from_dict(fv_data) for fid, fv_data in item.items()}
                for item in items_data
            ]

        # Restore history
        for fid, history_data in data.get("history", {}).items():
            report._history[fid] = [FieldValue.from_dict(fv) for fv in history_data]

        return report

    def __repr__(self) -> str:
        n_fields = len(self._fields)
        n_groups = sum(len(items) for items in self._groups.values())
        return (
            f"CanonicalReport(type={self._report_type.value}, "
            f"fields={n_fields}, group_items={n_groups}, "
            f"status={self.metadata.status!r})"
        )


class CanonicalAIFMReport(CanonicalReport):
    """Canonical report for an AIFM (38 ESMA fields)."""

    def __init__(self, registry: Optional[FieldRegistry] = None):
        super().__init__(ReportType.AIFM, registry)


class CanonicalAIFReport(CanonicalReport):
    """Canonical report for an AIF (302 ESMA fields)."""

    def __init__(self, registry: Optional[FieldRegistry] = None):
        super().__init__(ReportType.AIF, registry)
