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

## 2026-04-07: Session 9 — AIFM field mapping fix, group editing, NCA filtering

### What happened
The XML field extractor (`aifmd_xml_field_extractor.py`) had fundamentally wrong ESMA field ID assignments for AIFM reports. Currency/AuM fields were mapped to field IDs 24-30 instead of 33-38, and principal markets/instruments were at 31-37 instead of 26-32. This caused cascading issues: "USD" appeared in field Q26 (which should be Ranking=1), tables appeared duplicated because group field IDs didn't match section field IDs, and deduplication logic couldn't work.

### Root cause
The original XML extractor was written without cross-referencing the ESMA validation rules YAML. The field ordering in the XML schema (AuM appears before principal markets in the XML tree) was incorrectly assumed to match the ESMA question numbering. In reality, ESMA assigns Q26-Q32 to principal markets/instruments and Q33-Q38 to AuM/currency — the opposite order from the XML structure.

### What was fixed

1. **XML extractor field ID remapping** — `_AIFM_CURRENCY` corrected from {24,26,27,28,29,30} to {33,34,35,36,37,38}. `_AIFM_PRINCIPAL_MARKETS` corrected from {31,32,33,34} to {26,27,28,29}. `_AIFM_PRINCIPAL_INSTRUMENTS` from {35,36,37} to {30,31,32}. Added missing `_AIFM_OLD_IDENTIFIER` extraction for fields 24-25.

2. **Table duplication resolved** — With correct field IDs, the group rows now have the same IDs as section fields. The existing deduplication logic in `report.py` (line 598-615) now properly excludes group-covered fields from sections.

3. **Frontend GROUP_QUESTION_RANGES aligned to ESMA** — All 22 group ranges corrected (e.g., `aifm_principal_markets` from "Q208-Q217" to "Q26-Q29", `main_instruments` from "Q24-Q35" to "Q64-Q77", etc.). GROUP_SORT_KEYS also updated.

4. **Group tables made editable** — New `GroupCellEditRequest` model and `PUT /session/{session_id}/group` endpoint. Click any cell to inline-edit. Row 0 edits sync to `fields_json` for scalar field consistency.

5. **NCA filtering for AIF reports** — Removed automatic inclusion of AIFM home NCA (`rms`) in every AIF's `nca_codes`. Now only NCAs explicitly listed in `aif_national_codes` for that specific AIF are shown. Fallback to `rms` only if no NCA codes found at all.

### Impact
- Existing sessions created before this fix will still show old (wrong) field IDs until XML is re-extracted
- New uploads will have correct ESMA field numbering throughout
- AIFM report now shows Ranking=1 in Q26 instead of "USD"
- Tables appear inline at correct positions (sorted by question number)
- No more duplicate fields between sections and group tables

### Lessons for next time

1. **Always cross-reference field IDs against the validation rules YAML.** The YAML is the authoritative source for ESMA question numbering. XML element ordering does not determine field IDs.
2. **When multiple systems share field IDs, test with a round-trip.** The field registry, XML extractor, and frontend GROUP_SORT_KEYS all independently defined field-to-number mappings. A single integration test that extracts XML and compares field IDs against the registry would have caught this immediately.
3. **Auto-include of parent NCA is wrong for per-entity lists.** The AIFM's home NCA is not necessarily an NCA for every fund. NCA membership must come from explicit per-entity records, not from the report header.
4. **Deduplication depends on ID alignment.** The backend's "exclude group field IDs from sections" logic was always correct — it just couldn't work because the group IDs and section IDs were different numbers for the same conceptual fields.

## 2026-04-07: Session 9b — Report viewer Round 3 refinements

### What was fixed

1. **AIFM field migration for existing sessions** — Added a one-time migration in `_get_report()` that detects old-style field IDs (by checking if field "24" contains a numeric AuM value instead of a country code) and remaps them to the correct ESMA numbering. This fixes existing sessions without requiring re-upload. Migration is persisted on first load.

2. **Header reordered** — Report header now shows Type, Obligation, Frequency first, then NCA codes at the end. Previously NCA was first.

3. **Type column letters (M/C/O/F) now black** — Changed from colored (red=M, amber=C) to black for M/C and gray for O/F per user feedback.

4. **SRC column improved** — Now distinguishes between "Imported from source file" (header/identifier fields) and "Calculated from source data" (composite fields). Previously all fields showed the same provenance. Logic: system fields and header sections get IMPORTED, composite fields get DERIVED, manually overridden keeps MANUALLY_OVERRIDDEN.

5. **Group tables now show obligation letters** — Each column header in group tables displays the M/C/O/F obligation letter via a new `group_obligations` response field. Backend looks up obligation from field registry per column.

6. **Group table drill-down** — Added "[source →]" link in group table headers that opens the underlying source data (positions) inline. Uses the existing drill-down mechanism.

7. **NCA filtering tooltip** — Added hover explanation on "NCA: XX (filtered)" label clarifying that data is the same but NCA-specific validation rules are applied.

### Not yet fixed
- NCA switching appearance: the data intentionally stays the same (one report, multiple NCAs), but the user expects more visible changes. Could add NCA-specific field visibility or highlight fields with NCA deviations.
- Q17 validation: US is a valid country code, no validation rule should flag it. If flagged, it's from a stored YAML validation run — re-run validation to clear.
- AIF/AIFM rule separation: the auto-validation and combining logic correctly filters by report_type. The user may be seeing NCA override rules with wrong report_type in YAML files, or error messages that reference AIFM concepts in AIF fields (AIF Q17 = "AIFM National Code" which references AIFM by name).

### Lessons for next time
1. **Fix the extractor AND add migration.** Fixing the data generator is necessary for future correctness, but existing data in the DB won't change. Always add a backward-compatible migration path.
2. **Source provenance must match reality.** The XML extractor labelled everything identically. Users notice when the SRC column says "derived" for a field they know was directly imported. Set provenance based on field classification, not a blanket label.
3. **NCA-per-entity vs NCA-per-session.** The NCA list on individual reports should come from entity-specific data (aif_national_codes), not from the session-level reporting member state.

---

## 2026-04-08: Uvicorn --reload flag silently drops new API endpoints

### What happened
New POST and DELETE endpoints for source entity add/delete were added to `api/routers/report.py`. The module loaded correctly (diagnostic print confirmed), and a direct Python test proved the routes were registered on the router object. However, the running uvicorn server did not serve these endpoints — all returned 404 "Not Found". Even a trivial GET `/version` test endpoint at the top of the file was not served.

### Impact
- Add row and delete row buttons in the Report Viewer returned "Add failed" / 404 errors for ~2 hours of debugging
- Multiple red herrings investigated: Google Drive sync, Python `__pycache__`, CORS, Pydantic model import, router registration order

### Root cause
The `--reload` flag on uvicorn. When running `python -m uvicorn api.main:app --reload --port 8000`, the file watcher / reloader mechanism did not properly pick up the new endpoints despite the module being freshly imported. Removing `--reload` and restarting uvicorn manually resolved the issue immediately — all endpoints appeared in the OpenAPI spec and worked correctly.

### Diagnosis steps that worked
1. Added `print()` diagnostics at module level in report.py — confirmed the file loaded
2. Added route listing in main.py — confirmed routes were registered on the router object AND included in the app
3. Added a `/direct-test` endpoint on the app object (bypassing routers) — isolated whether the issue was router-level or app-level
4. Ran uvicorn **without** `--reload` — endpoints immediately worked

### Diagnosis steps that wasted time
1. Re-syncing files from Google Drive multiple times
2. Clearing `__pycache__` directories (necessary but not sufficient)
3. Adding increasingly verbose logging without changing the startup mode
4. Checking CORS configuration, Pydantic models, import fallbacks

### Fix
Removed `--reload` from the uvicorn command in `start_UI_eagle.bat`. After code changes, the server must be restarted manually (close the API window and rerun the startup script).

### Lessons for next time
1. **When endpoints exist in code but return 404, test without `--reload` first.** This is a 30-second test that eliminates or confirms the most common cause. Do this before adding logging or re-syncing files.
2. **Diagnostic layering matters.** The combination of module-level print, route listing before/after include, and a direct app-level bypass endpoint pinpointed the issue in one restart. Use this pattern again for router debugging.
3. **`--reload` is convenient but unreliable for structural changes.** Hot-reload works for editing existing endpoint logic but can fail silently when adding new route decorators. For Eagle's development workflow (sync from Google Drive → restart), a manual restart is more reliable.
4. **Batch script `--reload` removal is safe.** The start_UI_eagle.bat already kills old processes and restarts clean. The `--reload` flag added no real value since the sync-and-restart pattern was already in place.

## 2026-04-08: NCA code assignment bug — `if not aif_id` fallback includes all NCAs

### What happened
The sidebar displayed NCA codes (GB, NL, LU) for funds that should not have been associated with all of them. For example, a fund registered only with the FCA (GB) showed NL and LU NCAs too.

### Root cause
In `api/routers/session.py` line 295, the AIF NCA matching logic had a fallback:
```python
if not aif_id or nc_aif == aif_id:
    nca_list.append(nc_rms)
```
When `aif_id` was empty (couldn't find the AIF's Custom AIF Identification), the condition `not aif_id` was True for **every** national code record, so ALL NCAs from `aif_national_codes` were included for that fund.

