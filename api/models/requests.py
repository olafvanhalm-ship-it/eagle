"""Pydantic request models for Eagle API (SC-001 input validation)."""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class FieldEditRequest(BaseModel):
    """Edit a report-level entity field."""
    field_id: str = Field(..., description="ESMA question number")
    value: Any = Field(..., description="New field value")
    note: Optional[str] = Field(None, description="Optional edit note")


class SourceEntityEditRequest(BaseModel):
    """Edit a source entity field (e.g. position market_value)."""
    field: str = Field(..., description="Entity field name")
    value: Any = Field(..., description="New field value")
    note: Optional[str] = Field(None, description="Optional edit note")


class SourceEntityAddRequest(BaseModel):
    """Add a new row to a source entity collection."""
    values: dict[str, Any] = Field(default_factory=dict, description="Field name → value pairs")


class SourceEntityDeleteRequest(BaseModel):
    """Delete a row from a source entity collection."""
    index: int = Field(..., description="0-based index of the item to delete")
