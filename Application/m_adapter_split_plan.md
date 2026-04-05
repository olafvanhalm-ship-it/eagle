# Eagle Ingestion-to-Submission Pipeline — Design Plan

**Date:** 2026-04-02
**Author:** Eagle Architecture
**Status:** Proposal — v2
**Scope:** Decompose the current `m_adapter.py` monolith into a full pipeline architecture supporting multiple input sources, interactive validation, human review, and deferred XML packaging — aligned with `eagle_software_architecture.md` v1.4 (L1–L7).

---

## 1. Vision

Today the M adapter is a single Python file (~3,400 lines) that reads an Excel template, derives values, and immediately produces XML. The future Eagle pipeline is fundamentally different:

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                        MULTIPLE INPUT SOURCES                            │
 │                                                                          │
 │  M Excel       ESMA Excel     Old XML        Annual Report    Holdings   │
 │  Template      Template       (re-import)    (unstructured)   Report     │
 │  ────┬───      ────┬───       ────┬───       ────┬────        ────┬───  │
 │      │              │              │              │                │      │
 │      ▼              ▼              ▼              ▼                ▼      │
 │  ┌────────┐   ┌────────┐    ┌────────┐    ┌─────────┐     ┌────────┐   │
 │  │L1B     │   │L1B     │    │L1B     │    │L2 AI    │     │L2 AI   │   │
 │  │M Parse │   │ESMA    │    │XML     │    │Extract  │     │Extract │   │
 │  │        │   │Parse   │    │Import  │    │(Claude) │     │(Claude)│   │
 │  └───┬────┘   └───┬────┘    └───┬────┘    └───┬─────┘     └───┬────┘   │
 │      │             │             │             │                │        │
 │      └──────┬──────┴─────┬───────┴─────┬───────┘                │        │
 │             │            │             │                        │        │
 │             ▼            ▼             ▼                        │        │
 │  ┌──────────────────────────────────────────────────────────────┘        │
 │  │                                                                       │
 │  ▼                                                                       │
 │  ┌─────────────────────────────────────────────────────────┐             │
 │  │           CANONICAL RECORD (PostgreSQL / JSONB)          │             │
 │  │                                                          │             │
 │  │  • Merged from multiple sources                          │             │
 │  │  • Per-field provenance (IMPORTED / AI_PROPOSED / etc.)  │             │
 │  │  • Version-tracked, immutable audit trail                │             │
 │  └────────────────────────┬────────────────────────────────┘             │
 │                           │                                              │
 │               ┌───────────▼──────────────┐                               │
 │               │  DERIVATION ENGINE (L2b)  │                               │
 │               │  FX · AuM · NAV · Leverage│                               │
 │               │  Geo focus · Aggregation  │                               │
 │               └───────────┬──────────────┘                               │
 │                           │                                              │
 │               ┌───────────▼──────────────┐                               │
 │               │   VALIDATION (L3 + L4)    │  ◄──── Rules YAML            │
 │               │   Per-field CAF/CAM/PASS  │  ◄──── NCA Overrides         │
 │               │   Cross-record checks     │  ◄──── DQEF checks           │
 │               └───────────┬──────────────┘                               │
 │                           │                                              │
 │                    ┌──────┴──────┐                                        │
 │                    │             │                                        │
 │              CAF errors?    All PASS                                      │
 │                    │             │                                        │
 │                    ▼             │                                        │
 │  ┌──────────────────────┐       │                                        │
 │  │ CLIENT REVIEW SCREEN │       │                                        │
 │  │                      │       │                                        │
 │  │ • View full report   │       │                                        │
 │  │ • Edit fields        │───────┤  (re-validates after each edit)        │
 │  │ • Add extra source   │       │                                        │
 │  │ • Override with reason│      │                                        │
 │  └──────────────────────┘       │                                        │
 │                                 │                                        │
 │               ┌─────────────────▼──────────────┐                         │
 │               │    APPROVAL GATE (L5)           │                         │
 │               │    COMPLIANCE_REVIEWER approves │                         │
 │               │    Non-bypassable               │                         │
 │               └─────────────────┬──────────────┘                         │
 │                                 │                                        │
 │               ┌─────────────────▼──────────────┐                         │
 │               │    XML PACKAGING (L6)           │                         │
 │               │    Generate ONLY after approval │                         │
 │               │    NCA-specific bundling         │                         │
 │               └─────────────────┬──────────────┘                         │
 │                                 │                                        │
 │               ┌─────────────────▼──────────────┐                         │
 │               │    DELIVERY (L7)                │                         │
 │               │    API · Robot · S3 · SFTP      │                         │
 │               └────────────────────────────────┘                         │
 └──────────────────────────────────────────────────────────────────────────┘
