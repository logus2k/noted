# Debug All Cells - Implementation Plan

## Document Information

| Field   | Value                              |
|---------|------------------------------------|
| Date    | 2026-04-04                         |
| Status  | Ready for implementation           |
| Related | noted_dap.md, noted_dap_control_thread_deadlock.md |

---

## 1. Goal

Enable "Debug All Cells" in notebooks - a single debug session that executes all code cells sequentially, stopping at breakpoints in any cell, with correct per-cell output routing and seamless cross-cell awareness.

---

## 2. Architecture: Filename Injection

The core technique: each cell is executed individually via `kc.execute()` (preserving per-cell output), but the code is compiled with the shadow file path as the filename (so debugpy sees one continuous file for breakpoints).

### Why this works:
- **Per-cell output**: `kc.execute()` per cell means iopub messages are parented to the correct `msg_id`, so charts/prints appear under the right cell
- **Unified breakpoints**: `compile(code, shadow_path, 'exec')` makes debugpy think all cells belong to one file
- **Line alignment**: prepending `"\n" * (start_line - 1)` to each cell's code shifts line numbers to match the shadow file positions

---

## 3. Implementation Steps

### Step 1: Backend - Shadow File Endpoint

**File: `backend/app/routers/dap.py`**

Add `POST /api/dap/debug-notebook` endpoint:
- Input: `{ project_id, notebook_path, cells: [{cell_type, source}, ...] }`
- Generates percent-format Python from cells (with `# %%` markers)
- Writes to `/tmp/noted_debug_<hash>.py`
- Returns: `{ shadow_path, cell_map: [{cell_index, start_line, end_line}, ...] }`

The cell map uses 1-based line numbers matching what debugpy reports in stopped events.

### Step 2: Backend - IPython-Aware Execution Wrapper

**File: `backend/app/managers/execution_bridge.py`**

Add method `_wrap_for_debug(code, shadow_path, start_line)` that returns a wrapper string:

```python
def _wrap_for_debug(code, shadow_path, start_line):
    return f'''
import ast
from IPython import get_ipython

_shell = get_ipython()
_code = {repr(code)}
_path = {repr(shadow_path)}
_offset = {start_line}

_transformed = _shell.input_transformer_manager.transform_cell(_code)
_padded_code = ("\\n" * (_offset - 1)) + _transformed

_tree = ast.parse(_padded_code)
if _tree.body and isinstance(_tree.body[-1], ast.Expr):
    _last_expr = _tree.body.pop()
    _exec_node = ast.Module(body=_tree.body, type_ignore_list=[])
    _eval_node = ast.Interactive(body=[_last_expr])
else:
    _exec_node = _tree
    _eval_node = None

try:
    _compiled_exec = compile(_exec_node, _path, 'exec')
    exec(_compiled_exec, _shell.user_ns)
    if _eval_node:
        _compiled_eval = compile(_eval_node, _path, 'single')
        exec(_compiled_eval, _shell.user_ns)
except Exception:
    _shell.showtraceback()
'''
```

When `debug_active` and a `shadow_path` is set on the session, `execute_cell` uses this wrapper instead of raw code.

### Step 3: Backend - Store Debug Context on Session

**File: `backend/app/managers/kernel_manager.py`**

Add to KernelSession:
- `debug_shadow_path: str = ""` - path to the shadow file
- `debug_cell_map: list = field(default_factory=list)` - cell line mappings

These are set when `POST /api/dap/debug-notebook` is called and cleared when the debug session ends.

### Step 4: Frontend - debugAll() Flow

**File: `frontend/js/NotebookEditor.js`**

The `debugAll()` method:

1. Call `POST /api/dap/debug-notebook` with cells array
2. Receive `shadow_path` and `cell_map`
3. Store `_debugCellMap` and `_debugShadowPath`
4. Connect DebugClient, send initialize + attach
5. Set breakpoints using `shadow_path` as the source path, translating cell-relative breakpoint lines to shadow file lines using the cell map
6. Send configurationDone
7. Start executing cells sequentially via `_debugExecNext()`

