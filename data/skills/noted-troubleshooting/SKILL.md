---
name: noted-troubleshooting
description: Common errors, connectivity issues, and service health in noted. Use when user reports something not working, a service is unreachable, kernel won't start, container is down, or needs help diagnosing a platform issue.
triggers: [workspace_active]
priority: 1
max_tokens: 400
---
Common issues and fixes in noted:

SERVICES NOT REACHABLE:
- MLflow (port 5000): check docker logs noted-mlflow
- Airflow (API port 8080): check scheduler + worker logs
- MinIO (port 9000): check docker logs noted-minio
- Knowledge Graph (port 5523): check docker logs noted-graph
- Agent Server (port 7701): check docker logs agent_server

NOTEBOOK KERNEL ISSUES:
- Kernel not starting: check venv exists and has ipykernel installed.
- Module not found: package not in active venv. Install via terminal.
- Kernel dies silently: likely OOM. Check system memory.

AIRFLOW ISSUES:
- DAG not appearing: check DAG processor logs for parse errors.
- Run stuck in queued: DAG may be paused. Unpause it.
- Task fails with ImportError: package not in worker container.

DVC ISSUES:
- Push/pull fails: check MinIO is running and bucket exists.
- Not a DVC repo: DVC not initialized. Track a file to auto-init.

MLFLOW ISSUES:
- Experiment not found: check project ID matches experiment name.
- Artifacts not loading: MLflow server may need restart.

GENERAL:
- After container restart, wait 10-20s for services to initialize.
- Check docker ps to verify all containers are running.
- Health endpoints: /api/airflow/health, /api/mlflow/experiments, /api/serving/health

TOOL CHOICE FOR SPECIFIC COMPLAINTS:
- "/api/serving/predict returns 404" / "the serving endpoint isn't working": call `get_serving_status` ONCE. A 404 typically means noted-serving is idle (no model loaded) - suggest `deploy_model` as the fix. Do NOT call `get_serving_schema` - that's for inspecting a loaded model's schema.
- "my file has 50+ lint warnings" / "too many lint issues": this is a volume complaint, not a diagnostic request. Answer conceptually - recommend `fix_lint_issues` for bulk auto-fix, then describe how to handle residual manual fixes. Do NOT call `get_lint_diagnostics` just to enumerate the list; the user already said there are many.
