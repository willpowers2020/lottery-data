# Lottery Data Platform ("mld")

This repository (often referred to simply as `mld` or “lottery-data-tool”) contains the
code powering the Lottery Data Platform — a lottery data library, analysis
algorithms, and a small Flask REST API.  You may prefer to rename the GitHub
repo to something shorter (e.g. `mld` or `lottery-tool`) if you like; the
internal package is already named `mld`.

## Overview

The project has been reorganized for clarity and maintainability. Key areas:

```
/lottery-data          # new project root (formerly mylottodata-query-tool)
├── src/mld/             # Python package (core logic)
│   ├── api.py           # Flask application and routes
│   ├── analysis/        # prediction/utility scripts
│   ├── helpers/         # shared helper functions
│   └── legacy/          # older scripts queued for refactor
├── scripts/             # standalone maintenance/utilities
├── tests/               # automated tests (mostly API-driven)
├── templates/           # HTML templates used by the web app
├── docs/                # design docs and architectural notes
├── .github/             # GitHub Actions workflows
├── requirements.txt     # dependencies
└── README.md            # this file
```

### Package setup

- `src/mld` is a regular Python package.  When running tools you can either
  install the package with `pip install -e src` or simply run scripts from the
  repository root; many scripts already add `src/` to `sys.path`.
- `app.py` at the root is a thin wrapper importing `mld.api.app`.  You can start
  the web server via `python app.py` or `gunicorn mld.api:app`.

### Scripts

Common maintenance utilities live in `scripts/` (e.g. `check_db_current.py`,
`post_sync_gap_check.py`, `rebuild_chunked.py`).  They are self-contained and
adjust `PYTHONPATH` so they see the package.

### Analysis code

Algorithms, prediction tools and backtesting helpers are located under
`src/mld/analysis`.  You can import them in other projects via
`from mld.analysis import ...`.

### Tests

The `tests/` directory contains various scripts for exercising the API and
verifying outputs.  Most of them call the running Flask server using `requests`.

## Getting started

1. **Install dependencies**:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   # optionally install the package for import convenience
   pip install -e src
   ```

2. **Run the API**:

   ```bash
   python app.py
   # or:
   gunicorn mld.api:app
   ```

3. **Run a script**:

   ```bash
   python scripts/check_db_current.py
   ```

4. **Run tests** (requires the Flask app to be running):

   ```bash
   cd tests
   python test_pick5_all_states.py
   # or run them all with a simple shell loop or pytest
   ```

## Next steps

- Gradually move more legacy modules from `src/mld/legacy` into `analysis` or
  `helpers` and add corresponding tests.
- Add `pyproject.toml`/`setup.py` if packaging is needed.
- Update GitHub workflows to install from `src/` when running tools.

For more detailed refactoring guidance, see [CLAUDE.md](CLAUDE.md).
