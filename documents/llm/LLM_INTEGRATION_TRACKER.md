# LLM Integration - Progress Tracker

Full design: [LOCAL_LLM_INTEGRATION_PLAN.md](LOCAL_LLM_INTEGRATION_PLAN.md)

---

## Status Overview

| Phase | Description | Status | Notes |
|---|---|---|---|
| A | Connectivity | Done | agent_server on noted-network, Qwen 3 8B Q8, noted preset active |
| B | Context-Enriched Chat | Done | Context assembly, SSE streaming, ThinkingParser, cell selection, MLflow summary |
| C | Tool Calling | Done | 11 read tools, stream-first tool loop, tool badges, voice tag support |
| D | Chat Panel Refinements | Done | Project-scoped memory, clear button, copy code, auto-scroll, error display, health LED |
| E | MLOps UI Buttons | In Progress | "Ask Assistant" menu on cells, Hydra->Airflow integration done |
| F | Skills System | Done | 36 skills in folder/SKILL.md format, static injection + dynamic get_skill tool, skill badges |
| G | Write Tools | Not Started | update_cell, insert_cell with confirmation UI (jsPanel diff view) |
| H | Inline Completion | Not Started | CodeMirror ghost-text (concurrency-sensitive) |
| I | Anthropic API Backend | Not Started | Swap agent_server for Anthropic API as LLM backend |

---

## Phase A: Connectivity - DONE

- [x] agent_server on noted-network (external network in compose)
- [x] Qwen 3 8B Q8 active model, n_ctx=32768
- [x] noted agent preset with thread_window memory
- [x] System prompt with MLOps persona, tools, cell selection, voice output
- [x] Connectivity verified end-to-end

---

## Phase B: Context-Enriched Chat - DONE

New files:
- [x] `backend/app/managers/llm_manager.py` - httpx client to /v1/chat/completions
- [x] `backend/app/managers/llm_context.py` - context builders (notebook, MLflow, Hydra)
- [x] `backend/app/routers/llm.py` - /api/llm/chat (SSE), /api/llm/complete, /api/llm/health

Frontend:
- [x] ChatService.js - dual-path chat, ThinkingParser, context provider
- [x] ChatPanel.js - streaming messages, thinking indicator, collapsible reasoning
- [x] app.js - _buildLLMContext(), context provider wiring
- [x] chat-panel.css - full chat styling

Validated:
- [x] Notebook context injection, cell selection tracking, MLflow experiment summary
- [x] Token-by-token streaming, thinking collapsible UI
- [x] System prompt tuned for auto-instrumentation awareness

---

## Phase C: Tool Calling - DONE

- [x] 11 read tools: MLflow (3), Airflow (3), DVC (2), Files (1), Hydra (1), Knowledge Graph (1)
- [x] Stream-first tool loop (up to 6 rounds) with exhausted-loop fallback
- [x] Tool badges in UI (orange pills, hover for args)
- [x] ThinkingParser filters `<tool_call>` blocks from visible output
- [ ] Write tools + frontend confirmation widget (deferred)

---

## Phase D: Chat Panel Refinements - DONE

- [x] Project-scoped memory with file persistence (`backend/app/managers/llm_memory.py`)
  - Keyed by client_id + project_id (per-user, per-project conversations)
  - Auto-compaction via LLM summarization when token budget threshold hit
  - History survives container restarts
- [x] 32K context window (agent_config n_ctx=32768, max_context_tokens=32768)
- [x] Clear chat button (header bar, clears frontend + backend)
- [x] Copy code blocks (hover button on pre elements)
- [x] Error display (styled error cards)
- [x] Health LED via HTTP /api/llm/health + Socket.IO heartbeat
- [x] Chat history restore on page reload
- [x] Voice `<voice>` tag support in ThinkingParser (strips from display, routes to TTS)
- [x] System prompt updated with voice output directive

---

## Phase E: MLOps UI Buttons - NOT STARTED

- [ ] "Ask Assistant" on run detail panel
- [ ] "Explain Difference" on run comparison panel
- [ ] "Explain Error" in task log viewer
- [ ] "Explain" / "Refactor" on notebook cell toolbar
- [ ] "Suggest Sweep" on Hydra config panel

---

## Phase F: Inline Completion - NOT STARTED

- [ ] /api/llm/complete endpoint (exists, needs testing)
- [ ] CodeMirror 6 ViewPlugin (CompletionExtension.js)
- [ ] Integrate into CellEditor.js + FileEditor.js
- [ ] Kernel namespace introspection

---

## Shared File Warnings

These noted files may be modified by other agents. Coordinate before editing:
- `backend/app/main.py` (Phase B)
- `frontend/js/ChatService.js` (Phase B)
- `frontend/js/CellEditor.js` (Phase F)
- `frontend/js/FileEditor.js` (Phase F)

---

## Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-03-22 | Use agent_server instead of Ollama | Already running, same llama.cpp engine, has Socket.IO + presets + memory |
| 2026-03-22 | Qwen 3 8B Q8 as active model | Replaces Qwen 3.5 9B. Supports /think and /no_think modes |
| 2026-03-22 | Tool calling via structured output | agent_server doesn't support native tools param. Using `<tool_call>` JSON blocks |
| 2026-03-22 | pool_size=1, VRAM at 22.8/24 GB | No room for second engine. Tool loop is sequential |
| 2026-03-23 | Project-scoped memory in noted backend | Persistent (file-based), per-user per-project, with auto-compaction. Agent_server memory stays for direct/voice path |
| 2026-03-23 | 32K context window | Qwen 3 natively supports 32K. Gives room for longer conversations + rich context |
| 2026-03-23 | Health LED via HTTP + Socket.IO heartbeat | No polling; check on startup, Socket.IO handles ongoing status |
| 2026-03-23 | Voice via `<voice>` tag, not separate LLM call | No extra latency, no queue contention with pool_size=1. ThinkingParser strips from display |
| 2026-03-23 | Anthropic API integration planned | After local phases complete, test with Claude as backend for quality comparison |
