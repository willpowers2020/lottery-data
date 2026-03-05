"""
Multi-State Cross-Validation Tests.
=====================================
Ensures core endpoints work consistently across primary states.
"""

import pytest
from conftest import api_url, STATES


class TestMultiStatePick4:
    """Verify Pick 4 data across all primary states."""

    @pytest.mark.parametrize("state", STATES)
    def test_recent_draws_pick4(self, api_session, state):
        payload = {
            "state": state,
            "game_type": "pick4",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }
        r = api_session.post(api_url("/api/draws/recent"), json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] > 0, f"No Pick 4 draws for {state} in Jan 2025"

    @pytest.mark.parametrize("state", STATES)
    def test_rbtl_data_stats_pick4(self, api_session, state):
        r = api_session.get(api_url(f"/api/rbtl/data-stats/{state}/pick4"))
        assert r.status_code == 200
        data = r.json()
        assert data["total_draws"] > 0, f"No Pick 4 data for {state}"

    @pytest.mark.parametrize("state", STATES)
    def test_latest_draw_pick4(self, api_session, state):
        r = api_session.get(api_url(f"/api/prediction/latest/{state}/pick4"))
        assert r.status_code == 200
        data = r.json()
        assert "date" in data
        assert "value" in data

    @pytest.mark.parametrize("state", STATES)
    def test_games_available(self, api_session, state):
        r = api_session.get(api_url(f"/api/games/{state}"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, f"No games found for {state}"


class TestMultiStatePick5:
    """Verify Pick 5 data across states that support it."""

    PICK5_STATES = ["Florida", "Maryland", "Virginia", "Pennsylvania"]

    @pytest.mark.parametrize("state", PICK5_STATES)
    def test_recent_draws_pick5(self, api_session, state):
        payload = {
            "state": state,
            "game_type": "pick5",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }
        r = api_session.post(api_url("/api/draws/recent"), json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] > 0, f"No Pick 5 draws for {state} in Jan 2025"

    @pytest.mark.parametrize("state", PICK5_STATES)
    def test_rbtl_data_stats_pick5(self, api_session, state):
        r = api_session.get(api_url(f"/api/rbtl/data-stats/{state}/pick5"))
        assert r.status_code == 200
        data = r.json()
        assert data["total_draws"] > 0, f"No Pick 5 data for {state}"


class TestMultiStatePick3:
    """Verify Pick 3 across primary states."""

    @pytest.mark.parametrize("state", STATES)
    def test_recent_draws_pick3(self, api_session, state):
        payload = {
            "state": state,
            "game_type": "pick3",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }
        r = api_session.post(api_url("/api/draws/recent"), json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] > 0, f"No Pick 3 draws for {state} in Jan 2025"
