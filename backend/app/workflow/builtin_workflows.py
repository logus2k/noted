"""First-wave workflow registrations.

Importing this module registers `create_tool` and `remove_tool` against the
WorkflowRegistry singleton. noted/backend/app/main.py imports it at startup
so the workflows are available in time for the first chat turn.

Standalone `create_skill` / `remove_skill` workflows (skill without a tool)
are deferred; the paired skill operations inside `create_tool` and
`remove_tool` cover the high-frequency case.
"""

from __future__ import annotations

import logging

from . import step_handlers
from .registry import get_workflow_registry
from .types import StepType, WorkflowDefinition, WorkflowOutcome

logger = logging.getLogger(__name__)


# ─── create_tool ──────────────────────────────────────────────────


_TOOL_AUTHOR_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["tool_name", "language", "files"],
    "properties": {
        "tool_name": {"type": "string", "minLength": 1},
        "language": {"type": "string", "enum": ["python", "javascript"]},
        "summary": {"type": "string"},
        "files": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string"},
        },
    },
}

_API_TESTER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["language", "files"],
    "properties": {
        "language": {"type": "string", "enum": ["python", "javascript"]},
        "test_count": {"type": "integer"},
        "summary": {"type": "string"},
        "files": {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string"},
        },
        "additional_requirements": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },
    },
}

_CREATE_TOOL_INPUT_SCHEMA = {
    "type": "object",
    "required": ["tool_name", "mission", "language", "acceptance_criteria"],
    "properties": {
        "tool_name": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*$",
            "maxLength": 40,
            "description": (
                "Snake_case name for the new MCP tool. "
                "Must start with a lowercase letter; only lowercase, digits, "
                "and underscores allowed."
            ),
        },
        "mission": {
            "type": "string",
            "minLength": 8,
            "description": (
                "One- or two-sentence description of what the tool should "
                "do, including the expected input shape and the expected "
                "output shape."
            ),
        },
        "language": {
            "type": "string",
            "enum": ["python", "javascript"],
            "description": "Implementation language for the tool.",
        },
        "api_docs_urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "URLs of API documentation pages relevant to the tool. "
                "Multiple endpoints from the same service belong here."
            ),
        },
        "api_docs_url": {
            "type": "string",
            "description": (
                "DEPRECATED single-URL form. Prefer api_docs_urls. Kept "
                "for backward-compat with hand-crafted callers."
            ),
        },
        "acceptance_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": (
                "Concrete, smoke-testable behaviours the published tool "
                "must satisfy. Each criterion should be checkable by a "
                "single pytest assertion (e.g. \"missing input exits "
                "non-zero\", \"output JSON contains key X\")."
            ),
        },
        "verify_inputs": {
            "type": "object",
            "description": (
                "Sample input dict the framework will pass to the "
                "freshly-published tool to verify round-trip callability."
            ),
        },
    },
}


_REMOVE_TOOL_INPUT_SCHEMA = {
    "type": "object",
    "required": ["tool_name"],
    "properties": {
        "tool_name": {
            "type": "string",
            "description": "Name of the tool to archive (snake_case).",
        },
    },
}


_SKILL_AUTHOR_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["skill_name", "frontmatter", "body"],
    "properties": {
        "skill_name": {"type": "string", "minLength": 1},
        "summary": {"type": "string"},
        "frontmatter": {
            "type": "object",
            "required": ["name", "description", "type", "triggers"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "type": {"type": "string"},
                "priority": {"type": "integer"},
                "max_tokens": {"type": "integer"},
                "triggers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
        },
        "body": {
            "type": "object",
            "required": ["purpose", "inputs", "output_shape"],
            "properties": {
                "purpose": {"type": "string"},
                "inputs": {"type": "array", "items": {"type": "string"}},
                "output_shape": {"type": "array", "items": {"type": "string"}},
                "examples": {"type": "array", "items": {"type": "string"}},
                "when_not_to_use": {"type": ["string", "null"]},
            },
        },
    },
}


