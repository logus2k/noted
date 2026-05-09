"""Deterministic step handlers used by the first-wave workflows.

Each handler is `async def handler(state: WorkspaceState, inputs: dict) -> dict`
and returns a dict that the framework validates against the step's
`output_schema`. Failures raise; the loop's bounded-retry path catches and
feeds back as `validator_complaint`.

What's here in F3:
- fetch_docs: httpx GET the API docs URL into the workspace.
- validate_tool_structure: JSON-schema check the generated tool.json + ast.parse the tool.py.
- publish_tool: write generated files to the tenant's user_tools dir + force-refresh
  the noted-tools federation client so the LLM sees the new tool on the next turn.
- verify_tool_round_trip: invoke the just-published tool with a sample input via
  the federation MCP path; check it returns a non-error response.
- publish_skill: write the assembled skill markdown to data/skills/.
- archive_tool / archive_skill: move dirs / files to the tenant's _archive area.

Deferred to a follow-on: subprocess + pytest execution of api_tester's smoke
tests. The current validation set catches structural defects and proves the
published tool is callable; functional verification of richer behaviour
(network mocks, hermetic tests) needs noted backend to host a per-workflow
venv, which is its own piece of plumbing.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import DATA_DIR
from .workspace import WorkspaceState

logger = logging.getLogger(__name__)

# noted-tools runs as UID 1000:1000 (Phase A polish) so the per-tool
# venvs are host-owned. noted backend runs as root, so anything it writes
# into the tenants bind-mount lands root-owned and noted-tools can't
# create the venv inside. publish / archive steps explicitly chown to
# 1000:1000 after write so noted-tools' executor has write access.
NOTED_TOOLS_UID = 1000
NOTED_TOOLS_GID = 1000


def _chown_tree_to_noted_tools(path: Path) -> None:
    """Recursively chown a directory tree to noted-tools' runtime UID:GID.
    Best-effort: silently skip when running unprivileged (e.g. tests on
    host where the workflow process isn't root)."""
    try:
        os.chown(path, NOTED_TOOLS_UID, NOTED_TOOLS_GID)
        for child in path.rglob("*"):
            try:
                os.chown(child, NOTED_TOOLS_UID, NOTED_TOOLS_GID)
            except OSError:
                pass
    except OSError as e:
        logger.warning("chown to %d:%d failed for %s: %s",
                       NOTED_TOOLS_UID, NOTED_TOOLS_GID, path, e)


# ─── helpers ──────────────────────────────────────────────────────


def _tenant_user_tools_dir(tenant_id: str) -> Path:
    return Path(DATA_DIR) / "tenants" / tenant_id / "user_tools"


def _tenant_archive_dir(tenant_id: str) -> Path:
    return _tenant_user_tools_dir(tenant_id) / "_archive"


def _skills_dir() -> Path:
    return Path(DATA_DIR) / "skills"


def _previous(inputs: dict[str, Any], step_name: str | None = None) -> dict[str, Any]:
    prev = inputs.get("previous_step") or {}
    if step_name and prev.get("name") != step_name:
        return {}
    return prev.get("output") or {}


# ─── fetch_docs ───────────────────────────────────────────────────


async def fetch_docs(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    """Fetch the API documentation URL declared in workflow_inputs.

    Returns a dict with the fetched text (truncated). Workflow inputs may
    set `api_docs_url` to "" or null, in which case this step returns an
    empty doc and lets tool_author work from the mission alone.
    """
    wf_in = state.inputs or {}
    url = (wf_in.get("api_docs_url") or "").strip()
    if not url or url.upper() == "N/A":
        return {"api_docs": "", "fetched_url": None, "skipped": True}

    timeout = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "noted-workflow/1.0"})
            resp.raise_for_status()
            text = resp.text
    except httpx.HTTPError as e:
        raise ValueError(f"fetch_docs: {type(e).__name__} fetching {url}: {e}") from e

    # Hard cap so we don't blow the worker's context. Real API docs are
    # huge; the worker preset re-uses what's relevant. 60 KB is a balanced
    # default for Gemma's 131k window with room for the rest.
    cap = 60_000
    truncated = len(text) > cap
    if truncated:
        text = text[:cap] + "\n\n[... truncated by fetch_docs ...]"
    return {
        "api_docs": text,
        "fetched_url": url,
        "skipped": False,
        "truncated": truncated,
    }


# ─── validate_tool_structure ──────────────────────────────────────


def _required_files(language: str) -> list[str]:
    if language == "python":
        return ["tool.json", "tool.py", "requirements.txt"]
    if language == "javascript":
        return ["tool.json", "tool.js", "package.json"]
    return ["tool.json"]


_TOOL_JSON_REQUIRED = {"name", "description", "input_schema"}