```

**Key design shifts from the current M adapter:**

1. **Canonical-first** — Data is written to `canonical_records` (JSONB) immediately after parsing. All subsequent steps operate on the canonical record, not on the raw file.
2. **Multi-source merge** — Multiple input files can contribute to the same canonical record. Conflicts resolved by provenance priority and user confirmation.
3. **Deferred XML generation** — XML is only produced after approval at L5. The current approach of generating XML directly from parsed data is inverted.
4. **Interactive validation loop** — When validation finds errors, the client can correct data in the review screen, which triggers re-derivation and re-validation. This is a loop, not a one-shot pipeline.
5. **AI as a source, not a step** — AI extraction (L2) is just another input source alongside structured templates. Its output carries `AI_PROPOSED` provenance and requires human confirmation for LOW-confidence fields.

---

## 2. Module Architecture

### 2.1 Target directory structure

```
eagle-backend/app/products/aifmd/
│
├── ingestion/                          # L1 — Channel routing
│   ├── __init__.py
│   ├── channel_router.py               # Detects format, routes to correct adapter
│   └── format_detector.py              # 3-factor detection (sheet names, headers, version cells)
│
├── adapters/                           # L1B — One adapter per input format
│   ├── __init__.py
│   ├── adapter_registry.py             # Pluggable registry loaded from config
│   ├── base_adapter.py                 # LegacyAdapter protocol
│   │
│   ├── m_adapter/                      # M template adapter (current scope)
│   │   ├── __init__.py
│   │   ├── parser.py                   # Excel/CSV reading, sheet classification
│   │   ├── template_detector.py        # LIGHT vs FULL detection
│   │   └── field_mapper.py             # M column names → canonical field paths
│   │
│   ├── esma_adapter/                   # ESMA Excel template (future)
│   │   ├── __init__.py
│   │   ├── parser.py
│   │   └── field_mapper.py
│   │
│   └── xml_reimport_adapter/           # Old XML report re-import (future)
│       ├── __init__.py
│       └── xml_parser.py
│
├── transformation/                     # L2 — AI + Deterministic derivation
│   ├── __init__.py
│   ├── ai_extraction.py               # Claude: unstructured → canonical (future)
│   ├── source_merger.py               # Combine fields from multiple sources
│   ├── derivation_engine.py           # Deterministic: FX, AuM, NAV, leverage
│   ├── fx_service.py                  # ECB rate fetching + caching
│   ├── aum_calculator.py              # AuM, NAV, leverage, unencumbered cash
│   ├── geo_focus.py                   # Geographic concentration
│   └── aggregation.py                 # Position aggregation by sub-asset, asset type
│
├── validation/                         # L3 + L4 — Rules + DQEF
│   ├── __init__.py
│   ├── validation_engine.py           # Deterministic rule engine (YAML-driven)
│   ├── dqef_engine.py                 # ESMA DQEF statistical checks
│   ├── cross_record_validator.py      # AuM consistency, LEI checks, fund count
│   └── validation_result.py           # Per-field CAF/CAM/PASS + DQ_WARNING
│
├── review/                             # L5 — Human review gate
│   ├── __init__.py
│   ├── review_gate.py                 # Approval logic, non-bypassable
│   ├── field_editor.py                # Apply user corrections → re-derive → re-validate
│   └── supplementary_source.py        # Accept additional input during review
│
├── packaging/                          # L6 — XML generation (ONLY after L5 approval)
│   ├── __init__.py
│   ├── xml_builder.py                 # Canonical record → AIFM/AIF XML
│   ├── fca_xml_builder.py             # FCA-specific XML deviations
│   ├── nca_packager.py                # NCA-specific bundling (gz, zip, naming)
│   └── xml_utils.py                   # Pretty-print, namespace helpers
│
├── submission/                         # L7 — Delivery channels
│   ├── __init__.py
│   ├── delivery_router.py             # Routes to correct delivery channel
│   └── channels/                      # Per-channel implementations
│       ├── direct_api.py
│       ├── robot_portal.py
│       ├── s3_delivery.py
│       ├── sftp_delivery.py
│       └── manual_download.py
│
├── models/                             # Canonical data model
│   ├── __init__.py
│   ├── canonical_record.py            # Pydantic model mapping to canonical_records table
│   ├── canonical_field.py             # Per-field provenance model
│   ├── parsed_template.py             # In-memory intermediate (pre-DB write)
│   └── record_types.py                # MRecord with alias resolution (shared across adapters)
│
├── config/                             # Runtime configuration (never hard-coded)
│   ├── validation_rules/
│   │   └── aifmd_annex_iv_validation_rules.yaml
│   ├── nca_overrides/
│   │   ├── nca_override_cssf.yaml
│   │   ├── nca_override_afm.yaml
│   │   └── nca_override_bafin.yaml
│   ├── packaging/
│   │   ├── cssf.yaml
│   │   ├── afm.yaml
│   │   └── bafin.yaml
│   ├── smart_defaults/
│   ├── m_column_schema_v1.yaml
│   └── prompts/                        # AI system prompts (version-controlled)
│
└── shared/                             # Shared utilities
    ├── __init__.py
    ├── constants.py                    # EEA, regions, strategies, asset types
    ├── reference_data.py               # Country→region, position→turnover mappings
    └── formatting.py                   # _str(), _int_round(), _float_val(), etc.
