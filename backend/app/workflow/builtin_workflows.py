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
        plan_template=[
            StepType(
                name="fetch_docs",
                worker="deterministic",
                description="GET the api_docs_url; cap to 60 KB.",
                handler=step_handlers.fetch_docs,
                output_schema={
                    "type": "object",
                    "required": ["api_docs"],
                    "properties": {
                        "api_docs": {"type": "string"},
                        "fetched_url": {"type": ["string", "null"]},
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
                name="publish_tool",
                worker="deterministic",
                description="Write files to data/tenants/<tenant>/user_tools/<name>/ + refresh federation.",
                handler=step_handlers.publish_tool,
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
                name="verify_tool_round_trip",
                worker="deterministic",
                description="Call the just-published tool with sample args.",
                handler=step_handlers.verify_tool_round_trip,
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
        plan_template=[
            StepType(
                name="archive_tool",
                worker="deterministic",
                description="Move tool dir to _archive/<name>_<ts>/.",
                handler=step_handlers.archive_tool,
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
