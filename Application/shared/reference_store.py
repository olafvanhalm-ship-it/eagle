"""Reference data store — dual-backend (SQLite for test, PostgreSQL for production).

Provides a clean interface for storing and querying public reference data:
  - ECB exchange rates (REQ-REF-001)
  - GLEIF LEI register cache (REQ-REF-002)
  - ISO 10383 MIC codes (REQ-REF-001)

Usage:
    from shared.reference_store import ReferenceStore

    # Test phase (SQLite — works anywhere)
    store = ReferenceStore.sqlite("reference_data/reference_data.db")

    # Production (PostgreSQL)
    store = ReferenceStore.postgresql(
        host="localhost", port=5432,
        dbname="Project Eagle local", user="postgres",
    )

    # Query
    rate = store.get_ecb_rate("USD", date(2025, 12, 31))
    lei_record = store.get_lei("5493001KJTIIGC8Y1R12")
    mic = store.get_mic("XAMS")

Architecture reference: eagle_software_architecture.md §6.3
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


# ── Data classes matching architecture schema ──────────────────────────

@dataclass
class ECBRate:
    rate_date: date
    base_currency: str  # always EUR
    target_currency: str
    rate: float
    source: str
    fetched_at: datetime


@dataclass
class LEIRecord:
    lei: str
    legal_name: str
    normalized_name: str
    entity_status: str  # ACTIVE, INACTIVE, etc.
    country: str  # ISO 3166-1 alpha-2 (from GLEIF legalAddress.country)
    registration_authority: Optional[str]
    last_update: Optional[date]
    fetched_at: datetime
    expires_at: datetime


@dataclass
class MICRecord:
    mic: str
    operating_mic: str
    name: str
    country: str
    status: str  # ACTIVE, EXPIRED, UPDATED
    fetched_at: datetime


# ── Schema DDL ─────────────────────────────────────────────────────────
# Follows eagle_software_architecture.md §6.3 exactly.
# SQLite-compatible (no schema prefix); PostgreSQL uses aifmd.* prefix.

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ecb_rates (
    rate_date       TEXT    NOT NULL,
    base_currency   TEXT    NOT NULL DEFAULT 'EUR',
    target_currency TEXT    NOT NULL,
    rate            REAL    NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'ECB',
    fetched_at      TEXT    NOT NULL,
    PRIMARY KEY (rate_date, target_currency)
);

CREATE TABLE IF NOT EXISTS gleif_lei_cache (
    lei                     TEXT PRIMARY KEY,
    legal_name              TEXT NOT NULL,
    normalized_name         TEXT NOT NULL DEFAULT '',
    entity_status           TEXT NOT NULL,
    country                 TEXT NOT NULL DEFAULT '',
    registration_authority  TEXT,
    last_update             TEXT,
    fetched_at              TEXT NOT NULL,
    expires_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mic_codes (
    mic             TEXT PRIMARY KEY,
    operating_mic   TEXT NOT NULL,
    name            TEXT NOT NULL,
    country         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    fetched_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ecb_rates_currency
    ON ecb_rates(target_currency, rate_date);

CREATE INDEX IF NOT EXISTS idx_gleif_legal_name
    ON gleif_lei_cache(legal_name);

CREATE INDEX IF NOT EXISTS idx_gleif_normalized_name
    ON gleif_lei_cache(normalized_name);

CREATE INDEX IF NOT EXISTS idx_mic_country
    ON mic_codes(country);
"""

_POSTGRESQL_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS aifmd;

CREATE TABLE IF NOT EXISTS aifmd.ecb_rates (
    rate_date       DATE          NOT NULL,
    base_currency   CHAR(3)       NOT NULL DEFAULT 'EUR',
    target_currency CHAR(3)       NOT NULL,
    rate            NUMERIC(18,8) NOT NULL,
    source          VARCHAR(20)   NOT NULL DEFAULT 'ECB',
    fetched_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, target_currency)
);

