"""Workflow execution loop.

State machine that walks a WorkflowDefinition's plan template, dispatching
each step to either a deterministic handler or (in F2+) an LLM-driven worker
preset. Validates step output against the step type's JSON schema (when
declared); on validation failure, bounded retry up to N times with the
validator's complaint fed back as additional context. Beyond N: suspend with
system_request for HITL.

F1.2 scope: deterministic step path is fully implemented. LLM-driven step
dispatch is a stub (raises) until F2 wires the agent_server preset call.
That keeps the loop's state machine, suspend / resume / audit / telemetry
plumbing testable via the synthetic 3-step probe (F1.9), all of whose steps
will be deterministic.

Workflow lifecycle:

  pending -> running -> ( completed | failed | suspended | aborted )

The loop returns the final WorkspaceState. For long workflows, the caller
should spawn this as a background task; the inspector UI surfaces live
progress via the Socket.io events.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from . import audit, llm_dispatcher, telemetry
from .registry import get_workflow_registry
from .suspension import (
    get_suspension_manager,
    remove_snapshot,
    write_snapshot,
)
from .types import StepType, WorkflowDefinition
from .workspace import StepRecord, WorkspaceState, get_workspace_store

logger = logging.getLogger(__name__)


def _new_workflow_id() -> str:
    return f"wf_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def _validate_output(output: dict[str, Any], schema: dict[str, Any] | None) -> str | None:
    """Return None on pass, validator error message on fail.

    Lazy-imports jsonschema so the workflow module doesn't pull it in at
    startup if no validation is configured.
    """
    if schema is None:
        return None
    try:
        from jsonschema import ValidationError, validate
    except ImportError:
        logger.warning("jsonschema not installed; skipping output validation")
        return None
    try:
        validate(instance=output, schema=schema)
    except ValidationError as e:
        return f"{e.message} (path: {list(e.path)})"
    return None


async def _dispatch_step(
    step: StepType,
    state: WorkspaceState,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Run one step. Returns the step's output dict.

    Deterministic step: calls step.handler.
    LLM step: not implemented in F1.2; F2 wires this to agent_server.
    """
    if step.worker == "deterministic":
        if step.handler is None:
            raise RuntimeError(
                f"Step {step.name!r} declared deterministic but has no handler"
            )
        return await step.handler(state, inputs)
    # LLM-driven step: name of an agent_server preset (planner, tool_author,
    # api_tester, skill_author, ...). Dispatcher returns the parsed JSON
    # from the preset's structured output. The loop validates against
    # step.output_schema next; on validation failure the bounded-retry
    # path feeds the complaint back via inputs["validator_complaint"].
    return await llm_dispatcher.dispatch(step.worker, inputs, state=state)


