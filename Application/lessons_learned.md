# Lessons Learned — Project Eagle Development

## 2026-04-03: Schema loader path misconfiguration

### What happened
The M adapter column schema (`m_column_schema_v1.yaml`) defines fixed column positions per record type, making the parser independent of Excel header names. However, `schema_loader.py` looked for the file at `Application/Adapters/Code/policies/` — a path that never existed. The parser silently fell back to header-based parsing without any visible error or warning at runtime.

### Impact
- 14 of 22 authorised_anon XMLs failed XSD validation
- Field names depended on whatever each template provider wrote in their headers
- The core design principle (fixed column order, canonical field names) was never active in production

### Root cause
The schema loader used a wrong relative path (`parent.parent.parent.parent / "Code" / "policies"`) that resolved to `Application/Adapters/Code/policies/` instead of the actual file location. The `log.warning()` message was only visible when logging was explicitly enabled.

### What I did wrong in diagnosis
- Initially traced the XSD failures to a "field name mismatch" between the template header (`"Sub-asset type code of turnover"`) and what `aif_builder.py` expected (`"Sub-Asset Type of Turnover"`)
- This analysis was **correct for header-based parsing** but missed the real question: why was header-based parsing used at all?
- Olaf pointed out that the M adapter is designed around fixed column positions — that prompt led to finding the actual root cause

### Fix
1. Moved `m_column_schema_v1.yaml` to `Application/Adapters/Input adapters/M adapter/` (next to the code that uses it)
2. Updated `schema_loader.py` to resolve the path relative to the M adapter directory (2 parents up from `m_parser/schema_loader.py`)

### Result
- authorised_anon: 8/22 → 23/24 XSD valid
- m_split_nl: 1/3 → 3/3 XSD valid, DQF warnings 72 → 54
- All 9 golden set suites: PASS

### Lessons for next time

1. **When a silent fallback exists, verify the primary path first.** Before diagnosing downstream symptoms, check that upstream configuration is actually loaded. A quick `print(len(_COLUMN_SCHEMA))` would have revealed the empty schema immediately.

2. **Respect the design principles before guessing at symptoms.** The M adapter's core contract is fixed-position parsing. Any diagnosis that assumes header-based parsing should trigger the question: "wait, is the schema actually loaded?"

3. **Silent failures are dangerous.** The `log.warning()` in the schema loader was invisible during normal test runs. Consider making schema loading failure louder — raise an error or at minimum print to stderr.

4. **Test the assumption, not just the symptom.** Instead of reading Excel headers and comparing them to code, I should have first verified what the parser actually produced: `print(dict(adapter.turnovers[0]))`. That would have shown which field names were in the MRecord.

5. **File location matters.** Configuration files should live next to the code that depends on them, not in a separate directory tree that may not exist in all environments. The schema now lives in the M adapter directory.

## 2026-04-03: Public reference data — dual-backend store + fetchers

### What was built
Reference data ingestion pipeline for three public data sources needed by the AIFMD reporting pipeline:
- **ECB exchange rates** (REQ-REF-001): full history backfill (217K rates, 1999–present, 41 currencies)
- **GLEIF LEI register** (REQ-REF-002): API lookup + cache with 7-day TTL
- **ISO 10383 MIC codes** (REQ-REF-001): 2,832 codes across 149 countries

### Architecture decisions

1. **Dual-backend `ReferenceStore`** — single interface, SQLite for test phase, PostgreSQL for production. Same table names and columns as eagle_software_architecture.md §6.3. Switch is one line: `ReferenceStore.postgresql(...)` instead of `.sqlite(...)`.

2. **Fetchers as standalone scripts with CLI** — each fetcher is independently runnable (`python fetch_ecb_rates.py backfill`). Same code runs as Lambda/ECS task in production; only the trigger mechanism changes (CLI → EventBridge).

3. **`get_ecb_rate_closest()`** — returns the most recent rate on or before a given date. This implements REQ-LEG-003 ("ECB rate for last business day of reporting period") without requiring the caller to know which day is a business day.

### What went well
- All three public APIs are free, require no authentication, and responded reliably
- ECB XML format is clean and stable (same since 1999)
- GLEIF JSON:API is well-designed with good search + pagination
- MIC XLSX download is straightforward despite the openpyxl header-parsing quirk

### What to watch out for
- **Google Drive mount doesn't support SQLite** — WAL mode requires file locking. For local dev, the SQLite file must be on a local filesystem, not a mounted Drive folder. PostgreSQL on localhost doesn't have this issue.
- **ESMA AIFM register** has no clean bulk download — CSV export is row-limited. Paginated queries per NCA country + national register supplementation needed (not yet built, lower priority per REQ-GTM-003).
- **GLEIF rate limit is 60 req/min** — batch lookups need throttling. The `RATE_LIMIT_DELAY = 1.1s` setting stays well under the limit.
- **MIC XLSX column headers may change between publications** — the parser does fuzzy column detection, not hardcoded indices. If ISO changes the format, check the header matching logic.

## 2026-04-03: LEI validation module — two-path validation with name normalization

### What was built
`shared/lei_validator.py` — a complete LEI validation module implementing two ESMA-required validation paths:

1. **Path 1 (LEI provided)**: ISO 17442 format check → GLEIF lookup (cache-first, API fallback) → name similarity scoring between reported and GLEIF legal name
2. **Path 2 (LEI missing)**: normalize entity name → search GLEIF cache by normalized name + optional country filter → suggest matching LEI

Also added `normalized_name` and `country` columns to `gleif_lei_cache` in both SQLite and PostgreSQL schemas, with a migration script for existing databases.

### Key design decisions

1. **Name normalization pipeline**: Unicode NFKD → strip diacritics → uppercase → punctuation to spaces → collapse single-letter sequences ("S.A." → "SA") → strip legal suffixes → remove remaining non-alphanumeric. The single-letter collapse step was critical to handle European legal forms like "S.A.", "S.A.S.", "N.V." correctly.

2. **Country code as disambiguation filter**: Added `country` (ISO 3166-1 alpha-2 from GLEIF legalAddress) to Path 2. If provided, search first filters by country; if no results, falls back to name-only. This dramatically improves matching reliability for common names (e.g., "BlackRock" entities exist in US, UK, IE, LU, JP).

