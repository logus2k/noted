# Unified Technical Specification: Multi-Language "Debug All" Architecture

## 1. Architectural Vision & The "Fundamental Tension"
To support stepping through multiple notebook cells seamlessly ("Debug All"), the architecture must resolve the fundamental tension between **Breakpoints** (which require a single, unified file) and **Output/Execution** (which requires discrete cell execution). 

The solution is **Filename Injection** via a **Language Strategy Pattern**. By dynamically wrapping cell code before passing it to the kernel, we "trick" the language's debugger into mapping the execution to a backend-generated "Shadow File," while preserving the kernel's ability to map `iopub` output to individual cells.

---

## 2. Core Architecture: The Strategy Pattern

The `ExecutionBridge` is refactored to delegate language-specific code preparation to a `LanguageStrategy` interface. This abstracts the differences in how languages handle code compilation and source mapping.

### The Abstract Interface
```python
# backend/app/managers/strategies.py
from abc import ABC, abstractmethod

class BaseLanguageStrategy(ABC):
    @abstractmethod
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        """Injects filename/line metadata into the execution string."""
        pass

    @abstractmethod
    def get_extension(self) -> str:
        """Returns file extension (e.g., '.py', '.js')"""
        pass
        
    @abstractmethod
    def get_dap_transport(self) -> str:
        """Returns 'zmq' (ipykernel) or 'tcp' (xeus)"""
        return "zmq"
```

### Python Implementation (Baseline)
Python relies on an **IPython-Aware Wrapper** using the `ast` module to preserve Jupyter magics (`%`, `!`) and auto-display hooks (DataFrames, plots).

```python
class PythonStrategy(BaseLanguageStrategy):
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        return f"""
import ast
from IPython import get_ipython
_shell = get_ipython()

# Transform magics
_transformed = _shell.input_transformer_manager.transform_cell({repr(code)})

# Align line numbers with the shadow file
_padded = ("\\n" * ({start_line} - 1)) + _transformed

# Parse and execute using compile() to inject the shadow_path
_tree = ast.parse(_padded)
if _tree.body and isinstance(_tree.body[-1], ast.Expr):
    _last = _tree.body.pop()
    _exec_node = ast.Module(body=_tree.body, type_ignore_list=[])
    _eval_node = ast.Interactive(body=[_last])
else:
    _exec_node = _tree
    _eval_node = None

exec(compile(_exec_node, {repr(shadow_path)}, 'exec'), _shell.user_ns)
if _eval_node:
    exec(compile(_eval_node, {repr(shadow_path)}, 'single'), _shell.user_ns)
"""
```

### JavaScript Implementation (New Target)
JavaScript simplifies the wrapper by relying on the V8 engine's native `sourceURL` pragma.

```python
class JavascriptStrategy(BaseLanguageStrategy):
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        padding = "\\n" * (start_line - 1)
        return f"{padding}{code}\\n//# sourceURL={shadow_path}"

    def get_extension(self) -> str:
        return ".js"
        
    def get_dap_transport(self) -> str:
        return "tcp"
```

---

## 3. JavaScript Tooling & UX Mapping

To ensure the JavaScript UX matches the high standards of the Python environment, the backend and frontend tooling must be carefully selected to map to existing paradigms.

| Feature Area | Python Ecosystem | JavaScript Target Equivalent | Notes |
| :--- | :--- | :--- | :--- |
| **Virtual Environments** | `venv` | `fnm` + `pnpm` | Detect `package.json`. Use `fnm` (Fast Node Manager) for version switching. Use `pnpm` for content-addressable, disk-efficient package caching across projects. |
| **LSP / Autocomplete** | Jedi | `typescript-language-server` | Even for plain `.js` files, TS-Server provides superior type inference and IntelliSense. |
| **Linting & Formatting** | Ruff | Biome | Biome replaces ESLint/Prettier. It is written in Rust, exceptionally fast, and consolidates linting and formatting into a single tool. |
| **Execution Kernel** | `ipykernel` | `xeus-javascript` | Standardizes execution on Node.js, ensuring compatibility with standard `npm` modules (unlike Deno). |
| **Debugger** | `debugpy` | `vscode-js-debug` | Industry-standard debugger for V8/Node.js environments. |

---

## 4. DAP Orchestration & Transport Logistics

### Cross-Cell Stepping Logic (`dap.py`)
To prevent deadlocks and maintain a fluid UX when a user steps (F10) over a cell boundary:
1. **Detection:** The frontend tracks cell boundaries using a `CellMap`. When F10 is pressed on the final line of Cell *N*, it signals a boundary event.
2. **Backend Interception:** The backend converts the `next` command to a `continue` command to let Cell *N* terminate gracefully.
3. **Trigger Next:** Once the backend receives an `iopub` status of `idle`, it automatically triggers `ExecutionBridge.execute_cell(N + 1, is_debug=True)`.
4. **Optimistic UI:** The frontend visually moves the highlight to Cell *N+1* instantly, masking kernel latency.

### The Transport Protocol Shift (Crucial Architectural Change)
Integrating `xeus-javascript` introduces a paradigm shift in how DAP messages are routed:
* **Python (`ipykernel`):** Routes DAP messages inside the Jupyter ZMQ Control channel. This is prone to thread deadlocks requiring strict `disconnect` sequencing.
* **JavaScript (`xeus-javascript`):** Opens a **dedicated TCP port** for DAP communication. Your `dap.py` router must be upgraded to act as a **WebSocket-to-TCP proxy** for non-Python kernels, completely bypassing ZMQ for debug traffic.

---

## 5. Implementation Roadmap & Effort Estimation

| Phase | Milestone | Est. Effort | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Refactor to Strategy Pattern** | 1-2 Weeks | Extract current Python logic into `PythonStrategy`. Validate line mapping and "Shadow File" logic without breaking existing UX. |
| **Phase 2** | **JS Environment & LSP Support** | 2 Weeks | Implement `fnm`/`pnpm` environment generation. Integrate `typescript-language-server` and `Biome` into the WebSocket proxy. |
| **Phase 3** | **JS Execution & TCP Proxy** | 2-3 Weeks | Install `xeus-javascript`. Build the TCP DAP proxy logic into `dap.py` to support external debugger ports. |
| **Phase 4** | **JS Debug Integration** | 1 Week | Implement `JavascriptStrategy` (`sourceURL` injection). Wire frontend `DebugClient` to handle JS-specific stack frame mapping. |

*(Note: Future languages like R (`xeus-r`) or C++ (`xeus-cpp`) will require significantly higher effort—estimated 4-6 weeks—due to complex source reference patching and recompilation requirements, but will reuse the TCP Proxy built in Phase 3).*

---

## 6. Key JavaScript Caveats to Watch For

1. **Module Resolution:** Standardize shadow file generation to force **ESM (ECMAScript Modules)**. Avoid mixing `require()` and `import` across notebook cells to prevent runtime context conflicts.
2. **Top-Level Await:** Ensure `xeus-javascript` is configured to support top-level await, as users will expect `const data = await fetch(...)` to work at the root level of a cell (similar to IPython).
3. **Data Visualization:** Unlike Python's Pandas, JS lacks a native dataframe visualizer. You will need to integrate libraries like **Arquero** or **Danfo.js** and build custom frontend mimetype handlers to render their table outputs properly within the cell output blocks.
