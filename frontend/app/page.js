"use client";

import { useState, useEffect, useCallback } from "react";

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
// Provenance Icons
// ============================================================================

const PROVENANCE = {
  SMART_DEFAULT: { icon: "⚙️", label: "System default", color: "text-gray-400" },
  AI_PROPOSED: { icon: "🤖", label: "AI extracted", color: "text-purple-500" },
  DERIVED: { icon: "🧮", label: "Calculated from source data", color: "text-blue-500" },
  IMPORTED: { icon: "📥", label: "Imported from template", color: "text-green-600" },
  MANUALLY_OVERRIDDEN: { icon: "✏️", label: "Manual override", color: "text-orange-500" },
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
// Validation Badge
// ============================================================================

function ValidationBadge({ validation }) {
  if (!validation) return <span className="text-gray-300" title="Not validated yet">○</span>;
  if (validation.status === "PASS") return <span className="text-green-500" title="Validation passed">✅</span>;
  return (
    <span
      className="text-red-500 cursor-help"
      title={`${validation.rule_id}: ${validation.message}\n${validation.fix_suggestion || ""}`}
    >
      ❌ <span className="text-xs font-mono">{validation.rule_id}</span>
    </span>
  );
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
// Editable Cell
// ============================================================================

function EditableCell({ value, field, onSave, editable, dataType, format: fmt, allowedValuesRef, referenceValues }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [error, setError] = useState("");

  if (!editable) {
    return <span className="text-gray-400 bg-gray-50 px-2 py-1 rounded text-sm">{value ?? "—"}</span>;
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
          onBlur={() => { onSave(draft); setEditing(false); }}
          onKeyDown={(e) => { if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); } }}
        >
          <option value="">— Select —</option>
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
          onChange={(e) => { setDraft(e.target.value); onSave(e.target.value); setEditing(false); }}
        >
          <option value="">— Select —</option>
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
          onBlur={() => { onSave(draft); setEditing(false); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { onSave(draft); setEditing(false); }
            if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); }
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
          onBlur={() => { onSave(draft); setEditing(false); }}
          onKeyDown={(e) => {
            if (e.key === "Enter") { onSave(draft); setEditing(false); }
            if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); }
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
        onBlur={() => { onSave(draft); setEditing(false); }}
        onKeyDown={(e) => {
          if (e.key === "Enter") { onSave(draft); setEditing(false); }
          if (e.key === "Escape") { setEditing(false); setDraft(value ?? ""); }
        }}
      />
    );
  }

  // Display mode — click to edit
  return (
    <span
      className="px-2 py-1 rounded text-sm cursor-pointer hover:bg-blue-50 border border-transparent hover:border-blue-200 transition"
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      title="Click to edit"
    >
      {value ?? <span className="text-gray-300 italic">empty</span>}
    </span>
  );
}

// ============================================================================
// Field Row
// ============================================================================

function FieldRow({ field, onEdit, cascaded }) {
  const handleSave = (newValue) => {
    if (newValue !== field.value) {
      onEdit(field.field_id, newValue);
    }
  };

  return (
    <tr className={`border-b border-gray-100 hover:bg-gray-50 ${cascaded ? "cascade-highlight" : ""}`}>
      <td className="px-3 py-2 text-xs font-mono text-gray-400 w-10">{field.field_id}</td>
      <td className="px-3 py-2 text-sm text-gray-700 max-w-xs">
        <Tip text={`${field.obligation === "M" ? "Mandatory" : field.obligation === "C" ? "Conditional" : "Optional"} | ${field.xsd_element || ""}`}>
          {field.field_name}
          {field.obligation === "M" && <span className="text-red-500 ml-1">*</span>}
        </Tip>
      </td>
      <td className="px-3 py-2">
        <EditableCell
          value={field.value}
          field={field}
          onSave={handleSave}
          editable={field.editable}
          dataType={field.data_type}
          format={field.format}
          allowedValuesRef={field.allowed_values_ref}
          referenceValues={[]}
        />
      </td>
      <td className="px-2 py-2 text-center w-8">
        <ProvenanceIcon priority={field.priority} source={field.source} />
      </td>
      <td className="px-2 py-2 text-center w-8">
        <ValidationBadge validation={field.validation} />
      </td>
      <td className="px-3 py-2 text-xs text-gray-400">
        {field.nca_deviations && Object.keys(field.nca_deviations).length > 0
          ? Object.entries(field.nca_deviations).map(([cc, val]) => (
              <span key={cc} className="inline-block bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded mr-1">
                {cc}:{val}
              </span>
            ))
          : null}
      </td>
    </tr>
  );
}