```

### 2.2 What each module does — and what it does NOT do

| Module | Responsibility | Does NOT |
|---|---|---|
| **ingestion/** | Receives raw bytes, detects format, routes to adapter | Parse field values, derive anything, validate |
| **adapters/m_adapter/** | Reads M Excel/CSV → produces `ParsedTemplate` with canonical field names | Calculate AuM, generate XML, validate, package |
| **transformation/** | Merges sources, derives FX/AuM/NAV/leverage, writes to `canonical_records` | Read raw files, generate XML, validate rules |
| **validation/** | Applies rules YAML + NCA overrides → per-field CAF/CAM/PASS | Modify data, generate XML, read raw files |
| **review/** | Presents data for client review, applies corrections, triggers re-validation | Generate XML (only after approval) |
| **packaging/** | Reads approved `canonical_records` → generates XML + NCA bundles | Read raw files, validate, derive values |
| **submission/** | Delivers packaged files to NCA via configured channel | Everything except delivery |

---

## 3. Data Flow — The Canonical Record as Central Hub

### 3.1 The key insight: canonical_records is the system of record

In the current M adapter, data flows linearly: `Excel → Python dicts → XML`. There is no persistent intermediate state.

In the target architecture, `canonical_records` (PostgreSQL JSONB) is the hub that all modules read from and write to:

```
                    ┌──────────────────────────────────┐
                    │     aifmd.canonical_records       │
                    │                                    │
    WRITE ─────────▶│  record_id    UUID                │◀───────── READ
    (adapters,      │  data         JSONB               │  (validation,
     derivation,    │  status       DRAFT → ... → ACCEPTED  packaging,
     user edits)    │  version      auto-increment      │   review screen)
                    │                                    │
                    └──────────────────────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │    aifmd.canonical_fields         │
                    │                                    │
                    │  field_path   "AIF.NAV.Amount"    │
                    │  provenance   IMPORTED / AI_PROPOSED│
                    │               / DERIVED / MANUALLY_ │
                    │                 OVERRIDDEN          │
                    │  ai_confidence HIGH / MEDIUM / LOW │
                    └──────────────────────────────────┘
```

### 3.2 Multi-source merge strategy

When multiple sources contribute to the same canonical record (e.g., M template provides positions, but an annual report provides strategy description via AI):

```python
class SourceMerger:
    """Merges fields from multiple sources into one canonical record."""

    PRIORITY_ORDER = [
        "MANUALLY_OVERRIDDEN",   # Always wins — user explicitly chose this
        "IMPORTED",              # Structured template (M, ESMA, XML)
        "DERIVED",               # Calculated by derivation engine
        "AI_PROPOSED",           # AI extraction — lowest priority
        "SMART_DEFAULT",         # System default — lowest of all
    ]

    def merge(
        self,
        existing: CanonicalRecord,
        new_fields: list[CanonicalField],
    ) -> MergeResult:
        """
        For each incoming field:
        - If field doesn't exist yet → insert
        - If field exists with lower priority → replace (log previous value)
        - If field exists with equal/higher priority → conflict (flag for user)
        """
        ...
