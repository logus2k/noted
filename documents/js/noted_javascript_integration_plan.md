# noted - JavaScript Integration Plan

## Document Information

| Field   | Value                              |
|---------|------------------------------------|
| Date    | 2026-04-05                         |
| Status  | Draft - Pending Review             |
| Related | multi_language_plan_feedback.md, js_multi_language_technical_architecture.md, multi-runtime-architecture.md |

---

## 1. Goal

Add JavaScript/Node.js as a first-class language in noted, matching the Python experience: notebook cells, file editing, LSP (autocomplete, linting, formatting), debugging (breakpoints, stepping, variables), environment management, and package management. This enables noted users to build complete web applications with Python backends and JavaScript frontends in a single workspace.

---

## 2. Prerequisites

### Already in place:
- RuntimeRegistry + runtime.json architecture (language-agnostic by design)
- EnvironmentManager with templated commands
- CodeMirror JavaScript syntax highlighting (@codemirror/lang-javascript in bundle)
- DAP WebSocket relay infrastructure (DebugClient.js, DebugPanel.js, BreakpointGutter.js)
- LSP WebSocket proxy infrastructure (lsp.py, lsp_manager.py)
- NotebookLSPBridge for cell linting via shadow files

### Need to install in Docker:
- `fnm` (Fast Node Manager) - Rust-based Node.js version manager
- `pnpm` - disk-efficient package manager
- Node.js 20 LTS + Node.js 22 LTS (via fnm)
- `xeus-javascript` - Jupyter kernel for Node.js with native DAP
- `typescript-language-server` - LSP for JS/TS (installed globally via pnpm)
- `biome` - Rust-based linter/formatter (installed globally via pnpm)

---

## 3. Architecture Overview

```
[Browser]
    |
    | WebSocket (DAP)          WebSocket (LSP)         Socket.IO (execution)
    |                          |                        |
[noted backend]
    |                          |                        |
    +-- dap.py                 +-- lsp.py               +-- execution_bridge.py
    |   TransportManager       |   LSPProxyManager      |   LanguageStrategy
    |   |                      |   |                    |   |
    |   +-- ZMQTransport       |   +-- ruff (py)        |   +-- PythonStrategy
    |   |   (ipykernel)        |   +-- jedi (py)        |   +-- JavaScriptStrategy
    |   +-- TCPTransport       |   +-- tsserver (js)    |
    |       (xeus-*)           |   +-- biome (js)       |
    |                          |                        |
[Kernel Process]               [LSP Servers]            [Kernel Process]
    ipykernel (Python)         (per language)            xeus-javascript (JS)
    xeus-javascript (JS)
```

---

## 4. Detailed Specification

### 4.1 Runtime Configuration

**File: `data/runtimes/javascript/20/runtime.json`**
```json
{
    "language": "javascript",
    "version": "20",
    "display_name": "Node.js 20 LTS",
    "executable": "/root/.local/share/fnm/node-versions/v20.x.x/installation/bin/node",
    "env_create_cmd": ["mkdir", "-p", "{env_path}"],
    "env_post_create_cmds": [
        ["cp", "-n", "/app/data/runtimes/javascript/templates/package.json", "{env_path}/package.json"],
        ["{env_path}/../../../runtimes/javascript/pnpm-bin", "install", "--dir", "{env_path}"]
    ],
    "kernel_cmd": ["{executable}", "{env_path}/node_modules/.bin/xeus-javascript", "-f", "{connection_file}"],
    "kernel_language": "javascript",
    "package_manager": {
        "list_cmd": ["{env_path}/../../../runtimes/javascript/pnpm-bin", "list", "--json", "--dir", "{env_path}"],
        "install_cmd": ["{env_path}/../../../runtimes/javascript/pnpm-bin", "add", "--dir", "{env_path}"],
        "remove_cmd": ["{env_path}/../../../runtimes/javascript/pnpm-bin", "remove", "--dir", "{env_path}"]
    }
}
```

