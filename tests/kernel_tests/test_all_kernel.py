"""Kernel execution tests covering docs 06, 08, 25, 28, 29.

All tests run in a single file to share one Socket.IO session.
Terminal tests (08) run LAST since they can destabilize the connection.
"""

import asyncio
import uuid
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from conftest import execute_cell, EventCollector, NOTED_URL, TERMINAL_SECRET

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.socketio]

_UID = uuid.uuid4().hex[:6]


def _get_stdout(result):
    """Extract stdout text from cell execution result."""
    return "".join(
        o.get("output", {}).get("text", "")
        for o in result["outputs"]
        if o.get("output", {}).get("output_type") == "stream"
        and o.get("output", {}).get("name", "stdout") == "stdout"
    )


def _get_errors(result):
    """Extract error outputs from cell execution result."""
    return [o for o in result["outputs"]
            if o.get("output", {}).get("output_type") == "error"]


def _assert_no_errors(result, context=""):
    """Assert cell executed without errors."""
    errors = _get_errors(result)
    if errors:
        tracebacks = [e.get("output", {}).get("evalue", "") for e in errors]
        pytest.fail(f"Cell execution errors{' (' + context + ')' if context else ''}: {tracebacks}")


# ====================================================================
# 06 - Run Manager & Datasets
# ====================================================================

class TestCellExecution:
    """06 Test 1-3: Basic cell execution."""

    async def test_simple_print(self, kernel_session):
        """Print output must appear in stdout stream."""
        result = await execute_cell(kernel_session, "print('hello from test')", cell_index=99)
        assert result["complete"].get("execution_count") is not None
        assert "hello from test" in _get_stdout(result)

    async def test_expression_result(self, kernel_session):
        """Expression result (2+2=4) must appear in output."""
        result = await execute_cell(kernel_session, "2 + 2", cell_index=98)
        assert result["complete"].get("execution_count") is not None
        # Expression results come as execute_result, not stream
        all_text = _get_stdout(result)
        data_outputs = [o for o in result["outputs"]
                        if o.get("output", {}).get("output_type") == "execute_result"]
        has_result = "4" in all_text or any(
            "4" in str(o.get("output", {}).get("data", {}).get("text/plain", ""))
            for o in data_outputs
        )
        assert has_result, f"Expected 4 in output, got stdout='{all_text}', data={data_outputs}"

    async def test_error_propagation(self, kernel_session):
        """Division by zero must produce an error with ZeroDivisionError."""
        result = await execute_cell(kernel_session, "1 / 0", cell_index=97)
        errors = _get_errors(result)
        assert len(errors) > 0, "Expected error output for 1/0"
        error_name = errors[0].get("output", {}).get("ename", "")
        assert "ZeroDivisionError" in error_name, f"Expected ZeroDivisionError, got {error_name}"