```

### 3.3 The validation-correction loop

This is the interactive cycle that the current M adapter doesn't support:

```
         ┌──────────┐
         │  DRAFT   │ ◄─── Adapter writes canonical record
         └────┬─────┘
              │
              ▼
    ┌─────────────────┐
    │  derive()        │  Derivation engine enriches canonical record
    └────────┬────────┘
              │
              ▼
    ┌─────────────────┐
    │  validate()      │  Rules engine produces ValidationReport
    └────────┬────────┘
              │
        ┌─────┴─────┐
        │           │
    CAF errors   All PASS/CAM
        │           │
        ▼           ▼
┌──────────────┐ ┌──────────────┐
│ CAF_FAILED   │ │ REVIEW_      │
│              │ │ PENDING      │
│ Client sees: │ │              │
│ • Error list │ │ Client sees: │
│ • Edit form  │ │ • Full report│
│ • Upload more│ │ • Approve btn│
└──────┬───────┘ └──────┬───────┘
       │                │
       ▼                ▼
  User corrects     User approves
  field values      (COMPLIANCE_REVIEWER)
       │                │
       ▼                ▼
  ┌──────────┐    ┌──────────┐
  │ re-derive │    │ APPROVED │
  │ re-validate│   └────┬─────┘
  └─────┬─────┘        │
        │               ▼
        └───────▶  ┌──────────┐
                   │ package() │  XML generated here — NOT earlier
                   └────┬─────┘
                        │
                        ▼
                   ┌──────────┐
                   │ deliver() │
                   └──────────┘
```

**Key API for the correction loop:**

```python
class FieldEditor:
    """Handles user corrections during review, triggering re-validation."""

    async def update_field(
        self,
        record_id: UUID,
        field_path: str,
        new_value: Any,
        reason: str,               # Required for audit trail
        editor: User,              # Must be DATA_PREPARER or above
    ) -> EditResult:
        """
        1. Write new value to canonical_fields (provenance = MANUALLY_OVERRIDDEN)
        2. Store original value in override_record
        3. Mark any DERIVED fields that depend on this field as stale
        4. Trigger derivation_engine.re_derive(record_id, affected_fields)
        5. Trigger validation_engine.re_validate(record_id)
        6. Return updated ValidationReport
        """
        ...

    async def add_supplementary_source(
        self,
        record_id: UUID,
        source_file: bytes,
        source_type: str,          # "M_TEMPLATE", "ESMA_TEMPLATE", "ANNUAL_REPORT", etc.
    ) -> MergeResult:
        """
        1. Route file through ingestion → adapter (or AI extraction)
        2. Merge extracted fields into existing canonical record
        3. Re-derive + re-validate
        4. Return merge conflicts (if any) for user resolution
        """
        ...
```

---

## 4. Adapter Interface — Pluggable per Input Format

### 4.1 Base adapter protocol

Every input format implements the same interface, making new formats a config change (P6):

```python
class LegacyAdapter(Protocol):
    """L1B interface: raw file → canonical fields."""
    adapter_id: str          # "M_REGISTERED", "M_AUTHORISED", "ESMA_LEGACY", "XML_REIMPORT"
    version: str

    def detect(self, raw: bytes, metadata: dict) -> float:
        """Return confidence score 0.0–1.0 that this adapter handles the file."""
        ...

    def transform(self, raw: bytes, metadata: AdapterMetadata) -> list[CanonicalField]:
        """Extract all fields with canonical field paths and provenance."""
        ...

    def get_enrichment_calculations(self) -> list[str]:
        """List of derivation calculations this adapter's data requires."""
        ...
```

### 4.2 Adapter registry

```yaml
# config/adapter_registry.yaml
adapters:
  M_REGISTERED:
    class: adapters.m_adapter.MRegisteredAdapter
    version: "1.0"
    file_types: [".xlsx", ".xls", ".csv"]
    detection_priority: 10

  M_AUTHORISED:
    class: adapters.m_adapter.MAuthorisedAdapter
    version: "1.0"
    file_types: [".xlsx", ".xls", ".csv"]
    detection_priority: 10

  ESMA_LEGACY:
    class: adapters.esma_adapter.ESMALegacyAdapter
    version: "1.0"
    file_types: [".xlsx", ".xls"]
    detection_priority: 20

  XML_REIMPORT:
    class: adapters.xml_reimport_adapter.XMLReimportAdapter
    version: "1.0"
    file_types: [".xml"]
    detection_priority: 30

  AI_UNSTRUCTURED:
    class: transformation.ai_extraction.AIUnstructuredAdapter
    version: "1.0"
    file_types: [".pdf", ".docx", ".html"]
    detection_priority: 50
    requires_confirmation: true   # All AI fields need human confirmation
