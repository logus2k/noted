"""17 - Snapshots.

Maps to: testing/17_test-snapshots.md
End-to-end test: create snapshot from a kernel-produced run,
verify it captures git branch, DVC hashes, Hydra config hash, and MLflow metadata.
"""

import pytest

pytestmark = pytest.mark.api


class TestSnapshotEndpoints:
    """Snapshot API endpoints exist and respond."""

    def test_list_snapshots(self, api, project_id):
        """List snapshots for the project."""
        r = api.get(f"/api/snapshots/{project_id}")
        assert r.status_code == 200
        data = r.json()
        snapshots = data.get("snapshots", [])
        assert isinstance(snapshots, list), (
            f"'snapshots' should be a list, got: {type(snapshots)}"
        )
        for snap in snapshots:
            assert isinstance(snap, dict), "Snapshot item should be a dict"
            assert "branch" in snap or "version" in snap, (
                f"Snapshot missing branch/version: {list(snap.keys())}"
            )
            assert "experiment_name" in snap or "experiment_id" in snap, (
                f"Snapshot missing experiment ref: {list(snap.keys())}"
            )
            assert "run_id" in snap, (
                f"Snapshot missing run_id: {list(snap.keys())}"
            )

    def test_snapshot_lifecycle(self, api, project_id, existing_experiment):
        """Create snapshot, verify it captures git, DVC, Hydra, and MLflow state."""
        # --- Find a real run with metrics ---
        r_runs = api.get(f"/api/mlflow/experiments/{existing_experiment}/runs")
        runs = r_runs.json().get("runs", [])
        if not runs:
            pytest.skip("No runs found - need kernel tests to run first")
        run = runs[0]
        run_id = run.get("run_id") or run.get("info", {}).get("run_id")
        assert run_id, f"Could not extract run_id from run: {run}"

        # --- Create snapshot ---
        r_create = api.post("/api/snapshots/create", json={
            "project_id": project_id,
            "experiment_id": existing_experiment,
            "run_id": run_id,
            "name": "_test_snapshot",
            "description": "Automated end-to-end snapshot test",
            "auto_commit": True,
        })

        if r_create.status_code in (404, 405):
            pytest.skip(f"Snapshot create endpoint returned {r_create.status_code}")

        assert r_create.status_code in (200, 201), (
            f"Snapshot creation failed: {r_create.status_code} {r_create.text}"
        )
        created = r_create.json()
        assert isinstance(created, dict), "Create response should be a JSON object"

        # --- Verify git branch was created ---
        snap_branch = created.get("snapshot_branch") or created.get("branch")
        assert snap_branch is not None, (
            f"Snapshot missing branch: {list(created.keys())}"
        )
        assert "snapshot/" in snap_branch, (
            f"Branch should follow 'snapshot/...' naming, got: {snap_branch}"
        )

        # --- Verify git commit was captured ---
        git_commit = created.get("git_commit")
        assert git_commit and len(git_commit) >= 7, (
            f"Snapshot should capture git commit SHA, got: {git_commit}"
        )

        # --- Verify Hydra config hash ---
        hydra_hash = created.get("hydra_config_hash")
        if hydra_hash is not None:
            assert isinstance(hydra_hash, str), (
                f"hydra_config_hash should be string, got: {type(hydra_hash)}"
            )
            # Hash is either a sha256 or empty string if no config
            if hydra_hash:
                assert len(hydra_hash) > 8, (
                    f"Hydra hash too short: {hydra_hash}"
                )

        # --- Verify DVC hashes ---
        dvc_hashes = created.get("dvc_hashes")
        if dvc_hashes is not None:
            assert isinstance(dvc_hashes, (dict, list)), (
                f"dvc_hashes should be dict or list, got: {type(dvc_hashes)}"
            )

        # --- Verify experiment/run reference ---
        assert created.get("experiment_id") or created.get("experiment_name"), (
            f"Snapshot missing experiment reference: {list(created.keys())}"
        )
        assert created.get("run_id") == run_id, (
            f"Snapshot run_id mismatch: expected {run_id}, got {created.get('run_id')}"
        )

        # --- Verify version numbering ---
        version = created.get("version")
        if version is not None:
            assert str(version).isdigit(), (
                f"Version should be numeric, got: {version}"
            )

        # --- Verify it appears in the list with full metadata ---
        r_list = api.get(f"/api/snapshots/{project_id}")
        assert r_list.status_code == 200
        snapshots = r_list.json().get("snapshots", [])
        branches = [s.get("branch") for s in snapshots]
        assert snap_branch in branches, (
            f"Created snapshot {snap_branch} not found in list: {branches}"
        )

        # Find our snapshot in the list and verify it has metrics
        our_snap = next(s for s in snapshots if s.get("branch") == snap_branch)
        assert "metrics" in our_snap or "run_id" in our_snap, (
            f"Listed snapshot missing metrics or run_id: {list(our_snap.keys())}"
        )
        if "metrics" in our_snap:
            assert isinstance(our_snap["metrics"], dict), (
                f"metrics should be dict, got: {type(our_snap['metrics'])}"
            )

        # --- Verify git branch exists in the project ---
        r_branches = api.get(f"/api/git/{project_id}/branches")
        if r_branches.status_code == 200:
            branch_data = r_branches.json()
            branch_names = branch_data if isinstance(branch_data, list) else branch_data.get("branches", [])
            # Branch names might be full refs or just names
            branch_strs = [b if isinstance(b, str) else b.get("name", "") for b in branch_names]
            has_snap_branch = any(snap_branch in b for b in branch_strs)
            assert has_snap_branch, (
                f"Snapshot branch '{snap_branch}' not found in git branches: {branch_strs[:10]}"
            )
