"""LSP WebSocket endpoint.

Provides /ws/lsp for bidirectional relay between browser LSP clients
and language server processes managed by LSPProxyManager.
"""

import asyncio
import json
import logging
import os
import re
import subprocess

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel

from app.managers.lsp import (
    get_strategy_by_language,
    get_strategy_by_file,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Set by main.py at startup
_lsp_manager = None


def _enrich_diagnostics(message: dict):
    """Enrich diagnostic messages with rule code, category, and docs URL.

    codemirror-languageserver only renders the 'message' field from
    LSP diagnostics, ignoring 'code' and 'codeDescription'. This
    injects that info into the message text using a structured format
    that the frontend's linkify observer parses into styled elements.

    Per-language enrichment is delegated to the file's strategy.
    """
    if message.get("method") != "textDocument/publishDiagnostics":
        return
    uri = message.get("params", {}).get("uri", "")
    strategy = get_strategy_by_file(uri)
    for diag in message.get("params", {}).get("diagnostics", []):
        code = diag.get("code")
        msg = diag.get("message", "")
        if not msg:
            continue
        strategy.enrich_diagnostic(diag, code, msg)


def set_lsp_manager(manager):
    global _lsp_manager
    _lsp_manager = manager


def _resolve_project_root(project_id: str) -> str:
    """Get the real filesystem path for a project."""
    from app.managers.project_registry import get_registry
    try:
        return get_registry().resolve(project_id)
    except Exception:
        return f"/app/data/projects/{project_id}"


def _resolve_runtime_id(env_name: str, language: str) -> str | None:
    """Look up the runtime_id for an env name, scoped by language.

    Multiple languages can have envs with the same name, so we filter by
    the language hint that the WebSocket client provides. Returns None if
    no match is found - in that case lsp_manager runs without per-runtime
    env injection (the historical Python/JS behavior).
    """
    if not _lsp_manager or not env_name:
        return None
    env_mgr = getattr(_lsp_manager, "_env_manager", None)
    if env_mgr is None:
        return None
    inner = getattr(env_mgr, "env_manager", env_mgr)
    try:
        envs = inner.list_envs()
    except Exception:
        return None
    for entry in envs:
        if entry.get("name") != env_name:
            continue
        if language and entry.get("language") and entry["language"] != language:
            continue
        return entry.get("runtime_id")
    return None


def _rewrite_uri_to_real(uri: str, project_id: str, real_root: str) -> str:
    """Translate virtual URI to real filesystem path for jedi."""
    prefix = f"file:///{project_id}/"
    if uri.startswith(prefix):
        return f"file://{real_root}/{uri[len(prefix):]}"
    prefix2 = f"file:///{project_id}"
    if uri == prefix2:
        return f"file://{real_root}"
    return uri


def _rewrite_uri_to_virtual(uri: str, project_id: str, real_root: str) -> str:
    """Translate real filesystem URI back to virtual URI for the frontend."""
    prefix = f"file://{real_root}/"
    if uri.startswith(prefix):
        return f"file:///{project_id}/{uri[len(prefix):]}"
    prefix2 = f"file://{real_root}"
    if uri == prefix2:
        return f"file:///{project_id}"
    return uri


def _rewrite_lsp_uris(message: dict, rewrite_fn) -> dict:
    """Shallow rewrite of URIs in common LSP message locations."""
    import copy
    msg = copy.deepcopy(message)
    params = msg.get("params", {})
    # initialize: rootUri
    if "rootUri" in params:
        params["rootUri"] = rewrite_fn(params["rootUri"])
    # textDocument/didOpen, didChange, didClose, completion, hover, definition, etc.
    td = params.get("textDocument", {})
    if "uri" in td:
        td["uri"] = rewrite_fn(td["uri"])
    # definition/references response: result[].uri or result[].targetUri
    result = msg.get("result")
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                if "uri" in item:
                    item["uri"] = rewrite_fn(item["uri"])
                if "targetUri" in item:
                    item["targetUri"] = rewrite_fn(item["targetUri"])
    elif isinstance(result, dict) and "uri" in result:
        result["uri"] = rewrite_fn(result["uri"])
    # diagnostics: params.uri
    if "uri" in params:
        params["uri"] = rewrite_fn(params["uri"])
    return msg


# Methods routed to jedi (completions, navigation, hover)
_JEDI_METHODS = {
    'textDocument/completion', 'textDocument/hover',
    'textDocument/definition', 'textDocument/references',
    'textDocument/rename', 'textDocument/signatureHelp',
    'completionItem/resolve',
}
# Methods sent to both servers (document sync)
_SYNC_METHODS = {
    'textDocument/didOpen', 'textDocument/didChange', 'textDocument/didClose',
}


@router.websocket("/ws/lsp")
async def lsp_websocket(
    websocket: WebSocket,
    project: str = Query(...),
    env: str = Query(""),
    server: str = Query("ruff"),
    language: str = Query("python"),
):
    """WebSocket endpoint for LSP communication.

    Language-aware: starts the appropriate servers based on the language param.
    - Python: ruff (diagnostics/formatting) + jedi (completions/navigation)
    - JavaScript: biome (diagnostics/formatting) + tsserver (completions/navigation)
    """
    await websocket.accept()

    if not _lsp_manager:
        await websocket.close(code=1011, reason="LSP not available")
        return

    jedi = None
    try:
        # Resolve real project root for URI rewriting (jedi needs real paths)
        real_root = _resolve_project_root(project)
        to_real = lambda uri: _rewrite_uri_to_real(uri, project, real_root)
        to_virtual = lambda uri: _rewrite_uri_to_virtual(uri, project, real_root)

        # Per-language strategy drives server selection, URI rewriting,
        # diagnostic handling, and init capability merging.
        strategy = get_strategy_by_language(language)
        lint_type = strategy.lint_server_type
        completion_type = strategy.completion_server_type

        # Resolve runtime_id from env_name when the language needs per-runtime
        # env vars at LSP launch (R needs R_HOME / LD_LIBRARY_PATH per version).
        runtime_id = _resolve_runtime_id(env, language) if env else None

        # Start primary server
        ruff = await _lsp_manager.get_or_start(
            project, env, lint_type, runtime_id=runtime_id
        )
        ruff._ws_clients.add(websocket)

        # Start completion server if separate from linter
        if completion_type:
            try:
                jedi = await _lsp_manager.get_or_start(
                    project, env, completion_type, runtime_id=runtime_id
                )
                jedi._ws_clients.add(websocket)
                logger.info("LSP WebSocket connected: project=%s (%s + %s)",
                            project, lint_type, completion_type)
            except Exception as e:
                logger.warning("%s not available for %s: %s", completion_type, project, e)
                logger.info("LSP WebSocket connected: project=%s (%s only)",
                            project, lint_type)
        else:
            logger.info("LSP WebSocket connected: project=%s (%s)",
                        project, lint_type)

        # Broadcast from a server to all connected WebSocket clients
        def make_broadcast(srv):
            async def broadcast(message: dict):
                # Handle workspace/configuration requests (biome, tsserver)
                if message.get("method") == "workspace/configuration" and "id" in message:
                    items = message.get("params", {}).get("items", [])
                    await srv.send({
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": [None] * len(items) if items else [None],
                    })
                    return

                if not srv._initialized and srv._pending_init_id is not None:
                    msg_id = message.get("id")
                    if msg_id == srv._pending_init_id:
                        if "result" in message:
                            srv._init_result = message["result"]
                            srv._initialized = True
                            srv._init_event.set()
                        elif "error" in message:
                            logger.error("LSP %s init failed: %s", srv.server_type, message["error"])
                            srv._init_event.set()  # unblock waiter

                # Resolve pending request futures (for REST API hover etc.)
                resp_id = message.get("id")
                if resp_id is not None and ("result" in message or "error" in message):
                    srv.resolve_pending(resp_id, message.get("result") or message.get("error"))
                    # Don't forward internal responses to WebSocket clients
                    if isinstance(resp_id, str) and (resp_id.startswith("req-") or resp_id.startswith("ruff-") or resp_id.startswith("jedi-") or resp_id.startswith("nb-")):
                        return

                # Strategy decides whether to suppress diagnostics from this server
                if (strategy.drop_diagnostics_from(srv.server_type)
                        and message.get("method") == "textDocument/publishDiagnostics"):
                    return

                # Strategy decides whether this server's responses need URI rewriting
                if strategy.rewrite_to_virtual_for(srv.server_type):
                    message = _rewrite_lsp_uris(message, to_virtual)

                _enrich_diagnostics(message)
                # Strip per-item documentation from completion responses;
                # codemirror-languageserver otherwise renders a side panel
                # attached to the completion dropdown, duplicating the
                # external Documentation panel.
                _result = message.get("result")
                if isinstance(_result, dict) and "items" in _result:
                    for _item in _result.get("items") or []:
                        if isinstance(_item, dict):
                            _item.pop("documentation", None)
                elif isinstance(_result, list):
                    for _item in _result:
                        if isinstance(_item, dict) and "label" in _item:
                            _item.pop("documentation", None)
                clients = list(srv._ws_clients)
                for ws in clients:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        srv._ws_clients.discard(ws)

                for cb in getattr(srv, '_nb_diagnostic_callbacks', []):
                    try:
                        await cb(message)
                    except Exception as e:
                        logger.debug("Notebook diagnostic callback error: %s", e)
            return broadcast

        # Start read loops
        if not ruff._read_task or ruff._read_task.done():
            ruff._read_task = asyncio.create_task(ruff.read_loop(make_broadcast(ruff)))
        if jedi and (not jedi._read_task or jedi._read_task.done()):
            jedi._read_task = asyncio.create_task(jedi.read_loop(make_broadcast(jedi)))

        # Resolve venv path for jedi's environment_path
        venv_env_path = None
        if env:
            try:
                from app.managers.venv_manager import VenvManager
                vm = VenvManager()
                python = vm.get_python_path(env)
                # environment_path is the venv dir (parent of bin/)
                import os
                venv_env_path = os.path.dirname(os.path.dirname(python))
            except Exception:
                pass

        # Initialize both servers
        async def _init_server(srv, init_id, data):
            if srv._initialized and srv._init_result:
                logger.info("LSP %s already initialized", srv.server_type)
                return srv._init_result
            logger.info("LSP %s initializing (id=%s)...", srv.server_type, init_id)
            import copy
            msg = copy.deepcopy(data)
            msg["id"] = init_id
            # Rewrite rootUri to real filesystem path (frontend sends virtual URIs)
            params = msg.setdefault("params", {})
            if "rootUri" in params:
                virtual_root = params["rootUri"]
                # Extract project ID from file:///projectId
                parts = virtual_root.replace("file:///", "").split("/")
                if parts:
                    proj_id = parts[0]
                    real_root = _resolve_project_root(proj_id)
                    params["rootUri"] = f"file://{real_root}"
            # Force dynamicRegistration=false so servers advertise capabilities
            # statically (codemirror-languageserver doesn't handle dynamic registration)
            caps = params.setdefault("capabilities", {})
            td = caps.setdefault("textDocument", {})
            for key in ("completion", "hover", "signatureHelp", "definition",
                        "references", "rename", "diagnostics", "synchronization"):
                if key in td and isinstance(td[key], dict):
                    td[key]["dynamicRegistration"] = False
            # Strategy-specific init options (e.g., jedi environment_path)
            strategy.inject_init_options(params, srv.server_type, venv_env_path)
            srv._pending_init_id = init_id
            srv._init_event.clear()
            await srv.send(msg)
            try:
                init_timeout = 30.0 if srv.server_type == "tsserver" else 10.0
                await asyncio.wait_for(srv._init_event.wait(), timeout=init_timeout)
            except asyncio.TimeoutError:
                logger.warning("LSP %s init timed out (id=%s, pending=%s)", srv.server_type, init_id, srv._pending_init_id)
                # Kill timed-out server so a fresh one is created next time
                await srv.shutdown()
                key = next((k for k, v in _lsp_manager._servers.items() if v is srv), None)
                if key:
                    _lsp_manager._servers.pop(key, None)
                return None
            logger.info("LSP %s initialized OK", srv.server_type)
            if not srv._server_notified:
                srv._server_notified = True
                await srv.send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
            return srv._init_result

        # Relay WebSocket messages to the appropriate server(s)
        try:
            while True:
                data = await websocket.receive_json()
                method = data.get("method")
                msg_id = data.get("id")

                # Initialize: send to both, merge capabilities, reply once
                if method == "initialize":
                    if ruff._initialized and ruff._init_result:
                        # Reuse cached init result but re-apply strategy
                        # overrides so changes to capability handling
                        # propagate across websocket reconnects without
                        # a container restart.
                        result = dict(ruff._init_result)
                        result = strategy.complete_init_capabilities(
                            result, has_completion_server=jedi is not None
                        )
                        await websocket.send_json({
                            "jsonrpc": "2.0", "id": msg_id, "result": result,
                        })
                        continue

                    # Initialize primary server, respond immediately
                    ruff_result = await _init_server(ruff, f"ruff-{msg_id}", data)
                    result = dict(ruff_result) if ruff_result else {"capabilities": {}}

                    # Strategy applies the correct capability merge
                    # (dual-server languages inject completion/navigation caps;
                    # single-server languages fill in completionProvider fallback).
                    result = strategy.complete_init_capabilities(
                        result, has_completion_server=jedi is not None
                    )

                    ruff._init_result = result
                    await websocket.send_json({
                        "jsonrpc": "2.0", "id": msg_id, "result": result,
                    })

                    # Initialize the completion server in background, then
                    # replay buffered sync messages (honoring per-strategy
                    # URI rewriting).
                    if jedi:
                        jedi._pending_sync = []  # buffer sync messages until init completes
                        needs_rewrite = strategy.rewrite_to_real_for(jedi.server_type)
                        async def _init_jedi_and_replay():
                            await _init_server(jedi, f"jedi-{msg_id}", data)
                            if jedi._initialized:
                                for buffered in getattr(jedi, '_pending_sync', []):
                                    payload = (
                                        _rewrite_lsp_uris(buffered, to_real)
                                        if needs_rewrite
                                        else buffered
                                    )
                                    await jedi.send(payload)
                                jedi._pending_sync = None
                        asyncio.create_task(_init_jedi_and_replay())
                    continue

                # Initialized notification: send to ruff now, jedi after its init completes
                if method == "initialized":
                    if not ruff._server_notified:
                        ruff._server_notified = True
                        await ruff.send(data)
                    # Jedi gets 'initialized' from _init_server's background task
                    continue

                # Document sync: always sent to the primary (lint) server.
                # If a completion server is present, mirror to it, honoring
                # per-strategy URI rewriting (jedi and tsserver need real paths).
                if method in _SYNC_METHODS:
                    await ruff.send(data)
                    if jedi:
                        payload = (
                            _rewrite_lsp_uris(data, to_real)
                            if strategy.rewrite_to_real_for(jedi.server_type)
                            else data
                        )
                        if jedi._initialized:
                            await jedi.send(payload)
                        elif hasattr(jedi, '_pending_sync') and jedi._pending_sync is not None:
                            jedi._pending_sync.append(data)
                    continue

                # Navigation/completion: route to the completion server when
                # present, otherwise to the primary server (single-server mode).
                if method in _JEDI_METHODS:
                    if jedi and jedi._initialized:
                        payload = (
                            _rewrite_lsp_uris(data, to_real)
                            if strategy.rewrite_to_real_for(jedi.server_type)
                            else data
                        )
                        await jedi.send(payload)
                    elif not jedi:
                        await ruff.send(data)
                    continue

                # Everything else (formatting, code actions, etc.): route to ruff
                await ruff.send(data)

        except WebSocketDisconnect:
            pass

    except Exception as e:
        logger.error("LSP WebSocket error: %s", e)
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass

    finally:
        if _lsp_manager:
            for st in [lint_type, completion_type]:
                if st is None:
                    continue
                key = (project, env, st)
                srv = _lsp_manager._servers.get(key)
                if srv:
                    srv._ws_clients.discard(websocket)
        logger.info("LSP WebSocket disconnected: project=%s env=%s", project, env)


_docutils_css_cache = None

def _get_docutils_css() -> str:
    """Get the docutils default stylesheet (cached)."""
    global _docutils_css_cache
    if _docutils_css_cache is None:
        try:
            from docutils.core import publish_parts
            parts = publish_parts(source='', writer_name='html')
            import re
            match = re.search(r'<style[^>]*>(.*?)</style>', parts.get('stylesheet', ''), re.DOTALL)
            _docutils_css_cache = match.group(1) if match else ''
        except Exception:
            _docutils_css_cache = ''
    return _docutils_css_cache


async def _runtime_docstring_for_position(project: str, env: str, filename: str,
                                           line: int, character: int) -> str | None:
    """Resolve symbol at position and fetch its runtime docstring."""
    import subprocess as sp

    # Read the file to get source
    real_root = _resolve_project_root(project)
    filepath = os.path.join(real_root, filename)
    if not os.path.isfile(filepath):
        return None
    with open(filepath, 'r') as f:
        source = f.read()

    # Use jedi to resolve the full qualified name
    try:
        import jedi
        script = jedi.Script(source, path=filepath)
        names = script.goto(line + 1, character)  # jedi uses 1-based lines
        if not names:
            names = script.infer(line + 1, character)
        if not names:
            return None
        name = names[0]
        full_name = name.full_name
        if not full_name:
            return None
    except Exception:
        return None

    return _runtime_docstring(full_name, env)


def _runtime_docstring(symbol: str, env_name: str = "") -> str | None:
    """Fetch a docstring at runtime using the project's venv Python.

    Fallback for C-extension functions where jedi returns empty docs.
    """
    import subprocess

    # Resolve python path
    python = "python3"
    if env_name:
        try:
            from app.managers.venv_manager import VenvManager
            vm = VenvManager()
            python = vm.get_python_path(env_name)
        except Exception:
            pass

    # Build a safe import + __doc__ fetch
    # symbol is like "numpy.arange" or "matplotlib.pyplot.plot"
    parts = symbol.rsplit('.', 1)
    if len(parts) != 2:
        return None
    module_path, attr = parts

    code = (
        f"import {module_path} as _m\n"
        f"_obj = getattr(_m, '{attr}', None)\n"
        f"if _obj and _obj.__doc__:\n"
        f"    print(_obj.__doc__)\n"
    )

    try:
        result = subprocess.run(
            [python, "-c", code],
            capture_output=True, text=True, timeout=5,
        )
        doc = result.stdout.strip()
        return doc if doc else None
    except Exception:
        return None


def _preprocess_rst(text: str) -> str:
    """Fix common patterns that docutils doesn't handle well.

    - Strip markdown code fences (```language) that leak into reST content
    - Convert 'name -- description' lists (no blank lines) into reST definition lists
    """
    # Strip markdown code fences
    text = re.sub(r'^```\w*\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)
    lines = text.split('\n')
    result = []
    in_dash_list = False

    for line in lines:
        # Detect "name -- description" pattern (common in module docstrings)
        m = re.match(r'^(\w[\w.]*(?:\(\))?)\s+--\s+(.+)$', line)
        if m:
            if not in_dash_list and result and result[-1].strip():
                result.append('')  # blank line before list
            in_dash_list = True
            result.append(m.group(1))
            result.append(f'   {m.group(2)}')
        else:
            if in_dash_list and line.strip():
                result.append('')  # blank line after list
            in_dash_list = False
            result.append(line)

    return '\n'.join(result)


def _rst_to_html(text: str) -> str | None:
    """Convert reST text to an HTML fragment using docutils.

    Returns None if docutils is unavailable or parsing fails badly.
    """
    try:
        from docutils.core import publish_parts
        from docutils.utils import Reporter

        text = _preprocess_rst(text)

        parts = publish_parts(
            source=text,
            writer_name='html',
            settings_overrides={
                'report_level': Reporter.SEVERE_LEVEL,
                'halt_level': Reporter.SEVERE_LEVEL,
                'initial_header_level': 2,
            },
        )
        return parts.get('fragment', '')
    except Exception:
        return None


def _parse_docstring(raw: str) -> dict | None:
    """Parse a jedi hover response into structured documentation.

    Input format: "signature\\n---\\ndocstring"
    Returns: {signature, description, params, returns, raises, examples, notes}
    """
    try:
        import docstring_parser
    except ImportError:
        return None

    parts = raw.split('\n---\n', 1)
    signature = parts[0].strip() if len(parts) > 1 else None
    doctext = parts[1].strip() if len(parts) > 1 else parts[0].strip()

    # Strip markdown code fences from signature (```python\n...\n```)
    if signature and signature.startswith('```'):
        sig_lines = signature.split('\n')
        sig_lines = [l for l in sig_lines if not l.startswith('```')]
        signature = '\n'.join(sig_lines).strip()

    # Strip reST overline/underline headings that confuse docstring_parser
    import re
    doctext_lines = doctext.split('\n')
    cleaned = []
    for i, line in enumerate(doctext_lines):
        if re.match(r'^[=*~\-^]{3,}$', line.strip()):
            continue  # skip section underlines/overlines
        cleaned.append(line)
    doctext = '\n'.join(cleaned)

    try:
        parsed = docstring_parser.parse(doctext)
    except Exception:
        return None

    result = {"signature": signature}

    if parsed.short_description:
        result["description"] = parsed.short_description
    if parsed.long_description:
        result["long_description"] = parsed.long_description

    if parsed.params:
        result["params"] = [
            {"name": p.arg_name, "type": p.type_name, "description": p.description or ""}
            for p in parsed.params
        ]

    if parsed.returns:
        result["returns"] = parsed.returns.description

    if parsed.raises:
        result["raises"] = [
            {"type": r.type_name, "description": r.description or ""}
            for r in parsed.raises
        ]

    examples = []
    notes = []
    for m in parsed.meta:
        cls = type(m).__name__
        if cls == 'DocstringExample' or (hasattr(m, 'args') and 'examples' in m.args):
            if m.description:
                examples.append(m.description)
        elif cls == 'DocstringMeta' and hasattr(m, 'args') and 'notes' in m.args:
            if m.description:
                notes.append(m.description)

    if examples:
        result["examples"] = examples
    if notes:
        result["notes"] = notes

    return result


class HoverRequest(BaseModel):
    project: str
    env: str = ""
    filename: str
    line: int
    character: int


def _server_type_for_file(filename: str) -> tuple[str, bool]:
    """Return (server_type, is_web) for a filename.

    For dual-server languages, the completion server handles hover.
    For single-server languages, the lint server handles hover.
    """
    strategy = get_strategy_by_file(filename)
    if strategy.completion_server_type:
        return strategy.completion_server_type, False
    # Single-server language (HTML/CSS/JSON)
    return strategy.lint_server_type, True


def _find_initialized_server(project: str, server_type: str):
    """Find an existing initialized server (no start, no side effects)."""
    if not _lsp_manager:
        return None
    # Try empty env first (file editors use empty env for non-Python)
    for env_key in ["", None]:
        key = (project, env_key or "", server_type)
        srv = _lsp_manager._servers.get(key)
        if srv and srv.alive and srv._initialized:
            return srv
    # Search all envs
    for key, srv in _lsp_manager._servers.items():
        if key[0] == project and key[2] == server_type and srv.alive and srv._initialized:
            return srv
    return None


@router.post("/api/lsp/hover")
async def lsp_hover(req: HoverRequest):
    """Get hover documentation for a symbol at the given position."""
    if not _lsp_manager:
        return {"contents": None}

    try:
        server_type, is_web = _server_type_for_file(req.filename)

        if is_web or server_type == "tsserver":
            server = _find_initialized_server(req.project, server_type)
            if not server:
                return {"contents": None}
            # tsserver gets real URIs (rewritten in WebSocket sync path)
            # Web servers get virtual URIs (no rewriting in sync path)
            if server_type == "tsserver":
                real_root = _resolve_project_root(req.project)
                doc_uri = f"file://{real_root}/{req.filename}"
            else:
                doc_uri = f"file:///{req.project}/{req.filename}"
            result = await server.request("textDocument/hover", {
                "textDocument": {"uri": doc_uri},
                "position": {"line": req.line, "character": req.character},
            })
            if not result or not result.get("contents"):
                return {"contents": None}
            contents = result["contents"]
            raw = contents.get("value", str(contents)) if isinstance(contents, dict) else str(contents)
            kind = contents.get("kind", "plaintext") if isinstance(contents, dict) else "plaintext"
            return {"contents": raw, "kind": kind}

        jedi = await _lsp_manager.get_or_start(req.project, req.env, "jedi")
        if not jedi._initialized:
            return {"contents": None}

        real_root = _resolve_project_root(req.project)
        real_uri = f"file://{real_root}/{req.filename}"

        result = await jedi.request("textDocument/hover", {
            "textDocument": {"uri": real_uri},
            "position": {"line": req.line, "character": req.character},
        })

        if not result or not result.get("contents"):
            # Fallback: try runtime docstring for C-extension functions
            doc = await _runtime_docstring_for_position(
                req.project, req.env, req.filename, req.line, req.character
            )
            if doc:
                body_html = _rst_to_html(doc)
                if body_html:
                    return {"contents": doc, "kind": "plaintext", "body_html": body_html}
                return {"contents": doc, "kind": "plaintext"}
            return {"contents": None}

        contents = result["contents"]
        raw = contents.get("value", str(contents)) if isinstance(contents, dict) else str(contents)
        kind = contents.get("kind", "plaintext") if isinstance(contents, dict) else "plaintext"

        # Check if jedi returned just a signature with no docstring body
        parts_check = raw.split('\n---\n', 1)
        body_check = parts_check[1].strip() if len(parts_check) > 1 else raw.strip()
        if not body_check or len(body_check) < 10:
            # Try runtime fallback
            doc = await _runtime_docstring_for_position(
                req.project, req.env, req.filename, req.line, req.character
            )
            if doc:
                sig = parts_check[0].strip() if len(parts_check) > 1 else None
                if sig and sig.startswith('```'):
                    sig = '\n'.join(l for l in sig.split('\n') if not l.startswith('```')).strip()
                body_html = _rst_to_html(doc)
                if body_html:
                    return {"contents": doc, "kind": "plaintext", "signature": sig, "body_html": body_html}

        # Parse for structured function docs (signature, params, returns)
        parsed = _parse_docstring(raw)
        has_structure = parsed and any(k in parsed for k in ('params', 'returns', 'raises'))
        if has_structure:
            # Function docs with params - use structured rendering
            if parsed.get('long_description'):
                html = _rst_to_html(parsed['long_description'])
                if html:
                    parsed['long_description_html'] = html
            return {"contents": raw, "kind": kind, "parsed": parsed}
        # No params - use docutils for the full body (avoids docstring_parser truncation)
        parts = raw.split('\n---\n', 1)
        signature = parts[0].strip() if len(parts) > 1 else None
        body = parts[1].strip() if len(parts) > 1 else raw.strip()
        if signature and signature.startswith('```'):
            sig_lines = signature.split('\n')
            signature = '\n'.join(l for l in sig_lines if not l.startswith('```')).strip()
        body_html = _rst_to_html(body)
        if body_html:
            return {"contents": raw, "kind": kind, "signature": signature, "body_html": body_html}
        return {"contents": raw, "kind": kind}
    except Exception as e:
        logger.debug("Hover request failed: %s", e)
        return {"contents": None}


class NotebookLSPRequest(BaseModel):
    project: str
    env: str = ""
    notebook_path: str
    cell_index: int
    content: str = ""  # current cell content (for up-to-date completions)
    line: int
    character: int


async def _get_notebook_bridge_and_jedi(req: NotebookLSPRequest):
    """Get the notebook LSP bridge and jedi server for a request.

    If req.content is provided, updates the shadow file with the current
    cell content before returning (ensures jedi sees the latest edits).
    """
    from app.main import nb_lsp_mgr, notebook_mgr, lsp_mgr
    bridge = nb_lsp_mgr.get(req.project, req.notebook_path)
    if not bridge or not bridge._cell_regions:
        return None, None, None, None

    # Pick the right completion server per language. R uses
    # languageserver per-env (not jedi); routing to jedi would silently
    # leave the LSP unaware of the new content and return stale items.
    srv_type, srv_env, srv_runtime = _notebook_completion_server_args(bridge)

    # Update shadow with current cell content if provided
    if req.content:
        nb = notebook_mgr.get_notebook(req.project, req.notebook_path)
        nb = notebook_mgr.prepare_for_wire(nb)
        shadow = bridge.update_cell(req.cell_index, req.content, nb)
        # Send didChange to the completion server
        try:
            jedi = await lsp_mgr.get_or_start(
                req.project, srv_env, srv_type, runtime_id=srv_runtime
            )
            if jedi._initialized:
                # JS per-cell: update the specific cell's shadow
                if bridge.language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
                    cell_info = bridge._js_cell_shadows.get(req.cell_index)
                    if cell_info:
                        await jedi.send({
                            "jsonrpc": "2.0",
                            "method": "textDocument/didChange",
                            "params": {
                                "textDocument": {"uri": cell_info["uri"], "version": cell_info["version"]},
                                "contentChanges": [{"text": cell_info["text"]}],
                            }
                        })
                else:
                    await jedi.send({
                        "jsonrpc": "2.0",
                        "method": "textDocument/didChange",
                        "params": {
                            "textDocument": {"uri": bridge.uri, "version": bridge.version},
                            "contentChanges": [{"text": shadow}],
                        }
                    })
        except Exception:
            pass

    # Find the cell region and map to shadow line
    region = None
    for r in bridge._cell_regions:
        if r.cell_index == req.cell_index and r.cell_type == 'code':
            region = r
            break
    if not region:
        return None, None, None, None

    # JS per-cell shadows: use cell URI directly, no line offset
    if bridge.language == "javascript" and hasattr(bridge, '_js_cell_shadows'):
        cell_info = bridge._js_cell_shadows.get(req.cell_index)
        if cell_info:
            return bridge, req.line, req.character, cell_info["uri"]

    # Python combined shadow: offset line to global position
    shadow_line = region.start_line + req.line
    return bridge, shadow_line, req.character, bridge.uri


def _notebook_completion_server_args(bridge):
    """Pick the right (server_type, env_name, runtime_id) tuple for a
    notebook completion or hover request, based on the bridge's language.

    - Python: shared jedi server, env_name=""
    - JavaScript: shared tsserver, env_name=""
    - R: per-env languageserver (single server handles both lint and
      completion); env_name + runtime_id MUST match what
      _start_notebook_lsp used or the cache key won't hit and a stray
      server will be spawned.
    """
    lang = getattr(bridge, "language", "python")
    if lang == "javascript":
        return "tsserver", "", None
    if lang == "r":
        return "languageserver", (getattr(bridge, "env_name", None) or ""), \
            getattr(bridge, "runtime_id", None)
    return "jedi", "", None


@router.post("/api/lsp/notebook/hover")
async def notebook_hover(req: NotebookLSPRequest):
    """Get hover documentation for a symbol in a notebook cell."""
    if not _lsp_manager:
        return {"contents": None}
    try:
        bridge, shadow_line, character, uri = await _get_notebook_bridge_and_jedi(req)
        if not bridge:
            return {"contents": None}
        srv_type, env_for_srv, runtime_for_srv = _notebook_completion_server_args(bridge)
        jedi = await _lsp_manager.get_or_start(
            req.project, env_for_srv, srv_type, runtime_id=runtime_for_srv
        )
        if not jedi._initialized:
            return {"contents": None}
        result = await jedi.request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": shadow_line, "character": character},
        })
        if not result or not result.get("contents"):
            # Fallback: runtime docstring using the shadow file
            shadow_source = bridge.shadow_text
            if shadow_source:
                try:
                    import jedi as jedi_lib
                    script = jedi_lib.Script(shadow_source)
                    names = script.goto(shadow_line + 1, character)
                    if not names:
                        names = script.infer(shadow_line + 1, character)
                    if names and names[0].full_name:
                        doc = _runtime_docstring(names[0].full_name, req.env)
                        if doc:
                            body_html = _rst_to_html(doc)
                            if body_html:
                                return {"contents": doc, "kind": "plaintext", "body_html": body_html}
                            return {"contents": doc, "kind": "plaintext"}
                except Exception:
                    pass
            return {"contents": None}
        contents = result["contents"]
        raw = contents.get("value", str(contents)) if isinstance(contents, dict) else str(contents)
        kind = contents.get("kind", "plaintext") if isinstance(contents, dict) else "plaintext"
        parsed = _parse_docstring(raw)
        has_structure = parsed and any(k in parsed for k in ('params', 'returns', 'raises'))
        if has_structure:
            if parsed.get('long_description'):
                html = _rst_to_html(parsed['long_description'])
                if html:
                    parsed['long_description_html'] = html
            return {"contents": raw, "kind": kind, "parsed": parsed}
        parts = raw.split('\n---\n', 1)
        signature = parts[0].strip() if len(parts) > 1 else None
        body = parts[1].strip() if len(parts) > 1 else raw.strip()
        if signature and signature.startswith('```'):
            sig_lines = signature.split('\n')
            signature = '\n'.join(l for l in sig_lines if not l.startswith('```')).strip()
        body_html = _rst_to_html(body)
        if body_html:
            return {"contents": raw, "kind": kind, "signature": signature, "body_html": body_html}
        return {"contents": raw, "kind": kind}
    except Exception as e:
        logger.debug("Notebook hover failed: %s", e)
        return {"contents": None}


