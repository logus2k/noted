---
name: airflow-trigger-config
description: Configuring DAG triggers, loading Hydra config, and parameter setup. Use when user asks how to trigger a DAG, configure run parameters, load Hydra config into trigger, or set up sweep mode in the Trigger Panel.
triggers: [airflow_in_context]
priority: 1
max_tokens: 400
---
Triggering Airflow DAGs in noted:

TRIGGER PANEL:
- Open from the Pipelines panel or from a DAG's detail view.
- The Trigger Panel loads the DAG's expected parameters from its Hydra config.
- Parameters are editable before triggering.
- Submit triggers a new DAG run with the configured parameters.

HYDRA CONFIG LOADING:
- The Trigger Panel reads the project's `config/` directory.
- It composes the Hydra config with current group selections and overrides.
- The composed config populates the parameter fields in the trigger form.
- Changing a config group (e.g., model: lstm -> gru) updates all related fields.
- The config hash is computed and passed to the DAG run for lineage.

PARAMETER SETUP:
- Edit individual parameters directly in the trigger form.
- Override values use Hydra dotted-key notation: `training.learning_rate=0.001`.
- Group selection dropdowns show available config groups (model, data, training).
- The preview shows the final resolved config before triggering.

SWEEP MODE:
- Toggle "Sweep" in the Trigger Panel to enable parameter sweeps.
- Enter comma-separated values for parameters to sweep over.
- The preview table shows all combinations.
- Each combination becomes a separate DAG run with a shared sweep_id.

TRIGGER METHODS:
- UI: Trigger Panel in the Pipelines section.
- API: `POST /api/airflow/trigger` with dag_id and config JSON.
- Scheduled: cron-based automatic triggering (configured in the DAG).

AFTER TRIGGERING:
- The DAG run appears in the Pipelines panel with "running" state.
- Monitor task progress in real-time.
- If a task fails, check its log for the error before retrying.

ANSWERING "HOW DO I TRIGGER / CONFIGURE / SWEEP" QUESTIONS (conceptual - NO tool calls needed):
- These are advice questions. Answer directly from the sections above. Do NOT call list_dags, get_dag_status, or get_hydra_config just to answer a how-to.
- Concrete examples of conceptual questions where NO tools should be called:
  - "how do I trigger X with params?" -> no tools, explain Trigger Panel + CLI
  - "I want to trigger X 10 times with different seeds" -> no tools, explain sweep loop pattern / SWEEP MODE / airflow-sweep-strategy skill
  - "how do I let my DAG accept parameters?" -> no tools, explain params={...} + context["params"]
- For sweeps across N seeds/values, point to SWEEP MODE above and to the airflow-sweep-strategy skill. A bash/python loop that calls the trigger API N times also works.

ANSWERING "WHERE DO I SEE PROGRESS" QUESTIONS:
- Primary answer: the Pipelines panel Grid view shows status and per-task progress for the triggered run.
- Optional: call `get_dag_status(dag_id=<id>)` to list recent runs and identify the one just triggered (useful if the user wants programmatic visibility).
