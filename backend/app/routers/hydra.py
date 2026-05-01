"""Hydra configuration API - config schema, composition, and group browsing."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.managers.hydra_manager import HydraManager
from app.managers.hydra_source import MlflowSource
from app.managers.hydra_cache import get_cache
from app.managers.mlflow_manager import MlflowManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hydra", tags=["hydra"])
hydra_mgr = HydraManager()
mlflow_mgr = MlflowManager()


class ComposeRequest(BaseModel):
    project_id: str
    overrides: dict | None = None
    group_selections: dict | None = None


class TemplateRequest(BaseModel):
    name: str
    description: str = ''
    group_selections: dict | None = None
    overrides: dict | None = None


@router.get("/schema/{project_id}")
def get_config_schema(
    project_id: str,
    baseline_source: str | None = None,
    notebook_uid: str | None = None,
):
    """Get the Hydra config structure for a project.

    When `baseline_source` is provided, resolve the schema through that
    source (LocalSource for `project://...`, MlflowSource for `mlflow://...`).
    Without `baseline_source`, defaults to LocalSource(project_id) - the
    current local `config/` folder.

    Used by the notebook bar's baseline badge to detect reachability:
    if the notebook points at a pinned MLflow baseline that no longer
    exists, this endpoint returns 404 with a clear detail message, and
    the frontend renders the red error state on the badge.
    """
    try:
        if baseline_source and baseline_source != 'project://config/':
            from app.managers.hydra_source import parse_source
            try:
                source = parse_source(
                    baseline_source,
                    project_id=project_id,
                    notebook_uid=notebook_uid,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            # For MlflowSource, force-fetch the bundle so missing/unreachable
            # sources fail loud here instead of silently returning has_config=False.
            if baseline_source.startswith('mlflow://'):
                from app.managers.hydra_cache import get_cache
                run_id = baseline_source[len('mlflow://'):].strip('/')
                if not notebook_uid:
                    raise HTTPException(
                        status_code=400,
                        detail="notebook_uid is required when using an MLflow baseline source",
                    )
                try:
                    get_cache().fetch_from_mlflow(notebook_uid, run_id)
                except RuntimeError as e:
                    raise HTTPException(status_code=404, detail=str(e))
            return hydra_mgr.get_schema_from_source(source)
        return hydra_mgr.get_schema(project_id)
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get config schema")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/compose")
def compose_config(body: ComposeRequest):
    """Compose a resolved Hydra config with optional overrides and group selections."""
    try:
        return hydra_mgr.compose(body.project_id, body.overrides, body.group_selections)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to compose config")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/group/{project_id}/{group}/{option}")
def get_group_config(project_id: str, group: str, option: str):
    """Get the content of a specific config group option."""
    try:
        return hydra_mgr.get_group_config(project_id, group, option)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get group config")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Config Templates ──────────────────────────────────────────

@router.get("/templates/{project_id}")
def list_templates(project_id: str):
    """List all saved config templates for a project."""
    try:
        return {'templates': hydra_mgr.list_templates(project_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/templates/{project_id}")
def save_template(project_id: str, body: TemplateRequest):
    """Save a config template."""
    try:
        return hydra_mgr.save_template(
            project_id, body.name, body.description,
            body.group_selections, body.overrides)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/templates/{project_id}/{name}")
def get_template(project_id: str, name: str):
    """Load a specific config template."""
    try:
        return hydra_mgr.get_template(project_id, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/templates/{project_id}/{name}")
def delete_template(project_id: str, name: str):
    """Delete a config template."""
    try:
        return hydra_mgr.delete_template(project_id, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Hydra View Setting ───────────────────────────────────────

@router.get("/view/{project_id}")
def get_hydra_view(project_id: str):
    """Get whether Hydra view is enabled for a project."""
    try:
        return hydra_mgr.get_hydra_view(project_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


class HydraViewRequest(BaseModel):
    enabled: bool


@router.put("/view/{project_id}")
def set_hydra_view(project_id: str, body: HydraViewRequest):
    """Enable or disable Hydra view for a project."""
    try:
        return hydra_mgr.set_hydra_view(project_id, body.enabled)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Composer Time Machine (M3/M4) ─────────────────────────────

def _run_has_hydra_bundle(run_id: str) -> bool:
    """Return True if an MLflow run has a `hydra/` artifact folder."""
    try:
        items = mlflow_mgr.list_artifacts(run_id, "")
        return any(it.get("is_dir") and it.get("path") == "hydra" for it in items)
    except Exception:
        return False


@router.get("/experiments/{project_id}")
def list_hydra_experiments(project_id: str):
    """List MLflow experiments tagged with the given project that have
    at least one run with a `hydra/` artifact bundle.

    Used by the Composer's Experiment Run mode dropdown.
    """
    try:
        experiments = mlflow_mgr.list_experiments()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach MLflow: {e}",
        )

    result = []
    for exp in experiments:
        exp_id = exp["experiment_id"]
        try:
            runs = mlflow_mgr.list_runs(exp_id, max_results=50)
        except Exception:
            continue

        # Filter to runs tagged with this project
        project_runs = [
            r for r in runs
            if r.get("tags", {}).get("noted.project_id") == project_id
            or r.get("tags", {}).get("project_id") == project_id
        ]
        if not project_runs:
            # Also accept experiments whose name matches the project (older runs
            # may not carry the tag). Be generous here - the run-level filter
            # in /runs/ will still only return bundled runs.
            if project_id.lower() not in exp["name"].lower():
                continue
            project_runs = runs

        # Check at least one of these runs has a hydra/ bundle
        has_bundle = False
        for r in project_runs[:20]:
            if _run_has_hydra_bundle(r["run_id"]):
                has_bundle = True
                break
        if has_bundle:
            result.append({
                "experiment_id": exp_id,
                "name": exp["name"],
            })
    return {"experiments": result}


@router.get("/runs/{project_id}/{experiment_id}")
def list_hydra_runs(project_id: str, experiment_id: str):
    """List runs from an experiment that have a `hydra/` artifact bundle
    and belong to the current project.
    """
    try:
        runs = mlflow_mgr.list_runs(experiment_id, max_results=200)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach MLflow: {e}",
        )

    result = []
    for r in runs:
        tags = r.get("tags", {})
        # Filter by project (generous - accept by tag OR no tag)
        tagged_project = tags.get("noted.project_id") or tags.get("project_id")
        if tagged_project and tagged_project != project_id:
            continue
        if not _run_has_hydra_bundle(r["run_id"]):
            continue
        result.append({
            "run_id": r["run_id"],
            "run_name": r.get("run_name") or r["run_id"][:8],
            "status": r.get("status"),
            "start_time": r.get("start_time"),
            "hydra_config_hash": tags.get("noted.hydra_config_hash", ""),
        })
    return {"runs": result}


class LoadBundleRequest(BaseModel):
    run_id: str
    notebook_uid: str


class ComposeFromMlflowRequest(BaseModel):
    run_id: str
    notebook_uid: str
    group_selections: dict | None = None
    overrides: dict | None = None


@router.post("/compose-mlflow")
def compose_from_mlflow(body: ComposeFromMlflowRequest):
    """Compose a Hydra config against a cached MLflow baseline, allowing
    the caller to override group_selections and individual keys.

    Used by the Composer's Experiment Run mode preview, so users can
    tweak an archived baseline and see the recomposed YAML live.
    """
    try:
        source = MlflowSource(run_id=body.run_id, notebook_uid=body.notebook_uid)
        if not source.exists():
            # Cache miss - force a fetch
            get_cache().fetch_from_mlflow(body.notebook_uid, body.run_id)
        result = hydra_mgr.compose_from_source(
            source,
            overrides=body.overrides,
            group_selections=body.group_selections,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("compose-mlflow failed")
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__}: {e}"
        )


@router.post("/load-bundle")
def load_bundle(body: LoadBundleRequest):
    """Fetch a past run's `hydra/` bundle into the in-memory cache and
    return the schema + saved selections + resolved YAML.

    Per D17, this also runs composition validation: the recomposed hash
    should match the archived resolved.yaml hash, otherwise an error is
    surfaced.
    """
    cache = get_cache()
    try:
        cache.fetch_from_mlflow(body.notebook_uid, body.run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    source = MlflowSource(run_id=body.run_id, notebook_uid=body.notebook_uid)

    # Look up the run's experiment so the frontend can restore the
    # Experiment dropdown selection after mode toggles.
    experiment_id = ""
    try:
        run_info = mlflow_mgr.get_run(body.run_id)
        experiment_id = run_info.get("experiment_id", "") or ""
    except Exception as e:
        logger.warning(
            "Could not fetch run %s metadata for experiment_id: %s",
            body.run_id, e,
        )

    # Read the archived selections.json and resolved.yaml directly from the
    # cache (not via source.read_text - those live outside config_top).
    bundle = cache.get(body.notebook_uid, body.run_id) or {}

    import json as _json
    saved_selections = {"group_selections": {}, "overrides": {}}
    sel_bytes = bundle.get("selections.json")
    if sel_bytes:
        try:
            saved_selections = _json.loads(sel_bytes.decode("utf-8"))
        except Exception as e:
            logger.warning("selections.json parse failed for run %s: %s",
                           body.run_id, e)

    archived_resolved_yaml = ""
    res_bytes = bundle.get("resolved.yaml")
    if res_bytes:
        archived_resolved_yaml = res_bytes.decode("utf-8", errors="replace")

    # Get schema from the archived config
    schema = hydra_mgr.get_schema_from_source(source)

    # Recompose with the archived selections and verify hash match (D17)
    validation = {"ok": True, "expected_hash": "", "actual_hash": ""}
    try:
        composed = hydra_mgr.compose_from_source(
            source,
            overrides=saved_selections.get("overrides") or None,
            group_selections=saved_selections.get("group_selections") or None,
        )
        actual_hash = composed.get("hash", "")
        import hashlib
        expected_hash_raw = hashlib.sha256(
            archived_resolved_yaml.encode("utf-8")
        ).hexdigest()
        expected_hash = f"sha256:{expected_hash_raw}"
        validation["expected_hash"] = expected_hash
        validation["actual_hash"] = actual_hash
        validation["ok"] = (actual_hash == expected_hash)
        if not validation["ok"]:
            logger.warning(
                "Hydra bundle hash mismatch on load: run=%s expected=%s got=%s",
                body.run_id, expected_hash, actual_hash,
            )
    except Exception as e:
        validation["ok"] = False
        validation["error"] = str(e)
        composed = {"resolved": {}, "yaml": "", "hash": ""}

    return {
        "run_id": body.run_id,
        "experiment_id": experiment_id,
        "notebook_uid": body.notebook_uid,
        "schema": schema,
        "saved_selections": saved_selections,
        "archived_resolved_yaml": archived_resolved_yaml,
        "recomposed": composed,
        "validation": validation,
    }