def _register_create_tool() -> None:
    registry = get_workflow_registry()
    if registry.get("create_tool") is not None:
        return
    registry.register(WorkflowDefinition(
        type="create_tool",
        description=(
            "Authors a new MCP tool by reading API docs, generating a Python or "
            "JavaScript client, validating it structurally, publishing it, "
            "verifying round-trip callability, and pairing it with a skill."
        ),
        outcomes=[
            WorkflowOutcome(name="tool_published", description="tool registered with noted-tools"),
            WorkflowOutcome(name="skill_published", description="paired skill written to data/skills/"),
        ],
        input_schema=_CREATE_TOOL_INPUT_SCHEMA,
        plan_template=[
            StepType(
                name="fetch_docs",
                worker="deterministic",
                description=(
                    "GET each URL in api_docs_urls (or the legacy "
                    "api_docs_url); concatenate under per-URL headers; "
                    "cap to ~60 KB total."
                ),
                handler=step_handlers.fetch_docs,
                # Network HTTP fetch — one retry covers a transient blip without
                # turning a real failure into a 3x wait.
                max_retries=1,
                output_schema={
                    "type": "object",
                    "required": ["api_docs"],
                    "properties": {
                        "api_docs": {"type": "string"},
                        "fetched_url": {"type": ["string", "null"]},
                        "fetched_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "skipped": {"type": "boolean"},
                        "truncated": {"type": "boolean"},
                    },
                },
            ),
            StepType(
                name="tool_author",
                worker="tool_author",
                description="LLM-author the client + tool.json + requirements.",
                output_schema=_TOOL_AUTHOR_OUTPUT_SCHEMA,
            ),
            StepType(
                name="validate_tool_structure",
                worker="deterministic",
                description="Static checks: required files, JSON shape, ast.parse.",
                handler=step_handlers.validate_tool_structure,
                # Deterministic — same input → same failure. Skip retries.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["ok", "tool_name"],
                    "properties": {
                        "ok": {"const": True},
                        "tool_name": {"type": "string"},
                        "language": {"type": "string"},
                        "files_present": {"type": "array"},
                        "tool_json_keys": {"type": "array"},
                    },
                },
            ),
            StepType(
                name="api_tester",
                worker="api_tester",
                description="LLM-author smoke tests covering the acceptance criteria.",
                output_schema=_API_TESTER_OUTPUT_SCHEMA,
            ),
            StepType(
                name="validate_smoke_contract",
                worker="deterministic",
                description="Static check that smoke.py asserts only on keys named in acceptance_criteria.",
                handler=step_handlers.validate_smoke_contract,
                # Deterministic — same smoke.py + criteria → same outcome.
                # Recovery comes from A2 rewinding api_tester, not retry.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["ok"],
                    "properties": {
                        "ok": {"const": True},
                        "checked": {"type": "boolean"},
                        "reason": {"type": "string"},
                        "asserted_output_keys": {"type": "array"},
                        "criteria_count": {"type": "integer"},
                    },
                },
            ),
            StepType(
                name="publish_tool",
                worker="deterministic",
                description="Write files to data/tenants/<tenant>/user_tools/<name>/ + refresh federation.",
                handler=step_handlers.publish_tool,
                # Deterministic file-writes; if they fail it's an env issue (perms,
                # disk full) — retrying immediately won't help.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["tool_name", "tool_dir", "federation_refreshed"],
                    "properties": {
                        "tool_name": {"type": "string"},
                        "tool_dir": {"type": "string"},
                        "language": {"type": ["string", "null"]},
                        "files_written": {"type": "array"},
                        "federation_refreshed": {"type": "boolean"},
                    },
                },
            ),
            StepType(
                name="run_smoke_tests",
                worker="deterministic",
                description="F3.5: pytest smoke.py inside the tool's venv via noted-tools admin endpoint.",
                handler=step_handlers.run_smoke_tests,
                # Deterministic — pytest on identical files yields identical
                # failure. Bounded improvement comes from A2's regenerate-on-
                # smoke-failure rewind, not from re-running the same script.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["ok", "tool_name"],
                    "properties": {
                        "ok": {"const": True},
                        "tool_name": {"type": "string"},
                        "skipped": {"type": "boolean"},
                        "exit_code": {"type": "integer"},
                    },
                },
            ),
            StepType(
                name="verify_tool_round_trip",
                worker="deterministic",
                description="Call the just-published tool with sample args.",
                handler=step_handlers.verify_tool_round_trip,
                # Deterministic — calls the published tool with sample args.
                # Network blips are the only retry-recoverable case; rare
                # enough that one extra retry doesn't pay for itself.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["ok", "tool_name"],
                    "properties": {
                        "ok": {"const": True},
                        "tool_name": {"type": "string"},
                        "sample_args": {"type": "object"},
                        "result_preview": {"type": "string"},
                    },
                },
            ),
            StepType(
                name="skill_author",
                worker="skill_author",
                description="LLM-author the paired skill (frontmatter + body sections).",
                output_schema=_SKILL_AUTHOR_OUTPUT_SCHEMA,
            ),
            StepType(
                name="publish_skill",
                worker="deterministic",
                description="Assemble markdown, write data/skills/<name>.md.",
                handler=step_handlers.publish_skill,
                # Deterministic file-write; same retry rationale as publish_tool.
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["skill_name", "skill_path"],
                    "properties": {
                        "skill_name": {"type": "string"},
                        "skill_path": {"type": "string"},
                        "byte_size": {"type": "integer"},
                    },
                },
            ),
        ],
        # Generous wallclock cap: 7 steps, 2 LLM calls (each can be slow on
        # Gemma), retries on validation failure.
        max_wallclock_seconds=1800,
        max_retries_per_step=2,
    ))
    logger.info("registered workflow: create_tool (7 steps, 2 outcomes)")