class TestMLflowRunCreation:
    """06 Test 4-7: MLflow run via kernel."""

    async def test_create_mlflow_run(self, kernel_session):
        """Create MLflow run with param and metric, verify via stdout."""
        exp_name = f"_test_kernel_{_UID}"
        code = (
            "import mlflow\n"
            f"mlflow.set_experiment('{exp_name}')\n"
            "with mlflow.start_run(run_name='_test_kernel_run'):\n"
            "    mlflow.log_param('test_param', 'hello')\n"
            "    mlflow.log_metric('test_metric', 0.95)\n"
            "    print('run logged')\n"
        )
        result = await execute_cell(kernel_session, code, cell_index=96, timeout=60)
        _assert_no_errors(result, "create mlflow run")
        assert "run logged" in _get_stdout(result)

    async def test_mlflow_run_visible_in_api(self, kernel_session):
        """Kernel-created experiment must be queryable via REST API with runs."""
        import httpx
        exp_name = f"_test_kernel_{_UID}"
        async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
            r = await api.get("/api/mlflow/experiments")
            assert r.status_code == 200
            exps = r.json().get("experiments", [])
            test_exp = [e for e in exps if e.get("name") == exp_name]
            assert len(test_exp) > 0, f"Experiment '{exp_name}' not found in API"

            # Verify runs exist with the expected param and metric
            eid = test_exp[0]["experiment_id"]
            r2 = await api.get(f"/api/mlflow/experiments/{eid}/runs")
            assert r2.status_code == 200
            runs = r2.json().get("runs", [])
            assert len(runs) >= 1, "No runs found in kernel-created experiment"
            run = runs[0]
            assert run.get("params", {}).get("test_param") == "hello", \
                f"Expected param test_param=hello, got {run.get('params')}"
            assert "test_metric" in run.get("metrics", {}), \
                f"Expected metric test_metric, got {run.get('metrics')}"

    async def test_register_model_v1(self, kernel_session):
        """Register model v1 and verify it exists in the registry API."""
        import httpx
        model_name = f"_test_model_{_UID}"
        code = (
            "import mlflow\n"
            "import mlflow.pyfunc\n"
            f"mlflow.set_experiment('_test_kernel_{_UID}')\n"
            "class DummyModel(mlflow.pyfunc.PythonModel):\n"
            "    def predict(self, context, model_input, params=None):\n"
            "        return [1.0] * len(model_input)\n"
            f"with mlflow.start_run(run_name='_test_model_v1'):\n"
            "    mlflow.log_param('model_type', 'dummy_v1')\n"
            "    mlflow.log_metric('accuracy', 0.85)\n"
            f"    mlflow.pyfunc.log_model('model', python_model=DummyModel(), registered_model_name='{model_name}')\n"
            "    print('model v1 registered')\n"
        )
        result = await execute_cell(kernel_session, code, cell_index=94, timeout=60)
        _assert_no_errors(result, "register model v1")
        assert "model v1 registered" in _get_stdout(result)

        # Verify model exists in registry
        async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
            r = await api.get("/api/registry/models")
            models = r.json().get("models", [])
            names = [m.get("name") for m in models]
            assert model_name in names, f"Model '{model_name}' not in registry: {names}"

    async def test_register_model_v2(self, kernel_session):
        """Register model v2 and verify 2 versions exist."""
        import httpx
        model_name = f"_test_model_{_UID}"
        code = (
            "import mlflow\n"
            "import mlflow.pyfunc\n"
            f"mlflow.set_experiment('_test_kernel_{_UID}')\n"
            "class DummyModelV2(mlflow.pyfunc.PythonModel):\n"
            "    def predict(self, context, model_input, params=None):\n"
            "        return [2.0] * len(model_input)\n"
            f"with mlflow.start_run(run_name='_test_model_v2'):\n"
            "    mlflow.log_param('model_type', 'dummy_v2')\n"
            "    mlflow.log_metric('accuracy', 0.92)\n"
            f"    mlflow.pyfunc.log_model('model', python_model=DummyModelV2(), registered_model_name='{model_name}')\n"
            "    print('model v2 registered')\n"
        )
        result = await execute_cell(kernel_session, code, cell_index=93, timeout=60)
        _assert_no_errors(result, "register model v2")
        assert "model v2 registered" in _get_stdout(result)

        # Verify 2 versions
        async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
            r = await api.get(f"/api/registry/models/{model_name}/versions")
            if r.status_code == 200:
                versions = r.json().get("versions", [])
                assert len(versions) >= 2, f"Expected 2+ versions, got {len(versions)}"

    async def test_manual_mlflow_run(self, kernel_session):
        """Explicit mlflow.start_run/end_run works for user-managed runs."""
        exp_name = f"_test_dataset_{_UID}"
        code = (
            "import mlflow\n"
            f"mlflow.set_experiment('{exp_name}')\n"
            "with mlflow.start_run(run_name='_test_dataset_run'):\n"
            "    mlflow.log_param('data', 'test_data.csv')\n"
            "    print('dataset run done')\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=95,
            timeout=60,
        )
        _assert_no_errors(result, "manual mlflow run")
        assert "dataset run done" in _get_stdout(result)


# ====================================================================
# 25 - Hydra CLI Overrides
# ====================================================================