async def _run_step(
    state: WorkspaceState,
    step_type: StepType,
    step_index: int,
    definition: WorkflowDefinition,
) -> bool:
    """Execute a single step including validation + bounded retry.

    Returns True on success, False on retry exhaustion (caller suspends).
    Updates state.steps[step_index] in place.
    """
    record = state.steps[step_index]
    record.status = "running"
    record.started_at = time.time()
    state.current_step = step_index

    await telemetry.step_started(
        state.tenant_id, state.workflow_id, step_index, step_type.name
    )
    audit.record(
        state.tenant_id, state.workflow_id, "step_started",
        {"step_index": step_index, "step_name": step_type.name},
        actor_id=state.actor_id,
    )

    last_error: str | None = None
    # Per-step retry override (StepType.max_retries) wins over the workflow
    # default; this lets deterministic steps opt out of the retry loop
    # since retrying with the same input is pointless.
    step_max_retries = (
        step_type.max_retries
        if step_type.max_retries is not None
        else definition.max_retries_per_step
    )
    for attempt in range(step_max_retries + 1):
        record.retries = attempt
        try:
            inputs: dict[str, Any] = {"workflow_inputs": state.inputs}
            if step_index > 0:
                prior = state.steps[step_index - 1]
                inputs["previous_step"] = {
                    "name": prior.name,
                    "output": prior.output,
                }
            if attempt > 0 and last_error:
                inputs["validator_complaint"] = last_error
            # A2: when api_tester (or tool_author) is re-invoked after a
            # smoke-test failure, surface the failure tail as feedback so
            # the LLM can target the actual problem instead of producing
            # the same broken output again.
            if (
                state.last_smoke_error
                and step_type.name in ("api_tester", "tool_author")
            ):
                inputs["previous_smoke_failure"] = state.last_smoke_error
            output = await _dispatch_step(step_type, state, inputs)
        except NotImplementedError as e:
            # LLM dispatch not wired yet; surface clearly without consuming a retry.
            record.status = "failed"
            record.finished_at = time.time()
            record.error = str(e)
            await telemetry.step_failed(
                state.tenant_id, state.workflow_id, step_index, step_type.name,
                str(e), attempt,
            )
            audit.record(
                state.tenant_id, state.workflow_id, "step_failed",
                {"step_index": step_index, "step_name": step_type.name, "error": str(e)},
                actor_id=state.actor_id,
            )
            return False
        except Exception as e:  # noqa: BLE001
            logger.exception("step %s/%s raised", state.workflow_id, step_type.name)
            last_error = f"{type(e).__name__}: {e}"
            continue

        validator_error = _validate_output(output, step_type.output_schema)
        if validator_error is None:
            record.output = output
            record.status = "completed"
            record.finished_at = time.time()
            await telemetry.step_completed(
                state.tenant_id, state.workflow_id, step_index, step_type.name,
                {"keys": sorted(output.keys())},
            )
            audit.record(
                state.tenant_id, state.workflow_id, "step_completed",
                {
                    "step_index": step_index,
                    "step_name": step_type.name,
                    "retries": attempt,
                    "output_keys": sorted(output.keys()),
                },
                actor_id=state.actor_id,
            )
            return True

        last_error = f"validation: {validator_error}"
        logger.info(
            "step %s/%s validation failed (attempt %d): %s",
            state.workflow_id, step_type.name, attempt, validator_error,
        )

    record.status = "failed"
    record.finished_at = time.time()
    record.error = last_error or "retry_exhausted"
    await telemetry.step_failed(
        state.tenant_id, state.workflow_id, step_index, step_type.name,
        record.error, record.retries,
    )
    audit.record(
        state.tenant_id, state.workflow_id, "step_failed",
        {"step_index": step_index, "step_name": step_type.name,
         "retries": record.retries, "error": record.error},
        actor_id=state.actor_id,
    )
    return False


async def _suspend_for_hitl(state: WorkspaceState, reason: str,
                            definition: WorkflowDefinition) -> bool:
    """Snapshot + suspend the workflow. Returns True on resume, False on abort/timeout."""
    state.status = "suspended"
    state.suspend_reason = reason
    try:
        snapshot_path = str(write_snapshot(state))
    except OSError as e:
        logger.warning("snapshot write failed for %s/%s: %s",
                       state.tenant_id, state.workflow_id, e)
        snapshot_path = None

    await telemetry.workflow_suspended(
        state.tenant_id, state.workflow_id, reason, snapshot_path,
    )
    audit.record(
        state.tenant_id, state.workflow_id, "workflow_suspended",
        {"reason": reason, "snapshot_path": snapshot_path},
        actor_id=state.actor_id,
    )
    await telemetry.system_request(
        state.tenant_id, state.workflow_id,
        "approve_resume",
        f"Workflow suspended: {reason}. Resume to retry the failed step, or abort.",
    )

    suspension = get_suspension_manager()
    handle = suspension.begin(state.tenant_id, state.workflow_id)
    # Run blocking wait in a thread so we don't tie up the event loop.
    timeout_s = definition.max_wallclock_seconds
    resumed = await asyncio.to_thread(suspension.wait, handle, timeout_s)

    if resumed:
        state.status = "running"
        state.suspend_reason = None
        await telemetry.workflow_resumed(state.tenant_id, state.workflow_id)
        audit.record(state.tenant_id, state.workflow_id, "workflow_resumed",
                     {}, actor_id=state.actor_id)
        return True
    return False


