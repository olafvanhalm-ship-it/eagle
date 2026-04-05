# Project Eagle — Local Development Environment Setup Guide

**Version:** 1.0
**Date:** 2026-04-05
**Purpose:** Transform the current Google Drive-based workflow into a proper local development environment with Git version control, enabling efficient Cowork collaboration and automated testing.

---

## Executive Summary

### Current State (Problems)

1. **Code lives on Google Drive** — no version control, no history, no rollback capability
2. **No Python installed locally** — scripts can only run in Cowork sandbox sessions
3. **No `requirements.txt`** — dependencies are implicit, making reproducibility impossible
4. **Manual copying** between Drive, Cowork sandbox, and local — error-prone and slow
5. **Cowork cannot access PostgreSQL** — validation requires manual checking
6. **SQLite doesn't work on Google Drive** (WAL mode needs file locking)

### Target State (Solution)

1. **GitHub private repository** as single source of truth for all code
2. **Python 3.12 + virtual environment** on your laptop for local execution
3. **Proper project structure** with `pyproject.toml`, dependency management, and test configuration
4. **Git-based Cowork workflow** — Cowork clones the repo, makes changes, commits and pushes
5. **PostgreSQL accessible** for both local scripts and regression testing
6. **One-command** regression suite execution locally

### What Changes for You

| Before | After |
|--------|-------|
| Edit code via Cowork on Drive files | Cowork pushes to GitHub, you pull with one command |
| Run scripts only in Cowork sandbox | Run scripts locally OR in Cowork — same result |
| No undo if something breaks | Full git history, rollback any change |
| Manual copy between environments | `git pull` syncs everything instantly |
| "Did I lose that change?" | Every change tracked with author + timestamp |

---

## Architecture Decision: Why This Approach

### Why NOT Docker (for now)

Docker would be the production-grade answer, but for your situation it adds unnecessary complexity:

- You'd need to install Docker Desktop on Windows (~4 GB), learn Docker concepts, manage containers
- Your stack is simple right now: Python scripts + PostgreSQL — both run natively on Windows
- Docker is valuable when you have multiple services (frontend + backend + DB + queue) — that's Phase 2
- **Decision:** Install Python + use existing PostgreSQL natively. Revisit Docker when we add FastAPI + Next.js.

### Why GitHub as Central Hub

- **Cowork integration:** Cowork can clone repos, run tests, commit and push changes
- **Version control:** Every change tracked, every regression suite run reproducible
- **Collaboration:** Clear history of who changed what and why
- **Free:** Private repos are free on GitHub, unlimited for personal accounts
- **Future-proof:** When you hire developers, they onboard via the same repo

### Why NOT Keep Google Drive as Primary

Google Drive remains useful for **Blueprint documents** (architecture, requirements — non-code files). But code must move to Git because:

- Drive has no diff/merge capability
- Drive sync can corrupt files mid-edit
- SQLite (used for test reference stores) fails on Drive mounts
- Cowork's Drive access is read-heavy; Git access is faster and supports push

---

## Step-by-Step Setup

### Phase 1: Python ✅ Already Installed (3.11.9)

Python 3.11.9 is already installed. This is fine for Eagle — the architecture specifies 3.12+ as the production target, but 3.11.9 is fully compatible for development. We can upgrade to 3.12 later if needed.

**Step 1.1 — Verify Python is on PATH**

Open Command Prompt (Start → type `cmd` → Enter) and run:

```
python --version
pip --version
```

You should see `Python 3.11.9` and a `pip` version. If you see "not recognized", Python may not be on your PATH — let me know and we'll fix that.

---

### Phase 2: Install Git (10 minutes)

**Step 2.1 — Download Git for Windows**

1. Go to: https://git-scm.com/download/win
2. Download the 64-bit installer
3. Run the installer

**Step 2.2 — Installer settings**

Accept all defaults EXCEPT:
- When asked about the default editor: choose **"Use Visual Studio Code as Git's default editor"**
- When asked about PATH: choose **"Git from the command line and also from 3rd-party software"** (the recommended option)
- Everything else: keep defaults

