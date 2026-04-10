"""Dependency injection for Eagle API — singletons for store, registry, etc."""

from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

# Resolve paths
_API_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _API_DIR.parent
_APP_ROOT = _PROJECT_ROOT / "Application"
_ADAPTER_PATH = _APP_ROOT / "Adapters" / "Input adapters" / "M adapter"


def get_app_root() -> Path:
    return _APP_ROOT


def get_adapter_path() -> Path:
    return _ADAPTER_PATH


@lru_cache(maxsize=1)
def get_store():
    """Return the singleton ReportStore.

    Reads DATABASE_URL from environment, or builds it from EAGLE_DB_* vars
    in .env file. Falls back to SQLite if nothing is configured.
    """
    # Add Application to sys.path
    if str(_APP_ROOT) not in sys.path:
        sys.path.insert(0, str(_APP_ROOT))

    # Try loading .env file if python-dotenv is available
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            # Read .env manually if dotenv not installed
            _load_env_manual(env_file)

    from persistence.report_store import ReportStore

    # Option 1: DATABASE_URL set directly
    database_url = os.environ.get("DATABASE_URL", "").strip()

    # Option 2: Build from EAGLE_DB_* variables
    if not database_url:
        db_host = os.environ.get("EAGLE_DB_HOST", "").strip()
        db_port = os.environ.get("EAGLE_DB_PORT", "5432").strip()
        db_name = os.environ.get("EAGLE_DB_NAME", "").strip()
        db_user = os.environ.get("EAGLE_DB_USER", "").strip()
        db_pass = os.environ.get("EAGLE_DB_PASSWORD", "").strip()
        if db_host and db_name and db_user:
            database_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    return ReportStore(database_url if database_url else None)


def _load_env_manual(env_file: Path) -> None:
    """Minimal .env loader — no dependency on python-dotenv."""
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        log.warning("Could not read .env file: %s", e)


@lru_cache(maxsize=1)
def get_field_registry():
    """Return the singleton FieldRegistry (or None if not loadable)."""
    if str(_APP_ROOT) not in sys.path:
        sys.path.insert(0, str(_APP_ROOT))

    try:
        from canonical.aifmd_field_registry import get_registry
        return get_registry()
    except Exception as e:
        log.warning("Could not load field registry: %s", e)
        return None


@lru_cache(maxsize=1)
def get_field_classification() -> dict:
    """Load the field source classification YAML.

    Returns dict: "REPORT_TYPE.field_id" → {"category": ...}
    Also includes un-prefixed entries for backward compat (AIF wins on conflict).
    """
    if str(_APP_ROOT) not in sys.path:
        sys.path.insert(0, str(_APP_ROOT))

    classification_paths = [
        _APP_ROOT / "regulation" / "aifmd" / "annex_iv" / "aifmd_field_source_classification.yaml",
    ]

    for path in classification_paths:
        if path.exists():
            try:
                import yaml
                with open(path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f)

                result = {}
                _section_to_type = {"aifm_fields": "AIFM", "aif_fields": "AIF"}
                for section_key in ("aifm_fields", "aif_fields"):
                    rtype = _section_to_type[section_key]
                    for entry in raw.get(section_key, []):
                        fid = str(entry.get("field_id", ""))
                        val = {
                            "category": entry.get("category", "report"),
                            "source_entity": entry.get("source_entity"),
                            "source_field": entry.get("source_field"),
                        }
                        # Always use namespaced key: "AIFM.33" or "AIF.33"
                        # Field IDs are NOT globally unique — AIF and AIFM have
                        # independent numbering (e.g., field 33 = AuM in AIFM,
                        # share class flag in AIF).
                        result[f"{rtype}.{fid}"] = val
                log.info("Loaded field classification: %d entries from %s", len(result), path.name)
                return result
            except Exception as e:
                log.warning("Failed to load field classification from %s: %s", path, e)

    log.info("No field classification file found, using defaults")
    return {}