### Step 5: Frontend - Breakpoint Translation

When sending `setBreakpoints` during Debug All:
- For each cell with breakpoints, translate `cell_line` to `shadow_line = cell_map[cellIndex].start_line + cell_line - 1`
- Send ONE `setBreakpoints` request for the shadow file with ALL breakpoints from ALL cells

### Step 6: Frontend - Stopped Event Mapping

In `_onDebugStopped(body)`:
- Get `frame.line` from stackTrace
- If `_debugCellMap` exists, find the cell whose `start_line <= frame.line <= end_line`
- Calculate cell-relative line: `frame.line - cell_map_entry.start_line + 1`
- Highlight that cell at that line

### Step 7: Frontend - Cell Boundary Stepping

In step actions (handled on frontend, not backend, to avoid round-trips):
- When F10 at the last line of a cell's region (line >= cell_map entry's end_line):
  - Send `continue` (not `next`) to finish the current cell
  - `_onExecuteComplete` triggers `_debugExecNext()` for the next cell
- When F5 (Continue): run until next breakpoint in any cell, or end of current cell (then auto-advance)
- Frontend knows the cell map and current line, so boundary detection is instant

### Step 8: Frontend - Execution Chain

`_debugExecNext()`:
- Shift next cell index from `_debugExecQueue`
- Set `_debugCellIndex` to the new cell
- Call `cell.setDebugMode(true)` and `cell.startExecuting(true)`
- Send `cell:execute` with the cell's source (backend wraps it with the filename injection)

The execution bridge detects `debug_shadow_path` on the session and wraps the code automatically.

### Step 9: Frontend - Debug All UI

- Dropdown next to "Run All" with "Debug All Cells" option (already added)
- Debug bar shows throughout the entire debug-all session
- Each cell shows the bug icon while being debugged, reverts when moving to the next cell
- Stop button terminates the entire chain

---

## 4. Data Flow Diagram

```
User clicks "Debug All"
    |
    v
Frontend: POST /api/dap/debug-notebook  (cells array)
    |
    v
Backend: Generate shadow file, write to /tmp, return cell_map
    |
    v
Frontend: Connect DebugClient, initialize, attach
    |
    v
Frontend: setBreakpoints on shadow_path (all cells' breakpoints combined)
    |
    v
Frontend: configurationDone
    |
    v
Frontend: Execute Cell 0 via Socket.IO (cell:execute)
    |
    v
Backend: execution_bridge wraps code with compile(code, shadow_path, 'exec')
    |
    v
Kernel: executes wrapped code, debugpy sees shadow_path
    |
    v
debugpy: hits breakpoint -> stopped event -> Frontend highlights cell+line
    |
    v
User: F10/F5/Step -> Frontend sends DAP commands
    |
    v
Cell completes -> _onExecuteComplete -> _debugExecNext() -> Execute Cell 1
    |
    v
... repeat until all cells done or user clicks Stop
```

---

## 5. Files to Modify

| File | Change |
|------|--------|
| `backend/app/routers/dap.py` | Add `POST /api/dap/debug-notebook` endpoint |
| `backend/app/managers/execution_bridge.py` | Add `_wrap_for_debug()`, use it when `debug_shadow_path` is set |
| `backend/app/managers/kernel_manager.py` | Add `debug_shadow_path`, `debug_cell_map` to KernelSession |
| `frontend/js/NotebookEditor.js` | Rewrite `debugAll()` and `_debugExecNext()` to use shadow file, update `_onDebugStopped` for line mapping, update step logic for cell boundaries |

---

## 6. What NOT to Change

- `debugCell()` (single-cell debug) - stays as-is with `dumpCell`
- `_execute_silent()` - untouched
- `DebugClient.js` - untouched (DAP protocol is the same)
- `DebugPanel.js` - untouched (variables/call stack work the same)
- `BreakpointGutter.js` - untouched (breakpoints are still per-cell in the UI)

