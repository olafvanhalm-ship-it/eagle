"""Eagle Report Store — Persistence layer for review sessions, reports, and edits.

Dual-backend: SQLite for development/testing, PostgreSQL for production.
Uses SQLAlchemy ORM per SC-002 (no raw SQL injection risk).

Usage:
    store = ReportStore()  # auto-detects backend from DATABASE_URL env var
    store.save_session(session)
    session = store.get_session(session_id)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text, Boolean,
    ForeignKey, Index, event,
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, relationship, Session as DBSession,
)

log = logging.getLogger(__name__)

Base = declarative_base()


# ============================================================================
# ORM Models
# ============================================================================

class ReviewSessionRow(Base):
    __tablename__ = "review_sessions"

    session_id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    uploaded_at = Column(String, nullable=False)
    aifm_name = Column(String)
    filing_type = Column(String)
    template_type = Column(String)
    reporting_period = Column(String)
    reporting_member_state = Column(String)
    num_aifs = Column(Integer)
    source_canonical = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="DRAFT")
    product_id = Column(String, nullable=False, default="AIFMD_ANNEX_IV")
    updated_at = Column(String, nullable=False)

    reports = relationship("ReviewReportRow", back_populates="session", cascade="all, delete-orphan")
    edits = relationship("ReviewEditRow", back_populates="session", cascade="all, delete-orphan")
    validation_runs = relationship("ReviewValidationRunRow", back_populates="session", cascade="all, delete-orphan")


class ReviewReportRow(Base):
    __tablename__ = "review_reports"

    report_id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("review_sessions.session_id"), nullable=False)
    report_type = Column(String, nullable=False)
    entity_name = Column(String)
    entity_index = Column(Integer)
    nca_codes = Column(String)  # JSON array
    fields_json = Column(Text, nullable=False, default="{}")
    groups_json = Column(Text, nullable=False, default="{}")
    history_json = Column(Text, default="{}")
    completeness = Column(Float)
    field_count = Column(Integer)
    filled_count = Column(Integer)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    session = relationship("ReviewSessionRow", back_populates="reports")


class ReviewEditRow(Base):
    __tablename__ = "review_edits"

    edit_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("review_sessions.session_id"), nullable=False)
    report_id = Column(String)
    edit_type = Column(String, nullable=False)
    target = Column(String, nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    cascaded_fields = Column(Text)  # JSON array
    edited_at = Column(String, nullable=False)

    session = relationship("ReviewSessionRow", back_populates="edits")


class ReviewValidationRunRow(Base):
    __tablename__ = "review_validation_runs"

    run_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("review_sessions.session_id"), nullable=False)
    report_id = Column(String)
    xsd_valid = Column(Integer)
    dqf_pass = Column(Integer)
    dqf_fail = Column(Integer)
    findings_json = Column(Text)
    has_critical = Column(Integer, default=0)
    run_at = Column(String, nullable=False)

    session = relationship("ReviewSessionRow", back_populates="validation_runs")


# ============================================================================
# Data Transfer Objects
# ============================================================================

@dataclass
class ReviewSession:
    """In-memory representation of a review session."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    uploaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    aifm_name: str = ""
    filing_type: str = "INIT"
    template_type: str = "FULL"
    reporting_period: str = ""
    reporting_member_state: str = ""
    num_aifs: int = 0
    source_canonical: dict = field(default_factory=dict)
    status: str = "DRAFT"
    product_id: str = "AIFMD_ANNEX_IV"
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReviewReport:
    """In-memory representation of a report (AIFM or AIF)."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    report_type: str = "AIF"
    entity_name: str = ""
    entity_index: int = 0
    nca_codes: list[str] = field(default_factory=list)
    fields_json: dict = field(default_factory=dict)
    groups_json: dict = field(default_factory=dict)
    history_json: dict = field(default_factory=dict)
    completeness: float = 0.0
    field_count: int = 0
    filled_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReviewEdit:
    """In-memory representation of an edit log entry."""
    edit_id: Optional[int] = None
    session_id: str = ""
    report_id: Optional[str] = None
    edit_type: str = "field"
    target: str = ""
    old_value: Any = None
    new_value: Any = None
    cascaded_fields: list[str] = field(default_factory=list)
    edited_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReviewValidationRun:
    """In-memory representation of a validation run."""
    run_id: Optional[int] = None
    session_id: str = ""
    report_id: Optional[str] = None
    xsd_valid: bool = True
    dqf_pass: int = 0
    dqf_fail: int = 0
    findings_json: list[dict] = field(default_factory=list)
    has_critical: bool = False
    run_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================================
# Report Store
# ============================================================================

class ReportStore:
    """Dual-backend persistence for Eagle review sessions.

    Auto-detects database from DATABASE_URL environment variable:
    - PostgreSQL: postgresql://user:pass@host:port/dbname
    - SQLite (default): sqlite:///path/to/eagle_review.db
    """

    def __init__(self, database_url: Optional[str] = None):
        if database_url is None:
            database_url = os.environ.get("DATABASE_URL", "")

        if not database_url:
            # Default to SQLite. Try Application/persistence/ first,
            # fall back to temp dir if that's not writable (e.g. network drive).
            db_dir = Path(__file__).resolve().parent
            db_path = db_dir / "eagle_review.db"
            try:
                db_path.touch(exist_ok=True)
            except OSError:
                import tempfile
                db_path = Path(tempfile.gettempdir()) / "eagle_review.db"
            database_url = f"sqlite:///{db_path}"

        self._database_url = database_url
        self._is_sqlite = database_url.startswith("sqlite")

        engine_kwargs = {}
        if self._is_sqlite:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        self._engine = create_engine(database_url, echo=False, **engine_kwargs)

        # Enable WAL mode for SQLite (better concurrent reads)
        if self._is_sqlite:
            @event.listens_for(self._engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self._SessionFactory = sessionmaker(bind=self._engine)
        Base.metadata.create_all(self._engine)
        log.info("ReportStore initialized: %s", "PostgreSQL" if not self._is_sqlite else "SQLite")

    def _db(self) -> DBSession:
        return self._SessionFactory()

    # --- Session CRUD ---

    def save_session(self, session: ReviewSession) -> str:
        """Insert or update a review session."""
        with self._db() as db:
            row = db.get(ReviewSessionRow, session.session_id)
            now = datetime.now(timezone.utc).isoformat()
            if row is None:
                row = ReviewSessionRow(
                    session_id=session.session_id,
                    filename=session.filename,
                    uploaded_at=session.uploaded_at,
                    aifm_name=session.aifm_name,
                    filing_type=session.filing_type,
                    template_type=session.template_type,
                    reporting_period=session.reporting_period,
                    reporting_member_state=session.reporting_member_state,
                    num_aifs=session.num_aifs,
                    source_canonical=json.dumps(session.source_canonical),
                    status=session.status,
                    product_id=session.product_id,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.aifm_name = session.aifm_name
                row.filing_type = session.filing_type
                row.template_type = session.template_type
                row.reporting_period = session.reporting_period
                row.reporting_member_state = session.reporting_member_state
                row.num_aifs = session.num_aifs
                row.source_canonical = json.dumps(session.source_canonical)
                row.status = session.status
                row.updated_at = now
            db.commit()
        return session.session_id

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        """Retrieve a review session by ID."""
        with self._db() as db:
            row = db.get(ReviewSessionRow, session_id)
            if row is None:
                return None
            return ReviewSession(
                session_id=row.session_id,
                filename=row.filename,
                uploaded_at=row.uploaded_at,
                aifm_name=row.aifm_name or "",
                filing_type=row.filing_type or "INIT",
                template_type=row.template_type or "FULL",
                reporting_period=row.reporting_period or "",
                reporting_member_state=row.reporting_member_state or "",
                num_aifs=row.num_aifs or 0,
                source_canonical=json.loads(row.source_canonical) if row.source_canonical else {},
                status=row.status or "DRAFT",
                product_id=row.product_id or "AIFMD_ANNEX_IV",
                updated_at=row.updated_at or "",
            )

    def get_active_session(self) -> Optional[ReviewSession]:
        """Get the most recent non-archived session."""
        with self._db() as db:
            row = (
                db.query(ReviewSessionRow)
                .filter(ReviewSessionRow.status != "ARCHIVED")
                .order_by(ReviewSessionRow.uploaded_at.desc())
                .first()
            )
            if row is None:
                return None
            return self.get_session(row.session_id)

    def archive_active_sessions(self) -> int:
        """Archive all non-archived sessions. Returns count archived."""
        with self._db() as db:
            count = (
                db.query(ReviewSessionRow)
                .filter(ReviewSessionRow.status != "ARCHIVED")
                .update({"status": "ARCHIVED", "updated_at": datetime.now(timezone.utc).isoformat()})
            )
            db.commit()
            return count

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """List sessions (most recent first), returning summary dicts."""
        with self._db() as db:
            rows = (
                db.query(ReviewSessionRow)
                .order_by(ReviewSessionRow.uploaded_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "session_id": r.session_id,
                    "filename": r.filename,
                    "uploaded_at": r.uploaded_at,
                    "aifm_name": r.aifm_name,
                    "status": r.status,
                    "num_aifs": r.num_aifs,
                    "product_id": r.product_id,
                }
                for r in rows
            ]

    # --- Report CRUD ---

    def save_report(self, report: ReviewReport) -> str:
        """Insert or update a report."""
        with self._db() as db:
            row = db.get(ReviewReportRow, report.report_id)
            now = datetime.now(timezone.utc).isoformat()
            if row is None:
                row = ReviewReportRow(
                    report_id=report.report_id,
                    session_id=report.session_id,
                    report_type=report.report_type,
                    entity_name=report.entity_name,
                    entity_index=report.entity_index,
                    nca_codes=json.dumps(report.nca_codes),
                    fields_json=json.dumps(report.fields_json),
                    groups_json=json.dumps(report.groups_json),
                    history_json=json.dumps(report.history_json),
                    completeness=report.completeness,
                    field_count=report.field_count,
                    filled_count=report.filled_count,
                    created_at=report.created_at,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.fields_json = json.dumps(report.fields_json)
                row.groups_json = json.dumps(report.groups_json)
                row.history_json = json.dumps(report.history_json)
                row.completeness = report.completeness
                row.field_count = report.field_count
                row.filled_count = report.filled_count
                row.nca_codes = json.dumps(report.nca_codes)
                row.updated_at = now
            db.commit()
        return report.report_id

    def get_report(self, report_id: str) -> Optional[ReviewReport]:
        """Retrieve a single report by ID."""
        with self._db() as db:
            row = db.get(ReviewReportRow, report_id)
            if row is None:
                return None
            return self._row_to_report(row)

    def get_reports_for_session(self, session_id: str) -> list[ReviewReport]:
        """Get all reports for a session, ordered by type (AIFM first) and index."""
        with self._db() as db:
            rows = (
                db.query(ReviewReportRow)
                .filter(ReviewReportRow.session_id == session_id)
                .order_by(ReviewReportRow.report_type, ReviewReportRow.entity_index)
                .all()
            )
            return [self._row_to_report(r) for r in rows]

    def get_report_by_type_and_index(
        self, session_id: str, report_type: str, entity_index: int = 0
    ) -> Optional[ReviewReport]:
        """Get a specific report by type and index."""
        with self._db() as db:
            row = (
                db.query(ReviewReportRow)
                .filter(
                    ReviewReportRow.session_id == session_id,
                    ReviewReportRow.report_type == report_type,
                    ReviewReportRow.entity_index == entity_index,
                )
                .first()
            )
            if row is None:
                return None
            return self._row_to_report(row)

    def _row_to_report(self, row: ReviewReportRow) -> ReviewReport:
        return ReviewReport(
            report_id=row.report_id,
            session_id=row.session_id,
            report_type=row.report_type,
            entity_name=row.entity_name or "",
            entity_index=row.entity_index or 0,
            nca_codes=json.loads(row.nca_codes) if row.nca_codes else [],
            fields_json=json.loads(row.fields_json) if row.fields_json else {},
            groups_json=json.loads(row.groups_json) if row.groups_json else {},
            history_json=json.loads(row.history_json) if row.history_json else {},
            completeness=row.completeness or 0.0,
            field_count=row.field_count or 0,
            filled_count=row.filled_count or 0,
            created_at=row.created_at or "",
            updated_at=row.updated_at or "",
        )

    # --- Edit Log ---

    def log_edit(self, edit: ReviewEdit) -> int:
        """Record an edit in the log. Returns the edit_id."""
        with self._db() as db:
            row = ReviewEditRow(
                session_id=edit.session_id,
                report_id=edit.report_id,
                edit_type=edit.edit_type,
                target=edit.target,
                old_value=json.dumps(edit.old_value),
                new_value=json.dumps(edit.new_value),
                cascaded_fields=json.dumps(edit.cascaded_fields),
                edited_at=edit.edited_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.edit_id

    def get_edits(self, session_id: str) -> list[ReviewEdit]:
        """Get all edits for a session, oldest first."""
        with self._db() as db:
            rows = (
                db.query(ReviewEditRow)
                .filter(ReviewEditRow.session_id == session_id)
                .order_by(ReviewEditRow.edit_id)
                .all()
            )
            return [
                ReviewEdit(
                    edit_id=r.edit_id,
                    session_id=r.session_id,
                    report_id=r.report_id,
                    edit_type=r.edit_type,
                    target=r.target,
                    old_value=json.loads(r.old_value) if r.old_value else None,
                    new_value=json.loads(r.new_value) if r.new_value else None,
                    cascaded_fields=json.loads(r.cascaded_fields) if r.cascaded_fields else [],
                    edited_at=r.edited_at,
                )
                for r in rows
            ]

    def delete_last_edit(self, session_id: str) -> Optional[ReviewEdit]:
        """Delete and return the most recent edit for undo. Returns None if no edits."""
        with self._db() as db:
            row = (
                db.query(ReviewEditRow)
                .filter(ReviewEditRow.session_id == session_id)
                .order_by(ReviewEditRow.edit_id.desc())
                .first()
            )
            if row is None:
                return None
            edit = ReviewEdit(
                edit_id=row.edit_id,
                session_id=row.session_id,
                report_id=row.report_id,
                edit_type=row.edit_type,
                target=row.target,
                old_value=json.loads(row.old_value) if row.old_value else None,
                new_value=json.loads(row.new_value) if row.new_value else None,
                cascaded_fields=json.loads(row.cascaded_fields) if row.cascaded_fields else [],
                edited_at=row.edited_at,
            )
            db.delete(row)
            db.commit()
            return edit

    # --- Validation Runs ---

    def save_validation_run(self, run: ReviewValidationRun) -> int:
        """Save a validation run. Returns the run_id."""
        with self._db() as db:
            row = ReviewValidationRunRow(
                session_id=run.session_id,
                report_id=run.report_id,
                xsd_valid=1 if run.xsd_valid else 0,
                dqf_pass=run.dqf_pass,
                dqf_fail=run.dqf_fail,
                findings_json=json.dumps(run.findings_json),
                has_critical=1 if run.has_critical else 0,
                run_at=run.run_at,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.run_id

    def get_latest_validation(self, session_id: str) -> Optional[ReviewValidationRun]:
        """Get the most recent validation run for a session."""
        with self._db() as db:
            row = (
                db.query(ReviewValidationRunRow)
                .filter(ReviewValidationRunRow.session_id == session_id)
                .order_by(ReviewValidationRunRow.run_id.desc())
                .first()
            )
            if row is None:
                return None
            return ReviewValidationRun(
                run_id=row.run_id,
                session_id=row.session_id,
                report_id=row.report_id,
                xsd_valid=bool(row.xsd_valid),
                dqf_pass=row.dqf_pass or 0,
                dqf_fail=row.dqf_fail or 0,
                findings_json=json.loads(row.findings_json) if row.findings_json else [],
                has_critical=bool(row.has_critical),
                run_at=row.run_at or "",
            )