async def run_workflow(
    tenant_id: str,
    workflow_type: str,
    inputs: dict[str, Any],
    actor_id: str = "default",
    workflow_id: str | None = None,
) -> WorkspaceState:
    """Run a workflow end-to-end. Returns the final WorkspaceState.

    Raises ValueError if the workflow type is not registered.
    """
    registry = get_workflow_registry()
    definition = registry.get(workflow_type)
    if definition is None:
        raise ValueError(f"unknown workflow type: {workflow_type!r}")

    workflow_id = workflow_id or _new_workflow_id()
    store = get_workspace_store()

    plan_serialized = [
        {"name": s.name, "worker": s.worker, "description": s.description}
        for s in definition.plan_template
    ]
    state = WorkspaceState(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        actor_id=actor_id,
        plan=plan_serialized,
        steps=[
            StepRecord(name=s.name, index=i)
            for i, s in enumerate(definition.plan_template)
        ],
        inputs=inputs,
    )
    store.create(state)

    await telemetry.workflow_started(
        tenant_id, workflow_id, workflow_type,
        [o.name for o in definition.outcomes], plan_serialized,
    )
    audit.record(
        tenant_id, workflow_id, "workflow_started",
        {"type": workflow_type, "outcomes": [o.name for o in definition.outcomes]},
        actor_id=actor_id,
    )

    try:
        return await _execute_plan(state, definition, start_index=0)
    except Exception as e:  # noqa: BLE001
        logger.exception("workflow %s failed unexpectedly", workflow_id)
        state.status = "failed"
        state.finished_at = time.time()
        await telemetry.workflow_failed(
            tenant_id, workflow_id, f"{type(e).__name__}: {e}",
        )
        audit.record(
            tenant_id, workflow_id, "workflow_failed",
            {"error": f"{type(e).__name__}: {e}"},
            actor_id=actor_id,
        )
        try:
            write_snapshot(state)
        except OSError:
            pass
        return state


async def resume_workflow(tenant_id: str, workflow_id: str) -> WorkspaceState:
    """Resume a previously-suspended workflow from its snapshot.

    The snapshot must already be hydrated into the workspace store
    (via suspension.hydrate_workspace_from_snapshot if missing).
    """
    store = get_workspace_store()
    state = store.get(tenant_id, workflow_id)
    if state is None:
        raise ValueError(f"workflow {tenant_id}/{workflow_id} not loaded in workspace store")
    registry = get_workflow_registry()
    definition = registry.get(state.workflow_type)
    if definition is None:
        raise ValueError(f"workflow type {state.workflow_type!r} not registered")

    # Resume from current_step (the failed step in the suspended state).
    return await _execute_plan(state, definition, start_index=state.current_step)


