# Technical Specification: Multi-Language "Debug All" Architecture

This document outlines the architectural shift from Python-specific debugging to a **Language Strategy Pattern**. It addresses the "Fundamental Tension" between unified file breakpoints and discrete cell execution, while providing a roadmap for JavaScript (and future) integration.

---

## 1. Core Architectural Concept: Filename Injection

To support "Debug All" across cells, we must trick the language's debugger into seeing a single continuous source file, while the Jupyter kernel maintains the ability to route output to specific cells.



### The Strategy Interface
The `ExecutionBridge` no longer handles raw code. It delegates to a `LanguageStrategy`.

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
        """Returns file extension (.py, .js, etc.)"""
        pass
```

---

## 2. Python Implementation (The Baseline)

Python requires an **IPython-Aware Wrapper**. We use the `ast` module to ensure that magics are transformed and the last expression is still rendered as rich output (DataFrames, Plots).



### PythonStrategy.py
```python
class PythonStrategy(BaseLanguageStrategy):
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        # Use repr() to safely escape the cell code string
        return f"""
import ast
from IPython import get_ipython
_shell = get_ipython()

# 1. Transform magics (%matplotlib, !pip)
_transformed = _shell.input_transformer_manager.transform_cell({repr(code)})

# 2. Add padding so line numbers match the shadow file exactly
_padded = ("\\n" * ({start_line} - 1)) + _transformed

# 3. Parse and execute with 'shadow_path' as the filename
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

---

## 3. JavaScript Implementation (The New Frontier)

JavaScript support leverages `xeus-javascript` and the V8 engine’s `sourceURL` feature.

### JavascriptStrategy.py
```python
class JavascriptStrategy(BaseLanguageStrategy):
    def wrap_code(self, code: str, shadow_path: str, start_line: int) -> str:
        # Node.js/V8 uses the //# sourceURL comment to map code to a file
        # We inject newlines to align the cell code with the shadow file lines
        padding = "\\n" * (start_line - 1)
        return f"{padding}{code}\\n//# sourceURL={shadow_path}"

    def get_extension(self) -> str:
        return ".js"
```

---

## 4. The DAP Orchestration Logic (dap.py)

To prevent the "Control Thread Deadlock" and support cross-cell stepping, the backend must act as a sophisticated state machine.

### The Sequence for "Step Over" at Cell Boundaries:
1. **Detection:** Frontend reports F10 on the last line of Cell $N$ (using `CellMap`).
2. **Backend Interception:** - Backend sends DAP `continue` (to finish Cell $N$).
   - Backend waits for `iopub` status `idle`.
   - Backend triggers `ExecutionBridge.execute_cell(N + 1, is_debug=True)`.
3. **Optimistic Stepping:** Frontend moves the highlight to the first line of the next cell immediately.



---

## 5. Deployment & Tooling Roadmap

### Infrastructure (Backend)
- **Kernel:** Install `xeus-javascript` in the Docker container.
- **DAP Proxy:** Update `dap.py` to handle kernels that open a separate TCP port for DAP (common in Xeus kernels) instead of just ZMQ.
- **Environment:** Implement `fnm` (Fast Node Manager) to manage Node versions per project, similar to how VENVs manage Python versions.

### User Experience (Frontend)
- **LSP:** Connect to `typescript-language-server` for JS/TS IntelliSense.
- **Linting:** Integrate **Biome** (the "Ruff of JS") for sub-millisecond linting and formatting.
- **Optimistic UI:** Implement a `step_counter` in `DebugClient.js` to discard stale `stopped` events if the user clicks F10 rapidly.

---

## 6. Effort and Specificity Notes

| Task | Language | Difficulty | Note |
| :--- | :--- | :--- | :--- |
| **Shadow File Generation** | All | Low | Reuse `NotebookLSPBridge`. |
| **Filename Injection** | JavaScript | Low | `sourceURL` is a native V8 feature. |
| **Filename Injection** | R | High | Requires manual `srcref` patching in the R interpreter. |
| **TCP DAP Proxy** | All (Xeus) | Medium | Required for non-Python kernels. |

### Summary Recommendation
Start with the **PythonStrategy** refactor to validate the line-mapping logic. Then move to **JavaScript** using `xeus-javascript`. The jump to JS will force you to build the **TCP DAP Proxy**, which is the final bridge needed to support any other language in the Jupyter ecosystem.
