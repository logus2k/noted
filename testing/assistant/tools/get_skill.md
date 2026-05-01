# Tool: get_skill

**Type:** tool
**Tier:** read
**Domain:** skills
**Handler:** [backend/app/managers/llm_tools.py `_tool_get_skill`](../../../backend/app/managers/llm_tools.py)

## Purpose

Loads detailed instructions for a specific topic. Skills marked priority-1 auto-inject when their triggers fire — the Assistant must NOT call `get_skill` for those (already in context). Backend redirects already-active fetches.

## Input schema

- `skill_name` (required); `reference` (optional).

## Setup prerequisites

- Skill files in `data/skills/`.

## Scenarios

### S1 - Fetch non-active skill
"load dvc-versioning" → `get_skill(skill_name="dvc-versioning")`.

### S2 - Don't fetch already-active
"what does noted-platform-overview say?" → already injected; answer from context; do NOT call.

### S3 - Skill not found
Tool errors; report.

### S4 - Pre-flight specialized task
"set up Hydra" → `get_skill("hydra-setup")` if not active.

### S5 - Load reference doc
Direct call; report content.

### S6 - Skill with reference (DEFERRED)
### S7 - Large skill content (DEFERRED)
