# Technical Architecture Document: Local Sub-Agent Orchestration

## 1. Executive Summary
This document outlines the architecture for integrating a sub-agent workflow into a localized LLM environment. It leverages a single base model (**Gemma 4 4B Q4**) multiplexed across different personas using an `agent_server` and `llama.cpp`. By separating planning, orchestration, and execution, and by utilizing an ephemeral worker model with a shared "Blackboard" state, the system maximizes hardware efficiency (VRAM) while enabling complex, multi-step autonomous workflows.

---

## 2. Core Architecture Principles

### 2.1 Single-Model Multiplexing
Instead of loading multiple models into VRAM, the system dynamically switches the persona of a single loaded Gemma 4 4B model. Each "Agent" is functionally just a unique System Prompt and a specific set of Model Context Protocol (MCP) tools.

### 2.2 Ephemeral Workers
Sub-agents have **no persistent memory**. They are instantiated with a clean context window containing only:
1. Their persona (System Prompt).
2. The specific task assigned to them.
3. Relevant state extracted from the Blackboard.
*Benefit: Prevents context degradation, minimizes VRAM KV-cache bloat, and reduces hallucination.*

### 2.3 The "Blackboard" State Management
Because sub-agents are ephemeral, state is maintained externally in a shared, memory-mapped file (e.g., a RAM-disk like `/dev/shm` on Linux). 
* Agents read from this file to understand the current project state.
* Agents write to this file (via MCP tools) to publish their results.

---

## 3. System Components

1.  **LLM Engine:** `llama.cpp` serving Gemma 4 4B Q4.
2.  **Orchestration Layer:** `agent_server` supporting role-based system prompts and tool injection.
3.  **Tool Registry:** MCP (Model Context Protocol) exposing local functions and the Blackboard to the agents.
4.  **Real-Time Telemetry:** * **SSE (Server-Sent Events):** Streams token generation (e.g., the `<|think|>` blocks and final text).
    * **Socket.io:** Emits structured orchestration events (e.g., `agent_switch`, `task_complete`).
5.  **UI Components:** Main Chat Interface + Advanced Debug Panel for telemetry visualization.

---

## 4. The Execution Workflow

The system utilizes a **State Machine** driven by a Supervisor and a Planner.

### Phase 1: Triage & Planning
1.  **User Request:** The user submits a prompt.
2.  **Supervisor Assessment:** The Supervisor (Gemma 4) determines if the task requires a complex workflow or can be handled directly.
3.  **Delegation to Planner:** If complex, the Supervisor calls the `Planner` sub-agent via MCP.
4.  **Plan Generation:** The Planner returns a structured JSON sequential list of tasks, specifying which sub-agent role should handle each task.

### Phase 2: Sequential Execution
1.  **Blackboard Initialization:** The `agent_server` creates a temporary workflow file (e.g., `session_123_working_draft.md`) on a RAM-disk.
2.  **The Loop:** The Supervisor iterates through the JSON task list:
    * Reads the next task.
    * Invokes the required sub-agent (e.g., `Coder`, `Researcher`, `Critic`) via MCP.
    * Passes the task instructions and the path to the Blackboard file.
3.  **Sub-Agent Processing:** * The sub-agent reads the Blackboard (if needed), performs its task, and uses an `update_workspace` MCP tool to write its results back to the Blackboard file.
    * The sub-agent process terminates (KV cache cleared).
4.  **Progress Tracking:** The Supervisor marks the task as complete and moves to the next.

### Phase 3: Finalization
1.  **Completion Assessment:** The final task in the Planner's list triggers the Supervisor to summarize the workflow.
2.  **User Notification:** The Supervisor reads the final state of the Blackboard file and formats a human-friendly response for the user.

---

## 5. Telemetry & The Debug Panel

To prevent the "black box" latency issue inherent to sequential local LLM processing, the system streams its internal state to a dedicated UI Debug Panel.

### 5.1 Socket.io Event Schema
The `agent_server` emits the following events for UI orchestration:

| Event Name | Payload Example | Action in UI (Debug Panel) |
| :--- | :--- | :--- |
| `workflow_started` | `{ "id": "wf_123", "plan": [...] }` | Renders the sequential checklist. |
| `agent_switch` | `{ "from": "Supervisor", "to": "Coder" }` | Updates the "Active Agent" badge. |
| `task_update` | `{ "task_id": 2, "status": "running" }` | Shows a loading spinner on the active task. |
| `workspace_sync` | `{ "delta": "def main():..." }` | Live-updates the "Blackboard" preview tab. |
| `system_request` | `{ "type": "approval", "prompt": "..." }` | Pauses execution and asks user for permission. |

### 5.2 SSE Stream Routing
* **Main Chat:** Only receives final outputs from the Supervisor.
* **Debug Panel:** Subscribes to the raw token stream of the currently active sub-agent, specifically rendering the `<|think|>` tags to visualize the model's reasoning process.

---

## 6. Implementation Guidelines & Pro-Tips

### 6.1 Prompt Tuning for Gemma 4
* **The Supervisor:** Must have high-level instructions. *Example:* "You are an Orchestrator. You do not do the work. If a task requires coding or deep research, delegate it using your available tools. Your primary job is to ensure the Planner's list is executed."
* **The Sub-Agents:** Should be tightly constrained. *Example:* "You are a Coder. Read the provided file path, write the requested function, and use the `update_workspace` tool to save it. Do not output conversational filler."
* **Thinking Tags:** Allow Gemma 4 to use its native `<|think|>` protocol for complex logic, but strip these tags from the final saved Blackboard output to prevent polluting the context for the next agent.

### 6.2 Context Management
* **Strict Pruning:** When the Supervisor reads the Blackboard file to check progress, only inject the *most recent* additions or a condensed summary if the file exceeds 4,000 tokens. Gemma 4 has a 128k window, but keeping it small ensures fast time-to-first-token (TTFT).

### 6.3 Handling Failures & Hallucinations
* **The Critic Loop:** Always configure the Planner to insert a `Critic` or `Reviewer` task after any `Coder` or `Data Extractor` task. The Critic sub-agent's sole job is to read the Blackboard and verify the previous agent's work against the original goal.
* **Human-in-the-Loop (HITL):** Use Socket.io to allow the user to pause the execution loop from the Debug Panel if they see the Blackboard going off-track.

### 6.4 MCP Integration Hints
* Implement the Blackboard access as two standard MCP tools: `read_blackboard(path)` and `write_blackboard(path, content, mode='append'|'overwrite')`.
* Ensure file locking mechanisms are in place if you ever expand to parallel sub-agent execution, though for this sequential architecture, simple I/O is sufficient.
