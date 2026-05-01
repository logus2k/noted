"""Airflow pipeline API - DAG discovery, triggering, monitoring, and logs."""

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.managers.airflow_manager import AirflowManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/airflow", tags=["airflow"])
airflow_mgr = AirflowManager()
_sio = None  # Set by main.py after import


def set_sio(sio):
    """Register Socket.IO server for pipeline status events."""
    global _sio
    _sio = sio


async def _poll_run_status(dag_id: str, dag_run_id: str, poll_interval: int = 4, max_polls: int = 150):
    """Background task: poll Airflow run+task status and emit Socket.IO events."""
    terminal_states = {'success', 'failed', 'skipped', 'upstream_failed'}
    prev_task_states = {}
    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)
        try:
            state = airflow_mgr.get_run_state(dag_id, dag_run_id)
            # Get task-level updates
            tasks = []
            try:
                tasks = airflow_mgr.get_task_instances(dag_id, dag_run_id)
            except Exception:
                pass
            # Emit task updates for changed tasks
            for task in tasks:
                tid = task.get('task_id')
                tstate = task.get('state')
                if tid and tstate != prev_task_states.get(tid):
                    prev_task_states[tid] = tstate
                    if _sio:
                        await _sio.emit('pipeline:task_status', {
                            'dag_id': dag_id,
                            'dag_run_id': dag_run_id,
                            'task_id': tid,
                            'state': tstate,
                            'start_date': task.get('start_date'),
                            'end_date': task.get('end_date'),
                            'duration': task.get('duration'),
                        })
            # Emit run-level status
            if _sio:
                await _sio.emit('pipeline:status', {
                    'dag_id': dag_id,
                    'dag_run_id': dag_run_id,
                    'state': state,
                })
            if state in terminal_states:
                break
        except Exception as e:
            logger.warning('Poll run status failed: %s', e)
            break


class TriggerRequest(BaseModel):
    conf: dict | None = None
    logical_date: str | None = None


class ScheduleRequest(BaseModel):
    schedule: str | None = None


class SweepRequest(BaseModel):
    param_grid: dict
    base_conf: dict | None = None


class PauseRequest(BaseModel):
    is_paused: bool


@router.get("/health")
def airflow_health():
    """Check Airflow API connectivity."""
    return airflow_mgr.health()


@router.get("/dags")
def list_dags(tag: str | None = None):
    """List all DAGs, optionally filtered by tag."""
    try:
        return {"dags": airflow_mgr.list_dags(tag)}
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list DAGs")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}")
def get_dag(dag_id: str):
    """Get details for a specific DAG."""
    try:
        return airflow_mgr.get_dag(dag_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get DAG")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/tasks")
def get_dag_tasks(dag_id: str):
    """Get tasks for a DAG (for visualization)."""
    try:
        return {"tasks": airflow_mgr.get_dag_tasks(dag_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get DAG tasks")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/structure")
def get_dag_structure(dag_id: str):
    """Get DAG task dependency graph for visualization."""
    try:
        return airflow_mgr.get_dag_structure(dag_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get DAG structure")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/dags/{dag_id}/trigger")
async def trigger_dag(dag_id: str, body: TriggerRequest):
    """Trigger a DAG run and start background status polling."""
    try:
        result = airflow_mgr.trigger_dag(dag_id, body.conf, body.logical_date)
        # Start background polling for run status updates
        dag_run_id = result.get('dag_run_id')
        if dag_run_id:
            asyncio.create_task(_poll_run_status(dag_id, dag_run_id))
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to trigger DAG")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/runs")
def list_dag_runs(dag_id: str, limit: int = 20):
    """List recent DAG runs."""
    try:
        return {"runs": airflow_mgr.list_dag_runs(dag_id, limit)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to list DAG runs")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/runs/{dag_run_id}")
