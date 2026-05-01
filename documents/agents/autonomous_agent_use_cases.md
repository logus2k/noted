# Autonomous agent: use cases + architecture

## Premise

An assistant in noted that, when it encounters a capability gap, can autonomously draft a new **skill** (text instructions, optionally referencing a helper script) and propose it for the user's review. After approval, the new capability becomes part of Gemma's repertoire without editing noted's backend code.

Three use cases stress different parts of the loop. The architecture must satisfy all three.

---

## Use Case 1 — Domain knowledge gap (text-only skill)

### Problem

User asks a question about a topic Gemma has weak coverage of (e.g., a niche library, a specialized statistical method, a domain framework). Gemma's training-memory answer is hedge-laden or wrong. The user has to context-dump every time.

### Requirements

| # | Requirement |
|---|---|
| R1.1 | Gemma can detect "I am about to give a low-confidence answer" and offer to research instead. |
| R1.2 | Gemma uses `fetch_url` (and ideally a search step) to gather authoritative source material. |
| R1.3 | Gemma synthesizes findings into a SKILL.md body — not a copy-paste of sources. |
| R1.4 | The proposed skill lands in a `skill_proposals/` review folder, not directly in `data/domains/<id>/skills/`. |
| R1.5 | The user can promote a proposal with one action; promotion triggers a SkillRegistry rescan. |
| R1.6 | After promotion, the next conversation that matches the skill's description loads it via `get_skill`. |

### Acceptance criteria

| # | Criterion |
|---|---|
| A1.1 | A canned "tell me about <topic Gemma knows poorly>" prompt produces an explicit "I'd like to research this" turn instead of a confident hallucination. |
| A1.2 | The research turn produces a `data/domains/<id>/skill_proposals/<name>/SKILL.md` with frontmatter (`name`, `description`, `priority: 3`, `triggers: []`, `domain_id`) and a body distilled from at least 2 source URLs cited in `references/sources.md`. |
| A1.3 | The proposed body is ≤ 50 lines and uses the imperative voice ("Do X. Avoid Y."), matching the existing skill style — not a 500-line essay. |
| A1.4 | A `POST /api/domains/<id>/skill_proposals/<name>/promote` call moves the folder to `skills/<name>/` and rescans the registry. |
| A1.5 | After promotion, asking the same kind of question again shows Gemma calling `get_skill("<name>")` before answering. |

---

## Use Case 2 — Repeatable computation (script + skill)

### Problem

The user repeatedly performs the same kind of analysis on data files in their project (e.g., "compute summary stats for any new CSV in `data/projects/foo/raw/`"). Gemma either re-derives the code each time (wasteful, inconsistent output) or lectures about pandas methods.

### Requirements

| # | Requirement |
|---|---|
| R2.1 | Gemma can detect "I have written essentially this Python before in this conversation / this project" — pattern repetition. |
| R2.2 | Gemma can write a parameterized helper script to `data/projects/<id>/scripts/<name>.py`. |
| R2.3 | Gemma can execute that script via `exec_in_sandbox` (NEW MCP tool — runs inside `noted-test` container) and read structured output. |
| R2.4 | The accompanying SKILL.md says "to compute X, run `scripts/<name>.py` with these args; here's how to interpret the output." |
| R2.5 | Sandboxed execution is timeout-capped, output-truncated, path-confined to `data/`, and isolated from the noted backend process. |
| R2.6 | The user can inspect the script + skill before promotion. |

### Acceptance criteria

| # | Criterion |
|---|---|
| A2.1 | After 2-3 manual computations of the same kind, Gemma offers: "I notice we keep doing X. I can write a helper script for it — want me to draft one?" |
| A2.2 | The drafted helper accepts a path argument, returns JSON to stdout, and runs without noted backend modification. |
| A2.3 | `exec_in_sandbox("scripts/<name>.py", ["data/raw/foo.csv"])` returns `{stdout, stderr, exit_code}` within 60 s for a 10 MB CSV. |
| A2.4 | A 30-min script gets killed at the configured timeout (default 600 s) with `exit_code: -1` and a clear timeout marker; noted backend stays responsive. |
| A2.5 | A script attempting to write outside `data/` (e.g., `/etc/passwd`, `/app/backend/main.py`) fails — noted-test's bind mount makes those paths invisible. |
| A2.6 | After promotion, asking "do that same analysis on the new CSV" shows Gemma loading the skill, reading the script, calling `exec_in_sandbox`, and integrating stdout into the answer. |

