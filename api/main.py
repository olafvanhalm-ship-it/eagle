"""Eagle API — Minimal FastAPI backend for Upload + Validate flow.

Usage (PowerShell):
    cd C:\Dev\eagle
    .venv\Scripts\Activate.ps1
    uvicorn api.main:app --reload --port 8000

Then open http://localhost:3000 (frontend) or http://localhost:8000/docs (API docs)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add Application and M adapter to path so we can import the pipeline
_app_root = Path(__file__).resolve().parent.parent / "Application"
sys.path.insert(0, str(_app_root))
sys.path.insert(0, str(_app_root / "Adapters" / "Input adapters" / "M adapter"))

app = FastAPI(title="Eagle API", version="0.1.0")

# Allow Next.js frontend (port 3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/upload")
async def upload_and_validate(file: UploadFile = File(...)):
    """Upload an Excel template, run the M adapter pipeline, return validation results.

    Flow:
        1. Save uploaded file to temp directory
        2. Parse with MAdapter
        3. Generate XMLs + validate
        4. Return structured JSON with results
        5. Clean up temp files
    """
    # Validate file type
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported")

    tmp_dir = tempfile.mkdtemp(prefix="eagle_")
    try:
        # Save uploaded file
        tmp_path = Path(tmp_dir) / file.filename
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Import pipeline (lazy to keep startup fast)
        from m_adapter import MAdapter

        # Parse template
        adapter = MAdapter(str(tmp_path))

        # Basic info from parsed adapter
        adapter_info = {
            "filename": file.filename,
            "filing_type": getattr(adapter, "filing_type", "INIT"),
            "reporting_member_state": getattr(adapter, "reporting_member_state", "unknown"),
            "aifm_name": getattr(adapter, "aifm_name", "unknown"),
            "num_aifs": len(adapter.aifs) if hasattr(adapter, "aifs") else 0,
        }

        # Generate XMLs + validate
        output_dir = str(Path(tmp_dir) / "output")
        Path(output_dir).mkdir(exist_ok=True)

        result = adapter.generate_and_validate(output_dir=output_dir)

        # Build response
        response = {
            "status": "success",
            "adapter": adapter_info,
            "generated": {
                "aifm_xmls": len(result.get("aifm_xmls", [])),
                "aif_xmls": len(result.get("aif_xmls", [])),
                "packages": len(result.get("aif_zips", []) + result.get("gz_files", [])),
            },
            "validation": _format_validation(result.get("validation")),
        }

        return JSONResponse(content=response)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _format_validation(validation) -> dict | None:
    """Format PipelineValidationResult into JSON-serializable dict.

    PipelineValidationResult is a dataclass with:
      - file_results: list[FileValidationResult]
      - xsd_valid_count, xsd_invalid_count: int properties
      - total_dqf_pass, total_dqf_fail: int properties
      - has_critical_failures: bool property
      - all_findings: list[ValidationFinding] property
    """
    if validation is None:
        return None

    try:
        # Get first 20 DQF failures for display
        failures = [
            {
                "rule": f.rule_id,
                "field": f.field_path,
                "message": f.message,
                "severity": f.severity,
            }
            for f in validation.all_findings
            if f.status == "FAIL"
        ][:20]

        return {
            "xsd": {
                "valid": validation.xsd_valid_count,
                "invalid": validation.xsd_invalid_count,
            },
            "dqf": {
                "pass": validation.total_dqf_pass,
                "fail": validation.total_dqf_fail,
            },
            "failures": failures,
            "has_critical": validation.has_critical_failures,
        }
    except Exception as e:
        return {"raw": str(validation), "error": str(e)}
