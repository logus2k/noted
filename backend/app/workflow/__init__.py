"""Workflow framework: capability-extension workflows over a generic loop.

Public API for the rest of noted backend. Workflow types are registered with
get_workflow_registry().register(); the loop consumes the registry at run
time. See documents/self-learning/self_learning_plan.md for the full design.
"""

from .identity import DEFAULT_ACTOR_ID, DEFAULT_TENANT_ID, Identity, extract_identity
from .llm_dispatcher import AGENT_SERVER_URL, dispatch as llm_dispatch
from .loop import resume_workflow, run_workflow
from .registry import WorkflowRegistry, get_workflow_registry
from .suspension import (
    SuspensionManager,
    get_suspension_manager,
    hydrate_workspace_from_snapshot,
    read_snapshot,
    write_snapshot,
)
from .telemetry import set_sio
from .types import StepType, WorkflowDefinition, WorkflowOutcome
from .workspace import (
    StepRecord,
    WorkspaceState,
    WorkspaceStore,
    get_workspace_store,
)

__all__ = [
    # types
    "StepType",
    "WorkflowDefinition",
    "WorkflowOutcome",
    "StepRecord",
    "WorkspaceState",
    # registry
    "WorkflowRegistry",
    "get_workflow_registry",
    # workspace
    "WorkspaceStore",
    "get_workspace_store",
    # loop
    "run_workflow",
    "resume_workflow",
    # suspension
    "SuspensionManager",
    "get_suspension_manager",
    "write_snapshot",
    "read_snapshot",
    "hydrate_workspace_from_snapshot",
    # telemetry wiring
    "set_sio",
    # identity
    "Identity",
    "extract_identity",
    "DEFAULT_TENANT_ID",
    "DEFAULT_ACTOR_ID",
    # llm dispatcher
    "AGENT_SERVER_URL",
    "llm_dispatch",
]