---

## Use Case 3 — Web-driven workflow (Playwright skill)

### Problem

User wants to extract data from a JS-rendered site, a single-page app, or a service that requires login. Static `fetch_url` returns near-empty HTML because the content is React-rendered. The user can't easily script this themselves and doesn't want to context-paste 30 pages.

### Requirements

| # | Requirement |
|---|---|
| R3.1 | Gemma can detect "the URL the user gave me returns near-empty HTML through `fetch_url` — needs JS rendering." |
| R3.2 | Gemma can write a Playwright script to `data/projects/<id>/scripts/<name>.py` that drives Chromium (already installed in `noted-test`). |
| R3.3 | Same `exec_in_sandbox` tool runs Playwright scripts — no separate browser-automation tool. |
| R3.4 | Credential handling is explicit: the skill's body tells the user to set env vars before promotion; the script reads from env, not hardcodes. |
| R3.5 | The script can produce structured artifacts (JSON, CSV, screenshots) under `data/projects/<id>/artifacts/`. |

### Acceptance criteria

| # | Criterion |
|---|---|
| A3.1 | Given a URL whose `fetch_url` content is < 1 kB while the visible page is rich, Gemma surfaces "this page is JS-rendered. I can write a Playwright script in the noted-test sandbox — want me to?" |
| A3.2 | The drafted Playwright script imports `playwright.sync_api` and runs to completion in noted-test (Chromium present per the existing test setup). |
| A3.3 | `exec_in_sandbox` invocation returns structured stdout (JSON or CSV) within the configured timeout. |
| A3.4 | Any login flow uses `os.environ["SITE_USERNAME"]` / `os.environ["SITE_PASSWORD"]`; the SKILL.md `references/setup.md` documents which env vars to set. No credential ever appears in the script body or skill body. |
| A3.5 | A failed selector (site changed) returns a clear `stderr` with the failed selector name and the page URL — not a Python traceback dump. |

---

## Common architecture

```
                ┌───────────────────────────────────────────────┐
                │  noted backend (FastAPI, MCP server @ /mcp/)  │
                │                                               │
                │  Existing tools (25):                         │
                │    fetch_url, get_file_contents, list_files,  │
                │    search_files, get_skill, run_agent, ...    │
                │                                               │
                │  NEW tool:                                    │
                │    exec_in_sandbox(script_path, args, cwd?)   │
                │       └──┬──────────────────────────────────  │
                │          │  docker exec / docker start        │
                └──────────┼────────────────────────────────────┘
                           │
                  ┌────────▼────────────────────┐
                  │  noted-test container       │
                  │  (Python 3.12 + Playwright  │
                  │   + Chromium + pandas/etc.) │
                  │                             │
                  │  Bind mounts:               │
                  │    /app/data <- ../data     │
                  │    /app/data/projects <-    │
                  │      ../data/projects       │
                  │                             │
                  │  Network: noted-network     │
                  │   (can reach noted, rag,    │
                  │    graph, plus the public   │
                  │    internet for Playwright) │
                  └─────────────────────────────┘

   ┌──────────────────────────┐   ┌──────────────────────────┐
   │  data/domains/<id>/      │   │  data/domains/<id>/      │
   │   skill_proposals/       │   │   skills/                │
   │   <name>/                │   │   <name>/                │
   │     SKILL.md (frontmatter│   │     SKILL.md             │
   │     priority: 3,         │──►│     references/          │
   │     triggers: [],        │   │     scripts/             │
   │     domain_id: <id>)     │ promote                      │
   │     references/          │   │  (registered in          │
   │     scripts/             │   │   SkillRegistry on       │
   │                          │   │   next rescan)           │
   └──────────────────────────┘   └──────────────────────────┘
```