3. **Suffix list is aggressive**: ~50 legal suffixes including "AKTIENGESELLSCHAFT", "HOLDING", "MANAGEMENT", "THE", etc. This improves matching (Deutsche Bank AG ↔ Deutsche Bank Aktiengesellschaft) but means entities whose entire name is a suffix (e.g., just "Fund" or "Trust") will fall back to the un-stripped form.

### What failed during testing and how it was fixed

1. **"Aktiengesellschaft" not stripped** — was not in the suffix list. Added it (along with "THE").
2. **"S.A." not matching "SA"** — punctuation broke word boundaries. Fixed by: (a) converting punctuation to spaces first, then (b) collapsing single-letter sequences before suffix matching.
3. **GLEIF API fallback in tests** — test for "LEI not in GLEIF" unexpectedly found the LEI because the API fallback actually hit the live GLEIF API. Tests should either mock external APIs or adjust expectations. For now, adjusted expectations; proper mocking needed for CI.

### Lessons for next time

1. **Normalization order matters enormously.** The original order (strip suffixes → remove punctuation) failed because "S.A." had dots that broke the word-boundary regex for "SA". Changing to (remove punctuation → collapse single-letters → strip suffixes) fixed it. When building text normalization pipelines, test with European entity names (Société Générale S.A., Deutsche Bank Aktiengesellschaft, BV, NV) not just English ones.

2. **Country code is cheap to add but expensive to retrofit.** Adding it during initial design was trivial. If we'd deployed Path 2 without it, every "BlackRock" lookup would have returned ambiguous results across 10+ jurisdictions. Always consider disambiguation dimensions upfront.

3. **External API calls in unit tests are fragile.** The GLEIF API fallback in `validate_lei_with_gleif` makes the function behave differently depending on network availability. For CI, inject a mock store or disable the API fallback path.

## 2026-04-03: LEI enrichment engine — auto-fill empty LEI fields from GLEIF

### What was built
`shared/lei_enrichment.py` — an enrichment engine that scans all 8 LEI-bearing entity types in a SourceCanonical and auto-fills empty LEI codes from the GLEIF cache:

- **ENRICHED**: Single GLEIF match → auto-fill with `SourcePriority.DERIVED`
- **PENDING_USER_CHOICE**: Multiple matches → record candidates for later UI selection
- **NO_MATCH**: No GLEIF match → flag for manual assignment
- **SKIPPED**: LEI already present → no action

Integrated at L1B in `to_canonical_from_source()` (post-parsing, pre-projection). The enrichment runs only when a `ReferenceStore` is provided.

### Key design decisions

1. **Provenance-native enrichment**: Enriched LEIs use `SourcePriority.DERIVED` (priority 30), so they never overwrite imported data (priority 40) or manual overrides (priority 50). User choices via `apply_user_choice()` use `MANUALLY_OVERRIDDEN` (priority 50). The existing provenance system tracks everything.

2. **Country hint per entity type**: Only Manager (jurisdiction), Fund (domicile), and ControlledCompany (domicile) have a relevant country field. All other entities (counterparties, positions, instruments, borrowing sources, controlled structures) search without country filter. This is by design — counterparty country isn't known until after the GLEIF lookup.

3. **Only populated entities**: The enrichment iterates through actual entities in the canonical. A LIGHT manager report with no counterparties produces zero counterparty enrichment actions. No forced enrichment of missing entities.

4. **`LEI_FIELD_MAP` as registry**: All 8 entity types with their lei/name/country field mappings in one declarative structure. Adding a new LEI-bearing entity in the future = one dict entry.

### What surprised us during testing

1. **"BlackRock Fund" normalizes to "BLACKROCK"** because "Fund" is in the legal suffix list. This produced a PENDING_USER_CHOICE instead of the expected NO_MATCH. This is actually correct behavior — the suffix stripping is doing its job. The user would then pick the right BlackRock entity for their fund.

2. **`_init_schema()` PostgreSQL failure**: When the migration added `normalized_name` and `country` columns, the `CREATE TABLE IF NOT EXISTS` was correctly skipped for the existing table, but the subsequent `CREATE INDEX` on the not-yet-existing columns failed. Fixed by executing each DDL statement individually with try/except in `_init_schema()`.

### Lessons for next time

1. **Schema migrations and schema init must be independent.** The `_init_schema()` method assumed fresh databases. Real databases evolve — DDL changes need to be idempotent and tolerant of missing columns during index creation.

2. **Suffix stripping has surprising effects.** "Fund", "Trust", "Management", "Capital" are common legal suffixes AND common words in fund names. "BlackRock Capital Management Fund" normalizes to just "BLACKROCK". This is a feature for matching but means more multi-match scenarios. Consider adding a minimum-name-length check after stripping.

3. **Country availability varies by entity type.** Don't assume all LEI-bearing entities have a country field. The enrichment engine must gracefully handle missing country hints — search broadly when country is unknown, search narrowly when available.

## 2026-04-03: LEI enrichment in regression suite + canonical path bugs

### What was built
Integrated LEI enrichment analysis into `run_regression_suite.py` via `--with-enrichment` flag. Created `gleif_seed.yaml` with 12 synthetic GLEIF cache entries (6 for M example templates, 6 for authorised_anon) — all with ISO 7064 Mod 97-10 valid check digits. The seed is loaded into an in-memory SQLite `ReferenceStore` at test startup.

### Architecture decision: report-only enrichment
The original plan was to run enrichment through the full canonical path (`to_canonical_from_source → build_from_canonical`) so enriched LEIs would appear in the generated XML. This failed because the `from_canonical()` → `generate_all()` round-trip had multiple untested reconstruction bugs. Instead, enrichment runs as a parallel analysis step: the canonical path produces the enrichment log, while the standard `generate_all()` path produces the XML. This keeps baseline stability while still capturing enrichment metrics in evidence.

### Bugs found and fixed in the canonical projection layer

1. **`report.groups` is a read-only copy** — `CanonicalReport.groups` is a `@property` that returns `dict(self._groups)`. The `project_groups()` function wrote to `report.groups["positions"] = []` which mutated the copy, not the internal dict. Next line reading `report.groups["positions"]` got a fresh copy without the key → `KeyError`. Fixed by using `report._groups` directly.