```

### 4.3 How the M adapter becomes one adapter among many

The current `m_adapter.py` maps to the target as follows:

| Current m_adapter.py section | Target location | Role |
|---|---|---|
| `MAdapter.__init__`, `_classify_sheet`, `_parse_sheet`, `_parse_csv` | `adapters/m_adapter/parser.py` | Read raw file, produce MRecord list |
| `MRecord`, alias resolution, `from_row()` | `models/record_types.py` | Shared record type (used by M + ESMA adapters) |
| `_detect_template_type` | `adapters/m_adapter/template_detector.py` | LIGHT vs FULL |
| Field name normalization | `adapters/m_adapter/field_mapper.py` | M column names → canonical field paths |
| `_fetch_ecb_fx_rate`, `_get_fx_rate` | `transformation/fx_service.py` | Shared FX service |
| `_calc_aum`, `_calc_nav`, `_calc_leverage`, etc. | `transformation/aum_calculator.py` | Shared derivation |
| `_geo_focus`, `_aggregate_by_*` | `transformation/geo_focus.py`, `aggregation.py` | Shared derivation |
| `generate_aifm_xml`, `generate_aif_xml`, all `_build_*` | `packaging/xml_builder.py` | L6 — only after approval |
| FCA-specific XML logic (`is_fca` branches) | `packaging/fca_xml_builder.py` | Separate builder |
| NCA bundling in `generate_all()` (gz, zip) | `packaging/nca_packager.py` | L6 |
| Constants, region maps, strategy maps | `shared/constants.py`, `shared/reference_data.py` | Shared |
| Formatting helpers | `shared/formatting.py` | Shared |

---

## 5. Packaging — XML Generation Only After Approval

This is the biggest conceptual change. Currently `generate_aifm_xml()` reads data from Python dicts that were just parsed. In the target, XML is generated from an **approved canonical record in the database**.

### 5.1 New XML builder interface

```python
class XMLBuilder:
    """L6: Generates AIFM/AIF XML from an approved canonical record."""

    def build_aifm_xml(
        self,
        record: CanonicalRecord,        # Loaded from DB — status = APPROVED
        nca_code: str,
        packaging_config: NCAPackagingConfig,
    ) -> bytes:
        """
        Reads all field values from record.data (JSONB).
        No file parsing. No derivation. No validation.
        Pure transformation: canonical data → XML structure.
        """
        ...

    def build_aif_xml(
        self,
        record: CanonicalRecord,
        nca_code: str,
        packaging_config: NCAPackagingConfig,
    ) -> bytes:
        ...
```

### 5.2 NCA-specific packaging stays config-driven

```python
class NCAPackager:
    """Wraps XML files per NCA requirements (compression, file naming)."""

    def package(
        self,
        xml_files: list[GeneratedXML],
        nca_code: str,
        config: NCAPackagingConfig,       # Loaded from config/packaging/{nca}.yaml
    ) -> list[PackagedFile]:
        """
        DE (BaFin)  → individual .gz per XML
        BE (FSMA)   → .zip bundles
        LU (CSSF)   → single .zip
        GB (FCA)    → FCA-specific XML namespace + structure
        Default     → .zip when multiple files
        """
        ...