| Surface | Status | Notes |
|---|---|---|
| `exec_in_sandbox` MCP tool | NEW | ~80 lines in `backend/app/mcp/tools.py` + `backend/app/managers/llm_tools.py` |
| `noted-test` container | EXISTS (currently `Exited`) | Per memory `reference_playwright_for_browser_testing.md`. Lazy-start on first exec call. |
| `skill_proposals/` folder convention | NEW | Just a folder under each domain — no schema work needed; SKILL.md format identical to `skills/` |
| Promote endpoint | NEW | `POST /api/domains/<id>/skill_proposals/<name>/promote` — moves folder, calls `SkillRegistry.rescan()` |
| Registry rescan API | EXISTS partial | Singleton requires module-level reset; restart-on-promote is acceptable for v1 |
| File write to `data/` | EXISTS | Existing file-write surface (used by `/api/files/...`) |
| Web research | EXISTS | `fetch_url` |
| Skill discovery | EXISTS | `get_skill` tool already in registry |

---

## Implementation details

### `exec_in_sandbox` tool (covers A2.3-A2.5, A3.2-A3.3)

```python
# backend/app/mcp/tools.py — registration in _WRITE_TOOLS
types.Tool(
    name="exec_in_sandbox",
    description=(
        "Run a Python (or shell) script in the noted-test container. "
        "Path must be inside data/. Returns stdout, stderr, exit_code. "
        "Timeout-capped, output-truncated, isolated from the noted backend. "
        "Use for repeatable computation, browser automation (Playwright), "
        "or any helper script written into data/projects/<id>/scripts/."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "description": "Path under data/ (e.g. data/projects/foo/scripts/bar.py)"},
            "args": {"type": "array", "items": {"type": "string"}, "description": "Positional args for the script"},
            "cwd": {"type": "string", "description": "Optional working directory under data/ (defaults to script's parent)"},
            "timeout_s": {"type": "integer", "description": "Default 600, max 1800"},
        },
        "required": ["script_path"],
    },
)
```

