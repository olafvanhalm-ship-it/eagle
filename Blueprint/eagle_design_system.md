# Project Eagle — UI Design System
**Version 1.0 | Owner: CTO / CPO | Status: Baselined**

> This document defines the visual language, component library, and UI patterns for the Eagle platform. It governs the **Client Compliance Portal** (tenant-facing), the **Eagle Administration** interface (internal operations), and the **Management Intelligence** dashboards (leadership). Every design decision traces back to the 16 Eagle principles. Generated from the full Blueprint document set (26 files, 12 modules, 8 role documents).

---

## 1. Design Principles (UI-specific)

| # | Principle | Implication for UI |
|---|-----------|-------------------|
| 1 | **Trust over delight** | Every visual choice reinforces professional credibility. Compliance officers stake their reputation on Eagle's outputs — the interface must feel as reliable as the engine. No decorative elements that do not serve information clarity. |
| 2 | **Data density with clarity** | Dashboards are information-dense by design. Clarity comes from hierarchy, spacing, and consistent patterns — not from hiding data. The COO operations dashboard (REQ-OPS-001) must load 200 clients in a single scrollable view. |
| 3 | **Status is king** | Regulatory reporting is deadline-driven. Pipeline status, validation outcomes, and urgency indicators must be visible at a glance without interaction. Every entity — submission, client, AIF, NCA registration — carries a visible status badge. |
| 4 | **Progressive disclosure** | Show the summary first; reveal detail on demand. Field-level lineage (REQ-LIN-001), audit trail entries (REQ-AUD-001), and validation rule detail expand — they don't clutter the default view. |
| 5 | **Deterministic feedback** | Every user action produces an explicit, unambiguous response. No optimistic UI for regulated actions. Approval is confirmed only after the server confirms the write. Loading states for all server-confirmed actions. |
| 6 | **Accessible by default** | WCAG 2.1 AA minimum. All colour-coded states have a secondary indicator (icon and text label). Colour alone never carries meaning. |
| 7 | **Platform-first separation** | Navigation, layout shells, and shared components (IAM, audit trail viewer, notification centre) are platform-level. Module-specific UI (validation results, NCA obligation matrix, DQEF feedback export) is product-level. The two never mix (P15). |
| 8 | **Three audiences, one system** | The same design tokens and components serve three distinct audiences with different access patterns: compliance professionals (precision, auditability), operations staff (throughput, status overview), and leadership (KPIs, trends). Role-based views, not separate applications. |

---

## 2. Design Tokens

### 2.1 Colour Palette

#### Brand Colours
| Token | Hex | Usage |
|-------|-----|-------|
| `brand-900` | `#0F172A` | Primary text, headings |
| `brand-800` | `#1E293B` | Sidebar background, navigation chrome |
| `brand-700` | `#334155` | Secondary text, active nav items |
| `brand-600` | `#475569` | Tertiary text, placeholders |
| `brand-500` | `#64748B` | Disabled text, default borders |
| `brand-100` | `#F1F5F9` | Page background, table header background |
| `brand-50`  | `#F8FAFC` | Card backgrounds, alternating table rows |
| `brand-white` | `#FFFFFF` | Card surface, input backgrounds, modal backgrounds |

#### Accent — Eagle Blue
| Token | Hex | Usage |
|-------|-----|-------|
| `accent-700` | `#1D4ED8` | Primary action buttons, active links, selected nav |
| `accent-600` | `#2563EB` | Hover state for primary actions |
| `accent-500` | `#3B82F6` | Focus rings, selected row indicator |
| `accent-100` | `#DBEAFE` | Accent background, selected row highlight |
| `accent-50`  | `#EFF6FF` | Subtle accent fill, hover row background |

#### Semantic — Status Colours
These map directly to the Eagle urgency model (REQ-OPS-001), validation outcomes (REQ-VAL-001), and health scores (REQ-CS-002).

| Token | Hex | Icon | Usage |
|-------|-----|------|-------|
| `status-success` | `#16A34A` | `CheckCircle` | Validation PASS, submission ACCEPTED, health GREEN, deadline GREEN (>7d) |
| `status-success-bg` | `#F0FDF4` | — | Success row/card background |
| `status-warning` | `#D97706` | `AlertTriangle` | CAM flags, DQ warnings, health AMBER, deadline AMBER (3–7d), trial WARM |
| `status-warning-bg` | `#FFFBEB` | — | Warning row/card background |
| `status-error` | `#DC2626` | `XCircle` | CAF errors, validation FAIL, health RED, deadline RED (<3d), trial HOT (conversion urgency) |
| `status-error-bg` | `#FEF2F2` | — | Error row/card background |
| `status-critical` | `#18181B` | `AlertOctagon` | BLACK — overdue deadline, NCA REJECTED, DORA MAJOR incident |
| `status-critical-bg` | `#F4F4F5` | — | Critical row background with `border-status-left` |
| `status-info` | `#2563EB` | `Info` | Informational notices, DQEF 01_STATS flow type, system events |
| `status-info-bg` | `#EFF6FF` | — | Info background |
| `status-neutral` | `#6B7280` | `Minus` | Not applicable, no data, pending, trial INACTIVE |

> **Accessibility rule:** Every status colour is always paired with an icon and a text label. Colour alone never carries meaning. All combinations meet WCAG 2.1 AA contrast (4.5:1 for normal text, 3:1 for large text and UI components).

#### Deadline Urgency Mapping (REQ-OPS-001 / REQ-OBL-002)
| Urgency | Token | Days remaining | Icon | Notification trigger |
|---------|-------|----------------|------|---------------------|
| GREEN | `status-success` | > 7 days | `CheckCircle` | T-30: period opens |
| AMBER | `status-warning` | 3–7 days | `Clock` | T-7: escalate if data not ingested |
| RED | `status-error` | < 3 days | `AlertTriangle` | T-2: escalate if not approved |
| BLACK | `status-critical` | Overdue | `AlertOctagon` | T+1: immediate escalation |

#### Provenance Colours (REQ-POS-004)
| Provenance | Indicator | Colour accent |
|------------|-----------|---------------|
| DERIVED | `∑` formula icon | `accent-500` |
| AI_PROPOSED | AI badge + confidence chip | `#7C3AED` (purple) |
| MANUALLY_ENTERED | Pencil icon | `brand-600` |
| MANUALLY_OVERRIDDEN | Override icon | `status-warning` |
| IMPORTED | Import icon | `brand-500` |
| SMART_DEFAULT | Default icon | `brand-500` |
| LOCKED | Lock icon | `brand-700` |
| PRE_POPULATED_PUBLIC | Solid pill "From public register" | `status-success` |
| AI_PROPOSED_INDICATIVE | Dashed pill "Suggested" | `#7C3AED` (purple, dashed) |
| MANUAL_OPS_CORRECTION | Pencil icon "Reviewed by Eagle team" | `status-warning` |

### 2.2 Typography

