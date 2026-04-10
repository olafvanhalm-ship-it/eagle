"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const API = "http://localhost:8000/api/v1";

// ============================================================================
// API Client
// ============================================================================

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok && !opts.rawResponse) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || "API error");
  }
  return opts.rawResponse ? res : res.json();
}

// ============================================================================
// Provenance Icons — (9) Only show pen when priority is MANUALLY_OVERRIDDEN
// ============================================================================

const PROVENANCE = {
  SMART_DEFAULT: { icon: "\u2699\uFE0F", label: "System default", color: "text-gray-400" },
  AI_PROPOSED: { icon: "\uD83E\uDD16", label: "AI extracted", color: "text-purple-500" },
  DERIVED: { icon: "\uD83E\uDDEE", label: "Calculated from source data", color: "text-blue-500" },
  IMPORTED: { icon: "\uD83D\uDCE5", label: "Imported from template", color: "text-green-600" },
  MANUALLY_OVERRIDDEN: { icon: "\u270F\uFE0F", label: "Manual override", color: "text-orange-500" },
};

function ProvenanceIcon({ priority, source }) {
  const p = PROVENANCE[priority] || PROVENANCE.IMPORTED;
  return (
    <span className={`cursor-help ${p.color}`} title={`${p.label}\nSource: ${source || "unknown"}`}>
      {p.icon}
    </span>
  );
}

// ============================================================================
// Validation background color for value cells — (1) traffic light in value
// ============================================================================

function validationBg(validation) {
  if (!validation) return "bg-gray-50";
  // Brighter traffic-light colors for higher contrast in dense grids
  if (validation.status === "PASS") return "bg-green-200";
  if (validation.status === "WARNING") return "bg-orange-200";
  if (validation.status === "FAIL") return "bg-red-200";
  return "bg-gray-50";
}

// (1) Build hover text from ALL findings, not just one
function validationTitle(validation) {
  if (!validation) return "";
  if (validation.status === "PASS") return "Validation passed";
  // Use the findings array if available (multi-finding support)
  const findings = validation.findings || [];
  if (findings.length > 0) {
    return findings
      .filter((f) => f.status !== "PASS")
      .map((f) => {
        const parts = [];
        if (f.rule_id) parts.push(`[${f.rule_id}]`);
        if (f.message) parts.push(f.message);
        if (f.fix_suggestion) parts.push(`Fix: ${f.fix_suggestion}`);
        return parts.join(" ");
      })
      .join("\n\n");
  }
  // Fallback to legacy single-finding fields
  const parts = [];
  if (validation.rule_id) parts.push(`[${validation.rule_id}]`);
  if (validation.message) parts.push(validation.message);
  if (validation.fix_suggestion) parts.push(`Fix: ${validation.fix_suggestion}`);
  return parts.join("\n");
}

// ============================================================================
// Tooltip Wrapper
// ============================================================================

function Tip({ text, children }) {
  return <span title={text} className="cursor-help">{children}</span>;
}

// ============================================================================
// Completion Bar
// ============================================================================

function CompletionBar({ pct, filled, total }) {
  const barColor = pct >= 90 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500">{pct}% ({filled}/{total})</span>
    </div>
  );
}

// ============================================================================
// Editable Cell — (1) traffic light bg, (3) non-editable hover reason,
//                 (4) fixed Enter+blur double-fire, (10) composite drill-down
// ============================================================================

// Resolve the description label for an enum-coded value.
// Returns "" when the field is not an enum or no label is known.
// `allowedValuesRef` is the base reference-table name; labels come from
// `AIFMD_REF_LABELS` (defined below), falling back to `SOURCE_DOMAIN_LABELS`
// for ISO country/currency codes.
function _enumLabel(value, allowedValuesRef) {
  if (!allowedValuesRef || value == null || value === "") return "";
  const key = String(value);
  if (typeof AIFMD_REF_LABELS !== "undefined" && AIFMD_REF_LABELS[allowedValuesRef]) {
    const m = AIFMD_REF_LABELS[allowedValuesRef];
    if (m[key] != null) return m[key];
  }
  if (allowedValuesRef === "iso_country_code" || allowedValuesRef === "iso_country_codes"
      || allowedValuesRef === "iso_currency_code" || allowedValuesRef === "iso_currency_codes") {
    if (typeof SOURCE_DOMAIN_LABELS !== "undefined" && SOURCE_DOMAIN_LABELS[key] != null) {
      return SOURCE_DOMAIN_LABELS[key];
    }
  }
  return "";
}

function EditableCell({ value, field, onSave, editable, dataType, format: fmt, allowedValuesRef, referenceValues, validation, nonEditableReason, onDrillDown, locked }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [error, setError] = useState("");
  // (4) Track whether save was already triggered by Enter to prevent double-fire
  const savedRef = useRef(false);

  // Sync draft with value prop when value changes externally
  useEffect(() => { setDraft(value ?? ""); }, [value]);

  // When the cell is `locked` (dependency rule or derived field), suppress
  // the validation traffic-light and use a neutral gray so the read-only
  // state is visually obvious even for cells that carry a populated value.
  const vBg = locked ? "bg-gray-200 text-gray-500" : validationBg(validation);
  const vTitle = validationTitle(validation);

  // (4) Unified save handler that prevents double-fire
  const doSave = useCallback((val) => {
    if (savedRef.current) return;
    savedRef.current = true;
    onSave(val);
    setEditing(false);
  }, [onSave]);

  // Reset saved flag when entering edit mode
  useEffect(() => {
    if (editing) savedRef.current = false;
  }, [editing]);

  // Resolve enum description label (e.g. "INIT" → "Initial filing")
  const enumLabel = _enumLabel(value, allowedValuesRef);

  if (!editable) {
    // (3) Show reason why field is not editable on hover
    const reasonText = nonEditableReason
      ? `${nonEditableReason}${vTitle ? "\n\n" + vTitle : ""}`
      : vTitle || "";
    // (10) If category is composite, show pointer cursor for drill-down
    const isComposite = field?.category === "composite";
    return (
      <span
        className={`px-1.5 py-0.5 rounded text-sm ${vBg} ${locked ? "italic" : "text-gray-900"} ${isComposite ? "cursor-pointer underline decoration-dotted hover:bg-blue-50" : ""}`}
        title={reasonText}
        onClick={isComposite && onDrillDown ? onDrillDown : undefined}
      >
        {value != null && value !== ""
          ? <>
              {value}
              {enumLabel && <span className="text-gray-500 ml-1">— {enumLabel}</span>}
            </>
          : <span className="text-gray-300 italic">{"\u2014"}</span>}
      </span>
    );
  }

  if (editing) {
    // Dropdown for enumerated values — searchable with description labels.
    //
    // The backend `reference_values` list is derived from
    // `reference_tables` in `aifmd_validation_rules.yaml`. Two common refs
    // are *not* defined there: `iso_country_code` and `iso_currency_code`
    // (they're validated by a dedicated `validation_type: iso_check`
    // branch, not a membership list). Without a fallback, fields like
    // AFM17 (jurisdiction) and AFM35 (base currency) would render as a
    // plain text box because `referenceValues.length === 0`. We detect
    // those refs here and supply a client-side default option list.
    const isIsoCountryRef =
      allowedValuesRef === "iso_country_code" ||
      allowedValuesRef === "iso_country_codes";
    const isIsoCurrencyRef =
      allowedValuesRef === "iso_currency_code" ||
      allowedValuesRef === "iso_currency_codes";

    let effectiveRefValues = referenceValues;
    if ((!effectiveRefValues || effectiveRefValues.length === 0) && isIsoCountryRef) {
      effectiveRefValues = ISO_COUNTRY_CODES;
    } else if ((!effectiveRefValues || effectiveRefValues.length === 0) && isIsoCurrencyRef) {
      effectiveRefValues = ISO_CURRENCY_CODES;
    }

    if (allowedValuesRef && effectiveRefValues && effectiveRefValues.length > 0) {
      // Pick label map based on allowed_values_ref name.
      // Country / currency refs reuse SOURCE_DOMAIN_LABELS (ISO-2 / ISO-4217);
      // other refs come from AIFMD_REF_LABELS. Fall back to empty so codes
      // still render cleanly.
      let labels = AIFMD_REF_LABELS[allowedValuesRef];
      if (!labels) {
        if (isIsoCountryRef || isIsoCurrencyRef) {
          labels = SOURCE_DOMAIN_LABELS;
        } else {
          labels = {};
        }
      }
      // Normalise referenceValues to a flat list of code strings.
      const options = effectiveRefValues.map((v) =>
        typeof v === "object" ? (v.code || v.value || "") : String(v)
      );
      return (
        <div className="min-w-[220px]" onKeyDown={(e) => {
          if (e.key === "Escape") { savedRef.current = true; setEditing(false); setDraft(value ?? ""); }
        }}>
          <SearchableSelect
            value={draft}
            options={options}
            labels={labels}
            autoOpen={true}
            onChange={(val) => { setDraft(val); doSave(val); }}
          />
        </div>
      );
    }

    // Boolean toggle
    if (dataType === "B") {
      return (
        <select
          className="border rounded px-2 py-1 text-sm focus:ring-2 focus:ring-blue-300"
          value={draft}
          autoFocus
          onChange={(e) => { setDraft(e.target.value); doSave(e.target.value); }}
        >
          <option value="">{"— Select —"}</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }

    // Date picker
    if (dataType === "D") {
      return (
        <input
          type="date"
          className="border rounded px-2 py-1 text-sm focus:ring-2 focus:ring-blue-300"
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => doSave(draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") doSave(draft);
            if (e.key === "Escape") { savedRef.current = true; setEditing(false); setDraft(value ?? ""); }
          }}
        />
      );
    }

    // Number input
    if (dataType === "N") {
      return (
        <input
          type="number"
          step="any"
          className={`border rounded px-2 py-1 text-sm w-36 focus:ring-2 ${error ? "border-red-500 focus:ring-red-300" : "focus:ring-blue-300"}`}
          value={draft}
          autoFocus
          placeholder={fmt || ""}
          onChange={(e) => { setDraft(e.target.value); setError(""); }}
          onBlur={() => doSave(draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") doSave(draft);
            if (e.key === "Escape") { savedRef.current = true; setEditing(false); setDraft(value ?? ""); }
          }}
        />
      );
    }

    // Text input (default)
    return (
      <input
        type="text"
        className={`border rounded px-2 py-1 text-sm w-48 focus:ring-2 ${error ? "border-red-500 focus:ring-red-300" : "focus:ring-blue-300"}`}
        value={draft}
        autoFocus
        placeholder={fmt || ""}
        onChange={(e) => { setDraft(e.target.value); setError(""); }}
        onBlur={() => doSave(draft)}
        onKeyDown={(e) => {
          if (e.key === "Enter") doSave(draft);
          if (e.key === "Escape") { savedRef.current = true; setEditing(false); setDraft(value ?? ""); }
        }}
      />
    );
  }

  // Display mode — click to edit
  // (1) Validation status as background color on the value
  return (
    <span
      className={`text-gray-900 px-1.5 py-0.5 rounded text-sm cursor-pointer hover:brightness-95 border border-transparent hover:border-blue-200 transition ${vBg}`}
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      title={vTitle ? `Click to edit\n\n${vTitle}` : "Click to edit"}
    >
      {value != null && value !== ""
        ? <>
            {value}
            {enumLabel && <span className="text-gray-500 ml-1">— {enumLabel}</span>}
          </>
        : <span className="text-gray-300 italic">empty</span>}
    </span>
  );
}

// ============================================================================
// Field Row — (1) traffic light in value, no separate Validate column
// ============================================================================

// Conditional field dependencies — ESMA Annex IV rules where one field's
// ── Field editability ────────────────────────────────────────────────
// All conditional-dependency validation (AFM34-38 currency gates,
// derived EEA flags, system-field locks, etc.) is now handled
// exclusively by the backend. The frontend trusts field.editable and
// only adds UI-level tooltip reasons for composite/entity fields.
// Removed in screen audit 2026-04-10: AIFMD_FIELD_DEPENDENCIES,
// _dependencyLockReason(), system-field sets, dependency lock overrides.

function _nonEditableReason(field) {
  if (!field) return "";
  if (field.category === "composite") return "Derived field \u2014 edit the underlying source data instead. Click to view source positions.";
  if (field.category === "entity") return "";
  // All other editability decisions (system fields, conditional
  // dependencies, obligation-based locks) come from the backend's
  // `editable` flag — no frontend duplication needed.
  return "";
}