Implementation guards:
- `script_path` resolved + verified to start with `/app/data/` (or its host equivalent inside noted-test).
- `noted-test` started with `docker start noted-test` if `Exited`. Healthcheck: `docker exec noted-test python3 -c "import sys"` returns within 5 s.
- Execution: `docker exec --workdir <cwd> noted-test python3 <script_path> <args...>` (or `bash` for `.sh` scripts) with `subprocess.run(..., timeout=timeout_s, capture_output=True)`.
- stdout/stderr each truncated to 32 kB; truncation flagged in the return.
- Write-tier classification (requires user approval per noted's existing approval middleware).

### `skill_proposals/` convention (covers A1.4, A2.6, A3.x)

- Identical layout to `skills/<name>/` (SKILL.md + optional `scripts/` + `references/`).
- Frontmatter MUST set `priority: 3` and `triggers: []` for proposals — agent doesn't draft always-on skills.
- The agent's drafting loop produces these via existing file-write tools; no new MCP tool needed for the proposal stage itself.

### Promote endpoint (covers A1.4, A1.5)

```python
# backend/app/routers/skills.py (NEW small router)
@router.post("/api/domains/{domain_id}/skill_proposals/{name}/promote")
async def promote(domain_id: str, name: str):
    src = Path(DOMAINS_DIR) / domain_id / "skill_proposals" / name
    dst = Path(DOMAINS_DIR) / domain_id / "skills" / name
    if not src.is_dir(): raise HTTPException(404)
    if dst.exists():     raise HTTPException(409, "skill name already exists")
    shutil.move(str(src), str(dst))
    SkillRegistry.reset_singleton()  # forces rescan on next get_registry()
    return {"status": "ok", "promoted": name}
```

UI: a small "Skill Proposals" panel listing proposals with diff-style preview + Promote / Discard buttons. Lazy add — v1 can be a CLI / curl call.

### Detection prompts (covers A1.1, A2.1, A3.1)

These are skill content, not new code. Add small priority-1 skill `propose-skill` in `general` domain:

```markdown
---
name: propose-skill
description: When you encounter a capability gap that would benefit a future conversation - low-confidence answer, repeated computation, JS-rendered page that fetch_url cannot read - offer to draft a skill proposal in skill_proposals/.
triggers: [always]
priority: 1
max_tokens: 400
---
You may detect three kinds of capability gaps:

1. KNOWLEDGE GAP - you are about to answer with hedging language
   ("might", "I think", "could potentially") on a factual question.
   Offer: "Want me to research this and draft a skill we can keep?"

2. REPETITION - you have written essentially the same Python or
   produced the same kind of analysis 2-3 times in this conversation
   or for this project. Offer: "Want me to write this as a script
   plus skill so we don't redo it next time?"

3. JS-RENDERED PAGE - fetch_url returns near-empty content for a
   URL whose visible page is rich. Offer: "This page needs a real
   browser. Want me to draft a Playwright script in the noted-test
   sandbox?"

When the user accepts, write the proposal under
data/domains/<active_domain>/skill_proposals/<name>/. Do NOT promote
it yourself - that is the user's decision.
```

### Lifecycle of `noted-test`

| Event | Action |
|---|---|
| `exec_in_sandbox` called, container `Exited` | `docker start noted-test`; wait for health (~2-5 s) |
| `exec_in_sandbox` called, container `Up` | Use directly |
| Idle for > 30 min after last exec | (Optional v2) auto-stop to free resources |

For v1, simplest: leave `noted-test` running once first started; `restart: unless-stopped` in compose.

### Trust + safety boundaries (covers A2.4, A2.5, A3.4)

| Boundary | Mechanism |
|---|---|
| Path traversal | `script_path` resolved + must be inside `/app/data/` |
| Resource exhaustion | `timeout_s` (default 600, max 1800); stdout truncated to 32 kB |
| Host escape | noted-test cannot see `/app/backend/`, `/app/frontend/`, host root — only `/app/data/` is bind-mounted |
| Credential leak | Skill body MAY NOT contain credentials; scripts read from env; promotion review checks for hardcoded secrets |
| Agent misuse (auto-promotion) | Agent NEVER calls `/promote` itself; only the user can promote |
| Skill flood | Proposals in `skill_proposals/` do NOT auto-load (they're not in `skills/`); only promoted skills enter the registry |

### Phased rollout

| Phase | Deliverable | Effort |
|---|---|---|
| P1 | `exec_in_sandbox` tool + noted-test lifecycle wiring | ~1 day |
| P2 | `skill_proposals/` folder + promote endpoint + `propose-skill` general skill | ~half day |
| P3 | Skill Proposals UI panel (list + preview + Promote/Discard) | ~1 day |
| P4 | (optional) noted-test idle-shutdown + restart hardening | ~half day |

P1 + P2 already delivers the entire loop; P3 is convenience.

---

## Open questions

| # | Question | Suggested default |
|---|---|---|
| Q1 | Should `exec_in_sandbox` block on the user's approval middleware (write-tier) every call? | Yes for v1 — agent-written scripts should not auto-execute. Per-script "trust this script" toggle in v2. |
| Q2 | When `noted-test` crashes mid-script, do we surface that to the user or silently restart? | Surface explicitly; don't paper over. |
| Q3 | Where do scripts in `skill_proposals/<name>/scripts/` live after promotion — copied or symlinked? | Move with the folder. Each promoted skill owns its own scripts in `skills/<name>/scripts/`. |
| Q4 | Should `propose-skill` be priority 1 (always-on) or priority 3 (loaded only when context tags suggest a gap)? | Priority 1 for v1 — gap detection is universally applicable. Reconsider if context bloat becomes an issue. |
| Q5 | Does the promote endpoint require the noted backend to restart, or can `SkillRegistry.reset_singleton()` rescan without one? | Aim for in-process rescan; restart only if singleton state contains references that survive `reset()`. |