async def validate_tool_structure(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Static validation of tool_author's output: required files present,
    tool.json is valid JSON with the required keys, Python source parses
    via ast.parse (JS source check is a basic non-empty for now).

    Subprocess-based functional validation is a separate step in a future
    iteration of this plan."""
    prev = _previous(inputs, "tool_author") or _previous(inputs)
    files: dict[str, str] = prev.get("files") or {}
    language = prev.get("language") or "python"
    tool_name = prev.get("tool_name") or ""

    if not tool_name or not tool_name.replace("_", "").isalnum():
        raise ValueError(f"validate_tool_structure: invalid tool_name {tool_name!r}")

    missing = [f for f in _required_files(language) if f not in files]
    if missing:
        raise ValueError(
            f"validate_tool_structure: missing required files for {language}: {missing}"
        )

    # tool.json round-trip + key check
    try:
        tool_json = json.loads(files["tool.json"])
    except json.JSONDecodeError as e:
        raise ValueError(f"validate_tool_structure: tool.json is not valid JSON: {e}") from e
    if not isinstance(tool_json, dict):
        raise ValueError("validate_tool_structure: tool.json is not a JSON object")
    missing_keys = _TOOL_JSON_REQUIRED - set(tool_json.keys())
    if missing_keys:
        raise ValueError(
            f"validate_tool_structure: tool.json missing required keys: {sorted(missing_keys)}"
        )
    if tool_json.get("name") != tool_name:
        raise ValueError(
            f"validate_tool_structure: tool.json name {tool_json.get('name')!r} "
            f"does not match outer tool_name {tool_name!r}"
        )

    # Implementation source parse
    if language == "python":
        try:
            ast.parse(files["tool.py"], filename="tool.py")
        except SyntaxError as e:
            raise ValueError(f"validate_tool_structure: tool.py SyntaxError: {e}") from e
    elif language == "javascript":
        if not files.get("tool.js", "").strip():
            raise ValueError("validate_tool_structure: tool.js is empty")
        # JS syntax check would need node; skipping until F3-extended.

    return {
        "tool_name": tool_name,
        "language": language,
        "files_present": sorted(files.keys()),
        "tool_json_keys": sorted(tool_json.keys()),
        "ok": True,
    }


# ─── publish_tool ─────────────────────────────────────────────────


async def publish_tool(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Write tool_author's files to data/tenants/<tenant_id>/user_tools/<name>/.

    On conflict (tool already exists), archive the prior version first so
    the operator can roll back. Triggers a federation refresh so the LLM
    sees the new tool immediately.
    """
    # Pull files from the most recent author-step output. tool_author may
    # not be the immediately-prior step (validation could be in between);
    # walk back through completed steps until we find files.
    files: dict[str, str] | None = None
    tool_name: str | None = None
    language: str | None = None
    for step in reversed(state.steps):
        if step.status != "completed":
            continue
        out = step.output or {}
        if isinstance(out.get("files"), dict) and out.get("tool_name"):
            files = out["files"]
            tool_name = out["tool_name"]
            language = out.get("language") or "python"
            break
    if not files or not tool_name:
        raise ValueError("publish_tool: no upstream tool_author output found in workspace")

    tools_root = _tenant_user_tools_dir(state.tenant_id)
    tool_dir = tools_root / tool_name
    tools_root.mkdir(parents=True, exist_ok=True)

    if tool_dir.exists():
        archive_root = _tenant_archive_dir(state.tenant_id)
        archive_root.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        archived = archive_root / f"{tool_name}_{ts}"
        shutil.move(str(tool_dir), str(archived))
        logger.info("publish_tool: archived prior version to %s", archived)

    tool_dir.mkdir(parents=True, exist_ok=False)

    # F6.5: inject source-workflow lineage + created_by + created_at into
    # tool.json's `_meta` so the Explorer's tool detail can render the
    # provenance card with a click-through to the WorkflowMonitor. The LLM
    # (tool_author) shouldn't know its own workflow id; this step does.
    from datetime import datetime, timezone
    files = dict(files)
    if "tool.json" in files:
        try:
            tool_json = json.loads(files["tool.json"])
        except json.JSONDecodeError:
            tool_json = None
        if isinstance(tool_json, dict):
            meta = dict(tool_json.get("_meta") or {})
            meta.setdefault("provenance", "user")
            meta.setdefault("language", language)
            meta.setdefault("version", 1)
            meta["created_by"] = state.actor_id
            meta["created_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            meta["source_workflow"] = {
                "type": state.workflow_type,
                "workflow_id": state.workflow_id,
                "tenant_id": state.tenant_id,
            }
            tool_json["_meta"] = meta
            files["tool.json"] = json.dumps(tool_json, indent=2)

    for fname, content in files.items():
        (tool_dir / fname).write_text(content)
    # Hand ownership to noted-tools so its UID-1000 executor can build the venv.
    _chown_tree_to_noted_tools(tool_dir)

    refreshed = await _refresh_user_tools_federation()

    return {
        "tool_name": tool_name,
        "language": language,
        "tool_dir": str(tool_dir),
        "files_written": sorted(files.keys()),
        "federation_refreshed": refreshed,
    }


async def _refresh_user_tools_federation() -> bool:
    """Tell noted's federation client to re-pull noted-tools' registry NOW.

    Without this, the new tool appears on the LLM tool list within the
    next 30s polling cycle. Forcing a refresh here ensures the LLM can
    call the tool on the very next chat turn.
    """
    try:
        from app.mcp.user_tools_client import get_user_tools_client
        client = get_user_tools_client()
        return await client.refresh()
    except Exception as e:
        logger.warning("publish_tool: federation refresh failed: %s", e)
        return False


# ─── verify_tool_round_trip ───────────────────────────────────────


async def verify_tool_round_trip(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Invoke the just-published tool through the federation MCP path.

    Uses sample inputs from the workflow's `verify_inputs` field if
    provided, else builds a minimal call from the input_schema's required
    fields.

    Pass = the call returns content with `isError: false`. Anything else
    fails the step (and the loop's retry feeds the error back to
    tool_author).
    """
    prev_publish = _previous(inputs, "publish_tool")
    if not prev_publish:
        for step in reversed(state.steps):
            if step.name == "publish_tool" and step.status == "completed":
                prev_publish = step.output or {}
                break
    if not prev_publish:
        raise ValueError("verify_tool_round_trip: no upstream publish_tool output found")

    tool_name = prev_publish.get("tool_name")
    if not tool_name:
        raise ValueError("verify_tool_round_trip: publish_tool did not record tool_name")

    sample_args = (state.inputs or {}).get("verify_inputs") or {}
    if not sample_args:
        # Try to derive from the published tool.json's input_schema.
        tool_dir = Path(prev_publish.get("tool_dir") or "")
        try:
            tool_json = json.loads((tool_dir / "tool.json").read_text())
            schema = tool_json.get("input_schema") or {}
            required = schema.get("required") or []
            props = schema.get("properties") or {}
            for req in required:
                t = (props.get(req) or {}).get("type")
                sample_args[req] = {
                    "string": "test",
                    "integer": 1,
                    "number": 1.0,
                    "boolean": True,
                    "array": [],
                    "object": {},
                }.get(t, "test")
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(
                f"verify_tool_round_trip: cannot derive sample args from tool.json: {e}"
            ) from e

    # Federation has a small grace window where the just-refreshed cache
    # might not yet reflect the new tool. Retry briefly.
    from app.mcp.user_tools_client import get_user_tools_client
    client = get_user_tools_client()
    for _ in range(5):
        if client.has_tool(tool_name):
            break
        await asyncio.sleep(0.2)
        await client.refresh()

    if not client.has_tool(tool_name):
        raise ValueError(
            f"verify_tool_round_trip: tool {tool_name!r} did not appear in federation registry"
        )

    result = await client.call(tool_name, sample_args)
    if result.startswith("Error:"):
        raise ValueError(
            f"verify_tool_round_trip: tool returned error: {result[:300]}"
        )
    return {
        "tool_name": tool_name,
        "sample_args": sample_args,
        "result_preview": result[:300],
        "ok": True,
    }


# ─── publish_skill ────────────────────────────────────────────────


# Skills follow the folder convention: data/skills/<skill_name>/SKILL.md.
# Frontmatter MUST use inline YAML list syntax for `triggers` because the
# noted SkillRegistry parser only handles `key: [a, b]` style, not the
# multi-line `key:\n  - a\n  - b` form. Same for `references` etc.
_SKILL_TEMPLATE = """---
name: {name}
description: {description}
type: {skill_type}
priority: {priority}
max_tokens: {max_tokens}
triggers: [{triggers_inline}]
---
**Purpose**
{purpose}

**Inputs**
{inputs_md}

**Output shape**
{output_shape_md}

**Examples**
{examples_md}
{when_not_block}"""


def _quote_yaml_inline(value: str) -> str:
    safe = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{safe}"'


def _assemble_skill_markdown(skill_data: dict[str, Any]) -> str:
    fm = skill_data.get("frontmatter") or {}
    body = skill_data.get("body") or {}
    triggers = fm.get("triggers") or []
    triggers_inline = ", ".join(_quote_yaml_inline(t) for t in triggers)
    inputs_md = "\n".join(f"- {x}" for x in (body.get("inputs") or []))
    output_md = "\n".join(f"- {x}" for x in (body.get("output_shape") or []))
    examples_md = "\n".join(f"- {x}" for x in (body.get("examples") or []))
    when_not = body.get("when_not_to_use") or ""
    when_block = f"\n**When NOT to use**\n{when_not}\n" if when_not else ""
    return _SKILL_TEMPLATE.format(
        name=fm.get("name") or skill_data.get("skill_name") or "",
        description=fm.get("description") or "",
        skill_type=fm.get("type") or "tool_skill",
        priority=fm.get("priority") if fm.get("priority") is not None else 2,
        max_tokens=fm.get("max_tokens") if fm.get("max_tokens") is not None else 500,
        triggers_inline=triggers_inline,
        purpose=body.get("purpose") or "",
        inputs_md=inputs_md,
        output_shape_md=output_md,
        examples_md=examples_md,
        when_not_block=when_block,
    )


async def publish_skill(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Assemble the skill markdown from skill_author's structured output and
    write it to data/skills/<skill_name>.md.
    """
    skill_data: dict[str, Any] | None = None
    for step in reversed(state.steps):
        if step.status != "completed":
            continue
        out = step.output or {}
        if isinstance(out.get("frontmatter"), dict) and isinstance(out.get("body"), dict):
            skill_data = out
            break
    if not skill_data:
        raise ValueError("publish_skill: no upstream skill_author output found in workspace")

    skill_name = skill_data.get("skill_name") or (skill_data.get("frontmatter") or {}).get("name")
    if not skill_name:
        raise ValueError("publish_skill: skill_name missing from skill_author output")

    md_text = _assemble_skill_markdown(skill_data)
    skills_root = _skills_dir()
    skills_root.mkdir(parents=True, exist_ok=True)
    skill_dir = skills_root / skill_name
    # noted's SkillRegistry expects folder/<skill_name>/SKILL.md, not a flat
    # .md file. Use the folder convention. Writing SKILL.md atomically via
    # write-then-rename so the file watcher (F4) doesn't see a partial file.
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md_path = skill_dir / "SKILL.md"
    tmp = skill_md_path.with_suffix(".md.tmp")
    tmp.write_text(md_text)
    tmp.replace(skill_md_path)

    return {
        "skill_name": skill_name,
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_md_path),
        "byte_size": len(md_text),
    }


# ─── archive_tool / archive_skill ─────────────────────────────────


async def archive_tool(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    """Move data/tenants/<tenant_id>/user_tools/<name>/ to _archive/<name>_<ts>/."""
    wf_in = state.inputs or {}
    tool_name = wf_in.get("tool_name")
    if not tool_name:
        raise ValueError("archive_tool: tool_name missing from workflow inputs")

    tool_dir = _tenant_user_tools_dir(state.tenant_id) / tool_name
    if not tool_dir.is_dir():
        return {"tool_name": tool_name, "archived": False, "note": "tool_dir not found (already removed?)"}

    archive_root = _tenant_archive_dir(state.tenant_id)
    archive_root.mkdir(parents=True, exist_ok=True)
    _chown_tree_to_noted_tools(archive_root)
    ts = int(time.time() * 1000)
    archive_path = archive_root / f"{tool_name}_{ts}"
    shutil.move(str(tool_dir), str(archive_path))
    _chown_tree_to_noted_tools(archive_path)

    # Give noted-tools' file watcher (~50-200ms debounce) time to notice
    # the dir is gone before we pull the federation cache; otherwise we
    # refresh against a stale registry and the LLM keeps seeing the tool
    # for another 30s polling cycle.
    await asyncio.sleep(0.4)
    refreshed = await _refresh_user_tools_federation()

    return {
        "tool_name": tool_name,
        "archive_path": str(archive_path),
        "federation_refreshed": refreshed,
        "archived": True,
    }


async def archive_skill(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    """Move data/skills/<name>/ to data/skills/_archive/<name>_<ts>/.

    Skills aren't per-tenant in V1 (per the plan); the archive lives
    alongside the active skills dir.
    """
    wf_in = state.inputs or {}
    skill_name = wf_in.get("skill_name") or wf_in.get("tool_name")
    if not skill_name:
        raise ValueError("archive_skill: skill_name missing from workflow inputs")

    skill_dir = _skills_dir() / skill_name
    if not skill_dir.is_dir():
        return {"skill_name": skill_name, "archived": False, "note": "skill not found"}

    archive_root = _skills_dir() / "_archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    archive_path = archive_root / f"{skill_name}_{ts}"
    shutil.move(str(skill_dir), str(archive_path))
    return {
        "skill_name": skill_name,
        "archive_path": str(archive_path),
        "archived": True,
    }
