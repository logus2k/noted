# LLM Write Tools - Design Document

## Overview

Write tools enable the LLM to propose changes to the user's workspace (notebook cells, files) with a confirmation step before execution. The user always has final say - the LLM proposes, the user approves.

## Principles

1. **No silent modifications** - Every write action requires explicit user approval
2. **Visual diff** - The user sees exactly what will change before approving
3. **Reversible** - Apply can be undone (Ctrl+Z in the cell editor)
4. **Consistent UI** - Confirmation panels use jsPanel, matching noted's existing floating panels

## Write Tools (Phase 1)

### update_cell

Updates the content of an existing notebook cell.

```
Tool: update_cell
Args: {
    "project_id": "string",      // project or mount ID (optional - defaults to current context)
    "notebook_path": "string",   // notebook path within project (optional - defaults to current context)
    "cell_index": number,        // 0-based cell index
    "new_content": "string",     // proposed new cell content
    "description": "string"      // short description of what changed
}
```

**Path resolution:**
- If `project_id` and `notebook_path` are provided, use them explicitly
- If omitted, fall back to the current context descriptor (the focused notebook)
- If neither is available, return an error: "No target notebook specified"
- Backend validates the path exists before creating the pending action

**Flow:**
1. LLM outputs `<tool_call>{"name": "update_cell", "args": {...}}</tool_call>`
2. Backend resolves the target notebook (explicit args or current context)
3. Backend fetches the current cell content for diff comparison
4. Backend detects this is a write tool - does NOT execute immediately
5. Backend sends SSE event: `data: {"pending_action": {"id": "uuid", "tool": "update_cell", "args": {...}, "current_content": "..."}}`
6. Frontend renders a jsPanel with:
   - Header: "Proposed Change - Cell {index} in {notebook_name}" with cell type icon
   - Body: unified diff (old content vs new content) with syntax highlighting
   - Footer: "Apply" (green) + "Reject" (red) buttons
5. User clicks Apply:
   - Frontend sends `POST /api/llm/confirm` with `{"action_id": "uuid", "approved": true}`
   - Backend applies the change via NotebookManager
   - Tool result returned to LLM: "Cell {index} updated successfully"
   - LLM continues with follow-up answer
6. User clicks Reject:
   - Frontend sends confirm with `{"approved": false}`
   - Tool result returned to LLM: "User rejected the change"
   - LLM acknowledges and may suggest alternatives

### insert_cell

Inserts a new cell into the notebook.

```
Tool: insert_cell
Args: {
    "project_id": "string",      // optional - defaults to current context
    "notebook_path": "string",   // optional - defaults to current context
    "after_cell_index": number,  // insert after this cell (-1 for beginning)
    "cell_type": "code" | "markdown",
    "content": "string",         // cell content
    "description": "string"      // short description
}
```

**Path resolution:** Same as update_cell - explicit args or current context fallback.

**Flow:**
Same confirmation pattern as update_cell, but the panel shows:
- Header: "Insert {type} Cell after Cell {index} in {notebook_name}"
- Body: proposed content with syntax highlighting (no diff needed - it's new)
- Footer: Apply + Reject

## Write Tools (Phase 2 - future)

| Tool | Description |
|---|---|
| `delete_cell` | Remove a cell (with content preview in confirmation) |
| `create_file` | Create a new file in the project |
| `update_file` | Edit an existing project file |
| `trigger_dag` | Trigger an Airflow DAG run |
| `register_model` | Register a model in MLflow Registry |

## Architecture

### Backend

```
POST /api/llm/chat (existing)
  - Stream response as before
  - When a write tool is detected:
    - Generate action_id (UUID)
    - Store pending action in memory (action_id -> tool_call details)
    - Send SSE event: {"pending_action": {...}}
    - Pause the tool loop (wait for confirmation)

POST /api/llm/confirm (new endpoint)
  - Receives: {"action_id": "uuid", "approved": bool}
  - If approved: execute the write action, return tool result to LLM
  - If rejected: return rejection message to LLM
  - Resume the tool loop / stream the LLM's follow-up response
```

### Frontend

```
ChatService.js:
  - Handles "pending_action" SSE event
  - Calls ChatPanel.showConfirmationPanel(action)

ChatPanel.js:
  - showConfirmationPanel(action):
    - Creates jsPanel with diff view
    - Apply button -> POST /api/llm/confirm {approved: true}
    - Reject button -> POST /api/llm/confirm {approved: false}
    - After confirmation, stream resumes with LLM follow-up

Diff rendering:
  - Use a simple unified diff algorithm (or just side-by-side display)
  - Syntax highlight both old and new with hljs
  - Additions in green background, deletions in red background
```

### Confirmation Panel Layout

```
+-----------------------------------------------+
| Proposed Change - Cell 5 (code)          [x]  |
+-----------------------------------------------+
|                                               |
|  - old_line_1                    (red bg)     |
|  + new_line_1                    (green bg)   |
|    unchanged_line                             |
|  - old_line_2                    (red bg)     |
|  + new_line_2                    (green bg)   |
|  + new_line_3                    (green bg)   |
|    unchanged_line                             |
|                                               |
|  Description: Added error handling for NaN    |
|  values in the loss computation               |
|                                               |
+-----------------------------------------------+
|        [ Apply ]          [ Reject ]          |
+-----------------------------------------------+
```

## System Prompt Update

Add to the agent_server system prompt:

```
Write tools (require user confirmation before executing):
13. update_cell - Modify a notebook cell. Args: {"project_id": "string (optional)", "notebook_path": "string (optional)", "cell_index": number, "new_content": "string", "description": "string"}
14. insert_cell - Insert a new cell. Args: {"project_id": "string (optional)", "notebook_path": "string (optional)", "after_cell_index": number, "cell_type": "code"|"markdown", "content": "string", "description": "string"}

Rules for write tools:
- ALWAYS provide a clear description of what you're changing and why.
- For update_cell, include the COMPLETE new cell content, not just the changed lines.
- Prefer minimal changes - don't rewrite entire cells when only a few lines need to change.
- If the user asks to "fix", "improve", or "refactor" code, use update_cell.
- If the user asks to "add", "create", or "write" new code, use insert_cell.
- If project_id and notebook_path are omitted, the currently focused notebook is used.
- If the user references a different notebook by name, include the path explicitly.
```

## Token Budget Impact

Write tool calls include the full cell content in the `new_content` arg, which can be large. For a typical code cell (~50 lines, ~1500 chars), this adds ~400 tokens to the response. Within budget for 32K context.

## Security Considerations

- Confirmation is mandatory - no bypass path
- The pending action is stored server-side with a UUID - the frontend can't fabricate actions
- Actions expire after 5 minutes if not confirmed (timeout cleanup)
- Only the session that initiated the action can confirm it
