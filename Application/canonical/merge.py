"""Multi-source merge logic for canonical reports.

When multiple adapters contribute to the same report (e.g. M template for
most fields, AI extraction for missing fields, client edits for corrections),
this module merges their outputs into a single canonical report using the
priority hierarchy:

    MANUALLY_OVERRIDDEN > IMPORTED > DERIVED > AI_PROPOSED > SMART_DEFAULT

At equal priority, higher confidence wins; at equal confidence, the most
recent timestamp wins.
"""

from __future__ import annotations

import logging
from typing import Optional

from .aifmd_field_registry import FieldRegistry, get_registry
from .model import CanonicalReport
from .provenance import FieldValue

log = logging.getLogger(__name__)


def merge_reports(
    target: CanonicalReport,
    *sources: CanonicalReport,
    registry: Optional[FieldRegistry] = None,
) -> CanonicalReport:
    """Merge one or more source reports into a target report.

    For each field, the value with the highest effective priority wins.
    The target report is modified in place and returned.

    Args:
        target:   The base report to merge into (may already have values).
        sources:  One or more reports whose fields should be merged in.
        registry: Optional field registry (uses global singleton if None).

    Returns:
        The target report with merged fields and groups.
    """
    reg = registry or get_registry()

    for source in sources:
        # Merge scalar fields
        for fid, fv in source.fields.items():
            existing = target.get_field(fid)
            if existing is None or fv.beats(existing):
                # Direct set — bypasses the priority check in set_field
                # because we already checked with beats()
                target._fields[fid] = fv
                if existing is not None:
                    target._history.setdefault(fid, []).append(existing)
            else:
                # Record the losing value in history for audit
                target._history.setdefault(fid, []).append(fv)

        # Merge repeating groups
        for gname, items in source.groups.items():
            existing_items = target.get_group(gname)
            if not existing_items:
                # No existing data for this group — take source data as-is
                target._groups[gname] = [dict(item) for item in items]
            else:
                # Group already has items — check source priority.
                # For repeating groups, we replace the entire group if
                # the source has higher priority on average.
                source_avg = _avg_priority(items)
                target_avg = _avg_priority(existing_items)
                if source_avg > target_avg:
                    # Archive old items in history
                    for old_item in existing_items:
                        for fid, fv in old_item.items():
                            target._history.setdefault(
                                f"{gname}.{fid}", []
                            ).append(fv)
                    target._groups[gname] = [dict(item) for item in items]

        # Merge metadata
        for s in source.metadata.sources:
            if s not in target.metadata.sources:
                target.metadata.sources.append(s)

    return target


def merge_field(
    target: CanonicalReport,
    field_id: str,
    value: FieldValue,
) -> bool:
    """Merge a single field value into a target report.

    Returns True if the value was accepted (overwrote or was first), False
    if it lost to an existing higher-priority value.
    """
    existing = target.get_field(field_id)
    if existing is None or value.beats(existing):
        if existing is not None:
            target._history.setdefault(field_id, []).append(existing)
        target._fields[field_id] = value
        return True
    else:
        target._history.setdefault(field_id, []).append(value)
        return False


def _avg_priority(items: list[dict[str, FieldValue]]) -> float:
    """Calculate the average priority across all fields in a group's items."""
    total = 0
    count = 0
    for item in items:
        for fv in item.values():
            total += fv.priority
            count += 1
    return total / count if count else 0