**Notes:**
- `env_create_cmd` creates a directory (JS "environments" are project directories with package.json)
- `env_post_create_cmds` copies a template package.json and runs pnpm install
- `kernel_cmd` launches xeus-javascript with the project's node_modules
- Package management via pnpm with --dir flag for project-scoped installs
- The runtime.json path references need to be validated against actual fnm/pnpm install locations

### 4.2 DAP Transport Manager

**File: `backend/app/managers/dap_transport.py` (NEW)**

**Architecture Note (updated 2026-04-05):** xeus-javascript only works in JupyterLite
(browser-only), so the kernel is IJavascript (npm). IJavascript has no built-in DAP
support, so we use the VS Code approach: launch the Node process with `--inspect=0`
to open a V8 Inspector port, then run `vscode-js-debug` as a standalone DAP adapter
that bridges DAP commands to Chrome DevTools Protocol (CDP).

Data flow for JS debug:
```
Frontend (WebSocket) -> dap.py (TCP proxy) -> vscode-js-debug (DAP adapter)
    -> Chrome DevTools Protocol -> V8 Inspector (Node --inspect)
```

This keeps dap.py language-agnostic: it always shuttles DAP JSON between a WebSocket
and a TCP port, whether the target is debugpy (Python) or vscode-js-debug (JS).

```python
from abc import ABC, abstractmethod

class BaseDebugTransport(ABC):
    """Abstract transport for DAP communication."""

    @abstractmethod
    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        """Send a DAP request and wait for reply."""
        pass

    @abstractmethod
    async def start(self):
        """Start reading from the transport."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop reading and clean up."""
        pass


class ZMQDebugTransport(BaseDebugTransport):
    """DAP over Jupyter control channel (ipykernel/Python).

    Wraps the existing ControlChannelDispatcher logic.
    """
    def __init__(self, debug_kc):
        self._dispatcher = ControlChannelDispatcher(debug_kc)

    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        return await self._dispatcher.send_request(command, arguments, seq, timeout)

    async def start(self):
        self._dispatcher.start()

    async def stop(self):
        await self._dispatcher.stop()


class TCPDebugTransport(BaseDebugTransport):
    """DAP over raw TCP (xeus kernels).

    Connects to the debug port specified in the kernel's connection file.
    Uses Content-Length framed JSON (standard DAP wire protocol).
    """
    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._reader = None
        self._writer = None
        self._pending = {}  # seq -> asyncio.Future
        self._read_task = None
        self._seq = 1

    async def start(self):
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port
        )
        self._read_task = asyncio.create_task(self._read_loop())

    async def stop(self):
        if self._read_task:
            self._read_task.cancel()
        if self._writer:
            self._writer.close()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(asyncio.CancelledError())
        self._pending.clear()

    async def send_request(self, command, arguments=None, seq=0, timeout=15):
        msg = {
            "type": "request",
            "command": command,
            "seq": self._seq,
            "arguments": arguments or {},
        }
        self._seq += 1

        fut = asyncio.get_event_loop().create_future()
        self._pending[msg["seq"]] = fut

        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._writer.write(header.encode() + body.encode())
        await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg["seq"], None)
            raise TimeoutError(f"DAP TCP request timed out: {command}")

    async def _read_loop(self):
        """Read Content-Length framed DAP messages from TCP."""
        try:
            while True:
                # Read headers
                content_length = None
                while True:
                    line = await self._reader.readline()
                    if not line:
                        return
                    header = line.decode().strip()
                    if not header:
                        break
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())

                if content_length is None:
                    continue

                body = await self._reader.readexactly(content_length)
                msg = json.loads(body)

                if msg.get("type") == "response":
                    seq = msg.get("request_seq")
                    if seq in self._pending:
                        fut = self._pending.pop(seq)
                        if not fut.done():
                            fut.set_result(msg)
                elif msg.get("type") == "event":
                    # Forward events via callback
                    if self._on_event:
                        await self._on_event(msg)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except asyncio.CancelledError:
            pass
```

### 4.3 dap.py Refactoring

**Changes to `backend/app/routers/dap.py`:**

