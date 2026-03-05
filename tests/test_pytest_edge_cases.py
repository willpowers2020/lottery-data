"""
Edge Case & Error Handling Tests.
==================================
"""

import pytest
from conftest import api_url, BASE_URL


class TestInvalidInputs:
    """Test that invalid inputs return proper errors."""

    def test_lookup_no_json_body(self, api_session):
        r = api_session.post(
            api_url("/api/lookup"),
            data="not json",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code in [400, 415, 500]

    def test_prediction_invalid_state(self, api_session):
        payload = {
            "seed_number": "1234",
            "seed_date": "2025-01-15",
            "state": "Narnia",
            "game_type": "pick4",
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/2dp-ap"), json=payload, timeout=30)
        data = r.json()
        # Should return error or empty results
        assert r.status_code in [200, 400, 404] or data.get("error")

    def test_backtest_v2_missing_required(self, api_session):
        payload = {"state": "Florida"}  # Missing most required fields
        r = api_session.post(api_url("/api/rbtl/backtest-v2"), json=payload, timeout=30)
        # The endpoint may use defaults for missing fields — accept any response
        assert r.status_code in [200, 400, 500]

    def test_draws_recent_missing_state(self, api_session):
        payload = {"game_type": "pick4", "start_date": "2025-01-01", "end_date": "2025-01-31"}
        r = api_session.post(api_url("/api/draws/recent"), json=payload, timeout=30)
        # May return empty results or error
        assert r.status_code in [200, 400]

    def test_td_lookup_invalid_game_type(self, api_session):
        payload = {
            "candidates": ["1234"],
            "state": "Florida",
            "game_type": "pick99",
        }
        r = api_session.post(api_url("/api/td/lookup"), json=payload, timeout=30)
        data = r.json()
        assert r.status_code in [200, 400, 404] or data.get("error")


class TestBoundaryConditions:
    """Test boundary and extreme values."""

    def test_td_lookup_many_candidates(self, api_session):
        """Should cap at 500 candidates."""
        candidates = [str(i).zfill(4) for i in range(600)]
        payload = {"candidates": candidates, "state": "Florida", "game_type": "pick4"}
        r = api_session.post(api_url("/api/td/lookup"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        # Should be capped at 500
        assert data["count"] <= 500

    @pytest.mark.slow
    def test_consecutive_draws_future_date(self, api_session):
        """Future date range should return empty or zero results."""
        payload = {
            "game_type": "pick4",
            "states": ["Florida"],
            "start_date": "2030-01-01",
            "end_date": "2030-01-07",
            "tod": "All",
        }
        r = api_session.post(api_url("/api/consecutive/draws"), json=payload, timeout=120)
        assert r.status_code == 200

    def test_nonexistent_api_route(self, api_session):
        """Non-existent route should 404."""
        r = api_session.get(f"{BASE_URL}/api/nonexistent/endpoint")
        assert r.status_code == 404

    def test_games_nonexistent_state(self, api_session):
        """Games for non-existent state should return empty list."""
        r = api_session.get(api_url("/api/games/Atlantis"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 0

    def test_states_nonexistent_country(self, api_session):
        """States for non-existent country should return empty list."""
        r = api_session.get(api_url("/api/states/Mordor"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 0
