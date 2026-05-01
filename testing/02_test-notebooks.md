# 02 - Notebooks, Environments and Kernels - Test Procedure

## Prerequisites

- noted is running and accessible (Test 01 passed)
- At least one project exists in the Explorer

---

## Test 1: Create a new project

1. In the Explorer panel, click the "+" button or right-click to create a new project
2. Enter a project name (e.g., `TestProject`)
3. **Expected:** Project appears in the Explorer tree
4. **Expected:** Project folder is created at `data/projects/TestProject/`

## Test 2: Create a new notebook

1. Right-click on the project node in the Explorer
2. Select "New Notebook" from the context menu
3. Enter a name (e.g., `test_notebook`)
4. **Expected:** Notebook is created and opens in the editor
5. **Expected:** The notebook has an empty code cell ready for input
6. **Expected:** The tab bar shows the notebook name

## Test 3: Create a virtual environment

1. In the Explorer panel, expand the "Virtual Environments" section
2. Click on a runtime (e.g., "Python 3.12")
3. In the detail panel, enter an environment name (e.g., `test_env`)
4. Click "Create Virtual Environment"
5. **Expected:** An inline terminal shows the creation progress
6. **Expected:** The terminal shows pip/venv setup output
7. **Expected:** After completion, the environment appears in the tree under its runtime

## Test 4: Install packages in the environment

1. Select the newly created environment in the Explorer
2. In the detail panel, find the Packages section
3. Enter package names in the textarea: `numpy pandas matplotlib`
4. Click "Install"
5. **Expected:** A floating terminal panel opens showing pip install output
6. **Expected:** Packages download and install successfully
7. **Expected:** After completion, the packages appear in the installed packages list

## Test 5: Assign kernel to notebook

1. Open the test notebook (from Test 2)
2. Select the virtual environment from the environment selector in the toolbar
3. **Expected:** Kernel starts (status indicator shows "starting" then "idle")
4. **Expected:** The environment name appears in the toolbar/status area

## Test 6: Write and execute a code cell

1. In the first code cell, type:
   ```python
   import numpy as np
   x = np.array([1, 2, 3, 4, 5])
   print(f"Sum: {x.sum()}, Mean: {x.mean()}")
   ```
2. Click the play button on the cell (or press Ctrl+Enter)
3. **Expected:** Cell shows "executing" state briefly
4. **Expected:** Output appears below the cell: `Sum: 15, Mean: 3.0`
5. **Expected:** Cell shows an execution count number (e.g., `[1]`)

## Test 7: Multiple cell execution

1. Add a new code cell (click "+ code" between cells)
2. In the new cell, type:
   ```python
   import pandas as pd
   df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
   df
   ```
3. Execute the cell
4. **Expected:** A formatted table output appears (HTML rendering of the DataFrame)
5. Add another cell:
   ```python
   import matplotlib.pyplot as plt
   plt.figure(figsize=(4, 3))
   plt.plot([1, 2, 3], [1, 4, 9])
   plt.title("Test Plot")
   plt.show()
   ```
6. Execute the cell
7. **Expected:** A plot image appears in the cell output

## Test 8: Markdown cells

1. Add a new markdown cell (click "+ markdown")
2. Type: `# Test Heading\nThis is a **bold** test.`
3. Click outside the cell or press Shift+Enter to render
4. **Expected:** Markdown renders with a heading and bold text

## Test 9: Kernel operations

1. With a running kernel, click the Restart kernel button in the toolbar
2. **Expected:** Kernel status briefly shows "starting" then returns to "idle"
3. Execute a cell that uses a previously defined variable (e.g., `print(x)`)
4. **Expected:** Error output - `NameError: name 'x' is not defined` (kernel state was reset)
5. Re-run the first cell to restore the variable
6. **Expected:** Cell executes successfully

## Test 10: Interrupt execution

1. Execute a long-running cell:
   ```python
   import time
   for i in range(100):
       print(i)
       time.sleep(1)
   ```
2. While it's running, click the Interrupt/Stop button
3. **Expected:** Execution stops with a `KeyboardInterrupt` error
4. **Expected:** Partial output is visible (some numbers printed before interrupt)

## Test 11: Cell error handling

1. Execute a cell with an error:
   ```python
   1 / 0
   ```
2. **Expected:** Error output shows `ZeroDivisionError: division by zero`
3. **Expected:** Traceback is displayed with proper formatting
4. Execute the next cell:
   ```python
   print("Still works")
   ```
5. **Expected:** Executes normally - kernel is not dead after an error

## Test 12: Save and reopen notebook

1. Make changes to the notebook (add cells, outputs)
2. Save the notebook (Ctrl+S or auto-save)
3. Close the notebook tab
4. Re-open the same notebook from the Explorer
5. **Expected:** All cells, code, and outputs are preserved
6. **Expected:** Markdown cells render correctly

## Test 13: Kernel persists across notebook navigation

1. With a running kernel, switch to a different tab (e.g., a service iframe)
2. Switch back to the notebook tab
3. Execute a cell
4. **Expected:** Kernel is still running, execution works without restarting

## Test 14: Multi-notebook tabs

1. Open a notebook from the Explorer (double-click to pin)
2. Open a second notebook from the same or different project (double-click)
3. **Expected:** Both notebooks have their own tabs in the tab bar
4. Switch between tabs
5. **Expected:** Each notebook shows its own cells and state
6. Start a kernel on each notebook (can be same or different venv)
7. Execute a cell in each notebook
8. **Expected:** Each notebook maintains its own kernel and execution state independently

## Test 15: File preview (single-click vs double-click)

1. In the Explorer, single-click on a notebook file
2. **Expected:** Notebook opens in a preview (transient) tab - tab title may appear in italic
3. Single-click on a different notebook file
4. **Expected:** The preview tab is replaced by the new notebook
5. Double-click on a notebook file
6. **Expected:** The tab becomes pinned (permanent) - it will not be replaced
7. Single-click on a `.py` file
8. **Expected:** File content opens in a preview tab (not the file detail panel)
9. Start editing the file
10. **Expected:** Tab becomes pinned automatically when edits are made

## Test 16: Kernel picker

1. Open a notebook and click the kernel selector in the toolbar
2. **Expected:** Kernel picker shows with yellow (#ffe39e) title bar reading "Select Environment Kernel"
3. **Expected:** Available environments are listed with version numbers
4. Select an environment
5. **Expected:** A gold star icon appears at the left of the selected kernel row
6. **Expected:** Kernel starts and status shows in the toolbar

---

## Troubleshooting

- **Kernel won't start:** Check that the virtual environment was created successfully and the runtime exists
- **Package install hangs:** Check network connectivity from the container (`docker exec noted ping pypi.org`)
- **No output from cell:** Check browser console for Socket.IO connection errors
- **Plot doesn't render:** Ensure matplotlib is installed and the kernel was restarted after installation
- **"No active kernel" error:** Select an environment and wait for the kernel status to show "idle"