// ============================================================================
// Section Accordion
// ============================================================================

function SectionAccordion({ name, fields, onEdit, cascadedFields }) {
  const [open, setOpen] = useState(true);
  const filled = fields.filter((f) => f.value != null && f.value !== "").length;
  const mandatory = fields.filter((f) => f.obligation === "M").length;
  const failed = fields.filter((f) => f.validation?.status === "FAIL").length;

  return (
    <div className="border border-gray-200 rounded-lg mb-2 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50 transition"
      >
        <div className="flex items-center gap-3">
          <span className="text-gray-400">{open ? "▼" : "▶"}</span>
          <span className="font-medium text-gray-800 text-sm">{name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {failed > 0 && (
            <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{failed} failed</span>
          )}
          <span className="text-gray-500">{filled}/{fields.length} fields</span>
        </div>
      </button>
      {open && (
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50 text-xs text-gray-500 uppercase">
              <th className="px-3 py-2 text-left w-10">#</th>
              <th className="px-3 py-2 text-left">Field</th>
              <th className="px-3 py-2 text-left">Value</th>
              <th className="px-2 py-2 text-center w-8" title="Data source">Src</th>
              <th className="px-2 py-2 text-center w-8" title="Validation status">DQF</th>
              <th className="px-3 py-2 text-left" title="NCA-specific deviations">NCA</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <FieldRow
                key={f.field_id}
                field={f}
                onEdit={onEdit}
                cascaded={cascadedFields?.includes(f.field_id)}
              />
            ))}
          </tbody>
        </table>
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

  // Show most useful columns first
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
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">← Prev</button>
            <span>Page {page + 1} of {totalPages}</span>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border disabled:opacity-30 hover:bg-white">Next →</button>
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
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">✕</button>
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
              <span className="text-gray-400">→</span>
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
            <p className="text-sm text-gray-500 mt-1">{(file.size / 1024).toFixed(0)} KB — Click or drop to replace</p>
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
// Report Viewer (shared by Manager and Fund tabs)
// ============================================================================

function ReportViewer({ sessionId, reportType, fundIndex, onEdit }) {
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

  const handleEdit = async (fieldId, newValue) => {
    try {
      const data = await api(`/session/${sessionId}/field`, {
        method: "PUT",
        body: JSON.stringify({ field_id: fieldId, value: newValue }),
      });
      setCascadedFields(data.updated_fields || []);
      loadReport(); // Reload to get updated data
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

  return (
    <div>
      {/* Report header */}
      <div className="bg-white rounded-lg border p-4 mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">{report.entity_name || (reportType === "AIFM" ? "Manager Report" : "Fund Report")}</h2>
            <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
              {report.nca_codes?.length > 0 && <span>NCA: {report.nca_codes.join(", ")}</span>}
              <span>Type: {report.report_type}</span>
            </div>
          </div>
          <CompletionBar pct={report.completeness} filled={report.filled_count} total={report.field_count} />
        </div>
      </div>

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
        />
      ))}

      {/* Empty sections badge */}
      {report.empty_section_count > 0 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="w-full text-center py-2 text-xs text-gray-400 hover:text-gray-600 transition"
        >
          {report.empty_section_count} empty sections — click "All Fields" to show
        </button>
      )}
    </div>
  );
}

// ============================================================================
// Fund Sidebar
// ============================================================================

