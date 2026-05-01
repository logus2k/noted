# noted - Debug Adapter Protocol Integration Plan

## Document Information

| Field         | Value                              |
|---------------|-------------------------------------|
| Document      | DAP Integration Plan                |
| Project       | noted - Integrated MLOps Platform   |
| Version       | 1.0                                 |
| Date          | 2026-04-01                          |
| Status        | Draft                               |
| Related       | LSP Integration Plan, Vision v1.5   |

---

## 1. Purpose

This document defines the integration plan for Debug Adapter Protocol (DAP) support in noted. DAP enables interactive debugging - breakpoints, step execution, variable inspection, and call stack navigation - for Python code in both notebook cells and source files. The implementation uses **debugpy** (Microsoft's Python debugger) and shares the WebSocket infrastructure designed for LSP.

---

## 2. Why DAP

### 2.1 Current State

noted's debugging capabilities:
- **Print debugging** - users add `print()` statements and re-run cells
- **Cell-by-cell execution** - step through by running one cell at a time
- **No breakpoints** - can't pause execution mid-cell
- **No variable inspection** - no way to examine state without print/display
- **No step-through** - can't step line-by-line within a cell

### 2.2 What DAP Provides

| Feature | Description | User Value |
|---|---|---|
| **Breakpoints** | Click gutter to set breakpoints on any line | Pause execution at the exact point of interest |
| **Step execution** | Step over, step into, step out, continue | Fine-grained control over execution flow |
| **Variable inspection** | Browse all variables with types and values | Understand state without print statements |
| **Call stack** | See the full call chain at a breakpoint | Trace how execution reached the current point |
| **Watch expressions** | Monitor specific expressions across steps | Track values without modifying code |
| **Conditional breakpoints** | Break only when a condition is true | Debug specific iterations in loops |
| **Exception breakpoints** | Break on raised/uncaught exceptions | Catch errors at the moment they occur |

### 2.3 Alignment with noted Principles

| Principle | How DAP Aligns |
|---|---|
| P1: Zero Vendor Lock-In | DAP is an open standard. debugpy is open-source (MIT). |
| P2: Backend Services Stay Canonical | The debugger runs inside the kernel process - no state duplication. |
| P3: Integration Over Aggregation | noted renders breakpoint gutters, variable panels, and call stacks as purpose-built UI. |
| P5: Progressive Complexity | Debugging is opt-in - users who don't need it see no UI changes. |

---

## 3. Architecture

### 3.1 Protocol Stack

```
Browser (Debug UI)
    |
    | Plain WebSocket (DAP JSON messages)
    |
noted backend (DAP proxy)
    |
    | TCP socket (DAP JSON messages)
    |
debugpy (attached to kernel process)
    |
    | Controls execution of
    |
Jupyter kernel (Python process)
```

### 3.2 Key Difference from LSP

LSP runs a **separate** language server process alongside the kernel. DAP attaches to the **existing** kernel process. This is critical: the debugger must see the same variables, modules, and state that the notebook cells produce.

| Aspect | LSP | DAP |
|---|---|---|
| Process | Separate language server | Attached to existing kernel |
| Protocol | JSON-RPC 2.0 | DAP (JSON over TCP/socket) |
| Transport | stdio pipe | TCP socket |
| State | File-based (reads .py) | Runtime (live Python process) |
| Lifecycle | Per-project, long-lived | Per-debug-session, transient |

### 3.3 Component Diagram

```
+----------------------------------------------------------+
|  Browser                                                  |
|                                                           |
|  +-------------------+    +---------------------------+  |
|  | NotebookEditor    |    | Debug Panel               |  |
|  | - Breakpoint      |    | - Variables inspector     |  |
|  |   gutter markers  |    | - Call stack              |  |
|  | - Current line    |    | - Watch expressions       |  |
|  |   highlight       |    | - Debug toolbar           |  |
|  +-------------------+    +---------------------------+  |
|           |                          |                    |
+-----------|--------------------------|-------------------+
            |  WebSocket               |
            |  ws://host/ws/dap?       |
            |    kernel=<session_id>   |
            |                          |
+-----------|--------------------------|-------------------+
|  noted backend (FastAPI)             |                    |
|           v                          v                    |
|  +------------------------------------------+            |
|  | DAPProxyManager                           |            |
|  | - WebSocket endpoint (/ws/dap)            |            |
|  | - Attaches debugpy to kernel process      |            |
|  | - DAP message relay                       |            |
|  | - Notebook cell position mapping          |            |
|  +------------------------------------------+            |
|            |                                              |
|            | TCP socket (localhost:<debug_port>)           |
|            v                                              |
|  +------------------------------------------+            |
|  | debugpy (inside kernel process)           |            |
|  | - Breakpoint management                   |            |
|  | - Step execution control                  |            |
|  | - Variable evaluation                     |            |
|  | - Call stack inspection                    |            |
|  +------------------------------------------+            |
|            |                                              |
|            | Controls                                     |
|            v                                              |
|  +------------------------------------------+            |
|  | Jupyter Kernel Process                    |            |
|  | (ipykernel + user code)                   |            |
|  +------------------------------------------+            |
+----------------------------------------------------------+
```

### 3.4 Shared Infrastructure with LSP

| Component | LSP | DAP | Shared? |
|---|---|---|---|
| WebSocket endpoint | `/ws/lsp` | `/ws/dap` | Pattern shared, separate endpoints |
| Proxy manager | `LSPProxyManager` | `DAPProxyManager` | Separate classes, similar structure |
| Position mapping | `NotebookLSPBridge` (Jupytext) | `NotebookDebugMapper` | Separate - DAP maps to runtime, not virtual file |
| CodeMirror extensions | Diagnostics, completions | Breakpoint gutter, line highlight | Separate extensions |
| Frontend panel | Inline in editor | Sidebar debug panel | Separate UI |

---

## 4. debugpy Integration

### 4.1 Why debugpy

- Microsoft's official Python debugger, used by VS Code
- Speaks DAP natively - no adapter layer needed
- Attaches to running processes (no restart required)
- Supports Jupyter kernels via `debugpy.listen()` and `debugpy.connect()`
- Open-source (MIT), actively maintained, pip-installable

### 4.2 Attaching to the Kernel

noted's `KernelManagerService` starts Jupyter kernels via `jupyter_client`. To enable debugging:

1. **Install debugpy** in the kernel's virtual environment
2. **Inject debugpy setup** into the kernel at startup:
   ```python
   import debugpy
   debugpy.listen(("127.0.0.1", 0))  # Listen on a random port
   # Port is communicated back to noted via kernel stdout/env
   ```
3. **Connect** when the user starts a debug session:
   ```python
   debugpy.wait_for_client()  # Blocks until noted's DAP proxy connects
   ```

### 4.3 Kernel Startup Modification

The `KernelManagerService` already injects environment variables at kernel start (MLFLOW_TRACKING_URI, PYTHONPATH, etc.). debugpy setup is added the same way:

```python
# In kernel_manager.py, during kernel startup:
kernel_env['PYTHONSTARTUP_DEBUGPY'] = 'true'

# Or inject via a startup script that the kernel runs:
startup_code = """
import debugpy
_debug_port = debugpy.listen(("127.0.0.1", 0))
print(f"DEBUGPY_PORT={_debug_port[1]}")
"""
```

The debug port is captured from kernel stdout and stored in the session metadata. The DAP proxy connects to this port when debugging begins.

### 4.4 Lifecycle

| Event | Action |
|---|---|
| Kernel starts | debugpy listens on a random port, port stored in session |
| User clicks "Debug" or sets first breakpoint | Frontend opens WebSocket to `/ws/dap`, backend connects to debugpy |
| Debug session active | DAP messages relayed between browser and debugpy |
| User clicks "Stop Debugging" | DAP `disconnect` sent, debugpy detaches, kernel continues normally |
| Kernel restarts | debugpy re-initializes on new port |
| Kernel stops | Debug session ends automatically |

---

## 5. Notebook Cell Debugging

### 5.1 The Problem

Breakpoints are set on cell lines, but debugpy operates on files. When a cell executes, ipykernel uses `exec()` with a synthetic filename like `<ipython-input-5-abc123>`. debugpy needs to map breakpoints to these synthetic filenames.

### 5.2 Solution: Cell-Aware Breakpoint Mapping

When the user sets a breakpoint on line 3 of Cell 5:

1. Frontend sends: `setBreakpoints({ source: { cell_id: "abc123" }, breakpoints: [{ line: 3 }] })`
2. Backend's `NotebookDebugMapper` translates to debugpy's format: `setBreakpoints({ source: { path: "<ipython-input-5-abc123>" }, breakpoints: [{ line: 3 }] })`
3. debugpy sets the breakpoint in the kernel's code object

When execution hits the breakpoint:

1. debugpy reports: `stopped({ reason: "breakpoint", source: { path: "<ipython-input-5-abc123>" }, line: 3 })`
2. Backend maps back: `stopped({ reason: "breakpoint", cell_id: "abc123", line: 3 })`
3. Frontend highlights line 3 in Cell 5

### 5.3 Tracking Cell Execution Names

ipykernel assigns synthetic filenames to each cell execution. noted's `ExecutionBridge` already intercepts kernel messages. We add tracking of the `code` -> `filename` mapping:

```python
# In execution_bridge.py, when a cell executes:
# The kernel's execute_reply contains the filename used
cell_exec_name = f"<ipython-input-{execution_count}-{cell_id}>"
self._cell_filename_map[cell_id] = cell_exec_name
```

### 5.4 Multi-Cell Debugging

When stepping through code that calls functions defined in other cells:

- **Step Into** follows the call into the other cell's code
- The call stack shows entries from multiple cells, each labeled with its cell number
- Variables panel shows the scope of the current frame regardless of which cell defined it

---

## 6. Frontend Integration

### 6.1 Debug Panel (Sidebar View)

A new sidebar view registered in the icon bar, below the existing views:

```
Icon Bar:
  [Projects]
  [TOC]
  [Git]
  [Debug]        <-- new
  [AI Assistant]
  ...
```

The Debug panel contains:

#### Variables Inspector
```
Variables
  Locals
    df          DataFrame    (150, 4)
    model       GRU          <keras.Model>
    epochs      int          30
    loss        float        0.0234
  Globals
    pd          module       <pandas>
    np          module       <numpy>
```

#### Call Stack
```
Call Stack
  > train (cell 4, line 12)
    _build_model (src/model.py, line 45)
    fit (keras/engine/training.py, line 1234)
```

#### Watch Expressions
```
Watch
  + [Add expression]
  model.summary()    <bound method>
  df.shape           (150, 4)
  loss < 0.01        False
```

#### Debug Toolbar
```
[Continue] [Step Over] [Step Into] [Step Out] [Restart] [Stop]
```

### 6.2 Breakpoint Gutter

CodeMirror cells get a breakpoint gutter (left of line numbers):

- **Click** gutter to toggle breakpoint (red dot)
- **Right-click** for conditional breakpoint (yellow dot with condition)
- **Shift-click** for logpoint (diamond icon, logs without stopping)
- Breakpoints persist in notebook metadata under `metadata.noted.breakpoints`

### 6.3 Current Line Highlight

When execution is paused:
- The paused cell scrolls into view
- The current line is highlighted with a yellow/gold background
- An arrow marker appears in the gutter pointing to the current line
- Other cells are slightly dimmed to focus attention

### 6.4 Inline Variable Hover

When paused at a breakpoint:
- Hovering over a variable shows its current value in a tooltip
- This reuses the LSP hover infrastructure (same CodeMirror extension pattern)
- Values are fetched via DAP's `evaluate` request

---

## 7. Backend Implementation

### 7.1 New Components

| Component | File | Responsibility |
|---|---|---|
| `DAPProxyManager` | `backend/app/managers/dap_manager.py` | Manage debugpy connections, WebSocket relay |
| `NotebookDebugMapper` | `backend/app/managers/notebook_debug_mapper.py` | Cell ID to synthetic filename mapping |
| WebSocket endpoint | `backend/app/routers/dap.py` | `/ws/dap` WebSocket route |

### 7.2 DAPProxyManager

```python
class DAPProxyManager:
    """Manages debugpy connections and DAP WebSocket relay."""
    
    # Key: kernel_session_id -> { debugpy_port, tcp_connection, ws_connections }
    _sessions: dict[str, dict]
    
    async def start_debug_session(self, kernel_session_id: str) -> int:
        """Connect to debugpy on the kernel's debug port. Returns debug port."""
        
    async def stop_debug_session(self, kernel_session_id: str):
        """Disconnect from debugpy, resume normal execution."""
        
    async def handle_websocket(self, websocket, kernel_session_id: str):
        """Bidirectional relay between browser WebSocket and debugpy TCP."""
        
    async def set_breakpoints(self, kernel_session_id, cell_id, breakpoints):
        """Set breakpoints, mapping cell positions to debugpy filenames."""
```

### 7.3 NotebookDebugMapper

```python
class NotebookDebugMapper:
    """Maps between notebook cell positions and debugpy synthetic filenames."""
    
    # Key: cell_id -> synthetic filename (e.g. "<ipython-input-5-abc123>")
    _cell_filenames: dict[str, str]
    
    def register_cell_execution(self, cell_id, execution_count):
        """Record the synthetic filename for a cell execution."""
        
    def cell_to_debugpy(self, cell_id, line) -> tuple[str, int]:
        """Map (cell_id, line) to (synthetic_filename, line)."""
        
    def debugpy_to_cell(self, filename, line) -> tuple[str, int]:
        """Map (synthetic_filename, line) to (cell_id, line)."""
```

---

## 8. DAP Message Flow

### 8.1 Starting a Debug Session

```
Browser                    noted backend              debugpy (kernel)
   |                           |                           |
   |-- ws connect /ws/dap ---->|                           |
   |                           |-- TCP connect ----------->|
   |                           |<-- initialize response ---|
   |<-- initialize response ---|                           |
   |-- setBreakpoints -------->|                           |
   |    (cell_id, lines)       |-- setBreakpoints -------->|
   |                           |   (synthetic filename)    |
   |<-- breakpoints verified --|<-- breakpoints verified --|
   |                           |                           |
```

### 8.2 Hitting a Breakpoint

```
Browser                    noted backend              debugpy (kernel)
   |                           |                           |
   |   (user runs cell)        |                           |
   |                           |       (execution hits BP) |
   |                           |<-- stopped (breakpoint) --|
   |<-- stopped (cell_id, ln) -|                           |
   |                           |                           |
   |-- stackTrace request ---->|-- stackTrace request ---->|
   |<-- stackTrace response ---|<-- stackTrace response ---|
   |   (cell_ids, lines)       |   (filenames, lines)      |
   |                           |                           |
   |-- variables request ----->|-- variables request ----->|
   |<-- variables response ----|<-- variables response ----|
   |                           |                           |
```

### 8.3 Stepping

```
Browser                    noted backend              debugpy (kernel)
   |                           |                           |
   |-- stepOver -------------->|-- next ------------------>|
   |                           |<-- stopped (step) --------|
   |<-- stopped (cell_id, ln) -|                           |
   |                           |                           |
```

---

## 9. Run Menu - Final Plan

Debug commands are added to the existing Run menu (currently not present - cells are run via keyboard shortcuts and toolbar buttons).

### Final Run Menu

```
Run
  Run Cell                     Shift+Enter     (hasNotebook)
  Run Cell and Stay            Ctrl+Enter      (hasNotebook)
  Run All Cells                                (hasNotebook)
  Run All Above                                (hasNotebook)
  Run All Below                                (hasNotebook)
  ---
  Start Debugging              F5              (hasKernel)
  Stop Debugging               Shift+F5        (hasDebugSession)
  Restart Debugging            Ctrl+Shift+F5   (hasDebugSession)
  ---
  Continue                     F5              (isPaused)
  Step Over                    F10             (isPaused)
  Step Into                    F11             (isPaused)
  Step Out                     Shift+F11       (isPaused)
  ---
  Toggle Breakpoint            F9              (hasNotebook)
  Conditional Breakpoint...                    (hasNotebook)
  Remove All Breakpoints                       (hasNotebook)
```

### Enabled conditions

| Condition | Meaning |
|---|---|
| `hasNotebook` | A notebook is open |
| `hasKernel` | A kernel is running and debugpy is available |
| `hasDebugSession` | An active debug session exists |
| `isPaused` | Execution is paused at a breakpoint |

---

## 10. Implementation Phases

### Phase D1: debugpy Attachment (2-3 days)

| Task | Description |
|---|---|
| D1.1 | Modify `KernelManagerService` to inject debugpy setup at kernel startup |
| D1.2 | Capture debugpy port from kernel stdout, store in session metadata |
| D1.3 | Create `DAPProxyManager` - TCP connection to debugpy, WebSocket relay |
| D1.4 | Add `/ws/dap` WebSocket endpoint |
| D1.5 | Install `debugpy` in the container image and default venvs |

**Exit criteria:** Backend can connect to debugpy in a running kernel and relay DAP messages.

### Phase D2: Breakpoints and Step Execution (3-4 days)

| Task | Description |
|---|---|
| D2.1 | Create `NotebookDebugMapper` - cell-to-filename position mapping |
| D2.2 | Breakpoint gutter in CodeMirror (click to toggle, red dot) |
| D2.3 | `setBreakpoints` DAP flow with cell-aware mapping |
| D2.4 | Current line highlight when paused |
| D2.5 | Debug toolbar (Continue, Step Over, Step Into, Step Out, Stop) |
| D2.6 | Breakpoint persistence in notebook metadata |

**Exit criteria:** Set a breakpoint in a cell, run the cell, execution pauses, step through line by line.

### Phase D3: Variable Inspection and Debug Panel (3-4 days)

| Task | Description |
|---|---|
| D3.1 | Debug sidebar panel with Variables inspector |
| D3.2 | Call stack display with cell-aware frame labels |
| D3.3 | Watch expressions (add, remove, auto-evaluate on step) |
| D3.4 | Inline variable hover (reuse LSP hover pattern) |
| D3.5 | Conditional breakpoints and logpoints |
| D3.6 | Exception breakpoints (break on raised/uncaught) |

**Exit criteria:** Full debug experience - set breakpoints, inspect variables, navigate call stack, watch expressions.

### Phase D4: Polish and Run Menu (1-2 days)

| Task | Description |
|---|---|
| D4.1 | Add Run menu with all debug commands |
| D4.2 | Keyboard shortcuts (F5, F9, F10, F11) |
| D4.3 | Debug icon in icon bar with sidebar panel |
| D4.4 | Status bar indicator (debug mode active) |
| D4.5 | Dim non-paused cells during debugging |

**Exit criteria:** Complete debug UX matching the Run menu plan above.

**Total estimated effort: 9-13 days**

---

## 11. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| debugpy attachment fails on some kernels | Medium | Graceful fallback - debugging unavailable, cell execution unaffected |
| Synthetic filename mapping breaks across kernel restarts | Medium | Clear mapping on restart, re-set breakpoints automatically |
| debugpy overhead on kernel performance | Low | debugpy has negligible overhead when no breakpoints are set |
| Cell re-execution changes synthetic filenames | Medium | Re-map breakpoints when cell is re-executed |
| Multi-user debugging conflicts | Low | Debug sessions are per-user, per-kernel (already isolated) |
| Large variable inspection (DataFrames, tensors) | Medium | Truncate display, lazy-load children, size limits on evaluation |

---

## 12. Dependencies

| Dependency | Purpose | Size |
|---|---|---|
| `debugpy` | Python debugger, DAP server | ~5MB pip install |
| DAP specification | Protocol reference | Documentation only |
| CodeMirror gutter API | Breakpoint markers | Already in CodeMirror bundle |
| WebSocket (FastAPI) | DAP transport | Already available (shared with LSP) |

No new containers. No Node.js. No external services. debugpy runs inside the existing kernel process.

---

## 13. Impact on Existing Code

| Component | Change |
|---|---|
| `KernelManagerService` | Add debugpy injection at kernel startup |
| `ExecutionBridge` | Track cell execution filenames for debug mapping |
| `CellEditor` | Add breakpoint gutter extension |
| `NotebookEditor` | Handle debug state (paused, current line highlight) |
| `menu.json` | Add Run menu |
| `app.js` | Register Run menu commands, debug panel |
| `IconBar` | Add Debug icon |
| `Dockerfile` | Install `debugpy` |

Existing cell execution is unaffected. debugpy is passive until a debug session is explicitly started.
