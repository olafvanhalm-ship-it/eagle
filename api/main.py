"""Eagle API — FastAPI backend for Report Viewer + Validation.

Usage (PowerShell):
    cd C:\\Dev\\eagle
    .venv\\Scripts\\Activate.ps1
    uvicorn api.main:app --reload --port 8000

Then open http://localhost:3000 (frontend) or http://localhost:8000/docs (API docs)
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add Application and M adapter to path so we can import the pipeline
_app_root = Path(__file__).resolve().parent.parent / "Application"
sys.path.insert(0, str(_app_root))
sys.path.insert(0, str(_app_root / "Adapters" / "Input adapters" / "M adapter"))

app = FastAPI(title="Eagle API", version="0.2.0")

# Allow Next.js frontend (port 3000) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from api.routers import session, report, registry, validation

app.include_router(session.router)
app.include_router(report.router)
app.include_router(registry.router)
app.include_router(validation.router)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.2.0"}
