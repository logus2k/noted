# Tool: create_file

**Type:** tool
**Tier:** write
**Domain:** files
**Handler:** [backend/app/managers/llm_tools.py](../../../backend/app/managers/llm_tools.py)

## Purpose

Creates a new project file with given content + description. NOT for existing files (use `update_file`); risky for `.ipynb` (JSON structure).

## Scenarios

### S1 - New Python file
COMPLETE initial content + description.

### S2 - Don't use for existing
Check first; ask user (overwrite vs modify); never overwrite silently.

### S3 - New config file
Create YAML; mention selectability in Hydra group.

### S4 - Don't use for notebook
.ipynb needs valid JSON; suggest UI flow.

### S5 - Description arg
Explains purpose; content has the code.

### S6 - Deeply-nested non-existent path (DEFERRED)
### S7 - Binary file (DEFERRED)
