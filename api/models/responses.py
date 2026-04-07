"""Pydantic response models for Eagle API (SC-001 input validation)."""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class SessionSummary(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    aifm_name: str
    status: str
    num_aifs: int
    product_id: str


class SessionDetail(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    aifm_name: str
    filing_type: str
    template_type: str
    reporting_period: str
    reporting_member_state: str
    num_aifs: int
    status: str
    product_id: str
    reports: list[ReportSummary]


class ReportSummary(BaseModel):
    report_id: str
    report_type: str
    entity_name: str
    entity_index: int
    nca_codes: list[str]
    completeness: float
    field_count: int
    filled_count: int


class FieldValueResponse(BaseModel):
    value: Any
    source: str
    priority: str
    confidence: float
    timestamp: str
    source_ref: Optional[str] = None
    note: Optional[str] = None


class ReportFieldResponse(BaseModel):
    field_id: str
    field_name: str
    section: str
    value: Any
    source: str
    priority: str
    data_type: str
    obligation: str
    format: str
    allowed_values_ref: Optional[str] = None
    xsd_element: str
    repetition: str
    editable: bool
    category: str  # entity, composite, report
    nca_deviations: dict[str, Any] = {}  # CC → value
    validation: Optional[FieldValidationResponse] = None


class FieldValidationFinding(BaseModel):
    """Single validation finding for a field."""
    rule_id: str = ""
    status: str = "PASS"  # PASS, FAIL, WARNING
    severity: str = "INFO"  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    message: str = ""
    fix_suggestion: str = ""


class FieldValidationResponse(BaseModel):
    status: str  # Aggregate: FAIL if any FAIL, WARNING if any WARNING, else PASS
    findings: list[FieldValidationFinding] = []
    # Legacy single-finding fields (populated from worst finding)
    rule_id: Optional[str] = None
    message: Optional[str] = None
    fix_suggestion: Optional[str] = None
    severity: Optional[str] = None


class ReportDetailResponse(BaseModel):
    report_id: str
    session_id: str
    report_type: str
    entity_name: str
    entity_index: int
    nca_codes: list[str]
    completeness: float
    field_count: int
    filled_count: int
    sections: dict[str, list[ReportFieldResponse]]
    groups: dict[str, list[dict[str, Any]]]
    group_columns: dict[str, dict[str, str]] = {}  # group_name → {field_id: field_name}
    empty_section_count: int
    validation_run: bool = False
    no_reporting: bool = False


class SourceEntityResponse(BaseModel):
    entity_type: str
    items: list[dict[str, Any]]
    field_names: list[str]


class SourceDataResponse(BaseModel):
    manager: dict[str, Any]
    fund_static: dict[str, Any]
    fund_dynamic: dict[str, Any]
    entities: dict[str, SourceEntityResponse]


class EditResultResponse(BaseModel):
    edit_id: int
    updated_fields: list[str]
    field_snapshots: dict[str, dict[str, Any]]


class DiffEntry(BaseModel):
    edit_id: int
    edit_type: str
    target: str
    old_value: Any
    new_value: Any
    cascaded_fields: list[str]
    edited_at: str


class DiffResponse(BaseModel):
    total_direct_edits: int
    total_cascaded: int
    entries: list[DiffEntry]


class ValidationResultResponse(BaseModel):
    run_id: int
    xsd_valid: bool
    dqf_pass: int
    dqf_fail: int
    has_critical: bool
    findings: list[dict[str, Any]]
    field_results: dict[str, FieldValidationResponse]


class FieldDefResponse(BaseModel):
    field_id: str
    field_name: str
    report_type: str
    section: str
    data_type: str
    format: str
    obligation: str
    mandatory: bool
    repetition: str
    xsd_element: str
    severity: str
    allowed_values_ref: Optional[str] = None


class UploadResponse(BaseModel):
    status: str
    session_id: str
    adapter: dict[str, Any]
    generated: dict[str, int]
    validation: Optional[dict[str, Any]] = None
    error: Optional[str] = None


# Needed for forward reference resolution
SessionDetail.model_rebuild()