```

---

## 6. Client Review Screen — Data Model

The review screen needs to show the complete report with validation status per field and allow edits. The data model supports this:

```
┌─────────────────────────────────────────────────────────────────┐
│  CLIENT REVIEW SCREEN                                           │
│                                                                  │
│  Report: AIFM ABC Capital — Q4 2025 — NCA: CSSF                │
│  Status: CAF_FAILED (3 errors, 2 warnings)                     │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Section: AIFM Identification                              │  │
│  │                                                            │  │
│  │  AIFM Name         ABC Capital Management    ✓ PASS       │  │
│  │  AIFM LEI          5493001K...               ✓ PASS       │  │
│  │  National Code     A01234                    ✓ PASS       │  │
│  │  Reporting Period  Q4 2025                   ✓ PASS       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Section: AIF "Global Equity Fund"                         │  │
│  │                                                            │  │
│  │  NAV               €125,000,000              ✓ PASS       │  │
│  │  AuM               €130,500,000   [derived]  ✓ PASS       │  │
│  │  Base Currency      EUR                      ✓ PASS       │  │
│  │  Inception Date    [empty]                   ✗ CAF        │  │
│  │                    Rule: REQ-VAL-001-F42                   │  │
│  │                    [Edit] [Upload source]                  │  │
│  │                                                            │  │
│  │  Leverage (GNM)    1.45           [derived]  ⚠ DQ_WARNING │  │
│  │                    DQEF: >20% change vs prior period       │  │
│  │                    [Acknowledge] [Edit]                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────┐                                    │
│  │ [Upload additional file] │  ← Add ESMA template, annual      │
│  │ [Re-validate]            │    report, etc. as extra source    │
│  │ [Approve all]            │  ← Only when 0 CAF errors          │
│  └─────────────────────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

**What the screen reads:**

| API endpoint | Returns |
|---|---|
| `GET /api/v1/records/{record_id}` | Canonical record (all fields + provenance) |
| `GET /api/v1/records/{record_id}/validation` | ValidationReport (per-field CAF/CAM/PASS) |
| `GET /api/v1/records/{record_id}/derivations` | Which fields were derived and from what inputs |

**What the screen writes:**

| API endpoint | Effect |
|---|---|
| `PATCH /api/v1/records/{record_id}/fields/{field_path}` | Update field → re-derive → re-validate |
| `POST /api/v1/records/{record_id}/sources` | Upload additional source → merge → re-derive → re-validate |
| `POST /api/v1/records/{record_id}/approve` | Move to APPROVED (only if 0 CAF errors + user is COMPLIANCE_REVIEWER) |

---

## 7. Migration Strategy — Phased Approach

The regression suite (`run_regression_suite.py`) remains the safety net. After each phase, all existing test cases must produce identical XML output.

### Phase 1: Extract shared code (1–2 days)

- `shared/constants.py` — all lookup tables
- `shared/reference_data.py` — country/region/turnover mappings
- `shared/formatting.py` — string/number formatting helpers
- **Zero behavior change.** Import paths updated in `m_adapter.py`.
- Run regression suite.

### Phase 2: Extract canonical model + parser (2–3 days)

- `models/record_types.py` — `MRecord` class
- `models/parsed_template.py` — `ParsedTemplate` dataclass
- `adapters/m_adapter/parser.py` — Excel/CSV reading
- `adapters/m_adapter/template_detector.py`
- `adapters/m_adapter/field_mapper.py` — M column names → canonical paths
- `m_adapter.py.__init__` now calls `parse_template()` → returns `ParsedTemplate`
- Run regression suite.

### Phase 3: Extract derivation engine (2–3 days)

- `transformation/fx_service.py` — ECB rate fetching
- `transformation/aum_calculator.py` — AuM, NAV, leverage
- `transformation/geo_focus.py` — geographic aggregation
- `transformation/aggregation.py` — position rollups
- Derivation methods operate on `ParsedTemplate` → produce `EnrichedTemplate`
- Run regression suite.

### Phase 4: Extract XML packaging (3–4 days)

Largest volume of code — all `_build_*` methods and `generate_all()`.

- `packaging/xml_builder.py` — AIFM + AIF XML generation
- `packaging/fca_xml_builder.py` — FCA-specific deviations
- `packaging/nca_packager.py` — gz/zip/naming per NCA
- `packaging/xml_utils.py` — pretty-print, `_sub()`, namespace constants
- Run regression suite.

### Phase 5: Add validation engine (2–3 days, new functionality)

- `validation/validation_engine.py` — rule engine reading from `aifmd_annex_iv_validation_rules.yaml`
- `validation/validation_result.py` — per-field CAF/CAM/PASS
- `validation/cross_record_validator.py` — batch-level consistency
- Wire into M adapter facade: parse → derive → **validate** → package
- Add validation-specific tests.

### Phase 6: Wire to canonical DB + review loop (3–5 days, new functionality)

- Write `ParsedTemplate` fields to `canonical_records` + `canonical_fields`
- Implement `SourceMerger` for multi-source canonical records
- Implement `FieldEditor` for user corrections
- Re-derive + re-validate after edits
- Only generate XML from approved DB records
- This phase connects the refactored modules to the platform pipeline (L9 orchestration).

### Phase 7: Add new adapters (ongoing)

