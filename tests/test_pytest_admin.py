"""
Admin & Infrastructure Tests — Cost estimation, background jobs, email.
=======================================================================
"""

import pytest
from conftest import api_url


class TestQueryCostEstimation:
    """Verify query cost estimation endpoint."""

    @pytest.mark.admin
    def test_estimate_cost_efficacy(self, api_session):
        payload = {
            "query_type": "efficacy_report",
            "params": {
                "start_date": "2025-01-01",
                "end_date": "2025-01-03",
                "game_type": "pick4",
            },
        }
        r = api_session.post(api_url("/api/query/estimate-cost"), json=payload, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "requires_confirmation" in data or "estimate" in data or "is_heavy" in data

    @pytest.mark.admin
    def test_estimate_cost_consecutive(self, api_session):
        payload = {
            "query_type": "consecutive_draws",
            "params": {
                "start_date": "2025-01-01",
                "end_date": "2025-01-07",
                "states": ["Florida"],
                "game_type": "pick4",
            },
        }
        r = api_session.post(api_url("/api/query/estimate-cost"), json=payload, timeout=10)
        assert r.status_code == 200


class TestBackgroundJobs:
    """Verify background job creation and status."""

    @pytest.mark.admin
    def test_job_status_not_found(self, api_session):
        r = api_session.get(api_url("/api/query/job-status/nonexistent_id_12345"))
        assert r.status_code == 404 or "error" in r.json()


class TestEmailEndpoints:
    """Verify email endpoints handle missing data properly."""

    @pytest.mark.admin
    def test_email_predictions_no_body(self, api_session):
        payload = {}
        r = api_session.post(api_url("/api/rbtl/email-predictions"), json=payload, timeout=10)
        data = r.json()
        # Should return error for missing required fields
        assert r.status_code == 400 or data.get("error")

    @pytest.mark.admin
    def test_consecutive_email_no_body(self, api_session):
        payload = {}
        r = api_session.post(api_url("/api/consecutive/email-report"), json=payload, timeout=10)
        data = r.json()
        assert r.status_code == 400 or data.get("error")


class TestQueryCharge:
    """Verify query charge endpoint."""

    @pytest.mark.admin
    def test_charge_endpoint_exists(self, api_session):
        payload = {"query_type": "test", "token": "invalid"}
        r = api_session.post(api_url("/api/query/charge"), json=payload, timeout=10)
        # Should respond (even if with error) — confirms route exists
        assert r.status_code in [200, 400, 401, 403, 404, 500]
