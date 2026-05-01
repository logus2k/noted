# noted - Language Server Protocol Integration Plan

## Document Information

| Field         | Value                              |
|---------------|-------------------------------------|
| Document      | LSP Integration Plan                |
| Project       | noted - Integrated MLOps Platform   |
| Version       | 1.0                                 |
| Date          | 2026-04-01                          |
| Status        | Draft                               |
| Related       | Vision v1.5, Scope v1.5, Architecture Principles |

---

## 1. Purpose

This document defines the integration plan for Language Server Protocol (LSP) support in noted. LSP enables intelligent code features - diagnostics (linting), formatting, autocomplete, go-to-definition, hover documentation, and symbol navigation - for both Python source files and notebook cells. The initial implementation uses **ruff server** for linting and formatting, with a design that supports adding additional language servers (pyright, jedi-language-server) in the future.

---

## 2. Why LSP

### 2.1 Current State

noted's code editing capabilities:
- **CodeMirror 6** with Python syntax highlighting
- **No diagnostics** - errors only appear at execution time
- **No autocomplete** - users type everything manually
- **No formatting** - code style is inconsistent across cells
- **No navigation** - no go-to-definition or find-references

### 2.2 What LSP Provides

| Feature | Description | User Value |
|---|---|---|
| **Diagnostics** | Real-time linting with inline error markers | Catch bugs before running the cell |
| **Formatting** | Auto-format on save or on demand | Consistent code style, no manual cleanup |
| **Auto-fix** | Quick fixes for common issues (unused imports, etc.) | One-click code cleanup |
| **Autocomplete** (phase 2) | Context-aware completions from installed packages | Faster coding, fewer typos |
| **Hover docs** (phase 2) | Inline documentation on mouse hover | No need to switch to browser for API docs |
| **Go to definition** (phase 2) | Navigate to function/class source | Understand code without searching files |

### 2.3 Alignment with noted Principles

| Principle | How LSP Aligns |
|---|---|
| P1: Zero Vendor Lock-In | LSP is an open standard. Language servers are independent tools. |
| P2: Backend Services Stay Canonical | Language servers are the source of truth for diagnostics and completions. noted proxies, doesn't replicate. |
| P3: Integration Over Aggregation | noted renders diagnostics inline in CodeMirror using purpose-built UI, not an embedded IDE. |
| P5: Progressive Complexity | Linting appears automatically. Advanced features (completions, navigation) are discoverable but not intrusive. |
| P10: No Framework, No Build Step | The CodeMirror bundle already requires a build step. The LSP client is added to the existing bundle. |

---

## 3. Architecture

### 3.1 Protocol Stack

```
Browser (CodeMirror + LSP client)
    |
    | Plain WebSocket (JSON-RPC 2.0)
    |
noted backend (LSP proxy)
    |
    | stdio pipe (JSON-RPC 2.0 with Content-Length headers)
    |
Language Server process (ruff server, pyright, jedi-lsp)
    |
    | File system access
    |
Project files + virtual environment (site-packages)
```

### 3.2 Why Plain WebSocket, Not Socket.IO

Socket.IO adds its own framing protocol on top of WebSocket (event names, acknowledgements, namespaces, binary encoding). LSP uses **raw JSON-RPC 2.0** over a transport layer. The `codemirror-languageserver` client expects a standard `WebSocket` object.

noted's backend already runs FastAPI + Uvicorn which natively supports WebSocket endpoints. Adding a `/ws/lsp` endpoint is straightforward and keeps the LSP transport cleanly separated from the Socket.IO collaboration layer.

### 3.3 Component Diagram

