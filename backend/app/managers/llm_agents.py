"""LLM Agents - subagent execution for isolated context exploration.

Agents are defined in .noted/agents/{name}/AGENT.md with YAML frontmatter.
A subagent runs in a fresh context (no conversation history) with a specific
task. It has access to a restricted set of read-only tools and returns a
compact summary to the main assistant.

Agent AGENT.md format:
    ---
    name: notebook-explorer
    description: What this agent does
    model: claude-haiku-4-5-20251001   # optional, defaults to haiku
    tools: [get_notebook_cells, get_file_contents, list_files, search_files]
    max_tokens: 1024
    ---
    System prompt for this agent...
"""

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

AGENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.noted', 'agents')
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_AGENT_ROUNDS = 4


class Agent:
    """A subagent definition loaded from AGENT.md."""
    __slots__ = ('name', 'description', 'model', 'tools', 'max_tokens', 'system_prompt')

    def __init__(self, name, description, model, tools, max_tokens, system_prompt):
        self.name = name
        self.description = description
        self.model = model or DEFAULT_MODEL
        self.tools = set(tools)
        self.max_tokens = int(max_tokens)
        self.system_prompt = system_prompt


class AgentRegistry:
    """Registry of available subagents loaded from data/agents/."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if not os.path.isdir(AGENTS_DIR):
            logger.warning("Agents directory not found: %s", AGENTS_DIR)
            return
        count = 0
        for entry in sorted(os.scandir(AGENTS_DIR), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            agent_file = os.path.join(entry.path, 'AGENT.md')
            if not os.path.isfile(agent_file):
                continue
            try:
                agent = _parse_agent(agent_file)
                self._agents[agent.name] = agent
                count += 1
            except Exception as e:
                logger.warning("Failed to load agent %s: %s", agent_file, e)
        logger.info("Loaded %d agent(s) from %s", count, AGENTS_DIR)

    def get(self, name: str) -> Optional[Agent]:
        self._load()
        return self._agents.get(name)

    def list_agents(self) -> list[Agent]:
        self._load()
        return list(self._agents.values())


_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def _parse_agent(path: str) -> Agent:
    """Parse an AGENT.md file into an Agent instance."""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
    if not match:
        raise ValueError(f"Missing YAML frontmatter in {path}")
    try:
        import yaml
        meta = yaml.safe_load(match.group(1))
    except Exception as e:
        raise ValueError(f"Invalid YAML frontmatter in {path}: {e}")
    system_prompt = match.group(2).strip()
    return Agent(
        name=meta['name'],
        description=meta.get('description', ''),
        model=meta.get('model') or DEFAULT_MODEL,
        tools=meta.get('tools', []),
        max_tokens=meta.get('max_tokens', 1024),
        system_prompt=system_prompt,
    )


async def run_subagent(task: str, agent_name: str, managers: dict,
                        ctx: dict | None = None) -> str:
    """Execute a subagent with a fresh context and return its answer.

    The subagent has no conversation history - only the task and its system
    prompt. It can call its allowed tools up to MAX_AGENT_ROUNDS times.
    Always uses the Anthropic API (requires ANTHROPIC_API_KEY).

    Args:
        task: The specific task for the subagent to perform.
        agent_name: Name of the agent definition to use.
        managers: Manager dict (same as main tool loop; "llm" key is ignored).
        ctx: Workspace context from the parent turn. Forwarded into every
            tool call the subagent makes so project_id / notebook_path /
            file_path resolve the same way they would for the parent. The
            subagent also receives a short workspace-context preamble so it
            knows which project it's operating on without having to ask the
            user back.

    Returns:
        A string summary from the subagent, or an error message.
    """
    from app.managers.anthropic_llm_manager import AnthropicLLMManager, ANTHROPIC_API_KEY
    from app.managers.llm_tools import get_tool_descriptions, parse_tool_call, execute_tool

    if not ANTHROPIC_API_KEY:
        return "Error: Subagents require the Anthropic API (ANTHROPIC_API_KEY not set)"

    registry = get_registry()
    agent = registry.get(agent_name)
    if not agent:
        available = [a.name for a in registry.list_agents()]
        return f"Error: Agent '{agent_name}' not found. Available: {available or ['none']}"

    # Subagents always use a direct AnthropicLLMManager (bypasses router/model state)
    anthropic = AnthropicLLMManager(ANTHROPIC_API_KEY)

    # System prompt = tool call format + agent-specific instructions
    system = f"{get_tool_descriptions()}\n\n{agent.system_prompt}"

    # Surface the parent's workspace context to the subagent so it doesn't
    # ask the user for identifiers the parent already knows.
    sub_ctx = dict(ctx or {})
    workspace_lines = []
    if sub_ctx.get("project_id"):
        workspace_lines.append(f"Workspace project_id: {sub_ctx['project_id']}")
    if sub_ctx.get("notebook_path"):
        workspace_lines.append(f"Active notebook_path: {sub_ctx['notebook_path']}")
    if sub_ctx.get("file_path"):
        workspace_lines.append(f"Active file_path: {sub_ctx['file_path']}")
    workspace_preamble = ""
    if workspace_lines:
        workspace_preamble = (
            "WORKSPACE CONTEXT (inherited from parent; reuse these for any "
            "tool that takes project_id / notebook_path / file_path - do "
            "NOT ask the parent for them again):\n  - "
            + "\n  - ".join(workspace_lines)
            + "\n\n"
        )

    # Fresh context - just the task plus the inherited workspace preamble
    messages = [{"role": "user", "content": workspace_preamble + task + " /no_think"}]

    response_text = ''
    for round_num in range(MAX_AGENT_ROUNDS):
        response_text = ''
        async for chunk in anthropic.chat_stream(
            messages,
            temperature=0.3,
            max_tokens=agent.max_tokens,
            model=agent.model,
            system=system,
        ):
            choices = chunk.get("choices", [])
            if choices:
                content = choices[0].get("delta", {}).get("content")
                if content:
                    response_text += content

        tool_call = parse_tool_call(response_text)
        if not tool_call:
            break  # Final answer, no more tool calls

        tool_name = tool_call["name"]

        # Enforce allowed tools for this agent
        if tool_name not in agent.tools:
            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": f"Tool '{tool_name}' is not available. Allowed: {sorted(agent.tools)}"
            })
            continue

        try:
            tool_result = await execute_tool(tool_call, managers, sub_ctx)
        except Exception as e:
            tool_result = f"Error executing {tool_name}: {e}"

        logger.info("Subagent %s round %d: %s -> %d chars",
                    agent_name, round_num + 1, tool_name, len(tool_result))

        messages.append({"role": "assistant", "content": response_text})
        messages.append({
            "role": "user",
            "content": f"TOOL RESULT for {tool_name}:\n{tool_result}"
        })

    # Strip any residual thinking blocks
    final = re.sub(r'<think>[\s\S]*?</think>\s*', '', response_text).strip()
    return final or "Agent produced no output"
