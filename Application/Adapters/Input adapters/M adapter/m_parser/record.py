"""Canonical M adapter record class with AIFMD question lookup support.

MRecord is a dict subclass that supports lookup by both field name and
AIFMD Annex IV question number. It maintains both canonical and variant
field name mappings for backward compatibility with different template
providers and legacy code.
"""

from typing import Any

from shared.formatting import _str


class MRecord(dict):
    """A dict subclass that also supports lookup by AIFMD question number.

    Records are created from a fixed column schema, so field names are
    canonical regardless of how a particular template provider labels them.
    Extra columns beyond the schema are silently ignored.

    An alias layer maps common variant field names (used by different template
    providers or legacy adapter code) to the canonical schema names, so that
    existing .get("variant name") calls still work transparently.
    """

    # Maps variant field names → canonical schema field names.
    # When .get("variant") is called and the variant is not a direct key,
    # it tries the canonical name instead. Case-insensitive matching is also
    # applied as a last resort.
    _ALIASES: dict[str, str] = {
        # AIF identification
        "AIF ID": "Custom AIF Identification",
        "AIF_ID": "Custom AIF Identification",
        # AIF fields — legacy / provider variants
        "AIF No Reporting Flag": "AIF No Reporting Flag (Nothing to report)",
        "AIF reporting code": "AIF Reporting Code",
        "Domicile of the AIF": "AIF Domicile",
        "Inception Date of AIF": "AIF Inception Date",
        "AIF LEI code": "AIF LEI Code",
        "Base currency of the AIF": "AIF Base Currency",
        "AIF EEA Flag": "(Legacy) AIF EEA Flag",
        "Master feeder status": "(Legacy) Master-Feeder Status",
        "AIF National Code": "AIF National Code",
        "Last reporting flag": "Last Reporting Flag",
        "Investor Concentration percentage by retail investors":
            "Investor Concentration NAV percentage by retail investors",
        # AIFM fields
        "AIF(M) Reporting Member State": "AIFM Reporting Member State",
        "Reporting Member State": "AIFM Reporting Member State",
        "AIFM LEI code": "AIFM LEI Code",
        "AIFM no reporting flag (Nothing to report)":
            "AIFM No Reporting Flag (Nothing to report)",
        # Position fields — provider variants
        "Sub-Asset Type": "Sub-Asset Type of Position",
        "Instrument position value (as calculated under Article 3 AIFMD) in AIF Base Currency":
            "Position value (Article 2 AIFMD)",
        "Instrument position value": "Position value (Article 2 AIFMD)",
        "Position Value": "Position value (Article 2 AIFMD)",
        "Net Asset Value (NAV) at Reporting Period End Date in AIF Base Currency":
            "Net Asset Value (NAV)",
        "Instrument Currency": "Currency of the exposure",
        # Strategy
        "NAV Rate": "Share in NAV (%)",
        "Share in NAV": "Share in NAV (%)",
        # Share class
        "Share class name": "Share Class Name",
        "Share class national code": "Share Class National Code",
        # Custom FX
        "FX EUR Rate": "Currency / EUR FX rate",
        "FXEURRate": "Currency / EUR FX rate",
        # Turnover
        "Turnover Sub-Asset Type": "Sub-Asset Type of Turnover",
        "Turnover market value": "Market Value of Turnover",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._q_map: dict[str, Any] = {}   # question_number → value
        # Build a case-insensitive lookup index
        self._lower_map: dict[str, str] = {}

    def _rebuild_lower_map(self):
        """Rebuild case-insensitive key index after all keys are set."""
        self._lower_map = {k.lower(): k for k in self}

    def get(self, key, default=None):
        """Extended get with alias resolution and case-insensitive fallback."""
        # 1. Direct key match (fastest path)
        if key in self:
            return super().get(key, default)
        # 2. Try alias mapping
        canonical = self._ALIASES.get(key)
        if canonical and canonical in self:
            return super().get(canonical, default)
        # 3. Case-insensitive fallback
        if self._lower_map:
            actual_key = self._lower_map.get(key.lower())
            if actual_key:
                return super().get(actual_key, default)
        return default

    def __getitem__(self, key):
        """Extended [] access with alias resolution."""
        try:
            return super().__getitem__(key)
        except KeyError:
            canonical = self._ALIASES.get(key)
            if canonical:
                try:
                    return super().__getitem__(canonical)
                except KeyError:
                    pass
            raise KeyError(key)

    def by_q(self, question: int | str) -> Any:
        """Lookup a value by AIFMD Annex IV question number.

        Args:
            question: Question number (e.g. 23, "23", or "120, 119")

        Returns:
            The cell value, or None if not found.
        """
        return self._q_map.get(str(question))

    @classmethod
    def from_row(cls, record_type: str, row, schema_cols: list[dict] | None = None,
                 header_row=None) -> "MRecord":
        """Create a MRecord from an Excel row.

        If schema_cols is provided, uses fixed column indices for canonical
        field names. Otherwise falls back to header-based parsing.

        Args:
            record_type: e.g. "AIF", "AIFM", "POSITION"
            row:         openpyxl row (tuple of cells)
            schema_cols: list of {index, name, questions} from the schema
            header_row:  fallback header row for name-based parsing
        """
        rec = cls()

        if schema_cols:
            # Schema-driven: use column index for canonical field names
            for col_def in schema_cols:
                idx = col_def["index"] - 1  # 0-based
                if idx < len(row):
                    value = row[idx].value
                    name = col_def["name"]
                    rec[name] = value
                    # Build question number map
                    q_str = col_def.get("questions", "")
                    if q_str:
                        # Question field can contain "120, 119" or "48, 76, 86-93"
                        for part in str(q_str).split(","):
                            part = part.strip()
                            if "-" in part and part[0].isdigit():
                                # Range like "86-93" → map each number
                                try:
                                    lo, hi = part.split("-", 1)
                                    for qn in range(int(lo), int(hi) + 1):
                                        rec._q_map[str(qn)] = value
                                except ValueError:
                                    rec._q_map[part] = value
                            else:
                                rec._q_map[part] = value
        elif header_row:
            # Legacy fallback: header-based parsing
            for hcell, dcell in zip(header_row, row):
                h = hcell.value
                if h and not _str(h).startswith("#"):
                    rec[_str(h)] = dcell.value

        rec._rebuild_lower_map()
        return rec

    @classmethod
    def from_csv_row(cls, record_type: str, row_values: list[str],
                     schema_cols: list[dict] | None = None) -> "MRecord":
        """Create a MRecord from a CSV row (list of string values).

        Same logic as from_row but operates on plain string values instead
        of openpyxl Cell objects.
        """
        rec = cls()

        if schema_cols:
            for col_def in schema_cols:
                idx = col_def["index"] - 1  # 0-based
                if idx < len(row_values):
                    raw = row_values[idx].strip() if row_values[idx] else None
                    # Try numeric conversion for values that look like numbers
                    value = cls._csv_coerce(raw)
                    name = col_def["name"]
                    rec[name] = value
                    q_str = col_def.get("questions", "")
                    if q_str:
                        for part in str(q_str).split(","):
                            part = part.strip()
                            if "-" in part and part[0].isdigit():
                                try:
                                    lo, hi = part.split("-", 1)
                                    for qn in range(int(lo), int(hi) + 1):
                                        rec._q_map[str(qn)] = value
                                except ValueError:
                                    rec._q_map[part] = value
                            else:
                                rec._q_map[part] = value
        else:
            # Without schema, just store by index (no field names available)
            for i, val in enumerate(row_values):
                if i == 0:
                    continue  # skip record type column
                rec[f"col_{i}"] = cls._csv_coerce(val.strip() if val else None)

        rec._rebuild_lower_map()
        return rec

    @staticmethod
    def _csv_coerce(raw: str | None):
        """Coerce a CSV string value to int/float where appropriate."""
        if raw is None or raw == "":
            return None
        # Try int first, then float
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw
