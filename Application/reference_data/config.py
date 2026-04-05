"""Reference data configuration.

Edit these values to match your local PostgreSQL setup.
The setup_and_fetch_all.py script uses these defaults.
"""

# Backend: "sqlite" or "postgresql"
BACKEND = "postgresql"

# PostgreSQL settings (used when BACKEND = "postgresql")
PG_HOST = "localhost"
PG_PORT = 5432
PG_DBNAME = "postgres"
PG_USER = "postgres"
PG_PASSWORD = "Eagle1968"  # fill in if you set a password

# SQLite settings (used when BACKEND = "sqlite")
SQLITE_PATH = "reference_data/reference_data.db"


def get_store():
    """Return a configured ReferenceStore instance."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared.reference_store import ReferenceStore

    if BACKEND == "postgresql":
        return ReferenceStore.postgresql(
            host=PG_HOST, port=PG_PORT,
            dbname=PG_DBNAME, user=PG_USER, password=PG_PASSWORD,
        )
    else:
        return ReferenceStore.sqlite(SQLITE_PATH)