CREATE TABLE IF NOT EXISTS aifmd.gleif_lei_cache (
    lei                     CHAR(20) PRIMARY KEY,
    legal_name              VARCHAR(500) NOT NULL,
    normalized_name         VARCHAR(500) NOT NULL DEFAULT '',
    entity_status           VARCHAR(20)  NOT NULL,
    country                 CHAR(2)      NOT NULL DEFAULT '',
    registration_authority  VARCHAR(100),
    last_update             DATE,
    fetched_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at              TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS aifmd.mic_codes (
    mic             VARCHAR(10) PRIMARY KEY,
    operating_mic   VARCHAR(10) NOT NULL,
    name            VARCHAR(500) NOT NULL,
    country         CHAR(2)     NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ecb_rates_currency
    ON aifmd.ecb_rates(target_currency, rate_date);

CREATE INDEX IF NOT EXISTS idx_gleif_legal_name
    ON aifmd.gleif_lei_cache(legal_name);

CREATE INDEX IF NOT EXISTS idx_gleif_normalized_name
    ON aifmd.gleif_lei_cache(normalized_name);

CREATE INDEX IF NOT EXISTS idx_mic_country
    ON aifmd.mic_codes(country);
"""


# ── Store implementation ───────────────────────────────────────────────

class ReferenceStore:
    """Unified reference data store with pluggable backend."""

    def __init__(self, backend: str, connection):
        self._backend = backend  # "sqlite" or "postgresql"
        self._conn = connection
        self._table_prefix = "" if backend == "sqlite" else "aifmd."

    # ── Factory methods ────────────────────────────────────────────

    @classmethod
    def sqlite(cls, db_path: str) -> "ReferenceStore":
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        store = cls("sqlite", conn)
        store._init_schema()
        return store

    @classmethod
    def postgresql(
        cls,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "Project Eagle local",
        user: str = "postgres",
        password: str = "",
    ) -> "ReferenceStore":
        import psycopg2
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password,
        )
        conn.autocommit = True
        store = cls("postgresql", conn)
        store._init_schema()
        return store

    def _init_schema(self):
        schema = _SQLITE_SCHEMA if self._backend == "sqlite" else _POSTGRESQL_SCHEMA
        cur = self._conn.cursor()
        if self._backend == "sqlite":
            cur.executescript(schema)
            self._conn.commit()
        else:
            # Execute each statement individually so that index creation on
            # not-yet-migrated columns doesn't block table creation.
            for stmt in schema.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                try:
                    cur.execute(stmt)
                except Exception:
                    # Typically: CREATE INDEX on a column that hasn't been added
                    # yet via migration.  Safe to skip — the migration script
                    # will add the column and create the index.
                    pass
        cur.close()

    @contextmanager
    def _cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
            if self._backend == "sqlite":
                self._conn.commit()
        finally:
            cur.close()

    def _t(self, table: str) -> str:
        """Return prefixed table name."""
        return f"{self._table_prefix}{table}"

    # ── ECB Exchange Rates ─────────────────────────────────────────

    def upsert_ecb_rates(self, rates: list[dict]):
        """Bulk upsert ECB rates. Each dict: {rate_date, target_currency, rate}."""
        if not rates:
            return
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            if self._backend == "sqlite":
                cur.executemany(
                    f"""INSERT OR REPLACE INTO {self._t('ecb_rates')}
                        (rate_date, base_currency, target_currency, rate, source, fetched_at)
                        VALUES (?, 'EUR', ?, ?, 'ECB', ?)""",
                    [(r["rate_date"], r["target_currency"], r["rate"], now) for r in rates],
                )
            else:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    f"""INSERT INTO {self._t('ecb_rates')}
                        (rate_date, base_currency, target_currency, rate, source, fetched_at)
                        VALUES %s
                        ON CONFLICT (rate_date, target_currency)
                        DO UPDATE SET rate = EXCLUDED.rate, fetched_at = EXCLUDED.fetched_at""",
                    [(r["rate_date"], "EUR", r["target_currency"], r["rate"], "ECB", now) for r in rates],
                )

    def get_ecb_rate(self, target_currency: str, rate_date: date) -> Optional[ECBRate]:
        """Get ECB rate for a currency on a specific date."""
        param = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT rate_date, base_currency, target_currency, rate, source, fetched_at
                    FROM {self._t('ecb_rates')}
                    WHERE target_currency = {param} AND rate_date = {param}""",
                (target_currency, str(rate_date)),
            )
            row = cur.fetchone()
            if not row:
                return None
            return ECBRate(
                rate_date=date.fromisoformat(str(row[0])) if isinstance(row[0], str) else row[0],
                base_currency=row[1].strip(),
                target_currency=row[2].strip(),
                rate=float(row[3]),
                source=row[4].strip() if row[4] else "ECB",
                fetched_at=datetime.fromisoformat(str(row[5])) if isinstance(row[5], str) else row[5],
            )

    def get_ecb_rate_closest(self, target_currency: str, rate_date: date) -> Optional[ECBRate]:
        """Get the most recent ECB rate on or before the given date.

        Per REQ-LEG-003: use the rate for the last business day of reporting period.
        """
        param = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT rate_date, base_currency, target_currency, rate, source, fetched_at
                    FROM {self._t('ecb_rates')}
                    WHERE target_currency = {param} AND rate_date <= {param}
                    ORDER BY rate_date DESC LIMIT 1""",
                (target_currency, str(rate_date)),
            )
            row = cur.fetchone()
            if not row:
                return None
            return ECBRate(
                rate_date=date.fromisoformat(str(row[0])) if isinstance(row[0], str) else row[0],
                base_currency=row[1].strip(),
                target_currency=row[2].strip(),
                rate=float(row[3]),
                source=row[4].strip() if row[4] else "ECB",
                fetched_at=datetime.fromisoformat(str(row[5])) if isinstance(row[5], str) else row[5],
            )

    def get_ecb_rate_count(self) -> int:
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._t('ecb_rates')}")
            return cur.fetchone()[0]

    def get_ecb_date_range(self) -> tuple[Optional[date], Optional[date]]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT MIN(rate_date), MAX(rate_date) FROM {self._t('ecb_rates')}"
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return (None, None)
            parse = lambda v: date.fromisoformat(str(v)) if isinstance(v, str) else v
            return (parse(row[0]), parse(row[1]))

    def get_ecb_currencies(self) -> list[str]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT target_currency FROM {self._t('ecb_rates')} ORDER BY target_currency"
            )
            return [row[0].strip() for row in cur.fetchall()]

    # ── GLEIF LEI Cache ────────────────────────────────────────────

    def upsert_lei(self, records: list[dict]):
        """Bulk upsert LEI records. Automatically computes normalized_name."""
        if not records:
            return
        from shared.lei_validator import normalize_entity_name
        now = datetime.utcnow().isoformat()
        rows = [
            (
                r["lei"], r["legal_name"],
                normalize_entity_name(r["legal_name"]),
                r["entity_status"],
                r.get("country", ""),
                r.get("registration_authority"),
                r.get("last_update"), now,
                r.get("expires_at", now),
            )
            for r in records
        ]
        with self._cursor() as cur:
            if self._backend == "sqlite":
                cur.executemany(
                    f"""INSERT OR REPLACE INTO {self._t('gleif_lei_cache')}
                        (lei, legal_name, normalized_name, entity_status, country,
                         registration_authority, last_update, fetched_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
            else:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    f"""INSERT INTO {self._t('gleif_lei_cache')}
                        (lei, legal_name, normalized_name, entity_status, country,
                         registration_authority, last_update, fetched_at, expires_at)
                        VALUES %s
                        ON CONFLICT (lei)
                        DO UPDATE SET
                            legal_name = EXCLUDED.legal_name,
                            normalized_name = EXCLUDED.normalized_name,
                            entity_status = EXCLUDED.entity_status,
                            country = EXCLUDED.country,
                            registration_authority = EXCLUDED.registration_authority,
                            last_update = EXCLUDED.last_update,
                            fetched_at = EXCLUDED.fetched_at,
                            expires_at = EXCLUDED.expires_at""",
                    rows,
                )

    def get_lei(self, lei: str) -> Optional[LEIRecord]:
        param = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT lei, legal_name, normalized_name, entity_status, country,
                           registration_authority, last_update, fetched_at, expires_at
                    FROM {self._t('gleif_lei_cache')}
                    WHERE lei = {param}""",
                (lei,),
            )
            row = cur.fetchone()
            if not row:
                return None
            parse_dt = lambda v: datetime.fromisoformat(str(v)) if v and isinstance(v, str) else v
            parse_d = lambda v: date.fromisoformat(str(v)) if v and isinstance(v, str) else v
            return LEIRecord(
                lei=row[0].strip(),
                legal_name=row[1],
                normalized_name=row[2] or "",
                entity_status=row[3].strip() if row[3] else "",
                country=row[4].strip() if row[4] else "",
                registration_authority=row[5],
                last_update=parse_d(row[6]),
                fetched_at=parse_dt(row[7]),
                expires_at=parse_dt(row[8]),
            )

    def search_lei_by_normalized_name(
        self, normalized_name: str, country: str = "", limit: int = 10,
    ) -> list[LEIRecord]:
        """Search LEI cache by normalized name, optionally filtered by country.

        If country is provided (ISO 3166-1 alpha-2), results are filtered to
        that country first. If no matches found with country filter, falls back
        to name-only search.
        """
        param = "?" if self._backend == "sqlite" else "%s"
        parse_dt = lambda v: datetime.fromisoformat(str(v)) if v and isinstance(v, str) else v
        parse_d = lambda v: date.fromisoformat(str(v)) if v and isinstance(v, str) else v

        def _to_records(rows):
            return [
                LEIRecord(
                    lei=r[0].strip(), legal_name=r[1], normalized_name=r[2] or "",
                    entity_status=r[3].strip() if r[3] else "",
                    country=r[4].strip() if r[4] else "",
                    registration_authority=r[5], last_update=parse_d(r[6]),
                    fetched_at=parse_dt(r[7]), expires_at=parse_dt(r[8]),
                )
                for r in rows
            ]

        with self._cursor() as cur:
            # Try with country filter first (if provided)
            if country and country.strip():
                cur.execute(
                    f"""SELECT lei, legal_name, normalized_name, entity_status, country,
                               registration_authority, last_update, fetched_at, expires_at
                        FROM {self._t('gleif_lei_cache')}
                        WHERE normalized_name = {param} AND country = {param}
                        LIMIT {limit}""",
                    (normalized_name, country.strip().upper()),
                )
                rows = cur.fetchall()
                if rows:
                    return _to_records(rows)
                # Fall through to name-only search if no country match

            # Name-only search
            cur.execute(
                f"""SELECT lei, legal_name, normalized_name, entity_status, country,
                           registration_authority, last_update, fetched_at, expires_at
                    FROM {self._t('gleif_lei_cache')}
                    WHERE normalized_name = {param}
                    LIMIT {limit}""",
                (normalized_name,),
            )
            return _to_records(cur.fetchall())

    def get_lei_count(self) -> int:
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._t('gleif_lei_cache')}")
            return cur.fetchone()[0]

    # ── MIC Codes ──────────────────────────────────────────────────

    def upsert_mic_codes(self, records: list[dict]):
        """Bulk upsert MIC code records."""
        if not records:
            return
        now = datetime.utcnow().isoformat()
        with self._cursor() as cur:
            if self._backend == "sqlite":
                cur.executemany(
                    f"""INSERT OR REPLACE INTO {self._t('mic_codes')}
                        (mic, operating_mic, name, country, status, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                    [(r["mic"], r["operating_mic"], r["name"], r["country"], r["status"], now) for r in records],
                )
            else:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    f"""INSERT INTO {self._t('mic_codes')}
                        (mic, operating_mic, name, country, status, fetched_at)
                        VALUES %s
                        ON CONFLICT (mic)
                        DO UPDATE SET
                            operating_mic = EXCLUDED.operating_mic,
                            name = EXCLUDED.name,
                            country = EXCLUDED.country,
                            status = EXCLUDED.status,
                            fetched_at = EXCLUDED.fetched_at""",
                    [(r["mic"], r["operating_mic"], r["name"], r["country"], r["status"], now) for r in records],
                )

    def get_mic(self, mic: str) -> Optional[MICRecord]:
        param = "?" if self._backend == "sqlite" else "%s"
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT mic, operating_mic, name, country, status, fetched_at
                    FROM {self._t('mic_codes')} WHERE mic = {param}""",
                (mic,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return MICRecord(
                mic=row[0].strip(), operating_mic=row[1].strip(),
                name=row[2], country=row[3].strip(),
                status=row[4].strip(),
                fetched_at=datetime.fromisoformat(str(row[5])) if isinstance(row[5], str) else row[5],
            )

    def get_mic_count(self) -> int:
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self._t('mic_codes')}")
            return cur.fetchone()[0]

    # ── Freshness checks (REQ-REF-002) ─────────────────────────────

    def get_freshness_report(self) -> dict:
        """Return freshness status for each data type per REQ-REF-002."""
        report = {}
        with self._cursor() as cur:
            # ECB rates
            cur.execute(f"SELECT MAX(fetched_at), COUNT(*), MAX(rate_date) FROM {self._t('ecb_rates')}")
            row = cur.fetchone()
            report["ecb_rates"] = {
                "last_fetched": row[0], "record_count": row[1], "latest_rate_date": row[2],
            }
            # GLEIF
            cur.execute(f"SELECT MAX(fetched_at), COUNT(*) FROM {self._t('gleif_lei_cache')}")
            row = cur.fetchone()
            report["gleif_lei_cache"] = {"last_fetched": row[0], "record_count": row[1]}
            # MIC
            cur.execute(f"SELECT MAX(fetched_at), COUNT(*) FROM {self._t('mic_codes')}")
            row = cur.fetchone()
            report["mic_codes"] = {"last_fetched": row[0], "record_count": row[1]}
        return report

    # ── Lifecycle ──────────────────────────────────────────────────

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