### Fix
Changed the matching logic to only match when both sides explicitly agree:
- If `aif_id` is found: only include NCA records where `nc_aif == aif_id` (explicit match)
- If `aif_id` is empty: only include NCA records where `nc_aif` is ALSO empty (legacy single-AIF template case)
- Never fall back to including all NCAs just because we can't identify the fund

### Lessons for next time
1. **Guard clauses with `not x` are dangerous for matching logic.** An empty string is falsy in Python, so `if not aif_id` silently turns a "no match found" into "match everything". Use explicit empty-string checks and consider what the fallback actually means.
2. **Always consider the multi-entity case.** The original code probably worked for single-AIF templates but broke silently when multiple AIFs were present.

## 2026-04-08: NCA national codes — display registration codes in sidebar

### What happened
The sidebar showed country codes (GB, NL, LU) but not the actual national registration code assigned by each NCA (e.g., "FCA12345"). This made it hard to verify which registration the NCA view corresponded to.

### Fix
Added `nca_national_codes` field (dict: country → national code) throughout the stack:
- **Persistence**: new column in `review_reports` table + auto-migration for existing DBs
- **API models**: added to `ReportSummary` and `ReportDetailResponse`
- **Session upload**: populated from `AIFM National Code` and `AIF National Code` fields in the M adapter national code records
- **Frontend**: displays as "NCA: GB (FCA12345)" in sidebar buttons and report header

### Lessons for next time
1. **Add auto-migration when adding new DB columns.** SQLAlchemy `create_all` only creates missing tables, not missing columns. A try/except ALTER TABLE in the ReportStore init handles existing databases gracefully.
2. **Keep backward compatibility.** Adding a new field with a default (`{}`) is safer than changing the type of an existing field (`nca_codes` from list to dict). Old data continues to work.

## 2026-04-08: Multi-NCA XML deduplication — one report per AIF, not per XML

### What happened
The Report Viewer showed Q1 (Reporting Member State) = "BE" for a fund that only reports to NL and GB. Q17 (AIF National Code) also showed the wrong code (a BE national code instead of the GB one).

### Root cause
The orchestrator generates one XML per (AIF × NCA) combination. With 5 NCAs and 15 AIFs, this produces ~60+ XML files. But `session.py` iterated over ALL these XMLs with `enumerate()` and mapped `idx → adapter.aifs[idx]`. This meant:
- Index 0-14 got fields from BE XMLs (alphabetically first NCA in the set)
- Indexes 15+ exceeded `adapter.aifs` length and fell back to XML field extraction
- Q1 and Q17 reflected whichever NCA's XML was extracted, not the fund's actual NCA