Font stack: `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
Monospace (rule IDs, field codes, XML, hashes, LEIs): `'JetBrains Mono', 'Fira Code', 'Consolas', monospace`

| Token | Size | Weight | Line height | Usage |
|-------|------|--------|-------------|-------|
| `text-display` | 30px | 700 | 1.2 | Page title ("Operations Dashboard", "Compliance Portal") |
| `text-heading-1` | 24px | 600 | 1.3 | Section heading |
| `text-heading-2` | 20px | 600 | 1.35 | Card title, panel heading, module heading |
| `text-heading-3` | 16px | 600 | 1.4 | Sub-section, table group header, widget title |
| `text-body` | 14px | 400 | 1.5 | Default body text, table cells, form labels |
| `text-body-medium` | 14px | 500 | 1.5 | Emphasis within body (column headers, KPI labels, active tabs) |
| `text-small` | 12px | 400 | 1.5 | Captions, timestamps, audit trail metadata, ESMA error codes |
| `text-mono` | 13px | 400 | 1.5 | Rule IDs (REQ-VAL-001), field references, DQEF codes, XML snippets, LEIs, hashes |

### 2.3 Spacing Scale

Base unit: `4px`. All spacing values are multiples of the base.

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Inline icon gap, tight padding |
| `space-2` | 8px | Input internal padding, list item gap, chip padding |
| `space-3` | 12px | Button padding (vertical), compact card padding |
| `space-4` | 16px | Card padding, form group gap |
| `space-5` | 20px | Section gap within a card |
| `space-6` | 24px | Card-to-card gap, panel padding |
| `space-8` | 32px | Section-to-section gap |
| `space-10` | 40px | Page margin (desktop) |
| `space-12` | 48px | Major layout gap (e.g. between dashboard rows) |

### 2.4 Border & Radius

| Token | Value | Usage |
|-------|-------|-------|
| `border-default` | `1px solid #E2E8F0` | Card borders, input borders, table cell borders |
| `border-strong` | `1px solid #CBD5E1` | Dividers, active input border |
| `border-accent` | `2px solid accent-500` | Focus ring, selected state border |
| `border-status-left` | `3px solid [status-color]` | Left border on status rows, validation result cards, health indicators |
| `radius-sm` | 4px | Buttons, badges, chips |
| `radius-md` | 8px | Cards, modals, dropdowns |
| `radius-lg` | 12px | Large panels, popovers |
| `radius-full` | 9999px | Avatars, circular indicators, health score badges |

### 2.5 Elevation (Shadows)

| Token | Value | Usage |
|-------|-------|-------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Buttons (resting), inputs |
| `shadow-md` | `0 4px 6px rgba(0,0,0,0.07)` | Cards, dropdown menus |
| `shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, popovers, tooltips |
| `shadow-focus` | `0 0 0 3px rgba(59,130,246,0.3)` | Focus ring (accent-500 @ 30%) |

### 2.6 Motion

| Token | Duration | Easing | Usage |
|-------|----------|--------|-------|
| `motion-fast` | 100ms | `ease-out` | Button hover, icon state change, tooltip show |
| `motion-normal` | 200ms | `ease-in-out` | Panel expand/collapse, drawer open, row expand |
| `motion-slow` | 300ms | `ease-in-out` | Modal enter/exit, page transition, sidebar toggle |
| `motion-none` | 0ms | — | Respect `prefers-reduced-motion` — all animation disabled |

---

## 3. Core Components

### 3.1 Buttons

| Variant | Background | Text | Border | Use when |
|---------|------------|------|--------|----------|
| **Primary** | `accent-700` | `white` | none | Main action per screen (Submit, Approve, Save, Confirm) |
| **Secondary** | `white` | `brand-800` | `border-default` | Supporting action (Cancel, Back, Export, Download) |
| **Danger** | `status-error` | `white` | none | Destructive or high-consequence action (Reject, Revoke, Override CAF) |
| **Ghost** | `transparent` | `accent-700` | none | Tertiary action, inline table actions, drill-down links |
| **Upgrade** | `#7C3AED` | `white` | none | Trial feature gate prompt ("Available in paid plan") |

**Sizes:** `sm` (28px height, text-small), `md` (36px height, text-body), `lg` (44px height, text-body-medium)

**States:** Default → Hover (darken 8%) → Active (darken 12%) → Disabled (opacity 0.5, cursor not-allowed) → Loading (spinner replaces label, width preserved)

**Rules:**
- Maximum one Primary button per visible screen area
- Regulated actions (Approve, Submit to NCA, Override CAF) always use `lg` size with explicit icon and confirmation modal
- Loading state for all server-confirmed actions — no optimistic feedback (P5)
- Trial feature gates show Upgrade variant with lock icon, not disabled Primary

### 3.2 Inputs

| Type | Description |
|------|-------------|
| **Text** | Single-line, 36px height, `text-body`, left-aligned. Used for LEI, national codes, free-text search |
| **TextArea** | Multi-line. Override justifications (min 50/100 chars per REQ-OVR-001), exception descriptions, constraint log entries |
| **Select** | Single-value dropdown, searchable when > 8 options. NCA codes, reporting frequencies, filing types, entity scopes |
| **Multi-select** | Chip display for selected values. NCA registrations, marketing jurisdictions, pipeline stage filters |
| **Date picker** | Calendar with period presets (Q1-Q4, H1-H2, Y1, X1-X2). Respects NCA deadline calendar (REQ-OBL-002) |
| **Date range** | Dual calendar for audit trail queries, SLA reporting windows, exception log filters |
| **File upload** | Drag-and-drop zone with accepted format badges (.xlsx, .csv, .json, .xml). Max 50MB indicator (REQ-ING-002) |
| **LEI input** | Text + inline GLEIF validation badge. Shows ✓ valid / ⚠ expired / ✗ not found |
| **Percentage** | Numeric with % suffix, right-aligned. For financing %, leverage, investor concentration |
| **Currency** | Numeric with currency code prefix (ISO 4217), right-aligned. For AuM, NAV, market values |

**Validation states:** Default → Focus (accent border + shadow-focus) → Error (status-error border + inline error below) → Warning (status-warning border + inline warning) → Disabled (brand-100 background)

**Rules:**
- All inputs have visible labels — no placeholder-only labels
- Required fields marked with `*` in label, not colour alone
- Error messages reference the specific validation rule ID and ESMA error code when applicable
- Override justification fields show character count and minimum requirement
- AI_PROPOSED fields show purple dashed border with confidence chip until confirmed

### 3.3 Data Tables

The primary information display pattern across Eagle. Tables handle validation results, submission lists, audit trails, client rosters, NCA obligation matrices, exception logs, renewal trackers, and operational dashboards.

**Structure:**
- **Header row:** `text-body-medium`, `brand-100` background, sticky on scroll
- **Data rows:** `text-body`, alternating `brand-white` / `brand-50`
- **Status column:** Left-aligned icon + text label, using semantic status colours
- **Action column:** Right-aligned, Ghost buttons or icon buttons
- **Row hover:** `accent-50` background
- **Status left-border:** `border-status-left` on the entire row for at-a-glance scanning