def get_dag_run(dag_id: str, dag_run_id: str):
    """Get details for a specific DAG run."""
    try:
        return airflow_mgr.get_dag_run(dag_id, dag_run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get DAG run")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.delete("/dags/{dag_id}/runs/{dag_run_id}")
def delete_dag_run(dag_id: str, dag_run_id: str):
    """Delete a specific DAG run."""
    try:
        airflow_mgr.delete_dag_run(dag_id, dag_run_id)
        return {"status": "deleted"}
    except Exception as e:
        logger.exception("Failed to delete DAG run")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.patch("/dags/{dag_id}/runs/{dag_run_id}/stop")
def stop_dag_run(dag_id: str, dag_run_id: str):
    """Stop a running DAG run by marking it as failed."""
    try:
        result = airflow_mgr.stop_dag_run(dag_id, dag_run_id)
        return {"status": "stopped", "state": result.get("state", "failed")}
    except Exception as e:
        logger.exception("Failed to stop DAG run")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/runs/{dag_run_id}/tasks")
def get_task_instances(dag_id: str, dag_run_id: str):
    """Get task instances for a DAG run."""
    try:
        return {"tasks": airflow_mgr.get_task_instances(dag_id, dag_run_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to get task instances")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.get("/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/logs")
def get_task_log(dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1):
    """Get log content for a specific task instance."""
    try:
        log = airflow_mgr.get_task_log(dag_id, dag_run_id, task_id, try_number)
        return {"log": log}
    except Exception as e:
        logger.exception("Failed to get task log")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/dags/{dag_id}/runs/{dag_run_id}/tasks/{task_id}/clear")
def clear_task_instance(dag_id: str, dag_run_id: str, task_id: str):
    """Clear a failed task instance so Airflow re-queues it."""
    try:
        result = airflow_mgr.clear_task_instance(dag_id, dag_run_id, task_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to clear task instance")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.patch("/dags/{dag_id}/pause")
def set_dag_paused(dag_id: str, body: PauseRequest):
    """Pause or unpause a DAG."""
    try:
        return airflow_mgr.set_dag_paused(dag_id, body.is_paused)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to pause/unpause DAG")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Schedule Management ───────────────────────────────────────

@router.get("/dags/{dag_id}/schedule")
def get_schedule(dag_id: str):
    """Get the current schedule variable for a DAG."""
    try:
        return airflow_mgr.get_schedule(dag_id)
    except Exception as e:
        logger.exception("Failed to get schedule")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.put("/dags/{dag_id}/schedule")
def set_schedule(dag_id: str, body: ScheduleRequest):
    """Set or clear the schedule for a DAG via Airflow Variable.

    The DAG must use Variable.get('{dag_id}_schedule') for this to take effect.
    Changes apply on the next DAG parse cycle (typically within 30 seconds).
    """
    try:
        return airflow_mgr.set_schedule(dag_id, body.schedule)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to set schedule")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── Sweep (Parameter Grid) ────────────────────────────────────

@router.post("/dags/{dag_id}/sweep")
async def sweep_dag(dag_id: str, body: SweepRequest):
    """Trigger multiple DAG runs for all combinations of parameter values.

    Example body:
    {
        "param_grid": {"model_type": ["GRU", "LSTM"], "learning_rate": [0.001, 0.0005]},
        "base_conf": {"epochs": 30}
    }
    This triggers 4 runs (2x2 combinations), each with a unique parameter set.
    """
    try:
        result = airflow_mgr.sweep(dag_id, body.param_grid, body.base_conf)
        # Start monitoring for each triggered run
        for run in result.get('runs', []):
            if 'dag_run_id' in run and 'error' not in run:
                asyncio.ensure_future(_poll_run_status(dag_id, run['dag_run_id']))
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Failed to submit sweep")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── DAG Templates ─────────────────────────────────────────────

class ValidateDagRequest(BaseModel):
    content: str


@router.post("/validate-dag")
def validate_dag(body: ValidateDagRequest):
    """Validate a DAG Python file for common issues."""
    warnings = []
    content = body.content

    # Check for DAG import
    if 'from airflow' not in content and 'import airflow' not in content:
        warnings.append({'level': 'error', 'message': 'Missing Airflow import (from airflow.decorators import dag, task)'})

    # Check for DAG definition
    if '@dag' not in content and 'DAG(' not in content:
        warnings.append({'level': 'error', 'message': 'No DAG definition found (@dag decorator or DAG() constructor)'})

    # Check for common pitfalls
    if 'datetime.now()' in content:
        warnings.append({'level': 'warning', 'message': 'datetime.now() in DAG file runs at parse time, not execution time. Use pendulum or templates.'})

    if 'Variable.get(' in content and 'from airflow.models import Variable' not in content:
        warnings.append({'level': 'warning', 'message': 'Variable.get() used but Variable not imported'})

    if 'top_level' not in content:
        # Check for heavy imports at module level
        heavy_imports = ['pandas', 'numpy', 'torch', 'tensorflow', 'sklearn']
        for lib in heavy_imports:
            if f'import {lib}' in content and f'import {lib}' in content.split('def ')[0]:
                warnings.append({'level': 'warning', 'message': f'"{lib}" imported at module level - move inside task for faster DAG parsing'})
                break

    # Try to compile for syntax errors
    try:
        compile(content, '<dag>', 'exec')
    except SyntaxError as e:
        warnings.append({'level': 'error', 'message': f'Syntax error at line {e.lineno}: {e.msg}'})

    if not warnings:
        warnings.append({'level': 'ok', 'message': 'DAG validation passed'})

    return {'warnings': warnings}


class CreateDagRequest(BaseModel):
    project_id: str
    template: str       # blank, training, data, parallel
    dag_id: str


@router.get("/templates")
def list_dag_templates():
    """List available DAG templates."""
    from app.managers.dag_templates import list_templates
    return {'templates': list_templates()}


@router.post("/dags/create-from-template")
def create_dag_from_template(body: CreateDagRequest):
    """Create a new DAG file from a template in the project's dags/ directory."""
    import os
    from app.config import PROJECTS_DIR, MOUNTS_DIR
    from app.managers.dag_templates import render_template

    try:
        filename, content = render_template(body.template, body.dag_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Resolve project path
    from app.managers.project_registry import get_registry
    try:
        base = get_registry().resolve(body.project_id)
    except FileNotFoundError:
        base = None

    if not base or not os.path.isdir(base):
        raise HTTPException(status_code=404, detail=f"Project not found: {body.project_id}")

    dags_dir = os.path.join(base, 'dags')
    os.makedirs(dags_dir, exist_ok=True)

    filepath = os.path.join(dags_dir, filename)
    if os.path.exists(filepath):
        raise HTTPException(status_code=409, detail=f"File already exists: dags/{filename}")

    with open(filepath, 'w') as f:
        f.write(content)

    return {'created': True, 'path': f'dags/{filename}', 'dag_id': body.dag_id}
