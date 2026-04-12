"""Field-level provenance tracking for AIFMD canonical records.

Every field value in a canonical report carries provenance metadata:
which adapter produced it, at what priority level, and when. This enables
multi-source merge (e.g. M template + AI extraction), audit trails, and
the interactive correction loop where client edits override imported data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Optional


class SourcePriority(IntEnum):
    """Priority levels for field value sources.

    Higher numeric value = higher priority = wins in merge conflicts.
    Aligned with eagle_software_architecture.md §L2 merge spec.
    """
    SMART_DEFAULT = 10     # System-generated default value
    AI_PROPOSED = 20       # AI-extracted from unstructured source (low confidence)
    DERIVED = 30           # Calculated from other fields (e.g. EEA flag from domicile)
    IMPORTED = 40          # Parsed from structured input (M template, ESMA Excel, XML)
    SYSTEM = 45            # Auto-generated metadata (version, dates, NCA code) — not editable
    MANUALLY_OVERRIDDEN = 50  # Client edit via review screen


@dataclass
class FieldValue:
    """A single field value with full provenance metadata.

    Attributes:
        value:       The actual data (str, int, float, bool, None).
        source:      Identifier of the adapter or process that produced this value
                     (e.g. "m_adapter", "esma_excel", "xml_import", "ai_extract",
                     "derivation_engine", "client_review").
        priority:    Source priority level — determines winner in merge conflicts.
        confidence:  Confidence score 0.0-1.0 (relevant for AI_PROPOSED; 1.0 for
                     deterministic sources).
        timestamp:   When this value was produced (UTC).
        source_ref:  Optional reference to the source location (e.g. cell address,
                     XML XPath, page number in PDF).
        note:        Optional human-readable note (e.g. "Derived from positions",
                     "AI extracted from annual report page 42").
    """
    value: Any
    source: str
    priority: SourcePriority = SourcePriority.IMPORTED
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_ref: Optional[str] = None
    note: Optional[str] = None

    def beats(self, other: "FieldValue") -> bool:
        """Return True if this value should override the other in a merge.

        Rules:
        1. Higher priority always wins.
        2. At equal priority, higher confidence wins.
        3. At equal priority and confidence, newer timestamp wins.
        """
        if self.priority != other.priority:
            return self.priority > other.priority
        if self.confidence != other.confidence:
            return self.confidence > other.confidence
        return self.timestamp > other.timestamp

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "value": self.value,
            "source": self.source,
            "priority": self.priority.name,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "source_ref": self.source_ref,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FieldValue":
        """Deserialize from a JSON-compatible dict."""
        priority_map = {p.name: p for p in SourcePriority}
        return cls(
            value=data["value"],
            source=data["source"],
            priority=priority_map.get(data.get("priority", "IMPORTED"), SourcePriority.IMPORTED),
            confidence=data.get("confidence", 1.0),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(timezone.utc),
            source_ref=data.get("source_ref"),
            note=data.get("note"),
        )

    def __repr__(self) -> str:
        return (
            f"FieldValue({self.value!r}, source={self.source!r}, "
            f"priority={self.priority.name}, confidence={self.confidence})"
        )