**Features:**
- Column sorting (click header; visual arrow indicator)
- Column filtering (funnel icon in header → dropdown filter)
- Pagination (25 / 50 / 100 rows; server-side for > 500 records)
- Row expansion (chevron → expands detail panel inline; used for field lineage, exception detail, health score breakdown)
- Bulk selection (checkbox column; bulk action bar appears above table; used for bulk approval of zero-flag records)
- Freeze panes: first column (entity name) and header always visible
- Exportable: PDF and CSV export buttons in table header (P14: generated views of DB data)

**Responsive:** Tables scroll horizontally on mobile with frozen first column. Critical tables (Operations Dashboard, Deadline Pressure) have a card-view alternative below `768px` (REQ-OPS-001: mobile-responsive for on-call).

### 3.4 Cards

| Variant | Usage |
|---------|-------|
| **Metric card** | Single KPI with label, value, trend indicator (sparkline or ↑↓), and period context. Used in: operations dashboard (REQ-OPS-001), CCO-view (REQ-INT-001), CFO subview, CS subview |
| **Status card** | Entity summary with status badge, key metadata, and action link. Used in: per-client health (REQ-CS-002), per-NCA submission status, trial health (REQ-TRIAL-006) |
| **Detail card** | Expandable card for field-level lineage (REQ-LIN-001), validation rule detail, audit event, exception record |
| **Period card** | Per-NCA reporting period card showing: NCA chip, period, deadline, pipeline stage, validation score, action buttons. Used in Client Compliance Dashboard |
| **Gate card** | Pre-condition gate display: each prerequisite as a row with pass/fail indicator. Used in: review gate checklist, go-live qualification (REQ-AIFMD-006), tenant onboarding checklist |

**Structure:** `radius-md`, `shadow-md`, `space-4` padding, `brand-white` background, `border-default`. Status cards add `border-status-left`.

### 3.5 Navigation

**Sidebar (desktop):**
- Width: 240px (expanded), 64px (collapsed — icon only)
- Background: `brand-800`
- Nav items: `text-body`, `brand-white` text → active item: `accent-100` text with `accent-700` left border
- **Platform sections** (always present): Dashboard, Notifications, Audit Trail, Settings
- **Product sections** (context-dependent): Submissions, Validation, Data Upload, Reports
- **Internal sections** (EAGLE_ADMIN only): Operations (COO-view), Commercial (CCO-view), Customer Success (CS-view), Compliance, Finance (CFO subview)
- Tenant switcher (service provider model, REQ-TEN-002): dropdown at top of sidebar showing current AIFM sub-entity
- AIFM sub-entity selector: for service providers managing multiple AIFMs
- Role indicator: current user role chip below user name
- Trial indicator: TRIAL_TENANT badge with days remaining when applicable

**Top bar:**
- Height: 56px
- Contains: breadcrumb, global search, notification bell (with count badge), Pipedrive staleness indicator (CCO-view only, REQ-INT-001), user avatar/menu
- Breadcrumb reflects: Module → Entity → Action (e.g. Submissions → AIFM-X → Q4 2025 → CSSF)

**Tabs:**
- Used within pages to switch context
- Per-NCA views within a submission (REQ-MJ-003: one tab per NCA registration)
- Validation categories (CAF / CAM / DQ / Cross-record)
- Management subviews (COO-view / CCO-view / CS-view / CFO subview)
- Underline style, `accent-700` active indicator, `brand-600` inactive

### 3.6 Badges & Chips

| Type | Usage | Style |
|------|-------|-------|
| **Status badge** | Pipeline stage (INGESTING, VALIDATING, REVIEW_PENDING, etc.), submission outcome (ACCEPTED, REJECTED), health tier | Rounded pill, coloured background + matching text |
| **Count badge** | Notification count, error count, open exception count, AIF count per client | Circular, `status-error` for alerts, `brand-500` for neutral |
| **Role chip** | User role display (COMPLIANCE_REVIEWER, TENANT_ADMIN, EAGLE_ADMIN, etc.) | `radius-sm`, `brand-100` background, `brand-700` text |
| **NCA chip** | NCA code display (CSSF, AFM, BaFin, CBI, FCA, etc.) | `radius-sm`, subtle coloured background per NCA; consistent colour per NCA across all views |
| **Flag chip** | CAF / CAM / DQ flag type with severity | Colour-coded per severity: CAF = `status-error`, CAM = `status-warning`, DQ = `status-warning` (lighter) |
| **Provenance chip** | Field provenance type (DERIVED, AI_PROPOSED, IMPORTED, etc.) per REQ-POS-004 | Icon + label, colour per provenance type (see §2.1) |
| **Confidence chip** | AI confidence level (HIGH / MEDIUM / LOW) per REQ-ING-004 | Colour-coded: HIGH = `status-success`, MEDIUM = `status-warning`, LOW = `status-error` |
| **Trial health chip** | Trial engagement tier (HOT / WARM / COLD / INACTIVE) per REQ-TRIAL-006 | HOT = `status-error`, WARM = `status-warning`, COLD = `brand-500`, INACTIVE = `brand-400` |
| **Legitimacy chip** | Legitimacy score (HIGH / MEDIUM / LOW / NONE) per REQ-GTM-002 | Colour-coded per score tier |
| **Tenant type chip** | TRIAL_TENANT / ACTIVE_TENANT distinction | TRIAL = dashed border + clock icon; ACTIVE = solid border |

### 3.7 Modals & Dialogs

| Type | Usage |
|------|-------|
| **Confirmation modal** | Regulated actions: Approve, Submit to NCA, Confirm regime. Requires explicit action — no auto-dismiss. Escape key disabled. |
| **Override justification modal** | Override of a CAF/CAM/DQ flag (REQ-OVR-001). Multi-step: (1) full flag detail display, (2) category dropdown + justification text (min chars enforced), (3) responsibility acknowledgement checkbox, (4) countersignature request for CAF. |
| **Review gate modal** | Per-checklist-item acknowledgement (REQ-REV-001). Each item requires individual toggle. Approve button enabled only when all items checked. |
| **Destructive confirmation** | Red-accent modal with "type to confirm" pattern for: reject submission, cancel record, revoke access. |
| **AI confirmation modal** | Confirm or reject AI_PROPOSED field values (REQ-ING-004). Shows: extracted value, confidence score, source text fragment, model version. Bulk confirm available for HIGH confidence fields. |
| **NCA enquiry pack modal** | Generate response pack (REQ-AIFMD-005). Shows: included documents checklist, generation progress. |
| **Information modal** | Non-blocking detail display (rule explanation, ESMA error code detail, DQEF rationale). Closeable via X or Escape. |

