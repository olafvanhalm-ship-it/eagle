"""Pydantic request models for Eagle API (SC-001 input validation)."""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class FieldEditRequest(BaseModel):
    """Edit a report-level entity field."""
    field_id: str = Field(..., description="ESMA question number")
    value: Any = Field(..., description="New field value")
    report_type: str = Field("AIFM", description="Report type: AIFM or AIF")
    fund_index: int = Field(0, description="Fund index (0 for AIFM, 0-N for AIF)")
    note: Optional[str] = Field(None, description="Optional edit note")


class GroupCellEditRequest(BaseModel):
    """Edit a single cell in a repeating group table."""
    group_name: str = Field(..., description="Programmatic group name, e.g. aifm_principal_markets")
    row_index: int = Field(..., description="0-based row index within the group")
    column_id: str = Field(..., description="Column key (field_id or synthetic key)")
    value: Any = Field(..., description="New cell value")
    report_type: str = Field("AIFM", description="Report type: AIFM or AIF")
    fund_index: int = Field(0, description="Fund index (0 for AIFM, 0-N for AIF)")
    note: Optional[str] = Field(None, description="Optional edit note")


class SourceEntityEditRequest(BaseModel):
    """Edit a source entity field (e.g. position market_value)."""
    field: str = Field(..., description="Entity field name")
    value: Any = Field(..., description="New field value")
    note: Optional[str] = Field(None, description="Optional edit note")


class SourceEntityAddRequest(BaseModel):
    """Add a new row to a source entity collection."""
    values: dict[str, Any] = Field(default_factory=dict, description="Field name → value pairs")
    fund_index: int = Field(0, description="Fund index (0 for AIFM-level)")


class SourceEntityDeleteRequest(BaseModel):
    """Delete a row from a source entity collection."""
    index: int = Field(..., description="0-based index of the item to delete")
