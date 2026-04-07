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
  if (validation.status === "PASS") return "bg-green-50";
  if (validation.status === "WARNING") return "bg-orange-50";
  if (validation.status === "FAIL") return "bg-red-50";
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

function EditableCell({ value, field, onSave, editable, dataType, format: fmt, allowedValuesRef, referenceValues, validation, nonEditableReason, onDrillDown }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [error, setError] = useState("");
  // (4) Track whether save was already triggered by Enter to prevent double-fire
  const savedRef = useRef(false);

  // Sync draft with value prop when value changes externally
  useEffect(() => { setDraft(value ?? ""); }, [value]);

  const vBg = validationBg(validation);
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

  if (!editable) {
    // (3) Show reason why field is not editable on hover
    const reasonText = nonEditableReason
      ? `${nonEditableReason}${vTitle ? "\n\n" + vTitle : ""}`
      : vTitle || "";
    // (10) If category is composite, show pointer cursor for drill-down
    const isComposite = field?.category === "composite";
    return (
      <span
        className={`text-gray-900 px-1.5 py-0.5 rounded text-sm ${vBg} ${isComposite ? "cursor-pointer underline decoration-dotted hover:bg-blue-50" : ""}`}
        title={reasonText}
        onClick={isComposite && onDrillDown ? onDrillDown : undefined}
      >
        {value ?? <span className="text-gray-300 italic">{"\u2014"}</span>}
      </span>
    );
  }

  if (editing) {
    // Dropdown for enumerated values
    if (allowedValuesRef && referenceValues && referenceValues.length > 0) {
      return (
        <select
          className="border rounded px-2 py-1 text-sm focus:ring-2 focus:ring-blue-300 focus:border-blue-500"
          value={draft}
          autoFocus
          onChange={(e) => { setDraft(e.target.value); setError(""); }}
          onBlur={() => doSave(draft)}
          onKeyDown={(e) => { if (e.key === "Escape") { savedRef.current = true; setEditing(false); setDraft(value ?? ""); } }}
        >
          <option value="">{"— Select —"}</option>
          {referenceValues.map((v) => (
            <option key={typeof v === "object" ? v.code || v.value : v} value={typeof v === "object" ? v.code || v.value : v}>
              {typeof v === "object" ? `${v.code || v.value} — ${v.description || v.label || ""}` : v}
            </option>
          ))}
        </select>
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
      {value ?? <span className="text-gray-300 italic">empty</span>}
    </span>
  );
}

// ============================================================================
// Field Row — (1) traffic light in value, no separate Validate column
// ============================================================================

function _nonEditableReason(field) {
  if (!field) return "";
  if (field.category === "composite") return "Derived field \u2014 edit the underlying source data instead. Click to view source positions.";
  if (field.category === "entity") return "";
  // System fields (auto-generated)
  const sysAifm = new Set(["1","2","3","4","5","6","7","8","9","10","11","12","13","16"]);
  const sysAif = new Set(["1","2","3","4","5","6","7","8","9","10","11","12","13","16","17"]);
  const sysSet = field.report_type === "AIFM" ? sysAifm : sysAif;
  if (sysSet.has(field.field_id)) return "System-generated field \u2014 populated automatically from template metadata";
  if (field.obligation === "O" && (field.value == null || field.value === "")) return "Empty optional field \u2014 data must come from source";
  return "";
}

function FieldRow({ field, onEdit, cascaded, onDrillDown }) {
  const handleSave = (newValue) => {
    if (newValue !== field.value) {
      onEdit(field.field_id, newValue);
    }
  };

  return (
    <tr className={`border-b border-gray-100 hover:bg-gray-50 ${cascaded ? "cascade-highlight" : ""}`}>
      <td className="px-2 py-1 text-xs font-mono text-gray-400">{field.field_id}</td>
      <td className="px-2 py-1 text-sm text-gray-700 truncate">
        <Tip text={`${field.obligation === "M" ? "Mandatory" : field.obligation === "C" ? "Conditional" : "Optional"} | ${field.xsd_element || ""}`}>
          {field.field_name}
          {field.obligation === "M" && <span className="text-red-500 ml-1">*</span>}
        </Tip>
      </td>
      <td className="px-2 py-1 overflow-hidden">
        <EditableCell
          value={field.value}
          field={field}
          onSave={handleSave}
          editable={field.editable}
          dataType={field.data_type}
          format={field.format}
          allowedValuesRef={field.allowed_values_ref}
          referenceValues={[]}
          validation={field.validation}
          nonEditableReason={_nonEditableReason(field)}
          onDrillDown={field.category === "composite" && onDrillDown ? () => onDrillDown(field) : undefined}
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

function SectionAccordion({ name, fields, onEdit, cascadedFields, onDrillDown }) {
  const [open, setOpen] = useState(true);
  const filled = fields.filter((f) => f.value != null && f.value !== "").length;
  const failed = fields.filter((f) => f.validation?.status === "FAIL").length;
  const warned = fields.filter((f) => f.validation?.status === "WARNING").length;

  return (
    <div className="border border-gray-200 rounded-lg mb-2 overflow-hidden">
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
            <col style={{ width: "36px" }} />
            <col style={{ width: "32%" }} />
            <col style={{ width: "auto" }} />
            <col style={{ width: "48px" }} />
          </colgroup>
          <thead>
            <tr className="bg-gray-50 text-xs text-gray-500 uppercase">
              <th className="px-2 py-1 text-left">#</th>
              <th className="px-2 py-1 text-left">Field</th>
              <th className="px-2 py-1 text-left">Value</th>
              <th className="px-2 py-1 text-center" title="Data source">Source</th>
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
  dominant_influence: "Dominant influence",
  controlled_structures: "Controlled structures",
  monthly_returns: "Monthly returns",
  monthly_navs: "Monthly NAVs",
};

// (5) Question number ranges for each group
const GROUP_QUESTION_RANGES = {
  main_instruments: "Q24\u2013Q35",
  nav_geographical_focus: "Q78\u2013Q85",
  aum_geographical_focus: "Q86\u2013Q93",
  principal_exposures: "Q94\u2013Q102",
  portfolio_concentrations: "Q103\u2013Q112",
  fund_to_counterparty: "Q113\u2013Q117",
  counterparty_to_fund: "Q118\u2013Q122",
  ccp_exposures: "Q123\u2013Q127",
  asset_type_exposures: "Q128\u2013Q137",
  asset_type_turnovers: "Q138\u2013Q147",
  currency_exposures: "Q148\u2013Q157",
  borrowing_sources: "Q158\u2013Q167",
  strategies: "Q168\u2013Q177",
  investor_groups: "Q178\u2013Q187",
  share_classes: "Q188\u2013Q197",
  aif_principal_markets: "Q198\u2013Q207",
  aifm_principal_markets: "Q208\u2013Q217",
  monthly_returns: "Q218\u2013Q229",
  monthly_navs: "Q230\u2013Q241",
};

function GroupTable({ groupName, rows, columnNames }) {
  const [open, setOpen] = useState(true);
  if (!rows || rows.length === 0) return null;

  const label = GROUP_LABELS[groupName] || groupName.replace(/_/g, " ");
  const qRange = GROUP_QUESTION_RANGES[groupName] || "";
  const columns = Object.keys(rows[0]).filter((k) => k !== "field_id");

  // (5) Use columnNames from backend (field_id -> human name), show Q# + name
  const colHeader = (col) => {
    const humanName = columnNames && columnNames[col] ? columnNames[col] : col.replace(/_/g, " ");
    const isNumeric = /^\d+$/.test(col);
    if (isNumeric) return `Q${col}: ${humanName}`;
    return humanName;
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
        </div>
        <span className="text-xs text-blue-500">{rows.length} row{rows.length !== 1 ? "s" : ""}</span>
      </button>
      {open && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              {/* (5) Black header text */}
              <tr className="bg-blue-50 text-xs text-gray-900">
                <th className="px-2 py-1 text-left w-8 font-semibold">#</th>
                {columns.map((col) => (
                  <th key={col} className="px-2 py-1 text-left font-semibold" title={`Field ${col}`}>
                    {colHeader(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx} className="border-b border-blue-50 hover:bg-gray-50">
                  <td className="px-2 py-1 text-gray-400">{idx + 1}</td>
                  {columns.map((col) => (
                    <td key={col} className="px-2 py-1 text-gray-900">
                      {row[col] != null && row[col] !== "" ? String(row[col]) : <span className="text-gray-300">{"\u2014"}</span>}
                    </td>
                  ))}
                </tr>
              ))}
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

function SourceDataEditor({ entityType, items, fieldNames, onEditItem }) {
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const totalPages = Math.ceil(items.length / pageSize);
  const pageItems = items.slice(page * pageSize, (page + 1) * pageSize);

  const priorityFields = ["instrument_name", "name", "isin", "sub_asset_type", "market_value",
    "notional_value", "currency", "region", "market_type", "counterparty_name"];
  const sortedFields = [
    ...priorityFields.filter((f) => fieldNames.includes(f)),
    ...fieldNames.filter((f) => !priorityFields.includes(f)),
  ];

  if (items.length === 0) {
    return <div className="text-sm text-gray-400 italic p-4">No {entityType} data</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50">
            <th className="px-2 py-1.5 text-left text-gray-500 font-medium w-8">#</th>
            {sortedFields.slice(0, 10).map((f) => (
              <th key={f} className="px-2 py-1.5 text-left text-gray-500 font-medium truncate max-w-[120px]">
                {f.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pageItems.map((item, idx) => (
            <tr key={idx} className="border-b border-gray-100 hover:bg-blue-50">
              <td className="px-2 py-1.5 text-gray-400">{page * pageSize + idx + 1}</td>
              {sortedFields.slice(0, 10).map((f) => (
                <td key={f} className="px-2 py-1.5 max-w-[120px] truncate">
                  <EditableCell
                    value={item[f]}
                    editable={true}
                    dataType="A"
                    onSave={(val) => onEditItem(page * pageSize + idx, f, val)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 bg-gray-50 text-xs text-gray-500">
          <span>{items.length} items</span>
          <div className="flex gap-2">
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">{"\u2190 Prev"}</button>
            <span>Page {page + 1} of {totalPages}</span>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">{"Next \u2192"}</button>
          </div>
        </div>
      )}
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

function ReportViewer({ sessionId, reportType, fundIndex, onEdit, onDrillDown }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [cascadedFields, setCascadedFields] = useState([]);

  const loadReport = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const path = reportType === "AIFM"
        ? `/session/${sessionId}/report/manager?show_all=${showAll}`
        : `/session/${sessionId}/report/fund/${fundIndex}?show_all=${showAll}`;
      const data = await api(path);
      setReport(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, reportType, fundIndex, showAll]);

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

  if (loading) return <div className="flex justify-center py-12"><div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" /></div>;
  if (error) return <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">{error}</div>;
  if (!report) return <div className="text-gray-400 text-center py-12">No report data available</div>;

  const sections = report.sections || {};
  const sectionNames = Object.keys(sections);
  const groups = report.groups || {};
  const groupColumns = report.group_columns || {};
  const groupNames = Object.keys(groups).filter((g) => groups[g]?.length > 0);

  // Derive reporting obligation from content type (field 5)
  const allFields = Object.values(sections).flat();
  const getFieldValue = (fid) => allFields.find((f) => f.field_id === fid)?.value;

  const CT_LABELS_AIF = {
    "1": "Header only",
    "2": "Art 24(1)(2)",
    "3": "Art 24(1)(2)",
    "4": "Art 24(1)(2)(4)",
    "5": "Art 24(1)(4)",
  };
  const CT_LABELS_AIFM = {
    "1": "Registered (Art 3(3)(d))",
    "2": "Authorised (Art 7)",
  };
  const CT_LABELS = reportType === "AIFM" ? CT_LABELS_AIFM : CT_LABELS_AIF;
  const FREQ_LABELS = {
    Q1: "Quarterly", Q2: "Quarterly", Q3: "Quarterly", Q4: "Quarterly",
    H1: "Half-yearly", H2: "Half-yearly",
    Y1: "Annual", X1: "Transitional", X2: "Transitional",
  };
  const contentType = getFieldValue("5") || "";
  const periodType = getFieldValue("8") || "";
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
              {report.nca_codes?.length > 0 && <span>NCA: {report.nca_codes.join(", ")}</span>}
              <span>Type: {report.report_type}</span>
              {obligation && <span>Obligation: {obligation}</span>}
              {frequency && <span>Frequency: {frequency}</span>}
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

      {/* Sections */}
      {sectionNames.map((name) => (
        <SectionAccordion
          key={name}
          name={name}
          fields={sections[name]}
          onEdit={handleEdit}
          cascadedFields={cascadedFields}
          onDrillDown={onDrillDown}
        />
      ))}

      {/* Repeating group tables */}
      {groupNames.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3">Repeating Groups</h3>
          {groupNames.map((gName) => (
            <GroupTable key={gName} groupName={gName} rows={groups[gName]} columnNames={groupColumns[gName]} />
          ))}
        </div>
      )}

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

  const entities = reportType === "AIFM"
    ? reports.filter((r) => r.report_type === "AIFM")
    : reports.filter((r) => r.report_type === "AIF");

  const entityTypes = [
    { key: "positions", label: "Positions" },
    { key: "transactions", label: "Transactions" },
    { key: "share_classes", label: "Share Classes" },
    { key: "counterparties", label: "Counterparties" },
    { key: "strategies", label: "Strategies" },
    { key: "investors", label: "Investors" },
    { key: "risk_measures", label: "Risk Measures" },
    { key: "borrowing_sources", label: "Borrowing Sources" },
  ];

  const heading = reportType === "AIFM" ? "Manager" : "Funds";

  return (
    <div className="w-56 flex-shrink-0 border-r bg-white overflow-y-auto">
      <div className="p-3">
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">{heading}</h3>
        {entities.map((entity, idx) => (
          <div key={entity.report_id || idx} className="mb-1">
            <button
              onClick={() => {
                onSelect(entity.entity_index);
                setExpandedEntity(expandedEntity === idx ? null : idx);
                setSelectedSource(null);
                onSelectSource(null);
                if (onSelectNca) onSelectNca(null); // Reset NCA filter
              }}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                selectedSource === null && selectedIndex === entity.entity_index && !selectedNca
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate text-xs">{entity.entity_name || (reportType === "AIFM" ? "Manager" : `Fund ${idx + 1}`)}</span>
                <span className="text-xs text-gray-400">{expandedEntity === idx ? "\u25BC" : "\u25B6"}</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{ width: `${entity.completeness}%` }} />
                </div>
                <span className="text-xs text-gray-400">{Math.round(entity.completeness)}%</span>
              </div>
            </button>
            {expandedEntity === idx && (
              <div className="ml-4 mt-1 space-y-0.5">
                {/* (2) "Consolidated" shows all NCAs */}
                <button
                  onClick={() => {
                    onSelect(entity.entity_index);
                    setSelectedSource(null);
                    onSelectSource(null);
                    if (onSelectNca) onSelectNca(null);
                  }}
                  className={`w-full text-left px-2 py-1 rounded text-xs ${
                    selectedSource === null && selectedIndex === entity.entity_index && !selectedNca
                      ? "bg-blue-100 text-blue-700 font-medium"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  Consolidated (all NCAs)
                </button>
                {/* (2) Per-NCA view */}
                {entity.nca_codes?.map((nca) => (
                  <button key={nca}
                    onClick={() => {
                      onSelect(entity.entity_index);
                      setSelectedSource(null);
                      onSelectSource(null);
                      if (onSelectNca) onSelectNca(nca);
                    }}
                    className={`w-full text-left px-2 py-1 rounded text-xs ${
                      selectedNca === nca && selectedIndex === entity.entity_index
                        ? "bg-blue-100 text-blue-700 font-medium"
                        : "text-gray-500 hover:bg-gray-50"
                    }`}
                  >
                    NCA: {nca}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Source Data section — shown for both AIFM and AIF */}
        {sourceEntities && (
          <>
            <hr className="my-3" />
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
          </>
        )}
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

  // Load AIFM source data (for manager sidebar)
  useEffect(() => {
    if (!sessionId) return;
    api(`/session/${sessionId}/source?fund_index=0`).then(setAifmSourceData).catch(() => {});
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

  const handleSourceEdit = async (index, field, value) => {
    if (!sessionId || !selectedSource) return;
    try {
      await api(`/session/${sessionId}/source/${selectedSource}/${index}`, {
        method: "PUT",
        body: JSON.stringify({ field, value }),
      });
      // Reload source data
      const data = await api(`/session/${sessionId}/source?fund_index=${selectedFund}`);
      setSourceData(data);
      setToast("Source data updated — derived fields will be recalculated");
    } catch (e) {
      alert(`Edit failed: ${e.message}`);
    }
  };

  // (10) Handle drill-down from composite field to source data
  // Maps field ranges to the most likely source entity type
  const FIELD_TO_SOURCE = {
    // Main instruments → positions
    ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(24 + i), "positions"])),
    // Asset type exposures → positions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(128 + i), "positions"])),
    // Turnovers → transactions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(138 + i), "transactions"])),
    // Principal exposures → positions
    ...Object.fromEntries(Array.from({ length: 9 }, (_, i) => [String(94 + i), "positions"])),
    // Counterparty → counterparties
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(113 + i), "counterparties"])),
    // Strategies → strategies
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(168 + i), "strategies"])),
    // Investor groups → investors
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(178 + i), "investors"])),
    // Borrowing sources → borrowing_sources
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(158 + i), "borrowing_sources"])),
    // Currency → positions
    ...Object.fromEntries(Array.from({ length: 10 }, (_, i) => [String(148 + i), "positions"])),
    // Geographical focus → positions
    ...Object.fromEntries(Array.from({ length: 16 }, (_, i) => [String(78 + i), "positions"])),
    // Q48 (total AIF NAV), Q47 (net equity delta) → positions
    "47": "positions", "48": "positions", "49": "positions",
  };

  const handleDrillDown = (field) => {
    const source = FIELD_TO_SOURCE[field.field_id] || "positions";
    setTab("funds");
    setSelectedSource(source);
    setToast(`Showing ${source.replace(/_/g, " ")} for derived field Q${field.field_id}. Edit here and save to recalculate.`);
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
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
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
          <div className="max-w-7xl mx-auto px-4 pb-2 text-xs text-gray-500 flex gap-6">
            <span>File: {sessionData.filename}</span>
            <span>AIFM: {sessionData.aifm_name}</span>
            <span>NCA: {allNcaCodes.length > 0 ? allNcaCodes.join(", ") : sessionData.reporting_member_state}</span>
            <span>Filing: {sessionData.filing_type}</span>
            <span>Status: {sessionData.status}</span>
          </div>
        )}
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto">
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
              {selectedSource && aifmSourceData ? (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-800">
                      {selectedSource.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </h2>
                    <button
                      onClick={() => setSelectedSource(null)}
                      className="text-sm text-blue-600 hover:text-blue-800"
                    >
                      {"\u2190"} Back to report
                    </button>
                  </div>
                  <SourceDataEditor
                    entityType={selectedSource}
                    items={aifmSourceData.entities?.[selectedSource]?.items || []}
                    fieldNames={aifmSourceData.entities?.[selectedSource]?.field_names || []}
                    onEditItem={handleSourceEdit}
                  />
                </div>
              ) : (
                <ReportViewer
                  sessionId={sessionId}
                  reportType="AIFM"
                  fundIndex={0}
                  onEdit={handleEdit}
                  onDrillDown={handleDrillDown}
                />
              )}
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
              {selectedSource && sourceData ? (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-800">
                      {selectedSource.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                    </h2>
                    <button
                      onClick={() => setSelectedSource(null)}
                      className="text-sm text-blue-600 hover:text-blue-800"
                    >
                      {"\u2190"} Back to report
                    </button>
                  </div>
                  <SourceDataEditor
                    entityType={selectedSource}
                    items={sourceData.entities?.[selectedSource]?.items || []}
                    fieldNames={sourceData.entities?.[selectedSource]?.field_names || []}
                    onEditItem={handleSourceEdit}
                  />
                </div>
              ) : (
                <ReportViewer
                  sessionId={sessionId}
                  reportType="AIF"
                  fundIndex={selectedFund}
                  onEdit={handleEdit}
                  onDrillDown={handleDrillDown}
                />
              )}
            </div>
          </div>
        )}
      </main>

      {/* Diff Panel */}
      {showDiff && <DiffPanel diff={diff} onClose={() => setShowDiff(false)} />}

      {/* Toast */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