```
+----------------------------------------------------------+
|  Browser                                                  |
|                                                           |
|  +-------------------+    +---------------------------+  |
|  | CodeMirror Editor  |    | codemirror-languageserver |  |
|  | (Python mode)      |<-->| (LSP client, WebSocket)   |  |
|  +-------------------+    +---------------------------+  |
|                                   |                       |
+-----------------------------------|----------------------+
                                    | WebSocket
                                    | ws://host/ws/lsp?
                                    |   kernel=<runtime_id>
                                    |   &env=<env_name>
                                    |   &project=<project_id>
                                    |
+-----------------------------------|----------------------+
|  noted backend (FastAPI)          |                       |
|                                   v                       |
|  +---------------------------+                            |
|  | LSPProxyManager           |                            |
|  | - WebSocket endpoint      |                            |
|  | - Per-session LS process  |                            |
|  | - JSON-RPC relay          |                            |
|  | - Virtual doc management  |                            |
|  +---------------------------+                            |
|            |                                              |
|            | stdio (JSON-RPC + Content-Length headers)     |
|            v                                              |
|  +---------------------------+                            |
|  | Language Server Process   |                            |
|  | (ruff server / pyright)   |                            |
|  | - Runs in project venv    |                            |
|  | - Sees site-packages      |                            |
|  +---------------------------+                            |
|            |                                              |
|            | reads                                        |
|            v                                              |
|  +---------------------------+                            |
|  | Project Files             |                            |
|  | - src/*.py                |                            |
|  | - .notebook_<id>.py       |  (Jupytext percent-format) |
|  | - pyproject.toml / ruff.toml                           |
|  +---------------------------+                            |
+----------------------------------------------------------+
```

### 3.4 Connection Lifecycle

1. User opens a notebook or `.py` file in noted
2. Frontend opens a WebSocket to `/ws/lsp` with query params: `kernel` (runtime_id), `env` (env_name), `project` (project_id)
3. Backend's `LSPProxyManager` spawns a language server process (if not already running for this project+env combination)
4. Backend relays JSON-RPC messages between the WebSocket and the language server's stdio
5. When the editor tab closes, the WebSocket disconnects
6. After an idle timeout (e.g. 5 minutes with no open editors for that project), the language server process is terminated

---

## 4. Notebook Cell Support

### 4.1 The Problem

LSP servers expect to work with files on disk. Notebook cells are fragments of Python code that share a kernel namespace but aren't individual files. A single cell might reference variables defined in earlier cells.

### 4.2 Solution: Jupytext Percent Format