2. **`_position_to_dict()` and 9 other entity-to-dict converters** accessed non-existent attributes like `position.id`, `position.market_code`. SourceEntity objects use `get()`/`get_field()` — they don't expose fields as Python attributes. Replaced all 10 converters with a generic `_entity_to_dict()` that iterates `entity._FIELD_NAMES` and stores FieldValue objects directly.

3. **Missing reporting year in canonical report fields** — `_collect_aifm_report_fields()` set fields "1"–"8" but not "9" (reporting year). When `from_canonical()` tried to reconstruct the MAdapter, it got `reporting_year=0`, causing FX rate lookup to fail with `'0-12-31'`. Added field "9" to the report fields dict.

4. **Content type confusion in `from_canonical()`** — AIF builder expected `content_type` as "1"/"2"/"3" but received the filing type "INIT" instead. This is a field mapping bug in the reconstruction path that wasn't addressed (deferred — the report-only enrichment approach avoids this path).

### Regression results with enrichment
All 9 suites: PASS. Enrichment found 3 matches per standard template (manager + 2 fund LEIs from seed). Evidence file records enrichment counts per suite under `mode: E2E+enrichment`.

### Lessons for next time

1. **Read-only property traps.** If a class exposes internal state via a `@property` that returns a copy, any code that tries to mutate through it will silently fail. When designing properties on model classes, either return a view (not a copy) or raise `AttributeError` on mutation attempts.

2. **Entity-to-dict converters must use the entity's API.** SourceEntity uses `get()`/`get_field()`, not attribute access. When writing converters between layers, always use the public API of the source object — don't assume attribute access works just because it's a Python object.

3. **The `from_canonical()` round-trip is fragile.** The canonical→MAdapter→XML path has never been tested end-to-end. It relies on correct mapping of ~300 ESMA field IDs back to the adapter's internal structures. Until this path is battle-tested, keep it as a parallel analysis rather than the primary generation path.

4. **Synthetic LEI check digits matter.** The original hand-written LEIs all failed ISO 7064 validation. Use the formula `check_digits = 98 - (numeric_lei_with_00 % 97)` to compute valid check digits for any test LEI.

## 2026-04-04: Synthetic test expansion — 31 NCAs, 350 rules, 100% coverage

### What happened
Expanded the synthetic test suite from 4 NCAs (NL, DE, BE, GB) to all 31 AIFMD jurisdictions (30 ESMA + 1 FCA). Built field coverage evidence showing every AIFM and AIF validation rule is exercised.

### Key findings and fixes

1. **CSSF (LU) NCA override format bug.** The AIF-34 share class national code override used `format: '[0-9]{4}  (4-digit zero-padded share class identifier)'` — the validator treated the entire string (including the description) as a regex, causing all LU AIF XMLs to fail DQF. Fix: changed to `format: '4 [0-9]{4}'` using the standard ESMA length-prefix notation, and added a separate `format_description` field. Lesson: NCA override format fields must use the same notation as base ESMA rules — never embed human-readable descriptions in the regex field.

2. **XSD element name precision.** `TotalFinancingInDaysMore365Rate` vs `TotalFinancingInDays365MoreRate` — a subtle transposition that caused XSD validation failures for all full-template AIFs. The builder used a plausible but incorrect name. Lesson: always verify element names against the XSD schema directly, not from memory or documentation paraphrases.

3. **Reference XML storage location.** Generated reference XMLs into `reference_xml/` subdirectories, but the regression suite's `_find_reference_xmls()` looks for `*.xml` in the suite directory root. All 54 new suites showed "Extra file: not in reference set" until references were moved. Lesson: match the existing convention before inventing new directory structures.

4. **Rule Coverage aggregation is per-file, not per-suite.** The validator's Rule Coverage sheet shows the status from the last file processed, not the best status across all files. This made 15 actually-EVALUATED rules appear as N_A when running all files together. The merged cross-suite analysis correctly shows 0 NOT_FOUND. Lesson: when reporting coverage, always merge across all files and suites before drawing conclusions.

5. **Obligation change codes (AIF-10/11, AIFM-10/11) are AMND-only.** These 4 rules never appear in INIT filings — they require a separate AMND test suite to be covered. Without the synthetic_amnd_nl suite, they show as NOT_FOUND. Lesson: filing-type-dependent rules need dedicated filing-type test suites.

### Final state
- 74 regression suites: ALL PASS (72 PASS + 2 WARNING for FI filename convention)
- 65 synthetic test suites covering 31 NCAs × light+full, AMND, CANCEL, negative
- 350/350 validation rules covered (300 EVALUATED + 50 CONDITIONAL_NA, 0 gaps)
- 516 reference XMLs across synthetic suites
- Field coverage evidence Excel generated with per-rule audit trail

## 2026-04-04: NCA-specific packaging — 31 NCAs, config-driven orchestration

### What was built
Implemented proper NCA-specific packaging for all 31 AIFMD jurisdictions, replacing the hardcoded DE/BE-only logic in `orchestrator.py` with a config-driven approach.

### Architecture decisions

1. **Single source of truth: `aifmd_nca_packaging.py`**. Created `Application/aifmd_packaging/aifmd_nca_packaging.py` with a `NCA_PACKAGING_CONFIG` dict covering all 31 NCAs. This module is imported by the orchestrator (to produce correct packaging), the regression suite (to validate packaging), and can be used by the validator. Avoids duplicating packaging logic across files.

2. **Four packaging types implemented:**
   - `gzip`: Each XML individually GZIP-compressed (DE/BaFin only)
   - `zip`: All XMLs bundled in a single ZIP (BE, ES, PT, SE, CZ, MT)
   - `zip-in-zip`: Per-AIF ZIPs bundled in a master ZIP (LU/CSSF)
   - `xml`: Plain XML, ZIP only when multi-AIF for convenience (all others)

3. **`get_expected_extensions()` utility function**: Returns the expected file extensions for a given NCA and AIF count, used by the regression suite to predict packaging artifacts without reimplementing the logic.

### Bugs found and fixed

1. **BE packaging format change broke reference packages.** The old code produced separate `AIFM_BE_*.zip` + `AIF_BE_*.zip`; the new code produces a single `AIFMD_BE_*.zip` bundle. The multi-NCA suite failed because the old reference `AIFM_BE_0000088701_20240930.zip` no longer matched. Fix: regenerated reference packages.