- `adapters/esma_adapter/` — ESMA Excel template parser
- `adapters/xml_reimport_adapter/` — old XML re-import
- `transformation/ai_extraction.py` — Claude-based extraction for annual reports
- `review/supplementary_source.py` — accept additional sources during review
- Each new adapter is independent — no changes to existing modules.

---

## 8. Architecture Principle Alignment

| Principle | How this design addresses it |
|---|---|
| **P5 — Deterministic core, probabilistic edge** | AI extraction (L2) is one source among many. All validation (L3), derivation (L2b), and packaging (L6) are deterministic. AI output never reaches XML without passing the validation gate AND human approval. |
| **P6 — Modular and portable** | Each adapter is independently versioned and swappable. Validation rules and NCA configs loaded from YAML. New input format = new adapter, zero changes to pipeline. |
| **P9 — Security by design** | Canonical records enforce RLS at DB level. All user edits carry provenance and audit trail. AI content flagged and sandboxed. |
| **P14 — Database-first** | `canonical_records` is the system of record. XML files are generated views of DB data. Review screen reads from DB. Edits write to DB. |
| **P15 — Platform-first** | Ingestion routing, orchestration (L9), audit trail (L8), and IAM (L11) are platform-agnostic. All AIFMD logic lives under `products/aifmd/`. |

---

## 9. Backward Compatibility

During the migration (Phases 1–4), the existing `MAdapter` class remains the public API:

```python
# m_adapter.py — becomes a thin facade
class MAdapter:
    """Backward-compatible facade. Will be deprecated when platform pipeline is live."""

    def __init__(self, *paths, csv_paths=None):
        self._parsed = parse_template(*paths, csv_paths=csv_paths)
        self._enriched = derive(self._parsed)
        # Phase 5+: self._validation = validate(self._enriched)

    def generate_aifm_xml(self, output_path=None, reporting_member_state=None):
        return build_aifm_xml(self._enriched, output_path, reporting_member_state)

    def generate_aif_xml(self, output_path=None, **kwargs):
        return build_aif_xml(self._enriched, output_path, **kwargs)

    def generate_all(self, output_dir=None, reporting_member_state=None):
        return package_all(self._enriched, output_dir, reporting_member_state)

    def summary(self):
        return build_summary(self._enriched)
```

Once the platform pipeline (Phase 6+) is live, this facade is deprecated in favor of the API-driven flow:
`POST /api/v1/ingestion → GET /api/v1/records/{id}/validation → PATCH fields → POST approve → GET files`

---

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| XML output changes after refactor | High — NCA rejection | Byte-level regression on full test suite after each phase |
| Multi-source merge conflicts confuse users | Medium — data quality | Clear UI showing provenance per field, explicit conflict resolution |
| AI extraction produces bad data | Medium — wrong submission | AI fields carry LOW/MEDIUM/HIGH confidence; LOW requires explicit confirmation; L3 catches impossible values |
| Re-validation loop creates performance issues | Medium — slow UX | Only re-derive/re-validate affected fields (dependency graph), not the full record |
| FCA logic tightly interleaved with ESMA | Medium — hard to separate | Phase 4 explicitly creates `fca_xml_builder.py` as subclass/strategy |
| Phase 6 (DB integration) is a big leap | High — integration risk | Phases 1–5 are pure refactoring with regression safety. Phase 6 is new functionality with its own test suite. |

---

## 11. Estimated Timeline

| Phase | Effort | Depends on | Deliverable |
|---|---|---|---|
| 1 — Shared utilities | 1–2 days | — | Clean imports, reduced m_adapter.py |
| 2 — Canonical + parser | 2–3 days | Phase 1 | `ParsedTemplate`, standalone parser |
| 3 — Derivation engine | 2–3 days | Phase 2 | `EnrichedTemplate`, reusable derivation |
| 4 — XML packaging | 3–4 days | Phase 3 | XML generation decoupled from parsing |
| 5 — Validation engine | 2–3 days | Phase 4 | Per-field CAF/CAM/PASS before packaging |
| 6 — DB + review loop | 3–5 days | Phase 5 | Full pipeline: ingest → validate → review → package |
| 7 — New adapters | Ongoing | Phase 6 | ESMA, XML reimport, AI extraction |

**Total for Phases 1–6: ~15–20 working days**
Phase 7 is continuous — each new adapter is 2–5 days depending on complexity.