Instead of a custom virtual document assembler, we use **Jupytext** ([github.com/mwouts/jupytext](https://github.com/mwouts/jupytext)) - the established standard for notebook-to-script roundtripping (6k+ stars, used by VS Code, PyCharm, JupyterLab).

Jupytext's **percent format** uses `# %%` cell markers that are already recognized by ruff, pyright, and other Python tools as cell boundaries:

```python
# %% [markdown]
# ## Data Loading

# %%
import pandas as pd
import numpy as np

# %%
df = pd.read_csv("data.csv")
print(df.head())

# %%
model = LinearRegression()
model.fit(df[["x"]], df["y"])
```

Key advantages over a custom solution:
- `# %%` markers are valid Python comments - no lint warnings
- Language servers already understand them (VS Code interactive Python support)
- Jupytext handles edge cases: magic commands, raw cells, markdown cells, cell metadata
- Roundtrip-safe: `.ipynb` -> `.py` -> `.ipynb` preserves cell boundaries and metadata
- Battle-tested in production across the Python ecosystem

### 4.3 Jupytext Integration Flow

```
NotebookEditor (browser)
    |
    | cell content changes (Socket.IO, existing events)
    |
    v
noted backend (NotebookLSPBridge)
    |
    | 1. Receives cell updates
    | 2. Uses Jupytext API to generate percent-format .py in memory
    | 3. Maintains cell-to-line mapping from Jupytext's cell metadata
    | 4. Sends textDocument/didChange to language server
    |
    v
Language Server
    |
    | Returns diagnostics with document positions (line numbers in .py)
    |
    v
noted backend (NotebookLSPBridge)
    |
    | Maps .py line numbers back to cell positions using Jupytext metadata
    |
    v
NotebookEditor (browser)
    |
    | Renders diagnostics in the correct cell's CodeMirror instance
```

### 4.4 Position Mapping

Jupytext's percent format produces a deterministic mapping between cells and lines. Each cell contributes:
- 1 line for the `# %%` marker (or `# %% [markdown]`)
- N lines for the cell content
- 1 blank line separator

The `NotebookLSPBridge` maintains a simple array:

```python
# cell_map[i] = (start_line, end_line, cell_id)
cell_map = [
    (0, 0, None),      # marker line
    (1, 2, "abc123"),   # Cell 0: import lines
    (4, 4, None),       # marker line
    (5, 6, "def456"),   # Cell 1: data loading
    (8, 8, None),       # marker line
    (9, 10, "ghi789"),  # Cell 2: model training
]
```

When the language server reports a diagnostic at line 9, column 5, the bridge maps it to Cell 2 (`ghi789`), local line 0, column 5.

### 4.5 Cell Change Handling

When a user edits a cell:

1. The existing `cell:update` Socket.IO event fires (already implemented)
2. The backend's `NotebookLSPBridge` regenerates the percent-format document using Jupytext
3. The bridge computes the diff and sends `textDocument/didChange` (incremental) to the language server
4. The language server responds with updated diagnostics
5. The bridge maps diagnostics back to cell positions using the cell map
6. Diagnostics are pushed to the frontend via a new Socket.IO event: `cell:diagnostics`

Debouncing: cell changes are debounced (500ms) before regenerating the document, matching the existing cell update debounce in NotebookEditor.

### 4.6 Jupytext API Usage

```python
import jupytext

# Notebook to percent-format script (in memory)
notebook = jupytext.read("notebook.ipynb")
script_content = jupytext.writes(notebook, fmt="py:percent")

# Or build from noted's in-memory cell data:
notebook = jupytext.v3.new_notebook()
for cell in cells:
    if cell["cell_type"] == "code":
        notebook.cells.append(jupytext.v3.new_code_cell(cell["source"]))
    elif cell["cell_type"] == "markdown":
        notebook.cells.append(jupytext.v3.new_markdown_cell(cell["source"]))

script = jupytext.writes(notebook, fmt="py:percent")
```

### 4.7 Markdown Cells

Jupytext converts markdown cells to commented Python:

```python
# %% [markdown]
# ## Section Title
# Some description with **bold** text
```

These are valid Python comments, so ruff ignores them and pyright doesn't complain. The `[markdown]` tag in the marker tells Jupytext to restore them as markdown cells on roundtrip.

---

## 5. Language Servers

### 5.1 Phase 1: ruff server

**What it provides:** Diagnostics (800+ lint rules), formatting, auto-fix, import sorting.

**Installation:** `pip install ruff` in the project's venv (or globally in the container).

**Launch command:**
```bash
ruff server --preview
```

**Configuration:** `pyproject.toml` or `ruff.toml` in the project root. Defaults are sensible - no config required to start.

**LSP capabilities used:**
- `textDocument/publishDiagnostics` - linting results
- `textDocument/formatting` - format document
- `textDocument/codeAction` - auto-fix suggestions
- `textDocument/didOpen`, `textDocument/didChange`, `textDocument/didClose` - document sync

### 5.2 Phase 2: jedi-language-server (or pyright)

**What it provides:** Autocomplete, go-to-definition, hover docs, find references, rename.

**Why jedi over pyright:**
- Pure Python (no Node.js dependency in the container)
- Lighter memory footprint (~50MB vs ~200MB)
- Better at dynamic Python (ML code with runtime types)
- Pyright excels at typed codebases; ML code is often untyped

**Installation:** `pip install jedi-language-server` in the project's venv.

**Launch command:**
```bash
jedi-language-server
```

**LSP capabilities used:**
- `textDocument/completion` - autocomplete
- `textDocument/hover` - hover documentation
- `textDocument/definition` - go-to-definition
- `textDocument/references` - find references
- `textDocument/rename` - rename symbol
- `textDocument/signatureHelp` - function signature hints

### 5.3 Running Multiple Servers

ruff and jedi can run simultaneously for the same project. The backend merges their diagnostics and routes requests to the appropriate server:

- Diagnostics: merged from both (ruff for lint, jedi for type hints)
- Formatting: routed to ruff only
- Completions: routed to jedi only
- Navigation: routed to jedi only

---

## 6. Frontend Integration

### 6.1 CodeMirror Bundle Changes

The existing CodeMirror ESM bundle (`frontend/vendor/codemirror/codemirror.bundle.js`) needs to be rebuilt with the LSP client:

```bash
npm install codemirror-languageserver
```

New exports from the bundle:
- `languageServerWithTransport` or `LanguageServerClient`
- Diagnostic rendering extensions (`lintGutter`, `setDiagnostics`)

### 6.2 For .py Files (Source Editor)

The source file editor already uses CodeMirror. Adding LSP:

1. Open WebSocket to `/ws/lsp` when a `.py` file tab is opened
2. Create `LanguageServerClient` with the WebSocket
3. Attach diagnostic, completion, and hover extensions to the editor
4. Close WebSocket when the tab closes

Document URI: `file:///<project_id>/<relative_path>`

### 6.3 For Notebook Cells

Each notebook cell has its own CodeMirror instance. LSP integration:

1. One WebSocket per notebook (not per cell)
2. Backend manages the virtual document
3. Frontend sends cell edits via the existing Socket.IO `cell:update` events
4. Backend pushes per-cell diagnostics via a new Socket.IO event: `cell:diagnostics`
5. Frontend applies diagnostics to the correct cell's CodeMirror instance

```javascript
// New Socket.IO event
socket.on('cell:diagnostics', ({ cell_id, diagnostics }) => {
    const cell = this._cells.find(c => c.id === cell_id);
    if (cell) cell.setDiagnostics(diagnostics);
});
```

### 6.4 UI Elements

| Feature | UI | Location |
|---|---|---|
| **Diagnostics** | Red/yellow squiggly underlines + gutter markers | Inline in cell/editor |
| **Diagnostic hover** | Tooltip with error message + fix suggestion | On hover over squiggly |
| **Format document** | Context menu or keyboard shortcut (Shift+Alt+F) | Editor/cell context |
| **Auto-fix** | Light bulb icon + quick fix menu | Gutter, on diagnostic line |
| **Autocomplete** (phase 2) | Dropdown list below cursor | On typing or Ctrl+Space |
| **Hover docs** (phase 2) | Floating panel with function signature + docstring | On hover over identifier |
| **Go to definition** (phase 2) | Ctrl+Click or F12 | Opens target file tab or scrolls to cell |

### 6.5 Edit Menu - Final Plan

The Edit menu is defined in `frontend/menu.json` and commands are registered in `app.js`. LSP commands are added alongside the existing cell operations. All LSP items are visible from the start but **disabled** until the corresponding LSP phase is implemented. Items are enabled via the `enabled` field in `menu.json` (e.g. `"hasLSP"`, `"hasLSPNavigation"`).

#### Current Edit menu (pre-LSP)

```
Edit
  Undo                              (hasNotebook)
  ---
  Cut Cell                          (hasNotebook)
  Copy Cell                         (hasNotebook)
  Paste Cell                        (hasNotebook)
  Delete Cell                       (hasNotebook)
  ---
  Find & Replace...        Ctrl+H   (hasNotebook)
```

#### Final Edit menu (all phases complete)

```
Edit
  Undo                              (hasNotebook)
  ---
  Cut Cell                          (hasNotebook)
  Copy Cell                         (hasNotebook)
  Paste Cell                        (hasNotebook)
  Delete Cell                       (hasNotebook)
  ---
  Find & Replace...        Ctrl+H   (hasNotebook)
  Find All References      Shift+F12 (hasLSPNavigation)     [Phase 2]
  ---
  Format Document          Shift+Alt+F (hasLSP)             [Phase 1]
  Format Selection         Ctrl+K Ctrl+F (hasLSP)           [Phase 1]
  Organize Imports         Shift+Alt+O (hasLSP)             [Phase 1]
  Fix All Auto-fixable     Ctrl+.   (hasLSP)                [Phase 1]
  ---
  Go to Definition         F12      (hasLSPNavigation)      [Phase 2]
  Peek Definition          Alt+F12  (hasLSPNavigation)      [Phase 2]
  Rename Symbol            F2       (hasLSPNavigation)      [Phase 2]
```

#### Command-to-LSP mapping

| Command | menu.json key | Shortcut | LSP Method | Server | Phase |
|---|---|---|---|---|---|
| Format Document | `edit.formatDocument` | Shift+Alt+F | `textDocument/formatting` | ruff | 1 |
| Format Selection | `edit.formatSelection` | Ctrl+K Ctrl+F | `textDocument/rangeFormatting` | ruff | 1 |
| Organize Imports | `edit.organizeImports` | Shift+Alt+O | `textDocument/codeAction` (organizeImports) | ruff | 1 |
| Fix All Auto-fixable | `edit.fixAll` | Ctrl+. | `textDocument/codeAction` (quickfix) | ruff | 1 |
| Go to Definition | `edit.goToDefinition` | F12 | `textDocument/definition` | jedi | 2 |
| Go to Definition (alt) | - | Ctrl+Click | `textDocument/definition` | jedi | 2 |
| Peek Definition | `edit.peekDefinition` | Alt+F12 | `textDocument/definition` (inline) | jedi | 2 |
| Find All References | `edit.findReferences` | Shift+F12 | `textDocument/references` | jedi | 2 |
| Rename Symbol | `edit.renameSymbol` | F2 | `textDocument/rename` | jedi | 2 |
| Trigger Suggest | - | Ctrl+Space | `textDocument/completion` | jedi | 2 |

Note: Trigger Suggest and Ctrl+Click are keyboard/mouse shortcuts only - no menu entry needed.

#### Enabled conditions

| Condition | Meaning | Active when |
|---|---|---|
| `hasNotebook` | A notebook is open (existing) | Always, when a notebook tab is active |
| `hasLSP` | Phase 1 LSP is connected (ruff) | WebSocket to `/ws/lsp` is open and ruff is responding |
| `hasLSPNavigation` | Phase 2 LSP is connected (jedi) | jedi-language-server is running for the active project |

Items with unmet conditions appear **greyed out** in the menu but are still visible, showing users what capabilities exist. This follows VS Code's pattern of showing all commands regardless of extension state.

#### Notebook-specific behavior

- **Format Document** formats the currently focused cell, not the entire virtual document
- **Format Selection** formats the selected text within a cell
- **Go to Definition** navigates to the target `.py` file (opens in a new tab) or scrolls to the target cell within the same notebook
- **Find All References** searches across all cells in the notebook and across open `.py` files in the same project
- **Rename Symbol** renames across all cells in the notebook (coordinated via the Jupytext virtual document)
- **Organize Imports** organizes imports in the focused cell

---

## 7. Backend Implementation

### 7.1 New Components

| Component | File | Responsibility |
|---|---|---|
| `LSPProxyManager` | `backend/app/managers/lsp_manager.py` | Spawn/manage language server processes, WebSocket relay |
| `NotebookLSPBridge` | `backend/app/managers/notebook_lsp_bridge.py` | Jupytext-based notebook-to-script conversion, position mapping |
| WebSocket endpoint | `backend/app/routers/lsp.py` | `/ws/lsp` WebSocket route |

### 7.2 LSPProxyManager

```python
class LSPProxyManager:
    """Manages language server processes and WebSocket connections."""
    
    # Key: (project_id, env_name, server_type) -> LSP process
    _servers: dict[tuple, subprocess.Popen]
    
    async def get_or_start_server(self, project_id, env_name, server_type='ruff'):
        """Start a language server if not running, return its stdio streams."""
        
    async def relay_message(self, server_key, message: dict):
        """Send a JSON-RPC message to the language server."""
        
    async def handle_websocket(self, websocket, project_id, env_name):
        """Bidirectional relay between WebSocket and language server stdio."""
        
    async def shutdown_idle_servers(self):
        """Terminate servers with no active WebSocket connections."""
```

### 7.3 NotebookLSPBridge

```python
class NotebookLSPBridge:
    """Jupytext-based notebook-to-script bridge for LSP support.
    
    Uses Jupytext's percent format to generate a virtual .py document
    from notebook cells, maintaining bidirectional position mapping.
    """
    
    # Key: notebook_key -> { script: str, cell_map: list }
    _documents: dict[str, dict]
    
    def update_cells(self, notebook_key, cells: list[dict]):
        """Regenerate the percent-format script from notebook cells using Jupytext."""
        
    def get_script(self, notebook_key) -> str:
        """Get the current percent-format script content."""
        
    def cell_to_script_pos(self, notebook_key, cell_id, line, col) -> tuple[int, int]:
        """Map cell-local (line, col) to script-global (line, col)."""
        
    def script_to_cell_pos(self, notebook_key, script_line, script_col) -> tuple[str, int, int]:
        """Map script-global (line, col) to (cell_id, local_line, col)."""
        
    def diagnostics_to_cells(self, notebook_key, diagnostics: list) -> dict[str, list]:
        """Map LSP diagnostics from script positions to per-cell diagnostic lists.
        Returns: { cell_id: [diagnostic, ...] }
        """
```

### 7.4 WebSocket Endpoint

```python
@app.websocket("/ws/lsp")
async def lsp_websocket(websocket: WebSocket, 
                        kernel: str, env: str, project: str):
    await websocket.accept()
    server = await lsp_manager.get_or_start_server(project, env)
    
    # Bidirectional relay
    async def ws_to_server():
        async for message in websocket.iter_json():
            await server.send(message)
    
    async def server_to_ws():
        async for message in server.receive():
            await websocket.send_json(message)
    
    await asyncio.gather(ws_to_server(), server_to_ws())
```

---

## 8. Language Server Process Management

### 8.1 Launching

The language server runs in the project's venv to see installed packages:

```python
def _build_server_command(self, env_name, runtime_id, server_type):
    env_path = env_manager.get_env_path(env_name, runtime_id)
    python = os.path.join(env_path, 'bin', 'python')
    
    if server_type == 'ruff':
        # ruff is a standalone binary, not a Python package
        return ['ruff', 'server', '--preview']
    elif server_type == 'jedi':
        return [python, '-m', 'jedi_language_server']
    elif server_type == 'pyright':
        return ['pyright-langserver', '--stdio']
```

### 8.2 Working Directory

The language server's working directory is set to the project root so it discovers:
- `pyproject.toml` / `ruff.toml` for ruff configuration
- `src/` and other Python packages for import resolution
- The venv's `site-packages` for installed package completions

### 8.3 Lifecycle

| Event | Action |
|---|---|
| First editor opens for project+env | Spawn language server process |
| Additional editors open for same project+env | Reuse existing server |
| Editor tab closes | Decrement reference count |
| Last editor closes for project+env | Start idle timer (5 min) |
| Idle timer expires | Terminate language server process |
| Kernel restart | Restart language server (packages may have changed) |

---

## 9. Implementation Phases

### Phase 1: ruff Linting for .py Files (3-4 days)

| Task | Description |
|---|---|
| L1.1 | Add `codemirror-languageserver` to CodeMirror bundle, rebuild |
| L1.2 | Create `LSPProxyManager` - spawn ruff server, stdio relay |
| L1.3 | Add `/ws/lsp` WebSocket endpoint to FastAPI |
| L1.4 | Wire CodeMirror LSP client to the WebSocket in the source file editor |
| L1.5 | Diagnostic rendering: squiggly underlines + gutter markers |
| L1.6 | Format on demand: context menu + Shift+Alt+F shortcut |
| L1.7 | Install `ruff` in the container image |

**Exit criteria:** Open a `.py` file in noted, see lint errors inline, format with a shortcut.

### Phase 2: ruff Linting for Notebook Cells (3-4 days)

| Task | Description |
|---|---|
| L2.1 | Create `NotebookLSPBridge` using Jupytext percent format for cell-to-script conversion |
| L2.2 | Hook into existing `cell:update` events to regenerate percent-format script via Jupytext |
| L2.3 | Add `cell:diagnostics` Socket.IO event |
| L2.4 | Map language server diagnostics to per-cell positions using `NotebookLSPBridge` |
| L2.5 | Render diagnostics in individual cell CodeMirror instances |
| L2.6 | Format cell on demand |
| L2.7 | Install `jupytext` in the container image |

**Exit criteria:** Edit a notebook cell, see lint errors appear inline across all cells.

### Phase 3: Autocomplete and Navigation (4-5 days)

| Task | Description |
|---|---|
| L3.1 | Add jedi-language-server support to `LSPProxyManager` |
| L3.2 | Run ruff + jedi simultaneously, merge diagnostics |
| L3.3 | Autocomplete dropdown in CodeMirror (Ctrl+Space or auto-trigger) |
| L3.4 | Hover documentation panel |
| L3.5 | Go-to-definition (Ctrl+Click) for `.py` files |
| L3.6 | Go-to-definition for notebook cells (scroll to target cell) |
| L3.7 | Install `jedi-language-server` in venvs or container |

**Exit criteria:** Type `pd.` in a cell with pandas installed, see autocomplete suggestions.

**Total estimated effort: 10-13 days**

---

## 10. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| codemirror-languageserver compatibility with our bundle | Medium | Test with a minimal prototype before committing to the approach |
| Virtual document position mapping errors | Medium | Extensive unit tests for the position mapper; start with .py files only |
| Language server memory usage with many projects | Low | Idle timeout, max concurrent servers limit |
| ruff version changes breaking LSP protocol | Low | Pin ruff version, test on upgrades |
| Latency for notebook diagnostics (many cells) | Medium | Debounce cell changes; incremental document updates |
| CodeMirror bundle size increase | Low | codemirror-languageserver is small (~10KB) |

---

## 11. Configuration

### 11.1 Per-Project ruff Configuration

Users can add a `ruff.toml` or `[tool.ruff]` section in `pyproject.toml` in their project root:

```toml
[tool.ruff]
line-length = 120
select = ["E", "F", "W", "I"]  # pycodestyle, pyflakes, warnings, isort

[tool.ruff.format]
quote-style = "double"
```

noted discovers this automatically via the language server's working directory.

### 11.2 noted Settings

```json
{
    "lsp": {
        "enabled": true,
        "servers": ["ruff"],
        "idle_timeout": 300,
        "max_concurrent_servers": 5,
        "diagnostics_debounce_ms": 500
    }
}
```

---

## 12. Impact on Existing Code

| Component | Change |
|---|---|
| **CodeMirror bundle** | Rebuild with `codemirror-languageserver` |
| **Source file editor** | Add LSP client initialization |
| **NotebookEditor** | Add `setDiagnostics` method to CellEditor, handle `cell:diagnostics` event |
| **CellEditor** | Add diagnostic extension to CodeMirror instance |
| **Backend main.py** | Register `/ws/lsp` WebSocket route |
| **Dockerfile** | Install `ruff` and `jupytext` |
| **Existing Socket.IO events** | No changes - `cell:update` is reused as the trigger |

No existing functionality is modified. LSP is purely additive.
