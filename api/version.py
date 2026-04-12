"""Single source of truth for Eagle build metadata.

Bump BUILD_NUMBER every time you deploy a code change so the frontend
debug bar instantly shows whether browser, API server, and database
schema are all running the same version.

Usage from anywhere in the backend:
    from api.version import BUILD_NUMBER, VERSION, BUILD_TIMESTAMP
"""

VERSION = "0.3.1"
BUILD_NUMBER = 17
BUILD_TIMESTAMP = "2026-04-11T03:00:00Z"

# Database schema version — bump when you run a migration / ALTER TABLE.
DB_SCHEMA_VERSION = 1
