"""
Data Access Tests — Metadata, lookups, draws, and consecutive endpoints.
========================================================================
"""

import pytest
from conftest import api_url, STATES


class TestPredictionStatesAndGames:
    """Verify prediction state and game listing endpoints."""

    @pytest.mark.data_access
    def test_prediction_states(self, api_session):
        r = api_session.get(api_url("/api/prediction/states"))
        assert r.status_code == 200
        states = r.json()
        assert isinstance(states, list)
        assert "Florida" in states
        assert "Maryland" in states

    @pytest.mark.data_access
    @pytest.mark.parametrize("state", STATES)
    def test_prediction_games(self, api_session, state):
        r = api_session.get(api_url(f"/api/prediction/games/{state}"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.data_access
    @pytest.mark.parametrize("game_type", ["pick3", "pick4", "pick5"])
    def test_prediction_states_by_game(self, api_session, game_type):
        r = api_session.get(api_url(f"/api/prediction/{game_type}/states"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.data_access
    def test_pick5_states(self, api_session):
        r = api_session.get(api_url("/api/prediction/pick5/states"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

    @pytest.mark.data_access
    def test_pick5_games_florida(self, api_session):
        r = api_session.get(api_url("/api/prediction/pick5/games/Florida"))
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0


class TestLatestDraw:
    """Verify latest draw retrieval."""

    @pytest.mark.data_access
    @pytest.mark.parametrize("state,game_type", [
        ("Florida", "pick4"),
        ("Maryland", "pick4"),
        ("Florida", "pick5"),
        ("Virginia", "pick4"),
    ])
    def test_latest_draw(self, api_session, state, game_type):
        r = api_session.get(api_url(f"/api/prediction/latest/{state}/{game_type}"))
        assert r.status_code == 200
        data = r.json()
        assert "date" in data
        assert "value" in data

    @pytest.mark.data_access
    def test_pick5_latest_florida(self, api_session):
        r = api_session.get(api_url("/api/prediction/pick5/latest/Florida"))
        assert r.status_code == 200
        data = r.json()
        assert "date" in data


class TestDrawByDate:
    """Verify draw-by-date retrieval."""

    @pytest.mark.data_access
    def test_draw_by_date_valid(self, api_session):
        r = api_session.get(api_url("/api/prediction/draw-by-date/Florida/pick4/2019-09-15"))
        assert r.status_code == 200
        data = r.json()
        assert "draws" in data or "value" in data or "date" in data

    @pytest.mark.data_access
    def test_pick5_draw_by_date(self, api_session):
        r = api_session.get(api_url("/api/prediction/pick5/draw-by-date/Florida/2025-01-15"))
        assert r.status_code == 200


class TestRecentDraws:
    """Verify recent draws retrieval."""

    @pytest.mark.data_access
    @pytest.mark.parametrize("state,game_type", [
        ("Florida", "pick4"),
        ("Maryland", "pick3"),
        ("Virginia", "pick5"),
        ("Pennsylvania", "pick4"),
    ])
    def test_recent_draws(self, api_session, state, game_type):
        payload = {
            "state": state,
            "game_type": game_type,
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }
        r = api_session.post(api_url("/api/draws/recent"), json=payload, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "draws" in data
        assert "count" in data
        assert data["count"] >= 0


class TestLookup:
    """Verify number lookup endpoint."""

    @pytest.mark.data_access
    @pytest.mark.slow
    def test_lookup_number(self, api_session):
        # Lookup scans all draws for the state — can be slow
        payload = {"number": "1234", "state": "Florida", "game": ""}
        r = api_session.post(api_url("/api/lookup"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert "total_hits" in data
        assert "search_normalized" in data
        assert data["search_normalized"] == "1234"

    @pytest.mark.data_access
    def test_lookup_empty_number(self, api_session):
        payload = {"number": "", "state": "Florida"}
        r = api_session.post(api_url("/api/lookup"), json=payload, timeout=10)
        assert r.status_code == 400
        data = r.json()
        assert "error" in data


class TestTdLookup:
    """Verify Times Drawn lookup endpoint."""

    @pytest.mark.data_access
    def test_td_lookup(self, api_session):
        payload = {
            "candidates": ["1234", "5678", "0123"],
            "state": "Florida",
            "game_type": "pick4",
        }
        r = api_session.post(api_url("/api/td/lookup"), json=payload, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert "td" in data
        assert data["count"] == 3
        assert data["game_type"] == "pick4"

    @pytest.mark.data_access
    def test_td_lookup_empty(self, api_session):
        payload = {"candidates": [], "state": "Florida", "game_type": "pick4"}
        r = api_session.post(api_url("/api/td/lookup"), json=payload, timeout=10)
        assert r.status_code == 400


class TestConsecutive:
    """Verify consecutive draws endpoints."""

    @pytest.mark.data_access
    def test_consecutive_states(self, api_session):
        r = api_session.get(api_url("/api/consecutive/states?game_type=pick4"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.data_access
    def test_consecutive_debug_games(self, api_session):
        r = api_session.get(api_url("/api/consecutive/debug-games/Florida"))
        assert r.status_code == 200

    @pytest.mark.data_access
    @pytest.mark.slow
    def test_consecutive_draws(self, api_session):
        payload = {
            "game_type": "pick4",
            "states": ["Florida"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-07",
            "tod": "All",
        }
        r = api_session.post(api_url("/api/consecutive/draws"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        # Response should contain draw data
        assert isinstance(data, dict)
