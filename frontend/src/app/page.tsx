"use client";
import { useState, useCallback } from "react";

const STATUS_COLORS = {
  idle: "border-gray-300 bg-gray-50",
  dragging: "border-blue-500 bg-blue-50",
  uploading: "border-yellow-500 bg-yellow-50",
  success: "border-green-500 bg-green-50",
  error: "border-red-500 bg-red-50",
};

export default function EagleUpload() {
  const [status, setStatus] = useState("idle");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setStatus("idle");
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && (droppedFile.name.endsWith(".xlsx") || droppedFile.name.endsWith(".xls"))) {
      setFile(droppedFile);
      setResult(null);
      setError(null);
    } else {
      setError("Only .xlsx and .xls files are supported");
    }
  }, []);

  const handleFileSelect = (e) => {
    const selected = e.target.files[0];
    if (selected) {
      setFile(selected);
      setResult(null);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setStatus("uploading");
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.status === "success") {
        setStatus("success");
        setResult(data);
      } else {
        setStatus("error");
        setError(data.error || "Unknown error");
        setResult(data);
      }
    } catch (err) {
      setStatus("error");
      setError(`Connection failed: ${err.message}. Is the API running on port 8000?`);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-white rounded-lg shadow-lg p-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-800">Eagle — AIFMD Validator</h1>
          <p className="text-gray-500 mt-1">Upload an M adapter Excel template to generate and validate AIFMD Annex IV reports</p>
        </div>

        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${STATUS_COLORS[status]}`}
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setStatus("dragging"); }}
          onDragLeave={() => setStatus(file ? "idle" : "idle")}
          onClick={() => document.getElementById("fileInput").click()}
        >
          <input
            id="fileInput"
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleFileSelect}
          />
          {status === "uploading" ? (
            <div>
              <div className="animate-spin w-8 h-8 border-4 border-yellow-500 border-t-transparent rounded-full mx-auto mb-3"></div>
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

        {/* Upload button */}
        {file && status !== "uploading" && (
          <button
            onClick={handleUpload}
            className="mt-4 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            Validate Template
          </button>
        )}

        {/* Error */}
        {error && (
          <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
            <h3 className="font-medium text-red-800">Error</h3>
            <p className="text-red-700 text-sm mt-1">{error}</p>
            {result?.traceback && (
              <pre className="mt-2 text-xs text-red-600 overflow-x-auto whitespace-pre-wrap">{result.traceback}</pre>
            )}
          </div>
        )}

        {/* Results */}
        {result?.status === "success" && (
          <div className="mt-6 space-y-4">
            {/* Adapter info */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="font-medium text-gray-800 mb-2">Template Info</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-gray-500">AIFM:</span>
                <span className="font-medium">{result.adapter.aifm_name}</span>
                <span className="text-gray-500">Filing type:</span>
                <span className="font-medium">{result.adapter.filing_type}</span>
                <span className="text-gray-500">NCA:</span>
                <span className="font-medium">{result.adapter.reporting_member_state}</span>
                <span className="text-gray-500">AIFs:</span>
                <span className="font-medium">{result.adapter.num_aifs}</span>
              </div>
            </div>

            {/* Generated files */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="font-medium text-gray-800 mb-2">Generated Output</h3>
              <div className="flex gap-4 text-sm">
                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                  {result.generated.aifm_xmls} AIFM XML
                </span>
                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                  {result.generated.aif_xmls} AIF XML{result.generated.aif_xmls !== 1 ? "s" : ""}
                </span>
                {result.generated.packages > 0 && (
                  <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                    {result.generated.packages} package{result.generated.packages !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </div>

            {/* Validation results */}
            {result.validation && (
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-medium text-gray-800 mb-2">Validation Results</h3>
                <div className="flex gap-4 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-green-600 font-bold text-lg">{result.validation.xsd.valid}</span>
                    <span className="text-sm text-gray-500">XSD valid</span>
                  </div>
                  {result.validation.xsd.invalid > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-red-600 font-bold text-lg">{result.validation.xsd.invalid}</span>
                      <span className="text-sm text-gray-500">XSD invalid</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="text-green-600 font-bold text-lg">{result.validation.dqf.pass}</span>
                    <span className="text-sm text-gray-500">DQF pass</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`font-bold text-lg ${result.validation.dqf.fail > 0 ? "text-red-600" : "text-green-600"}`}>
                      {result.validation.dqf.fail}
                    </span>
                    <span className="text-sm text-gray-500">DQF fail</span>
                  </div>
                </div>

                {/* Failure details */}
                {result.validation.failures?.length > 0 && (
                  <div className="mt-3 border-t pt-3">
                    <h4 className="text-sm font-medium text-gray-600 mb-2">
                      Failed Rules ({result.validation.failures.length})
                    </h4>
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {result.validation.failures.map((f, i) => (
                        <div key={i} className="text-xs bg-white rounded p-2 flex gap-2">
                          <span className="font-mono text-red-600 whitespace-nowrap">{f.rule}</span>
                          <span className="text-gray-600 truncate">{f.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

