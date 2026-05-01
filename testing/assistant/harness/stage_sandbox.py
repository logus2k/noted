"""One-time sandbox pre-stage for the Assistant test harness.

Creates the MLflow artifacts the test scenarios reference so the harness can
run without touching real user projects (e.g. jena_weather).

Artifacts staged (idempotent; re-running is safe):

  - Experiment `noted-testing`
  - Registered model `Sandbox Forecaster` with:
      - v1 @champion (healthy tensor model, shape (1,120,16) -> (1,24),
        target_mean / target_std logged as params)
      - v2 @staging (second healthy version)
      - v3 (no alias, a third healthy version)
      - v4 (poisoned: imports a non-existent package in load_context so
        pyfunc.load_model fails with ModuleNotFoundError at serving load time)
  - An active-but-unregistered run with a healthy model artifact at
    `runs:/<run_id>/model` (source for "deploy this run's model" scenarios)

Invocation:

    python -m testing.assistant.harness.stage_sandbox [--dry-run] [--force-recreate]

Environment:

    MLFLOW_TRACKING_URI     default http://localhost:5000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import mlflow
from mlflow.exceptions import MlflowException, RestException
from mlflow.types.schema import Schema, TensorSpec
from mlflow.models.signature import ModelSignature
import numpy as np


EXPERIMENT_NAME = "noted-testing"
MODEL_NAME = "Sandbox Forecaster"
INPUT_SHAPE = (-1, 120, 16)
OUTPUT_SHAPE = (-1, 24)
TARGET_MEAN = 9.099239278235567
TARGET_STD = 8.644593993225591


# ── Sandbox model implementations ────────────────────────────────────

def _unwrap_named_tensor(model_input):
    """PyFuncModel signature enforcement wraps TensorSpec(name='input') as
    {'input': ndarray}. Real-world pyfunc models need to handle both raw
    ndarray and named-dict input."""
    if isinstance(model_input, dict):
        if 'input' in model_input:
            return model_input['input']
        return next(iter(model_input.values()))
    return model_input


class _HealthyPredictor(mlflow.pyfunc.PythonModel):
    """Returns zeros of the expected output shape. Matches jena-style
    (batch, lookback=120, features=16) -> (batch, horizon=24)."""

    def predict(self, context, model_input):
        arr = np.asarray(_unwrap_named_tensor(model_input), dtype=np.float32)
        batch = arr.shape[0] if arr.ndim >= 1 else 1
        return np.zeros((batch, 24), dtype=np.float32)


class _PoisonedPredictor(mlflow.pyfunc.PythonModel):
    """Registers fine; fails at load time. The serving container's
    pyfunc.load_model invokes load_context after instantiation, which
    imports a non-existent module and raises ModuleNotFoundError."""

    def load_context(self, context):
        import _sandbox_poisoned_module_does_not_exist_abc123  # noqa: F401

    def predict(self, context, model_input):  # unreachable
        arr = np.asarray(_unwrap_named_tensor(model_input), dtype=np.float32)
        batch = arr.shape[0] if arr.ndim >= 1 else 1
        return np.zeros((batch, 24), dtype=np.float32)


# ── Ops ──────────────────────────────────────────────────────────────

@dataclass
class StageReport:
    created: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"  Created:  {len(self.created)}",
            f"  Verified: {len(self.verified)}",
            f"  Skipped:  {len(self.skipped)}",
            f"  Errors:   {len(self.errors)}",
        ]
        for label, items in [
            ("CREATED", self.created),
            ("VERIFIED", self.verified),
            ("SKIPPED", self.skipped),
            ("ERRORS", self.errors),
        ]:
            if items:
                lines.append(f"\n{label}:")
                for it in items:
                    lines.append(f"  - {it}")
        return "\n".join(lines)


def _signature() -> ModelSignature:
    return ModelSignature(
        inputs=Schema([TensorSpec(np.dtype(np.float32), INPUT_SHAPE, name="input")]),
        outputs=Schema([TensorSpec(np.dtype(np.float32), OUTPUT_SHAPE, name="prediction")]),
    )


def _ensure_experiment(client: mlflow.MlflowClient, report: StageReport, dry_run: bool) -> str:
    exp = client.get_experiment_by_name(EXPERIMENT_NAME)
    if exp is not None:
        report.verified.append(f"experiment '{EXPERIMENT_NAME}' (id={exp.experiment_id})")
        return exp.experiment_id
    if dry_run:
        report.skipped.append(f"would create experiment '{EXPERIMENT_NAME}' (dry-run)")
        return ""
    exp_id = client.create_experiment(EXPERIMENT_NAME)
    report.created.append(f"experiment '{EXPERIMENT_NAME}' (id={exp_id})")
    return exp_id


def _ensure_registered_model(client: mlflow.MlflowClient, report: StageReport, dry_run: bool) -> None:
    try:
        client.get_registered_model(MODEL_NAME)
        report.verified.append(f"registered model '{MODEL_NAME}'")
        return
    except (MlflowException, RestException) as e:
        if "RESOURCE_DOES_NOT_EXIST" not in str(e) and "not found" not in str(e).lower():
            raise
    if dry_run:
        report.skipped.append(f"would create registered model '{MODEL_NAME}' (dry-run)")
        return
    client.create_registered_model(MODEL_NAME)
    report.created.append(f"registered model '{MODEL_NAME}'")


def _version_exists(client: mlflow.MlflowClient, version: str) -> bool:
    try:
        client.get_model_version(MODEL_NAME, version)
        return True
    except (MlflowException, RestException) as e:
        if "RESOURCE_DOES_NOT_EXIST" in str(e) or "not found" in str(e).lower():
            return False
        raise


def _log_and_register_version(
    experiment_id: str,
    model: mlflow.pyfunc.PythonModel,
    expected_version: str,
    alias: Optional[str],
    tags: dict,
    pip_requirements: Optional[list[str]],
    report: StageReport,
    dry_run: bool,
) -> None:
    label = f"{MODEL_NAME} v{expected_version}" + (f" @{alias}" if alias else "")

    client = mlflow.MlflowClient()
    if _version_exists(client, expected_version):
        aliases = client.get_model_version(MODEL_NAME, expected_version).aliases
        report.verified.append(f"{label} (existing, aliases={list(aliases)})")
        # Re-assert alias if missing
        if alias and alias not in aliases:
            if dry_run:
                report.skipped.append(f"would set alias @{alias} on v{expected_version} (dry-run)")
            else:
                client.set_registered_model_alias(MODEL_NAME, alias, expected_version)
                report.created.append(f"alias @{alias} -> v{expected_version}")
        return

    if dry_run:
        report.skipped.append(f"would create {label} (dry-run)")
        return

    # Per-version synthetic metrics so "which version is better?" scenarios
    # have something to compare. The differences are deliberate and
    # version-ordered so a comparison tool has a clear answer.
    version_metrics = {
        "1": {"val_mae": 2.15, "val_rmse": 3.02, "val_r2": 0.894},  # champion: best
        "2": {"val_mae": 2.41, "val_rmse": 3.28, "val_r2": 0.871},  # staging: second
        "3": {"val_mae": 2.67, "val_rmse": 3.55, "val_r2": 0.849},  # trailing
        "4": {"val_mae": 3.12, "val_rmse": 4.01, "val_r2": 0.803},  # poisoned: worst (never loads anyway)
    }
    metrics = version_metrics.get(expected_version, {})

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.log_param("target_mean", TARGET_MEAN)
        mlflow.log_param("target_std", TARGET_STD)
        for k, v in metrics.items():
            mlflow.log_metric(k, v)
        for k, v in tags.items():
            mlflow.set_tag(k, v)

        mlflow.pyfunc.log_model(
            python_model=model,
            artifact_path="model",
            signature=_signature(),
            pip_requirements=pip_requirements,
        )

        model_uri = f"runs:/{run.info.run_id}/model"
        mv = mlflow.register_model(model_uri=model_uri, name=MODEL_NAME)

    if mv.version != expected_version:
        # The registry assigned a different version number than we expected
        # (someone else registered in parallel). Log but don't fail; scenarios
        # reference versions by the numeric value that actually exists.
        report.errors.append(
            f"expected v{expected_version} but registry assigned v{mv.version} for {label}"
        )

    if alias:
        client.set_registered_model_alias(MODEL_NAME, alias, mv.version)
        report.created.append(f"{label} (run={run.info.run_id[:8]}, alias @{alias} set)")
    else:
        report.created.append(f"{label} (run={run.info.run_id[:8]})")


def _ensure_unregistered_run(experiment_id: str, report: StageReport, dry_run: bool) -> None:
    """Create an active-but-unregistered run with a pyfunc model logged as
    artifact but NOT registered in the Model Registry. Used by scenarios
    that exercise the 'register_model from a run, then deploy' chain."""
    tag_key = "noted.sandbox.role"
    tag_value = "unregistered-model-source"

    # In dry-run, the experiment may not exist yet; skip the search entirely
    # to avoid a real API call with a potentially-empty experiment_id.
    if dry_run:
        report.skipped.append("would create unregistered-source run (dry-run)")
        return

    if not experiment_id:
        report.errors.append(
            "cannot stage unregistered-source run: experiment_id is empty (experiment creation must have failed)"
        )
        return

    # Idempotency: check if a run with this tag already exists
    client = mlflow.MlflowClient()
    existing = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f"tags.`{tag_key}` = '{tag_value}'",
        max_results=1,
    )
    if existing:
        run = existing[0]
        report.verified.append(
            f"unregistered-source run (id={run.info.run_id[:8]}, tag={tag_key}={tag_value})"
        )
        return

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.set_tag(tag_key, tag_value)
        mlflow.log_param("target_mean", TARGET_MEAN)
        mlflow.log_param("target_std", TARGET_STD)
        mlflow.pyfunc.log_model(
            python_model=_HealthyPredictor(),
            artifact_path="model",
            signature=_signature(),
        )
    report.created.append(
        f"unregistered-source run (id={run.info.run_id[:8]}, artifact at runs:/{run.info.run_id}/model)"
    )


def _wipe_sandbox(client: mlflow.MlflowClient, report: StageReport) -> None:
    """Destructive: delete all sandbox artifacts so they can be recreated.
    Only invoked with --force-recreate.

    Also deletes all runs in the experiment so we don't accumulate orphaned
    runs across successive --force-recreate invocations (keeps the MLflow
    experiment context block compact - the Assistant's reasoning degrades
    when too many runs are listed)."""
    try:
        client.delete_registered_model(MODEL_NAME)
        report.created.append(f"deleted registered model '{MODEL_NAME}' (force-recreate)")
    except (MlflowException, RestException) as e:
        if "RESOURCE_DOES_NOT_EXIST" not in str(e) and "not found" not in str(e).lower():
            report.errors.append(f"failed to delete '{MODEL_NAME}': {e}")

    # Delete all runs in the experiment to prevent orphan accumulation
    try:
        exp = client.get_experiment_by_name(EXPERIMENT_NAME)
        if exp is None:
            return
        runs = client.search_runs(experiment_ids=[exp.experiment_id], max_results=200)
        deleted = 0
        for r in runs:
            try:
                client.delete_run(r.info.run_id)
                deleted += 1
            except Exception as e:
                report.errors.append(f"failed to delete run {r.info.run_id[:8]}: {e}")
        if deleted:
            report.created.append(f"deleted {deleted} old runs from experiment '{EXPERIMENT_NAME}'")
    except Exception as e:
        report.errors.append(f"failed to clean experiment runs: {e}")


# ── Entry point ──────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="stage_sandbox",
        description="Idempotent MLflow pre-stage for the noted Assistant test harness.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, do nothing.")
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="DESTRUCTIVE: delete sandbox registered model and recreate from scratch.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger("stage_sandbox")

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    log.info("MLflow tracking URI: %s", tracking_uri)

    report = StageReport()
    client = mlflow.MlflowClient(tracking_uri=tracking_uri)

    # Sanity check: MLflow reachable
    try:
        client.search_experiments(max_results=1)
    except Exception as e:
        print(f"ERROR: cannot reach MLflow at {tracking_uri}: {e}", file=sys.stderr)
        return 2

    if args.force_recreate:
        if args.dry_run:
            report.skipped.append(f"would WIPE sandbox registered model (dry-run + force-recreate)")
        else:
            _wipe_sandbox(client, report)

    try:
        experiment_id = _ensure_experiment(client, report, args.dry_run)
        _ensure_registered_model(client, report, args.dry_run)

        # v1 @champion (healthy)
        _log_and_register_version(
            experiment_id=experiment_id,
            model=_HealthyPredictor(),
            expected_version="1",
            alias="champion",
            tags={"noted.sandbox.role": "healthy"},
            pip_requirements=None,
            report=report,
            dry_run=args.dry_run,
        )
        # v2 @staging (healthy)
        _log_and_register_version(
            experiment_id=experiment_id,
            model=_HealthyPredictor(),
            expected_version="2",
            alias="staging",
            tags={"noted.sandbox.role": "healthy"},
            pip_requirements=None,
            report=report,
            dry_run=args.dry_run,
        )
        # v3 (no alias, healthy)
        _log_and_register_version(
            experiment_id=experiment_id,
            model=_HealthyPredictor(),
            expected_version="3",
            alias=None,
            tags={"noted.sandbox.role": "healthy"},
            pip_requirements=None,
            report=report,
            dry_run=args.dry_run,
        )
        # v4 poisoned (registration succeeds, serving load fails)
        _log_and_register_version(
            experiment_id=experiment_id,
            model=_PoisonedPredictor(),
            expected_version="4",
            alias=None,
            tags={"noted.sandbox.role": "poisoned"},
            pip_requirements=None,
            report=report,
            dry_run=args.dry_run,
        )
        # Unregistered-source run for register-then-deploy scenarios
        _ensure_unregistered_run(experiment_id, report, args.dry_run)

    except Exception as e:
        log.exception("stage_sandbox aborted")
        report.errors.append(f"unhandled: {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print(f"Sandbox pre-stage {'(DRY RUN) ' if args.dry_run else ''}summary:")
    print("=" * 60)
    print(report.summary())
    print()
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