**Step 2.3 — Configure Git identity**

Open a new Command Prompt and run:

```
git config --global user.name "Olaf van Halm"
git config --global user.email "olaf.van.halm@maxxmanagement.nl"
```

**Step 2.4 — Authenticate with GitHub**

Install the GitHub CLI (easiest way to authenticate):

1. Go to: https://cli.github.com/
2. Download and install the Windows MSI
3. Open Command Prompt and run:

```
gh auth login
```

Follow the prompts:
- Select "GitHub.com"
- Select "HTTPS"
- Select "Login with a web browser"
- Copy the code shown, press Enter, and paste it in the browser

---

### Phase 3: Create Local Project Directory (5 minutes)

**Step 3.1 — Create the project folder**

We create the project on your LOCAL disk (not Google Drive) for performance and SQLite compatibility:

```
mkdir C:\Dev\eagle
cd C:\Dev\eagle
```

**Step 3.2 — Initialize Git repository**

```
git init
```

---

### Phase 4: Set Up Project Structure (Cowork does this)

> **This is where Cowork takes over.** After you complete Phases 1–3, start a new Cowork session and say:
> "I've installed Python, Git, and created C:\Dev\eagle. Please set up the project structure."

Cowork will create the following structure:

```
C:\Dev\eagle/
├── pyproject.toml              # Project metadata + dependencies
├── README.md                   # Project overview
├── .gitignore                  # Files to exclude from Git
├── .env.example                # Environment variable template (no secrets)
├── .vscode/                    # VS Code workspace settings
│   ├── settings.json           # Python path, linting, formatting
│   └── extensions.json         # Recommended extensions
│
├── src/                        # All source code
│   └── eagle/                  # Python package root
│       ├── __init__.py
│       ├── adapters/           # L1B — Input adapters
│       │   ├── __init__.py
│       │   ├── m_adapter/      # M adapter (Excel templates)
│       │   ├── esma_adapter/   # ESMA v1.2 adapter
│       │   └── fca_adapter/    # FCA v2.0 adapter
│       │
│       ├── canonical/          # Canonical data model
│       │   ├── __init__.py
│       │   ├── model.py
│       │   ├── source_entities.py
│       │   ├── field_registry.py
│       │   ├── projection.py
│       │   ├── merge.py
│       │   ├── provenance.py
│       │   └── store.py
│       │
│       ├── derivation/         # L2 — Deterministic derivation engine
│       │   ├── __init__.py
│       │   ├── period.py
│       │   ├── investor.py
│       │   ├── portfolio.py
│       │   ├── turnover.py
│       │   └── fx_service.py
│       │
│       ├── validation/         # L3 — Validation engine
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   └── approved_rule_hashes.yaml
│       │
│       ├── packaging/          # L6 — NCA file packaging
│       │   ├── __init__.py
│       │   ├── aifm_builder.py
│       │   ├── aif_builder.py
│       │   ├── nca_packaging.py
│       │   └── orchestrator.py
│       │
│       ├── reference_data/     # Reference data fetchers + store
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── store.py
│       │   ├── fetch_ecb_rates.py
│       │   ├── fetch_gleif_lei.py
│       │   └── fetch_mic_codes.py
│       │
│       └── shared/             # Cross-cutting utilities
│           ├── __init__.py
│           ├── constants.py
│           ├── formatting.py
│           ├── lei_validator.py
│           └── lei_enrichment.py
│
├── config/                     # Runtime configuration (YAML rules, NCA overrides)
│   └── aifmd/
│       └── annex_iv/
│           ├── validation_rules.yaml
│           ├── field_source_classification.yaml
│           └── nca_overrides/
│               ├── nl_afm.yaml
│               ├── de_bafin.yaml
│               └── ... (31 NCA override files)
│
├── xsd/                        # XSD schemas for XML validation
│   ├── esma_1.2/
│   └── fca_2.0/
│
├── tests/                      # All tests
│   ├── conftest.py             # Shared fixtures (DB connections, test data)
│   ├── unit/                   # Unit tests per module
│   ├── regression/             # Regression suite
│   │   ├── run_regression.py
│   │   ├── golden_set/         # Reference data + expected results
│   │   └── evidence/           # Regression run results
│   └── integration/            # Integration tests (DB, full pipeline)
│
├── scripts/                    # Utility scripts
│   ├── setup_db.py             # Create PostgreSQL schema
│   ├── seed_reference_data.py  # Populate reference data
│   └── run_regression.bat      # Windows one-click regression runner
│
└── data/                       # Local test data (gitignored if sensitive)
    ├── sqlite/                 # SQLite databases for testing
    └── templates/              # Test Excel templates
```