2. **`_FILENAME_PATTERN` too restrictive.** The regex `^(AIFM|AIF)_...` rejected the new `AIFMD_` prefix for bundled ZIPs and the `_master` suffix for LU zip-in-zip. Also, FI national codes contain `#` characters (`8506386#001`) which weren't in the character class. Fix: updated pattern to `^(AIFMD|AIFM|AIF)_..._([A-Za-z0-9_#.-]+)_...(_master)?\.`.

3. **FI suites regressed after filename pattern was first extended.** The initial fix only added `AIFMD` to the prefix group but didn't add `#` to the character class. The FI suites went from 0 naming failures to 8 (light) / 6 (full). This was caught by the baseline regression check and fixed in the same cycle.

### Lessons for next time

1. **Packaging format is a naming convention too.** When changing how packages are named (e.g., `AIFM_BE_*.zip` → `AIFMD_BE_*.zip`), every pattern that matches filenames needs updating: the regression suite's `_FILENAME_PATTERN`, the validator's `_NCA_FILE_SPECS`, and the reference package discovery function. Always grep for the old prefix before changing it.

2. **National code character sets vary wildly.** The initial `[A-Za-z0-9_-]` character class assumed clean alphanumeric codes. FI uses `#` in national codes (e.g., `8506386#001`). When building filename patterns, check actual national code formats across all NCAs before choosing a character class.

3. **Config-driven beats hardcoded.** The old `if rms == "DE": ... elif rms == "BE": ... else:` approach required code changes for every new NCA. The config-driven approach (`NCA_PACKAGING_CONFIG[rms]`) makes adding or changing an NCA a one-line dict update with no code changes to the orchestrator.

4. **Reference package updates are part of the change.** Whenever packaging logic changes, the reference packages in `golden_set/` must be regenerated. Forgetting this causes false-positive regressions that mask real issues.

### Final state
- 74 regression suites: ALL PASS
- 65 synthetic test suites: ALL PREDICTIONS MATCH, 0 DEVIATIONS
- NCA packaging validated for all 31 jurisdictions
- `adapter-regression-harness` skill created for future autonomous regression cycles

## 2026-04-04: FCA consolidated naming fix + regression suite split

### What was built

1. **Validator fix for FCA consolidated AIF files.** The `validate_aifmd_xml.py` National Code check (Check 3) failed for `AIF_REPORTS_GB_{AIFM_NC}_{DATE}.xml` files because:
   - The code extracted the national code from position `parts[2:-1]` which for `AIF_REPORTS_GB_123456_20251231.xml` yielded `"GB_123456"` instead of `"123456"` (wrong index due to the `REPORTS` token)
   - It compared against `AIFNationalCode` (an individual AIF's code) instead of `AIFMNationalCode` (the AIFM's FRN in the filename)
   Fix: detect `AIF_REPORTS_` prefix, shift code extraction index from 2 to 3, and compare against `AIFMNationalCode` for consolidated files.

2. **Regression suite split.** Added `--scope` argument to `run_regression_suite.py` with three modes:
   - `realdata`: 9 M example suites (quick, for small changes)
   - `synthetic`: 65 synthetic suites (thorough, for large changes)
   - `all`: all 74 suites (default, or when skill is invoked)
   Created wrapper scripts `run_regression_realdata.py` and `run_regression_synthetic.py`.
   Added `"category"` field to every suite in the SUITES dict.

3. **Reference XML regeneration.** The AIF-level Assumptions block (added for FCA consolidated support) affected all full-template AIF XMLs. 33 synthetic full suites + m_multi_nca had stale references. Regenerated all affected references.

### Bugs found and fixed

1. **Validator filename code extraction off-by-one for `AIF_REPORTS_` prefix.** The generic `parts[2:-1]` logic assumed all filenames are `{TYPE}_{CC}_{CODE}_{DATE}` (3 underscored tokens before CC). The consolidated format has 4 tokens (`AIF_REPORTS_GB_...`). Fix: detect prefix and adjust start index.

2. **Validator compared against wrong XML element for consolidated files.** Consolidated files carry the AIFM's national code (FRN) in the filename, not an individual AIF's code. But Check 3 read `AIFNationalCode` for all non-AIFM files. Fix: for `is_consolidated` files, read `AIFMNationalCode` instead.

3. **Stale reference XMLs for 33+ suites.** The AIF-level Assumptions block was added to `_build_aif_record()` for all NCAs (not just GB), so all full-template AIF XMLs gained an `<Assumptions>` element. The existing references didn't have this element. Fix: batch regeneration of all affected reference XMLs.

4. **Expected findings baseline stale for 2 suites.** `synthetic_light_gb_init` had `file_naming_fail: 1` in the baseline (from the pre-fix state), but after the validator fix it became 0. `synthetic_negative_crossfield` had no baseline entry at all. Fix: recaptured expected findings.

5. **Old GB per-AIF ZIP reference in m_multi_nca_gb.** The file `AIF_GB_845672_20240930.zip` was a reference from the pre-consolidated era. GB now produces `AIF_REPORTS_GB_*` (no ZIP). Fix: removed the stale ZIP reference.

### Lessons for next time

1. **Multi-token filename prefixes break naive splitting.** When parsing filenames like `AIF_REPORTS_GB_123456_20251231.xml`, splitting on `_` and using fixed indices fails because the prefix has a variable number of tokens. Always detect the prefix pattern first, then extract fields relative to that.

2. **Consolidated files use the AIFM code, not the AIF code.** For consolidated multi-AIF files, the filename identifies the AIFM (one entity), not any specific AIF (multiple entities inside). Any validation that compares filename codes to XML content must account for this semantic difference.

3. **Builder changes affect ALL NCAs, not just the target.** The Assumptions block was added primarily for FCA, but `_build_aif_record()` is shared code. Any structural change to the XML builder affects every NCA's output. Always regenerate references for ALL suites after a builder change, not just the target NCA.

4. **Baseline drift compounds.** When multiple changes happen in sequence (packaging changes, then builder changes), each change may leave stale references or baselines. Running `--capture-expected` after the final state is cleaner than incremental updates.

5. **authorised_anon needs per-template sub-suite support.** The directory contains independent templates (each a different AIFM) that cannot be processed as a single adapter instance. Implementing per-template discovery is needed before this suite can be automated.

## 2026-04-05: Report Viewer — full-stack implementation (backend + frontend + cascade)

