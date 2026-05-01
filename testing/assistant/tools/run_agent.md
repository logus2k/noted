# Tool: run_agent

**Type:** tool
**Tier:** read
**Domain:** delegation / agents
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Delegates a reading/exploration task to a named subagent in a fresh context window. Used for multi-file or open-ended research that would bloat the main context.

## Input schema

- `task` (required, detailed description), `agent_name` (required).

## Setup prerequisites

- Subagent registered (e.g. `notebook-explorer`).

## Scenarios

### S1 - Delegate notebook exploration
"use notebook-explorer to summarize training_sandbox.ipynb" → `run_agent(agent_name="notebook-explorer", task=...)`.

### S2 - Don't delegate trivial work
"what's in cell 5?" → `get_notebook_cells` directly; do NOT delegate.

### S3 - Multi-file research
"summarize how the project trains/evaluates" → delegate.

### S4 - Specify task clearly
Concrete, actionable task description; report findings.

### S5 - Subagent fails (DEFERRED)
### S6 - Cross-agent chaining (DEFERRED)
