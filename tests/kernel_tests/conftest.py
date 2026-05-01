"""Socket.IO test fixtures for kernel execution and terminal tests.

Provides async Socket.IO client that connects to noted, opens a notebook,
starts a kernel, and cleans up on teardown.
"""

import os
import asyncio
import pytest
import pytest_asyncio
import httpx
import socketio

NOTED_URL = os.environ.get("NOTED_URL", "http://localhost:8123")
PROJECT_ID = os.environ.get("NOTED_PROJECT", "noted-testing")
NOTEBOOK_PATH = "test_notebook.ipynb"
TERMINAL_SECRET = os.environ.get("NOTED_TERMINAL_SECRET", "")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def scaffold_for_kernel():
    """Ensure essential project artifacts exist before kernel tests."""
    async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
        async def _write(path, content):
            parts = path.split("/")
            for i in range(1, len(parts)):
                d = "/".join(parts[:i])
                await api.post(f"/api/files/project/{PROJECT_ID}",
                               json={"path": d, "is_dir": True})
            await api.put(f"/api/files/project/{PROJECT_ID}/write",
                          params={"path": path}, json={"content": content})

        # Hydra config
        await _write("config/config.yaml", (
            "defaults:\n  - model: linear\n\n"
            "training:\n  epochs: 10\n  batch_size: 32\n  learning_rate: 0.001\n"
        ))
        await _write("config/model/linear.yaml", (
            "type: linear\nparams:\n  input_dim: 14\n  output_dim: 1\n"
        ))
        await _write("config/model/gru.yaml", (
            "type: gru\nparams:\n  units1: 128\n  units2: 64\n  dropout: 0.2\n"
        ))

        # Notebook for kernel tests
        import json
        nb = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3",
                                         "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "code", "metadata": {}, "outputs": [],
                 "source": ["print('kernel test notebook')"], "execution_count": None},
            ],
        }
        await api.put(f"/api/files/project/{PROJECT_ID}/write",
                       params={"path": NOTEBOOK_PATH},
                       json={"content": json.dumps(nb)})


class EventCollector:
    """Collects Socket.IO events for test assertions."""

    def __init__(self):
        self.events = {}
        self._queue = asyncio.Queue()

    def record(self, event_name, data):
        self.events.setdefault(event_name, []).append(data)
        self._queue.put_nowait((event_name, data))

    def get(self, event_name):
        return self.events.get(event_name, [])

    def clear(self, event_name=None):
        if event_name:
            self.events.pop(event_name, None)
        else:
            self.events.clear()
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def wait_for(self, event_name, timeout=30, predicate=None):
        """Wait until an event matching predicate arrives."""
        # Check existing
        for data in self.get(event_name):
            if predicate is None or predicate(data):
                return data

        # Wait for new events from queue
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                name, data = await asyncio.wait_for(
                    self._queue.get(), timeout=remaining
                )
                if name == event_name and (predicate is None or predicate(data)):
                    return data
            except asyncio.TimeoutError:
                break

        # Debug: show what events are in the collector
        all_events = {k: len(v) for k, v in self.events.items()}
        pytest.fail(
            f"Timed out waiting for '{event_name}' within {timeout}s. "
            f"Events collected: {all_events}, queue empty: {self._queue.empty()}"
        )


@pytest_asyncio.fixture(scope="session")
async def runtime_info():
    """Discover available runtime and env for kernel start."""
    async with httpx.AsyncClient(base_url=NOTED_URL, timeout=10) as api:
        r = await api.get("/api/envs")
        if r.status_code != 200:
            pytest.skip(f"Cannot list envs: {r.status_code}")
        envs = r.json()
        if not envs:
            pytest.skip("No environments available")

        env = envs[0]
        return {
            "runtime_id": env.get("runtime_id", "python/3.12"),
            "env_name": env["name"],
        }


@pytest_asyncio.fixture(scope="session")
async def kernel_session(runtime_info):
    """Connect Socket.IO, open notebook, start kernel, yield collector."""
    collector = EventCollector()
    client = socketio.AsyncClient(
        reconnection=True,
        reconnection_attempts=3,
        reconnection_delay=1,
    )

    def _make_handler(evt_name):
        async def handler(data):
            collector.record(evt_name, data)
        return handler

    for evt in ["notebook:state", "kernel:status", "error",
                "cell:output", "cell:execute_complete", "metrics:update",
                "terminal:auth_ok", "terminal:auth_failed",
                "terminal:started", "terminal:output"]:
        client.on(evt, _make_handler(evt))

    await client.connect(NOTED_URL, wait_timeout=15)

    # Open notebook
    await client.emit("notebook:open", {
        "project_id": PROJECT_ID,
        "notebook_path": NOTEBOOK_PATH,
        "user_name": "test-runner",
    })
    await asyncio.sleep(2)

    # Start kernel
    await client.emit("kernel:start", {
        "project_id": PROJECT_ID,
        "notebook_path": NOTEBOOK_PATH,
        "runtime_id": runtime_info["runtime_id"],
        "env_name": runtime_info["env_name"],
    })

    # Wait for kernel idle
    await collector.wait_for(
        "kernel:status",
        timeout=30,
        predicate=lambda d: d.get("status") == "idle",
    )

    yield {
        "client": client,
        "collector": collector,
        "project_id": PROJECT_ID,
        "notebook_path": NOTEBOOK_PATH,
    }

    # Teardown - resilient to already-disconnected client
    try:
        if client.connected:
            await client.emit("kernel:stop", {
                "project_id": PROJECT_ID,
                "notebook_path": NOTEBOOK_PATH,
            })
            await asyncio.sleep(1)
            await client.emit("notebook:close", {
                "project_id": PROJECT_ID,
                "notebook_path": NOTEBOOK_PATH,
            })
            await client.disconnect()
    except Exception:
        pass


async def execute_cell(session, code, cell_index=0, timeout=30,
                       hydra_config=None):
    """Execute a cell and wait for completion."""
    client = session["client"]
    collector = session["collector"]

    collector.clear("cell:output")
    collector.clear("cell:execute_complete")

    payload = {
        "project_id": session["project_id"],
        "notebook_path": session["notebook_path"],
        "cell_index": cell_index,
        "code": code,
    }
    if hydra_config:
        payload["hydra_config"] = hydra_config

    await client.emit("cell:execute", payload)

    complete = await collector.wait_for(
        "cell:execute_complete",
        timeout=timeout,
        predicate=lambda d: d.get("cell_index") == cell_index,
    )

    outputs = [o for o in collector.get("cell:output")
               if o.get("cell_index") == cell_index]

    return {
        "outputs": outputs,
        "complete": complete,
    }