**Rules:**
- Modals trap focus (WCAG)
- Escape closes informational modals only — not confirmation modals for regulated actions
- Background overlay: `rgba(0,0,0,0.5)`, no interaction with underlying page
- All modal actions logged in audit trail

### 3.8 Feedback & Notifications

| Type | Behaviour | Duration |
|------|-----------|----------|
| **Toast** | Non-blocking success/info feedback, top-right | Auto-dismiss 5s (success/info); manual dismiss required (error/warning) |
| **Inline alert** | Contextual feedback within a form or section | Persistent until condition resolved |
| **Banner** | Page-level or system-level notice | Persistent, dismissible (except: OVERDUE, REJECTED, DORA MAJOR — non-dismissible per REQ-NOT-001) |
| **Empty state** | Illustration + message + primary action when no data exists | — |
| **Staleness indicator** | Data freshness warning (Pipedrive staleness per REQ-INT-001, reference data per REQ-REF-001) | Persistent with last-known-good timestamp |
| **Upgrade prompt** | Trial feature gate prompt (REQ-TRIAL-002) | Shown on gated action attempt; dismissible but re-shown |

**Notification centre (REQ-NOT-001):**
- Bell icon in top bar with unread count badge
- Dropdown panel: grouped by category (Deadline, Submission, System, DORA incident)
- Mandatory notifications (OVERDUE, REJECTED, CAF_FAILED, RESPONSE_PARSE_ERROR, DORA MAJOR) cannot be dismissed without acknowledgement
- Each notification links to the relevant entity (submission, client, exception)
- Email and in-app delivery; delivery failure retried 3× with exponential backoff

---

## 4. UI Patterns — Client Compliance Portal

### 4.1 Client Compliance Dashboard (REQ-DSH-001)

**Layout:** Per-tenant view. Primary workspace for COMPLIANCE_REVIEWER, TENANT_ADMIN, DATA_PREPARER.

**Top bar context:** Current tenant name, tenant type chip (TRIAL/ACTIVE), active reporting period selector.

**Row 1 — Period cards:** One card per active NCA registration × reporting period. Each shows: NCA chip, period (Q4 2025), deadline date, days remaining with urgency colour, pipeline stage badge (DRAFT → INGESTING → VALIDATING → REVIEW_PENDING → APPROVED → SUBMITTING → SUBMITTED → ACCEPTED/REJECTED), AIF count, validation score bar. Cards sorted by deadline urgency.

**Row 2 — NCA Obligation Matrix (REQ-MJ-003):** Table with rows = AIFs, columns = NCA registrations, cells = marketing flag (✓/✗), obligation status badge, deadline. Exportable as PDF.

**Row 3 — AIFM Aggregation Status:** Indicator showing COMPLETE / PARTIAL / MANUAL for the current AIFM record. PARTIAL lists which AIFs are missing their contribution (REQ-POS-003).

**Row 4 — Quick Actions:** Upload data, View pending reviews, View submission history, Download templates (REQ-ING-002).

**Row 5 — Reference Data Indicators:** ECB rate freshness, GLEIF freshness, NCA register freshness — with status badges.

**Row 6 — Reporting Calendar (REQ-OBL-002):** Timeline view of all deadlines for this tenant. Notification milestones (T-30, T-14, T-7, T-2, T+1) marked on timeline.

**Performance:** Loads in < 2 seconds for up to 50 AIFs. Mobile-responsive.

### 4.2 Validation Results View (REQ-DSH-002 / REQ-VAL-001)

The core interface for compliance reviewers examining submission quality.

**Layout:** Three-panel view:
- **Left panel (240px):** Entity tree — AIFM at root, AIFs as children, per-NCA grouping. Count badges on each node showing error/warning/pass tallies. Cross-record validation node at AIFM level (REQ-VAL-002).
- **Centre panel:** Validation results table for the selected entity. Grouped by category: Format, Cross-field, Business Logic (CAF/CAM), DQEF Quality (DQ). Each row: Rule ID (`text-mono`), field reference, ESMA error code, expected value, actual value, status badge (PASS/FAIL), severity chip (CAF/CAM/DQ), flow type (for DQEF: 01_STATS/03_HARDCHECK/04_SOFTCHECK per REQ-VAL-003).
- **Right panel (320px, collapsible):** Detail pane for selected rule. Shows: full rule description, regulatory source reference (CDR article, ESMA guideline), field lineage (REQ-LIN-001), provenance indicator (REQ-POS-004), override history, and "Override" action button.

**Status summary bar** above the table: horizontal bar showing proportional pass/warn/fail with counts. Overall status per NCA: PASS / BLOCKED / REVIEW_REQUIRED.

**Provenance indicators** per field per REQ-POS-004: clickable icon opens lineage view. Every field with a non-PASS result shows its provenance.

**DQEF-specific display:**
- 01_STATS (informational): info badge, no review action required
- 03_HARDCHECK (impossible value): mapped to CAF, `status-error`
- 04_SOFTCHECK (implausible value): mapped to DQ_WARNING, `status-warning`, requires individual acknowledgement

**Filter bar:** Filter by status (FAIL/WARN/PASS), severity (CAF/CAM/DQ), category, NCA, DQEF flow type.

**Report export:** Printable and exportable as PDF. Plain English error descriptions — no unexplained field codes.

### 4.3 Review & Approval Gate (REQ-REV-001)

**Layout:** Dedicated full-page view per submission batch.

**Top section — Submission summary card:** AIFM name, reporting period, NCA chip, AIF count, overall validation score, filing type (INIT/AMND), AI classification flag (deterministic indicator per P5), field provenance summary (count per type: DERIVED, AI_PROPOSED confirmed, MANUALLY_ENTERED, MANUALLY_OVERRIDDEN, IMPORTED).

**Overrides section:** Dedicated section showing all overridden flags. Cannot be hidden or collapsed. Grouped by: CAF overrides (with countersignature status), CAM overrides, DQ overrides. Each showing: rule ID, field, original/overridden value, justification text, override author.

**Checklist section (REQ-REV-001):** Each checklist item rendered as an individual acknowledgement row:
- Checklist text (left)
- Related metric linked to filtered validation view (e.g. "3 CAF overrides → view")
- Individual toggle (right) — each must be separately activated
- Items: (1) All CAF errors resolved or overridden, (2) All CAM flags reviewed, (3) All DQ warnings acknowledged individually, (4) Reporting period and filing type confirmed, (5) Fund count and AIFM-AIF consistency confirmed, (6) For overridden checks: regulatory responsibility acknowledged

**Action bar (sticky bottom):**
- "Approve" (Primary, lg) — enabled only when all checklist items acknowledged
- "Return for correction" (Secondary) — routes back to DATA_PREPARER
- "Reject" (Danger) — for records that should not be submitted

**Bulk approval mode (REQ-SCL-003):** When records meet zero-flag criteria (all L3 PASS, zero CAM, zero DQ, zero overrides), a batch summary view replaces individual review. Shows: record count, batch summary statistics, Merkle tree root hash (displayed in `text-mono`, copyable). Single "Approve batch" with batch-level checklist. Excluded: any record with any flag requires individual review.

