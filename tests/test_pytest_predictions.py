"""
Prediction Endpoint Tests — 2DP-AP, 3DP-AP, Unified, Efficacy.
===============================================================
"""

import pytest
from conftest import api_url


class Test2DpAp:
    """Test 2-Digit Pair All Pairs prediction endpoint."""

    @pytest.mark.prediction
    def test_2dp_ap_basic(self, api_session):
        payload = {
            "seed_number": "9869",
            "seed_date": "2019-09-15",
            "state": "Florida",
            "game_type": "pick4",
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/2dp-ap"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert "predictions" in data or "pairs_2dp" in data or "candidates" in data
        # Should have some results
        assert not data.get("error")

    @pytest.mark.prediction
    def test_2dp_ap_maryland(self, api_session):
        payload = {
            "seed_number": "4567",
            "seed_date": "2025-01-15",
            "state": "Maryland",
            "game_type": "pick4",
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/2dp-ap"), json=payload, timeout=120)
        assert r.status_code == 200
        assert not r.json().get("error")

    @pytest.mark.prediction
    def test_2dp_ap_missing_seed(self, api_session):
        payload = {"seed_number": "", "seed_date": "2019-09-15", "state": "Florida", "game_type": "pick4"}
        r = api_session.post(api_url("/api/prediction/2dp-ap"), json=payload, timeout=10)
        # Should return error (400 or error in json)
        data = r.json()
        assert r.status_code == 400 or data.get("error")


class Test3DpAp:
    """Test 3-Digit Pair prediction endpoint for Pick 5."""

    @pytest.mark.prediction
    def test_3dp_ap_basic(self, api_session):
        payload = {
            "seed_number": "12345",
            "seed_date": "2025-01-15",
            "state": "Florida",
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/3dp-ap"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")

    @pytest.mark.prediction
    def test_3dp_ap_virginia(self, api_session):
        payload = {
            "seed_number": "67890",
            "seed_date": "2025-01-15",
            "state": "Virginia",
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/3dp-ap"), json=payload, timeout=120)
        assert r.status_code == 200
        assert not r.json().get("error")


class TestUnifiedDpAp:
    """Test unified DP-AP endpoint across game types."""

    @pytest.mark.prediction
    @pytest.mark.parametrize("game_type,seed,pair_size", [
        ("pick3", "123", 2),
        ("pick4", "1234", 2),
        ("pick4", "1234", 3),
        ("pick5", "12345", 3),
    ])
    def test_unified_dp_ap(self, api_session, game_type, seed, pair_size):
        payload = {
            "state": "Florida",
            "game_type": game_type,
            "seed_number": seed,
            "seed_date": "2025-01-15",
            "pair_size": pair_size,
            "days_threshold": 30,
        }
        r = api_session.post(api_url("/api/prediction/unified-dp-ap"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")

    @pytest.mark.prediction
    def test_unified_dp_ap_missing_state(self, api_session):
        payload = {
            "state": "",
            "game_type": "pick4",
            "seed_number": "1234",
            "seed_date": "2025-01-15",
            "pair_size": 2,
        }
        r = api_session.post(api_url("/api/prediction/unified-dp-ap"), json=payload, timeout=30)
        data = r.json()
        # Should either 400 or return error in json
        assert r.status_code == 400 or data.get("error")


class TestEfficacyReport:
    """Test efficacy report endpoints."""

    @pytest.mark.prediction
    @pytest.mark.slow
    def test_efficacy_report_basic(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "start_date": "2025-01-01",
            "end_date": "2025-01-03",
            "days_threshold": 30,
            "hit_window": 10,
            "pair_size": 2,
        }
        r = api_session.post(api_url("/api/prediction/efficacy-report"), json=payload, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert not data.get("error")

    @pytest.mark.prediction
    @pytest.mark.slow
    def test_efficacy_report_all_states(self, api_session):
        payload = {
            "state": "Florida",
            "game_type": "pick4",
            "start_date": "2025-01-01",
            "end_date": "2025-01-02",
            "pair_size": 2,
        }
        r = api_session.post(api_url("/api/prediction/efficacy-report-all-states"), json=payload, timeout=120)
        assert r.status_code == 200

    @pytest.mark.prediction
    def test_dp_options_pick4(self, api_session):
        r = api_session.get(api_url("/api/prediction/dp-options/pick4"))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.prediction
    def test_dp_options_pick5(self, api_session):
        r = api_session.get(api_url("/api/prediction/dp-options/pick5"))
        assert r.status_code == 200