The `dap_websocket` function currently creates a `ControlChannelDispatcher` directly. Refactor to:

1. Read kernel's `kernel_language` from the session
2. If Python: use `ZMQDebugTransport` (existing logic via ControlChannelDispatcher)
3. If JavaScript: spin up `vscode-js-debug` adapter targeting the kernel's V8 inspector
   port, use `TCPDebugTransport` to connect to the adapter's DAP port
4. The rest of the WebSocket handler stays the same - it just calls
   `transport.send_request()` instead of `dispatcher.send_request()`

```python
# In dap_websocket, after getting kernel_session:
if kernel_session.kernel_language == 'python':
    transport = ZMQDebugTransport(debug_kc)
else:
    # JS: kernel was started with --inspect=0, port captured in session
    inspect_port = kernel_session.debug_port  # V8 inspector port
    # Launch vscode-js-debug adapter as background process
    adapter_port = find_free_port()
    adapter_proc = await launch_js_debug_adapter(adapter_port, inspect_port)
    transport = TCPDebugTransport("127.0.0.1", adapter_port)

await transport.start()
```

**Cleanup changes:**
- The `continue` + `disconnect` cleanup sequence only applies to Python/ZMQ
  (control thread deadlock is ipykernel-specific)
- For TCP transport: send DAP `disconnect`, close TCP connection, kill adapter process
- The `was_paused` flag and kernel restart fallback are Python-specific

### 4.4 Language Strategy for Execution

**File: `backend/app/managers/language_strategies.py` (NEW)**

```python
class PythonStrategy:
    """Existing _wrap_for_debug logic, extracted."""

    def wrap_code(self, code, shadow_path, start_line):
        return f"""
import ast as _ast
from IPython import get_ipython as _get_ipython
_shell = _get_ipython()
_code = {repr(code)}
_path = {repr(shadow_path)}
_offset = {start_line}
_transformed = _shell.input_transformer_manager.transform_cell(_code)
_padded = ("\\n" * (_offset - 1)) + _transformed
_tree = _ast.parse(_padded)
if _tree.body and isinstance(_tree.body[-1], _ast.Expr):
    _last = _tree.body.pop()
    _exec_node = _ast.Module(body=_tree.body, type_ignore_list=[])
    _eval_node = _ast.Interactive(body=[_last])
else:
    _exec_node = _tree
    _eval_node = None
try:
    _compiled = compile(_exec_node, _path, 'exec')
    exec(_compiled, _shell.user_ns)
    if _eval_node:
        _compiled_eval = compile(_eval_node, _path, 'single')
        exec(_compiled_eval, _shell.user_ns)
except Exception:
    _shell.showtraceback()
"""

    def get_extension(self):
        return ".py"

    def get_shadow_marker(self):
        return "# %%"


class JavaScriptStrategy:
    """Filename injection via V8 sourceURL pragma."""

    def wrap_code(self, code, shadow_path, start_line):
        padding = "\\n" * (start_line - 1)
        return f"{padding}{code}\n//# sourceURL={shadow_path}"

    def get_extension(self):
        return ".js"

    def get_shadow_marker(self):
        return "// %%"


STRATEGIES = {
    "python": PythonStrategy(),
    "javascript": JavaScriptStrategy(),
}
```

### 4.5 LSP Integration

**Changes to `backend/app/managers/lsp_manager.py`:**

Add JavaScript LSP server support:

```python
# In LSPProxyManager, language detection for LSP server selection:
# Python files -> ruff (linting) + jedi (completions)
# JavaScript files -> biome (linting/formatting) + tsserver (completions)

class LSPServerConfig:
    SERVERS = {
        "python": {
            "lint": {"cmd": ["ruff", "server", "--preview"], "type": "ruff"},
            "complete": {"cmd": ["jedi-language-server"], "type": "jedi"},
        },
        "javascript": {
            "lint": {"cmd": ["biome", "lsp-proxy"], "type": "biome"},
            "complete": {"cmd": ["typescript-language-server", "--stdio"], "type": "tsserver"},
        },
    }
```