**Cross-NCA grouped approval (REQ-MJ-006):** Content-identical NCA variants offered for single-action approval. Where NCA overrides differ: individual review with diff view highlighting substantive differences.

### 4.4 Data Ingestion & Upload Interface (MOD-DATA)

**File upload view (REQ-ING-002):**
- Drag-and-drop zone with format badges (.xlsx, .csv, .json, .xml)
- Eagle-provided template download links per report type
- Auto-detection indicator (REQ-LEG-002): detected format badge, confirm/override dropdown
- Column mapping preview for custom formats
- Upload progress with file hash display

**AI-assisted ingestion (REQ-ING-004):**
- Upload zone for unstructured documents
- Extraction results table: each field as a row showing extracted value, confidence chip (HIGH/MEDIUM/LOW), source text fragment, provenance = AI_PROPOSED
- LOW confidence fields highlighted with explicit confirmation required
- Bulk confirm button for HIGH confidence fields
- Each field has "Confirm" / "Edit" / "Reject" actions
- Clear labelling: "These values are AI proposals — not validated data" (REQ-AIACT-006 transparency)

**Enrichment calculation review (REQ-LEG-003):**
- Side-by-side view: original template values (left) vs. calculated values (right)
- Highlighted differences with formula explanation (e.g. "Gross Leverage = CDR Art.7: |sum positions| / NAV × 100")
- Accept / Reject per calculation; Reject keeps original value

**Position data view (REQ-POS-001):**
- Table of positions: instrument ID, asset type, long/short, market value, currency, notional, counterparty LEI
- Derived fields shown with provenance indicator (∑ icon)
- Incremental update indicator: shows which positions changed since last version

### 4.5 Override Workflow (REQ-OVR-001)

**Trigger:** User clicks "Override" on a failed validation rule.

**Modal flow (multi-step):**
1. **Step 1 — Flag detail:** Full rule detail: rule ID, field, expected value, actual value, ESMA error code, regulatory source, DQEF rationale (if DQ).
2. **Step 2 — Category & Justification:** Override category dropdown (Data quality exception / NCA-specific interpretation / Client-confirmed value / Other). Free-text justification (mandatory: min 100 chars for CAF, min 50 chars for CAM/DQ). Character counter displayed.
3. **Step 3 — Acknowledgement:** Checkbox: "I acknowledge that this override transfers full regulatory responsibility for this field value to the approving party."
4. **Step 4 — Countersignature (CAF only, REQ-OVR-001):** If second TENANT_ADMIN exists, system requires their confirmation. If no second TENANT_ADMIN: logged as warning, EAGLE_ADMIN auto-notified.
5. **Confirmation:** Override recorded in audit trail. Original value and overridden value both preserved. Override valid for this submission only — does not carry over.

**Monthly override report:** Generated for EAGLE_ADMIN showing systematic data quality patterns per client.

### 4.6 Amendment Workflow (REQ-AMD-001)

**Entry point:** "Initiate Amendment" button on an ACCEPTED submission (available to COMPLIANCE_REVIEWER / TENANT_ADMIN).

**Flow:**
1. AMND draft created, pre-populated from original INIT data (read-only reference panel shows original)
2. DATA_PREPARER corrects fields in editable AMND record
3. Changed fields highlighted with diff indicator (original → corrected)
4. Full validation pipeline (L3 + L4) runs on corrected record
5. DQEF DQ-T-002 flag auto-applied if AMND > 90 days after INIT
6. Review gate for AMND record
7. AMND linked to original INIT in submission history timeline

### 4.7 Field-Level Lineage Display (REQ-LIN-001 / REQ-POS-004)

**Trigger:** Click on any field value anywhere in the application → lineage popover or side panel.

**Content:**
- Current value with provenance chip
- **Provenance chain** displayed as horizontal stepper/flow: Data source → Adapter/AI extraction → Derivation/Enrichment → Validation → Review → Submission. Each step as a coloured node, expandable.
- **Per-provenance-type detail:**
  - DERIVED: formula ID, formula description, legal basis (CDR article), input fields and values, engine version, calculation timestamp, reference data used
  - AI_PROPOSED: model version, confidence score (0.00–1.00), source text fragment (verbatim), source page, extraction timestamp
  - MANUALLY_ENTERED: user role, user ID, entry timestamp, channel (WEB_UI/API)
  - MANUALLY_OVERRIDDEN: original provenance, original value, override reason, override user, timestamp
  - IMPORTED: adapter ID and version, source template field, source cell reference, enrichments applied
  - SMART_DEFAULT: rule ID, rule description, trigger condition
- **Version history:** Full ordered history of all provenance changes for this field. Immutable. 10-year retention.
- **Regulatory reference:** ESMA Annex IV field code

### 4.8 NCA Submission Preview (MOD-SUB)

**Pre-submission view (REQ-FMT-001):**
- Packaging preview: XML structure (single/multi), compression format, file naming pattern
- Delivery channel indicator: DIRECT_API / ROBOT_PORTAL / S3 / SFTP / MANUAL
- Checksum display (MD5 or SHA-256)
- "Submit" action with confirmation modal showing: NCA, channel, record count, submission sequence

**Submission history timeline:**
- Vertical timeline per AIFM × period × NCA
- Events: INIT submitted → NCA response → AMND submitted → NCA response
- Each event expandable to show: packaged file hash, delivery timestamp, NCA reference number, NCA error codes if rejected (REQ-AIFMD-003)

**DQEF feedback export (REQ-DQEF-001):**
- Dashboard view of DQ_WARNING flags per DQEF cycle (HY1/HY2) per NCA
- Mark as CONFIRMED_ERROR (→ amendment workflow) or FALSE_POSITIVE (with justification)
- Generate ESMA feedback export (.xlsx, exact column format per ESMA template)
- 12-week deadline reminder displayed prominently

---

## 5. UI Patterns — Eagle Administration (Internal)

### 5.1 Operations Dashboard (REQ-OPS-001)

**Layout:** Full-width, sidebar collapsed. Primary workspace for EAGLE_ADMIN in COO role.

**Row 1 — Metric cards (4 across):**
- Active clients (count + AIF count + NCA registration count)
- Submissions in progress (count by stage: INGESTING / VALIDATING / REVIEW_PENDING / SUBMITTING)
- Automation ratio (percentage + trend sparkline, 30-day rolling per REQ-OPS-002)
- Submission success rate (current period: % accepted / % rejected / % pending)

**Row 2 — Deadline pressure view (REQ-OPS-001):**
- Table sorted by urgency (BLACK → RED → AMBER → GREEN)
- Columns: Client, NCA chip, Period, Status badge, Days remaining, Submission channel, Action (drill-down)
- Left border colour per urgency token
- All NCA deadlines within next 14 days
- Auto-refreshes every 60 seconds (max lag)
- One-click drill-down to client's submission in admin tenant view