async def _classify_smoke_failure(
    state: WorkspaceState,
    definition: WorkflowDefinition,
    err: str,
) -> tuple[str | None, str | None]:
    """Call the smoke_failure_classifier LLM agent to decide which agent
    should be rewound when run_smoke_tests fails. Returns (target_name,
    actionable_reason) — both None if the classifier itself fails, in
    which case the caller should not rewind (suspending for HITL is
    preferable to guessing).

    Replaces the prior keyword-regex classifier. The model reads pytest
    output + tool.py + smoke.py + acceptance_criteria + (when available)
    the tool's actual output captured by the probe step, then emits
    `{target: "tool_author" | "api_tester", reason: "<actionable>"}`.
    """
    # Gather context. tool.py and smoke.py come from the last completed
    # tool_author / api_tester outputs in state. Acceptance criteria
    # come from workflow inputs. Probed output (when present) comes from
    # the most recent completed verify_tool_round_trip step.
    tool_py = ""
    smoke_py = ""
    probed_output: Any = None
    for step in state.steps:
        if step.status != "completed":
            continue
        out = step.output or {}
        if step.name == "tool_author":
            files = out.get("files") or {}
            tool_py = files.get("tool.py") or ""
        elif step.name == "api_tester":
            files = out.get("files") or {}
            smoke_py = files.get("smoke.py") or ""
        elif step.name == "verify_tool_round_trip":
            probed_output = out.get("result_parsed")
            if probed_output is None:
                probed_output = (out.get("result_full") or "")[:2000]

    criteria = (state.inputs or {}).get("acceptance_criteria") or []

    classifier_inputs: dict[str, Any] = {
        "pytest_output": err[:6000],  # cap to keep prompt bounded
        "tool_py": tool_py[:8000],
        "smoke_py": smoke_py[:4000],
        "acceptance_criteria": criteria,
    }
    if probed_output is not None:
        classifier_inputs["tool_actual_output"] = probed_output

    # Bounded retry for the same reason the validator has one: Gemma's
    # `<think>` budget occasionally consumes max_tokens with no JSON
    # emitted afterwards, so the dispatcher raises a parse error.
    # Suspending the workflow on a transient one-off LLM hiccup is too
    # punishing — give it 3 attempts before bailing, same pattern as
    # validate_smoke_contract.
    last_err: str | None = None
    for attempt in range(3):
        try:
            out = await llm_dispatcher.dispatch(
                "smoke_failure_classifier",
                classifier_inputs,
                state=state,
            )
            target = (out.get("target") or "").strip()
            reason = (out.get("reason") or "").strip()
            if target not in ("tool_author", "api_tester"):
                logger.warning(
                    "smoke_failure_classifier returned unrecognised target %r on attempt %d/3",
                    target, attempt + 1,
                )
                last_err = f"unrecognised target: {target!r}"
                continue
            if not reason:
                reason = err[:300]
            logger.info(
                "smoke_failure_classifier → %s (reason: %s)",
                target, reason[:200],
            )
            return target, reason
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            logger.warning(
                "smoke_failure_classifier dispatch attempt %d/3 failed: %s",
                attempt + 1, last_err,
            )
    logger.error(
        "smoke_failure_classifier failed all 3 attempts (%s); suspending workflow"
        " rather than guessing",
        last_err,
    )
    return None, None


