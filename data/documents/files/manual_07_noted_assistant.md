# Page 7: noted Assistant

**Goal**: Understand what the noted Assistant can do, how to pick
between local and cloud models, and how to use its skills and MCP
tools to speed up common tasks.

**Time**: ~10 minutes.

---

## What is the noted Assistant?

The noted Assistant is an AI chat panel built into the platform. It
is aware of noted's structure and can retrieve context, interpret
it, and take actions on your behalf - without leaving the browser
tab.

Concretely, the Assistant can:

- Explain an MLflow run's metrics and parameters in plain English.
- Compare two runs and summarize what changed and why it matters.
- Read a failed Airflow task log and point at the probable cause.
- Walk through the steps to set up a Hydra config for a new project.
- Use domain skills (Airflow, DVC, Evidently, Hydra, MLflow, noted)
  to answer "how do I...?" questions with accurate, platform-aware
  guidance.
- Invoke MCP tools such as listing a notebook's cells, fetching a
  run's artifacts, or retrieving the current Hydra selections - so
  it can act on live state rather than guess.

Open the Assistant by clicking the **speech bubble icon** in the
icon bar, or by clicking **Ask Assistant** on any run, task log, or
comparison panel.

---

## Choosing a model

The Assistant dropdown at the top of the chat panel lists the
models available to this noted instance.

### Local models (via `llama-cpp-python`)

noted ships with a local LLM served by `llama-cpp-python`. The
default is **Gemma 4** (4B parameters, instruction-tuned),
GPU-accelerated when CUDA is available. Local models:

- Run entirely inside the noted container - no API key required,
  no outbound calls, no data leaving your machine.
- Support native tool calling via Gemma 4's tool-call tokens, so
  the Assistant can invoke MCP tools just like the cloud models
  can.
- Are the right choice for experiments, sensitive data, offline
  demos, or when you want to stay cost-free.

### Cloud models (via Anthropic)

If `ANTHROPIC_API_KEY` is set in the environment, noted also
exposes Claude models in the dropdown:

- **Claude Sonnet 4.6** - the default cloud model. Good balance of
  speed, cost, and reasoning quality for day-to-day use.
- **Claude Opus 4.6** - the most capable model for long or complex
  investigations (run triage, multi-step refactors, deep
  diagnostics).
- **Claude Haiku 4.5** - the fastest and cheapest option for short
  tasks and quick answers.

All Claude models have a 200k-token context window and support the
full MCP tool surface.

Switching models mid-conversation is safe: the chat history is
preserved and the next turn is answered by the newly-selected
model.

---

## Skills

noted ships with approximately 40 **domain skills** that load
automatically into the Assistant's context when relevant. Each
skill is a short, curated document describing a specific capability
or best practice of one of noted's integrated tools.

The skills cover seven domains:

**Airflow** - DAG creation, DAG overview, scheduling, performance,
sweep strategies, task debugging, task dependencies, trigger
configuration.

**DVC** - best practices, checkout, lineage, sync debugging, file
tracking, versioning.

**Evidently** - data quality, drift detection, monitoring setup.

**Hydra** - composition, group structure, pipeline integration,
initial setup, sweep design, template patterns.

**MLflow** - artifact management, hyperparameter analysis, model
registration, reporting, run comparison, run debugging, run
interpretation, serving, snapshots, training curve analysis.

**noted core** - auto-instrumentation, coding conventions, lineage,
notebook resolution, platform overview, troubleshooting.

**General ML** - workflow guidance, Python linting, web fetch.

When you ask the Assistant a question, it picks the relevant
skills for the topic and loads their content into context before
generating an answer. You never need to select a skill manually;
the routing is automatic.

---

## MCP tools

Beyond skills, the Assistant can call **MCP (Model Context
Protocol) tools** to fetch live state or perform actions:

- `get_notebook_cells` - returns the source of every cell in the
  current notebook, so the Assistant can reason about actual code.
- `get_active_hydra_config` - returns the current Composer
  selections and the resolved config, so it can explain what will
  run.
- `mlflow-run-interpretation` - retrieves a run's full metrics,
  parameters, tags, and artifacts for analysis.
- `compare_runs` - retrieves two runs and produces a structured
  diff the Assistant can narrate.
- `airflow-task-debugging` - retrieves a task log and Airflow
  metadata for root-cause analysis.
- Tools for DVC lineage, registered model metadata, project files,
  and more.

Tool calls appear inline in the chat as collapsed "Tool call"
blocks. You can expand them to see the exact arguments and the raw
result the Assistant received before forming its answer.

---

## Example 1: Explain a training run

1. Open the Experiments tree and navigate to a finished run.
2. Click the **Ask Assistant** button at the top of the run detail
   panel.
3. The Assistant panel opens and is pre-populated with a message
   like:
   > Analyze run `92215c82...` ("DEMO Run #3") in the jena_weather
   > experiment. Explain its metrics and parameters and tell me if
   > the result looks reasonable.
4. Send the message. The Assistant calls
   `mlflow-run-interpretation` to fetch the run's full record, then
   produces a narrative covering the hyperparameters used, the
   final metric values, what the training curves look like, and any
   red flags (overfitting, exploding loss, missing metrics).

Useful for: triaging a large batch of runs, onboarding a team
member to an unfamiliar experiment, generating a summary paragraph
for a status update.

---

## Example 2: Compare two runs

1. Open a run detail and click **Compare**.
2. Pick a second run.
3. The comparison panel opens, showing the metrics / parameters /
   tags diff plus overlaid metric charts.
4. Click **Explain Differences**. The Assistant opens with both
   run IDs pre-loaded and analyzes what changed between them.
5. The Assistant calls `compare_runs` to get the structured diff,
   then explains which parameter changes caused which metric
   movements and whether the difference is statistically
   meaningful.

Useful for: understanding why a sweep's best run beat the baseline,
verifying that an improvement is real and not noise, documenting a
promotion decision.

---

## Example 3: Debug a failed Airflow task

1. Open the Orchestration tree and click a failed DAG run.
2. Click the failed task to open its log viewer.
3. Click **Ask Assistant** at the top of the log viewer.
4. The Assistant receives the last 1000 characters of the log, the
   task state, the task ID, and the DAG ID, along with a request to
   diagnose the failure.
5. The Assistant uses the `airflow-task-debugging` skill to frame
   the analysis, then explains what the stack trace means, what
   the likely root cause is, and what to fix before retrying the
   task.

Useful for: unblocking a teammate who does not know the codebase,
handling a 3 am pager event, writing a clear incident ticket.

---

## Example 4: Hydra configuration question

You do not always need a button - you can just type a question in
the Assistant panel:

> I have a new project with a config/ folder but my Composer shows
> "Not a valid Hydra config". What am I missing?

The Assistant routes to the `hydra-setup` and `noted-troubleshooting`
skills, checks the expected folder structure and the `defaults:`
list rules, and walks you through the likely fix.

---

## The "right panel" lifecycle

The Assistant lives in the **right panel**, which is collapsible:

- Click the speech bubble icon or **Ask Assistant** to open it.
- Click the X on the panel header to close it. The chat history is
  preserved across close/reopen for the lifetime of the browser
  session.
- Use the dropdown to switch between models without losing history.
- Use the **New Chat** button to clear the history and start fresh.

---

## Where to go next

- **Page 1 - Your First Project** - the starting point if you are
  new to noted.
- **Page 6 - Serving & Deploying Models** - the most recent feature
  area, a good place to ask the Assistant questions if you are
  exploring deployment workflows.
