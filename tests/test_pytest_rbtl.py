"""
RBTL Endpoint Tests — Data stats, backtest-v2, batch, live predictions, compare-dp.
====================================================================================
"""

import pytest
from conftest import api_url


class TestRbtlDataStats:
    """Verify RBTL data statistics endpoint."""

    @pytest.mark.rbtl
    @pytest.mark.parametrize("state,game_type", [
        ("Florida", "pick4"),
        ("Maryland", "pick4"),
        ("Virginia", "pick5"),
        ("Pennsylvania", "pick4"),
    ])
    def test_data_stats(self, api_session, state, game_type):
        r = api_session.get(api_url(f"/api/rbtl/data-stats/{state}/{game_type}"))
        assert r.status_code == 200
        data = r.json()
        assert data["total_draws"] > 0
        assert "first_draw_date" in data or "date_range" in data or "last_draw_date" in data


class TestRbtlAnalyze:
    """Verify RBTL analyze endpoint."""

    @pytest.mark.rbtl
    def test_analyze_basic(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "seed_values": ["9869", "5489"],
        }
        r = api_session.post(api_url("/api/rbtl/analyze"), json=payload, timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")


class TestRbtlBacktestV2:
    """Test the core backtest-v2 endpoint with various configurations."""

    @pytest.mark.rbtl
    def test_backtest_v2_shadow(self, api_session):
        """Shadow mode (lookback=-1) for Win #2 scenario."""
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "target_date": "2019-10-09",
            "target_tod": "midday",
            "lookback_days": -1,
            "min_count": 2,
            "dp_size": 0,
            "dp_seed_mode": "last",
            "suggested_limit": 999,
            "include_same_day": True,
            "look_forward_days": 0,
            "grouping": "monthly",
        }
        r = api_session.post(api_url("/api/rbtl/backtest-v2"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")
        assert "suggested_plays" in data
        assert "winner_results" in data
        assert len(data["suggested_plays"]) > 0

    @pytest.mark.rbtl
    def test_backtest_v2_sniper(self, api_session):
        """Sniper mode (lookback=5) for Win #1 scenario — no DP filter."""
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "target_date": "2019-09-15",
            "target_tod": "evening",
            "lookback_days": 5,
            "min_count": 3,
            "dp_size": 0,
            "dp_seed_mode": "last",
            "suggested_limit": 999,
            "include_same_day": True,
        }
        r = api_session.post(api_url("/api/rbtl/backtest-v2"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")
        assert "suggested_plays" in data
        assert len(data["suggested_plays"]) > 0
        # Win #1 (9869, norm 6899) should be found without DP filter
        found = any(
            wr.get("found_in_candidates")
            for wr in data.get("winner_results", [])
        )
        assert found, "Win #1 (9869) should be found in candidates"

    @pytest.mark.rbtl
    @pytest.mark.parametrize("grouping", ["monthly", "cluster_30", "cluster_60", "cluster_year"])
    def test_backtest_v2_groupings(self, api_session, grouping):
        """Test all grouping modes return valid results."""
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "target_date": "2019-10-09",
            "target_tod": "midday",
            "lookback_days": -1,
            "min_count": 2,
            "dp_size": 0,
            "grouping": grouping,
            "suggested_limit": 100,
        }
        r = api_session.post(api_url("/api/rbtl/backtest-v2"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")
        assert "suggested_plays" in data

    @pytest.mark.rbtl
    def test_backtest_v2_with_truth_table(self, api_session):
        """Test truth_table_seed parameter."""
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "target_date": "2019-10-09",
            "target_tod": "midday",
            "lookback_days": -1,
            "min_count": 2,
            "dp_size": 0,
            "grouping": "monthly",
            "truth_table_seed": "4426",
        }
        r = api_session.post(api_url("/api/rbtl/backtest-v2"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")


class TestRbtlBatchBacktest:
    """Test batch backtesting endpoint."""

    @pytest.mark.rbtl
    @pytest.mark.slow
    def test_batch_backtest(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "start_date": "2019-09-15",
            "end_date": "2019-09-17",
            "lookback_days": 5,
            "dp_size": 2,
            "min_count": 2,
        }
        r = api_session.post(api_url("/api/rbtl/backtest/batch"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")


class TestRbtlLivePredictions:
    """Test live predictions endpoint."""

    @pytest.mark.rbtl
    def test_live_predictions(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "lookback_days": 5,
            "dp_size": 2,
            "min_count": 2,
        }
        r = api_session.post(api_url("/api/rbtl/live-predictions"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")
        assert "suggested_plays" in data
        assert len(data["suggested_plays"]) > 0


class TestRbtlCompareDp:
    """Test DP comparison endpoint."""

    @pytest.mark.rbtl
    @pytest.mark.slow
    def test_compare_dp(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "start_date": "2019-09-15",
            "end_date": "2019-09-17",
            "lookback_days": 5,
        }
        r = api_session.post(api_url("/api/rbtl/compare-dp"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")
