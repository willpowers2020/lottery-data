# Lottery Data Platform ("mld") - Project Structure Guidance

This repository supports the Lottery Data Platform (internally called **mld**),
a lottery data library and API suite used by lottery enthusiasts. It contains:

- data ingestion/scraper scripts
- analysis and prediction algorithms
- a Flask web API (`app.py`) that powers a frontend and exposes endpoints
- various one-off utilities and tests

To make the code easier to navigate, maintain, and extend, the following
higher-level directory structure is recommended.  Initially everything lives in
the top‑level directory; the structure below guides a gradual refactor.

## Suggested directory layout

```
/mylottodata-query-tool
├── src/                # Python package source
│   └── mld/            # core modules (database adapters, utils, api)
│       ├── __init__.py
│       ├── db.py       # adapters for sqlite/mongo (existing code)
│       ├── api.py      # Flask routes extracted from app.py
│       ├── analysis/   # prediction algorithms, reports, etc.
│       └── helpers/    # shared helpers (parsing, normalization)
├── scripts/            # standalone scripts and maintenance tools
│   ├── post_sync_gap_check.py
│   ├── check_db_current.py
│   ├── rebuild_chunked.py
│   └── ...             # move other one-offs here
├── tests/              # automated tests (pytest, shell helpers)
│   ├── test_*py
│   └── fixtures/       # sample data used by tests
├── templates/          # HTML templates for the Flask app
├── docs/               # design docs, user guides, architecture notes
│   └── architecture.md # this file or more detailed docs
├── .github/            # workflows & CI config (db_check.yml already exists)
├── requirements.txt    # dependencies for development
├── Procfile, railway.toml, etc.
└── app.py              # small wrapper that imports src.mld.api
```

> **Note:** the existing flat Python files can be moved one by one into the
> appropriate package/modules in `src/mld/`.  This repository history will
> preserve their content, so you can refactor gradually.

## How to start refactoring

1. **Package initialization**: create `src/mld/__init__.py` and update
   `PYTHONPATH`/`setup.py` if you have one.  All imports should use
   `from mld import ...`.
2. **Separate the API**: split `app.py` into `src/mld/api.py` (routes) and a
   small top‑level `app.py` that just does `from mld.api import app`.
3. **Group utilities**: identify common helper functions (e.g. parsing,
   state normalization, database helpers) and move them into `helpers`.
4. **Move scripts**: relocate standalone utilities into `scripts/` and call
   them with `python -m mld.scripts.whatever` if desired.
5. **Add tests**: for each module you extract, add a corresponding test under
   `tests/` using `pytest` (the repo already contains many test files).
6. **Update workflow**: adjust GitHub Actions to install from `src/` if you add
   a `setup.py` or `pyproject.toml`.

## File categorization ideas

- `cluster_predictor.py`, `hots_tighten.py`, `backtest_*` → go under
  `src/mld/analysis/`
- `db_maintenance.py`, `migrate_to_mongo.py` → `scripts/`
- `diagnose_lottery_db*.py` → `scripts/diagnose.py` or similar
- `pick5_*`, `prediction_output.txt`, etc. → either tests or analysis modules

## Operational resources

- `docs/` can contain notes such as:
  - architecture overview
  - database schema descriptions
  - deployment instructions (railway, Procfile, etc.)
  - instructions for developers: `python -m venv`, activating env, etc.

- `CLAUDE.md` and/or `architecture.md` are checkpoints for the current state
  and future plans; think of them as living documentation that you can expand.

## Benefits of restructuring

- **Clarity**: new contributors (or future you) can find relevant code quickly.
- **Testability**: modules under `src/` are easier to import in tests.
- **Reuse**: shared helpers live in one place instead of being copied.
- **Deployment**: packaging the project as a Python package simplifies the
  web service deployment (e.g. `gunicorn mld.api:app`).

---

This file is just a starting point.  As you refactor, feel free to update the
structure and documentation to suit the actual needs of the project.  If you
want help moving specific scripts or splitting modules, let me know!  Happy
refactoring.