function FieldRow({ field, onEdit, cascaded, onDrillDown, reportType }) {
  // AIFM fields are prefixed AFM1..AFM38; AIF fields remain Q1..Qn
  const idPrefix = reportType === "AIFM" ? "AFM" : "Q";
  const handleSave = (newValue) => {
    if (newValue !== field.value) {
      onEdit(field.field_id, newValue);
    }
  };

  // Build hover tooltip: technical_guidance (ESMA definition) + obligation + XSD element
  const guidanceLines = [];
  if (field.technical_guidance) guidanceLines.push(field.technical_guidance);
  guidanceLines.push(`${field.obligation === "M" ? "Mandatory" : field.obligation === "C" ? "Conditional" : "Optional"} | ${field.xsd_element || ""}`);
  if (field.format) guidanceLines.push(`Format: ${field.format}`);
  if (field.data_type) guidanceLines.push(`Type: ${field.data_type}`);
  const guidanceText = guidanceLines.join("\n");

  // Obligation letter + colour
  const OB_LABELS = { M: "Mandatory", C: "Conditional", O: "Optional", F: "Forbidden" };
  const OB_COLORS = { M: "text-gray-900", C: "text-gray-900", O: "text-gray-400", F: "text-gray-300" };
  const ob = field.obligation || "O";

  return (
    <tr className={`border-b border-gray-100 hover:bg-gray-50 ${cascaded ? "cascade-highlight" : ""}`}>
      <td className="px-2 py-1 text-xs font-mono text-gray-400 cursor-help" title={guidanceText}>{idPrefix}{field.field_id}</td>
      <td className="px-2 py-1 text-sm text-gray-700">
        <Tip text={guidanceText}>
          {field.field_name}
        </Tip>
      </td>
      <td className="px-1 py-1 text-center">
        <span className={`text-xs cursor-help ${OB_COLORS[ob] || "text-gray-400"}`} title={OB_LABELS[ob] || ob}>
          {ob}
        </span>
      </td>
      <td className="px-2 py-1">
        <EditableCell
          value={field.value}
          field={field}
          onSave={handleSave}
          editable={field.editable}
          dataType={field.data_type}
          format={field.format}
          allowedValuesRef={field.allowed_values_ref}
          referenceValues={field.reference_values || []}
          validation={field.validation}
          nonEditableReason={_nonEditableReason(field)}
          onDrillDown={field.category === "composite" && onDrillDown ? () => onDrillDown(field) : undefined}
          locked={!field.editable}
        />
      </td>
      <td className="px-1 py-1 text-center">
        <ProvenanceIcon priority={field.priority} source={field.source} />
      </td>
    </tr>
  );
}

// ============================================================================
// Section Accordion
// ============================================================================