@router.post("/api/lsp/notebook/complete")
async def notebook_complete(req: NotebookLSPRequest):
    """Get completions for a position in a notebook cell."""
    if not _lsp_manager:
        return {"items": []}
    try:
        bridge, shadow_line, character, uri = await _get_notebook_bridge_and_jedi(req)
        if not bridge:
            return {"items": []}
        srv_type, env_for_srv, runtime_for_srv = _notebook_completion_server_args(bridge)
        jedi = await _lsp_manager.get_or_start(
            req.project, env_for_srv, srv_type, runtime_id=runtime_for_srv
        )
        if not jedi._initialized:
            return {"items": []}
        result = await jedi.request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": shadow_line, "character": character},
        })
        if not result:
            return {"items": []}
        # LSP returns either a list or {isIncomplete, items}
        items = result.get("items", result) if isinstance(result, dict) else result
        if not isinstance(items, list):
            items = []
        return {"items": items}
    except Exception as e:
        logger.debug("Notebook completion failed: %s", e)
        return {"items": []}


class FormatRequest(BaseModel):
    project: str
    filename: str
    content: str


@router.post("/api/lsp/fixes")
async def get_fixes(req: FormatRequest):
    """Get available fixes for diagnostics using ruff check --output-format json."""
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ruff", "check", "--preview", "--output-format", "json", "-e",
                 "--stdin-filename", req.filename, "-"],
                input=req.content,
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )
        import json as json_mod
        diagnostics = json_mod.loads(result.stdout) if result.stdout else []
        # Return only fixable diagnostics with their edits
        fixes = []
        for d in diagnostics:
            if d.get("fix") and d["fix"].get("edits"):
                fixes.append({
                    "code": d["code"],
                    "message": d["message"],
                    "line": d["location"]["row"],
                    "fix_message": d["fix"]["message"],
                    "applicability": d["fix"]["applicability"],
                    "edits": d["fix"]["edits"],
                })
        return {"fixes": fixes}
    except Exception as e:
        return {"fixes": [], "error": str(e)}