**Row 3 — Per-client health table:**
- Full client roster: client name, tenant type, AIF count, last submission date, current period status, SLA score (12-month per REQ-OPS-003), health score (REQ-CS-002 composite), open exception count (REQ-OPS-004)
- Sortable by any column; filterable by status and health tier
- Deteriorating clients (health AMBER/RED) highlighted with `status-warning-bg` / `status-error-bg`

**Row 4 — Ingestion status panel:**
- Per-client data receipt matrix: RECEIVED / PARTIAL / NOT_YET_RECEIVED / OVERDUE
- Expected vs. received feed counts for SFTP/API push clients
- Flag for overdue relative to deadline minus configured lead time

**Row 5 — Reference data panel (REQ-REF-001):**
- ECB rate freshness, GLEIF freshness, NCA register freshness — with status indicators
- Staleness alerts

**Active incident banner:** During DORA MAJOR/SIGNIFICANT incident: persistent banner at top showing incident ID, classification, affected client count, regulatory notification deadline. Links to impact register (REQ-OPS-006).

**Mobile layout (< 768px):** Metric cards stack vertically. Deadline table → card view sorted by urgency. Client health → scrollable card list, most critical first.

**Performance:** Loads in < 3 seconds for 200 active clients. Dashboard state (filters, sort) persisted in DB per user (P14).

### 5.2 Operational Exception Log (REQ-OPS-004)

**Layout:** Searchable, filterable table view within COO-view.

**Columns:** Exception ID, opened timestamp, category badge (PIPELINE_FAILURE, DATA_QUALITY_ISSUE, SLA_AT_RISK, REFERENCE_DATA_STALE, MANUAL_ESCALATION, DORA_INCIDENT_LINKED), severity badge (LOW/MEDIUM/HIGH/CRITICAL), client, period, status badge (OPEN/IN_PROGRESS/RESOLVED/CLOSED), assigned to, resolution time.

**Features:**
- Filter bar: status, severity, category, client, date range
- Auto-created exceptions (robot failure, NCA rejection, reference data failure, overdue) shown with "System" as opener
- Root cause required before CLOSED — inline text field with validation
- Linked audit events: expandable section showing related audit trail entries
- Monthly exception summary: auto-computed, displayed as metric cards above the table

### 5.3 Capacity Calendar (REQ-OPS-005)

**Layout:** Calendar view within COO-view.

- Monthly and weekly views showing all NCA submission deadlines across all clients
- Each deadline: bar labelled with client name, NCA chip, AIF count, submission channel icon
- Peak-load indicator: 7-day windows above threshold highlighted (AMBER/RED)
- Load distribution bar chart: submissions by calendar week, next 6 months
- Scenario planning: toggle to add projected clients (2×, 5× current load)

### 5.4 DORA Incident Impact Register (REQ-OPS-006)

**Layout:** Structured form + table within COO-view. Activated when a DORA incident is classified as MAJOR or SIGNIFICANT.

**Header:** Incident ID (linked to REQ-ISO-005 technical record), classification badge, detected timestamp, regulatory notification deadline with countdown timer.

**Affected clients table:** One row per client. Columns: client name, impact type badge (SUBMISSION_DELAYED, DATA_UNAVAILABLE, etc.), submission at risk (boolean), deadline, SLA breach (boolean), client notified timestamp, notification channel, remediation status (PENDING/IN_PROGRESS/COMPLETED).

**Pre-populated:** System auto-populates clients with active submissions near the incident window. EAGLE_ADMIN completes remaining fields.

**Post-incident section:** 5-day review deadline, lessons learned text, link to operational improvement items.

---

## 6. UI Patterns — Management Intelligence

### 6.1 CCO/CRO Commercial Dashboard (REQ-INT-001)

**Layout:** Full-width dashboard within CCO-view. Accessible to EAGLE_ADMIN, CCO, CRO.

**Row 1 — Funnel metric cards:**
- Prospect database: total AIFMs, coverage rate (% of ESMA register), enrichment completion rate
- Outbound: MQL rate, inbound lead volume
- Legitimacy queue: pending reviews (count + average age), approval rate by tier
- Trials: active by health tier (HOT/WARM/COLD/INACTIVE), trial-to-paid conversion rate

**Row 2 — Revenue metrics:**
- New ARR (monthly + rolling 12m)
- Pipeline ARR (probability-weighted per Pipedrive stage)
- LTV:CAC ratio
- NRR (net revenue retention)

**Row 3 — Trial funnel:**
- Trial activation rate, trial-to-demo rate, average days to conversion
- Trial health distribution chart (stacked bar by tier)

**Pipedrive integration:**
- Deal stage updates reflected within 15 minutes via webhook
- Staleness indicator if no webhook event in > 2 hours: warning badge on all Pipedrive-sourced metrics

**Revenue concentration alert (REQ-INT-001):** When any single client > 30% of total ARR: red banner, alert to CFO and CEO.

**CFO subview tab:**
- ARR bridge: opening + new + expansion - churn = closing
- MRR with month-over-month trend
- Revenue forecast: pipeline-weighted 3-month projection

### 6.2 Legitimacy Review Queue (REQ-GTM-002)

**Layout:** Queue view within CCO-view. Accessible to CCO, CCO_DELEGATE, EAGLE_ADMIN.

**Table:** Pending trial requests sorted oldest-first. Columns: company name, registrant name, legitimacy score chip (HIGH/MEDIUM/LOW/NONE), matching sources (checkmarks per: ESMA register, service provider DB, LinkedIn, company website), submitted timestamp, age indicator.

**Detail panel:** Per-request matching detail: per-source score breakdown, company website preview, LinkedIn match summary.

**Actions:** APPROVE / REJECT / REQUEST_INFO. Rejection sends standard message (no reason given to prospect per GDPR). All actions logged with actor identity.

### 6.3 Customer Success Subview (REQ-CS-001)

**Layout:** Tabbed view within CS-view. Accessible to HEAD_OF_CS, EAGLE_ADMIN.

**Tabs:**
1. **Health overview (REQ-CS-002):** Per-client health scorecard table. Columns: client name, composite score (0-100), RAG tier badge, submission success rate, SLA performance, support ticket frequency, engagement level, renewal proximity. Drill-down: per-component breakdown, score history chart.
2. **Renewal pipeline (REQ-CS-003):** Contract calendar sorted by end date. Columns: client, contract end date, ARR, auto-renew, renewal status badge (NOT_STARTED/IN_CONVERSATION/AGREED/AT_RISK/CHURNED), renewal owner, next action date. Alerting: colour-coded by proximity (90d/60d/30d). ARR at risk metric card.
3. **Expansion pipeline (REQ-CS-005):** Opportunity log table. Columns: client, type badge, estimated ARR uplift, probability tier, status, CRO handoff date.
4. **Constraint log (REQ-CS-006):** Voice of the Client register. Columns: title, type badge, client count affected, support ticket count, retention impact (LOW/MEDIUM/HIGH), status, presented date, CTO response.
5. **Contact register (REQ-CS-004):** Per-client contacts table. Contact type, name, role, email, preferred channel. Missing INCIDENT_ESCALATION contact: warning indicator.
6. **Incident follow-up (REQ-CS-007):** Post-incident follow-up tracker. Overdue follow-ups highlighted RED.