function SectionAccordion({ name, fields, onEdit, cascadedFields, onDrillDown, reportType }) {
  const [open, setOpen] = useState(true);
  const filled = fields.filter((f) => f.value != null && f.value !== "").length;
  const failed = fields.filter((f) => f.validation?.status === "FAIL").length;
  const warned = fields.filter((f) => f.validation?.status === "WARNING").length;

  return (
    <div className="border border-gray-200 rounded-lg mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-white hover:bg-gray-50 transition"
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-xs">{open ? "\u25BC" : "\u25B6"}</span>
          <span className="font-medium text-gray-800 text-sm">{name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {failed > 0 && (
            <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{failed} error{failed !== 1 ? "s" : ""}</span>
          )}
          {warned > 0 && (
            <span className="bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">{warned} warning{warned !== 1 ? "s" : ""}</span>
          )}
          <span className="text-gray-500">{filled}/{fields.length} fields</span>
        </div>
      </button>
      {open && (
        <table className="w-full" style={{ tableLayout: "fixed" }}>
          <colgroup>
            <col style={{ width: "44px" }} />
            <col style={{ width: "40%" }} />
            <col style={{ width: "32px" }} />
            <col style={{ width: "auto" }} />
            <col style={{ width: "44px" }} />
          </colgroup>
          <thead>
            <tr className="bg-gray-50 text-xs text-gray-500 uppercase">
              <th className="px-2 py-1 text-left">#</th>
              <th className="px-2 py-1 text-left">Field</th>
              <th className="px-1 py-1 text-center" title="Mandatory / Conditional / Optional / Forbidden">Type</th>
              <th className="px-2 py-1 text-left">Value</th>
              <th className="px-2 py-1 text-center" title="Data source">Src</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <FieldRow
                key={f.field_id}
                field={f}
                onEdit={onEdit}
                cascaded={cascadedFields?.includes(f.field_id)}
                onDrillDown={onDrillDown}
                reportType={reportType}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ============================================================================
// Group Table — (5) question numbers in header, black header text
// ============================================================================

const GROUP_LABELS = {
  main_instruments: "Main instruments traded (ranked)",
  nav_geographical_focus: "NAV geographical focus",
  aum_geographical_focus: "AUM geographical focus",
  principal_exposures: "Principal exposures (ranked)",
  portfolio_concentrations: "Portfolio concentrations (ranked)",
  fund_to_counterparty: "Top 5 counterparty exposures (fund to counterparty)",
  counterparty_to_fund: "Top 5 counterparty exposures (counterparty to fund)",
  ccp_exposures: "CCP exposures",
  asset_type_exposures: "Individual exposures by asset type",
  asset_type_turnovers: "Turnover by asset class",
  currency_exposures: "Currency exposures",
  borrowing_sources: "Largest borrowing sources",
  funding_jurisdictions: "Funding source jurisdictions",
  market_risk_measures: "Market risk measures",
  strategies: "Investment strategies",
  investor_groups: "Investor groups",
  share_classes: "Share classes",
  aif_principal_markets: "Principal markets",
  aifm_principal_markets: "Principal markets (AIFM)",
  aifm_principal_instruments: "Principal instruments (AIFM)",
  dominant_influence: "Dominant influence",
  controlled_structures: "Controlled structures",
  monthly_returns: "Monthly returns",
  monthly_navs: "Monthly NAVs",
  monthly_data: "Monthly data (returns, NAV, subscriptions, redemptions)",
};

// (5) Question number ranges for each group — aligned with ESMA Annex IV numbering
const GROUP_QUESTION_RANGES = {
  aifm_principal_markets: "Q26\u2013Q29",
  aifm_principal_instruments: "Q30\u2013Q32",
  share_classes: "Q34\u2013Q40",
  strategies: "Q58\u2013Q61",
  main_instruments: "Q64\u2013Q77",
  nav_geographical_focus: "Q78\u2013Q85",
  aum_geographical_focus: "Q86\u2013Q93",
  principal_exposures: "Q94\u2013Q102",
  portfolio_concentrations: "Q103\u2013Q112",
  aif_principal_markets: "Q114\u2013Q117",
  asset_type_exposures: "Q121\u2013Q124",
  asset_type_turnovers: "Q125\u2013Q127",
  currency_exposures: "Q128\u2013Q130",
  dominant_influence: "Q131\u2013Q136",
  market_risk_measures: "Q138\u2013Q147",
  fund_to_counterparty: "Q160\u2013Q165",
  counterparty_to_fund: "Q166\u2013Q171",
  ccp_exposures: "Q173\u2013Q177",
  investor_groups: "Q208\u2013Q209",
  monthly_data: "Q219\u2013Q278",
  controlled_structures: "Q290\u2013Q293",
  borrowing_sources: "Q296\u2013Q301",
};

// Groups derived from source data — read-only, click opens source modal.
// Value = source entity type to drill down to, or null if purely calculated.
const DERIVED_GROUPS = {
  // AIF — Derived from positions
  main_instruments: "positions",
  principal_exposures: "positions",
  portfolio_concentrations: "positions",
  asset_type_exposures: "positions",
  currency_exposures: "positions",
  nav_geographical_focus: "positions",
  aum_geographical_focus: "positions",
  // AIF — Derived from transactions
  asset_type_turnovers: "transactions",
  // AIF — Derived from other source entities
  aif_principal_markets: "positions",
  investor_groups: "investors",
  strategies: "strategies",
  market_risk_measures: "risk_measures",
  // AIF — Calculated (no single source)
  monthly_data: null,
  // AIFM — Derived from positions (aggregated across all AIFs)
  aifm_principal_markets: "positions",
  aifm_principal_instruments: "positions",
};

function GroupTable({ groupName, rows, columnNames, obligations, onEditGroup, onDrillDown, reportType }) {
  const idPrefix = reportType === "AIFM" ? "AFM" : "Q";
  const [open, setOpen] = useState(true);
  const [editCell, setEditCell] = useState(null); // { row, col }
  const [editValue, setEditValue] = useState("");
  if (!rows || rows.length === 0) return null;

  const isDerived = groupName in DERIVED_GROUPS;
  const derivedSource = DERIVED_GROUPS[groupName]; // e.g. "positions"

  const label = GROUP_LABELS[groupName] || groupName.replace(/_/g, " ");
  const qRange = GROUP_QUESTION_RANGES[groupName] || "";
  const columns = Object.keys(rows[0]).filter((k) => k !== "field_id");

  // (5) Use columnNames from backend (field_id -> human name), show Q# + name + obligation
  const OB_SHORT = { M: "Mandatory", C: "Conditional", O: "Optional", F: "Forbidden" };
  const colHeader = (col) => {
    const humanName = columnNames && columnNames[col] ? columnNames[col] : col.replace(/_/g, " ");
    const ob = obligations && obligations[col] ? obligations[col] : "";
    const isNumeric = /^\d+$/.test(col);
    const obTag = ob ? ` [${ob}]` : "";
    if (isNumeric) return `${idPrefix}${col}: ${humanName}${obTag}`;
    return humanName;
  };
  const colObligation = (col) => obligations && obligations[col] ? obligations[col] : "";

  // A cell is "data-populated" if it carries an actual submitted value.
  // Empty strings, nulls and the ESMA "NOT" placeholder (used to fill
  // unused slots in top-N lists like Principal markets/instruments) all
  // count as "not populated".
  const isCellPopulated = (val) => {
    if (val == null) return false;
    const s = String(val).trim();
    if (s === "") return false;
    if (s.toUpperCase() === "NOT") return false;
    return true;
  };

  // A row is "empty" when the ranking column (if any) is the only thing
  // populated — all other cells are empty or carry the NOT placeholder.
  // Empty rows render in neutral grey so they don't fight the validation
  // colors of rows that actually contain data.
  const isEmptyRow = (row) => {
    let hasDataBeyondRanking = false;
    for (const col of columns) {
      // Treat single-digit numeric columns like "26" (ranking) as metadata:
      // rankings are always populated in a top-N table and shouldn't count
      // as "real" data that flips the row into coloured mode.
      const lowerName = (columnNames && columnNames[col] ? columnNames[col] : col).toLowerCase();
      const isRanking = lowerName.includes("ranking") || lowerName === "#";
      if (isRanking) continue;
      if (isCellPopulated(row[col])) {
        hasDataBeyondRanking = true;
        break;
      }
    }
    return !hasDataBeyondRanking;
  };

  // Traffic-light background for group cells — mirrors validationBg() for single fields.
  // Populated cells are treated as PASS (green); empty cells inherit color from the
  // column's obligation (Mandatory→red, Conditional→orange, Optional/unknown→neutral).
  // Empty rows short-circuit to neutral grey regardless of obligation — an
  // empty slot in a top-5 list is not a validation error.
  const cellValidationBg = (col, val, rowIsEmpty) => {
    if (rowIsEmpty) return "bg-gray-50";
    if (isCellPopulated(val)) return "bg-green-200";
    const ob = colObligation(col);
    if (ob === "M") return "bg-red-200";
    if (ob === "C") return "bg-orange-200";
    if (ob === "F") return "bg-gray-50"; // forbidden-empty is fine
    return "bg-gray-50";
  };

  const handleCellClick = (rowIdx, col) => {
    // Derived groups: open source modal instead of editing
    if (isDerived) {
      if (derivedSource && onDrillDown) {
        onDrillDown({ field_id: col, category: "composite", _sourceEntity: derivedSource });
      }
      return;
    }
    if (!onEditGroup) return;
    setEditCell({ row: rowIdx, col });
    setEditValue(rows[rowIdx][col] != null ? String(rows[rowIdx][col]) : "");
  };

  const handleCellSave = () => {
    if (!editCell || !onEditGroup) return;
    onEditGroup(groupName, editCell.row, editCell.col, editValue);
    setEditCell(null);
  };

  const handleCellKeyDown = (e) => {
    if (e.key === "Enter") handleCellSave();
    else if (e.key === "Escape") setEditCell(null);
  };

  return (
    <div className="border border-blue-100 rounded-lg mb-2 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 bg-blue-50 hover:bg-blue-100 transition"
      >
        <div className="flex items-center gap-3">
          <span className="text-blue-400">{open ? "\u25BC" : "\u25B6"}</span>
          <span className="font-medium text-blue-800 text-sm">{label}</span>
          {qRange && <span className="text-xs text-blue-400 font-mono">{qRange}</span>}
          {isDerived && derivedSource && (
            <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">
              derived from {derivedSource}
            </span>
          )}
          {isDerived && !derivedSource && (
            <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded font-medium">
              calculated
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-blue-500">{rows.length} row{rows.length !== 1 ? "s" : ""}</span>
          {onDrillDown && (isDerived ? derivedSource : true) && (
            <span
              className="text-xs text-blue-400 hover:text-blue-600 cursor-pointer"
              title={`View underlying source data (${derivedSource || "positions"})`}
              onClick={(e) => { e.stopPropagation(); onDrillDown({ field_id: columns[0], category: "composite", _sourceEntity: derivedSource }); }}
            >
              {`[${derivedSource || "source"} \u2192]`}
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              {/* (5) Black header text. The `#` row-counter column was
                  removed because it duplicated the Ranking column in the
                  Principal markets / Principal instruments groups. */}
              <tr className="bg-blue-50 text-xs text-gray-900">
                {columns.map((col) => (
                  <th key={col} className="px-2 py-1 text-left font-semibold" title={`Field ${col}`}>
                    {colHeader(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => {
                const rowIsEmpty = isEmptyRow(row);
                return (
                <tr key={idx} className="border-b border-blue-50 hover:bg-gray-50">
                  {columns.map((col) => {
                    const cellVal = row[col];
                    const vBg = cellValidationBg(col, cellVal, rowIsEmpty);
                    const interactionCls = isDerived && derivedSource
                      ? "cursor-pointer hover:brightness-95 text-gray-700"
                      : onEditGroup
                        ? "cursor-pointer hover:brightness-95 text-gray-900"
                        : "text-gray-900";
                    return (
                    <td
                      key={col}
                      className={`px-2 py-1 ${vBg} ${interactionCls}`}
                      title={isDerived && derivedSource ? `Derived from ${derivedSource} — click to view source data` : undefined}
                      onClick={() => handleCellClick(idx, col)}
                    >
                      {editCell && editCell.row === idx && editCell.col === col ? (
                        <input
                          type="text"
                          className="w-full border border-blue-300 rounded px-1 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={handleCellSave}
                          onKeyDown={handleCellKeyDown}
                          autoFocus
                        />
                      ) : row[col] != null && row[col] !== "" ? (
                        String(row[col])
                      ) : (
                        <span className="text-gray-300">{"\u2014"}</span>
                      )}
                    </td>
                    );
                  })}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Source Data Editor
// ============================================================================

// Domain values for AIFMD Annex IV dropdown fields
// Human-readable labels for domain codes (from ESMA XSD specification)
const SOURCE_DOMAIN_LABELS = {
  // Regions
  AFRICA: "Africa", ASIAPACIFIC: "Asia and Pacific", EUROPEEEA: "Europe (EEA)",
  EUROPENONEEA: "Europe (non-EEA)", MIDDLEEAST: "Middle East",
  NORTHAMERICA: "North America", SOUTHAMERICA: "South America",
  SUPRANATIONAL: "Supranational / multiple",
  // ISO-2 country codes — EEA
  AT: "Austria (EEA)", BE: "Belgium (EEA)", BG: "Bulgaria (EEA)", CY: "Cyprus (EEA)",
  CZ: "Czechia (EEA)", DE: "Germany (EEA)", DK: "Denmark (EEA)", EE: "Estonia (EEA)",
  ES: "Spain (EEA)", FI: "Finland (EEA)", FR: "France (EEA)", GR: "Greece (EEA)",
  HR: "Croatia (EEA)", HU: "Hungary (EEA)", IE: "Ireland (EEA)", IS: "Iceland (EEA)",
  IT: "Italy (EEA)", LI: "Liechtenstein (EEA)", LT: "Lithuania (EEA)", LU: "Luxembourg (EEA)",
  LV: "Latvia (EEA)", MT: "Malta (EEA)", NL: "Netherlands (EEA)", NO: "Norway (EEA)",
  PL: "Poland (EEA)", PT: "Portugal (EEA)", RO: "Romania (EEA)", SE: "Sweden (EEA)",
  SI: "Slovenia (EEA)", SK: "Slovakia (EEA)",
  // ISO-2 — Europe non-EEA
  AD: "Andorra (Europe non-EEA)", AL: "Albania (Europe non-EEA)", BA: "Bosnia and Herzegovina (Europe non-EEA)",
  BY: "Belarus (Europe non-EEA)", CH: "Switzerland (Europe non-EEA)", FO: "Faroe Islands (Europe non-EEA)",
  GB: "United Kingdom (Europe non-EEA)", GG: "Guernsey (Europe non-EEA)", GI: "Gibraltar (Europe non-EEA)",
  IM: "Isle of Man (Europe non-EEA)", JE: "Jersey (Europe non-EEA)", MD: "Moldova (Europe non-EEA)",
  ME: "Montenegro (Europe non-EEA)", MK: "North Macedonia (Europe non-EEA)", RS: "Serbia (Europe non-EEA)",
  RU: "Russia (Europe non-EEA)", SM: "San Marino (Europe non-EEA)", TR: "Turkey (Europe non-EEA)",
  UA: "Ukraine (Europe non-EEA)", VA: "Vatican (Europe non-EEA)",
  // ISO-2 — Africa
  AO: "Angola (Africa)", BF: "Burkina Faso (Africa)", BI: "Burundi (Africa)", BJ: "Benin (Africa)",
  BW: "Botswana (Africa)", CD: "DR Congo (Africa)", CF: "Central African Rep. (Africa)",
  CG: "Congo (Africa)", CI: "Côte d'Ivoire (Africa)", CM: "Cameroon (Africa)", CV: "Cabo Verde (Africa)",
  DJ: "Djibouti (Africa)", DZ: "Algeria (Africa)", EG: "Egypt (Africa)", ER: "Eritrea (Africa)",
  ET: "Ethiopia (Africa)", GA: "Gabon (Africa)", GH: "Ghana (Africa)", GM: "Gambia (Africa)",
  GN: "Guinea (Africa)", GQ: "Equatorial Guinea (Africa)", GW: "Guinea-Bissau (Africa)",
  IO: "British Indian Ocean Terr. (Africa)", KE: "Kenya (Africa)", KM: "Comoros (Africa)",
  LR: "Liberia (Africa)", LS: "Lesotho (Africa)", LY: "Libya (Africa)", MA: "Morocco (Africa)",
  MG: "Madagascar (Africa)", ML: "Mali (Africa)", MR: "Mauritania (Africa)", MU: "Mauritius (Africa)",
  MW: "Malawi (Africa)", MZ: "Mozambique (Africa)", NA: "Namibia (Africa)", NE: "Niger (Africa)",
  NG: "Nigeria (Africa)", RW: "Rwanda (Africa)", SC: "Seychelles (Africa)", SD: "Sudan (Africa)",
  SH: "Saint Helena (Africa)", SL: "Sierra Leone (Africa)", SN: "Senegal (Africa)", SO: "Somalia (Africa)",
  SS: "South Sudan (Africa)", ST: "São Tomé and Príncipe (Africa)", SZ: "Eswatini (Africa)",
  TD: "Chad (Africa)", TG: "Togo (Africa)", TN: "Tunisia (Africa)", TZ: "Tanzania (Africa)",
  UG: "Uganda (Africa)", ZA: "South Africa (Africa)", ZM: "Zambia (Africa)", ZW: "Zimbabwe (Africa)",
  // ISO-2 — North America
  CA: "Canada (North America)", GL: "Greenland (North America)", US: "United States (North America)",
  // ISO-2 — South America (incl. Central America, Caribbean)
  AG: "Antigua and Barbuda (South America)", AI: "Anguilla (South America)", AR: "Argentina (South America)",
  AW: "Aruba (South America)", BB: "Barbados (South America)", BM: "Bermuda (South America)",
  BO: "Bolivia (South America)", BQ: "Bonaire (South America)", BR: "Brazil (South America)",
  BS: "Bahamas (South America)", BZ: "Belize (South America)", CL: "Chile (South America)",
  CO: "Colombia (South America)", CR: "Costa Rica (South America)", CU: "Cuba (South America)",
  CW: "Curaçao (South America)", DM: "Dominica (South America)", DO: "Dominican Rep. (South America)",
  EC: "Ecuador (South America)", FK: "Falkland Islands (South America)", GD: "Grenada (South America)",
  GT: "Guatemala (South America)", GY: "Guyana (South America)", HN: "Honduras (South America)",
  HT: "Haiti (South America)", JM: "Jamaica (South America)", KN: "St Kitts and Nevis (South America)",
  KY: "Cayman Islands (South America)", LC: "Saint Lucia (South America)", MS: "Montserrat (South America)",
  MX: "Mexico (South America)", NI: "Nicaragua (South America)", PA: "Panama (South America)",
  PE: "Peru (South America)", PY: "Paraguay (South America)", SR: "Suriname (South America)",
  SV: "El Salvador (South America)", SX: "Sint Maarten (South America)", TC: "Turks and Caicos (South America)",
  TT: "Trinidad and Tobago (South America)", UY: "Uruguay (South America)", VC: "St Vincent (South America)",
  VE: "Venezuela (South America)", VG: "British Virgin Islands (South America)", VI: "US Virgin Islands (South America)",
  // ISO-2 — Middle East
  AE: "United Arab Emirates (Middle East)", AM: "Armenia (Middle East)", AZ: "Azerbaijan (Middle East)",
  BH: "Bahrain (Middle East)", GE: "Georgia (Middle East)", IL: "Israel (Middle East)",
  IQ: "Iraq (Middle East)", IR: "Iran (Middle East)", JO: "Jordan (Middle East)",
  KW: "Kuwait (Middle East)", LB: "Lebanon (Middle East)", OM: "Oman (Middle East)",
  PS: "Palestine (Middle East)", QA: "Qatar (Middle East)", SA: "Saudi Arabia (Middle East)",
  SY: "Syria (Middle East)", YE: "Yemen (Middle East)",
  // ISO-2 — Asia Pacific
  AF: "Afghanistan (Asia Pacific)", AS: "American Samoa (Asia Pacific)", AU: "Australia (Asia Pacific)",
  BD: "Bangladesh (Asia Pacific)", BN: "Brunei (Asia Pacific)", BT: "Bhutan (Asia Pacific)",
  CN: "China (Asia Pacific)", FJ: "Fiji (Asia Pacific)", HK: "Hong Kong (Asia Pacific)",
  ID: "Indonesia (Asia Pacific)", IN: "India (Asia Pacific)", JP: "Japan (Asia Pacific)",
  KG: "Kyrgyzstan (Asia Pacific)", KH: "Cambodia (Asia Pacific)", KI: "Kiribati (Asia Pacific)",
  KP: "North Korea (Asia Pacific)", KR: "South Korea (Asia Pacific)", KZ: "Kazakhstan (Asia Pacific)",
  LA: "Laos (Asia Pacific)", LK: "Sri Lanka (Asia Pacific)", MH: "Marshall Islands (Asia Pacific)",
  MM: "Myanmar (Asia Pacific)", MN: "Mongolia (Asia Pacific)", MO: "Macao (Asia Pacific)",
  MV: "Maldives (Asia Pacific)", MY: "Malaysia (Asia Pacific)", NP: "Nepal (Asia Pacific)",
  NZ: "New Zealand (Asia Pacific)", PH: "Philippines (Asia Pacific)", PK: "Pakistan (Asia Pacific)",
  SG: "Singapore (Asia Pacific)", TH: "Thailand (Asia Pacific)", TJ: "Tajikistan (Asia Pacific)",
  TL: "Timor-Leste (Asia Pacific)", TM: "Turkmenistan (Asia Pacific)", TW: "Taiwan (Asia Pacific)",
  UZ: "Uzbekistan (Asia Pacific)", VN: "Vietnam (Asia Pacific)",
  // Sub-asset types — Securities
  SEC_CSH_CODP: "Certificates of deposit", SEC_CSH_COMP: "Commercial papers",
  SEC_CSH_OTHD: "Other deposits", SEC_CSH_OTHC: "Other cash and cash equiv.",
  SEC_LEQ_IFIN: "Listed equities (financial inst.)", SEC_LEQ_OTHR: "Other listed equity",
  SEC_UEQ_UEQY: "Unlisted equities",
  SEC_CPN_INVG: "Corp. bonds non-fin. (inv. grade)", SEC_CPN_NIVG: "Corp. bonds non-fin. (non-inv. grade)",
  SEC_CPI_INVG: "Corp. bonds fin. (inv. grade)", SEC_CPI_NIVG: "Corp. bonds fin. (non-inv. grade)",
  SEC_SBD_EUBY: "EU bonds (0-1yr)", SEC_SBD_EUBM: "EU bonds (1+yr)",
  SEC_SBD_NOGY: "Non-G10 bonds (0-1yr)", SEC_SBD_NOGM: "Non-G10 bonds (1+yr)",
  SEC_SBD_EUGY: "G10 non-EU bonds (0-1yr)", SEC_SBD_EUGM: "G10 non-EU bonds (1+yr)",
  SEC_MBN_MNPL: "Municipal bonds",
  SEC_CBN_INVG: "Conv. bonds non-fin. (inv. grade)", SEC_CBN_NIVG: "Conv. bonds non-fin. (non-inv. grade)",
  SEC_CBI_INVG: "Conv. bonds fin. (inv. grade)", SEC_CBI_NIVG: "Conv. bonds fin. (non-inv. grade)",
  SEC_LON_LEVL: "Leveraged loans", SEC_LON_OTHL: "Other loans",
  SEC_SSP_SABS: "ABS", SEC_SSP_RMBS: "RMBS", SEC_SSP_CMBS: "CMBS",
  SEC_SSP_AMBS: "Agency MBS", SEC_SSP_ABCP: "ABCP", SEC_SSP_CDOC: "CDO/CLO",
  SEC_SSP_STRC: "Structured certificates", SEC_SSP_SETP: "ETP", SEC_SSP_OTHS: "Other structured/securitised",
  // Sub-asset types — Derivatives
  DER_EQD_FINI: "Equity deriv. (financial inst.)", DER_EQD_OTHD: "Other equity derivatives",
  DER_FID_FIXI: "Fixed income derivatives",
  DER_CDS_SNFI: "Single name financial CDS", DER_CDS_SNSO: "Single name sovereign CDS",
  DER_CDS_SNOT: "Single name other CDS", DER_CDS_INDX: "Index CDS",
  DER_CDS_EXOT: "Exotic CDS", DER_CDS_OTHR: "Other CDS",
  DER_FEX_INVT: "FX (investment)", DER_FEX_HEDG: "FX (hedging)",
  DER_IRD_INTR: "Interest rate derivatives",
  DER_CTY_ECOL: "Energy/Crude oil", DER_CTY_ENNG: "Energy/Natural gas",
  DER_CTY_ENPW: "Energy/Power", DER_CTY_ENOT: "Energy/Other",
  DER_CTY_PMGD: "Precious metals/Gold", DER_CTY_PMOT: "Precious metals/Other",
  DER_CTY_OTIM: "Industrial metals", DER_CTY_OTLS: "Livestock",
  DER_CTY_OTAP: "Agricultural products", DER_CTY_OTHR: "Other commodities",
  DER_OTH_OTHR: "Other derivatives",
  // Sub-asset types — Physical
  PHY_RES_RESL: "Residential real estate", PHY_RES_COML: "Commercial real estate",
  PHY_RES_OTHR: "Other real estate", PHY_CTY_PCTY: "Physical: Commodities",
  PHY_TIM_PTIM: "Physical: Timber", PHY_ART_PART: "Physical: Art and collectables",
  PHY_TPT_PTPT: "Physical: Transportation assets", PHY_OTH_OTHR: "Physical: Other",
  // Sub-asset types — CIU
  CIU_OAM_MMFC: "CIU managed by AIFM: MMF", CIU_OAM_AETF: "CIU managed by AIFM: ETF",
  CIU_OAM_OTHR: "CIU managed by AIFM: Other",
  CIU_NAM_MMFC: "CIU not managed by AIFM: MMF", CIU_NAM_AETF: "CIU not managed by AIFM: ETF",
  CIU_NAM_OTHR: "CIU not managed by AIFM: Other",
  OTH_OTH_OTHR: "Total Other", NTA_NTA_NOTA: "N/A",
  // Long/Short
  L: "Long", S: "Short",
  // Investment strategies — Hedge fund
  EQTY_LGBS: "Equity: Long Bias", EQTY_LGST: "Equity: Long/Short",
  EQTY_MTNL: "Equity: Market Neutral", EQTY_STBS: "Equity: Short Bias",
  RELV_FXIA: "Relative Value: Fixed Income Arb.", RELV_CBAR: "Relative Value: Conv. Bond Arb.",
  RELV_VLAR: "Relative Value: Volatility Arb.",
  EVDR_DSRS: "Event Driven: Distressed", EVDR_RAMA: "Event Driven: Merger Arb.",
  EVDR_EYSS: "Event Driven: Equity Special Sit.",
  CRED_LGST: "Credit Long/Short", CRED_ABLG: "Credit Asset Based Lending",
  MACR_MACR: "Macro",
  MANF_CTAF: "Managed Futures/CTA: Fundamental", MANF_CTAQ: "Managed Futures/CTA: Quantitative",
  MULT_HFND: "Multi-strategy hedge fund", OTHR_HFND: "Other hedge fund strategy",
  // Investment strategies — Private equity
  VENT_CAPL: "Venture Capital", GRTH_CAPL: "Growth Capital", MZNE_CAPL: "Mezzanine Capital",
  MULT_PEQF: "Multi-strategy PE fund", OTHR_PEQF: "Other PE fund strategy",
  // Investment strategies — Real estate
  RESL_REST: "Residential real estate", COML_REST: "Commercial real estate",
  INDL_REST: "Industrial real estate", MULT_REST: "Multi-strategy RE fund", OTHR_REST: "Other RE strategy",
  // Investment strategies — Fund of funds
  FOFS_FHFS: "Fund of hedge funds", FOFS_PRIV: "Fund of private equity", OTHR_FOFS: "Other fund of funds",
  // Investment strategies — Other
  OTHR_COMF: "Commodity Fund", OTHR_EQYF: "Equity fund", OTHR_FXIF: "Fixed income fund",
  OTHR_INFF: "Infrastructure fund", OTHR_OTHF: "Other fund",
  // Investor type groups
  NFCO: "Non-financial corporations", BANK: "Banks", INSC: "Insurance corporations",
  OFIN: "Other financial institutions", PFND: "Pension plans/funds",
  GENG: "General government", OCIU: "Other CIU (e.g. fund of funds)",
  HHLD: "Households", UNKN: "Unknown", NONE: "None",
};

// ============================================================================
// AIFMD reference-table labels — human-readable descriptions for header fields
// Keyed by `allowed_values_ref` name (from aifmd_validation_rules.yaml)
// Used by EditableCell when rendering a dropdown for fields 4, 5, 8, 13, 16,
// 20, 21, 35, 36, etc.
// ============================================================================
const AIFMD_REF_LABELS = {
  filing_types: {
    INIT: "Initial filing",
    AMND: "Amendment of a previously submitted filing",
    CANC: "Cancellation of a previously submitted filing",
    CANCEL: "Cancellation of a previously submitted filing",
  },
  // AFM5 — AIFM content type. Business-friendly labels. The numeric ↔ label
  // mapping MUST respect ESMA Technical Guidance Rev.6:
  //   1 = Art 24(1) reporting for all AIFs managed       → Authorised (full-scope)
  //   2 = Art 3(3)(d) reporting for all AIFs managed     → Registered (sub-threshold)
  //   3 = Art 24(1) reporting for all AIFs marketed      → NPPR (typically non-EU)
  // See aifmd_validation_rules.yaml → reference_table_labels.aifm_content_types.
  aifm_content_types: {
    "1": "Authorised/Licensed Manager",
    "2": "Registered/Light Manager",
    "3": "NPPR/Non-EU Manager",
  },
  // AIF-5 — AIF content type. ESMA Technical Guidance Rev.6:
  //   1 = Art 24(1) reporting obligation
  //   2 = Art 24(1) + 24(2) reporting obligation
  //   3 = Art 3(3)(d) reporting obligation
  //   4 = Art 24(1) + 24(2) + 24(4) reporting obligation
  //   5 = Art 24(1) + 24(4) reporting obligation
  aif_content_types: {
    "1": "AIF reporting — Art. 24(1)",
    "2": "AIF reporting — Art. 24(1) + 24(2)",
    "3": "AIF reporting — Art. 3(3)(d)",
    "4": "AIF reporting — Art. 24(1) + 24(2) + 24(4)",
    "5": "AIF reporting — Art. 24(1) + 24(4)",
  },
  reporting_period_types: {
    Q1: "Quarter 1 (Jan–Mar)",
    Q2: "Quarter 2 (Apr–Jun)",
    Q3: "Quarter 3 (Jul–Sep)",
    Q4: "Quarter 4 (Oct–Dec)",
    H1: "First half (Jan–Jun)",
    H2: "Second half (Jul–Dec)",
    Y1: "Annual (full calendar year)",
    X1: "First ad-hoc period",
    X2: "Second ad-hoc period",
  },
  boolean_values: {
    true: "Yes",
    false: "No",
    TRUE: "Yes",
    FALSE: "No",
  },
  fx_rate_source: {
    ECB: "European Central Bank reference rate",
    OTH: "Other source (disclose in narrative)",
    OTHR: "Other source (disclose in narrative)",
  },
  cancelled_record_flag: {
    C: "Cancellation — corrected by firm",
    D: "Deletion — removed by NCA",
  },
  // AFM16 — AIFM reporting code. Values 1-9 per ESMA Annex IV Technical
  // Guidance Rev.6 (AIFM-16). The reference table in the YAML exposes '1'
  // through '9' but without descriptions, so the viewer used to show only
  // the raw number. These labels provide the human-readable description
  // shown as "<code> — <label>" alongside the value.
  aifm_reporting_codes: {
    "1": "Registered AIFM (Art. 3)",
    "2": "Authorised AIFM — opt-in (Art. 7)",
    "3": "Authorised AIFM — unleveraged, non-listed control (Art. 7)",
    "4": "Authorised AIFM — half-yearly obligation (Art. 7)",
    "5": "Authorised AIFM — quarterly obligation (Art. 7)",
    "6": "Non-EU AIFM under NPPR — annual obligation",
    "7": "Non-EU AIFM under NPPR — half-yearly obligation",
    "8": "Non-EU AIFM under NPPR — quarterly obligation",
    "9": "Non-EU AIFM — no-reporting period",
  },
  aif_reporting_codes: {
    "1": "Sub-threshold AIF (Art. 3)",
    "2": "AIF managed by authorised AIFM — below thresholds",
    "3": "Non-EU AIF marketed in EU (NPPR)",
    "4": "EU AIF managed by EU AIFM",
    "5": "EU AIF managed by non-EU AIFM",
  },
  frequency_change_codes: {
    Q: "Quarterly",
    H: "Half-yearly",
    Y: "Yearly",
    N: "No change",
  },
  aifm_contents_change_codes: {
    A: "Added content",
    R: "Removed content",
    N: "No change",
  },
};

// Fallback option list for fields with `allowed_values_ref: iso_country_code`.
// The YAML validation-rules file doesn't include a reference_tables entry
// for ISO country codes (they're validated via `validation_type: iso_check`),
// so the backend returns an empty `reference_values` list for fields like
// AFM17 (AIFM jurisdiction), AFM24 (AIFM home jurisdiction), Q21 (AIF domicile),
// etc. EditableCell picks this list up when the backend list is empty.
// Labels come from SOURCE_DOMAIN_LABELS which already covers all 250 ISO-2
// country codes.
const ISO_COUNTRY_CODES = [
  // EEA (30)
  "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
  "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO",
  "PL", "PT", "RO", "SE", "SI", "SK",
  // Europe non-EEA
  "AD", "AL", "BA", "BY", "CH", "FO", "GB", "GG", "GI", "IM", "JE",
  "MD", "ME", "MK", "RS", "RU", "SM", "TR", "UA", "VA",
  // Africa
  "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV",
  "DJ", "DZ", "EG", "ER", "ET", "GA", "GH", "GM", "GN", "GQ", "GW",
  "IO", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU",
  "MW", "MZ", "NA", "NE", "NG", "RW", "SC", "SD", "SH", "SL", "SN",
  "SO", "SS", "ST", "SZ", "TD", "TG", "TN", "TZ", "UG", "ZA", "ZM", "ZW",
  // North America
  "CA", "GL", "US",
  // South America + Central America + Caribbean
  "AG", "AI", "AR", "AW", "BB", "BM", "BO", "BQ", "BR", "BS", "BZ",
  "CL", "CO", "CR", "CU", "CW", "DM", "DO", "EC", "FK", "GD", "GT",
  "GY", "HN", "HT", "JM", "KN", "KY", "LC", "MS", "MX", "NI", "PA",
  "PE", "PY", "SR", "SV", "SX", "TC", "TT", "UY", "VC", "VE", "VG", "VI",
  // Middle East
  "AE", "AM", "AZ", "BH", "GE", "IL", "IQ", "IR", "JO", "KW", "LB",
  "OM", "PS", "QA", "SA", "SY", "YE",
  // Asia Pacific
  "AF", "AS", "AU", "BD", "BN", "BT", "CC", "CK", "CN", "CX", "FJ",
  "FM", "GU", "HK", "HM", "ID", "IN", "JP", "KG", "KH", "KI", "KP",
  "KR", "KZ", "LA", "LK", "MH", "MM", "MN", "MO", "MP", "MV", "MY",
  "NC", "NF", "NP", "NR", "NU", "NZ", "PF", "PG", "PH", "PK", "PN",
  "PW", "SB", "SG", "TH", "TJ", "TK", "TL", "TM", "TO", "TV", "TW",
  "UM", "UZ", "VN", "VU", "WF", "WS",
];

// Fallback option list for fields with `allowed_values_ref: iso_currency_code`.
// Same reason as ISO_COUNTRY_CODES: the validator uses iso_check, so the
// backend reference_values is empty. Used by AFM35 (AIFM base currency) and
// AIF base currency fields. List is the ISO 4217 alphabetic codes.
const ISO_CURRENCY_CODES = [
  "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
  "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
  "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHE", "CHF",
  "CHW", "CLF", "CLP", "CNY", "COP", "COU", "CRC", "CUC", "CUP", "CVE",
  "CZK", "DJF", "DKK", "DOP", "DZD", "EGP", "ERN", "ETB", "EUR", "FJD",
  "FKP", "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
  "HNL", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK", "JMD",
  "JOD", "JPY", "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD", "KYD",
  "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD", "MAD", "MDL", "MGA",
  "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN", "MXV",
  "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD", "OMR", "PAB",
  "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD", "RUB",
  "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SLL",
  "SOS", "SRD", "SSP", "STN", "SVC", "SYP", "SZL", "THB", "TJS", "TMT",
  "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "USN",
  "UYI", "UYU", "UYW", "UZS", "VED", "VES", "VND", "VUV", "WST", "XAF",
  "XAG", "XAU", "XBA", "XBB", "XBC", "XBD", "XCD", "XDR", "XOF", "XPD",
  "XPF", "XPT", "XSU", "XTS", "XUA", "YER", "ZAR", "ZMW", "ZWL",
];

const SOURCE_DOMAIN_VALUES = {
  region: [
    // AIFMD region codes (used in reporting output)
    "AFRICA", "ASIAPACIFIC", "EUROPEEEA", "EUROPENONEEA",
    "MIDDLEEAST", "NORTHAMERICA", "SOUTHAMERICA", "SUPRANATIONAL",
    // ISO-2 country codes — EEA
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR",
    "GR", "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT",
    "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
    // ISO-2 — Europe non-EEA
    "AD", "AL", "BA", "BY", "CH", "FO", "GB", "GG", "GI", "IM", "JE",
    "MD", "ME", "MK", "RS", "RU", "SM", "TR", "UA", "VA",
    // ISO-2 — Africa
    "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM", "CV",
    "DJ", "DZ", "EG", "ER", "ET", "GA", "GH", "GM", "GN", "GQ", "GW",
    "IO", "KE", "KM", "LR", "LS", "LY", "MA", "MG", "ML", "MR", "MU",
    "MW", "MZ", "NA", "NE", "NG", "RW", "SC", "SD", "SH", "SL", "SN",
    "SO", "SS", "ST", "SZ", "TD", "TG", "TN", "TZ", "UG", "ZA", "ZM", "ZW",
    // ISO-2 — North America
    "CA", "GL", "US",
    // ISO-2 — South America (incl. Central America, Caribbean per ESMA)
    "AG", "AI", "AR", "AW", "BB", "BM", "BO", "BQ", "BR", "BS", "BZ",
    "CL", "CO", "CR", "CU", "CW", "DM", "DO", "EC", "FK", "GD", "GT",
    "GY", "HN", "HT", "JM", "KN", "KY", "LC", "MS", "MX", "NI", "PA",
    "PE", "PY", "SR", "SV", "SX", "TC", "TT", "UY", "VC", "VE", "VG", "VI",
    // ISO-2 — Middle East
    "AE", "AM", "AZ", "BH", "GE", "IL", "IQ", "IR", "JO", "KW", "LB",
    "OM", "PS", "QA", "SA", "SY", "YE",
    // ISO-2 — Asia Pacific
    "AF", "AS", "AU", "BD", "BN", "BT", "CC", "CK", "CN", "CX", "FJ",
    "FM", "GU", "HK", "HM", "ID", "IN", "JP", "KG", "KH", "KI", "KP",
    "KR", "KZ", "LA", "LK", "MH", "MM", "MN", "MO", "MP", "MV", "MY",
    "NC", "NF", "NP", "NR", "NU", "NZ", "PF", "PG", "PH", "PK", "PN",
    "PW", "SB", "SG", "TH", "TJ", "TK", "TL", "TM", "TO", "TV", "TW",
    "UM", "UZ", "VN", "VU", "WF", "WS",
  ],
  sub_asset_type: [
    // Securities — Cash
    "SEC_CSH_CODP", "SEC_CSH_COMP", "SEC_CSH_OTHD", "SEC_CSH_OTHC",
    // Securities — Listed equities
    "SEC_LEQ_IFIN", "SEC_LEQ_OTHR",
    // Securities — Unlisted equities
    "SEC_UEQ_UEQY",
    // Securities — Corporate bonds (non-financial)
    "SEC_CPN_INVG", "SEC_CPN_NIVG",
    // Securities — Corporate bonds (financial)
    "SEC_CPI_INVG", "SEC_CPI_NIVG",
    // Securities — Sovereign bonds
    "SEC_SBD_EUBY", "SEC_SBD_EUBM", "SEC_SBD_NOGY", "SEC_SBD_NOGM", "SEC_SBD_EUGY", "SEC_SBD_EUGM",
    // Securities — Municipal bonds
    "SEC_MBN_MNPL",
    // Securities — Convertible bonds
    "SEC_CBN_INVG", "SEC_CBN_NIVG", "SEC_CBI_INVG", "SEC_CBI_NIVG",
    // Securities — Loans
    "SEC_LON_LEVL", "SEC_LON_OTHL",
    // Securities — Structured/securitised
    "SEC_SSP_SABS", "SEC_SSP_RMBS", "SEC_SSP_CMBS", "SEC_SSP_AMBS", "SEC_SSP_ABCP",
    "SEC_SSP_CDOC", "SEC_SSP_STRC", "SEC_SSP_SETP", "SEC_SSP_OTHS",
    // Derivatives — Equity
    "DER_EQD_FINI", "DER_EQD_OTHD",
    // Derivatives — Fixed income
    "DER_FID_FIXI",
    // Derivatives — CDS
    "DER_CDS_SNFI", "DER_CDS_SNSO", "DER_CDS_SNOT", "DER_CDS_INDX", "DER_CDS_EXOT", "DER_CDS_OTHR",
    // Derivatives — Foreign exchange
    "DER_FEX_INVT", "DER_FEX_HEDG",
    // Derivatives — Interest rate
    "DER_IRD_INTR",
    // Derivatives — Commodity
    "DER_CTY_ECOL", "DER_CTY_ENNG", "DER_CTY_ENPW", "DER_CTY_ENOT",
    "DER_CTY_PMGD", "DER_CTY_PMOT", "DER_CTY_OTIM", "DER_CTY_OTLS",
    "DER_CTY_OTAP", "DER_CTY_OTHR",
    // Derivatives — Other
    "DER_OTH_OTHR",
    // Physical assets
    "PHY_RES_RESL", "PHY_RES_COML", "PHY_RES_OTHR",
    "PHY_CTY_PCTY", "PHY_TIM_PTIM", "PHY_ART_PART", "PHY_TPT_PTPT", "PHY_OTH_OTHR",
    // Collective investment undertakings
    "CIU_OAM_MMFC", "CIU_OAM_AETF", "CIU_OAM_OTHR",
    "CIU_NAM_MMFC", "CIU_NAM_AETF", "CIU_NAM_OTHR",
    // Other
    "OTH_OTH_OTHR", "NTA_NTA_NOTA",
  ],
  currency: [
    "EUR", "USD", "GBP", "CHF", "JPY", "AUD", "CAD", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "RON", "BGN", "HRK", "ISK", "RUB", "TRY", "ZAR",
    "BRL", "CNY", "HKD", "SGD", "KRW", "INR", "MXN", "NZD", "ILS", "THB",
    "MYR", "IDR", "PHP", "TWD", "CLP", "COP", "PEN", "ARS", "AED", "SAR",
    "QAR", "KWD", "BHD", "OMR", "EGP", "NGN", "KES",
  ],
  long_short: ["L", "S"],
  investment_strategy: [
    // Hedge fund — Equity
    "EQTY_LGBS", "EQTY_LGST", "EQTY_MTNL", "EQTY_STBS",
    // Hedge fund — Relative value
    "RELV_FXIA", "RELV_CBAR", "RELV_VLAR",
    // Hedge fund — Event driven
    "EVDR_DSRS", "EVDR_RAMA", "EVDR_EYSS",
    // Hedge fund — Credit
    "CRED_LGST", "CRED_ABLG",
    // Hedge fund — Macro
    "MACR_MACR",
    // Hedge fund — CTA/Managed futures
    "MANF_CTAF", "MANF_CTAQ",
    // Hedge fund — Multi/Other
    "MULT_HFND", "OTHR_HFND",
    // Private equity
    "VENT_CAPL", "GRTH_CAPL", "MZNE_CAPL", "MULT_PEQF", "OTHR_PEQF",
    // Real estate
    "RESL_REST", "COML_REST", "INDL_REST", "MULT_REST", "OTHR_REST",
    // Fund of funds
    "FOFS_FHFS", "FOFS_PRIV", "OTHR_FOFS",
    // Other fund types
    "OTHR_COMF", "OTHR_EQYF", "OTHR_FXIF", "OTHR_INFF", "OTHR_OTHF",
  ],
  investor_type_group: [
    "NFCO", "BANK", "INSC", "OFIN", "PFND",
    "GENG", "OCIU", "HHLD", "UNKN", "NONE",
  ],
};

// Map source field names to domain value keys.
// Keys must match the EXACT field names from the source data (human-readable, from M adapter).
// Also includes snake_case variants as fallback.
const FIELD_TO_DOMAIN = {
  // Region
  "Region": "region",
  "region": "region",
  "Geographical Focus": "region",
  "geographical_focus": "region",
  // Sub-asset type
  "Sub-Asset Type of Position": "sub_asset_type",
  "Sub-Asset Type of Turnover": "sub_asset_type",
  "Sub-asset type code of turnover": "sub_asset_type",
  "sub_asset_type": "sub_asset_type",
  "sub_asset_type_code": "sub_asset_type",
  // Currency
  "Currency of the exposure": "currency",
  "Currency": "currency",
  "Base Currency": "currency",
  "currency": "currency",
  "currency_of_the_exposure": "currency",
  "base_currency": "currency",
  // Long / Short
  "Long / Short": "long_short",
  "Long/Short": "long_short",
  "long_short": "long_short",
  // Investment strategy
  "Investment strategy code": "investment_strategy",
  "Investment Strategy": "investment_strategy",
  "investment_strategy": "investment_strategy",
  "investment_strategy_code": "investment_strategy",
  "predominant_aif_type": "investment_strategy",
  "strategy_code": "investment_strategy",
  // Investor type group
  "Investor Group Type": "investor_type_group",
  "Investor Type Group": "investor_type_group",
  "investor_type_group": "investor_type_group",
  "investor_group_type": "investor_type_group",
  "investor_type": "investor_type_group",
};

// Searchable dropdown: type to filter on code or description, click to select
function SearchableSelect({ value, options, labels, onChange, className = "", autoOpen = false }) {
  const [open, setOpen] = useState(autoOpen);
  const [search, setSearch] = useState("");
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  const filtered = search.trim()
    ? options.filter((v) => {
        const q = search.toLowerCase();
        return v.toLowerCase().includes(q) || (labels[v] || "").toLowerCase().includes(q);
      })
    : options;

  const displayValue = value ? `${value}${labels[value] ? " — " + labels[value] : ""}` : "—";

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => { setOpen(!open); setSearch(""); }}
        className="w-full text-left text-xs border border-gray-200 rounded px-1 py-0.5 bg-white hover:border-blue-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200 cursor-pointer truncate"
        title={displayValue}
      >
        {displayValue}
      </button>
      {open && (
        <div className="absolute z-[70] left-0 top-full mt-0.5 bg-white border border-gray-300 rounded shadow-lg min-w-[280px] max-w-[400px]">
          <div className="p-1 border-b border-gray-200">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Type to search..."
              className="w-full px-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
            />
          </div>
          <div className="max-h-60 overflow-y-auto">
            <div
              className="px-2 py-1 text-xs text-gray-400 cursor-pointer hover:bg-gray-100"
              onClick={() => { onChange(""); setOpen(false); }}
            >— (empty)</div>
            {filtered.map((v) => (
              <div
                key={v}
                className={`px-2 py-1 text-xs cursor-pointer hover:bg-blue-50 ${v === value ? "bg-blue-100 font-semibold" : ""}`}
                onClick={() => { onChange(v); setOpen(false); }}
              >
                <span className="font-mono">{v}</span>
                {labels[v] && <span className="text-gray-500 ml-1">— {labels[v]}</span>}
              </div>
            ))}
            {filtered.length === 0 && (
              <div className="px-2 py-2 text-xs text-gray-400 italic">No matches</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceDataEditor({ entityType, items, fieldNames, onEditItem, onAddItem, onDeleteItem }) {
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState({});
  const [pendingDelete, setPendingDelete] = useState(null);
  const pageSize = 50;

  const priorityFields = ["instrument_name", "name", "isin", "sub_asset_type", "market_value",
    "notional_value", "currency", "region", "market_type", "counterparty_name"];
  const sortedFields = [
    ...priorityFields.filter((f) => fieldNames.includes(f)),
    ...fieldNames.filter((f) => !priorityFields.includes(f)),
  ];

  // Apply column filters
  const filteredItems = items.filter((item) =>
    Object.entries(filters).every(([col, q]) => {
      if (!q) return true;
      const val = String(item[col] ?? "").toLowerCase();
      return val.includes(q.toLowerCase());
    })
  );

  const totalPages = Math.ceil(filteredItems.length / pageSize);
  const pageItems = filteredItems.slice(page * pageSize, (page + 1) * pageSize);

  const updateFilter = (col, val) => {
    setFilters((prev) => ({ ...prev, [col]: val }));
    setPage(0);
  };

  const hasActiveFilters = Object.values(filters).some((v) => v);

  // Render: table part (scrollable) + footer (sticky) returned separately via a wrapper
  return (
    <div className="flex flex-col h-full">
      {/* Delete confirmation dialog */}
      {pendingDelete !== null && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={() => setPendingDelete(null)} />
          <div className="relative bg-white rounded-lg shadow-xl border p-5 max-w-sm">
            <p className="text-sm text-gray-800 mb-4">Are you sure you want to delete this record?</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setPendingDelete(null)}
                className="px-3 py-1.5 text-xs border rounded hover:bg-gray-50">Cancel</button>
              <button onClick={() => { onDeleteItem(pendingDelete); setPendingDelete(null); }}
                className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700">Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Scrollable table area */}
      <div className="flex-1 overflow-auto min-h-0">
        {items.length === 0 ? (
          <div className="text-sm text-gray-400 italic p-4">No {entityType} data</div>
        ) : (
          <table className="text-xs" style={{ minWidth: "100%" }}>
            <thead className="sticky top-0 z-10">
              <tr className="bg-gray-50">
                <th className="px-2 py-1.5 text-left text-gray-900 font-bold w-8">#</th>
                {sortedFields.map((f) => (
                  <th key={f} className="px-2 py-1.5 text-left text-gray-900 font-bold whitespace-nowrap">
                    {f.replace(/_/g, " ")}
                  </th>
                ))}
                {onDeleteItem && <th className="px-2 py-1.5 text-gray-900 font-bold w-10"></th>}
              </tr>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-2 py-1"></th>
                {sortedFields.map((f) => {
                  const domainKey = FIELD_TO_DOMAIN[f];
                  const domainValues = domainKey ? SOURCE_DOMAIN_VALUES[domainKey] : null;
                  // For domain fields, collect unique values actually present in data for the filter
                  const presentValues = domainValues
                    ? [...new Set(items.map((it) => it[f]).filter(Boolean))].sort()
                    : null;
                  return (
                    <th key={f} className="px-1 py-1">
                      {presentValues ? (
                        <select
                          value={filters[f] || ""}
                          onChange={(e) => updateFilter(f, e.target.value)}
                          className="w-full px-1 py-0.5 text-xs font-normal border border-gray-200 rounded bg-white focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
                        >
                          <option value="">All</option>
                          {presentValues.map((v) => (
                            <option key={v} value={v}>{v}{SOURCE_DOMAIN_LABELS[v] ? ` — ${SOURCE_DOMAIN_LABELS[v]}` : ""}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          placeholder="Filter..."
                          value={filters[f] || ""}
                          onChange={(e) => updateFilter(f, e.target.value)}
                          className="w-full px-1.5 py-0.5 text-xs font-normal border border-gray-200 rounded bg-white focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
                        />
                      )}
                    </th>
                  );
                })}
                {onDeleteItem && <th className="px-2 py-1"></th>}
              </tr>
            </thead>
            <tbody>
              {pageItems.map((item, idx) => {
                const realIndex = items.indexOf(filteredItems[page * pageSize + idx]);
                return (
                  <tr key={idx} className="border-b border-gray-100 hover:bg-blue-50">
                    <td className="px-2 py-1.5 text-gray-400">{page * pageSize + idx + 1}</td>
                    {sortedFields.map((f) => {
                      const domainKey = FIELD_TO_DOMAIN[f];
                      const domainValues = domainKey ? SOURCE_DOMAIN_VALUES[domainKey] : null;
                      return (
                        <td key={f} className="px-2 py-1.5 whitespace-nowrap">
                          {domainValues ? (
                            <SearchableSelect
                              value={item[f] ?? ""}
                              options={domainValues}
                              labels={SOURCE_DOMAIN_LABELS}
                              onChange={(val) => onEditItem(realIndex, f, val)}
                            />
                          ) : (
                            <EditableCell
                              value={item[f]}
                              editable={true}
                              dataType="A"
                              onSave={(val) => onEditItem(realIndex, f, val)}
                            />
                          )}
                        </td>
                      );
                    })}
                    {onDeleteItem && (
                      <td className="px-1 py-1.5 text-center">
                        <button
                          onClick={() => setPendingDelete(realIndex)}
                          className="w-5 h-5 flex items-center justify-center rounded text-xs font-bold text-red-600 border border-red-300 hover:bg-red-600 hover:text-white transition"
                          title="Delete row"
                        >D</button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Sticky footer — always visible */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 bg-gray-100 border-t text-xs text-gray-600">
        <div className="flex items-center gap-3">
          <span>
            {hasActiveFilters
              ? `${filteredItems.length} of ${items.length} items (filtered)`
              : `${items.length} items`}
          </span>
          {hasActiveFilters && (
            <button onClick={() => setFilters({})} className="text-blue-600 hover:text-blue-800 underline">
              Clear filters
            </button>
          )}
          {onAddItem && (
            <button onClick={onAddItem}
              className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 font-medium">
              + Add row
            </button>
          )}
        </div>
        {totalPages > 1 && (
          <div className="flex gap-2 items-center">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">{"\u2190 Prev"}</button>
            <span>Page {page + 1} of {totalPages}</span>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">{"Next \u2192"}</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Source Data Modal — floating dialog overlay
// ============================================================================

function SourceDataModal({ entityType, items, fieldNames, onEditItem, onAddItem, onDeleteItem, onClose }) {
  if (!entityType) return null;

  const title = entityType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      {/* Dialog — fills most of the viewport */}
      <div className="relative bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col"
        style={{ width: "96vw", height: "92vh" }}>
        {/* Header */}
        <div className="flex-shrink-0 flex items-center justify-between px-5 py-3 border-b bg-gray-50 rounded-t-xl">
          <h2 className="text-base font-semibold text-gray-800">Source: {title}</h2>
          <button onClick={onClose}
            className="text-gray-400 hover:text-gray-700 text-lg leading-none px-1"
            title="Close">{"\u2715"}</button>
        </div>
        {/* Body — SourceDataEditor handles its own scrolling and sticky footer */}
        <div className="flex-1 min-h-0">
          <SourceDataEditor
            entityType={entityType}
            items={items}
            fieldNames={fieldNames}
            onEditItem={onEditItem}
            onAddItem={onAddItem}
            onDeleteItem={onDeleteItem}
          />
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Diff Panel
// ============================================================================

function DiffPanel({ diff, onClose }) {
  if (!diff) return null;
  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white shadow-xl border-l z-50 flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
        <h3 className="font-medium text-gray-800">Changes Since Upload</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">{"\u2715"}</button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {diff.entries?.length === 0 && (
          <p className="text-sm text-gray-400 italic">No changes yet</p>
        )}
        {diff.entries?.map((e) => (
          <div key={e.edit_id} className="bg-gray-50 rounded-lg p-3 text-sm">
            <div className="font-mono text-xs text-gray-500 mb-1">{e.target}</div>
            <div className="flex items-center gap-2">
              <span className="bg-red-50 text-red-700 px-1.5 py-0.5 rounded text-xs line-through">
                {JSON.stringify(e.old_value)}
              </span>
              <span className="text-gray-400">{"\u2192"}</span>
              <span className="bg-green-50 text-green-700 px-1.5 py-0.5 rounded text-xs">
                {JSON.stringify(e.new_value)}
              </span>
            </div>
            {e.cascaded_fields?.length > 0 && (
              <div className="text-xs text-gray-400 mt-1">
                Cascaded to {e.cascaded_fields.length} fields
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="px-4 py-3 border-t bg-gray-50 text-xs text-gray-500">
        {diff.total_direct_edits || 0} direct edits, {diff.total_cascaded || 0} cascaded
      </div>
    </div>
  );
}

// ============================================================================
// Upload Tab
// ============================================================================

function UploadTab({ onUploadSuccess }) {
  const [status, setStatus] = useState("idle");
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const STATUS_COLORS = {
    idle: "border-gray-300 bg-gray-50",
    dragging: "border-blue-500 bg-blue-50",
    uploading: "border-yellow-500 bg-yellow-50",
    success: "border-green-500 bg-green-50",
    error: "border-red-500 bg-red-50",
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setStatus("idle");
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith(".xlsx") || f.name.endsWith(".xls"))) {
      setFile(f); setResult(null); setError(null);
    } else {
      setError("Only .xlsx and .xls files are supported");
    }
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setStatus("uploading"); setError(null); setResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: formData });
      const data = await res.json();
      if (data.status === "success") {
        setStatus("success"); setResult(data);
        onUploadSuccess(data.session_id);
      } else {
        setStatus("error"); setError(data.error || "Unknown error"); setResult(data);
      }
    } catch (err) {
      setStatus("error"); setError(`Connection failed: ${err.message}. Is the API running on port 8000?`);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${STATUS_COLORS[status]}`}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setStatus("dragging"); }}
        onDragLeave={() => setStatus("idle")}
        onClick={() => document.getElementById("fileInput").click()}
      >
        <input id="fileInput" type="file" accept=".xlsx,.xls" className="hidden"
          onChange={(e) => { if (e.target.files[0]) { setFile(e.target.files[0]); setResult(null); setError(null); } }} />
        {status === "uploading" ? (
          <div>
            <div className="animate-spin w-8 h-8 border-4 border-yellow-500 border-t-transparent rounded-full mx-auto mb-3" />
            <p className="text-yellow-700 font-medium">Processing template...</p>
          </div>
        ) : file ? (
          <div>
            <p className="text-lg font-medium text-gray-700">{file.name}</p>
            <p className="text-sm text-gray-500 mt-1">{(file.size / 1024).toFixed(0)} KB {"\u2014"} Click or drop to replace</p>
          </div>
        ) : (
          <div>
            <p className="text-lg text-gray-500">Drop your Excel template here</p>
            <p className="text-sm text-gray-400 mt-1">or click to browse</p>
          </div>
        )}
      </div>

      {file && status !== "uploading" && (
        <button onClick={handleUpload} className="mt-4 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition">
          Upload & Parse Template
        </button>
      )}

      {error && (
        <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="font-medium text-red-800">Error</h3>
          <p className="text-red-700 text-sm mt-1">{error}</p>
        </div>
      )}

      {result?.status === "success" && (
        <div className="mt-6 space-y-4">
          <div className="bg-gray-50 rounded-lg p-4">
            <h3 className="font-medium text-gray-800 mb-2">Template Info</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="text-gray-500">AIFM:</span><span className="font-medium">{result.adapter.aifm_name}</span>
              <span className="text-gray-500">Filing type:</span><span className="font-medium">{result.adapter.filing_type}</span>
              <span className="text-gray-500">NCA:</span><span className="font-medium">{result.adapter.reporting_member_state}</span>
              <span className="text-gray-500">AIFs:</span><span className="font-medium">{result.adapter.num_aifs}</span>
            </div>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
            <p className="text-green-800 font-medium">Template parsed successfully! Switch to the report tabs to view and edit.</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Report Viewer — (4) passes report_type + fund_index to edit endpoint,
//                  (10) improved drill-down mapping
// ============================================================================

function ReportViewer({ sessionId, reportType, fundIndex, onEdit, onDrillDown, nca }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(true); // Default: show all fields
  const [cascadedFields, setCascadedFields] = useState([]);

  const loadReport = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const ncaParam = nca ? `&nca=${encodeURIComponent(nca)}` : "";
      const path = reportType === "AIFM"
        ? `/session/${sessionId}/report/manager?show_all=${showAll}${ncaParam}`
        : `/session/${sessionId}/report/fund/${fundIndex}?show_all=${showAll}${ncaParam}`;
      const data = await api(path);
      setReport(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, reportType, fundIndex, showAll, nca]);

  useEffect(() => { loadReport(); }, [loadReport]);

  // Clear cascade highlights after animation
  useEffect(() => {
    if (cascadedFields.length > 0) {
      const t = setTimeout(() => setCascadedFields([]), 2500);
      return () => clearTimeout(t);
    }
  }, [cascadedFields]);

  // (4) Send report_type and fund_index so the backend edits the correct report
  const handleEdit = async (fieldId, newValue) => {
    try {
      const data = await api(`/session/${sessionId}/field`, {
        method: "PUT",
        body: JSON.stringify({
          field_id: fieldId,
          value: newValue,
          report_type: reportType,
          fund_index: fundIndex,
        }),
      });
      setCascadedFields(data.updated_fields || []);
      await loadReport(); // Reload to get updated data + re-validated state
      if (onEdit) onEdit(data);
    } catch (e) {
      alert(`Edit failed: ${e.message}`);
    }
  };

  const handleGroupEdit = async (groupName, rowIndex, columnId, newValue) => {
    try {
      await api(`/session/${sessionId}/group`, {
        method: "PUT",
        body: JSON.stringify({
          group_name: groupName,
          row_index: rowIndex,
          column_id: columnId,
          value: newValue,
          report_type: reportType,
          fund_index: fundIndex,
        }),
      });
      await loadReport(); // Reload to reflect the change
    } catch (e) {
      alert(`Group edit failed: ${e.message}`);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" /></div>;
  if (error) return <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">{error}</div>;
  if (!report) return <div className="text-gray-400 text-center py-12">No report data available</div>;

  const sections = report.sections || {};
  // Sort sections by the minimum question number in each section
  const sectionNames = Object.keys(sections).sort((a, b) => {
    const minA = Math.min(...(sections[a] || []).map((f) => parseInt(f.field_id, 10) || 9999));
    const minB = Math.min(...(sections[b] || []).map((f) => parseInt(f.field_id, 10) || 9999));
    return minA - minB;
  });
  const groups = report.groups || {};
  const groupColumns = report.group_columns || {};
  const groupObligations = report.group_obligations || {};
  const groupNames = Object.keys(groups).filter((g) => groups[g]?.length > 0);

  // Derive reporting obligation from content type (field 5)
  const allFields = Object.values(sections).flat();
  const getFieldValue = (fid) => allFields.find((f) => f.field_id === fid)?.value;
  const CT_LABELS_AIF = {
    "1": "Art 24(1)",
    "2": "Art 24(1)(2)",
    "3": "Art 3(3)(d)",
    "4": "Art 24(1)(2)(4)",
    "5": "Art 24(1)(4)",
  };
  const CT_LABELS_AIFM = {
    "1": "24(1) Authorised AIFM",
    "2": "3(3)(d) Registered AIFM",
    "3": "24(1) NPPR AIFM",
  };
  const CT_LABELS = reportType === "AIFM" ? CT_LABELS_AIFM : CT_LABELS_AIF;
  const FREQ_LABELS = {
    Q1: "Quarterly", Q2: "Quarterly", Q3: "Quarterly", Q4: "Quarterly",
    H1: "Half-yearly", H2: "Half-yearly",
    Y1: "Annual", X1: "Transitional", X2: "Transitional",
  };
  const contentType = String(getFieldValue("5") ?? "");
  const periodType = String(getFieldValue("8") ?? "");
  const obligation = CT_LABELS[contentType] || contentType;
  const frequency = FREQ_LABELS[periodType] || periodType;

  const displayName = (reportType === "AIF" ? getFieldValue("18") : null)
    || report.entity_name
    || (reportType === "AIFM" ? "Manager Report" : "Fund Report");

  return (
    <div>
      {/* Report header */}
      <div className="bg-white rounded-lg border p-4 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">{displayName}</h2>
            <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
              <span>Type: {report.report_type}</span>
              {obligation && <span>Obligation: {obligation}</span>}
              {frequency && <span>Frequency: {frequency}</span>}
              {nca && <span className="text-blue-600 font-medium cursor-help" title="NCA view: same data, NCA-specific validation rules and guidance applied">NCA: {nca}{report.nca_national_codes?.[nca] ? ` (${report.nca_national_codes[nca]})` : ""} (filtered)</span>}
              {!nca && report.nca_codes?.length > 0 && <span>NCA: {report.nca_codes.map((c) => report.nca_national_codes?.[c] ? `${c} (${report.nca_national_codes[c]})` : c).join(", ")}</span>}
            </div>
          </div>
          <CompletionBar pct={report.completeness} filled={report.filled_count} total={report.field_count} />
        </div>
      </div>

      {/* No-reporting banner */}
      {report.no_reporting && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 mb-4 text-sm text-amber-800">
          <span className="font-medium">No-reporting filing</span> {"\u2014"} only header fields (1{"\u2013"}{report.report_type === "AIFM" ? "21" : "23"}) are applicable per ESMA rules.
        </div>
      )}

      {/* Toggle */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => setShowAll(false)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${!showAll ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
        >
          Filled + Required
        </button>
        <button
          onClick={() => setShowAll(true)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${showAll ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
        >
          All Fields
        </button>
      </div>

      {/* Sections and tables interleaved by question number order */}
      {(() => {
        // Build a unified list of sections and groups, sorted by min Q number
        const items = [];
        sectionNames.forEach((name) => {
          const minQ = Math.min(...(sections[name] || []).map((f) => parseInt(f.field_id, 10) || 9999));
          items.push({ type: "section", key: name, sortKey: minQ });
        });
        // Map group names to their question range start
        const GROUP_SORT_KEYS = {
          aifm_principal_markets: 26, aifm_principal_instruments: 30,
          share_classes: 34, strategies: 58,
          main_instruments: 64, nav_geographical_focus: 78,
          aum_geographical_focus: 86, principal_exposures: 94,
          portfolio_concentrations: 103, aif_principal_markets: 114,
          asset_type_exposures: 121, asset_type_turnovers: 125,
          currency_exposures: 128, dominant_influence: 131,
          market_risk_measures: 138, fund_to_counterparty: 160,
          counterparty_to_fund: 166, ccp_exposures: 173,
          investor_groups: 208, monthly_data: 219,
          controlled_structures: 290, borrowing_sources: 296,
          funding_jurisdictions: 54,
        };
        groupNames.forEach((gName) => {
          // Try to extract sort key from first row's field_id, or use known mapping
          let sortKey = GROUP_SORT_KEYS[gName] || 9000;
          const rows = groups[gName];
          if (rows && rows[0]) {
            const firstNumKey = Object.keys(rows[0]).find((k) => /^\d+$/.test(k));
            if (firstNumKey) sortKey = parseInt(firstNumKey, 10);
          }
          items.push({ type: "group", key: gName, sortKey });
        });
        items.sort((a, b) => a.sortKey - b.sortKey);
        return items.map((item) =>
          item.type === "section" ? (
            <SectionAccordion
              key={item.key}
              name={item.key}
              fields={sections[item.key]}
              onEdit={handleEdit}
              cascadedFields={cascadedFields}
              onDrillDown={onDrillDown}
              reportType={report.report_type}
            />
          ) : (
            <GroupTable key={item.key} groupName={item.key} rows={groups[item.key]} columnNames={groupColumns[item.key]} obligations={groupObligations[item.key]} onEditGroup={handleGroupEdit} onDrillDown={onDrillDown} reportType={report.report_type} />
          )
        );
      })()}

      {/* (6) Show count of hidden sections when not showing all */}
      {report.empty_section_count > 0 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="w-full text-center py-2 text-xs text-gray-400 hover:text-gray-600 transition"
        >
          {report.empty_section_count} empty/optional sections hidden {"\u2014"} click "All Fields" to show all
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Entity Sidebar — (2) NCA click filters report, (8) shared for AIFM + AIF
// ============================================================================

function EntitySidebar({ reports, selectedIndex, onSelect, sourceEntities, onSelectSource, reportType, selectedNca, onSelectNca }) {
  const [expandedEntity, setExpandedEntity] = useState(null);
  const [selectedSource, setSelectedSource] = useState(null);
  const [fundFilter, setFundFilter] = useState("");
  const [ncaCompleteness, setNcaCompleteness] = useState({}); // { "reportId": { "NL": {pct, filled, total}, "GB": ... } }

  // Fetch per-NCA completeness when entity is expanded
  useEffect(() => {
    if (expandedEntity === null) return;
    const entity = (reportType === "AIFM"
      ? reports.filter((r) => r.report_type === "AIFM")
      : reports.filter((r) => r.report_type === "AIF")
    )[expandedEntity];
    if (!entity || !entity.nca_codes?.length) return;
    const rid = entity.report_id;
    if (ncaCompleteness[rid]) return; // already fetched
    const isAifm = reportType === "AIFM";
    const endpoint = isAifm
      ? `/session/${entity.report_id?.split?.("_")?.[0] || ""}/report/manager`
      : `/session/${entity.report_id?.split?.("_")?.[0] || ""}/report/fund/${entity.entity_index}`;
    // Fetch consolidated + each NCA
    (async () => {
      try {
        // Get session_id from report_id context — we'll use the parent session
        // Actually, we need the sessionId from props. Let's fetch from the active session.
        const sessRes = await api("/session/active/current");
        const sid = sessRes.session_id;
        if (!sid) return;
        const results = {};
        // Consolidated
        const consRes = await api(`/session/${sid}/report/${isAifm ? "manager" : `fund/${entity.entity_index}`}?show_all=true`);
        results["_consolidated"] = { pct: consRes.completeness, filled: consRes.filled_count, total: consRes.field_count };
        // Per NCA
        for (const nca of entity.nca_codes) {
          const ncaRes = await api(`/session/${sid}/report/${isAifm ? "manager" : `fund/${entity.entity_index}`}?show_all=true&nca=${nca}`);
          results[nca] = { pct: ncaRes.completeness, filled: ncaRes.filled_count, total: ncaRes.field_count };
        }
        setNcaCompleteness((prev) => ({ ...prev, [rid]: results }));
      } catch (e) {
        // Silently ignore — sidebar completeness is a nice-to-have
      }
    })();
  }, [expandedEntity, reports, reportType, ncaCompleteness]);

  const allEntities = reportType === "AIFM"
    ? reports.filter((r) => r.report_type === "AIFM")
    : reports.filter((r) => r.report_type === "AIF");

  // Apply fund filter (search by name or index)
  const entities = fundFilter
    ? allEntities.filter((e) => {
        const name = (e.entity_name || "").toLowerCase();
        const q = fundFilter.toLowerCase();
        return name.includes(q) || String(e.entity_index).includes(q);
      })
    : allEntities;

  // Filter source entity types based on report type
  // AIFM reports only use positions, transactions, counterparties (aggregated across all funds)
  // AIF reports use all entity types
  const allEntityTypes = [
    { key: "positions", label: "Positions", aifm: true, aif: true },
    { key: "transactions", label: "Transactions", aifm: true, aif: true },
    { key: "share_classes", label: "Share Classes", aifm: false, aif: true },
    { key: "counterparties", label: "Counterparties", aifm: true, aif: true },
    { key: "strategies", label: "Strategies", aifm: false, aif: true },
    { key: "investors", label: "Investors", aifm: false, aif: true },
    { key: "risk_measures", label: "Risk Measures", aifm: true, aif: true },
    { key: "borrowing_sources", label: "Borrowing Sources", aifm: false, aif: true },
  ];
  const entityTypes = allEntityTypes.filter((et) =>
    reportType === "AIFM" ? et.aifm : et.aif
  );

  const heading = reportType === "AIFM" ? "Manager" : "Funds";

  return (
    <div className="w-72 flex-shrink-0 border-r bg-white overflow-y-auto">
      <div className="p-3">
        {/* SOURCE DATA — shown first, above entity list */}
        {sourceEntities && (
          <>
            <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Source Data</h3>
            {entityTypes.map((et) => {
              const count = sourceEntities?.entities?.[et.key]?.items?.length || 0;
              if (count === 0) return null;
              return (
                <button key={et.key}
                  onClick={() => { setSelectedSource(et.key); onSelectSource(et.key); }}
                  className={`w-full text-left px-3 py-1.5 rounded text-xs transition mb-0.5 ${
                    selectedSource === et.key ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  {et.label} <span className="text-gray-400">({count})</span>
                </button>
              );
            })}
            <hr className="my-3" />
          </>
        )}

        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">{heading}</h3>

        {/* Fund filter — only for AIF with multiple entities */}
        {reportType === "AIF" && allEntities.length > 5 && (
          <input
            type="text"
            placeholder="Search funds..."
            value={fundFilter}
            onChange={(e) => setFundFilter(e.target.value)}
            className="w-full px-2 py-1.5 mb-2 text-xs border rounded focus:ring-1 focus:ring-blue-300 focus:border-blue-400"
          />
        )}

        {entities.map((entity, idx) => {
          // (5) Single-NCA entities collapse the sidebar view: no accordion,
          // no "Consolidated (all NCAs)" row, NCA code shown under the name.
          const isSingleNca = (entity.nca_codes?.length ?? 0) === 1;
          const singleNca = isSingleNca ? entity.nca_codes[0] : null;
          const singleNatCode = isSingleNca ? (entity.nca_national_codes?.[singleNca] || "") : "";
          return (
          <div key={entity.report_id || idx} className="mb-1">
            <button
              onClick={() => {
                onSelect(entity.entity_index);
                if (isSingleNca) {
                  // For single-NCA entities there is no "consolidated" view;
                  // selecting the header goes straight to the single NCA.
                  if (onSelectNca) onSelectNca(singleNca);
                } else {
                  setExpandedEntity(expandedEntity === idx ? null : idx);
                  if (onSelectNca) onSelectNca(null); // Reset NCA filter
                }
                setSelectedSource(null);
                onSelectSource(null);
              }}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                selectedSource === null && selectedIndex === entity.entity_index && (
                  isSingleNca ? selectedNca === singleNca : !selectedNca
                )
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate text-xs">{entity.entity_name || (reportType === "AIFM" ? "Manager" : `Fund ${idx + 1}`)}</span>
                {!isSingleNca && (
                  <span className="text-xs text-gray-400">{expandedEntity === idx ? "\u25BC" : "\u25B6"}</span>
                )}
              </div>
              {isSingleNca && (
                <div className="text-[11px] text-gray-500 font-mono truncate mt-0.5">
                  NCA: {singleNca}{singleNatCode ? ` (${singleNatCode})` : ""}
                </div>
              )}
              <div className="flex items-center gap-2 mt-0.5">
                {(() => {
                  const nc = ncaCompleteness[entity.report_id];
                  const pct = isSingleNca
                    ? (nc?.[singleNca]?.pct ?? entity.completeness)
                    : (nc?._consolidated?.pct ?? entity.completeness);
                  return (
                    <>
                      <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
                        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs text-gray-400">{Math.round(pct)}%</span>
                    </>
                  );
                })()}
              </div>
            </button>
            {!isSingleNca && expandedEntity === idx && (
              <div className="ml-4 mt-1 space-y-0.5">
                {/* "Consolidated" view — only shown when there are 2+ NCAs */}
                <button
                  onClick={() => {
                    onSelect(entity.entity_index);
                    setSelectedSource(null);
                    onSelectSource(null);
                    if (onSelectNca) onSelectNca(null);
                  }}
                  className={`w-full text-left px-2 py-1 rounded text-xs flex items-center justify-between ${
                    selectedSource === null && selectedIndex === entity.entity_index && !selectedNca
                      ? "bg-blue-100 text-blue-700 font-medium"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  <span>Consolidated (all NCAs)</span>
                  {(() => {
                    const nc = ncaCompleteness[entity.report_id];
                    return nc?._consolidated?.pct != null
                      ? <span className="text-gray-400">{Math.round(nc._consolidated.pct)}%</span>
                      : null;
                  })()}
                </button>
                {/* Per-NCA view */}
                {entity.nca_codes?.map((nca) => {
                  const nc = ncaCompleteness[entity.report_id];
                  const ncaPct = nc?.[nca]?.pct;
                  const natCode = entity.nca_national_codes?.[nca];
                  return (
                    <button key={nca}
                      onClick={() => {
                        onSelect(entity.entity_index);
                        setSelectedSource(null);
                        onSelectSource(null);
                        if (onSelectNca) onSelectNca(nca);
                      }}
                      className={`w-full text-left px-2 py-1 rounded text-xs flex items-center justify-between ${
                        selectedNca === nca && selectedIndex === entity.entity_index
                          ? "bg-blue-100 text-blue-700 font-medium"
                          : "text-gray-500 hover:bg-gray-50"
                      }`}
                    >
                      <span className="truncate">NCA: {nca}{natCode ? ` (${natCode})` : ""}</span>
                      {ncaPct != null && <span className="text-gray-400 flex-shrink-0 ml-1">{Math.round(ncaPct)}%</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          );
        })}

        {/* Source Data section moved to top of sidebar */}
      </div>
    </div>
  );
}

// ============================================================================
// Toast Notification
// ============================================================================

function Toast({ message, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t); }, [onClose]);
  return (
    <div className="fixed bottom-4 right-4 bg-gray-800 text-white px-4 py-3 rounded-lg shadow-lg text-sm flex items-center gap-3 z-50">
      <span>{message}</span>
      <button onClick={onClose} className="text-gray-400 hover:text-white">{"\u2715"}</button>
    </div>
  );
}

// ============================================================================
// Main App — (7) NCA display, (8) AIFM sidebar, (10) improved drill-down
// ============================================================================

export default function EagleApp() {
  const [tab, setTab] = useState("upload");
  const [sessionId, setSessionId] = useState(null);
  const [sessionData, setSessionData] = useState(null);
  const [selectedFund, setSelectedFund] = useState(0);
  const [selectedSource, setSelectedSource] = useState(null);
  const [selectedNca, setSelectedNca] = useState(null);
  const [sourceData, setSourceData] = useState(null);
  const [aifmSourceData, setAifmSourceData] = useState(null);
  const [showDiff, setShowDiff] = useState(false);
  const [diff, setDiff] = useState(null);
  const [toast, setToast] = useState(null);

  // Load active session on mount
  useEffect(() => {
    api("/session/active/current").then((data) => {
      if (data.session_id) {
        setSessionId(data.session_id);
        setSessionData(data);
      }
    }).catch(() => {});
  }, []);

  // Load source data when session/fund changes
  useEffect(() => {
    if (!sessionId) return;
    api(`/session/${sessionId}/source?fund_index=${selectedFund}`).then(setSourceData).catch(() => {});
  }, [sessionId, selectedFund]);

  // Load AIFM source data (for manager sidebar) — aggregate=true to collect all funds
  useEffect(() => {
    if (!sessionId) return;
    api(`/session/${sessionId}/source?fund_index=0&aggregate=true`).then(setAifmSourceData).catch(() => {});
  }, [sessionId]);

  const handleUploadSuccess = async (newSessionId) => {
    setSessionId(newSessionId);
    try {
      const data = await api(`/session/${newSessionId}`);
      setSessionData(data);
      setTab("manager");
    } catch (e) {
      console.error(e);
    }
  };

  const handleEdit = (result) => {
    if (result.updated_fields?.length > 0) {
      setToast(`${result.updated_fields.length} field(s) updated`);
    }
  };

  // Reload source data for both fund-level and AIFM-level
  const reloadSourceData = async () => {
    try {
      const [fundData, mgrData] = await Promise.all([
        api(`/session/${sessionId}/source?fund_index=${selectedFund}`),
        api(`/session/${sessionId}/source?fund_index=0&aggregate=true`),
      ]);
      setSourceData(fundData);
      setAifmSourceData(mgrData);
    } catch (e) {
      console.error("Failed to reload source data", e);
    }
  };

  const handleSourceEdit = async (index, field, value) => {
    if (!sessionId || !selectedSource) return;
    try {
      await api(`/session/${sessionId}/source/${selectedSource}/${index}`, {
        method: "PUT",
        body: JSON.stringify({ field, value }),
      });
      await reloadSourceData();
      setToast("Source data updated — derived fields will be recalculated");
    } catch (e) {
      alert(`Edit failed: ${e.message}`);
    }
  };

  const handleSourceAdd = async () => {
    if (!sessionId || !selectedSource) return;
    try {
      await api(`/session/${sessionId}/source/${selectedSource}`, {
        method: "POST",
        body: JSON.stringify({ values: {}, fund_index: tab === "manager" ? 0 : selectedFund }),
      });
      await reloadSourceData();
      setToast("New row added");
    } catch (e) {
      alert(`Add failed: ${e.message}`);
    }
  };

  const handleSourceDelete = async (index) => {
    if (!sessionId || !selectedSource) return;
    const fi = tab === "manager" ? 0 : selectedFund;
    try {
      await api(`/session/${sessionId}/source/${selectedSource}/${index}?fund_index=${fi}`, {
        method: "DELETE",
      });
      await reloadSourceData();
      setToast("Row deleted");
    } catch (e) {
      alert(`Delete failed: ${e.message}`);
    }
  };

  // (10) Handle drill-down from composite field to source data
  // Maps field ranges to the most likely source entity type.
  // IMPORTANT: AIF and AIFM have independent field numbering.
  // The same field_id means different things in each report type.
  const AIF_FIELD_TO_SOURCE = {
    // Main instruments (Q64-Q77) → positions
    ...Object.fromEntries(Array.from({ length: 14 }, (_, i) => [String(64 + i), "positions"])),
    // Geographical focus (Q78-Q93) → positions
    ...Object.fromEntries(Array.from({ length: 16 }, (_, i) => [String(78 + i), "positions"])),
    // Principal exposures (Q94-Q102) → positions
    ...Object.fromEntries(Array.from({ length: 9 }, (_, i) => [String(94 + i), "positions"])),
    // Counterparty (Q113-Q122) → counterparties
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(113 + i), "counterparties"])),
    // Asset type exposures (Q128-Q137) → positions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(128 + i), "positions"])),
    // Turnovers (Q138-Q147) → transactions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(138 + i), "transactions"])),
    // Currency (Q148-Q157) → positions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(148 + i), "positions"])),
    // Borrowing sources (Q158-Q167) → borrowing_sources
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(158 + i), "borrowing_sources"])),
    // Strategies (Q168-Q177) → strategies
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(168 + i), "strategies"])),
    // Investor groups (Q178-Q187) → investors
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(178 + i), "investors"])),
    // Q47-Q49 (NAV, equity delta) → positions
    "47": "positions", "48": "positions", "49": "positions",
    // Investor concentration (Q118-Q120) → investors
    "118": "investors", "119": "investors", "120": "investors",
  };

  const AIFM_FIELD_TO_SOURCE = {
    // AIFM principal markets (Q26-Q29) → positions
    ...Object.fromEntries(Array.from({ length: 4 }, (_, i) => [String(26 + i), "positions"])),
    // AIFM principal instruments (Q30-Q32) → positions
    ...Object.fromEntries(Array.from({ length: 3 }, (_, i) => [String(30 + i), "positions"])),
    // AIFM AuM (Q33-Q34) → positions (aggregated across all AIFs)
    "33": "positions", "34": "positions",
  };

  const handleDrillDown = (field) => {
    // Use explicit source entity from derived group, or look up by field_id
    // scoped to the current report type (AIF/AIFM have independent field IDs)
    const fieldMap = tab === "manager" ? AIFM_FIELD_TO_SOURCE : AIF_FIELD_TO_SOURCE;
    const source = field._sourceEntity || fieldMap[field.field_id] || "positions";
    setSelectedSource(source);
    const _prefix = tab === "manager" ? "AFM" : "Q";
    setToast(`Showing ${source.replace(/_/g, " ")} for derived field ${_prefix}${field.field_id}`);
  };

  const loadDiff = async () => {
    if (!sessionId) return;
    try {
      const data = await api(`/session/${sessionId}/diff`);
      setDiff(data);
      setShowDiff(true);
    } catch (e) {
      alert(e.message);
    }
  };

  const handleUndo = async () => {
    if (!sessionId) return;
    try {
      await api(`/session/${sessionId}/undo`, { method: "POST" });
      setToast("Last edit undone");
      const data = await api(`/session/${sessionId}/source?fund_index=${selectedFund}`);
      setSourceData(data);
    } catch (e) {
      alert(e.message);
    }
  };

  const handleValidate = async () => {
    if (!sessionId) return;
    try {
      const data = await api(`/session/${sessionId}/validate`, { method: "POST" });
      setToast(`Validation complete: ${data.dqf_pass} pass, ${data.dqf_fail} fail${data.has_critical ? " (CRITICAL issues found)" : ""}`);
    } catch (e) {
      alert(e.message);
    }
  };

  // (7) Collect all unique NCA codes across all reports
  const allNcaCodes = [...new Set((sessionData?.reports || []).flatMap((r) => r.nca_codes || []))].sort();

  const tabs = [
    { key: "upload", label: "Upload" },
    { key: "manager", label: "Manager Report", disabled: !sessionId },
    { key: "funds", label: "Fund Reports", disabled: !sessionId },
  ];

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-bold text-gray-800">Eagle</h1>
            <nav className="flex gap-1">
              {tabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => !t.disabled && setTab(t.key)}
                  disabled={t.disabled}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                    tab === t.key
                      ? "bg-blue-600 text-white"
                      : t.disabled
                      ? "text-gray-300 cursor-not-allowed"
                      : "text-gray-600 hover:bg-gray-100"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </nav>
          </div>
          {sessionId && (
            <div className="flex items-center gap-2">
              <Tip text="Undo the last edit">
                <button onClick={handleUndo} className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50 transition" title="Undo last edit">
                  {"\u21A9"} Undo
                </button>
              </Tip>
              <Tip text="View all changes since upload">
                <button onClick={loadDiff} className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50 transition" title="View changes">
                  View Changes
                </button>
              </Tip>
              <Tip text="Run full validation (YAML business rules) on canonical data">
                <button onClick={handleValidate} className="px-3 py-1.5 text-sm rounded-lg bg-green-600 text-white hover:bg-green-700 transition" title="Validate canonical">
                  Validate Report
                </button>
              </Tip>
            </div>
          )}
        </div>
        {/* (7) Fixed top bar — show all NCA codes with proper spacing */}
        {sessionData && sessionId && tab !== "upload" && (
          <div className="max-w-full mx-auto px-4 pb-2 text-xs text-gray-500 flex gap-6">
            <span>File: {sessionData.filename}</span>
            <span>AIFM: {sessionData.aifm_name}</span>
            <span>NCA: {allNcaCodes.length > 0 ? allNcaCodes.join(", ") : sessionData.reporting_member_state}</span>
            <span>Filing: {sessionData.filing_type}</span>
            <span>Status: {sessionData.status}</span>
          </div>
        )}
      </header>

      {/* Content */}
      <main className="max-w-full mx-auto">
        {tab === "upload" && (
          <div className="p-8">
            <UploadTab onUploadSuccess={handleUploadSuccess} />
          </div>
        )}

        {/* (8) Manager tab uses sidebar with NCA list and source data */}
        {tab === "manager" && sessionId && (
          <div className="flex h-[calc(100vh-120px)]">
            <EntitySidebar
              reports={sessionData?.reports || []}
              selectedIndex={0}
              onSelect={() => {}}
              sourceEntities={aifmSourceData}
              onSelectSource={(src) => { setSelectedSource(src); }}
              reportType="AIFM"
              selectedNca={selectedNca}
              onSelectNca={setSelectedNca}
            />
            <div className="flex-1 overflow-y-auto p-6">
              <ReportViewer
                sessionId={sessionId}
                reportType="AIFM"
                fundIndex={0}
                onEdit={handleEdit}
                onDrillDown={handleDrillDown}
                nca={selectedNca}
              />
              {/* Source data is now shown in a floating modal */}
            </div>
          </div>
        )}

        {tab === "funds" && sessionId && (
          <div className="flex h-[calc(100vh-120px)]">
            <EntitySidebar
              reports={sessionData?.reports || []}
              selectedIndex={selectedFund}
              onSelect={(idx) => { setSelectedFund(idx); setSelectedSource(null); setSelectedNca(null); }}
              sourceEntities={sourceData}
              onSelectSource={setSelectedSource}
              reportType="AIF"
              selectedNca={selectedNca}
              onSelectNca={setSelectedNca}
            />
            <div className="flex-1 overflow-y-auto p-6">
              <ReportViewer
                sessionId={sessionId}
                reportType="AIF"
                fundIndex={selectedFund}
                onEdit={handleEdit}
                onDrillDown={handleDrillDown}
                nca={selectedNca}
              />
              {/* Source data is now shown in a floating modal */}
            </div>
          </div>
        )}
      </main>

      {/* Source Data Modal */}
      {selectedSource && (
        <SourceDataModal
          entityType={selectedSource}
          items={
            (tab === "manager" ? aifmSourceData : sourceData)?.entities?.[selectedSource]?.items || []
          }
          fieldNames={
            (tab === "manager" ? aifmSourceData : sourceData)?.entities?.[selectedSource]?.field_names || []
          }
          onEditItem={handleSourceEdit}
          onAddItem={handleSourceAdd}
          onDeleteItem={handleSourceDelete}
          onClose={() => setSelectedSource(null)}
        />
      )}

      {/* Diff Panel */}
      {showDiff && <DiffPanel diff={diff} onClose={() => setShowDiff(false)} />}

      {/* Toast */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