### Fix (two-part)
**1. session.py — Deduplicate by AIF name:**
- Extract ALL AIF XMLs into a dict keyed by (AIF name → {RMS → fields})
- For each `adapter.aifs` entry, look up fields by name
- Prefer the home RMS (AIFM's reporting member state) so Q1/Q17 reflect the primary NCA
- Result: exactly one ReviewReport per AIF, with correct field values

**2. report.py — Dynamic Q1/Q17 override when NCA filter is active:**
- When `?nca=XX` parameter is set, override Q1 with the NCA country code
- Override Q17 with the national code from `nca_national_codes[nca]`
- This ensures switching NCA in the sidebar updates these fields immediately

### Lessons for next time
1. **Never assume a flat list of generated XMLs maps 1:1 to the adapter's entity list.** Multi-NCA orchestration multiplies the output by the number of NCAs. Always deduplicate by entity identity (name, ID), not by list index.
2. **NCA-specific fields (Q1, Q17, Q16) must be treated as dynamic.** They change per NCA filing, so storing one value and overriding at render time is the correct pattern.
3. **Test with multi-NCA templates early.** Single-NCA templates mask this class of bugs because the 1:1 mapping happens to work.

## 2026-04-08: Field IDs are NOT globally unique — AIF and AIFM have independent numbering

### What happened
AIFM principal markets/instruments tables and AuM fields (33, 34) did not drill down to source positions. Investigation revealed a deeper architectural issue: every place in the codebase that used a bare `field_id` (e.g., `"33"`) without scoping it to a report type (AIF vs AIFM) was potentially broken.

### Root cause
AIF and AIFM have completely independent field numbering schemes:
- AIFM field 33 = "Total AuM Amount In Euro" (composite, derived from positions)
- AIF field 33 = "ShareClassFlag" (entity field from fund data)

The field source classification YAML was loaded into a flat dict where `"33"` existed in both `aifm_fields` and `aif_fields`. The AIF entry always overwrote the AIFM entry ("last write wins"), causing AIFM field 33 to be classified as an editable entity field instead of a read-only composite.

### Audit findings
| File | Issue | Severity |
|------|-------|----------|
| deps.py | Flat dict merge — AIF overwrites AIFM for same field_id | CRITICAL |
| report.py:1108 | Field edit classification lookup used bare field_id | CRITICAL |
| report.py:189 | _build_field_response fell back to bare key | HIGH |
| page.js FIELD_TO_SOURCE | Single mapping for both AIF and AIFM | HIGH |
| page.js DERIVED_GROUPS | Missing AIFM groups (aifm_principal_markets/instruments) | MEDIUM |
| session.py, registry.py, validator | Already correctly scoped | SAFE |

### Fix
1. **deps.py**: Removed bare key fallback. Classification dict now ONLY uses namespaced keys: `"AIFM.33"`, `"AIF.33"`
2. **report.py**: All classification lookups now use `f"{report_type}.{field_id}"` — both in `_build_field_response` and in `edit_field`
3. **report.py**: Added `aifm_principal_markets` and `aifm_principal_instruments` to `_DERIVED_GROUPS`
4. **page.js**: Split `FIELD_TO_SOURCE` into `AIF_FIELD_TO_SOURCE` and `AIFM_FIELD_TO_SOURCE` with correct field ranges per report type
5. **page.js**: Added AIFM groups to `DERIVED_GROUPS`
6. **page.js**: `handleDrillDown` now selects the correct field map based on `tab` (manager vs funds)

### Lessons for next time
1. **Field IDs are NEVER globally unique in AIFMD.** Always scope by report type. The combination `(report_type, field_id)` is the true primary key.
2. **Flat dicts for classification/lookup data are dangerous.** If two domains share the same ID space, a flat dict guarantees data loss. Use composite keys from day one.
3. **"Last write wins" is never acceptable** for configuration merges. Either namespace, or detect and reject collisions.
4. **Audit ALL field_id usage** when fixing this class of bug. A single unscoped lookup is enough to break classification for an entire report type.

## 2026-04-09: AIFM Manager Report viewer — 9 UI/data fixes

### What happened
Olaf reported nine distinct issues on the Manager Report viewer when filtering an AIF report by a specific NCA:
1. `Q` prefix on field IDs was AIF-native; should be `AFM` for AIFM fields.
2. `Q17` (AIFM jurisdiction) was being overwritten with the NCA's AIFM national code.
3. `Q18` (AIFM national code) was not being overwritten when an NCA filter was applied.
4. `Q1` (reporting member state) stayed red after the NCA override — stale validation from before the override still lived in the `fields_json` validation map.
5. A pseudo-section "AIFM — Assets Under Management" with a single `CROSS-FIELD` row ("AuM base currency vs AuM Euro consistency") appeared in the AIFM report, but it is a cross-field rule — not a real field.
6. Header dropdown fields (4, 5, 8, 13, 16, 20, 21, 35, 36) rendered as plain `<select>` showing only raw codes (INIT, AMND, Q1, RPT, …) with no descriptions.
7. AIFM fields 10, 11, 12 (Prior year filing info) were missing entirely on INIT reports, even though they are AIFM header fields.
8. Q3 (Creation date/time) never updated on save — it kept the value captured at the first write.
9. Green/orange/red validation backgrounds were so pale on PASS/WARN/FAIL that you couldn't distinguish them at a glance.

### Root causes
- **Issue 1** — `FieldRow` and `GroupTable` hard-coded the `Q` prefix. They had no knowledge of the report type.
- **Issue 2/3** — The NCA override block in `report.py` used an unscoped `fr.field_id == "17"` branch that only considered AIF semantics. AIF.17 = AIFM jurisdiction; AIFM.17 = AIFM jurisdiction; AIFM.18 = AIFM national code. The semantics by `(report_type, field_id)` are:
  - AIF.17 → AIFM jurisdiction, AIF.18 → AIFM national code
  - AIFM.17 → AIFM jurisdiction, AIFM.18 → AIFM national code
  The original code only handled AIF correctly.
- **Issue 4** — After overwriting `fr.value`, the previously-stored validation finding (which referenced the pre-override value) was still attached to the field response. The override changed the value but left the red/amber status.
- **Issue 5** — The field registry loader in `aifmd_field_registry.py` loaded every YAML entry, including a `field_id: CROSS-FIELD` rule (AIFM-CAM-016) used by the cross-field validator. It had no section of its own, so the viewer invented one.
- **Issue 6** — `EditableCell`'s dropdown branch used a raw `<select>` that rendered just the code. The existing `SearchableSelect` component was only wired up for position/source-data tables via `SOURCE_DOMAIN_LABELS`.
- **Issue 7** — `amnd_only_fields` (used to hide amendment-only fields on INIT reports) mistakenly listed AIFM 10/11/12. Those three fields are regular AIFM header fields (last report info) that must always appear.
- **Issue 8** — Neither `edit_field` nor `edit_group_cell` touched Q3 when a save happened. The creation timestamp came from the template adapter and then stayed frozen.
- **Issue 9** — The palette used `bg-green-50 / bg-orange-50 / bg-red-50`, which on most monitors is near-white.

### Fix
1. Added a `reportType` prop to `FieldRow`, `SectionAccordion`, `GroupTable`, and the drill-down toast; selected `AFM` vs `Q` based on `report.report_type`. Passed down from the caller.
2. Made the NCA override block in `api/routers/report.py` **report-type-aware** with four explicit branches:
   - Field 1 → always the NCA ISO-2
   - AIF.17 → NCA national code (jurisdiction in AIF semantics)
   - AIFM.17 → NCA ISO-2 (jurisdiction in AIFM semantics)
   - AIFM.18 → NCA national code
3. Added a `_clear_validation(fr)` helper inside the override block that both replaces `fr.validation` with a synthetic `PASS` result AND pops the field from the validation map, so the stored red state cannot resurface on the next GET.
4. Added `_is_cross_field_rule()` to `canonical/aifmd_field_registry.py`: any rule whose `field_id` starts with `CROSS` OR whose `xsd_element` contains `/` (composite XPath) is skipped during registry load. Cross-field rules are still evaluated by the validator — they just don't pollute the viewer.
5. Built a new `AIFMD_REF_LABELS` dict in `page.js` keyed by `allowed_values_ref` name (`filing_types`, `aifm_content_types`, `aif_content_types`, `reporting_period_types`, `boolean_values`, `fx_rate_source`, `cancelled_record_flag`, `aifm_reporting_codes`, `aif_reporting_codes`, `frequency_change_codes`, `aifm_contents_change_codes`). Rewrote `EditableCell`'s dropdown branch to render `<SearchableSelect>` with the matching label map (falling back to `SOURCE_DOMAIN_LABELS` for `iso_country_code` / `iso_currency_code`). Field 9 has no ref table (plain year), so it stays a text input — as it should.
6. Split `amnd_only_fields` into a report-type-scoped dict (`AIFM`, `AIF`) and added an `_always_show` override. Removed 10, 11, 12 from the AIFM amendment-only set and added them to AIFM's `_always_show`.
7. In `edit_field` AND `edit_group_cell`, right before `store.save_report(report)`, compute a fresh `datetime.now(timezone.utc)` and overwrite `report.fields_json["3"]` with a `SYSTEM` priority entry — unless the user is editing field 3 directly.
8. Swapped validation background classes from `bg-{color}-50` to `bg-{color}-200` in `validationBg()`.

### Result
- All nine issues resolved.
- Python modules compile cleanly; registry now yields 42 AIFM fields (CROSS-FIELD excluded), 307 AIF fields; fields 10/11/12 and 4/5/8/13/16/20/21/35/36 all present with correct `allowed_values_ref` values.
- Dropdowns now show e.g. `INIT — Initial filing`, `Q1 — Quarter 1 (Jan–Mar)`, `EUR — Euro`.

### Lessons for next time
1. **Any lookup keyed on `field_id` alone is a latent bug.** The override block fix had to branch on `(report_type, field_id)`; this is the same root cause as the 2026-04-04 classification-dict incident. Whenever touching code that inspects `field_id`, ask "is AIF.N the same thing as AIFM.N?" The answer is almost always no.
2. **NCA overrides must clear stale validation state, not just overwrite values.** Any time a field is forcibly rewritten, the persisted `validation_map` entry for that field must be dropped. Otherwise the UI shows inconsistent state (new value, old severity).
3. **The field registry is not the rules engine — don't conflate them.** Cross-field rules belong to the validator, not the field list. The registry loader should treat them as a different class of entry. The heuristic "field_id starts with CROSS OR xsd_element contains `/`" is simple and covers all current cases; if a future rule lives under a real field ID we'll need to add an explicit `rule_type` discriminator.
4. **`amnd_only_fields` is a blacklist. Blacklists fail open.** Whenever a new AIFM header field is added, it silently joins the list unless someone manually checks the visibility filter. A whitelist (`visible_on_init`) would be safer; short-term fix is the `_always_show` override.
5. **Q3 auto-update belongs at the write path, not the adapter.** Creation-date-of-report is a system field: it should be refreshed any time the system mutates the report, not preserved from the initial template parse. Both `edit_field` and `edit_group_cell` had to be touched — any new write endpoint needs the same hook. Consider moving this into `ReportStore.save_report()` so we only need to maintain it in one place.
6. **Dropdown UX in a regulatory tool needs descriptions, not raw codes.** Reviewers don't remember what `aifm_content_types=1` means. The `SearchableSelect` component already existed for positions; reusing it for header fields was a small change with a disproportionate usability win. Treat "code → human label" as a cross-cutting concern: any new `allowed_values_ref` needs a matching entry in `AIFMD_REF_LABELS` the moment it's added to the YAML.
7. **Tailwind palette intensities matter for accessibility.** The `-50` tints looked fine in design-mode side-by-side comparisons but were invisible in the actual viewer. When using colour to encode severity, start at `-200` minimum; anything lighter reads as "no status".

---

## 2026-04-09 (part 2): AIFM Manager Report viewer — 5 follow-up fixes

After the 9-issue batch went live, the reviewer flagged five more problems on the same page. Root causes are compact but each one points at a systemic gap worth remembering.

### What was broken
1. **NCA LU, content type = 3 flagged red.** Switching NCA to LU caused AFM5 to go FAIL even though `3` is a valid CSSF content type. Other NCAs were green.
2. **Dropdowns not visible and descriptions not visible.** Fields 4, 5, 8, 13, 16 rendered as read-only values with no dropdown on click, and no `code — description` label in display mode.
3. **AFM20 (AIFMEEAFlag) empty.** For FCA reports the adapter doesn't emit the flag at all, and for other paths it can still be absent. The viewer showed a blank cell.
4. **`#` column in group tables duplicated the data.** Principal markets / instruments tables already carry a `Ranking` column; the auto-generated row counter was printing the same number twice.
5. **Single-NCA entities showed a pointless "Consolidated (all NCAs)" row.** If an AIFM or AIF only reports to one NCA, consolidated == that NCA — the accordion and the extra sub-button were just clutter.

### Root causes and fixes
1. `_apply_nca_overrides` treated the CSSF override's `format: '1'` as a regex. `re.fullmatch('1', '3')` → None → spurious FAIL. The override also has a proper `allowed_values` dict with `{1,2,3}` but it was being ignored by the re-validation. Fix: pass the registry into `_apply_nca_overrides`, skip the format regex branch when the base field has `allowed_values_ref` or when the override itself provides `allowed_values`, and validate enum membership directly against that dict/list.
2. Two bugs stacked: (a) fields 4, 5, 8, 13, 16 were still in `_is_system_field` (both backend and frontend copies) so `EditableCell` never rendered the dropdown; (b) display mode only printed the raw code. Fix: remove those IDs from both system-field sets and add an `_enumLabel(value, allowed_values_ref)` helper that looks up `AIFMD_REF_LABELS[ref][value]` (with an ISO-country/currency fallback to `SOURCE_DOMAIN_LABELS`) and renders `value — label` in both the non-editable branch and the click-to-edit span.
3. `aifm_builder.py` line 114 has `if not is_fca: _sub(rec, "AIFMEEAFlag", ...)` — FCA path deliberately doesn't write the flag, and legacy templates may be missing it. Fix: derive AFM20 from AFM17 (jurisdiction) in a post-NCA-override pass inside `report.py`, using a hard-coded `_EEA_COUNTRY_CODES` set of 30 ISO-2 codes. Mirror for AIF: derive AIF19 from AIF21 (domicile). The derivation only runs when the flag is empty, sets `source = "Derived from AIFM jurisdiction"` and `priority = "DERIVED"`, and clears any stale validation entry. Must run *after* the override replaces AFM17 so switching NCA also re-derives the flag.
4. `GroupTable` had a `#` `<th>` plus `<td>{idx + 1}</td>` inside the row map. Fix: delete both. The component didn't need any other change.
5. Sidebar `entities.map(...)` assumed all entities had the accordion + consolidated button. Fix: compute `isSingleNca = entity.nca_codes?.length === 1` and branch: single-NCA rows show `NCA: {code} ({natCode})` inline under the name, no chevron, no accordion, click routes straight to the single NCA's filtered view, and the completeness bar pulls from `nc?.[singleNca]?.pct` instead of `nc?._consolidated?.pct`.

### Verification
- `py_compile api/routers/report.py` → OK
- `node --check frontend/app/page.js` → OK
- Grep confirms `_derive_eea_flag`, `_EEA_COUNTRY_CODES`, `_enumLabel`, and `isSingleNca` all landed where expected.

### Lessons for next time
1. **Never let `format:` masquerade as both a length and a regex.** In the NCA override schema, `format: '1'` was meant as "length 1", but `_apply_nca_overrides` ran it through `re.fullmatch`. Any schema field that has overloaded meaning is a bug magnet — pick one interpretation or split into `format_regex` and `max_length`. Until that schema change lands, the validator must consult the base field: if it has `allowed_values_ref`, the format key is not a regex.
2. **Override re-validation must defer to the base field's validation class.** Enum fields are validated by membership, numeric fields by range, text fields by regex. An override that only changes the allowed set should not suddenly invoke regex logic. The fix added a `base_has_enum` check; the better long-term design is for each override to declare which validation dimension it is adjusting.
3. **"System field" and "non-editable" are not the same thing.** A field can be system-managed (pre-populated, not user-entered) and still need to render a dropdown so the user can correct it. The `_is_system_field` filter was doing double duty. New rule: `_is_system_field` is for "never re-editable by the user" fields only (IDs, timestamps, hashes). Anything with an enum stays editable.
4. **`_is_system_field` exists in two places — the backend and the frontend — and they must stay in sync.** This is the second time in a week a fix required editing both copies. Either share the definition via an API endpoint (`GET /fields/system`) or generate the frontend set from the backend at build time. For now: always grep both repos when touching either.
5. **Derivation must run after the overrides that feed it.** AFM20 derives from AFM17, so the derivation has to execute after the NCA override has rewritten AFM17 with the NCA country code. Any derived field needs an explicit note in the code about where it sits in the pipeline.
6. **Missing XML elements aren't always bugs — they can be regulator-specific.** FCA intentionally doesn't emit AIFMEEAFlag. The viewer needs to be resilient to any legitimately-absent field and derive it if possible, rather than showing an empty cell that looks like an error.
7. **Auto-generated row counters duplicate semantic columns more often than you'd think.** Before adding a `#` column, check whether the data already has a ranking/order concept. A table with a `Ranking` column does not need a `#`.
8. **UX cases proliferate when a dimension has cardinality 1.** The sidebar assumed `entities.nca_codes.length > 1` without saying so. Any time you iterate a list in the UI, handle the zero, one, and many cases explicitly. Single-NCA entities are a real cardinality case, not an edge case — about half of AIFMs in practice only report to one regulator.

## 2026-04-09 — Round 3 viewer fixes: enum labels, ISO dropdowns, conditional locks, table colors

### Goal
Olaf reviewed the viewer after the previous two rounds and surfaced 5 concrete issues: (a) AFM5 dropdown labels should be business-friendly (Registered / Authorised / NPPR) rather than the raw regulation citations; (b) AFM16 was rendering the raw numeric code with no description; (c) AFM17 (AIFM jurisdiction) and AFM35 (base currency) had no dropdown at all, just a free-text input; (d) GroupTable cells had no validation coloring — the same cells would be green/red on the single-field view and grey in the group view; (e) AFM38 (FX reference rate — free text for "OTH") must be locked and greyed out unless AFM36 == "OTH", and the same logic needs to extend to the rest of the AFM34–38 FX chain.

### Symptoms
1. **AFM5 dropdown** showed "1 — AIFM reporting — Art. 3(3)(d) / Art. 24(1)", "2 — AIFM reporting — Art. 24(2)", "3 — AIFM reporting — Art. 24(4)". The user wanted the simplified manager categories instead.
2. **AFM16** rendered as just "1" or "5" with no " — description" suffix, even though `aifm_reporting_codes` was in the `AIFMD_REF_LABELS` dict.
3. **AFM17 and AFM35** rendered as bare text inputs — the backend `reference_values` array was empty, so `EditableCell` skipped its dropdown branch entirely.
4. **GroupTable** cells were neutral white/gray regardless of whether they were populated; impossible to see at a glance which mandatory sub-fields were still missing.
5. **AFM38** accepted free-text input even when AFM36 was "ECB" (ECB rates don't need a free-text reference source).

### Root causes and fixes
1. **AFM5 labels were the regulation citation, not the category.** The `aifm_content_types` dict was being read verbatim from the ESMA guidance. The user wants the dropdown to reflect the *business* classification (who is this manager?) not the regulation reference. Fix: override the three labels in `AIFMD_REF_LABELS.aifm_content_types` and leave a code comment explaining that the numeric mapping (1→Art 24(1), 2→Art 3(3)(d), 3→Non-EU) is fixed by ESMA — we are only renaming what is displayed.
2. **`aifm_reporting_codes` dict had the wrong keys entirely.** Previous dict had `{NRP, NFR, RPT}` (3 string codes) but the ESMA values are numeric `1..9`. The lookup `AIFMD_REF_LABELS.aifm_reporting_codes["1"]` returned `undefined`, so no description was rendered. Same problem existed for `aif_reporting_codes`. Fix: replaced both dicts with the correct numeric keys and proper ESMA-aligned labels (Registered AIFM, Authorised AIFM, NPPR variants, etc.).
3. **iso_country_code / iso_currency_code refs have no backend reference_values.** These refs use `validation_type: iso_check` in the YAML, so they don't appear in `reference_tables:` and `registry.reference_table()` returns `[]`. `EditableCell` short-circuits to a text input when `referenceValues.length === 0`. Fix: added two new module-level constants — `ISO_COUNTRY_CODES` (~250 ISO-2) and `ISO_CURRENCY_CODES` (~180 ISO 4217) — and teach `EditableCell` to substitute them when the ref name is `iso_country_code[s]` or `iso_currency_code[s]` and the backend list is empty. Labels are already covered by `SOURCE_DOMAIN_LABELS` for countries; currencies fall back to the raw code.
4. **GroupTable has its own cell renderer.** The single-field path goes through `validationBg(validation)` using the backend validation status; GroupTable rows don't carry a per-cell validation object, so we can't reuse it directly. Fix: added a `cellValidationBg(col, val)` helper inside `GroupTable` that computes a color from two inputs — the cell's populated state and the column's obligation from the existing `obligations` prop. Populated → green (treat as PASS), empty + Mandatory → red, empty + Conditional → orange, empty + Optional/Forbidden → neutral. Rewrote the td-map to use an arrow function body so we could compute `vBg` and `interactionCls` per cell, and replaced the blanket `hover:bg-blue-50` with `hover:brightness-95` so the hover tint doesn't fight the validation color.
5. **No dependency system existed in the frontend.** Fix: introduced `AIFMD_FIELD_DEPENDENCIES`, a map keyed by `"AIFM.{id}"` where each entry declares `{ on: <parentId>, allow: (parentValue) => bool, reason: <string> }`. Covers all four dependent fields in the FX chain:
   - `AIFM.34` (member state of base currency), `AIFM.36` (FX reference rate type), `AIFM.37` (FX reference rate value) — all gated on AFM35 being populated and ≠ "EUR" (EUR is handled implicitly, no FX conversion needed).
   - `AIFM.38` (free-text FX source) — gated on AFM36 == "OTH" (ECB rates don't need a free-text source).

   Added `_dependencyLockReason(field, fieldValues)` which resolves the dependency and returns a human-readable explanation or `null`. Extended `_nonEditableReason(field, fieldValues)` to consult the dependency map so tooltips mention the gating rule. Extended `FieldRow` to compute `dependencyLock` per render and apply `bg-gray-100 opacity-70` to the td when locked. Passed a new `fieldValues` prop down from `ReportViewer` → `SectionAccordion` → `FieldRow` built from a `fieldValuesMap = Object.fromEntries(allFields.map(f => [f.field_id, f.value]))` — rebuilt on every render so an edit to AFM35 or AFM36 immediately re-locks/unlocks its dependents.

### Verification
- `esbuild --loader:.jsx=jsx /tmp/page_check.jsx` → OK (no JSX/syntax errors after the td-map rewrite and the dependency-prop plumbing).
- Grep confirmed `AIFMD_FIELD_DEPENDENCIES`, `_dependencyLockReason`, `ISO_COUNTRY_CODES`, `ISO_CURRENCY_CODES`, and the new `aifm_reporting_codes` numeric keys all landed where expected.

### Lessons for next time
1. **"The ref dict has a value for this code" is a two-step lookup — verify both halves.** `AIFMD_REF_LABELS[ref]` gives a dict; then `dict[code]` gives the label. It's easy to populate the dict with made-up codes and never notice because the render-site does `labels?.[code] ?? ""`. Any time a description silently doesn't render, grep the dict keys against the actual values the backend sends before debugging the render path.
2. **Empty `reference_values` is not always a bug — sometimes it's the schema saying "validate this differently".** `iso_check` is a validation *method*, not a reference table; the backend correctly returns `[]` and the frontend has to know to fall back to its own ISO list. This is a recurring confusion: a ref name can exist without a corresponding `reference_tables` entry. The fix belongs in the frontend (don't push 430 ISO codes into the regulation YAML) but the convention needs documenting so the next dev knows which fallback to apply.
3. **Traffic-light colors are a shared concept — centralize the rule, not the code.** GroupTable couldn't reuse `validationBg` because it doesn't have a validation object per cell. Instead of copy-pasting a color helper, the new `cellValidationBg` is *equivalent to* `validationBg` but derives PASS/FAIL/WARNING from `(populated, obligation)` rather than from a backend status. The semantic rule is "green means present, red means mandatory-missing, orange means conditional-missing" — that rule should live in one comment block, even if it has two implementations.
4. **Field dependencies are a first-class concern — build the machinery before the second one shows up.** AFM38 is not special: AFM34, 36, 37 all have the same "gated on AFM35 ≠ EUR" shape. Building `AIFMD_FIELD_DEPENDENCIES` as a map was the right move because it scales to all four fields with no additional code paths. When a user says "this one field should grey out if...", assume there are 3–10 more just like it and build the system not the single case.
5. **Edit-time invalidation of dependent fields needs the *current* value map, not the stale one.** `fieldValuesMap` is rebuilt on every render from `allFields` — not stored in state — so that editing AFM36 from "ECB" to "OTH" immediately unlocks AFM38 on the next re-render. Storing the map in useState would introduce a one-frame lag and is the bug we almost shipped.
6. **Hover styles compete with semantic backgrounds.** `hover:bg-blue-50` on a cell that is already `bg-red-200` looks broken. `hover:brightness-95` is a multiplicative effect that preserves the underlying color — use it any time a cell has a meaningful background color.
7. **`FieldRow` signatures grow by one prop every round — plan for a context.** We've now added `reportType`, `fieldValues`, `onEdit`, `cascaded`, `onDrillDown` in successive passes. The next time we touch `FieldRow`, consider introducing a `ReportContext` so we stop threading props through `SectionAccordion`.

## 2026-04-09: AIFMD Report Viewer — round 4 fixes (AFM17 override, revalidation regressions, dependency locks, AFM5 label/code mismatch)

### Context
Five user-reported issues after round 3:
1. AFM17 showing the filing NCA country instead of the uploaded jurisdiction (e.g. `US` for a 747 Capital NPPR filing was being overwritten with `DE`).
2. Principal markets group-table rows 2–5 rendering with red/orange validation colours even though they were just empty placeholder rows.
3. Hitting "Revalidate" flipped previously-green fields AFM13, AFM19, AFM20, AFM21 to red.
4. AFM38 was still editable when AFM36 ≠ "OTH", even though round 3 claimed to fix it.
5. New business-friendly labels for AFM5 (AIFM content type) needed to be propagated to the base YAML + NCA overrides.

### What I did
1. **AFM17 override removed entirely.** The `_apply_nca_overrides` logic in `api/routers/report.py` was unconditionally replacing AFM17 with the filing NCA's country code. AFM17 is the AIFM's *own establishment jurisdiction* — for EU-authorised AIFMs using a passport it can legitimately differ from the filing NCA, and for non-EU AIFMs filing under NPPR it must be the actual home country (e.g. `US`). Removed the AFM17 branch and left a tombstone comment so nobody adds it back. Kept the AFM18 (filing NCA) override in place because that one *is* the filing relationship field.

2. **`_check_format` rewritten to be ESMA-notation-aware.** The old implementation interpreted every bare number as "exact length" and never looked at `data_type`, so:
   - boolean fields like AFM13/20/21 with format `"1"` rejected `"true"`/`"false"` (length 4/5 ≠ 1),
   - text fields like AFM19 with format `"300 (max)"` rejected `"747 Capital, LLC"` because it parsed `300` as an exact length,
   - length-prefixed formats like `"2 [A-Z]+"` were accepted for any length because the `+` in `[A-Z]+` disabled the length check.

   New version: bare digit = max-length, explicit `N (max)` / `N (min)` regex, length-prefix `N [A-Z]+` becomes a hard `len(v) == N` check, `totalDigits` / `fractionDigits` / `minInclusive` / `maxInclusive` parsed together, and a top-level boolean short-circuit (`data_type == B` → accept `true`/`false`/`0`/`1` only, ignore the format string). Caller updated to pass `data_type` through.

3. **Stale findings were being merged back in after validate.** POST `/validate` stored findings in `ReviewValidationRun.findings_json`; GET `/report` then merged them back into per-field `validation` objects so that field-level traffic lights wouldn't require a re-validate. Problem: stored findings from before a `_check_format` fix would come back and recolour cells even though the live re-check now passed. Fix: strip `MAN-`/`FMT-`/`TYP-` prefixed findings before persisting in POST `/validate`, and also filter them on GET `/report` when reading `latest_val.findings_json`. Only cross-field / YAML rules (`AIFM-*`, `AIF-*`, `NCA-*`) survive persistence now.

4. **`EditableCell` got a `locked` prop.** The round-3 dependency machinery set `bg-gray-100 opacity-70` on the `<td>`, but `EditableCell`'s read-only `<span>` painted a `validationBg(...)` on top which covered the gray entirely. Added an explicit `locked` prop: when true the span uses `bg-gray-200 text-gray-500 italic` and ignores the validation traffic-light. `FieldRow` now passes `locked={Boolean(dependencyLock)}` alongside the existing `editable={effectiveEditable}`.

5. **AFM20 and Q19 added to `AIFMD_FIELD_DEPENDENCIES` as always-locked derived fields.** Per user feedback the EEA-flag fields are always computed from the establishment jurisdiction (AFM17 / AIF domicile) and must never be editable directly. Modelled with `allow: () => false` and a reason string so the normal lock pipeline handles them.

6. **AFM5 label/code mismatch discovered and fixed across the stack.** While updating the YAML I cross-checked the frontend `AIFMD_REF_LABELS.aifm_content_types` against ESMA Technical Guidance Rev.6 and found codes 1 and 2 were *swapped*: the frontend labelled code 1 as "Registered/Light Manager" and code 2 as "Authorised/Licensed Manager", but ESMA canonical is the opposite (1 = Art 24(1) authorised, 2 = Art 3(3)(d) registered, 3 = Art 24(1) marketed / NPPR). Also discovered `aif_content_types` labels were *completely* mismatched (code 1 labelled "Art 3(3)(d)" but ESMA says code 1 = Art 24(1), etc.). Corrected the frontend labels, added a new `reference_table_labels` section to `aifmd_validation_rules.yaml` as the canonical label source (parallel to `reference_tables` so flat-list consumers are untouched), and updated the AFM-5 `technical_guidance` and the LU CSSF override's `esma_code` sub-fields to use the corrected labels.

7. **NCA AFM5 override audit (only 1 file affected):**
   - `aifmd_nca_overrides_lu_cssf.yaml` — `NCA-CSSF-AIFMContentType` (base rule `AIFM-5`). LU-specific `cssf_label` text remained correct (it already described codes 1/2/3 with the right meanings). Updated the `esma_code` sub-field to carry the new business-friendly labels alongside the Article citations. No other NCA file has an AFM5 override.

### What went wrong
- Initially I propagated the frontend's swapped labels into the base YAML and the LU override before noticing the conflict with the original `technical_guidance` text. Had to revert both and verify against multiple Blueprint versions before re-applying with the ESMA canonical mapping.

### Lessons for next time
1. **Cross-check labels against code semantics before propagating them.** When the user says "update the YAML with the new labels", don't assume the new labels are numerically correct. The original `technical_guidance` text is the source of truth for code→meaning; new labels should *rename* descriptions, not remap them. My first pass in this round baked a swap into the YAML — caught only because I paused to check the Blueprint history. For any label update touching enumerated codes, cross-reference with the ESMA citation text before committing.

2. **`_check_format` must be data_type-aware.** The ESMA format column is overloaded: `"1"` means "max length 1" for text but has no meaning for booleans (where the value is always `true`/`false`/`0`/`1`). Any generic format checker has to look at `data_type` and short-circuit the cases where format notation doesn't apply. Same goes for dates (`4(n)-2(n)-2(n)` is a visual date mask, not a regex) — we currently accept dates through the type-aware ISO path.

3. **Validation findings persistence is a footgun.** Storing computed findings on disk means every time you fix the validator you have to also purge or filter stored findings — otherwise you get phantom failures after a code fix. The rule now: only cross-field and rule-engine findings survive persistence; field-level format/mandatory/type findings are always recomputed live from the current source. If it's cheap to recompute, don't cache.

4. **"Fixed the td background" ≠ "fixed the visual" when a child `<span>` has its own background.** The dependency-lock `<td>` was being painted with `bg-gray-100`, but `EditableCell` wrapped the value in a `<span>` with `validationBg(...)` that painted over it. Always trace the DOM: the final colour is the innermost element with a background, not the outermost.

5. **Overrides are rarely the right place to fix a firm-level field.** The AFM17 bug was a classic mis-scope: "NCA overrides" sounds like the place to put `country = nca_country`, but AFM17 is a property of the *firm*, not of the filing relationship. The filing relationship is AFM18. Rule of thumb: if the field would have the same value regardless of *which* NCA the firm files to, it doesn't belong in an NCA override branch — and if it *can* legitimately differ from the filing NCA (passport, NPPR), the NCA override must never touch it.

6. **Empty rows in a group table need an explicit "empty row" concept — cell-level checks aren't enough.** Principal markets placeholders render with `"NOT"` or blanks in every data column. A per-cell coloring rule can't tell "row 2 has a blank mandatory column because it's an empty row" from "row 1 has a blank mandatory column because the user forgot to fill it". The fix was to compute `isEmptyRow` once per row (any data-bearing cell populated? if not, it's empty) and propagate that flag into the cell-colour helper. Same pattern will apply to the other group tables when they get real data.

## 2026-04-10: YAML enrichment with Option A masking attributes (ESMA-sourced)

### What was done
Extended `aifmd_validation_rules.yaml` (v2.1 → v2.2) with three new per-field attributes, sourced from ESMA/2013/1358 Rev.6 Technical Guidance:
- `content_types`: which ESMA content types (1-5) the field applies to
- `no_reporting`: boolean — field hidden when no-reporting flag is set
- `filing_types`: list of filing types (INIT/AMND/CANCEL) the field is visible for

### Critical finding: code has wrong CT model
The first enrichment attempt derived content_types from the codebase (`aifmd_field_registry.py`). Olaf correctly challenged this — the YAML is the regulation and should be based on ESMA, not reverse-engineered from code. Cross-referencing against the ESMA Technical Guidance Rev.6 revealed that the field_registry.py uses an **internally invented CT numbering** that diverges from ESMA's actual content types:

- **ESMA CT 1** = "24(1) reporting obligation" — code treats as "no-reporting" (header only)
- **ESMA CT 2** = "24(1) + 24(2)" — code treats as "24(1) only"
- **ESMA CT 3** = "3(3)(d)" — code treats as "24(1) + 24(2)" (shows too many fields)
- **ESMA CT 4/5** — code gets these approximately right

This means 279 out of 307 AIF fields have wrong content-type masking in the code.

### ESMA-correct CT mapping (field 5 guidance + article headings)
- Header (Q1-Q23): {1,2,3,4,5}
- Article 24(1) (Q24-Q120): {1,2,3,4,5} — AIFPrincipalInfo for ALL CTs
- Article 24(2) (Q121-Q280, Q302): {2,4} — AIFIndividualInfo for CT 2 and 4
- Article 24(2)+24(4) (Q281-Q295): {2,4,5} — either article applies
- Article 24(4) (Q296-Q301): {4,5} — AIFLeverageArticle24-4

### Key numbers
- 350 rules enriched, 0 missing any property, all spot-checks pass
- AIF CT distribution (ESMA): [1,2,3,4,5]=125, [2,4]=161, [2,4,5]=15, [4,5]=6
- 279 AIF fields have ESMA↔Code CT mismatch (bugs in field_registry.py)
- 70 fields match (28 AIF header/CANC + 42 AIFM)

### Lessons for next time

1. **NEVER derive regulation config from code — always go to the source.** The first attempt produced a YAML that was "code-consistent" but ESMA-wrong. The code itself was the bug. Config files that encode regulatory rules must be sourced from the regulation documents.

2. **Challenge "zero mismatches" results.** When the first run showed 0 YAML↔Code mismatches, that should have been a prompt to verify against ESMA — not a sign of success. Zero divergence between YAML and code only proves they agree, not that either is correct.

3. **The ESMA Technical Guidance Excel is the authoritative source.** Field 5 (AIF content type) in the "Technical guidance AIF file" sheet defines exactly which XML blocks apply to which CT. The article headings in the same sheet define which fields belong to which article. Use these — not the code comments.

4. **Code comments can lie.** The field_registry.py comments said "CT=1: header only (no-reporting)" but the code reads CT from field 5 which uses ESMA numbering where CT 1 = "24(1) reporting obligation". The comment created a false mental model that infected the whole masking logic.

## 2026-04-10: Single source of truth change plan — cataloging all hardcoded logic

### What was built
`aifmd_single_source_change_plan.xlsx` — a 3-sheet Excel documenting every change needed to migrate from scattered hardcoded logic to YAML-as-single-source-of-truth architecture:
- **Per-Field Change Plan** (349 rows × 18 columns): for each field, shows ESMA article, ESMA CT vs Code CT, which hardcoded locations reference it, what's already in YAML, and specific backend + frontend changes needed
- **Global Changes** (19 rows): component-level changes with file, line numbers, current state, target state, change type (REPLACE/DELETE/EXTEND/KEEP), and priority (P0-P3)
- **Summary**: scope, bug counts, YAML status, and categorized list of deletions per layer

### What the audit found
- 279 of 307 AIF fields have wrong CT masking in code (P0 critical bug)
- 338 of 349 fields have at least one piece of hardcoded logic that should move to YAML
- 7 categories of hardcoded logic across 5 files: system_fields (19), AMND-only (12), CT section sets (279 buggy), dynamic gates (56), dependency locks (6), EEA derivations (2), validation duplicates (2 full functions)
- Frontend has 5 hardcoded structures to delete: sysAifm/sysAif, AIFMD_FIELD_DEPENDENCIES, AIFMD_REF_LABELS, ISO_COUNTRY_CODES, ISO_CURRENCY_CODES
- YAML v2.2 already has content_types, no_reporting, filing_types; still needs: system_field, gate_field, gate_condition, dependency_lock, derivation_rule

### Approach
1. Read all 5 source files (field_registry.py, report.py, validation.py, page.js, YAML) and extracted every hardcoded reference per field
2. Cross-referenced ESMA article mapping (from esma_field_article_map.json) against code's section-based CT model
3. Generated per-field change instructions that are specific enough for a developer to implement without re-analyzing the codebase
4. Prioritized global changes: P0 (CT bug fix), P1 (dedup/migrate), P2 (frontend cleanup), P3 (optional keep)

### Lessons for next time

1. **Catalog before you code.** The temptation was to start fixing the 279 CT bugs immediately. Instead, building the complete catalog first revealed that the CT fix is entangled with 6 other hardcoded patterns — fixing CT alone would leave the architecture half-migrated.

2. **Per-field granularity matters for CTO review.** A high-level "move hardcoded logic to YAML" plan is too vague for sign-off. The per-field Excel with specific columns (ESMA CT vs Code CT, which files, what changes) lets the CTO verify each decision independently.

3. **The change plan is a communication artifact, not just a technical one.** Its primary audience is the CTO who needs to approve the changes. Structure it for their review workflow: summary first, then drill-down to per-field details, with clear priority labels.

## 2026-04-10: YAML v2.3 — completing the single source of truth with gate conditions and derivation rules

### What was built
Enriched `aifmd_validation_rules.yaml` from v2.2 to v2.3 with 5 new attributes per field:
- **system_field** (boolean): 19 fields flagged as auto-populated metadata (sourced from report.py system_fields)
- **gate_field + gate_condition**: 127 fields with ESMA-sourced conditional visibility rules (sourced from ESMA/2013/1358 Rev.6 M/C/O column)
- **gate_esma_text**: original ESMA conditional text for traceability
- **dependency_lock**: 6 fields with UI editability constraints (AFM20, AIF19, AFM34-38)
- **derivation_rule**: 2 fields with auto-computation rules (EEA flags from jurisdiction/domicile)

Updated the change plan Excel to reflect that all attributes are now in YAML — the "STILL NEEDED" section became "YAML v2.3 NEW ATTRIBUTES (all complete)".

### Sources used
- **Gates**: ESMA/2013/1358 Rev.6 "Technical guidance AIF file" and "Technical guidance AIFM file" sheets, M/C/O column. Each conditional field has a specific condition like "F for AIF share class flag false; O otherwise" that was parsed into gate_field + gate_condition pairs.
- **System fields**: report.py hardcoded system_fields dict (these are metadata facts, not regulation)
- **Dependency locks**: ESMA FX/base currency rules (AFM34-38) confirmed by both ESMA guidance and code implementation
- **Derivation rules**: report.py EEA flag derivation (lines 904-941) — code enrichment, not ESMA regulation

### What the ESMA gate analysis revealed
The ESMA Technical Guidance contains far more conditional fields than the code implements:
- Code has 8 dynamic gate groups covering 56 fields (Q33→34-41, Q57→131-138/286-296, Q161→162-165, Q167→168-171, Q172→173-177, Q203→204-213, Q279-280→CT, Q297→298-301)
- ESMA defines 126 conditional fields — the extra 70 include: master-feeder gates (Q41→42-44), FX rate gates (Q49→50-52), instrument code type gates (Q66→68-74), sub-asset type gates, risk measure type gates (Q138→139-147/302), portfolio liquidity block gates, financing amount gates (Q210→211-217), and more

### Gate condition notation
Designed a compact notation for gate conditions that's both human-readable and machine-parseable:
- `equals(field, value)` — field must equal value
- `not_equals(field, value)` — field must not equal value
- `filled_in(field)` — field must have a non-empty value
- `in(field, [val1, val2])` — field must be one of the listed values
- `any_filled_in(f1, f2, ...)` — at least one of the fields must be filled
- `always_locked` — field is always non-editable (derived)

### Lessons for next time

1. **ESMA's M/C/O column is a goldmine.** The conditional field logic that was hardcoded in 8 gate groups in report.py actually covers only ~44% of the ESMA-defined conditions. By reading the M/C/O column systematically, we found 71 additional conditional relationships that the code doesn't implement yet — potential silent compliance gaps.

2. **Distinguish gates from locks from derivations.** These three concepts serve different purposes: gates control field visibility (hidden/shown), locks control editability (editable/read-only), and derivations auto-compute values. Keeping them as separate YAML attributes prevents confusion about what each one does.

3. **Include the ESMA source text in the YAML.** The `gate_esma_text` field preserves the original ESMA wording (e.g., "M for AIF share class flag true; F otherwise"). This makes it possible to audit the gate_condition notation against the regulation without going back to the Excel each time.

## 2026-04-10: Gate correction — why so many gates were wrong on first pass

### What happened
Olaf flagged that AIF138, AIF286-301, and AIF210-213 had incorrect gates, and that AIF41-44, AIF45-47, AIF197-207, AIF210-217 needed review. On re-examination, 12 fields had phantom or self-referencing gates.

### Root causes (3 categories of errors)

1. **Self-referencing gate (Q138)**: Set `gate_field=138` on Q138 itself — nonsensical. Q138 is a repeating block field whose M/C/O says "M for risk measure types NET_EQTY_DELTA, NET_CS01, NET_DV01 under 24(2)". This is a block-level conditionality (which instances must exist), NOT a gate on another field. The correct treatment: Q138 has no gate_field; Q139-Q147 and Q302 are gated on Q138's value.

2. **Phantom gates on non-conditional fields (Q283-Q297)**: Inherited from the code's dynamic gate `Q57→286-296` even though the ESMA M/C/O for these fields is plain M or O. The code's PE fund gate for controlled structures (Q286-296 on Q57=PEQF) is a CODE invention that doesn't appear in the ESMA M/C/O column. Per ESMA: Q283-Q289 are M/O, Q290-292 are O, Q294-Q297 are M. Only Q293 (exposure value) and Q298-Q301 (borrowing source details) have actual ESMA conditions.

3. **Manual transcription errors**: Hand-building a 127-entry dictionary from reading the M/C/O text introduced errors. Some fields were attributed conditions from the wrong neighboring field, and some conditional fields were missed entirely.

### Corrections applied
- Q138: gate REMOVED (block-level, not field gate)
- Q283-Q292, Q294-Q297: gates REMOVED (plain M/O per ESMA)
- Q204-Q207: confirmed NO gate (independent O flags per ESMA; code's Q203 gate is a code decision)
- Q45-Q47: confirmed NO gate (plain O per ESMA; related by name but not conditional)
- Q194-Q196: confirmed correctly gated on Q193
- Q211-Q217: confirmed correctly gated on Q210; Q210 itself has no gate
- Total gate count: 127→126 (net -1; removed 12 wrong, gained 11 from prior run already correct)

### Lessons for next time

1. **A field cannot gate itself.** Self-referencing gates (gate_field = own field_id) are logically invalid. Always verify that the gate_field points to a DIFFERENT field.

2. **Block-level conditionality ≠ field-level gate.** When ESMA says "M for risk measure types X, Y, Z under 24(2)", that defines WHICH INSTANCES of a repeating block must exist, not a visibility gate from another field. These are structural rules (which block entries to create), not field visibility gates.

3. **Code gates ≠ ESMA gates.** The code's dynamic gate `Q57→286-296` is a developer decision to hide controlled structure fields for non-PE funds. ESMA's M/C/O says these fields are M/O without conditions. The YAML must reflect ESMA, not the code's interpretation. Code-only visibility decisions can be tracked separately as "UI enhancement" rather than "ESMA gate".

4. **Verify every entry against its ESMA M/C/O.** The correction required reading every single field's M/C/O individually. Batch processing (e.g., "Q286-296 are all gated on Q57") is error-prone because ranges often contain a mix of M, O, and C fields.

## 2026-04-10: NCA override YAML verification — missing v2.2/v2.3 tags

### What happened
After enriching the base `aifmd_validation_rules.yaml` from v2.0 through v2.2 (content_types, no_reporting, filing_types) and v2.3 (system_field, gate_field, gate_condition, gate_esma_text, dependency_lock, derivation_rule), the 31 NCA override YAML files were never updated to include these new tags. Systematic verification revealed that ALL 151 NCA rules across all 31 files are missing ALL 9 new tags.

### Impact
- NCA override loader cannot determine content type visibility, gate conditions, or lock/derivation behavior for overridden fields
- base_yaml_version references are stale (pointing to v1.0 or v2.0 instead of v2.3)
- Inconsistency: NCA files carry old tags (m_c_o_f, mandatory, format, etc.) in full-definition style but miss all newer tags

### Root cause
The NCA files were created before the v2.2/v2.3 enrichment rounds. When new attributes were added to the base YAML, no process existed to propagate those additions to the NCA override files. Each enrichment round only touched the base YAML.

### Key numbers
- 31 NCA files, 151 total rules (93 overriding base fields, 58 NCA-specific)
- 9 missing tags × 151 rules = 1,359 missing attribute slots
- Top 5 by rule count: CSSF/LU (37), BaFin/DE (11), CBI/IE (11), FCA/GB (10), FSMA/BE (10)

### Architecture decision needed
The NCA files use Option A (full field definition per override). To stay consistent, all 9 new tags should be added. For the 93 rules that override base fields, values should be inherited from the base YAML. For the 58 NCA-specific rules, values should be set per NCA documentation.

### Lessons for next time

1. **When enriching the base YAML, always check downstream consumers.** The NCA override files are direct consumers of the base YAML schema. Any new attribute added to the base should trigger a review of all NCA files.

2. **Maintain a tag-propagation checklist.** When adding tags to the base, run a verification script against all NCA files before closing the enrichment task.

3. **base_yaml_version in NCA files is a contract.** It signals which base schema the NCA file is compatible with. Keeping it at v1.0/v2.0 while the base is at v2.3 creates a silent compatibility gap.

## 2026-04-10: NCA override migration to delta-only schema (Option B)

### What happened
Migrated all 31 NCA override YAML files from Option A (full field copy) to Option B (delta-only). Instead of duplicating all base YAML tags in every NCA rule, override rules now carry ONLY the tags that differ from the base rule they reference. The loader merges base + NCA delta at runtime: `merged_rule = base_rule | nca_override`.

### What changed
- 31 NCA files rewritten with delta-only rules
- 701 redundant keys removed (19% reduction across all files)
- All `base_yaml_version` references updated from v1.0/v2.0 to v2.3
- Clear schema documentation added to both base YAML header and every NCA file header
- Loader contract documented: `merged_rule = base_rule | nca_override`

### Key design decisions

1. **Override rules (93 rules)**: carry only `rule_id`, `base_rule_id`, `field_id` + NCA-only metadata + any tag where the NCA value differs from base. Tags not present → inherited from base at load time.

2. **NCA-specific rules (58 rules)**: carry full definitions since there's nothing to inherit from. These are rules like filename conventions, nil returns, and compression formats that have no ESMA equivalent.

3. **Infrastructure sections preserved**: transmission, file_format, correction_rules, eagle_implementation, return_files sections are NCA-unique data and always present in full.

### Pre-existing issues found and fixed during verification
- 11 NCA rules had `base_rule_id` values that didn't match any base YAML rule. Root cause: these are cross-field validations (e.g. "sum of financing % must be 99-101%"), multi-field range overrides (e.g. FCA geographic remapping across fields 78-93), or sub-element rules (e.g. RiskMeasureDescription under Q138). None of these map to a single base per-field rule.
- Fix: set `base_rule_id: ''` (making them NCA-specific under Option B), added `related_base_fields` list for documentation, and added `rule_type` (cross_field / multi_field / sub_element) to categorize them. This keeps the Option B loader contract clean while preserving the relational information.

### Lessons for next time

1. **Delta-only overrides prevent cascading maintenance.** Adding new tags to the base YAML no longer requires touching 31 NCA files. This is the primary reason to prefer Option B.

2. **None/null means "not present" in delta, not "override to null."** If the original NCA file didn't have a key, it should not appear as `null` in the delta — that would overwrite the base value with null at merge time. The correct behavior is to omit the key entirely.

3. **Key ordering matters for readability.** Enforce a consistent order: identifiers first (rule_id, base_rule_id, field_id), then deltas, then NCA metadata. This makes it easy to scan what each NCA rule actually changes.

## 2026-04-10: AIFMD screen compliance audit — YAML vs code gap analysis

### What happened
Ran a comprehensive screen audit comparing base YAML v2.3 (350 fields, 126 ESMA gates) against three code layers: frontend (page.js), backend (report.py), and field registry (aifmd_field_registry.py). The audit checked 7 dimensions per field: system_field, gate_field/gate_condition, dependency_lock, derivation_rule, content_types, no_reporting, and filing_types.

### Key findings

**279 content type mismatches (AIF fields):**
The field_registry.py maps sections to content types using a section-group approach (_HEADER_SECTIONS → CT{1-5}, _SECTIONS_24_1 → CT{2-5}, _SECTIONS_24_2 → CT{3,4}, _SECTIONS_24_4 → CT{4,5}). However, ESMA assigns content types per-field, not per-section. Many fields have ESMA CTs that don't match the section-level grouping. For example: fields in "24(2)" sections have YAML CTs `[2,4]` (ESMA says they apply to CT2 and CT4) but the registry maps those sections to `{3,4}`. This means the code may show/hide fields for the wrong content types.

**31 gate condition mismatches:**
The backend has 9 dynamic gate blocks (if/elif chain in report.py) that hide fields behind trigger conditions. Of these, 31 individual fields are gated in code but have no `gate_field` in the YAML. The v2.3 changelog specifically corrected several of these as ESMA-independent (e.g. Q204-Q207 are independent O flags per ESMA, NOT gated on Q203). This means the code is more restrictive than ESMA requires — it hides fields that should be visible.

**AIFM vs AIF distinction:**
AIFM content types (CT 1-3) represent AIFM type (authorised / registered / NPPR) and do NOT control field visibility. All AIFM fields are always shown. AIF content types (CT 1-5) DO control which fields appear on screen. This distinction must be reflected in the audit and in any code changes.

### Root cause
The field_registry.py content type logic was built section-by-section before the per-field ESMA content type data was available in the YAML. Now that v2.3 has authoritative per-field content_types, the code should consume those directly instead of inferring CTs from section names.

### Lessons for next time

1. **ESMA defines content types per-field, not per-section.** A section-level grouping is an approximation. Always source CT visibility from the YAML's per-field content_types tag, which was verified field-by-field against ESMA/2013/1358 Rev.6.

2. **Code gates should match YAML gates, not exceed them.** If the code hides fields that ESMA doesn't gate, users can't fill in data that ESMA expects. The YAML gate_field/gate_condition tags are the authoritative source.

3. **Audit both report types separately.** AIFM and AIF have fundamentally different content type semantics. An audit that treats them identically will produce false positives for AIFM fields.

4. **The field_registry should consume YAML content_types directly.** The current section→CT mapping in _SECTIONS_24_1 etc. should be replaced (or at least validated against) the per-field content_types from the YAML. This closes the gap between ESMA's per-field assignment and the code's section-level approximation.

## 2026-04-10: Reporting obligation matrix added to base YAML

### What was built
Added a `reporting_obligations` reference table to `aifmd_validation_rules.yaml` containing all 49 ESMA-defined combinations of AIFM type × AIF characteristics. Each row carries: AIFM content type, AIF content type, AIFM/AIF reporting codes and labels, derivation input conditions (leveraged, eu_aif, marketed_in_union, above_500m_threshold, unleveraged_non_listed), reporting frequency, and reporting contents.

### Architecture decisions
- **YAML reference table** (not database): keeps the obligation matrix version-controlled alongside the field rules, loaded at startup. Consistent with existing reference_tables pattern.
- **Derive + validate** at runtime: given AIFM type + AIF characteristics, the backend will auto-derive the correct AIF content type, reporting code, and frequency. User selections are validated against the matrix.
- **Derive from existing fields**: EEA flag from AIF.19 (already derived from AIF.21), leverage from AIF position/exposure data, marketed status from NCA registration context, threshold from AuM.
- **null conditions**: `null` in a condition column means "any value matches" (wildcards). 4 rows have `aif_content_type: null` representing NPPR AIFs not marketed in the Member State (no reporting obligation).

### Lessons for next time

1. **null means "don't care" in the lookup, not "unknown".** When matching AIF characteristics against the matrix, a `null` condition should be treated as a wildcard that always matches. This is distinct from the value `false`.

2. **AIF content type is fully determined by the obligation row.** Once the correct row is matched, the AIF content type, reporting code, frequency, and reporting contents are all derived outputs — the user should not set these independently.

## 2026-04-10: Field registry CT section mapping — full reconciliation and fix

### What happened
The `aifmd_field_registry.py` section→CT mapping had 16 sections assigned to the wrong article groups. After adding the reporting obligation matrix and confirming field-number-based article boundaries (24(1) = Q1-Q120, 24(2) = Q121-Q295 + Q302, 24(4) = Q281-Q301), a full reconciliation revealed mismatches across all three section sets.

### What was wrong

**CT assignment formula (the `section_applicable_cts` method):**
- `_SECTIONS_24_1` was mapped to `{2,3,4,5}` → corrected to `{1,2,3,4,5}`. CT1=24(1) was missing, CT3=3(3d) has same scope as 24(1) so correctly included.
- `_SECTIONS_24_2` was mapped to `{3,4}` → corrected to `{2,4}`. CT3 incorrectly included (3(3d) = header+24(1) only, no 24(2) content). CT2=24(1)+(2) was missing.

**CT comments at top of section definitions:**
- All 5 CT descriptions were wrong (CT1 was labelled "header only", CT2/CT3 were swapped). Corrected to match ESMA obligation matrix.

**Section membership (which sections belong to which article group):**
- 9 sections moved from `_SECTIONS_24_1` to `_SECTIONS_24_2` (Q121-Q218 fields wrongly in 24(1))
- 1 section moved from `_SECTIONS_24_2` to `_SECTIONS_24_1` (Q54-Q56 "Jurisdictions" wrongly in 24(2))
- 5 sections added to `_SECTIONS_24_4` (Q281-Q301 overlap zone, previously only in `_SECTIONS_24_2`)
- 1 section moved from `_SECTIONS_24_2` to `_SECTIONS_24_4` only (Q296-Q301 "Five largest sources")
- 1 section added to `_SECTIONS_24_2` (Q290-Q293 "Gross exposure" was only in `_SECTIONS_24_4`)

### Root cause
The original section assignments were based on section *names* rather than field *numbers*. Section names can be misleading (e.g. "Jurisdictions of the three main funding sources" sounds like 24(2) financing but it's Q54-Q56 = firmly 24(1)). The obligation matrix and field number ranges are the authoritative sources.

### Result
350 / 350 fields (43 AIFM + 307 AIF) now produce identical CTs from both the YAML per-field `content_types` and the registry `section_applicable_cts()` method.

### Lessons for next time

1. **Use field numbers, not section names, to determine article membership.** The boundary is Q120: fields 1-120 = 24(1), fields 121+ = 24(2) and/or 24(4). Section names are human labels that can mislead.

2. **Sections can span multiple articles.** Fields 281-295 are in both 24(2) and 24(4) — their sections must appear in both `_SECTIONS_24_2` and `_SECTIONS_24_4`. The `section_applicable_cts()` method uses `|=` (set union) which handles this correctly.

3. **Always reconcile field-by-field after structural changes.** The obligation matrix revealed errors that section-level reasoning alone couldn't catch. Running a programmatic 350-field comparison is fast and definitive.

## 2026-04-10: Report.py gate block corrections — 3 removals, 2 narrowings

### What happened
The gate reconciliation (9 dynamic gate blocks in `report.py` vs 126 ESMA per-field gates in YAML) identified 5 code gates that did not match the ESMA guidelines.

### What was fixed

**Removed (3 gates):**
1. `Q57→Q286-Q296` — code gated controlled structures on PredominantAIFType=PEQF, but ESMA does not gate these fields on Q57.
2. `Q203→Q204-Q213` — code gated investor preferential treatment details on a master flag, but per ESMA each Q204-Q213 field is an independent optional flag.
3. `CT→Q279-Q280` — code restricted stress test results to CT4/5, but this is already handled by CT-based section filtering upstream.

**Narrowed (2 gates):**
4. `Q57→Q131-Q138` narrowed to `Q131-Q136` — Q137-Q138 are not gated by Q57 per ESMA.
5. `Q33→Q34-Q41` narrowed to `Q34-Q40` — Q41 is not gated by Q33 per ESMA.

**Kept (4 gates):**
Q161→Q162-Q165, Q167→Q168-Q171, Q172→Q173-Q177, Q297→Q298-Q301 — all fully aligned with ESMA.

### Lessons for next time

1. **YAML per-field gates are the source of truth for ESMA rules.** Code gate blocks are convenience shortcuts. When they diverge, the YAML (ESMA-sourced) wins.

2. **Removing redundant gates is as important as adding missing ones.** Over-gating hides fields that users should be able to see and populate, causing silent data loss in reports.

## 2026-04-10: Frontend validation removal — backend-only validation architecture

### What happened
The frontend (`page.js`) contained conditional-dependency validation logic that duplicated backend behaviour: `AIFMD_FIELD_DEPENDENCIES` (7 rules for AFM20, AIF.19, AFM34-38), `_dependencyLockReason()`, system-field locks (sysAifm/sysAif sets), and dependency-override logic in `FieldRow`. This was removed in favour of backend-only validation.

### What was removed
- `AIFMD_FIELD_DEPENDENCIES` constant (7 conditional editability rules)
- `_dependencyLockReason()` function
- System-field sets and dependency lock check from `_nonEditableReason()`
- `dependencyLock` variable and `effectiveEditable` override in `FieldRow`
- `fieldValuesMap` computation and `fieldValues` prop chain (SectionAccordion → FieldRow)

### What was kept
- `_nonEditableReason()` still returns tooltip text for composite/entity fields (pure UI hint, not validation)
- `field.editable` from the backend API is now the single source of truth for editability

### Also fixed
- `CT_LABELS_AIF` CT1 label corrected from "Header only" to "Art 24(1)" (CT1 = fields 1-120, not header only)

### Lessons for next time

1. **Validation logic should live in one place.** Duplicating conditional editability rules in both frontend and backend creates maintenance burden and drift risk. The backend already computes `editable` correctly — the frontend should trust it.

2. **Frontend overrides of backend editability are a red flag.** When the frontend uses `effectiveEditable = field.editable && !dependencyLock`, it's second-guessing the backend. This pattern should be avoided unless there's a clear reason the backend can't handle it.

3. **CT labels must match ESMA definitions.** CT1 = Art 24(1) = fields 1-120, not "Header only". Incorrect labels mislead users about what data a report should contain.

## 2026-04-10: M adapter AIF content type derivation — CT2 vs CT3 confusion

### What happened
The M adapter's AIF content type (Q5) derivation for light/registered templates set CT2 instead of CT3. A light template corresponds to a registered AIFM under Art 3(3)(d), so the AIF content type should be CT3 = Art 3(3)(d) (fields 1-120), not CT2 = Art 24(1)+24(2) (fields 1-295+Q302).

### Root cause
The code confused AIFM and AIF content type numbering. **AIFM** CT2 = registered/3(3)(d), which is correct for the AIFM report. But the same "2" was used for the **AIF** content type, where CT2 means Art 24(1)+24(2) — a much broader reporting scope. The comment even said "2=24(2) registered" which conflates the two numbering systems.

### Fix
Changed `m_adapter.py` AIF Q5 derivation: `content_type = "2"` → `content_type = "3"` for non-FULL templates. The 3 AIFM derivation locations were already correct (AIFM CT2 = registered).

### Impact
Light template AIFs were being treated as CT2 (295+ fields required) instead of CT3 (120 fields). This would cause false validation failures for missing 24(2) fields that a registered AIFM is not required to report.

### Lessons for next time

1. **AIFM and AIF content types use different numbering.** AIFM CT1/2/3 = authorised/registered/NPPR. AIF CT1-5 = different article combinations. Never assume the same number means the same thing across report types.

2. **Always cross-reference the reporting obligation matrix.** The matrix explicitly maps AIFM CT2 → AIF CT3. A single lookup would have caught this immediately.