# ─── remove_tool ──────────────────────────────────────────────────


def _register_remove_tool() -> None:
    registry = get_workflow_registry()
    if registry.get("remove_tool") is not None:
        return
    registry.register(WorkflowDefinition(
        type="remove_tool",
        description=(
            "Archives a previously published tool and its paired skill. "
            "Both moves are atomic from the registry's POV: federation "
            "refreshed once at the end."
        ),
        outcomes=[
            WorkflowOutcome(name="tool_archived", description="tool moved to user_tools/_archive/"),
            WorkflowOutcome(name="skill_archived", description="skill moved to data/skills/_archive/"),
        ],
        input_schema=_REMOVE_TOOL_INPUT_SCHEMA,
        plan_template=[
            StepType(
                name="archive_tool",
                worker="deterministic",
                description="Move tool dir to _archive/<name>_<ts>/.",
                handler=step_handlers.archive_tool,
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["tool_name", "archived"],
                    "properties": {
                        "tool_name": {"type": "string"},
                        "archive_path": {"type": "string"},
                        "archived": {"type": "boolean"},
                        "federation_refreshed": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                },
            ),
            StepType(
                name="archive_skill",
                worker="deterministic",
                description="Move skill md to data/skills/_archive/.",
                handler=step_handlers.archive_skill,
                max_retries=0,
                output_schema={
                    "type": "object",
                    "required": ["skill_name", "archived"],
                    "properties": {
                        "skill_name": {"type": "string"},
                        "archive_path": {"type": "string"},
                        "archived": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                },
            ),
        ],
        max_wallclock_seconds=120,
        max_retries_per_step=1,
    ))
    logger.info("registered workflow: remove_tool (2 steps, 2 outcomes)")


# Run registrations at import time.
_register_create_tool()
_register_remove_tool()
