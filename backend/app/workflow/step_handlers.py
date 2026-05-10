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
import re
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
    """Fetch the API documentation URL(s) declared in workflow_inputs.

    Accepts either `api_docs_urls` (array, preferred) or `api_docs_url`
    (string, backward-compat). When neither is set or every URL is empty
    / "N/A", returns an empty doc and lets tool_author work from the
    mission alone. Multiple URLs are concatenated under `--- url: <url>
    ---` headers so the worker can reason across endpoints.
    """
    wf_in = state.inputs or {}

    raw_urls: list[str] = []
    arr = wf_in.get("api_docs_urls")
    if isinstance(arr, list):
        raw_urls.extend(str(u).strip() for u in arr if isinstance(u, str))
    single = wf_in.get("api_docs_url")
    if isinstance(single, str) and not raw_urls:
        raw_urls.append(single.strip())

    urls = [u for u in raw_urls if u and u.upper() != "N/A"]
    if not urls:
        return {
            "api_docs": "",
            "fetched_url": None,
            "fetched_urls": [],
            "skipped": True,
        }

    cap_total = 60_000
    per_url_cap = max(2_000, cap_total // len(urls))
    timeout = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)

    sections: list[str] = []
    fetched: list[str] = []
    any_truncated = False
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url, headers={"User-Agent": "noted-workflow/1.0"})
                resp.raise_for_status()
                text = resp.text
            except httpx.HTTPError as e:
                raise ValueError(
                    f"fetch_docs: {type(e).__name__} fetching {url}: {e}"
                ) from e
            truncated = len(text) > per_url_cap
            if truncated:
                text = text[:per_url_cap] + "\n\n[... truncated by fetch_docs ...]"
                any_truncated = True
            sections.append(f"--- url: {url} ---\n{text}")
            fetched.append(url)

    combined = "\n\n".join(sections)
    return {
        "api_docs": combined,
        "fetched_url": fetched[0] if len(fetched) == 1 else None,
        "fetched_urls": fetched,
        "skipped": False,
        "truncated": any_truncated,
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


# ─── validate_smoke_contract ──────────────────────────────────────


_OUTPUT_VERB = r"(?:contains?|returns?|includes?|produces?|emits?|outputs?|provides?|yields?|has|exposes?)"
_ARTICLE = r"(?:an?|the|some)"
_QUAL_WORD = r"[a-z][a-z\-]*"
_TYPE_WORD = r"(?:array|string|field|object|number|integer|boolean)"
_TYPE_WORDS_SET = {"array", "string", "field", "object", "number", "integer", "boolean"}
_CRITERIA_STOPWORDS = {
    "input", "output", "tool", "argument", "arguments", "fields",
    "the", "value", "type", "data", "json",
}

# Quoted keys: 'weather', "days", `extract`. Quoting is the planner's
# explicit signal that the token is a field name.
_QUOTED_KEY_RE = re.compile(r"['\"`]([a-zA-Z_][a-zA-Z0-9_]{1,40})['\"`]")

# Typed keys: only when anchored on an output-describing verb so we do
# not match arbitrary "<adjective> <type>" prose like "with string fields"
# or "integer field <name>". Pattern allows one optional qualifier word
# between article and id, and one between id and type.
_TYPED_KEY_RE = re.compile(
    # First qualifier slot is RELUCTANT (`??`) so the engine tries id at
    # the earliest position. Greedy here would eat "temperature" in
    # "contains a temperature numeric field", leaving id="numeric".
    rf"\b{_OUTPUT_VERB}\s+{_ARTICLE}\s+(?:{_QUAL_WORD}\s+)??"
    rf"([a-zA-Z_][a-zA-Z0-9_]{{2,40}})\s+(?:{_QUAL_WORD}\s+)?{_TYPE_WORD}\b",
    flags=re.IGNORECASE,
)


_OUTPUT_VERB_ANYWHERE_RE = re.compile(rf"\b{_OUTPUT_VERB}\b", flags=re.IGNORECASE)


def _extract_pinned_output_keys(criteria: list[Any]) -> set[str]:
    """Heuristic: pull identifiers that the criteria explicitly tag as
    output fields. Two patterns:
    (a) quoted identifiers (`'weather'`, `"days"`, `` `extract` ``)
    (b) output-verb-anchored typed phrases (`contains a non-empty days
        array`, `returns a temperature numeric field`).

    Per-criterion gate: only mine criteria whose text contains an
    output-describing verb anywhere. Otherwise quoted identifiers in
    INPUT or ERROR-behavior criteria (e.g. "exits if 'city_code' is
    absent") get falsely pinned as output requirements.

    Filters out matches whose captured id is itself a JSON type word."""
    pinned: set[str] = set()
    for criterion in criteria:
        text = str(criterion)
        if not _OUTPUT_VERB_ANYWHERE_RE.search(text):
            continue
        for m in _QUOTED_KEY_RE.finditer(text):
            w = m.group(1)
            if w.lower() in _TYPE_WORDS_SET or w.lower() in _CRITERIA_STOPWORDS:
                continue
            pinned.add(w)
        for m in _TYPED_KEY_RE.finditer(text):
            w = m.group(1)
            if w.lower() in _TYPE_WORDS_SET or w.lower() in _CRITERIA_STOPWORDS:
                continue
            pinned.add(w)
    return pinned


async def validate_smoke_contract(
    state: WorkspaceState, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Coverage check: every output key the acceptance_criteria pin MUST be
    asserted somewhere in smoke.py. Catches the api_tester-asserts-on-
    WRONG-key class (criteria say `days`, smoke asserts `forecast` →
    `days` missing). Permissive on extras: smoke.py may assert on keys
    the criteria mention but don't formally pin (multi-mode tools where
    a secondary mode's output isn't named in any criterion). Rewinds to
    api_tester via A2 on failure."""
    api_tester_out = _previous(inputs, "api_tester") or _previous(inputs)
    files: dict[str, str] = api_tester_out.get("files") or {}
    smoke_src = files.get("smoke.py") or ""
    if not smoke_src.strip():
        return {"ok": True, "checked": False, "reason": "no smoke.py to check"}

    workflow_inputs = inputs.get("workflow_inputs") or {}
    criteria = workflow_inputs.get("acceptance_criteria") or []
    if not isinstance(criteria, list) or not criteria:
        return {"ok": True, "checked": False, "reason": "no acceptance_criteria"}

    pinned = _extract_pinned_output_keys(criteria)
    if not pinned:
        return {
            "ok": True, "checked": False,
            "reason": "no pinned output keys extractable from criteria",
        }

    try:
        tree = ast.parse(smoke_src, filename="smoke.py")
    except SyntaxError as e:
        # Smoke run will catch the SyntaxError; not our job.
        return {"ok": True, "checked": False, "reason": f"smoke.py SyntaxError: {e}"}

    asserted: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "output"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            asserted.add(node.slice.value)
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            for op, right in zip(node.ops, node.comparators):
                if (
                    isinstance(op, ast.In)
                    and isinstance(right, ast.Name)
                    and right.id == "output"
                ):
                    asserted.add(node.left.value)

    missing = sorted(k for k in pinned if k not in asserted)
    if missing:
        raise ValueError(
            f"validate_smoke_contract: smoke.py is missing asserts for output keys "
            f"{missing} that the acceptance_criteria pin. Add asserts that check "
            f"for these keys in the tool's output. asserted={sorted(asserted)} "
            f"acceptance_criteria={criteria}"
        )

    return {
        "ok": True,
        "checked": True,
        "pinned_keys": sorted(pinned),
        "asserted_keys": sorted(asserted),
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

    # F3.5: also write api_tester's smoke.py + merge additional_requirements
    # into requirements.txt so the run_smoke_tests step can `pytest smoke.py`
    # against the published tool's venv.
    api_tester_out: dict[str, Any] | None = None
    for step in reversed(state.steps):
        if step.status != "completed":
            continue
        out = step.output or {}
        if "smoke.py" in (out.get("files") or {}) or "smoke.js" in (out.get("files") or {}):
            api_tester_out = out
            break
    if api_tester_out:
        smoke_files = api_tester_out.get("files") or {}
        for fname, content in smoke_files.items():
            (tool_dir / fname).write_text(content)
        # Merge additional_requirements (pytest etc.) into requirements.txt.
        extras = api_tester_out.get("additional_requirements") or []
        if extras and isinstance(extras, list):
            req_path = tool_dir / "requirements.txt"
            existing = req_path.read_text() if req_path.is_file() else ""
            existing_lines = {ln.strip() for ln in existing.splitlines() if ln.strip()}
            additions = [r for r in extras if isinstance(r, str) and r.strip() and r.strip() not in existing_lines]
            if additions:
                merged = existing.rstrip() + ("\n" if existing.strip() else "") + "\n".join(additions) + "\n"
                req_path.write_text(merged)

    # Hand ownership to noted-tools so its UID-1000 executor can build the venv.
    _chown_tree_to_noted_tools(tool_dir)

    # Same debounce-window settle as archive_tool: noted-tools' watcher
    # needs ~50-200ms to register the new dir; refresh BEFORE that races.
    await asyncio.sleep(0.4)
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


async def run_smoke_tests(state: WorkspaceState, inputs: dict[str, Any]) -> dict[str, Any]:
    """F3.5: invoke noted-tools' /admin/run-smoke-tests/<tool_name> after the
    tool is published. Failure (non-zero exit) raises ValueError with the
    pytest tail; the loop's bounded-retry path feeds the failure back to
    the next iteration via inputs["validator_complaint"].

    Skipped (returns ok=True with skipped=True) if no smoke.py was authored
    upstream - keeps the framework forwards-compatible with workflows that
    don't pair an api_tester.
    """
    prev_publish = _previous(inputs, "publish_tool")
    if not prev_publish:
        for step in reversed(state.steps):
            if step.name == "publish_tool" and step.status == "completed":
                prev_publish = step.output or {}
                break
    if not prev_publish:
        raise ValueError("run_smoke_tests: no upstream publish_tool output found")

    tool_name = prev_publish.get("tool_name")
    if not tool_name:
        raise ValueError("run_smoke_tests: publish_tool did not record tool_name")

    tool_dir = Path(prev_publish.get("tool_dir") or "")
    if not (tool_dir / "smoke.py").is_file():
        return {
            "tool_name": tool_name,
            "ok": True,
            "skipped": True,
            "note": "no smoke.py present (api_tester step omitted from this workflow)",
        }

    # F3.5: HTTP to noted-tools admin endpoint. AsyncClient because the
    # underlying pytest run can take 10-60s; never block the event loop.
    import os
    base = os.environ.get("NOTED_TOOLS_URL", "http://noted-tools:7702")
    timeout = httpx.Timeout(connect=5.0, read=180.0, write=5.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base}/admin/run-smoke-tests/{tool_name}")
            resp.raise_for_status()
            verdict = resp.json()
    except httpx.HTTPError as e:
        raise ValueError(f"run_smoke_tests: noted-tools call failed: {type(e).__name__}: {e}") from e

    if not verdict.get("ok"):
        # Pytest's stdout has the actual failure messages; stderr typically
        # carries the warning summary. Truncate both for the validator
        # complaint while keeping enough signal for the next iteration.
        stdout_tail = (verdict.get("stdout") or "")[-2000:]
        stderr_tail = (verdict.get("stderr") or "")[-500:]
        raise ValueError(
            f"smoke tests failed (exit={verdict.get('exit_code')}). "
            f"pytest output tail: {stdout_tail} | stderr: {stderr_tail}"
        )

    return {
        "tool_name": tool_name,
        "ok": True,
        "skipped": False,
        "exit_code": verdict.get("exit_code", 0),
        "stdout_tail": (verdict.get("stdout") or "")[-1000:],
    }


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
# Frontmatter uses inline YAML list syntax for `triggers` (the noted
# SkillRegistry parser only handles `key: [a, b]` style, not the multi-line
# form). Other fields are simple key:value lines.
#
# F6.4: provenance + source_workflow lineage flat-keyed (provenance,
# created_at, created_by, source_workflow_id, source_workflow_type,
# source_workflow_tenant) so the registry parser captures them via its
# generic key:value loop. The inspector reconstructs the source_workflow
# dict from those keys.

_FIXED_FM_ORDER = ["name", "description", "type", "priority", "max_tokens",
                   "provenance", "created_at", "created_by",
                   "source_workflow_id", "source_workflow_type",
                   "source_workflow_tenant"]


def _quote_yaml_inline(value: str) -> str:
    safe = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{safe}"'


def _render_yaml_frontmatter(fm: dict[str, Any]) -> str:
    """Render a flat dict as YAML frontmatter. Lists become inline
    `[a, b]` form (compatible with noted's SkillRegistry parser); other
    values render as `key: value`. Stable ordering for known keys
    (per _FIXED_FM_ORDER) so diffs stay readable."""
    out: list[str] = []
    seen: set[str] = set()
    keys = [k for k in _FIXED_FM_ORDER if k in fm] + [k for k in fm if k not in _FIXED_FM_ORDER and k != "triggers"]
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        v = fm[k]
        if v is None or v == "":
            continue
        out.append(f"{k}: {v}")
    triggers = fm.get("triggers") or []
    if triggers:
        triggers_inline = ", ".join(_quote_yaml_inline(t) for t in triggers)
        out.append(f"triggers: [{triggers_inline}]")
    return "\n".join(out)


def _assemble_skill_markdown(skill_data: dict[str, Any]) -> str:
    fm = dict(skill_data.get("frontmatter") or {})
    body = skill_data.get("body") or {}
    fm.setdefault("name", skill_data.get("skill_name") or "")
    fm.setdefault("type", "tool_skill")
    fm.setdefault("priority", 2)
    fm.setdefault("max_tokens", 500)
    inputs_md = "\n".join(f"- {x}" for x in (body.get("inputs") or []))
    output_md = "\n".join(f"- {x}" for x in (body.get("output_shape") or []))
    examples_md = "\n".join(f"- {x}" for x in (body.get("examples") or []))
    when_not = body.get("when_not_to_use") or ""
    when_block = f"\n**When NOT to use**\n{when_not}\n" if when_not else ""
    return (
        "---\n"
        + _render_yaml_frontmatter(fm)
        + "\n---\n"
        + f"**Purpose**\n{body.get('purpose') or ''}\n\n"
        + f"**Inputs**\n{inputs_md}\n\n"
        + f"**Output shape**\n{output_md}\n\n"
        + f"**Examples**\n{examples_md}\n"
        + when_block
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

    # Tool name from the workflow inputs is the source of truth — the skill
    # is the tool's companion and they MUST share one identity. If
    # skill_author drifted (renamed it, paraphrased, abbreviated), override
    # silently rather than publishing the skill at a different path than
    # the user expects. The prompt also forbids drift; this is the safety
    # net. Without this, tool=foo + skill=bar can ship and the user
    # cannot find the skill in the Skills tree under the tool's name.
    canonical_name = (state.inputs or {}).get("tool_name") or skill_data.get("skill_name")
    skill_authored_name = skill_data.get("skill_name") or (skill_data.get("frontmatter") or {}).get("name")
    if canonical_name and skill_authored_name and canonical_name != skill_authored_name:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "publish_skill: skill_author named the skill %r but the tool is %r — overriding to keep tool/skill paired",
            skill_authored_name, canonical_name,
        )
    skill_name = canonical_name or skill_authored_name
    if not skill_name:
        raise ValueError("publish_skill: skill_name missing from skill_author output")

    # F6.4: inject provenance + source_workflow lineage into frontmatter so
    # the SkillRegistry parser captures them and the inspector can link
    # back to the source workflow. Mirrors publish_tool's _meta lineage
    # injection.
    from datetime import datetime, timezone
    skill_data = dict(skill_data)
    fm = dict(skill_data.get("frontmatter") or {})
    # Force frontmatter name to match the canonical skill_name. SkillRegistry
    # keys the registry by frontmatter.name, so a mismatch between folder
    # and frontmatter would have the skill load under the wrong name even
    # though the folder is correct.
    fm["name"] = skill_name
    fm["provenance"] = "user"
    fm["created_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    fm["created_by"] = state.actor_id
    fm["source_workflow_id"] = state.workflow_id
    fm["source_workflow_type"] = state.workflow_type
    fm["source_workflow_tenant"] = state.tenant_id
    skill_data["frontmatter"] = fm
    # Also mirror the canonical name in skill_data.skill_name so any
    # downstream consumer reading either field gets the same answer.
    skill_data["skill_name"] = skill_name

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