### What was built
Complete report viewer for AIFMD Annex IV regulatory reports:
- **Persistence layer** (`persistence/report_store.py`): SQLAlchemy ORM with dual SQLite/PostgreSQL backend. Tables: review_sessions, review_reports, review_edits, review_validation_runs.
- **API layer** (`api/`): FastAPI v0.2.0 with 22 routes across 4 routers (session, report, registry, validation).
- **Dependency graph** (`canonical/dependency_graph.py`): 109 source→report field mappings. Reverse index enables instant lookup of which report fields cascade from a source entity edit.
- **Cascade re-projection**: Source entity edits automatically update derived report fields with provenance tracking (`cascade_reprojection` source).
- **Field-level validation**: Mandatory field checks, format validation, data type checks — provides inline DQF feedback without XML regeneration.
- **Frontend** (`frontend/app/page.js`): Next.js App Router + Tailwind CSS. Components: UploadTab, ReportViewer, SectionAccordion, FieldRow, EditableCell, ProvenanceIcon, ValidationBadge, CompletionBar, SourceDataEditor, DiffPanel, FundSidebar, Toast.
- **Product config** (`config/products/aifmd_annex_iv.yaml`): Product-specific settings for multi-regulation readiness.
- **Integration tests** (`Testing/test_review_api.py`): 8 tests covering persistence, dependency graph, cascade, validation, and API health.

### Architecture decisions

1. **Edit at source canonical level, cascade to report fields.** The user edits positions, fund_static, manager, etc. — not ESMA field IDs directly. The dependency graph maps `manager.name` → AIFM field 19, `fund_static.base_currency` → AIF field 49, etc. This ensures consistency when one source field feeds multiple report fields.

2. **Composite fields flagged but not auto-computed.** Fields like "total NAV" (sum of all position market values) or "top 5 counterparties" require full pipeline aggregation. The cascade marks them as stale but doesn't recompute — that requires "Validate Report" which regenerates from scratch.

3. **Dual-layer validation.** Field-level validation (mandatory, format, type) runs instantly for inline indicators. Full validation (XSD + DQF) runs on explicit "Validate Report" button and requires XML regeneration. The field-level approach gives immediate feedback; full validation catches cross-field and structural issues.

4. **Turbopack root resolution for Google Drive paths.** Next.js 16 with Turbopack fails to resolve the workspace root when the project lives on a Google Drive FUSE mount (paths with spaces and special characters). Fixed by setting `turbopack.root: __dirname` in next.config.mjs.

### Issues encountered

1. **Google Drive FUSE mount blocks SQLite.** WAL mode requires file locking not supported by FUSE. Persistence layer falls back to tempdir automatically.

2. **Google Drive FUSE mount blocks Next.js build cache.** The `.next/` directory contains files that FUSE can't unlink. Build must happen on a local filesystem. On Olaf's machine (C:\Dev\eagle) this is fine; in sandbox we verified by copying to /tmp.

3. **Turbopack root inference fails with nested app directory.** The error "couldn't find next/package.json from project directory" occurs because Turbopack infers the workspace root from the `app/` directory instead of the project root. Setting `turbopack.root` in config resolves this.

### Lessons for next time

1. **FUSE-mounted drives are hostile to build tooling.** SQLite, Next.js build cache, and file watching all assume POSIX file semantics. Google Drive FUSE doesn't provide them. Always build and run on local filesystem; use the mount only for final deliverables.

2. **Cascade graphs should be built from the same mapping tables used for projection.** The dependency graph reuses `AIFM_ENTITY_MAP` and `AIF_ENTITY_MAP` from `aifmd_projection.py` — no duplication. If the projection tables change, the cascade automatically updates.

3. **Integration tests are fast with SQLite in-memory.** The full 8-test suite runs in under 2 seconds with `sqlite://` (no disk I/O). Use this for rapid iteration; switch to PostgreSQL for pre-deployment testing.

4. **Missing `httpx` and `python-multipart` for FastAPI TestClient.** These are not in the standard FastAPI install. Add them to requirements: `pip install httpx python-multipart`.

## 2026-04-05: Dev environment migration — Google Drive to GitHub + local dev

### What was built
Complete local development environment: Git repo at `C:\Dev\eagle`, pushed to private GitHub repo (`olafvanhalm-ship-it/eagle`), Python venv with all dependencies, PostgreSQL `eagle_dev` database with reference data, VS Code setup, Node.js for future front-end, and a mini FastAPI + Next.js upload/validation UI.

### What went well
- Regression suite ran first try locally (9/9 PASS) after reference data setup
- End-to-end browser flow (upload Excel → generate XML → validate) worked with only one import path fix
- Helper .bat scripts (`run_tests.bat`, `pull_latest.bat`, `push_changes.bat`, `start_eagle.bat`) make the workflow accessible without CLI knowledge