**Changes to `backend/app/managers/notebook_lsp_bridge.py`:**

- Detect notebook kernel_language to choose shadow file extension (.py vs .js)
- Use language-appropriate cell markers (`# %%` vs `// %%`)
- Use language-appropriate Jupytext format or manual concatenation for JS

**Frontend LSP changes:**
- `FileEditor.js`: detect .js/.ts files, connect to JS LSP WebSocket
- `CellEditor.js`: detect kernel_language for notebook cells, use appropriate LSP
- `lintGutter` works the same regardless of language
- Autocompletion works the same (LSP protocol is language-agnostic)

### 4.6 Frontend Changes

**CodeMirror language detection:**
- `CellEditor.js`: switch between `python()` and `javascript()` extensions based on `kernel_language`
- `FileEditor.js`: already uses `python()` for .py files; add `javascript()` for .js/.ts/.mjs files

**Notebook metadata:**
- Notebooks store `kernelspec.language` in metadata
- When a JS kernel is selected, cells use JS syntax highlighting and JS LSP

**Explorer tree:**
- New runtime nodes under "Virtual Environments": `Node.js 20 LTS`, `Node.js 22 LTS`
- Environment nodes under each: project directories with package.json
- Package management: pnpm add/remove via the existing UI

### 4.7 Shadow File Generation for JS

**Changes to `POST /api/dap/debug-notebook`:**

Detect kernel language and use appropriate markers:

```python
# Python: # %% Cell 1
# JavaScript: // %% Cell 1

marker_prefix = "//" if kernel_language == "javascript" else "#"
marker = f"{marker_prefix} %% Cell {i + 1}"
```

Shadow file extension: `.py` for Python, `.js` for JavaScript.

### 4.8 Dockerfile Changes

```dockerfile
# --- Node.js via fnm ---
RUN curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell
ENV FNM_DIR="/root/.local/share/fnm"
ENV PATH="${FNM_DIR}:${PATH}"

# Install Node.js versions
RUN eval "$(fnm env)" && \
    fnm install 20 && \
    fnm install 22 && \
    fnm default 20

# Install pnpm globally
RUN eval "$(fnm env)" && \
    npm install -g pnpm

# Install global JS tools
RUN eval "$(fnm env)" && \
    pnpm add -g typescript-language-server typescript @biomejs/biome

# IJavascript kernel is installed per-environment via pnpm (in template package.json).
# vscode-js-debug adapter for JS debugging (bridges DAP to V8 Inspector Protocol)
RUN npm install -g @anthropic/js-debug-adapter || true  # TODO: verify exact package name

# Generate runtime.json files for JS
# (handled by scripts/create_runtime_configs.sh)
```

---

## 5. Implementation Phases

### Phase 1: Infrastructure (2-3 days)
**Goal:** JS cells execute and produce output.