class FixOneRequest(BaseModel):
    project: str
    filename: str
    content: str
    code: str  # rule code like F401, PIE790
    line: int  # line number of the diagnostic


@router.post("/api/lsp/fix-one")
async def fix_one(req: FixOneRequest):
    """Apply a single ruff fix for a specific diagnostic."""
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ruff", "check", "--preview", "--select", req.code, "--fix",
                 "--stdin-filename", req.filename, "-"],
                input=req.content,
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )
        fixed = result.stdout if result.stdout else req.content
        return {"fixed": fixed, "changed": fixed != req.content}
    except Exception as e:
        return {"fixed": req.content, "changed": False, "error": str(e)}


@router.post("/api/lsp/organize-imports")
async def organize_imports(req: FormatRequest):
    """Organize imports using ruff check --select I --fix."""
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["ruff", "check", "--preview", "--select", "I", "--fix", "--stdin-filename", req.filename, "-"],
                input=req.content,
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )
        return {"formatted": result.stdout if result.stdout else req.content}
    except Exception as e:
        return {"formatted": req.content, "error": str(e)}


@router.post("/api/lsp/format")
async def format_document(req: FormatRequest):
    """Format code using the appropriate formatter for the file type."""
    try:
        server_type, is_web = _server_type_for_file(req.filename)

        if server_type == "jedi":
            # Python: ruff format
            cmd = ["ruff", "format", "--stdin-filename", req.filename, "-"]
        elif server_type == "tsserver":
            # JavaScript/TypeScript: biome format
            cmd = ["biome", "format", "--stdin-file-path", req.filename]
        elif is_web:
            # HTML/CSS/JSON: use LSP textDocument/formatting via the server
            server = _find_initialized_server(req.project, server_type)
            if server:
                doc_uri = f"file:///{req.project}/{req.filename}"
                result = await server.request("textDocument/formatting", {
                    "textDocument": {"uri": doc_uri},
                    "options": {"tabSize": 4, "insertSpaces": True},
                }, timeout=10.0)
                if result and isinstance(result, list):
                    # Apply text edits to produce formatted output
                    formatted = req.content
                    for edit in sorted(result, key=lambda e: (-e["range"]["start"]["line"], -e["range"]["start"]["character"])):
                        lines = formatted.split('\n')
                        start = edit["range"]["start"]
                        end = edit["range"]["end"]
                        before = '\n'.join(lines[:start["line"]]) + ('\n' if start["line"] > 0 else '') + lines[start["line"]][:start["character"]]
                        after = lines[end["line"]][end["character"]:] + ('\n' if end["line"] < len(lines) - 1 else '') + '\n'.join(lines[end["line"]+1:])
                        formatted = before + edit["newText"] + after
                    return {"formatted": formatted}
            return {"formatted": req.content}
        else:
            return {"formatted": req.content}

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                input=req.content,
                capture_output=True,
                text=True,
                timeout=10,
            ),
        )
        if result.returncode == 0:
            return {"formatted": result.stdout}
        return {"formatted": req.content, "error": result.stderr}
    except Exception as e:
        return {"formatted": req.content, "error": str(e)}
