# Test 32: Run Python File with Venv

## Objective
Verify that `.py` files can be executed using the active virtual environment from both the Explorer context menu and the file editor top bar.

## Prerequisites
- noted container running
- `noted-testing` project with at least one `.py` file
- A virtual environment created and activated in Virtual Environments section

## Test Procedures

### Test 1: Context Menu - Run with Venv (Active Venv)
1. Navigate to `noted-testing` project in Explorer
2. Create or locate a `.py` file (e.g., `hello.py` with `print("Hello from venv!")`)
3. Right-click the `.py` file
4. Verify "Run with venv" appears in context menu with green play icon
5. Click "Run with venv"
6. **Expected**: Terminal panel opens with title `hello.py (venv_name)`
7. **Expected**: Terminal auto-executes `/app/venvs/{venv_name}/bin/python hello.py`
8. **Expected**: Output "Hello from venv!" appears in terminal

### Test 2: Context Menu - Run with Venv (No Active Venv)
1. Ensure no virtual environment is activated
2. Right-click a `.py` file
3. Click "Run with venv"
4. **Expected**: Terminal opens with title `hello.py (system)`
5. **Expected**: Uses system `python3` to execute the file

### Test 3: File Editor Play Button
1. Open a `.py` file by double-clicking in Explorer
2. Look at the second bar (below breadcrumbs)
3. **Expected**: Green play button visible next to Save and File Details buttons
4. Click the play button
5. **Expected**: Terminal panel opens and executes the file (same behavior as context menu)

### Test 4: Long-Running Process (Web Server)
1. Create a `.py` file with a simple HTTP server:
   ```python
   from http.server import HTTPServer, SimpleHTTPRequestHandler
   print("Server starting on port 8888...")
   HTTPServer(("", 8888), SimpleHTTPRequestHandler).serve_forever()
   ```
2. Run with venv
3. **Expected**: Terminal shows "Server starting on port 8888..."
4. **Expected**: Process keeps running (terminal stays active)
5. Press Ctrl+C in the terminal
6. **Expected**: Server stops, terminal returns to shell prompt

### Test 5: Script with Import from Venv
1. Activate a venv that has `numpy` installed
2. Create a script: `import numpy; print(numpy.__version__)`
3. Run with venv
4. **Expected**: Numpy version printed successfully (uses venv packages)

### Test 6: Context Menu Only for .py Files
1. Right-click a `.ipynb` file
2. **Expected**: "Run with venv" does NOT appear in context menu
3. Right-click a `.csv` or `.yaml` file
4. **Expected**: "Run with venv" does NOT appear in context menu
5. Right-click a `.py` file
6. **Expected**: "Run with venv" DOES appear

### Test 7: Play Button Only for .py Files
1. Open a `.md` file in the editor
2. **Expected**: No play button in second bar (preview toggle may be present)
3. Open a `.py` file in the editor
4. **Expected**: Play button IS present in second bar

## Pass Criteria
- All 7 tests pass
- Terminal correctly identifies and uses the active venv
- Process output streams in real-time
- Long-running processes can be killed with Ctrl+C
- Play button only appears for Python files