| Task | Description | Files |
|------|-------------|-------|
| T1.1 | Install fnm, pnpm, Node.js 20/22 in Dockerfile | Dockerfile |
| T1.2 | Install xeus-javascript in Dockerfile | Dockerfile |
| T1.3 | Create runtime.json for javascript/20 and javascript/22 | data/runtimes/javascript/*, scripts/ |
| T1.4 | Verify kernel starts and executes `console.log("hello")` | Manual test |
| T1.5 | Add JavaScript syntax highlighting to CellEditor | frontend/js/CellEditor.js |
| T1.6 | Detect kernel_language in execution_bridge, skip Python-specific hooks | backend/app/managers/execution_bridge.py |

**Exit criteria:** Open a notebook, select a Node.js environment, execute JS code, see output.

### Phase 2: DAP Transport (2-3 days)
**Goal:** Debug JS cells with breakpoints and stepping.

**Architecture:** IJavascript has no built-in DAP. We use the VS Code approach:
kernel starts with `node --inspect=0`, vscode-js-debug bridges DAP to V8 Inspector.

| Task | Description | Files |
|------|-------------|-------|
| T2.1 | Install vscode-js-debug in Dockerfile (npm global) | Dockerfile |
| T2.2 | Create dap_transport.py with BaseDebugTransport, ZMQDebugTransport, TCPDebugTransport | backend/app/managers/dap_transport.py (NEW) |
| T2.3 | Inject `--inspect=0` flag for JS kernels, capture V8 inspector port | backend/app/managers/kernel_manager.py |
| T2.4 | Create js_debug_adapter.py to launch/manage vscode-js-debug process | backend/app/managers/js_debug_adapter.py (NEW) |
| T2.5 | Refactor dap.py to use transport based on kernel_language | backend/app/routers/dap.py |
| T2.6 | Update shadow file generation for JS (// %% markers, .js extension) | backend/app/routers/dap.py |
| T2.7 | Test single cell debug + Debug All with JS kernel | Manual test |

**Exit criteria:** Set breakpoint in JS cell, hit it, step through, see variables in Debug Panel.

### Phase 3: Environment Management (1-2 days)
**Goal:** Create/delete JS environments, install/remove npm packages from UI.

| Task | Description | Files |
|------|-------------|-------|
| T3.1 | Validate runtime.json package_manager commands work with pnpm | Manual test |
| T3.2 | Handle pnpm list output format in frontend (different from pip list) | frontend/js/panels/ExplorerPanel.js |
| T3.3 | Template package.json for new JS environments | data/runtimes/javascript/templates/ |
| T3.4 | Ensure fnm PATH is set correctly in kernel launch | backend/app/managers/kernel_manager.py |

**Exit criteria:** Create a Node.js environment from Explorer, install a package (e.g., lodash), use it in a cell.

### Phase 4: LSP Integration (2-3 days)
**Goal:** Autocomplete, linting, formatting for JS files and notebook cells.

| Task | Description | Files |
|------|-------------|-------|
| T4.1 | Install typescript-language-server and biome in Dockerfile | Dockerfile |
| T4.2 | Add JS server configs to LSPProxyManager | backend/app/managers/lsp_manager.py |
| T4.3 | Detect .js/.ts files in FileEditor, connect to JS LSP | frontend/js/FileEditor.js |
| T4.4 | Detect kernel_language in CellEditor, use JS LSP for JS notebooks | frontend/js/CellEditor.js |
| T4.5 | Update NotebookLSPBridge for JS shadow files | backend/app/managers/notebook_lsp_bridge.py |
| T4.6 | Severity remapping for Biome diagnostics | backend/app/routers/lsp.py |

**Exit criteria:** JS file has autocomplete, hover docs, linting squiggles, format on Ctrl+Shift+F.

### Phase 5: Polish (1-2 days)
**Goal:** Production-ready JS experience.

| Task | Description | Files |
|------|-------------|-------|
| T5.1 | Ensure JS output rendering (console.log, tables, charts) | frontend/js/CellOutput.js |
| T5.2 | Handle top-level await in JS cells | Kernel config |
| T5.3 | Handle ESM vs CJS module resolution | Documentation |
| T5.4 | Test Debug All across mixed Python+JS notebooks (if applicable) | Manual test |
| T5.5 | Update README, vision, scope, plan documents | documents/* |
| T5.6 | Add JS kernel to Jena Weather demo (optional: JS visualization cells) | Demo notebook |

**Exit criteria:** Complete JS development experience matching Python's quality.

### Phase 6: JS File Execution and Debugging (1-2 days)
**Goal:** Run and debug standalone `.js` files, matching the Python `.py` file experience.

| Task | Description | Files |
|------|-------------|-------|
| T6.1 | Implement JS file execution via kernel (equivalent of Python's `%run -i`) | backend/app/managers/execution_bridge.py, frontend/js/app-file-editors.js |
| T6.2 | Implement JS file debugging (breakpoints, stepping in `.js` files) | backend/app/routers/dap.py, frontend/js/app-file-editors.js |
| T6.3 | Run button in file editor toolbar for `.js` files | frontend/js/FileEditor.js |
| T6.4 | Debug dropdown (Run/Debug) for `.js` files | frontend/js/FileEditor.js |
| T6.5 | Test: run `.js` file, debug `.js` file with breakpoints | Manual test |

**Architecture notes:**
- Python file execution uses `%run -i <path>` (IPython magic). JS equivalent: `require('<path>')` or `eval(fs.readFileSync('<path>', 'utf8'))` via the kernel.
- Python file debugging uses real file paths (no dumpCell needed). JS file debugging can use the real file path with `//# sourceURL` - vscode-js-debug should bind breakpoints directly to the file.
- The Run/Debug dropdown and breakpoint gutter already work for `.js` files (syntax + LSP from Phase 4). Only the execution and debug wiring are missing.

**Exit criteria:** User can open a `.js` file, click Run to execute it, click Debug to step through it with breakpoints and see output.

### Phase 7: Terminal-Based File Debugging (both Python and JS)
**Goal:** File debug shows output in a terminal, matching the Run experience.

**Current limitation:** File debug executes through the kernel (`cell_index=-1`), output has no UI target. This affects both Python and JS.

**Architecture:** Replace kernel-based file debug with terminal-based debug:
- **Python**: `python -m debugpy --listen 0 --wait-for-client file.py` in terminal + attach DAP
- **JS**: `node --inspect-brk=0 file.js` in terminal + attach vscode-js-debug
- Terminal shows stdout/stderr naturally
- Debug Panel shows variables, call stack, breakpoints (same as now)
- Same consistent UX for both languages

| Task | Description | Files |
|------|-------------|-------|
| T7.1 | Launch Python file debug via terminal with debugpy | frontend/js/app-file-editors.js |
| T7.2 | Launch JS file debug via terminal with --inspect-brk | frontend/js/app-file-editors.js |
| T7.3 | Attach DAP adapter to the terminal process (parse port from output) | backend/app/routers/dap.py |
| T7.4 | Remove kernel-based file debug path (%run -i, eval) | frontend/js/app-file-editors.js, backend/ |
| T7.5 | Test both Python and JS file debug with output visible | Manual test |

**Exit criteria:** Debug a file, see output in terminal, step through with breakpoints, inspect variables.

---

## 6. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| IJavascript kernel instability | Medium | Low | IJavascript is mature (v5.2), well-tested in Phase 1 |
| V8 inspector port capture timing | Medium | Medium | --inspect=0 prints port to stderr; parse before kernel ready |
| pnpm output format incompatible | Low | Medium | Parse JSON output, adapt frontend |
| tsserver memory usage | Medium | Medium | Strict process lifecycle, kill on disconnect timeout |
| sourceURL injection not working with V8 inspector | Medium | Low | Standard V8 feature, well-documented |
| vscode-js-debug adapter availability as standalone | High | Medium | May need to extract from VS Code extension |
| fnm PATH not propagating to kernel subprocess | Medium | Medium | Explicit env injection in kernel_manager.py |

---

## 7. What NOT to Change

- Python debugging flow (single cell, Debug All, file debug) - untouched
- Python LSP (ruff + jedi) - untouched
- DebugClient.js - protocol-agnostic, works as-is
- DebugPanel.js - protocol-agnostic, works as-is
- BreakpointGutter.js - language-agnostic, works as-is

---

## 8. Validation Checklist

- [ ] JS cell executes and shows output (console.log, return value)
- [ ] JS cell with breakpoint stops execution
- [ ] F10 stepping works in JS cells
- [ ] Debug All works across multiple JS cells
- [ ] Variables panel shows JS objects correctly
- [ ] Create JS environment from Explorer
- [ ] Install npm package from Explorer
- [ ] JS file has autocomplete (tsserver)
- [ ] JS file has linting (Biome)
- [ ] JS file has formatting (Biome)
- [ ] JS notebook cells have autocomplete and linting
- [ ] Mixed notebook (some Python cells, some JS cells) - if applicable
- [ ] Debug stop cleanup works for JS (no kernel deadlock)
