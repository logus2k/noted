---
name: airflow-performance
description: Analyzing pipeline duration and detecting bottlenecks. Use when user asks why a pipeline is slow, how to speed up DAG runs, which task takes the longest, or how to optimize training pipeline performance.
triggers: [airflow_in_context]
priority: 1
max_tokens: 400
---
Pipeline performance analysis in noted:

THE THREE COMMON WINS (always surface these when the user asks about slow pipelines):
1. **Parallelize independent tasks** - tasks without data dependencies should run in parallel, not chained with `>>`. Example: `train >> [eval_a, eval_b]` runs the two evaluations concurrently.
2. **Skip redundant re-compute** - if preprocessing output hasn't changed (check data hash), reuse the prior artifact instead of regenerating it. Dramatically reduces sweep cost.
3. **Cache intermediate artifacts** - persist per-task outputs in MinIO / shared mount keyed by content hash; subsequent runs load instead of recompute.

DURATION ANALYSIS:
- Each DAG run records total duration and per-task durations.
- View in the Pipelines panel: expand a run to see task-level timing.
- Use `get_dag_status` tool to retrieve run history and compare durations.

BOTTLENECK DETECTION:
- Identify the longest-running task - that is your bottleneck.
- Check if parallelizable tasks are actually running in parallel.
- Tasks waiting in "queued" state = worker resource constraints.
- Variable duration across runs = data-dependent bottleneck.

COMMON BOTTLENECKS:
- Training task: usually longest. Reduce epochs, use early stopping, mixed precision.
- Data loading: large datasets. Cache preprocessed data.
- Queue wait: too many concurrent runs. Limit sweep concurrency.

MONITORING:
- The Pipelines panel shows real-time task progress for running DAGs.
- Task state transitions (queued -> running -> success) are timestamped.
- For sweep runs, compare durations across the sweep to spot outliers.

When advising on performance, always start by identifying which specific task is the bottleneck before suggesting optimizations.

DIAGNOSTIC WORKFLOW (ONLY when the user explicitly asks you to investigate / diagnose a specific DAG - e.g. "can I speed up my DAG", "why is my DAG slow", "what's the bottleneck in my pipeline"):
- Use `list_dags` with default scope to find the project-local DAG(s); do NOT ask the user for the DAG id first.
- Then call `get_dag_status` on that DAG to get per-task durations.
- Only ask for clarification if multiple plausible DAGs remain ambiguous after listing.

CONCEPTUAL / ADVICE QUESTIONS (answer directly, NO tool calls) - covers things like:
- "training dominates the runtime" / "training is the slowest part"
- "my preprocessing runs from scratch every time even when data hasn't changed"
- "can two independent eval tasks run in parallel?"
- "how do I make X faster"
- Answer using the three common wins above plus the relevant bottleneck category. Concrete advice, no diagnostic detours.

Rule of thumb: a phrase that ASSERTS a performance fact ("training dominates", "preprocessing runs every time") is asking for advice. A phrase that ASKS FOR INVESTIGATION ("why is it slow", "can I speed it up", "what's the bottleneck") is asking for diagnosis.