function FundSidebar({ reports, selectedIndex, onSelect, sourceEntities, onSelectSource }) {
  const [expandedFund, setExpandedFund] = useState(null);
  const [selectedSource, setSelectedSource] = useState(null);

  const funds = reports.filter((r) => r.report_type === "AIF");

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

  return (
    <div className="w-56 flex-shrink-0 border-r bg-white overflow-y-auto">
      <div className="p-3">
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Funds</h3>
        {funds.map((fund, idx) => (
          <div key={fund.report_id} className="mb-1">
            <button
              onClick={() => { onSelect(fund.entity_index); setExpandedFund(expandedFund === idx ? null : idx); }}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                selectedIndex === fund.entity_index ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="truncate">{fund.entity_name || `Fund ${idx + 1}`}</span>
                <span className="text-xs text-gray-400">{expandedFund === idx ? "▼" : "▶"}</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <div className="w-16 h-1 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{ width: `${fund.completeness}%` }} />
                </div>
                <span className="text-xs text-gray-400">{Math.round(fund.completeness)}%</span>
              </div>
            </button>
            {expandedFund === idx && (
              <div className="ml-4 mt-1 space-y-0.5">
                <button
                  onClick={() => { onSelect(fund.entity_index); setSelectedSource(null); onSelectSource(null); }}
                  className={`w-full text-left px-2 py-1 rounded text-xs ${selectedSource === null && selectedIndex === fund.entity_index ? "bg-blue-100 text-blue-700" : "text-gray-500 hover:bg-gray-50"}`}
                >
                  Consolidated
                </button>
                {fund.nca_codes?.map((nca) => (
                  <button key={nca}
                    onClick={() => { onSelect(fund.entity_index); }}
                    className="w-full text-left px-2 py-1 rounded text-xs text-gray-500 hover:bg-gray-50"
                  >
                    {nca}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

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
      <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
    </div>
  );
}

// ============================================================================
// Main App
// ============================================================================

export default function EagleApp() {
  const [tab, setTab] = useState("upload");
  const [sessionId, setSessionId] = useState(null);
  const [sessionData, setSessionData] = useState(null);
  const [selectedFund, setSelectedFund] = useState(0);
  const [selectedSource, setSelectedSource] = useState(null);
  const [sourceData, setSourceData] = useState(null);
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

  // Load source data when session changes
  useEffect(() => {
    if (!sessionId) return;
    api(`/session/${sessionId}/source?fund_index=${selectedFund}`).then(setSourceData).catch(() => {});
  }, [sessionId, selectedFund]);

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
      setToast("Source data updated");
    } catch (e) {
      alert(`Edit failed: ${e.message}`);
    }
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
      // Reload everything
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
      setToast(`Validation complete: ${data.dqf_pass} pass, ${data.dqf_fail} fail`);
    } catch (e) {
      alert(e.message);
    }
  };

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
                  ↩ Undo
                </button>
              </Tip>
              <Tip text="View all changes since upload">
                <button onClick={loadDiff} className="px-3 py-1.5 text-sm rounded-lg border hover:bg-gray-50 transition" title="View changes">
                  View Changes
                </button>
              </Tip>
              <Tip text="Validate report and generate NCA files">
                <button onClick={handleValidate} className="px-3 py-1.5 text-sm rounded-lg bg-green-600 text-white hover:bg-green-700 transition" title="Validate report">
                  Validate Report
                </button>
              </Tip>
            </div>
          )}
        </div>
        {sessionData && (
          <div className="max-w-7xl mx-auto px-4 pb-2 text-xs text-gray-500 flex gap-4">
            <span>File: {sessionData.filename}</span>
            <span>AIFM: {sessionData.aifm_name}</span>
            <span>NCA: {sessionData.reporting_member_state}</span>
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

        {tab === "manager" && sessionId && (
          <div className="p-6">
            <ReportViewer
              sessionId={sessionId}
              reportType="AIFM"
              fundIndex={0}
              onEdit={handleEdit}
            />
          </div>
        )}

        {tab === "funds" && sessionId && (
          <div className="flex h-[calc(100vh-120px)]">
            <FundSidebar
              reports={sessionData?.reports || []}
              selectedIndex={selectedFund}
              onSelect={(idx) => { setSelectedFund(idx); setSelectedSource(null); }}
              sourceEntities={sourceData}
              onSelectSource={setSelectedSource}
            />
            <div className="flex-1 overflow-y-auto p-6">
              {selectedSource && sourceData ? (
                <div>
                  <h2 className="text-lg font-semibold text-gray-800 mb-4">
                    {selectedSource.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </h2>
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
