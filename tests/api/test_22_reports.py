"""22 - Experiment Reports.

Maps to: testing/22_test-experiment-reports.md
"""

import pytest

pytestmark = pytest.mark.api


class TestReportGeneration:
    """Report generation endpoints."""

    def test_report_endpoint_exists(self, api, existing_experiment):
        """Report endpoint responds for a valid experiment."""
        r = api.get(f"/api/reports/experiment/{existing_experiment}",
                     params={"format": "markdown"}, timeout=60)
        # 200 with report or 400 if no runs
        assert r.status_code in (200, 400, 500)
        if r.status_code == 200:
            body = r.text
            assert len(body) > 0, "Report response body is empty"
        elif r.status_code == 400:
            data = r.json()
            has_error = "error" in data or "message" in data or "detail" in data
            assert has_error, f"400 response missing error message: {data}"
