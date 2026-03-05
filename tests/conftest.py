"""Shared pytest fixtures for MLD integration tests."""

import pytest
import requests

BASE_URL = "http://localhost:5001"
DB_MODE = "mongo_v2"


def api_url(path, db=DB_MODE):
    """Build full API URL with db mode parameter."""
    sep = "&" if "?" in path else "?"
    return f"{BASE_URL}{path}{sep}db={db}"


@pytest.fixture(scope="session")
def api_base():
    """Base URL for the running Flask server."""
    return BASE_URL


@pytest.fixture(scope="session")
def db_mode():
    """Database mode to use in tests."""
    return DB_MODE


@pytest.fixture(scope="session")
def api_session():
    """Requests session pre-configured for API calls.

    Skips all tests if the Flask server is not running.
    """
    session = requests.Session()
    try:
        r = session.get(api_url("/api/db-status"), timeout=10)
        r.raise_for_status()
    except Exception as e:
        pytest.skip(f"Flask server not running at {BASE_URL}: {e}")
    return session


# Common test constants
STATES = ["Florida", "Maryland", "Virginia", "Pennsylvania"]
GAME_TYPES = ["pick2", "pick3", "pick4", "pick5"]