### Issues encountered
1. **PowerShell vs Command Prompt syntax.** `2>nul` (CMD redirect) fails in PowerShell — use `$null` instead. Gave CMD-style commands initially.
2. **setuptools build backend typo.** Used `setuptools.backends._legacy:_Backend` (doesn't exist) instead of `setuptools.build_meta`. Cost one round-trip.
3. **Flat-layout package discovery.** `setuptools` found `Testing/`, `Blueprint/`, `Application/` as top-level packages and refused to build. Fixed with `[tool.setuptools.packages.find] where = ["Application"]`.
4. **`config.py` truncated on Google Drive.** The `get_store()` function's last line was cut off (`return ReferenceStore.sqlite(SQLI`). File corruption or sync issue — always verify file integrity after Drive edits.
5. **FastAPI import path.** `m_adapter.py` lives deep in `Application/Adapters/Input adapters/M adapter/` — adding only `Application/` to sys.path wasn't enough. Had to add the M adapter directory explicitly.

### Lessons for next time
1. **Always use PowerShell syntax when giving Olaf commands.** He uses PowerShell, not CMD. Test redirect syntax, quoting, and special characters (`$` needs backtick escape).
2. **Google Drive file edits can truncate.** After editing a file on Drive, read it back to verify completeness before telling the user to copy it.
3. **Python project structure with spaces in paths is fragile.** Paths like `Input adapters/M adapter` work for scripts but complicate import paths. The future `src/eagle/` restructuring will fix this.
4. **`_format_validation()` needs fixing.** The PipelineValidationResult object structure doesn't match the assumed dict-based format. Validation scores show 0/0/0 in the UI. Investigate the actual object attributes in the next session.

## 2026-04-05: AIF canonical field mapping — completely wrong ESMA numbering

### What happened
The `to_canonical_aifs()` method in `m_adapter.py` mapped AIF data to field IDs using an invented numbering scheme instead of the official ESMA Annex IV question numbers. All 13 scalar fields it set were mapped to wrong field IDs.

### Impact
- **Every value in the AIF Report Viewer was in the wrong field.** "Reporting Member state" showed "Commercial real estate fund" (the AIF name), "Version" showed "Commercial real estate fund B.V." (another name), "Creation date" showed "NL" (the domicile), "Reporting period type" showed "EUR" (the base currency), "Reporting period year" showed "71000000" (the AuM).
- The AIFM report happened to be correct because its numbering aligned (fields 1-38), but AIF fields have a different structure.

### Root cause
When I wrote `to_canonical_aifs()`, I numbered the AIF fields sequentially as Q1=AIF ID, Q2=AIF Name, Q3=Domicile, etc. — treating them as "AIF-specific" question numbers. But the ESMA Annex IV AIF report uses its own field numbering where:
- Fields 1-3 are Header file metadata (RMS, Version, Creation date) — same as AIFM
- Fields 4-15 are Header section (filing type, content type, period dates, change codes)
- Fields 16-30 are AIF identification (AIFM NC, AIF NC, Name, EEA flag, domicile, LEI, etc.)
- Fields 48-53 are financial data (AuM, base currency, FX rate, NAV)

I never checked the field numbering against `aifmd_validation_rules.yaml` — I assumed the AIF fields had their own independent numbering starting from the entity-specific data.

### Fix
1. Rewrote `to_canonical_aifs()` to use correct ESMA field IDs from the validation rules YAML
2. AIF header fields 1-9 now match AIFM structure (report metadata)
3. AIF identification fields 16-30 now correctly map to ESMA questions
4. Financial fields use correct IDs: 48 (AuM), 49 (base ccy), 50-52 (FX), 53 (NAV)
5. Added auto-validation after upload so DQF indicators are populated immediately
6. Added AMND-only field filtering: change codes (10-12) hidden for INIT filings

### Also fixed
- Auto-validation now runs immediately after upload (session.py), so DQF column shows results from the first view
- Filled+Required filter now hides AMND-only fields (change codes 10-12) on INIT reports

### Lessons for next time

1. **Always verify canonical field IDs against the validation rules YAML.** The YAML is the single source of truth for ESMA field numbering. Never invent field numbers from domain knowledge or by counting sequentially. Open the YAML, find the field name, use that exact field ID.

2. **AIFM and AIF share the same header structure (fields 1-15).** Both report types have identical metadata fields for RMS, version, creation date, filing type, content type, period dates, and change codes. The entity-specific data starts at field 16 for both. This is an ESMA design decision, not obvious from the field names.

3. **Test the canonical output, not just the pipeline.** The regression suite tests the full pipeline (template → XML → validate), which exercises the old `generate_all()` path — not the new canonical path. A simple print of `{field_id: field_value}` from `to_canonical_aifs()` would have shown the misalignment instantly. Add canonical-level assertions to the test suite.

4. **"It works in the UI" is not "it works correctly."** The Report Viewer showed data in every row — it just showed the wrong data in the wrong fields. Functional tests must verify *content correctness*, not just *presence* of data.

## 2026-04-07: Report Viewer round 2 — dropdowns, NCA view, monthly table, hover tooltips

### What was built

1. **Reference value dropdowns**: Fields with `allowed_values_ref` (boolean, filing type, currency, country, sub-asset type, etc.) now show proper dropdown menus using `reference_values` from the API response instead of hardcoded empty arrays.

2. **NCA-specific report view**: Clicking an NCA code in the sidebar loads NCA override rules from the per-country YAML file. The backend applies format validation, overrides technical guidance with NCA-specific text, and populates `nca_deviations` on each field. Frontend passes `?nca=XX` parameter and shows "(filtered)" indicator.

3. **Monthly data table**: AIF fields Q219-Q278 (5 metrics × 12 months: gross return, net return, NAV change, subscriptions, redemptions) are synthesised into a single `monthly_data` group table, removing them from individual section display.

4. **Technical guidance hover**: Hovering over any field number (now prefixed with "Q") or field name shows the ESMA technical guidance text, obligation, format, and data type from the field registry.

5. **AIFM CT labels corrected**: Content type labels now match ESMA terminology: 1="24(1) Authorised AIFM", 2="3(3)(d) Registered AIFM", 3="24(1) NPPR AIFM".

6. **Section sorting**: Sections are now sorted by the minimum question number in each section, ensuring consistent display order.

7. **AIFM source data aggregation**: Manager tab source data now uses `aggregate=true` to collect positions, transactions, counterparties, and risk measures from ALL funds. A `_fund` column identifies which fund each item belongs to. Irrelevant source types (strategies, investors, share classes, borrowing sources) are filtered out for AIFM.

8. **Dynamic visibility**: ShareClassFlag (Q33) gates the share_classes group — hidden when false, shown when true. Full report reload after every edit ensures visibility recalculation.

### Architecture decisions

1. **NCA overrides loaded on-demand, not cached.** Each report request with `?nca=XX` reads the YAML file. For a UI with few concurrent users this is fine. If performance becomes an issue, add a `@lru_cache` on `_load_nca_overrides()`.

2. **NCA validation runs client-side of the field level.** NCA format checks apply after the base ESMA validation, adding findings rather than replacing them. This means a field can have both an ESMA PASS and an NCA FAIL.

3. **Monthly data as synthetic group, not XML group.** The ESMA schema stores months as individual scalar fields (Q219=January gross, Q220=February gross, etc.), not as repeating XML elements. The backend synthesises them into a tabular group just like geographical focus fields.

4. **Aggregate source data adds `_fund` metadata.** When `aggregate=true`, each position/transaction gets a `_fund` key showing which fund it belongs to, so the user can see the cross-fund overview.

### Lessons for next time

1. **Pass API response fields through to components — don't hardcode defaults.** The `referenceValues={[]}` hardcoding silently disabled all dropdown functionality. Always wire up the actual API response field (`field.reference_values`) even during initial development.

2. **ESMA content type codes differ between AIFM and AIF.** AIFM uses 1=Authorised, 2=Registered, 3=NPPR. AIF uses 1-5 for different Article combinations. Never assume they share the same labels.

3. **NCA override files have their own field_id mapping.** An NCA override references `field_id: '18'` but this could mean AIFM field 18 or AIF field 18 depending on `report_type`. Always filter by `report_type` when applying overrides.

4. **Synthetic groups must track their field IDs for exclusion.** Without `_synthetic_field_ids`, the monthly fields would appear both in the section view and the group table. Always add synthesised fields to the exclusion set.

5. **Dynamic visibility must cover ALL gate fields, not just the first one found.** The AIFMD schema has multiple boolean and enum gate fields that control section/field visibility. Full gate inventory (field-level + group-level):

   - Q33 (ShareClassFlag) → share class identifiers (Q34-Q41) + `share_classes` group
   - Q57 (PredominantAIFType=PEQF) → dominant influence (Q131-Q138) + controlled structures (Q286-Q296) + both groups + section
   - Q172 (DirectClearingFlag) → CCP details (Q173-Q177) + `ccp_exposures` group
   - Q161 (CounterpartyExposureFlag, AIF→counterparty) → counterparty details (Q162-Q165) + `fund_to_counterparty` group
   - Q167 (CounterpartyExposureFlag, counterparty→AIF) → counterparty details (Q168-Q171) + `counterparty_to_fund` group
   - Q297 (BorrowingSourceFlag) → borrowing source details (Q298-Q301) + `borrowing_sources` group
   - Q203 (PreferentialTreatment) → preferential treatment details (Q204-Q213)
   - Content type 4/5 → stress test results (Q279-Q280)

   Prime broker fields (Q45-Q47) have no explicit boolean gate — they are optional `[0..n]` and are handled by the standard "hide empty optional fields" logic. Gates operate at two levels: field-level (in the field-building loop) and group-level (on `groups_data` after synthesis).

## 2026-04-05: XML→field extraction — the right architecture for Report Viewer

### What happened
The `to_canonical_aifs()` / `to_canonical_aifm()` methods only mapped ~20 scalar fields out of 302 (6%). All derived, aggregated, and ranking data (instruments, geographical focus, exposures, turnovers, counterparties, risk measures, monthly returns, leverage, etc.) was missing because those methods only projected a subset of entity-level data to ESMA field IDs.

### Root cause
The canonical report methods were designed to produce a flat field→value mapping, but the ESMA Annex IV report has ~302 fields including extensive repeating groups. Manually mapping each group's elements to ESMA field IDs in `to_canonical_aifs()` was incomplete and error-prone. Meanwhile, the XML builders (`aif_builder.py`, `aifm_builder.py`) already produce **fully-populated, XSD-valid XML** with all 302 fields.

### Fix
Built `canonical/xml_field_extractor.py` which:
1. Parses the generated AIFM/AIF XML after `generate_and_validate()` runs
2. Walks the XML tree with context-aware parent disambiguation (e.g., `<Ranking>` under `MainInstrumentTraded` → field 64 vs under `PrincipalExposure` → field 94)
3. Extracts scalar fields into `fields_json` and repeating groups into `groups_json`
4. Handles FCA format (namespace stripping, `FCAFieldReference`/`AssumptionDetails` aliases)
5. Replaced the old `to_canonical_aifm()` / `to_canonical_aifs()` calls in `session.py` upload flow

Result: AIF fields went from 18/302 (6%) to 133/302 (44%) — the 44% represents all data actually present in the template. Missing fields are legitimately empty optionals (no share classes, no prime brokers, no dominant influence, etc.).

### Lessons for next time

1. **Don't reimplement what the pipeline already does correctly.** The XML builders already solve the field mapping problem. Parsing the XML output is simpler and guaranteed consistent with what gets submitted to the NCA.

2. **Shared XML element names need parent context.** Elements like `<Ranking>`, `<SubAssetType>`, `<EntityName>`, `<RateOctober>` appear in 6+ different contexts. A simple `find_element()` only finds the first match. Use the parent element chain to disambiguate.

3. **Completeness percentage should reflect reality.** 44% is correct for this fund — it doesn't have share classes, prime brokers, controlled structures, etc. Don't chase 100% by filling in phantom data.

5. **Validate before you display.** Running validation after upload (not just on button click) catches field-level issues immediately. The DQF column in the UI should never be empty when a report is first viewed.

## 2026-04-05: Report Viewer UI polish — 6 fixes in one pass

### What was fixed
1. **Repeating groups not displayed.** Backend already stored groups_json (instruments, exposures, strategies, risk measures, etc.) but the frontend never rendered them. Added `GroupTable` component with collapsible blue-accented tables.
2. **Value column misalignment.** Each section's table computed column widths independently. Fixed with `table-fixed` layout and consistent `<colgroup>` widths.
3. **Optional fields shown when empty.** Fields like 14 (assumptions), 34-40 (share classes) appeared even when empty. Tightened visibility: O (optional) and F (free) fields with no value are hidden in the default "Filled + Required" view.
4. **Empty fields incorrectly editable.** Field 61 (Other strategy description), 122, 127 etc. showed as editable despite being empty optionals. Now: empty optional fields are read-only with a dash indicator.
5. **Inconsistent value text color.** Non-editable values were gray (text-gray-400), editable had no explicit color. Now all values are text-gray-900 (near-black).
6. **DQF indicator only showed errors.** Backend only passed FAIL findings. Now also passes WARNING. Frontend uses 3-color dots: green (pass), orange (warning), red (error) instead of emoji checkmarks.

### Lessons for next time
1. **Don't collect only FAILs from the validator.** WARNING findings are just as important for the reviewer. Always include all severity levels in the validation_map.
2. **Use table-fixed layout when multiple sections share the same column structure.** Auto layout causes every section to compute its own widths, creating visual jumps.
3. **Empty optional ≠ editable.** If a field has no value because the source data doesn't provide it, making it editable creates a false sense of control — the field would just be overwritten on the next regeneration.

## 2026-04-05: Report Viewer — Source Data fix, multi-NCA, no-reporting support

### What was fixed
1. **Source Data sidebar empty.** The `_serialize_source_canonical(adapter)` function checked for `adapter.source_canonical` (an attribute that doesn't exist) instead of calling `adapter.to_source_canonical()` (the method). Fix: call the method, which returns `(aifm_source, aif_sources)` tuple of SourceCanonical dataclasses, then serialize via `.to_dict()`.
2. **Multi-NCA codes not collected.** Session creation only stored `[rms]` (single reporting member state). For templates with multiple NCAs (e.g., BE, NL, DE, GB), the per-AIF national code records were not read. Fix: extract NCA codes from `adapter.aifm_national_codes` and `adapter.aif_national_codes`, matching by AIF ID.
3. **No-reporting AIFs showed all fields.** When `AIFNoReportingFlag=true` (field 23), only header fields (1-23) should be visible per ESMA rules. The backend showed all fields including empty mandatory ones from post-header sections. Fix: filter fields > 23 (or > 21 for AIFM), suppress groups, and limit completeness calculation to header-only required fields. Added amber banner in frontend.

### Lessons for next time
1. **Check for the method, not the attribute.** When integrating with adapters, verify the exact API (`hasattr(x, "source_canonical")` vs `hasattr(x, "to_source_canonical")`). The silent fallback to an empty dict masked this for months.
2. **NCA codes live in collection records, not on the AIF object.** The M template stores per-NCA registration data in `aif_national_codes` records keyed by AIF ID + member state. Don't look for a flat `nca_codes` attribute on adapter.aifs entries — those are raw M template dicts.
3. **Regulatory flags change report structure.** The no-reporting flag isn't just a data issue — it changes which fields are applicable, which groups exist, and how completeness is calculated. Test with both reporting and no-reporting templates.

## 2026-04-07: Report Viewer — validation in value cells, AIFM sidebar, composite drill-down

### What was changed
1. **Validation status integrated into value cell.** Removed the separate "Validate" column. Value cells now have colored backgrounds: light green (PASS), light orange (WARNING), light red (FAIL). Hover shows the validation message. This saves a column and makes the status immediately visible.
2. **Non-editable fields show reason on hover.** System fields, composite/derived fields, and empty optionals now show why they're not editable. Composite fields have dotted underline and can be clicked to drill down to source data.
3. **Edit value persistence fixed.** Added `useEffect` to sync draft state with the value prop when it changes externally (e.g., after `loadReport()` completes). Previously the draft was initialized once and never updated.
4. **Group table headers show question numbers.** Numeric column IDs now display as "Q64: Sub-asset Type" instead of just the field name. Headers changed from blue to black for better readability.
5. **Top bar NCA display.** Now collects all unique NCA codes across all reports (AIFM + AIFs) instead of just `sessionData.reporting_member_state`.
6. **AIFM sidebar.** Manager Report tab now has a sidebar with NCA list, matching the Fund Reports layout. Replaced the separate `FundSidebar` with a shared `EntitySidebar` component.
7. **Composite field drill-down.** Clicking a derived field (category "composite") switches to the Fund Reports source data view, showing the underlying positions/entities.

### Architecture note from Olaf
Validation should run on the canonical layer, not on generated XML. The current flow (generate XML → validate XML → show results) should become (validate canonical → show results → generate XML only after validation passes). This is a larger refactor for a future session.

### Lessons for next time
1. **Separate validation columns waste space.** Integrating status into the value cell via background color is more information-dense and more intuitive — it's the standard pattern in spreadsheet tools.
2. **React state sync matters for edit flows.** When `EditableCell` receives a new value via props after an API call, the internal `draft` state must be updated. Without `useEffect(() => setDraft(value), [value])`, the old value persists in the input after a successful save.
3. **Shared sidebar components reduce duplication.** Instead of having `FundSidebar` (AIF-only) and a separate AIFM layout, a single `EntitySidebar` with a `reportType` prop works for both. Less code, consistent UX.

## 2026-04-07: Report Viewer — canonical validation, edit endpoint fix, multi-finding support

### What was changed
1. **Architecture: validate canonical, not XML.** Auto-validation now runs on every report load via `_field_level_validation()` in `report.py`. Every field gets a traffic-light colour immediately — no need to click "Validate Report" first. The "Validate Report" button runs the full YAML business rule set and stores results. Both sets of findings are merged per-field.
2. **Edit endpoint fixed.** `FieldEditRequest` now includes `report_type` and `fund_index`. The old endpoint defaulted everything to AIFM index 0, silently discarding edits to AIF reports. The frontend sends the correct report context with every edit.
3. **Multiple validation findings per field.** `FieldValidationResponse` now carries a `findings[]` array. The frontend hover tooltip shows ALL findings, not just the worst one. Aggregate status (FAIL > WARNING > PASS) determines the background color.
4. **Double-fire on Enter+blur fixed.** Used a `useRef(savedRef)` flag to prevent `onBlur` from triggering a second save after `Enter` already saved and closed the editor. The old code fired both `onKeyDown(Enter)` and `onBlur` when React removed the input from the DOM.
5. **Composite drill-down mapping.** `FIELD_TO_SOURCE` maps field ID ranges to the correct source entity type (positions, transactions, counterparties, etc.) instead of always defaulting to "positions".
6. **AIFM sidebar with source data.** Manager Report tab now loads AIFM-level source data and shows it in the sidebar, matching the Fund Reports layout.

### Critical bug found: edit endpoint silently updating wrong report
The `edit_field` endpoint had `report_type = "AIFM"` hardcoded with a TODO comment. It then tried to guess the type from the field registry, but many fields exist in both AIFM and AIF registries (header fields 1-13). All AIF edits were silently going to the AIFM report. The `fund_index` was also hardcoded to 0. Multi-fund templates had all edits targeting fund 0.

### Lessons for next time
1. **Never hardcode report context in API endpoints.** When an API serves multiple report types and entities, the client MUST specify which one it's editing. "Guess from field_id" is fragile because field numbering overlaps.
2. **Auto-validation on load eliminates the "run validation first" UX friction.** The previous design required users to click a button before seeing any validation feedback. Running lightweight validation on every load gives instant feedback. Heavy rules (YAML business logic) still need the explicit button.
3. **React: Enter and blur fire sequentially on input removal.** When `setEditing(false)` removes an `<input>` from the DOM, React fires `onBlur` even though the element is being destroyed. Use a ref-based flag to prevent double-action.
4. **Multiple findings per field is essential.** A single field can have both a format error AND a mandatory check failure. Showing only the "worst" one hides actionable information. The hover tooltip must show all.
