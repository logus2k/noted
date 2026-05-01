"""Idempotent state-staging primitives.

Each fixture verifies current state and mutates only if needed. Fixtures raise
FixtureError on unrecoverable failure; the harness converts those to an ERROR
verdict (D8) and skips the scenario's chat + judge calls.

MVP set (for the 4 pilot docs):
  - unload_model()
  - deploy_model(model_name, version=None, alias=None)
  - set_context(...)               (pure; builds the context_descriptor dict)

Additional fixtures land in M3 / M4 as new scenarios need them.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests


NOTED_BASE_URL = os.environ.get("NOTED_BASE_URL", "http://localhost:8123")


class FixtureError(RuntimeError):
    """Raised when a fixture cannot achieve the required state after retries."""

    def __init__(self, fixture_name: str, detail: str):
        super().__init__(f"{fixture_name}: {detail}")
        self.fixture_name = fixture_name
        self.detail = detail


@dataclass
class FixtureResult:
    fixture: str
    action: str  # "created" | "verified" | "skipped"
    detail: str


# ── Low-level serving calls ──────────────────────────────────────────

def _get_serving_health(timeout: float = 10.0) -> dict:
    try:
        r = requests.get(f"{NOTED_BASE_URL}/api/serving/health", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise FixtureError("serving_health", f"unreachable: {e}")


# ── Fixtures ─────────────────────────────────────────────────────────

def unload_model() -> FixtureResult:
    """Ensure the serving container is idle. No-op if already idle."""
    health = _get_serving_health()
    status = health.get("status", "idle")
    if status in ("idle", None) or not health.get("model_name"):
        return FixtureResult("unload_model", "verified", "serving already idle")
    try:
        r = requests.post(f"{NOTED_BASE_URL}/api/serving/unload", timeout=30.0)
        r.raise_for_status()
    except requests.RequestException as e:
        raise FixtureError("unload_model", f"POST /api/serving/unload failed: {e}")
    return FixtureResult("unload_model", "created", f"unloaded previous model ({health.get('model_name')})")


def deploy_model(model_name: str, version: Optional[str] = None, alias: Optional[str] = None) -> FixtureResult:
    """Ensure the requested model is loaded into serving. Idempotent if
    already loaded with the same (name, version/alias) tuple."""
    if not version and not alias:
        raise FixtureError("deploy_model", "must provide either version or alias")

    health = _get_serving_health()
    already_match = (
        health.get("status") == "ready"
        and health.get("model_name") == model_name
        and (
            (version and str(health.get("version")) == str(version))
            or (alias and health.get("alias") == alias)
        )
    )
    if already_match:
        return FixtureResult(
            "deploy_model",
            "verified",
            f"{model_name} v{health.get('version')} @{health.get('alias') or ''} already loaded",
        )

    body = {"model_name": model_name}
    if version is not None:
        body["version"] = str(version)
    if alias is not None:
        body["alias"] = alias

    # /api/serving/load is an NDJSON stream; consume until terminal event
    try:
        with requests.post(
            f"{NOTED_BASE_URL}/api/serving/load",
            json=body,
            stream=True,
            timeout=(10.0, 300.0),
        ) as r:
            if r.status_code >= 400:
                raise FixtureError(
                    "deploy_model",
                    f"POST /api/serving/load returned HTTP {r.status_code}: {r.text[:300]}",
                )
            terminal = None
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace").strip()
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                phase = ev.get("phase")
                if phase in ("ready", "error"):
                    terminal = ev
                    break
    except requests.RequestException as e:
        raise FixtureError("deploy_model", f"POST /api/serving/load failed: {e}")

    if terminal is None:
        raise FixtureError("deploy_model", "stream ended without a terminal event")
    if terminal.get("phase") == "error":
        raise FixtureError("deploy_model", f"deploy failed: {terminal.get('error')}")

    result = terminal.get("result") or {}
    detail = (
        f"loaded {result.get('model_name', model_name)}"
        f" v{result.get('version', '?')}"
        + (f" @{result.get('alias')}" if result.get("alias") else "")
    )
    return FixtureResult("deploy_model", "created", detail)


def set_context(
    project: str,
    notebook: Optional[str] = None,
    active_run_id: Optional[str] = None,
    selected_cell_indices: Optional[list[int]] = None,
) -> dict:
    """Pure function: returns a context_descriptor dict for the chat request.
    Does not mutate any state."""
    ctx: dict = {"project_id": project}
    if notebook:
        ctx["notebook_path"] = notebook
    if active_run_id:
        ctx["active_run_id"] = active_run_id
    if selected_cell_indices:
        ctx["selected_cell_indices"] = list(selected_cell_indices)
    return ctx


# ── Registry ─────────────────────────────────────────────────────────


_LINT_SAMPLE_DIRTY = """import os
import sys
import json  # unused
from typing import List

def process(data):
    unused_var = 42  # F841
    result = []
    for item in data:
        result.append(item*2)
    return result
def very_long_line_that_will_trigger_E501_because_it_goes_on_and_on_and_on_past_the_configured_line_length_limit_forever(x):
    return x
"""


def reset_lint_fixture(
    project: str = "noted-testing",
    file_path: str = "sample_lint.py",
) -> FixtureResult:
    """Restore the sample_lint.py fixture to its canonical 'dirty' state
    (contains F401/F841/E501/I001/UP035 issues). Needed before scenarios that
    test fix_lint_issues / get_lint_diagnostics so the tool has real issues
    to report after prior tests may have auto-fixed the file."""
    # Harness runs inside the noted container where projects live under
    # /app/data/projects/<project>/ (bind-mounted from host data/projects/).
    PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/app/data/projects")
    target = os.path.join(PROJECTS_DIR, project, file_path)
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(_LINT_SAMPLE_DIRTY)
        return FixtureResult(action="reset", fixture="reset_lint_fixture", detail=f"restored {file_path} in {project}")
    except Exception as e:
        raise FixtureError("reset_lint_fixture", f"failed to reset: {e}")


_PIPELINE_CANONICAL = '''"""Training pipeline placeholder for assistant test scenarios."""


class TrainingPipeline:
    """Minimal training pipeline used by tests that need a class to find."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def fit(self, X, y):
        return self

    def predict(self, X):
        return X
'''


def reset_pipeline_fixture(
    project: str = "noted-testing",
    file_path: str = "src/training/pipeline.py",
) -> FixtureResult:
    """Restore src/training/pipeline.py to its canonical minimal form.
    Needed before update_file::S2 (and any scenario that mutates this file),
    because successful update_file calls accumulate edits across runs and
    cause judge to see stale content on subsequent runs."""
    PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/app/data/projects")
    target = os.path.join(PROJECTS_DIR, project, file_path)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(_PIPELINE_CANONICAL)
        return FixtureResult(action="reset", fixture="reset_pipeline_fixture", detail=f"restored {file_path} in {project}")
    except Exception as e:
        raise FixtureError("reset_pipeline_fixture", f"failed to reset: {e}")


_REGISTRY = {
    "unload_model": unload_model,
    "deploy_model": deploy_model,
    "reset_lint_fixture": reset_lint_fixture,
    "reset_pipeline_fixture": reset_pipeline_fixture,
}


def apply_prerequisites(prerequisites) -> list[FixtureResult]:
    """Run each declared prerequisite in order. Raises FixtureError on any failure."""
    results: list[FixtureResult] = []
    for p in prerequisites:
        fn = _REGISTRY.get(p.fixture)
        if fn is None:
            raise FixtureError(p.fixture, f"unknown fixture (not in M1 registry)")
        results.append(fn(**p.args))
    return results
