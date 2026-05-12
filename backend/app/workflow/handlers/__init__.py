"""Per-workflow handler packages.

Each subpackage owns the handlers for a single workflow type. The package
shape is the agent-determinism convention agreed 2026-05-12: instead of
adding new handlers into a shared multi-thousand-line file, each workflow
type gets its own folder with one handler-per-file (plus `_helpers.py`
modules for code shared across that workflow's handlers).

`app/workflow/builtin_workflows.py` imports handlers from here when wiring
each `StepType`. The shared `app/workflow/step_handlers.py` is being
phased out as handlers migrate; nothing here re-exports back into it.
"""
