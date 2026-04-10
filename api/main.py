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

# Register routers — catch import errors so server still starts
_router_errors = {}

from api.routers import session, registry, validation
app.include_router(session.router)
app.include_router(registry.router)
app.include_router(validation.router)

try:
    from api.routers import report
    print(f"[Eagle] report module loaded from: {report.__file__}")
    print(f"[Eagle] report.router routes BEFORE include: {[r.path + ' [' + ','.join(r.methods) + ']' for r in report.router.routes]}")
    app.include_router(report.router)
    print("[Eagle] report router included OK")
except Exception as e:
    _router_errors["report"] = str(e)
    print(f"[Eagle] ERROR loading report router: {e}")
    import traceback
    traceback.print_exc()

# Print ALL registered routes after all routers are included
print("[Eagle] === ALL APP ROUTES ===")
for route in app.routes:
    methods = getattr(route, "methods", None)
    path = getattr(route, "path", str(route))
    if methods:
        print(f"[Eagle]   {path} [{','.join(methods)}]")
print("[Eagle] === END ROUTES ===")


# Direct app-level test endpoint (bypasses router entirely)
@app.get("/direct-test")
def direct_test():
    """If this works but /api/v1/version doesn't, the router include failed."""
    return {"direct": True, "msg": "app-level route works"}


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok" if not _router_errors else "degraded",
        "version": "0.3.0-session10b",
        "router_errors": _router_errors,
    }