---

## 7. Edge Cases

- **Empty code cells**: skip in the queue, don't include in shadow file
- **Markdown cells**: skip (not executable)
- **Cell with only magics**: the IPython transformer handles them
- **Last expression display**: `ast.Interactive` with `'single'` mode handles auto-display
- **Error in a cell**: `_shell.showtraceback()` renders the error in the cell output, debug continues or stops based on user action
- **Stop during Debug All**: calls `_debugStop()` which clears `_debugExecQueue` and terminates

---

## 8. Multi-Language Extensibility

See `documents/dap/multi_language_plan_feedback.md` for detailed analysis per language.

### Architecture: Strategy Pattern

Refactor `_wrap_for_debug` into a `BaseLanguageStrategy` abstract class with per-language implementations:

```python
class BaseLanguageStrategy:
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        raise NotImplementedError()
    def get_shadow_extension(self) -> str:
        raise NotImplementedError()
    def get_dap_transport(self) -> str:
        return "zmq"  # or "tcp" for xeus kernels
```

### Reusable across all languages:
- Shadow file generation (concatenating cells with markers)
- Cell map and line number mapping
- Frontend: breakpoint translation, stopped event mapping, cell boundary stepping, Debug Panel UI
- Backend: DAP WebSocket relay, ControlChannelDispatcher, debug session lifecycle
- The overall flow: generate shadow file -> set breakpoints -> execute cells with filename injection -> map stopped events back

### Language-specific filename injection methods:

| Language | Kernel | Method | Effort |
|----------|--------|--------|--------|
| Python | ipykernel | `ast.parse` + `compile(code, path, 'exec')` + IPython `transform_cell` | Done |
| Node.js | xeus-js | `eval(code + '\\n//# sourceURL=' + path)` | Low (2-3 weeks) |
| Julia | IJulia | `include_string(Main, code, path)` | Medium (3-4 weeks) |
| R | xeus-r | `source()` + `srcref` patching | High (5-6 weeks) |
| C++ | xeus-cpp | `#line` preprocessor directives | High |

### DAP Transport Protocols:
- **ZMQ (Python)**: DAP messages as `debug_request` on Jupyter control channel. Current `ControlChannelDispatcher` handles this. Must deal with ZMQ identity conflicts and control thread deadlocks.
- **TCP (Xeus kernels)**: Raw TCP port for DAP, separate from Jupyter ZMQ. Requires `dap.py` to act as TCP-to-WebSocket proxy instead of ZMQ-to-WebSocket.

### Recommended implementation order:
1. **Refactor for Strategy (1 week)**: Move Python logic into `PythonStrategy`. Proves `ExecutionBridge` can handle multiple handlers.
2. **Add Node.js (2-3 weeks)**: Lowest-hanging fruit, uses similar eval philosophy. Validates frontend CellMap generality. Requires TCP proxy for xeus-js.
3. **Add Julia (3-4 weeks)**: Clean injection via `include_string`. JIT compilation causes longer timeouts.
4. **Add R (5-6 weeks)**: Most complex. Recommend xeus-r over IRkernel for DAP support.

---

## 9. Testing Checklist

- [ ] Debug All with breakpoints in multiple cells - stops at each
- [ ] F10 stepping within a cell
- [ ] F10 at cell boundary - auto-advances to next cell
- [ ] F5 Continue - runs to next breakpoint in any cell
- [ ] Per-cell output appears correctly (charts, prints, dataframes)
- [ ] Magics (%matplotlib, %time) work inside debug
- [ ] Stop during Debug All - clean termination
- [ ] Normal Run after Debug All - works without kernel restart
- [ ] Debug All after Debug All - works
- [ ] Variables persist across cells (cell 1 defines x, cell 2 uses x)