### 6.4 Trial Management (REQ-TRIAL-001 through 007)

**Within CCO-view and CS-view:**

**Trial overview table:** All active trials. Columns: company name, tenant type chip (TRIAL), days remaining (with urgency colour), health tier chip (HOT/WARM/COLD/INACTIVE), pre-population score, legitimacy score, data uploaded (boolean), validation run (boolean), review gate accessed (boolean).

**Trial detail view:**
- Pre-population quality panel (REQ-TRIAL-005): per-attribute confidence, COO ops review status
- Engagement timeline: login events, data uploads, validation runs, review gate access
- Upgrade prompt history
- Conversion action (CS Manager only): triggers paid onboarding checklist

**COO ops review queue (REQ-TRIAL-005):** LOW-score trials queued for pre-population review. Actions: APPROVE_AS_IS, CORRECT_AND_APPROVE, SUPPRESS_ATTRIBUTE, NO_PRE_POPULATION. 4-hour non-blocking cutoff.

### 6.5 Enrichment Quality & Trial Analytics (REQ-INT-002)

**Within Management Intelligence:**
- Pre-population accuracy: % confirmed vs. corrected by confidence tier (chart)
- Most frequently corrected fields (top 5 table)
- COO ops correction rate
- Blank workspace fallback rate
- Time-to-first-validation comparison: pre-populated vs. blank cohort
- Strategy suggestion accuracy
- Source domain accuracy table (with suppress action)
- AI Act evidence panel: metrics by model version for accuracy drift detection

---

## 7. UI Patterns — Shared Platform

### 7.1 Audit Trail Viewer (REQ-AUD-001 / REQ-AUD-002)

**Layout:** Searchable, filterable log view. Accessible by role-appropriate scope.

**Filter bar:** Submission ID, Fund ID, User ID, date range picker, event type multi-select (ingestion, transformation, validation, quality, review, submission, amendment, user, system, override).

**Log entries:** Rendered as a vertical timeline:
- Timestamp (`text-small`, `text-mono`)
- Event type badge
- Actor (user ID or SYSTEM)
- Summary text with expandable detail
- Related entity link (submission, AIF, exception, incident)

**Detail expansion:** Full event payload in structured key-value format. For field-level lineage: provenance chain per REQ-POS-004 / REQ-LIN-001.

**Export:** Machine-readable JSON for external auditor access (ISAE 3402 evidence).

### 7.2 Onboarding Wizard (Trial + Paid)

**Trial onboarding (REQ-TRIAL-003 / REQ-TRIAL-004):**
1. Welcome screen with tenant name, AIFM identity (from pre-population), days remaining
2. Strategy confirmation: "Based on your public profile, we think you are a [type] fund. Is this correct?" (REQ-TRIAL-004). One-click confirm or change dropdown.
3. Pre-populated fields review: table of PRE_POPULATED_PUBLIC and AI_PROPOSED_INDICATIVE fields with confirm/edit actions. Bulk confirm for HIGH confidence.
4. Section highlighting: mandatory sections highlighted, not-applicable sections greyed, based on confirmed AIF type. Updates dynamically on type change.
5. First data upload prompt

**Paid onboarding checklist (REQ-TEN-003):**
- Gate card pattern: each prerequisite as a row with pass/fail indicator
- Items: AIFM name + LEI validated, NCA registrations configured, reporting regime confirmed, INCIDENT_ESCALATION contact registered, DPA confirmed (GDPR gate)
- CS Manager must complete checklist before tenant activation

### 7.3 User & Access Management (REQ-USR-001–003)

**Tenant admin view:**
- User list table: name, email, role chip, MFA status, last login, status (active/suspended)
- Role assignment: select from TENANT_ADMIN, COMPLIANCE_REVIEWER, DATA_PREPARER, READ_ONLY
- API key management: sandbox key (always available), production key (paid only — gated for trial)
- CCO_DELEGATE assignment (EAGLE_ADMIN only)

---

## 8. Layout Grid

**Desktop (≥ 1280px):** 12-column grid, 24px gutter, 40px page margin. Sidebar: 240px fixed. Content area: fluid. Max content width: 1440px (centred on ultra-wide).

**Tablet (768px – 1279px):** 8-column grid, 16px gutter, 24px page margin. Sidebar: collapsed (64px icon only).

**Mobile (< 768px):** 4-column grid, 12px gutter, 16px page margin. Sidebar: hidden, hamburger menu. Tables switch to card view. Touch targets: 44×44px minimum.

---

## 9. User Roles & Access Patterns

The UI clearly communicates the current user's role and access boundaries (P9).

| Role | Access scope | Sidebar sections | Visual indicator |
|------|-------------|------------------|------------------|
| `EAGLE_ADMIN` | All tenants + all internal views | Full: Admin + Operations + Commercial + CS + Compliance + Finance | Red admin badge |
| `COO` | Internal operations views | Operations (COO-view) | Blue ops badge |
| `CCO` / `CRO` | Internal commercial views | Commercial (CCO-view), CS expansion read-only | Blue commercial badge |
| `CFO` | Internal finance views | Finance subview within CCO-view | Blue finance badge |
| `HEAD_OF_CS` | Internal CS views | CS-view, contact register, health scores | Blue CS badge |
| `CCO_DELEGATE` | Delegated legitimacy review | CCO-view legitimacy queue only | Blue delegate badge |
| `TENANT_ADMIN` | Full tenant configuration + review + override | Portal: all tenant features | Blue tenant badge |
| `COMPLIANCE_REVIEWER` | Review, approve, override within tenant | Portal: review, validation, override, DQEF feedback | Green reviewer badge |
| `DATA_PREPARER` | Data entry, upload, view validation | Portal: data upload, data entry, validation read-only | Grey preparer badge |
| `READ_ONLY` | View-only access within tenant | Portal: dashboards and reports only | Grey read-only badge |
| `TRIAL_USER` | Trial-scoped access (feature-gated) | Portal: same as TENANT_ADMIN minus gated features | Trial badge with days remaining |

**Role enforcement rules:**
- Role-restricted actions are **hidden** (not disabled) for users without the required role. A DATA_PREPARER never sees an "Approve" button.
- Exception: trial feature gates show the action as visible but **locked** (Upgrade variant) with upgrade prompt (REQ-TRIAL-002).
- Server-side enforcement: API calls for gated actions return HTTP 403 (role) or 402 (trial gate).

---

## 10. Accessibility Requirements