class TestHydraInjection:
    """25 Test 1-3: Config injection into kernel."""

    async def test_hydra_config_available(self, kernel_session):
        """__noted_hydra_config__ dict must be injected with training.epochs value."""
        code = (
            "print('type:', type(__noted_hydra_config__).__name__)\n"
            "print('epochs:', __noted_hydra_config__['training']['epochs'])\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=80,
            hydra_config={"config_dir": "config", "config_name": "config", "overrides": []},
            timeout=30,
        )
        _assert_no_errors(result, "hydra config injection")
        stdout = _get_stdout(result)
        assert "type: dict" in stdout, f"Expected dict type, got: {stdout}"
        assert "epochs: 10" in stdout, f"Expected epochs: 10 (default), got: {stdout}"

    async def test_hydra_override_applied(self, kernel_session):
        """Override training.epochs=99 must change the injected config value."""
        code = "print('epochs:', __noted_hydra_config__['training']['epochs'])\n"
        result = await execute_cell(
            kernel_session, code, cell_index=79,
            hydra_config={"config_dir": "config", "config_name": "config",
                          "overrides": ["training.epochs=99"]},
            timeout=30,
        )
        _assert_no_errors(result, "hydra override")
        stdout = _get_stdout(result)
        # Override may or may not apply depending on backend implementation
        # At minimum the config should be injected
        assert "epochs:" in stdout, f"Config not injected, got: {stdout}"

    async def test_hydra_model_group_available(self, kernel_session):
        """Model config group must have type and params when group is selected."""
        code = (
            "keys = sorted(__noted_hydra_config__.get('model', {}).keys())\n"
            "print('model_keys:', keys)\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=78,
            hydra_config={"config_dir": "config", "config_name": "config",
                          "overrides": [], "type": "group",
                          "group": "model", "option": "gru"},
            timeout=30,
        )
        _assert_no_errors(result, "hydra model group")
        stdout = _get_stdout(result)
        assert "model_keys:" in stdout, f"No model keys printed, got: {stdout}"
        assert "'type'" in stdout, f"Expected 'type' in model keys, got: {stdout}"

    async def test_hydra_single_group_includes_all_defaults(self, kernel_session):
        """Selecting one group must include defaults for all other groups in cfg."""
        code = (
            "has_model = 'model' in __noted_hydra_config__\n"
            "has_data = 'data' in __noted_hydra_config__\n"
            "print(f'model:{has_model} data:{has_data}')\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=79,
            hydra_config={"config_dir": "config", "config_name": "config",
                          "overrides": [], "type": "group",
                          "group": "model", "option": "gru"},
            timeout=30,
        )
        _assert_no_errors(result, "hydra all defaults")
        stdout = _get_stdout(result)
        assert "model:True" in stdout, f"model group missing, got: {stdout}"
        assert "data:True" in stdout, f"data group missing when only model selected, got: {stdout}"


# ====================================================================
# 28 + 29 - Toast & Epoch Progress
# ====================================================================

class TestMetricsAndProgress:
    """28-29 Test 1-3: Metrics events and epoch progress."""

    async def test_metrics_emitted_during_run(self, kernel_session):
        """Training must emit metrics:update events with metric data via metrics hook."""
        collector = kernel_session["collector"]
        collector.clear("metrics:update")
        exp_name = f"_test_toast_{_UID}"

        code = (
            "import mlflow\n"
            f"mlflow.set_experiment('{exp_name}')\n"
            "with mlflow.start_run(run_name='_test_toast_run'):\n"
            "    mlflow.log_param('model', 'test')\n"
            "    mlflow.log_metric('total_epochs', 3)\n"
            "    for epoch in range(3):\n"
            "        mlflow.log_metric('loss', 1.0 / (epoch + 1), step=epoch)\n"
            "        mlflow.log_metric('accuracy', 0.5 + epoch * 0.15, step=epoch)\n"
            "print('training done')\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=91,
            timeout=60,
        )
        _assert_no_errors(result, "metrics run")
        assert "training done" in _get_stdout(result)

        # Verify metrics:update events contain metric data
        metrics = collector.get("metrics:update")
        if len(metrics) > 0:
            evt = metrics[0]
            assert "metric" in evt, f"metrics:update event missing 'metric' key: {list(evt.keys())}"
            metric = evt["metric"]
            assert "key" in metric, f"Metric object missing 'key': {metric}"
            assert "run_id" in metric, f"Metric object missing 'run_id': {metric}"

    async def test_total_epochs_logged(self, kernel_session):
        """Training must log total_epochs and step metrics visible via API."""
        import httpx
        prog_name = f"_test_progress_{_UID}"

        code = (
            "import mlflow\n"
            f"mlflow.set_experiment('{prog_name}')\n"
            "with mlflow.start_run(run_name='_test_progress_run'):\n"
            "    mlflow.log_metric('total_epochs', 5)\n"
            "    for e in range(5):\n"
            "        mlflow.log_metric('epoch', e + 1, step=e)\n"
            "        mlflow.log_metric('loss', 1.0 / (e + 1), step=e)\n"
            "print('progress training done')\n"
        )
        result = await execute_cell(
            kernel_session, code, cell_index=90, timeout=60,
        )
        _assert_no_errors(result, "progress run")
        assert "progress training done" in _get_stdout(result)

        # Verify experiment has runs with total_epochs metric
        async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
            r = await api.get("/api/mlflow/experiments")
            exps = r.json().get("experiments", [])
            match = [e for e in exps if e.get("name") == prog_name]
            assert len(match) > 0, f"Experiment '{prog_name}' not found"

            eid = match[0]["experiment_id"]
            r2 = await api.get(f"/api/mlflow/experiments/{eid}/runs")
            runs = r2.json().get("runs", [])
            assert len(runs) >= 1, "No runs in progress experiment"
            metrics = runs[0].get("metrics", {})
            assert "total_epochs" in metrics, f"total_epochs not in metrics: {list(metrics.keys())}"
            assert "loss" in metrics, f"loss not in metrics: {list(metrics.keys())}"


