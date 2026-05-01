"""MLflow Instrumentation Engine.

Generates silent Python code to inject into the kernel:
  - Metrics hook: monkey-patches mlflow.log_metric to stream live metrics to the UI
  - Run Manager: starts/ends named MLflow runs with dataset and config lineage
"""

import logging

logger = logging.getLogger(__name__)


## Run Manager injection code ────────────────────────────────────

RUN_START_CODE = """\
try:
    import mlflow as __mlf_run
    if __mlf_run.active_run() is not None:
        __mlf_run.end_run()
    __mlf_run.set_experiment("{experiment_name}")
    __mlf_run.start_run(run_name="{run_name}")
    __mlf_run.set_tag("instrumentation", "experiments")
    del __mlf_run
except Exception:
    pass
"""

RUN_END_CODE = """\
try:
    import mlflow as __mlf_run
    if __mlf_run.active_run() is not None:
        __mlf_run.end_run()
    del __mlf_run
except Exception:
    pass
"""


## Metrics hook - monkey-patches mlflow.log_metric to emit display_data ──
## Run-start hook - monkey-patches mlflow.start_run and autolog's run creation
## to notify noted when a new MLflow run becomes active. Used by the Hydra
## bundle logger to know when to upload the per-run config bundle.

METRICS_HOOK_CODE = """\
try:
    if not globals().get('__noted_metrics_hooked'):
        import mlflow as __mlf_hook
        from IPython.display import display as __ipy_display
        import json as __json_hook
        import time as __time_hook
        __orig_log_metric = __mlf_hook.log_metric
        __orig_log_metrics = __mlf_hook.log_metrics
        def __noted_log_metric(key, value, step=None, **kw):
            __orig_log_metric(key, value, step=step, **kw)
            try:
                run = __mlf_hook.active_run()
                rid = run.info.run_id if run else None
                __ipy_display({"application/x-noted-metric": __json_hook.dumps({
                    "run_id": rid, "key": key, "value": float(value),
                    "step": step, "timestamp": __time_hook.time()
                })}, raw=True)
            except Exception:
                pass
        def __noted_log_metrics(metrics, step=None, **kw):
            __orig_log_metrics(metrics, step=step, **kw)
            try:
                run = __mlf_hook.active_run()
                rid = run.info.run_id if run else None
                for k, v in metrics.items():
                    __ipy_display({"application/x-noted-metric": __json_hook.dumps({
                        "run_id": rid, "key": k, "value": float(v),
                        "step": step, "timestamp": __time_hook.time()
                    })}, raw=True)
            except Exception:
                pass
        __mlf_hook.log_metric = __noted_log_metric
        __mlf_hook.log_metrics = __noted_log_metrics

        # Run-start hook: notify noted whenever a new MLflow run becomes
        # active so the backend can upload the Hydra bundle for that run.
        # Patches both mlflow.start_run() and tracks the active run at
        # subsequent log_metric/log_param calls to catch autolog-created runs.
        __orig_start_run = __mlf_hook.start_run
        __noted_last_run_id = [None]
        def __noted_emit_run_start(rid):
            try:
                if rid and rid != __noted_last_run_id[0]:
                    __noted_last_run_id[0] = rid
                    __ipy_display({"application/x-noted-run-start": __json_hook.dumps({
                        "run_id": rid, "timestamp": __time_hook.time()
                    })}, raw=True)
            except Exception:
                pass
        def __noted_start_run(*a, **kw):
            _r = __orig_start_run(*a, **kw)
            try:
                rid = _r.info.run_id if _r and hasattr(_r, 'info') else None
                if not rid:
                    run = __mlf_hook.active_run()
                    rid = run.info.run_id if run else None
                __noted_emit_run_start(rid)
            except Exception:
                pass
            return _r
        __mlf_hook.start_run = __noted_start_run

        # Wrap log_param and set_tag to catch autolog-created runs that
        # bypass start_run. These fire once per new run_id, then short-circuit.
        __orig_log_param = __mlf_hook.log_param
        def __noted_log_param(key, value, **kw):
            _res = __orig_log_param(key, value, **kw)
            try:
                run = __mlf_hook.active_run()
                if run:
                    __noted_emit_run_start(run.info.run_id)
            except Exception:
                pass
            return _res
        __mlf_hook.log_param = __noted_log_param

        __noted_metrics_hooked = True
except Exception:
    pass
"""


class AutoInstrumentation:
    """Manages MLflow instrumentation code generation."""

    def get_metrics_hook_code(self) -> str:
        """Return code to install the mlflow.log_metric monkey-patch (idempotent)."""
        return METRICS_HOOK_CODE

    def get_run_start_code(self, run_name: str, experiment_name: str = '',
                           dataset_hashes: dict = None, config_hash: str = None) -> str:
        """Return code to start a named MLflow run (Run Manager).

        If dataset_hashes is provided, also logs DVC data lineage
        (hash as param + tags for hash and file path).
        If config_hash is provided, logs the Hydra config hash for reproducibility.
        """
        safe_name = run_name.replace("\\", "\\\\").replace('"', '\\"')
        safe_exp = experiment_name.replace("\\", "\\\\").replace('"', '\\"')
        code = METRICS_HOOK_CODE + RUN_START_CODE.format(run_name=safe_name, experiment_name=safe_exp)
        if dataset_hashes:
            code += self._get_dataset_logging_code(dataset_hashes)
        if config_hash:
            code += self._get_config_hash_logging_code(config_hash)
        return code

    @staticmethod
    def _get_dataset_logging_code(dataset_hashes: dict) -> str:
        """Generate silent code to log DVC dataset hashes into the active MLflow run."""
        lines = ["try:", "    import mlflow as __mlf_ds"]
        for path, md5 in dataset_hashes.items():
            safe_path = path.replace("\\", "\\\\").replace('"', '\\"')
            safe_hash = md5.replace('"', '\\"')
            lines.append(f'    __mlf_ds.log_param("dvc_data_hash", "{safe_hash}")')
            lines.append(f'    __mlf_ds.set_tag("dvc.data_hash", "{safe_hash}")')
            lines.append(f'    __mlf_ds.set_tag("dvc.data_file", "{safe_path}")')
        lines += ["    del __mlf_ds", "except Exception:", "    pass", ""]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _get_config_hash_logging_code(config_hash: str) -> str:
        """Generate silent code to log Hydra config hash into the active MLflow run."""
        safe_hash = config_hash.replace('"', '\\"')
        return (
            'try:\n'
            '    import mlflow as __mlf_cfg\n'
            f'    __mlf_cfg.log_param("hydra_config_hash", "{safe_hash}")\n'
            f'    __mlf_cfg.set_tag("hydra.config_hash", "{safe_hash}")\n'
            '    del __mlf_cfg\n'
            'except Exception:\n'
            '    pass\n'
        )

    def get_run_end_code(self) -> str:
        """Return code to activate autolog and end the MLflow run (Run Manager)."""
        return RUN_END_CODE
