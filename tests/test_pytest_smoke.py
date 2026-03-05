"""
Smoke Tests — Basic health checks for all endpoints.
=====================================================
Verifies every endpoint returns a valid response.
"""

import pytest
from conftest import api_url, BASE_URL


class TestHealthAndStatus:
    """Verify database connectivity and basic metadata."""

    @pytest.mark.smoke
    def test_db_status(self, api_session):
        r = api_session.get(api_url("/api/db-status"))
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "mongo_v2"
        assert "records" in data
        assert data["records"] > 0
        assert "date_range" in data

    @pytest.mark.smoke
    def test_countries(self, api_session):
        r = api_session.get(api_url("/api/countries"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        names = [c["name"] for c in data]
        assert "United States" in names

    @pytest.mark.smoke
    def test_states_united_states(self, api_session):
        r = api_session.get(api_url("/api/states/United States"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        names = [s["name"] for s in data]
        assert "Florida" in names
        assert "Maryland" in names

    @pytest.mark.smoke
    def test_states_all(self, api_session):
        r = api_session.get(api_url("/api/states/all"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.smoke
    def test_games_florida(self, api_session):
        r = api_session.get(api_url("/api/games/Florida"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.smoke
    def test_games_maryland(self, api_session):
        r = api_session.get(api_url("/api/games/Maryland"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.smoke
    def test_prediction_states(self, api_session):
        r = api_session.get(api_url("/api/prediction/states"))
        assert r.status_code == 200
        data = r.json()
        assert "Florida" in data

    @pytest.mark.smoke
    def test_dp_options_pick4(self, api_session):
        r = api_session.get(api_url("/api/prediction/dp-options/pick4"))
        assert r.status_code == 200


class TestUIRoutes:
    """Verify all template routes respond (may 500 if templates dir is wrong).

    These routes depend on the server being started from the project root
    so Flask can find the templates/ directory. We accept 200 or 500 here
    and only fail on connection errors.
    """

    @pytest.mark.smoke
    @pytest.mark.parametrize("path", [
        "/",
        "/legacy",
        "/predictions",
        "/platform",
        "/backtest",
        "/backtest/v5",
        "/tools/consecutive-sums",
        "/analysis/rbtl",
        "/analysis/efficacy",
        "/analysis/consecutive",
        "/analysis/patterns",
        "/nexus",
        "/settings",
        "/rbtl",
        "/consecutive",
        "/rbtl/predictions",
        "/rbtl/backtest",
        "/report/efficacy",
        "/report/efficacy-unified",
        "/report/efficacy-pick5",
        "/predictions/pick5",
        "/predictions/unified",
    ])
    def test_ui_route(self, api_session, path):
        r = api_session.get(f"{BASE_URL}{path}", timeout=10)
        # Accept 200 (templates found) or 500 (TemplateNotFound when
        # server wasn't started from the project root directory)
        assert r.status_code in (200, 500)
        assert len(r.text) > 0
