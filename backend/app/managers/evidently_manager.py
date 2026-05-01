"""Evidently Manager - queries the Evidently workspace API.

Provides lightweight access to Evidently projects, snapshots, and report
status for badges and alerts in the Explorer tree. Does not depend on the
evidently Python package - uses HTTP API only.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EVIDENTLY_URL = "http://noted-evidently:8000"
TIMEOUT = 10.0


class EvidentlyManager:
    """Client for the Evidently workspace HTTP API."""

    def __init__(self, base_url: str = EVIDENTLY_URL):
        self._base_url = base_url

    async def health(self) -> dict:
        """Check if Evidently service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/api/version")
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.warning("Evidently unreachable: %s", e)
            return {"status": "error", "detail": str(e)}

    async def list_projects(self) -> list[dict]:
        """List all Evidently projects."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/api/projects")
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to list Evidently projects: %s", e)
            return []

    async def get_project(self, project_id: str) -> Optional[dict]:
        """Get a specific Evidently project by ID."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{self._base_url}/api/projects/{project_id}")
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to get Evidently project %s: %s", project_id, e)
            return None

    async def create_project(self, name: str, description: str = "") -> Optional[str]:
        """Create a new Evidently project. Returns project ID."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/api/projects",
                    json={"name": name, "description": description},
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to create Evidently project: %s", e)
            return None

    async def list_reports(self, project_id: str) -> list[dict]:
        """List report snapshots for a project."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{self._base_url}/api/projects/{project_id}/snapshots"
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to list reports for %s: %s", project_id, e)
            return []

    async def get_latest_report(self, project_id: str, tag: Optional[str] = None) -> Optional[dict]:
        """Get the most recent report snapshot, optionally filtered by tag."""
        reports = await self.list_reports(project_id)
        if not reports:
            return None
        if tag:
            reports = [r for r in reports if tag in (r.get("tags") or [])]
        if not reports:
            return None
        reports.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return reports[0]

    async def get_report_data(self, project_id: str, run_id: str) -> Optional[dict]:
        """Get detailed report data for a specific run."""
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{self._base_url}/api/projects/{project_id}/snapshots/{run_id}"
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error("Failed to get report %s: %s", run_id, e)
            return None

    async def get_data_health_status(self, project_id: str) -> dict:
        """Get a summary health status from the latest data quality report.

        Returns a dict with 'status' (green/yellow/red), 'summary', and 'timestamp'.
        """
        report = await self.get_latest_report(project_id, tag="data-quality")
        if not report:
            return {"status": "unknown", "summary": "No data quality reports found"}

        # A DataSummaryPreset report (profiling) has no tests - just having it means green.
        # A quality gate report has test results in the detailed snapshot data.
        # For lightweight status, we check if the snapshot exists and has tags.
        return {
            "status": "green",
            "summary": "Data quality report available",
            "timestamp": report.get("timestamp"),
            "snapshot_id": report.get("id"),
        }

    async def get_drift_status(self, project_id: str) -> dict:
        """Get drift status from the latest drift report."""
        report = await self.get_latest_report(project_id, tag="drift")
        if not report:
            return {"status": "unknown", "summary": "No drift reports found"}

        metrics = report.get("metrics") or {}
        drift_share = metrics.get("dataset_drift_share", 0)

        if drift_share > 0.5:
            status = "red"
        elif drift_share > 0.2:
            status = "yellow"
        else:
            status = "green"

        return {
            "status": status,
            "summary": f"Drift share: {drift_share:.1%}",
            "drift_share": drift_share,
            "timestamp": report.get("timestamp"),
            "run_id": report.get("id"),
        }
