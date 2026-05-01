# Skill: noted-platform-overview

**Type:** skill
**File:** [data/skills/noted-platform-overview/SKILL.md](../../../data/skills/noted-platform-overview/SKILL.md)
**Auto-inject triggers:** `user_asks_about_noted`
**Priority:** 3
**Max tokens:** 500

## Purpose

This skill gives the Assistant a concise factual sheet about what noted is: core capabilities, MLOps integrations, key concepts, and container topology. It exists so the model can answer "what is noted?" style questions without hallucinating or generalizing from open-web knowledge of similar products.

## Auto-injection status (important for test interpretation)

As currently configured, this skill will **not auto-inject** in any scenario: priority 3 is below the priority-1 threshold used by `SkillRegistry._load_all`, and `user_asks_about_noted` is not a condition emitted by `build_context_message` (see `feedback_skill_injection_mechanics.md`). That means the Assistant cannot reach the skill body unless the user or the platform surfaces it via `get_skill`. Scenarios below are written assuming the skill IS loaded into the model's context (either because a future change makes it auto-inject, or because the harness pre-loads it with `get_skill` for the test). When the harness runs these scenarios on the current build, expect the answer axis to fail for scenarios that require specific facts from the skill body - that failure is a legitimate signal to fix the skill's trigger/priority.

## Setup prerequisites

Unless a scenario says otherwise:

- Project: `noted-testing`
- Open notebook: any notebook in `noted-testing` (use a minimal one like a Welcome clone); notebook content is not central
- MLflow: irrelevant, no run needs to be active
- Hydra / DVC / Airflow: no state required
- Deployed model: none required
- The skill `noted-platform-overview` is assumed to be present in the model's active skills (test harness should pre-load via `get_skill` for the current priority-3 configuration)

## Scenarios

### S1 - Direct "what is noted?"
**Setup:** default
**User request:** "what is noted?"
**Expected tool calls:** none
**Forbidden tool calls:** `get_notebook_cells`, `get_file_contents`, `list_files`, `query_knowledge_graph`, `fetch_url`
**Expected answer focus:** name it as an on-premises collaborative notebook and MLOps platform, mention Jupyter-compatible notebooks + MLflow + Airflow + DVC + Hydra integration. Do NOT claim cloud features.

### S2 - "What does the stack look like?"
**Setup:** default
**User request:** "what does the stack look like?"
**Expected tool calls:** none
**Forbidden tool calls:** `query_knowledge_graph`, `list_files`
**Expected answer focus:** list the 12 Docker containers (noted, mlflow, airflow x5, minio, serving, graph, postgres, redis), note Docker Compose, note on-premises with no cloud dependency.

### S3 - "Which MLOps tools are integrated?"
**Setup:** default
**User request:** "which MLOps tools are integrated with noted?"
**Expected tool calls:** none
**Forbidden tool calls:** `fetch_url`, `list_files`
**Expected answer focus:** MLflow (tracking + registry + serving), Airflow (orchestration), DVC (backed by MinIO), Hydra (config), Knowledge Graph. Should not invent extras.

### S4 - Project vs mount distinction
**Setup:** default
**User request:** "what's the difference between a project and a mount?"
**Expected tool calls:** none
**Forbidden tool calls:** `list_files`
**Expected answer focus:** projects hold notebooks/code/configs/DAGs; mounts are external directories exposed to noted (read-write). Do not conflate them.

### S5 - Run Manager concept
**Setup:** default
**User request:** "what is the Run Manager?"
**Expected tool calls:** none
**Forbidden tool calls:** `get_experiment_runs`, `get_notebook_cells`
**Expected answer focus:** it defines cell groups as named runs and executes them with automatic MLflow start/end and framework autologging. Do NOT suggest the user has to write `mlflow.start_run()` themselves.