| Requirement | Standard | Implementation |
|-------------|----------|----------------|
| Colour contrast | WCAG 2.1 AA (4.5:1 text, 3:1 large text/UI) | All token combinations verified; no status communicated by colour alone |
| Keyboard navigation | Full keyboard operability | All interactive elements focusable; visible focus ring (`shadow-focus`); logical tab order |
| Screen reader | ARIA landmarks and live regions | Sidebar as `nav`, main content as `main`, modals as `dialog`, status updates as `aria-live="polite"`, deadline alerts as `aria-live="assertive"` |
| Focus management | Modal focus trap, return focus on close | Confirmation modals trap focus; informational modals allow Escape |
| Reduced motion | `prefers-reduced-motion` respected | `motion-none` applied globally when preference detected |
| Touch targets | 44×44px minimum | All interactive elements on mobile meet minimum |
| Form accessibility | Labels, error messages, required indicators | All inputs have `<label>`, errors use `aria-describedby`, required uses `aria-required` |

---

## 11. Dark Mode (Phase 2)

Not in scope for Phase 1. Token architecture supports future dark mode by mapping semantic tokens to a separate dark palette. All colour references use tokens, never raw hex in components.

---

## 12. Technology & Implementation Notes

| Concern | Decision | Rationale |
|---------|----------|-----------|
| **Framework** | Next.js (React) | Per existing architecture decision |
| **Styling** | Tailwind CSS with custom design tokens mapped to `tailwind.config.ts` | Utility-first; tokens as CSS custom properties |
| **Component library** | Custom components on Radix UI primitives | Headless, accessible, composable |
| **Icons** | Lucide React | Consistent, open-source, tree-shakeable |
| **Charts** | Recharts for dashboards; sparklines for metric cards | React-native, declarative |
| **Tables** | TanStack Table v8 | Headless; supports sorting, filtering, virtualisation for 200+ client views |
| **Forms** | React Hook Form + Zod schema validation | Server-validated; Zod schemas shared with API |
| **Date handling** | date-fns with NCA calendar awareness | Lightweight; supports deadline calculation |
| **State persistence** | All UI state (filters, sort, view preferences) persisted in DB per user per P14 | Not localStorage; consistent across devices and sessions |
| **Token format** | Design tokens in `tokens.ts`; exported as CSS custom properties + Tailwind config | Single source of truth |
| **Real-time updates** | Server-Sent Events for dashboard refresh (max 60s lag per REQ-OPS-001) | Lightweight; no WebSocket overhead |

---

## 13. Principle Traceability Matrix

Every major design decision maps to one or more Eagle principles:

| Design decision | Principle(s) | Requirement reference |
|----------------|-------------|----------------------|
| No optimistic UI for regulated actions | P5 — Deterministic core | REQ-REV-001, REQ-OVR-001 |
| Status always shown with icon + text + colour | P8 — Compliance-proof by design | REQ-DSH-002 |
| Role-restricted UI: hide, don't disable (except trial gates) | P9 — Security by design | REQ-USR-001, REQ-TRIAL-002 |
| Field lineage accessible from any value | P4 — Single source of truth | REQ-LIN-001, REQ-POS-004 |
| Dashboard state persisted in DB, not browser storage | P14 — Database-first | REQ-OPS-001, REQ-CS-001 |
| All components work across devices and locations | P16 — Location-independent | REQ-OPS-001 (mobile on-call) |
| Override workflow with mandatory justification + countersignature | P8 — Compliance-proof | REQ-OVR-001 |
| Sidebar grouped by platform vs. product context | P15 — Platform-first, product-second | Platform/product taxonomy |
| NCA-specific packaging shown in preview before submission | P3 — Standardised product | REQ-FMT-001 |
| Validation rules traceable to regulatory source in UI | P10 — Founder-independent | REQ-VAL-001, REQ-DSH-002 |
| Automation ratio as primary metric card | P2 — Code-first, human-by-exception | REQ-OPS-002 |
| AI proposals labelled and gated behind confirmation | P5 — Deterministic core; P8 — Compliance-proof | REQ-ING-004, REQ-AIACT-006 |
| All exports generated from DB records on demand | P14 — Database-first | All REQ-OPS-*, REQ-CS-*, REQ-INT-* |
| Configuration-driven NCA packaging without code changes | P6 — Modular and portable | REQ-FMT-001, REQ-MOD-001 |
| Fallback mechanisms visible in UI (robot → manual) | P7 — Resilience | REQ-NCA-002, REQ-RES-001 |
| Trial feature gates with upgrade prompt, not errors | P12 — Ambitious growth | REQ-TRIAL-002 |
| Pre-population with confidence scoring and ops review | P1 — Customer experience first | REQ-TRIAL-003, REQ-TRIAL-005 |
| NCA obligation matrix as cross-reference dashboard | P3 — Standardised product | REQ-MJ-003 |
| Three management subviews from one dataset | P4 — Single source of truth | REQ-OPS-001, REQ-INT-001, REQ-CS-001 |
| Mandatory notifications non-dismissible for regulatory events | P8 — Compliance-proof | REQ-NOT-001 |
| All knowledge codified in system, not in people | P10 — Founder-independent | All rule descriptions, formula explanations |
| Enrichment accuracy feedback loop in analytics | P11 — Continuous learning | REQ-INT-002 |
| English throughout; international date/currency formatting | P13 — Internationally oriented | All modules |
| Async-first communication design (notifications over real-time) | P16 — Location-independent | REQ-NOT-001 |

---

## 14. Module Coverage Index

| Module | Key UI patterns | Section reference |
|--------|----------------|-------------------|
| MOD-ADMIN | Tenant management, user roles, NCA code register | §4.1, §7.3, §9 |
| MOD-CLIENT | Compliance dashboard, obligation matrix, notifications, reporting calendar | §4.1 |
| MOD-DATA | File upload, AI-assisted ingestion, position data, enrichment review, provenance | §4.4, §4.7 |
| MOD-COMP | Validation results, DQEF quality checks, override workflow, amendment, CAM register | §4.2, §4.5, §4.6 |
| MOD-REVIEW | Review gate, checklist, bulk approval, cross-NCA grouping | §4.3 |
| MOD-SUB | Submission preview, NCA packaging, delivery channels, DQEF feedback export | §4.8 |
| MOD-AUDIT | Audit trail viewer, field lineage display, submission history | §7.1, §4.7 |
| MOD-API | API documentation, API key management | §7.3 |
| MOD-MANAGEMENT | Operations dashboard, exception log, capacity calendar, DORA impact register, CCO/CRO dashboard, CS subview, CFO subview, trial analytics | §5.1–5.4, §6.1–6.5 |
| MOD-GTM | Prospect database, legitimacy review, enrichment pipeline | §6.2, §6.5 |
| MOD-TRIAL | Trial onboarding, feature gating, pre-population, strategy orientation, health monitoring, data retention | §6.4, §7.2 |
| MOD-BILLING | Stub (Phase 1.5) — no UI patterns defined yet | — |