async def _execute_plan(
    state: WorkspaceState,
    definition: WorkflowDefinition,
    start_index: int,
) -> WorkspaceState:
    state.status = "running"

    # A2: cap on smoke-test-driven rewinds within a single workflow run.
    # 2 means: original attempt + 2 regenerate cycles = up to 3 attempts at
    # api_tester before the workflow gives up and suspends for HITL.
    SMOKE_REWIND_CAP = 2

    index = start_index
    while index < len(definition.plan_template):
        step = definition.plan_template[index]
        ok = await _run_step(state, step, index, definition)

        if not ok:
            # A2: when a recoverable validation/test step fails AND we still
            # have rewinds left, rewind to the LLM step that produced the
            # broken artifact, re-invoked with the failure as feedback.
            # All subsequent steps re-run in the same cycle.
            #   - run_smoke_tests:        tool_author (AssertionError) | api_tester (SyntaxError etc)
            #   - validate_tool_structure: always tool_author (its files didn't parse / shape wrong)
            #   - validate_smoke_contract: always api_tester (its smoke.py asserts on invented keys)
            target_name: str | None = None
            rewind_reason: str | None = None
            if state.smoke_rewinds < SMOKE_REWIND_CAP:
                err = state.steps[index].error or ""
                if step.name == "validate_tool_structure":
                    target_name = "tool_author"
                    rewind_reason = err
                elif step.name == "verify_tool_round_trip":
                    # The probe step runs BEFORE api_tester so the tester
                    # can write assertions against the tool's real output.
                    # A genuine failure here = the tool can't respond to a
                    # sample call → tool is broken → rewind tool_author.
                    #
                    # NOTE (2026-05-14): the "secret not set" case is NOT
                    # a genuine failure and never reaches here — the
                    # handler short-circuits to a conditional pass when a
                    # declared `_meta.allowed_secrets` entry is missing
                    # from the vault. So a failure that DOES reach this
                    # branch is a real codegen defect; rewinding
                    # tool_author is the right call.
                    target_name = "tool_author"
                    rewind_reason = err
                elif step.name == "validate_smoke_contract":
                    target_name = "api_tester"
                    rewind_reason = err
                elif step.name == "run_smoke_tests":
                    # LLM-classified rewind. The `smoke_failure_classifier`
                    # agent reads the failure + tool.py + smoke.py +
                    # acceptance_criteria + (when available) the tool's
                    # actual output captured by the probe step, then
                    # emits JSON `{target, reason}` saying who's at fault.
                    # Replaces the prior keyword-regex classifier — a
                    # reasoning task gets a reasoning tool.
                    target_name, rewind_reason = await _classify_smoke_failure(
                        state, definition, err
                    )
            if target_name is not None:
                target_idx = next(
                    (i for i, s in enumerate(definition.plan_template) if s.name == target_name),
                    None,
                )
                if target_idx is not None:
                    state.smoke_rewinds += 1
                    # Prefer the classifier's specific actionable reason
                    # over the raw pytest output when available — it's
                    # the concrete change the rewound agent needs to make.
                    state.last_smoke_error = rewind_reason or err
                    # Reset the records for steps we're about to re-run so
                    # the inspector clearly shows them as in-flight again.
                    for j in range(target_idx, index + 1):
                        rec = state.steps[j]
                        rec.status = "pending"
                        rec.started_at = None
                        rec.finished_at = None
                        rec.output = {}
                        rec.error = None
                        rec.retries = 0
                    audit.record(
                        state.tenant_id, state.workflow_id, "smoke_rewind",
                        {
                            "rewind_index": state.smoke_rewinds,
                            "rewind_cap": SMOKE_REWIND_CAP,
                            "rewinding_to": target_name,
                            "reason": (state.last_smoke_error or "")[:300],
                        },
                        actor_id=state.actor_id,
                    )
                    logger.info(
                        "smoke rewind %d/%d for %s/%s: rewinding to %s",
                        state.smoke_rewinds, SMOKE_REWIND_CAP,
                        state.tenant_id, state.workflow_id, target_name,
                    )
                    index = target_idx
                    await telemetry.workspace_sync(
                        state.tenant_id, state.workflow_id, state.to_serializable(),
                    )
                    continue

            # Otherwise: suspend with HITL approval. If operator resumes,
            # retry the step.
            while not ok:
                resumed = await _suspend_for_hitl(
                    state, f"step_failed:{step.name}", definition,
                )
                if not resumed:
                    state.status = "aborted" if state.status == "suspended" else "failed"
                    state.finished_at = time.time()
                    await telemetry.workflow_failed(
                        state.tenant_id, state.workflow_id,
                        f"aborted_or_timed_out:{step.name}",
                    )
                    audit.record(
                        state.tenant_id, state.workflow_id, "workflow_failed",
                        {"reason": "aborted_or_timed_out", "at_step": step.name},
                        actor_id=state.actor_id,
                    )
                    return state
                # Retry the step after resume.
                ok = await _run_step(state, step, index, definition)

        await telemetry.workspace_sync(
            state.tenant_id, state.workflow_id, state.to_serializable(),
        )
        get_workspace_store().prune_if_needed(state)
        index += 1

    state.status = "completed"
    state.outcomes = [o.name for o in definition.outcomes]
    state.finished_at = time.time()
    await telemetry.workflow_completed(
        state.tenant_id, state.workflow_id, state.outcomes,
    )
    audit.record(
        state.tenant_id, state.workflow_id, "workflow_completed",
        {"outcomes": state.outcomes},
        actor_id=state.actor_id,
    )
    # F5: persist the final snapshot so the inspector can list / show this
    # workflow after a noted restart. The same path the suspend mechanism
    # uses; on completion it carries terminal status. Inspector reads
    # `data/tenants/<tenant_id>/workflows/<workflow_id>/state.json`.
    try:
        write_snapshot(state)
    except OSError as e:
        logger.warning("final snapshot write failed for %s/%s: %s",
                       state.tenant_id, state.workflow_id, e)
    return state
