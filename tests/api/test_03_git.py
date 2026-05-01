"""03 - Git Operations.

Maps to: testing/03_test-git.md
"""

import pytest

pytestmark = pytest.mark.api

REPO_PATH = "/app/data/projects/noted-testing"


class TestGitStatus:
    """Test 1: Git status for the project."""

    def test_repo_initialized(self, api):
        """noted-testing has git initialized."""
        r = api.post("/api/git/repo/status", json={"repo_path": REPO_PATH})
        assert r.status_code == 200
        data = r.json()
        assert data.get("initialized") is True

    def test_repo_has_branch(self, api):
        """Repo has a non-empty branch name (proves git is working)."""
        r = api.post("/api/git/repo/status", json={"repo_path": REPO_PATH})
        data = r.json()
        branch = data.get("branch")
        assert branch is not None, "branch must be present in git status"
        assert len(branch) > 0, "branch name must be non-empty"


class TestGitCommit:
    """Tests 2-3: Commit operations."""

    def test_commit_new_file(self, api, temp_file):
        """Create a file, commit it, verify in log."""
        path = temp_file("_test_git_commit.txt", "git test content")

        r = api.post("/api/git/repo/commit", json={
            "repo_path": REPO_PATH,
            "message": "test: automated git commit test",
            "files": [path],
        })
        assert r.status_code == 200

        # Check log
        r2 = api.post("/api/git/repo/log", json={"repo_path": REPO_PATH})
        assert r2.status_code == 200
        commits = r2.json().get("commits", r2.json())
        assert any("automated git commit test" in c.get("message", "") for c in commits)


class TestGitBranches:
    """Test 4: Branch operations."""

    def test_list_branches(self, api):
        """Branch listing returns at least one branch including main or master."""
        r = api.post("/api/git/repo/branches", json={"repo_path": REPO_PATH})
        assert r.status_code == 200
        data = r.json()
        branches = data.get("branches", [])
        assert len(branches) >= 1, "Expected at least one branch"
        assert "main" in branches or "master" in branches, (
            f"Expected 'main' or 'master' in branches, got: {branches}"
        )

    def test_create_and_delete_branch(self, api, unique_name):
        """Create a test branch and switch back."""
        branch_name = f"_test_br_{unique_name}"
        r0 = api.post("/api/git/repo/status", json={"repo_path": REPO_PATH})
        current = r0.json().get("branch", "master")

        r = api.post("/api/git/repo/create-branch", json={
            "repo_path": REPO_PATH,
            "branch": branch_name,
        })
        assert r.status_code == 200

        r2 = api.post("/api/git/repo/branches", json={"repo_path": REPO_PATH})
        branches = r2.json().get("branches", [])
        assert branch_name in branches

        # Switch back
        api.post("/api/git/repo/checkout", json={
            "repo_path": REPO_PATH,
            "branch": current,
        })


class TestGitTags:
    """Test 5: Tag operations."""

    def test_create_and_list_tag(self, api, unique_name):
        """Create a tag and verify it appears."""
        tag_name = f"_test_tag_{unique_name}"
        r = api.post("/api/git/repo/create-tag", json={
            "repo_path": REPO_PATH,
            "tag": tag_name,
            "message": "test tag",
        })
        assert r.status_code == 200

        r2 = api.post("/api/git/repo/tags", json={"repo_path": REPO_PATH})
        assert r2.status_code == 200
        tags = r2.json().get("tags", r2.json())
        tag_names = [t.get("name", t) if isinstance(t, dict) else t for t in tags]
        assert tag_name in tag_names

        # Cleanup
        api.post("/api/git/repo/delete-tag", json={
            "repo_path": REPO_PATH,
            "tag": tag_name,
        })
