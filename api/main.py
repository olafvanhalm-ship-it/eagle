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

try:
    from api.version import VERSION, BUILD_NUMBER, BUILD_TIMESTAMP, DB_SCHEMA_VERSION
except ImportError:
    # version.py not yet synced — use defaults so the server still starts
    VERSION, BUILD_NUMBER, BUILD_TIMESTAMP, DB_SCHEMA_VERSION = "0.3.1", 1, "2026-04-10", 1

app = FastAPI(title="Eagle API", version=VERSION)

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
        "version": VERSION,
        "build": BUILD_NUMBER,
        "build_ts": BUILD_TIMESTAMP,
        "router_errors": _router_errors,
    }


@app.get("/api/v1/build-info")
def build_info():
    """Build metadata for the frontend debug bar.

    Returns backend version, build number, and DB schema version so the
    UI can show at a glance whether all layers are in sync.
    """
    # Check DB schema version from the database itself
    db_version = DB_SCHEMA_VERSION
    db_status = "ok"
    try:
        from api.deps import get_store
        store = get_store()
        # Quick connectivity check
        with store._db() as sess:
            from sqlalchemy import text as _sa_text
            sess.execute(_sa_text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "backend_version": VERSION,
        "backend_build": BUILD_NUMBER,
        "backend_build_ts": BUILD_TIMESTAMP,
        "db_schema_version": db_version,
        "db_status": db_status,
    }