### S6 - Lineage chain explanation
**Setup:** default
**User request:** "how does noted track lineage across tools?"
**Expected tool calls:** none
**Forbidden tool calls:** `query_knowledge_graph` (the user is asking about the concept, not querying an instance)
**Expected answer focus:** Data (DVC) -> Config (Hydra) -> Code (Git) -> Pipeline (Airflow) -> Run (MLflow) -> Model (Registry). State the chain in order.

### S7 - Live Metrics
**Setup:** default
**User request:** "how does real-time metric streaming work?"
**Expected tool calls:** none
**Forbidden tool calls:** `search_files`, `get_notebook_cells`
**Expected answer focus:** Live Metrics streams training metrics during execution via Socket.IO. Brief is fine; do not fabricate implementation specifics not in the skill.

### S8 - Scope boundaries (what noted is NOT)
**Setup:** default
**User request:** "is noted a cloud service like SageMaker?"
**Expected tool calls:** none
**Forbidden tool calls:** `fetch_url`
**Expected answer focus:** no, noted is on-premises with zero cloud dependency; contrast briefly with managed cloud platforms. Should not refuse to answer or hedge excessively.

### S9 - Editor technology
**Setup:** default
**User request:** "what editor does noted use for notebooks?"
**Expected tool calls:** none
**Forbidden tool calls:** `list_files`, `search_files`
**Expected answer focus:** CodeMirror 6, Jupyter-compatible format. Should not claim JupyterLab or Monaco.

### S10 - Multi-venv capability
**Setup:** default
**User request:** "can I have different Python environments per project?"
**Expected tool calls:** none
**Forbidden tool calls:** `list_files`
**Expected answer focus:** yes, multiple Python runtimes/venvs per project is a core capability. Do NOT tell the user to install venvs manually with pyenv.

### S11 - Collaboration claim
**Setup:** default
**User request:** "can two people edit the same notebook at once?"
**Expected tool calls:** none
**Forbidden tool calls:** `fetch_url`
**Expected answer focus:** yes, real-time collaboration via Socket.IO is supported. Short is fine.

### S12 - Primary surface of interaction
**Setup:** default
**User request:** "where do users spend most of their time in noted?"
**Expected tool calls:** none
**Forbidden tool calls:** `get_file_contents`
**Expected answer focus:** primarily the notebook editor and Explorer panel; MLOps tools are accessed without leaving the notebook environment.

### S13 - Workflow orientation
**Setup:** default
**User request:** "walk me through a typical end-to-end workflow on noted"
**Expected tool calls:** none
**Forbidden tool calls:** `list_dags`, `get_experiment_runs` (user is asking the generic concept, not inspecting their own state)
**Expected answer focus:** describe the chain: open a notebook -> compose config via Hydra -> version data via DVC -> run via Run Manager -> track in MLflow -> orchestrate via Airflow -> register & deploy a model. Should not invent extra phases.

### S14 - Knowledge Graph purpose
**Setup:** default
**User request:** "what does the knowledge graph do?"
**Expected tool calls:** none (note distinction: the user is asking the concept, not querying an actual graph)
**Forbidden tool calls:** `query_knowledge_graph`
**Expected answer focus:** entity relationship visualization across projects; it's a capability not a query action. If the user then asks to see their project's graph, that would be a separate follow-up where `query_knowledge_graph` WOULD fire.

### S15 - Workflow test: overview followed by concrete ask
**Setup:** default, sandbox project `noted-testing` has at least one experiment with one completed run
**Turn 1 user request:** "what is noted?"
**Turn 1 expected tool calls:** none
**Turn 1 forbidden tool calls:** all
**Turn 1 expected answer focus:** standard overview (see S1)
**Turn 2 user request:** "ok then show me the recent runs in this project"
**Turn 2 expected tool calls:** `get_experiment_runs` (with `experiment_name="noted-testing"` or equivalent project_id arg)
**Turn 2 forbidden tool calls:** `list_files`, `query_knowledge_graph`
**Turn 2 expected answer focus:** the actual runs from the sandbox, not a generic explanation
**Notes:** This tests that the skill does not *suppress* the model's ability to call tools on subsequent turns.