### Key differences from current structure

| Current (Google Drive) | New (Git repo) | Why |
|------------------------|----------------|-----|
| `Application/Adapters/Input adapters/M adapter/` | `src/eagle/adapters/m_adapter/` | No spaces in paths (breaks imports), proper Python package |
| `Application/shared/` | `src/eagle/shared/` | Under the `eagle` package namespace |
| `Application/regulation/aifmd/annex_iv/` | `config/aifmd/annex_iv/` | Config separated from source code |
| No `requirements.txt` | `pyproject.toml` with all deps | Reproducible installs |
| No tests structure | `tests/` with unit + regression + integration | Organized test hierarchy |
| Files scattered, some duplicated in `Projects--Project Eagle` | Single authoritative location | No confusion about which version is current |

---

### Phase 5: Migrate Code (Cowork does this)

Cowork will:

1. Copy all 55 Python files from Google Drive to the new structure
2. Fix all import paths (e.g., `from shared.constants import` → `from eagle.shared.constants import`)
3. Create `pyproject.toml` with all dependencies discovered from import statements
4. Run the regression suite to verify nothing broke during migration
5. Commit everything to Git with a clear history

**Your Google Drive `Application/` folder stays untouched** as a backup. Once you're confident the Git repo works, the Drive copy becomes archive-only.

---

### Phase 6: Push to GitHub (5 minutes, you + Cowork)

**Step 6.1 — Create the GitHub repository**

In Command Prompt, from `C:\Dev\eagle`:

```
gh repo create eagle --private --source=. --push
```

This creates a private repo called `eagle` on your GitHub account and pushes all code.

**Step 6.2 — Verify**

Open https://github.com/YOUR_USERNAME/eagle in your browser. You should see all your code.

---

### Phase 7: Set Up Virtual Environment (5 minutes)

**Step 7.1 — Create virtual environment**

From Command Prompt in `C:\Dev\eagle`:

```
python -m venv .venv
.venv\Scripts\activate
```

You'll see `(.venv)` appear at the start of your command prompt.

**Step 7.2 — Install project dependencies**

```
pip install -e ".[dev]"
```

This installs the Eagle project in "editable" mode plus all development dependencies (pytest, linting tools, etc.).

---

### Phase 8: Configure VS Code (5 minutes)

**Step 8.1 — Open the project**

```
code C:\Dev\eagle
```

**Step 8.2 — Install recommended extensions**

VS Code will show a popup: "This workspace has extension recommendations." Click "Install All."

Key extensions that will be recommended:
- **Python** (Microsoft) — Python language support
- **Pylance** — Fast Python IntelliSense
- **GitLens** — Enhanced Git integration (see who changed what, when)
- **GitHub Pull Requests** — Review PRs from VS Code

**Step 8.3 — Select Python interpreter**

1. Press `Ctrl+Shift+P`
2. Type "Python: Select Interpreter"
3. Choose the `.venv` one: `C:\Dev\eagle\.venv\Scripts\python.exe`

---

### Phase 9: Configure PostgreSQL Connection (10 minutes)

**Step 9.1 — Create the Eagle database**

Open pgAdmin, connect to your local server, and run:

```sql
-- Create a dedicated Eagle database
CREATE DATABASE eagle_dev;

-- Create a dedicated user (not the postgres superuser)
CREATE USER eagle_app WITH PASSWORD 'eagle_dev_local';
GRANT ALL PRIVILEGES ON DATABASE eagle_dev TO eagle_app;

-- Connect to eagle_dev and enable required extensions
\c eagle_dev
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

**Step 9.2 — Create the `.env` file**

Copy `.env.example` to `.env` (this file is gitignored — never committed):

```
cp .env.example .env
```

Edit `.env` with your PostgreSQL connection details:

```env
# Database
EAGLE_DB_HOST=localhost
EAGLE_DB_PORT=5432
EAGLE_DB_NAME=eagle_dev
EAGLE_DB_USER=eagle_app
EAGLE_DB_PASSWORD=eagle_dev_local

# Reference data (SQLite for testing, stored locally)
EAGLE_SQLITE_PATH=C:/Dev/eagle/data/sqlite/reference.db

# Logging
EAGLE_LOG_LEVEL=INFO
```

**Step 9.3 — Initialize the database schema**

```
python scripts/setup_db.py
```

This creates all tables defined in the architecture (§6.1–6.3): `canonical_records`, `validation_results`, `ecb_exchange_rates`, `gleif_lei_cache`, `iso_mic_codes`, etc.

---

### Phase 10: Verify Everything Works (10 minutes)

**Step 10.1 — Run unit tests**

```
pytest tests/unit/ -v
```

**Step 10.2 — Run quick regression (real data)**

```
python tests/regression/run_regression.py --scope realdata
```

**Step 10.3 — Run full regression (all suites)**

```
python tests/regression/run_regression.py --scope all
```

If all suites pass, your local environment is fully operational.

---

## Daily Workflow After Setup

### For You (Olaf)

**Start of day:**
```
cd C:\Dev\eagle
git pull
```
This pulls any changes Cowork made.

**Run tests after changes:**
```
.venv\Scripts\activate
pytest tests/unit/ -v
```

**See what changed:**
```
git log --oneline -10
```

### For Cowork Sessions

When you start a Cowork session for development work, say something like:
> "Clone the Eagle repo and work on [task]"

Cowork will:
1. Clone `https://github.com/YOUR_USERNAME/eagle.git`
2. Install dependencies
3. Make changes
4. Run regression suite to verify
5. Commit and push

You then pull the changes locally with `git pull`.

### The Windows Batch Scripts

For convenience, `scripts/` will contain `.bat` files you can double-click:

| Script | What it does |
|--------|-------------|
| `run_tests.bat` | Activates venv + runs pytest |
| `run_regression_quick.bat` | Activates venv + runs realdata regression |
| `run_regression_full.bat` | Activates venv + runs all 74 suites |
| `pull_latest.bat` | Runs `git pull` to get latest changes |

---

## What Stays on Google Drive

| Location | Contents | Why |
|----------|----------|-----|
| `Blueprint/` | Architecture docs, requirements, role documents | These are reference documents, not code — Drive is fine |
| `Blueprint/eagle_dev_environment_setup.md` | This document | Reference |
| `Application/` (read-only archive) | Original code before migration | Backup until we're confident in the Git workflow |

---

## Migration Timeline

| Step | Duration | Who |
|------|----------|-----|
| Phase 1: Python (already done) | 0 min | ✅ |
| Phase 2: Install Git + GitHub CLI | 10 min | You |
| Phase 3: Create local directory | 5 min | You |
| Phase 4–5: Project structure + migrate code | 60–90 min | Cowork (next session) |
| Phase 6: Push to GitHub | 5 min | You + Cowork |
| Phase 7: Virtual environment | 5 min | You |
| Phase 8: VS Code setup | 5 min | You |
| Phase 9: PostgreSQL config | 10 min | You |
| Phase 10: Verify | 10 min | You |
| **Total** | **~2–3 hours** | Split across 2 sessions |

---

## Future Phases (Not Now)

These are documented for awareness but explicitly deferred:

1. **Docker Compose** — When we add FastAPI + Next.js, we'll containerize everything
2. **CI/CD with GitHub Actions** — Automated test runs on every push
3. **Pre-commit hooks** — Auto-format and lint before every commit
4. **Alembic migrations** — Database schema version control
5. **AWS deployment** — At least 12 months away per project timeline
