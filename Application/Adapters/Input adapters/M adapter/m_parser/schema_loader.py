"""Schema loader for M adapter column definitions.

Loads the M adapter column schema YAML file, which defines canonical field
names, column indices, and AIFMD Annex IV question mappings for each record type.
"""

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


def _load_column_schema(schema_path: Path | None = None) -> dict:
    """Load the M adapter column schema YAML.

    Args:
        schema_path: Optional path to the schema file. If not provided,
                     uses the default location relative to this module.

    Returns a dict mapping record_type → list of {index, name, questions}.
    """
    if schema_path is None:
        # This module is at:
        #   .../M adapter/m_parser/schema_loader.py
        # Schema lives alongside the M adapter at:
        #   .../M adapter/m_column_schema_v1.yaml
        _adapter_dir = Path(__file__).resolve().parent.parent   # …/M adapter/
        schema_path = _adapter_dir / "m_column_schema_v1.yaml"

    if not schema_path.exists():
        log.warning("Column schema not found at %s — falling back to header-based parsing", schema_path)
        return {}
    with open(schema_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("record_types", {})


_COLUMN_SCHEMA: dict = _load_column_schema()