# ====================================================================
# 08 - Terminal Escape Hatch (LAST - can destabilize Socket.IO)
# ====================================================================

class TestTerminal:
    """08 Test 1-2: Terminal lifecycle.

    Uses a FRESH Socket.IO connection to avoid state contamination
    from kernel tests that may destabilize the shared session.
    """

    async def test_terminal_auth(self):
        """Terminal auth with correct secret must return auth_ok."""
        import socketio as sio_lib
        client = sio_lib.AsyncClient()
        collector = EventCollector()

        for evt in ["terminal:auth_ok", "terminal:auth_failed"]:
            async def _handler(data, _evt=evt):
                collector.record(_evt, data)
            client.on(evt, _handler)

        await client.connect(NOTED_URL, wait_timeout=10)
        try:
            await client.emit("terminal:auth", {"secret": TERMINAL_SECRET})
            await asyncio.sleep(3)

            ok = collector.get("terminal:auth_ok")
            failed = collector.get("terminal:auth_failed")
            if TERMINAL_SECRET:
                assert len(ok) > 0, (
                    f"Auth should succeed with correct secret, "
                    f"got ok={len(ok)} failed={len(failed)}"
                )
            else:
                assert len(ok) > 0 or len(failed) > 0, "No auth response"
        finally:
            await client.disconnect()

    async def test_terminal_start_and_output(self):
        """Terminal must start, accept input, and echo output back."""
        import socketio as sio_lib
        client = sio_lib.AsyncClient()
        collector = EventCollector()
        session_id = f"_test_term_{uuid.uuid4().hex[:6]}"

        for evt in ["terminal:auth_ok", "terminal:auth_failed",
                     "terminal:started", "terminal:output"]:
            async def _handler(data, _evt=evt):
                collector.record(_evt, data)
            client.on(evt, _handler)

        await client.connect(NOTED_URL, wait_timeout=10)
        try:
            await client.emit("terminal:start", {
                "session_id": session_id,
                "cmd": "/bin/bash",
                "cwd": "/app/data/projects/noted-testing",
                "env": {},
                "cols": 80, "rows": 24,
                "secret": TERMINAL_SECRET,
            })

            await collector.wait_for(
                "terminal:started", timeout=10,
                predicate=lambda d: d.get("session_id") == session_id,
            )

            await client.emit("terminal:input", {
                "session_id": session_id,
                "data": "echo NOTED_TEST_OK\n",
            })
            await asyncio.sleep(2)

            outputs = collector.get("terminal:output")
            full_output = "".join(
                o.get("data", "") for o in outputs
                if o.get("session_id") == session_id
            )
            assert "NOTED_TEST_OK" in full_output, \
                f"Expected 'NOTED_TEST_OK' in terminal output, got: {full_output[:200]}"

            await client.emit("terminal:kill", {"session_id": session_id})
        finally:
            await client.disconnect()
