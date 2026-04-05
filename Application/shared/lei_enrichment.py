"""LEI enrichment engine — auto-enrich empty LEI fields from GLEIF cache.

Scans all LEI fields in a SourceCanonical. When a LEI field is empty but a
corresponding entity name is present, performs a GLEIF lookup (Path 2) and:

  - ENRICHED:             Exactly one match → writes LEI with DERIVED priority
  - PENDING_USER_CHOICE:  Multiple matches → records candidates for later UI
  - NO_MATCH:             No matches → records for manual assignment
  - SKIPPED:              LEI already filled → no action needed

Provenance: Enriched fields are set with SourcePriority.DERIVED, source
"lei_enrichment", and a note explaining the basis (e.g. "Auto-enriched from
GLEIF: 'BlackRock, Inc.' → 529900VBK42Y5HHRMD23, country=US, score=1.00").

The enrichment log tracks every decision for audit and for feeding the
review UI (which must clearly flag enriched fields to the user).

Architecture: runs at L1B (post-parsing, pre-validation).
Requirements: REQ-REF-002, REQ-VAL-001
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from canonical.aifmd_source_entities import SourceCanonical, SourceEntity
from canonical.provenance import FieldValue, SourcePriority
from shared.lei_validator import (
    normalize_entity_name,
    validate_lei_format,
)
from shared.reference_store import ReferenceStore, LEIRecord

logger = logging.getLogger(__name__)

__all__ = [
    "EnrichmentStatus",
    "EnrichmentAction",
    "EnrichmentLog",
    "enrich_lei_fields",
    "LEI_FIELD_MAP",
]


# ── Status enum ──────────────────────────────────────────────────────

class EnrichmentStatus(str, Enum):
    """Outcome of an LEI enrichment attempt."""
    ENRICHED = "ENRICHED"                        # Single match → auto-filled
    PENDING_USER_CHOICE = "PENDING_USER_CHOICE"  # Multiple matches → user picks
    NO_MATCH = "NO_MATCH"                        # No GLEIF match found
    SKIPPED = "SKIPPED"                          # LEI already present
    ERROR = "ERROR"                              # Unexpected error during lookup


# ── Action record ────────────────────────────────────────────────────

@dataclass
class EnrichmentAction:
    """One enrichment decision — written for every LEI field evaluated.

    Designed for serialization to the review UI and audit trail.
    """
    # Location
    entity_type: str          # "ManagerStatic", "Counterparty", etc.
    entity_index: int         # Position in collection (0 for scalar entities)
    lei_field: str            # "lei" or "counterparty_lei"
    name_field: str           # "name", "counterparty_name", "company_name", etc.
    entity_name: str          # The raw name value used for lookup

    # Result
    status: EnrichmentStatus
    enriched_lei: str = ""              # The LEI that was written (ENRICHED only)
    candidates: list[dict] = field(default_factory=list)
    # Each candidate: {"lei": str, "legal_name": str, "country": str, "score": float}

    original_lei: str = ""              # Original value (usually empty for enrichment)
    normalized_name: str = ""           # How the name was normalized
    message: str = ""                   # Human-readable explanation
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_index": self.entity_index,
            "lei_field": self.lei_field,
            "name_field": self.name_field,
            "entity_name": self.entity_name,
            "status": self.status.value,
            "enriched_lei": self.enriched_lei,
            "candidates": self.candidates,
            "original_lei": self.original_lei,
            "normalized_name": self.normalized_name,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


# ── Enrichment log ───────────────────────────────────────────────────

@dataclass
class EnrichmentLog:
    """Container for all enrichment actions on one SourceCanonical.

    Serializable for audit trail and for the review UI to flag enriched fields.
    """
    actions: list[EnrichmentAction] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    @property
    def enriched_count(self) -> int:
        return sum(1 for a in self.actions if a.status == EnrichmentStatus.ENRICHED)

    @property
    def pending_count(self) -> int:
        return sum(1 for a in self.actions if a.status == EnrichmentStatus.PENDING_USER_CHOICE)

    @property
    def no_match_count(self) -> int:
        return sum(1 for a in self.actions if a.status == EnrichmentStatus.NO_MATCH)

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.actions if a.status == EnrichmentStatus.SKIPPED)

    def summary(self) -> str:
        total = len(self.actions)
        return (
            f"LEI enrichment: {total} fields scanned — "
            f"{self.enriched_count} enriched, "
            f"{self.pending_count} pending user choice, "
            f"{self.no_match_count} no match, "
            f"{self.skipped_count} skipped (already filled)"
        )

    def to_dict(self) -> dict:
        return {
            "actions": [a.to_dict() for a in self.actions],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "summary": {
                "total": len(self.actions),
                "enriched": self.enriched_count,
                "pending_user_choice": self.pending_count,
                "no_match": self.no_match_count,
                "skipped": self.skipped_count,
            },
        }

    def get_pending_actions(self) -> list[EnrichmentAction]:
        """Return all PENDING_USER_CHOICE actions for the review UI."""
        return [a for a in self.actions if a.status == EnrichmentStatus.PENDING_USER_CHOICE]

    def get_enriched_fields(self) -> list[dict]:
        """Return a list of enriched field locations for UI flagging.

        Each entry identifies which field was enriched so the review screen
        can visually mark it as "auto-enriched, not original data".
        """
        return [
            {
                "entity_type": a.entity_type,
                "entity_index": a.entity_index,
                "lei_field": a.lei_field,
                "enriched_lei": a.enriched_lei,
                "basis": a.entity_name,
            }
            for a in self.actions
            if a.status == EnrichmentStatus.ENRICHED
        ]


# ── LEI field map ────────────────────────────────────────────────────
# Maps (entity_attribute_on_SourceCanonical, lei_field, name_field, country_field)
# for every LEI-bearing entity in the AIFMD canonical.

LEI_FIELD_MAP = [
    # Scalar entities (single instance)
    {
        "container": "manager",
        "is_collection": False,
        "entity_type": "ManagerStatic",
        "lei_field": "lei",
        "name_field": "name",
        "country_field": "jurisdiction",    # Manager jurisdiction as country hint
    },
    {
        "container": "fund_static",
        "is_collection": False,
        "entity_type": "FundStatic",
        "lei_field": "lei",
        "name_field": "name",
        "country_field": "domicile",        # Fund domicile as country hint
    },
    # Collection entities (lists of entities)
    {
        "container": "counterparties",
        "is_collection": True,
        "entity_type": "Counterparty",
        "lei_field": "lei",
        "name_field": "name",
        "country_field": "",                # No country on counterparty entity
    },
    {
        "container": "positions",
        "is_collection": True,
        "entity_type": "Position",
        "lei_field": "counterparty_lei",
        "name_field": "counterparty_name",
        "country_field": "",
    },
    {
        "container": "instruments",
        "is_collection": True,
        "entity_type": "Instrument",
        "lei_field": "counterparty_lei",
        "name_field": "counterparty_name",
        "country_field": "",
    },
    {
        "container": "borrowing_sources",
        "is_collection": True,
        "entity_type": "BorrowingSource",
        "lei_field": "lei",
        "name_field": "source_type",        # Best available name field
        "country_field": "",
    },
    {
        "container": "controlled_companies",
        "is_collection": True,
        "entity_type": "ControlledCompany",
        "lei_field": "lei",
        "name_field": "company_name",
        "country_field": "domicile",
    },
    {
        "container": "controlled_structures",
        "is_collection": True,
        "entity_type": "ControlledStructure",
        "lei_field": "lei",
        "name_field": "issuer_name",
        "country_field": "",
    },
]


# ── Core enrichment logic ────────────────────────────────────────────

def _enrich_single_entity(
    entity: SourceEntity,
    entity_type: str,
    entity_index: int,
    lei_field: str,
    name_field: str,
    country_field: str,
    store: ReferenceStore,
) -> EnrichmentAction:
    """Attempt LEI enrichment on a single entity.

    Returns an EnrichmentAction documenting what happened.
    """
    # Get current values
    current_lei = entity.get(lei_field, "") or ""
    entity_name = entity.get(name_field, "") or ""
    country = entity.get(country_field, "") if country_field else ""

    # If LEI already present and valid → skip
    if current_lei and current_lei.strip():
        is_valid, _ = validate_lei_format(current_lei.strip())
        if is_valid:
            return EnrichmentAction(
                entity_type=entity_type,
                entity_index=entity_index,
                lei_field=lei_field,
                name_field=name_field,
                entity_name=entity_name,
                status=EnrichmentStatus.SKIPPED,
                original_lei=current_lei.strip(),
                message=f"LEI already present: {current_lei.strip()}",
            )

    # If no name to search by → no match possible
    if not entity_name or not entity_name.strip():
        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name="",
            status=EnrichmentStatus.NO_MATCH,
            message=f"No entity name in field '{name_field}' — cannot search GLEIF",
        )

    # Normalize and search
    normalized = normalize_entity_name(entity_name)
    if not normalized:
        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name=entity_name,
            status=EnrichmentStatus.NO_MATCH,
            normalized_name=normalized,
            message=f"Entity name '{entity_name}' normalizes to empty string",
        )

    try:
        matches = store.search_lei_by_normalized_name(
            normalized, country=country, limit=10,
        )
    except Exception as e:
        logger.error("GLEIF lookup failed for '%s': %s", entity_name, e)
        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name=entity_name,
            status=EnrichmentStatus.ERROR,
            normalized_name=normalized,
            message=f"GLEIF lookup error: {e}",
        )

    # Build candidate list for logging/UI
    candidates = [
        {
            "lei": m.lei,
            "legal_name": m.legal_name,
            "country": m.country,
            "entity_status": m.entity_status,
        }
        for m in matches
    ]

    if len(matches) == 0:
        # ── NO MATCH ────────────────────────────────────────────
        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name=entity_name,
            status=EnrichmentStatus.NO_MATCH,
            normalized_name=normalized,
            candidates=[],
            message=(f"No GLEIF match for '{entity_name}' "
                     f"(normalized: '{normalized}'). "
                     f"Manual LEI assignment required."),
        )

    elif len(matches) == 1:
        # ── SINGLE MATCH → AUTO-ENRICH ─────────────────────────
        best = matches[0]
        enriched_lei = best.lei

        # Write the LEI into the entity with DERIVED priority
        entity.set(
            lei_field,
            enriched_lei,
            source="lei_enrichment",
            priority=SourcePriority.DERIVED,
            confidence=1.0,
            note=(f"Auto-enriched from GLEIF: '{best.legal_name}' "
                  f"(LEI: {enriched_lei}, country={best.country})"),
        )

        logger.info(
            "ENRICHED %s[%d].%s: '%s' → %s (%s, %s)",
            entity_type, entity_index, lei_field,
            entity_name, enriched_lei, best.legal_name, best.country,
        )

        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name=entity_name,
            status=EnrichmentStatus.ENRICHED,
            enriched_lei=enriched_lei,
            candidates=candidates,
            normalized_name=normalized,
            message=(f"Auto-enriched: '{entity_name}' → "
                     f"{enriched_lei} ({best.legal_name}, {best.country})"),
        )

    else:
        # ── MULTIPLE MATCHES → PENDING USER CHOICE ─────────────
        logger.info(
            "PENDING %s[%d].%s: '%s' → %d candidates",
            entity_type, entity_index, lei_field,
            entity_name, len(matches),
        )

        return EnrichmentAction(
            entity_type=entity_type,
            entity_index=entity_index,
            lei_field=lei_field,
            name_field=name_field,
            entity_name=entity_name,
            status=EnrichmentStatus.PENDING_USER_CHOICE,
            candidates=candidates,
            normalized_name=normalized,
            message=(f"Multiple GLEIF matches for '{entity_name}' "
                     f"(normalized: '{normalized}'): "
                     f"{len(matches)} candidates. User must choose."),
        )


def enrich_lei_fields(
    canonical: SourceCanonical,
    store: ReferenceStore,
) -> EnrichmentLog:
    """Enrich all empty LEI fields in a SourceCanonical from the GLEIF cache.

    Iterates through every LEI-bearing entity defined in LEI_FIELD_MAP.
    For scalar entities (manager, fund_static): checks one instance.
    For collection entities (counterparties, positions, etc.): checks each item.

    Args:
        canonical: The SourceCanonical to enrich (modified in-place)
        store: ReferenceStore with GLEIF cache

    Returns:
        EnrichmentLog documenting every action taken
    """
    log = EnrichmentLog()

    for mapping in LEI_FIELD_MAP:
        container_name = mapping["container"]
        is_collection = mapping["is_collection"]
        entity_type = mapping["entity_type"]
        lei_field = mapping["lei_field"]
        name_field = mapping["name_field"]
        country_field = mapping["country_field"]

        if is_collection:
            entities = getattr(canonical, container_name, [])
            for idx, entity in enumerate(entities):
                action = _enrich_single_entity(
                    entity, entity_type, idx,
                    lei_field, name_field, country_field, store,
                )
                log.actions.append(action)
        else:
            entity = getattr(canonical, container_name, None)
            if entity is not None:
                action = _enrich_single_entity(
                    entity, entity_type, 0,
                    lei_field, name_field, country_field, store,
                )
                log.actions.append(action)

    log.completed_at = datetime.now(timezone.utc)
    logger.info(log.summary())
    return log


def apply_user_choice(
    canonical: SourceCanonical,
    action: EnrichmentAction,
    chosen_lei: str,
) -> None:
    """Apply a user's LEI choice for a PENDING_USER_CHOICE action.

    Called when the review UI presents multi-match candidates and the
    user selects one. Writes the chosen LEI with MANUALLY_OVERRIDDEN
    priority (highest), since the user has explicitly confirmed it.

    Args:
        canonical: The SourceCanonical to update
        action: The EnrichmentAction with PENDING_USER_CHOICE status
        chosen_lei: The LEI the user selected from the candidates
    """
    mapping = next(
        (m for m in LEI_FIELD_MAP if m["entity_type"] == action.entity_type),
        None,
    )
    if not mapping:
        raise ValueError(f"Unknown entity type: {action.entity_type}")

    container_name = mapping["container"]

    if mapping["is_collection"]:
        entities = getattr(canonical, container_name, [])
        if action.entity_index < len(entities):
            entity = entities[action.entity_index]
        else:
            raise IndexError(
                f"{action.entity_type}[{action.entity_index}] out of range "
                f"(collection has {len(entities)} items)"
            )
    else:
        entity = getattr(canonical, container_name)

    # Find the chosen candidate's legal name for the note
    candidate_name = ""
    for c in action.candidates:
        if c["lei"] == chosen_lei:
            candidate_name = c["legal_name"]
            break

    entity.set(
        action.lei_field,
        chosen_lei,
        source="lei_enrichment_user_choice",
        priority=SourcePriority.MANUALLY_OVERRIDDEN,
        confidence=1.0,
        note=(f"User selected from {len(action.candidates)} candidates: "
              f"'{candidate_name}' (LEI: {chosen_lei})"),
    )

    # Update the action record
    action.status = EnrichmentStatus.ENRICHED
    action.enriched_lei = chosen_lei
    action.message = (
        f"User chose: '{candidate_name}' ({chosen_lei}) "
        f"from {len(action.candidates)} candidates"
    )

    logger.info(
        "USER CHOICE %s[%d].%s: user selected %s (%s)",
        action.entity_type, action.entity_index, action.lei_field,
        chosen_lei, candidate_name,
    )
