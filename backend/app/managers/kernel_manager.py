import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from jupyter_client import KernelManager as JupyterKernelManager
from app.config import KERNEL_IDLE_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class KernelSession:
    session_id: str
    kernel_manager: JupyterKernelManager
    kernel_cmd: list[str]
    kernel_language: str
    display_name: str
    project_id: str
    notebook_path: str
    client_sid: str
    room_key: str = ""
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    status: str = "starting"
    debug_port: int = 0  # debugpy listen port (0 = not yet initialized)
    kernel_pid: int = 0  # kernel process PID (for cell temp file mapping)
    debug_active: bool = False  # True when DAP debug session is connected
    debug_shadow_path: str = ""  # path to shadow file for Debug All
    debug_cell_map: list = field(default_factory=list)  # cell-to-line mapping
    # Per-runtime config preserved for restart
    runtime_kernel_env: Optional[dict] = None
    env_path: Optional[str] = None
    # Latest hydra_config payload sent by the frontend for this session.
    # Used by the iopub listener to upload a per-run bundle when a new MLflow
    # run is detected (Hydra unification plan M2).
    current_hydra_config: Optional[dict] = None
    # Notebook UID (set by the frontend on Hydra-using notebooks). Used as
    # part of the cache key for MLflow-sourced baselines (M3).
    current_notebook_uid: Optional[str] = None
    _debug_kc: object = field(default=None, repr=False)  # debug kernel client
    _cached_client: object = field(default=None, repr=False)


class KernelManagerService:
    """Manages Jupyter kernel processes."""

    def __init__(self):
        self._kernels: dict[str, KernelSession] = {}
        self._room_index: dict[str, str] = {}  # room_key -> session_id
        self._cleanup_task: Optional[asyncio.Task] = None
        self._client_locks: dict[str, asyncio.Lock] = {}

    async def start(self):
        self._cleanup_task = asyncio.create_task(self._idle_cleanup_loop())

    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        for session_id in list(self._kernels.keys()):
            await self.stop_kernel(session_id)

    async def start_kernel(self, session_id: str, kernel_cmd: list[str],
                           kernel_language: str, display_name: str,
                           project_id: str, notebook_path: str,
                           client_sid: str, room_key: str = "",
                           runtime_kernel_env: Optional[dict] = None,
                           env_path: Optional[str] = None) -> KernelSession:
        if session_id in self._kernels:
            await self.stop_kernel(session_id)

        km = JupyterKernelManager(kernel_name="python3")

        # Bypass kernel spec lookup by providing the command directly.
        km.kernel_cmd = kernel_cmd

        # Provide a minimal kernel spec so the manager doesn't try to
        # look one up from disk.
        from jupyter_client.kernelspec import KernelSpec
        km._kernel_spec = KernelSpec(
            argv=kernel_cmd,
            display_name=display_name,
            language=kernel_language,
        )

        # Set kernel working directory to the project root
        kernel_cwd = None
        if project_id:
            from app.managers.project_registry import get_registry
            try:
                kernel_cwd = get_registry().resolve(project_id)
            except FileNotFoundError:
                kernel_cwd = None
        if not kernel_cwd or not os.path.isdir(kernel_cwd):
            kernel_cwd = None

        # Add project root to PYTHONPATH so notebooks can import project files
        project_root = kernel_cwd

        # Build a clean environment for the kernel subprocess.
        kernel_env = os.environ.copy()

        if kernel_language == "python":
            self._inject_python_env(kernel_env, kernel_cmd, project_root)
        elif kernel_language == "javascript":
            self._inject_javascript_env(kernel_env, kernel_cmd)

        # Merge per-runtime kernel_env declared in runtime.json (R uses this
        # for R_HOME, LD_LIBRARY_PATH, R_PROFILE_USER, RENV_PATHS_*).
        # Templates {env_path} and {project_root} are resolved here so the
        # runtime.json file stays generic.
        if runtime_kernel_env:
            for key, value in runtime_kernel_env.items():
                resolved = value
                if env_path:
                    resolved = resolved.replace("{env_path}", env_path)
                if project_root:
                    resolved = resolved.replace("{project_root}", project_root)
                kernel_env[key] = resolved

        # Run blocking kernel start in executor to avoid blocking the event loop
        kw = {"env": kernel_env}
        if kernel_cwd:
            kw["cwd"] = kernel_cwd
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: km.start_kernel(**kw)
        )

        # Give kernel process a moment to either start or crash
        await asyncio.sleep(1)
        if not km.is_alive():
            logger.error(f"Kernel process died immediately for {session_id}")
            raise RuntimeError(
                f"Kernel process failed to start. Check that the kernel is properly installed in the environment."
            )

        # Capture kernel PID for debugpy cell filename mapping
        kernel_pid = 0
        try:
            if hasattr(km, 'provisioner') and km.provisioner:
                kernel_pid = km.provisioner.pid or 0
        except Exception:
            pass

        session = KernelSession(
            session_id=session_id,
            kernel_manager=km,
            kernel_cmd=kernel_cmd,
            kernel_language=kernel_language,
            display_name=display_name,
            project_id=project_id,
            notebook_path=notebook_path,
            client_sid=client_sid,
            room_key=room_key,
            status="idle",
            kernel_pid=kernel_pid,
            runtime_kernel_env=runtime_kernel_env,
            env_path=env_path,
        )
        self._kernels[session_id] = session
        if room_key:
            self._room_index[room_key] = session_id
        self._client_locks[session_id] = asyncio.Lock()

        # Eagerly create and cache the kernel client
        kc = km.client()
        kc.start_channels()
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: kc.wait_for_ready(timeout=15)
            )
            session._cached_client = kc
        except RuntimeError as e:
            logger.warning(f"Kernel client not immediately ready: {e}")
            kc.stop_channels()

        # Run silent init code to configure the kernel environment
        if session._cached_client:
            if kernel_language == "python":
                init_code = (
                    "try:\n"
                    "    get_ipython().run_line_magic('matplotlib', 'inline')\n"
                    "except Exception:\n"
                    "    pass\n"
                    "try:\n"
                    "    import plotly.io as pio; pio.renderers.default = 'notebook'\n"
                    "except Exception:\n"
                    "    pass\n"
                )
                session._cached_client.execute(init_code, silent=True, store_history=False)
                # debugpy is initialized on-demand when user starts a debug session
            elif kernel_language == "javascript":
                # Enable automatic Promise resolution so top-level await
                # patterns work (async IIFEs wait for completion)
                session._cached_client.execute(
                    "$$.config.awaitExecution = true;",
                    silent=True, store_history=False,
                )
                # Capture V8 Inspector port (kernel started with --inspect=0)
                await self._capture_inspect_port(session)

        logger.info(f"Kernel started: {session_id} ({display_name}), pid={kernel_pid}")
        return session

    async def init_debugpy(self, session_id: str) -> int:
        """Initialize or reinitialize debugpy inside the kernel process.

        Called on-demand when user starts a debug session.
        Forces a new listener on a random port (closes any previous one).
        Returns the debug port, or 0 on failure.
        """
        session = self._kernels.get(session_id)
        if not session:
            return 0
        kc = session._cached_client
        if not kc:
            return 0

        debugpy_code = (
            "try:\n"
            "    import debugpy\n"
            "    # Close existing listener/connection if any\n"
            "    try:\n"
            "        debugpy.disconnect()\n"
            "    except Exception:\n"
            "        pass\n"
            "    _host, _port = debugpy.listen(('127.0.0.1', 0))\n"
            "    print(f'DEBUGPY_PORT={_port}')\n"
            "except Exception as _e:\n"
            "    print(f'DEBUGPY_FAILED={_e}')\n"
        )

        msg_id = kc.execute(debugpy_code, silent=True, store_history=False)

        # Wait for the output that contains the port number
        try:
            for _ in range(50):  # up to 5 seconds
                await asyncio.sleep(0.1)
                try:
                    msg = kc.get_iopub_msg(timeout=0.05)
                    content = msg.get("content", {})
                    text = content.get("text", "")
                    if "DEBUGPY_PORT=" in text:
                        port = int(text.strip().split("=")[1])
                        session.debug_port = port
                        logger.info(f"debugpy listening on port {port} for {session.session_id}")
                        return port
                    if "DEBUGPY_FAILED=" in text:
                        logger.warning(f"debugpy init failed for {session.session_id}: {text}")
                        return 0
                except Exception:
                    continue
            logger.warning(f"debugpy port not captured for {session.session_id} (timeout)")
        except Exception as e:
            logger.warning(f"debugpy init error for {session.session_id}: {e}")
        return 0

    def _inject_python_env(self, kernel_env: dict, kernel_cmd: list[str],
                           project_root: str | None):
        """Set Python-specific environment variables for the kernel process.

        Includes CUDA/GPU library paths, PYTHONPATH, TensorFlow noise
        suppression, matplotlib inline backend, and MLflow tracking URI.
        """
        gpu_lib_paths = [
            "/usr/lib/wsl/lib",
            "/usr/local/cuda/lib64",
        ]

        # Add pip-installed nvidia library paths from the venv (tensorflow[and-cuda])
        import glob
        venv_python = kernel_cmd[0] if kernel_cmd else None
        if venv_python:
            venv_dir = os.path.dirname(os.path.dirname(venv_python))
            nvidia_glob = os.path.join(
                venv_dir, "lib", "python*", "site-packages", "nvidia", "*", "lib"
            )
            gpu_lib_paths.extend(sorted(glob.glob(nvidia_glob)))

        existing_ld = kernel_env.get("LD_LIBRARY_PATH", "")
        extra = ":".join(p for p in gpu_lib_paths if os.path.isdir(p))
        if extra:
            kernel_env["LD_LIBRARY_PATH"] = f"{extra}:{existing_ld}" if existing_ld else extra

        # Add project root to PYTHONPATH for notebook imports
        if project_root:
            existing_pp = kernel_env.get("PYTHONPATH", "")
            kernel_env["PYTHONPATH"] = (
                f"{project_root}:{existing_pp}" if existing_pp else project_root
            )

        # Suppress TensorFlow C++ runtime warnings (oneDNN, CPU feature guards, absl)
        kernel_env["TF_CPP_MIN_LOG_LEVEL"] = "3"
        kernel_env["TF_ENABLE_ONEDNN_OPTS"] = "0"
        kernel_env["GRPC_VERBOSITY"] = "ERROR"

        # Set matplotlib to inline backend for notebook rendering
        kernel_env["MPLBACKEND"] = "module://matplotlib_inline.backend_inline"

        # MLflow integration - connect notebooks to the platform MLflow instance.
        # Only TRACKING_URI is set. Experiment name is NOT set automatically.
        # Experiments are created explicitly via Run Manager or user code.
        kernel_env["MLFLOW_TRACKING_URI"] = "http://mlflow:5000"

    def _inject_javascript_env(self, kernel_env: dict, kernel_cmd: list[str]):
        """Set JavaScript-specific environment variables for the kernel process.

        Ensures fnm-managed Node.js is on the PATH and the environment's
        node_modules is on NODE_PATH so require() finds user packages.
        """
        fnm_dir = os.environ.get("FNM_DIR", "/root/.local/share/fnm")
        # fnm stores the active Node.js binary in a multishell or aliases dir.
        # We add both the fnm dir and the default node installation to PATH.
        fnm_paths = [fnm_dir]

        # Resolve the default Node.js installation path
        aliases_dir = os.path.join(fnm_dir, "aliases", "default")
        if os.path.islink(aliases_dir):
            resolved = os.path.realpath(aliases_dir)
            bin_dir = os.path.join(resolved, "bin")
            if os.path.isdir(bin_dir):
                fnm_paths.append(bin_dir)
        else:
            # Fallback: scan node-versions for the first available
            node_versions = os.path.join(fnm_dir, "node-versions")
            if os.path.isdir(node_versions):
                for entry in sorted(os.listdir(node_versions)):
                    bin_dir = os.path.join(node_versions, entry, "installation", "bin")
                    if os.path.isdir(bin_dir):
                        fnm_paths.append(bin_dir)
                        break

        existing_path = kernel_env.get("PATH", "")
        extra = ":".join(fnm_paths)
        kernel_env["PATH"] = f"{extra}:{existing_path}" if existing_path else extra

        # Add the environment's node_modules to NODE_PATH so require()
        # finds user-installed packages (lodash, express, etc.).
        # kernel_cmd[0] is "{env_path}/node_modules/.bin/ijskernel"
        if kernel_cmd:
            env_path = os.path.dirname(os.path.dirname(os.path.dirname(kernel_cmd[0])))
            node_modules = os.path.join(env_path, "node_modules")
            if os.path.isdir(node_modules):
                existing_np = kernel_env.get("NODE_PATH", "")
                kernel_env["NODE_PATH"] = (
                    f"{node_modules}:{existing_np}" if existing_np else node_modules
                )

        # Enable V8 Inspector for debugging. --inspect=0 picks a random port.
        # Both the parent kernel and the NEL child evaluator get inspectors.
        # We capture the child's port (via code execution) and attach to it.
        kernel_env["NODE_OPTIONS"] = "--inspect=0"

    async def _capture_inspect_port(self, session: 'KernelSession') -> int:
        """Capture the V8 Inspector port from a running JS kernel.

        When Node starts with --inspect=0, it prints:
            Debugger listening on ws://127.0.0.1:<port>/<uuid>
        We parse this from /proc/<pid>/fd/2 (stderr) or by connecting
        to the kernel and asking it to report the port.
        """
        # Ask the kernel to report its inspector URL via code execution
        kc = session._cached_client
        if not kc:
            return 0

        inspect_code = (
            "try {"
            "  const url = require('inspector').url();"
            "  if (url) {"
            "    const port = new URL(url).port;"
            "    console.log('NOTED_INSPECT_PORT=' + port);"
            "  } else {"
            "    console.log('NOTED_INSPECT_PORT=0');"
            "  }"
            "} catch(e) {"
            "  console.log('NOTED_INSPECT_PORT=0');"
            "}"
        )

        msg_id = kc.execute(inspect_code, silent=True, store_history=False)
        try:
            for _ in range(50):  # up to 5 seconds
                await asyncio.sleep(0.1)
                try:
                    msg = kc.get_iopub_msg(timeout=0.05)
                    content = msg.get("content", {})
                    text = content.get("text", "")
                    if "NOTED_INSPECT_PORT=" in text:
                        port = int(text.strip().split("=")[1])
                        session.debug_port = port
                        logger.info(
                            "V8 Inspector port captured: %d for %s",
                            port, session.session_id,
                        )
                        return port
                except Exception:
                    continue
            logger.warning("V8 Inspector port not captured for %s (timeout)", session.session_id)
        except Exception as e:
            logger.warning("V8 Inspector port capture error for %s: %s", session.session_id, e)
        return 0

    async def stop_kernel(self, session_id: str) -> bool:
        session = self._kernels.pop(session_id, None)
        self._client_locks.pop(session_id, None)
        if not session:
            return False
        if session.room_key:
            self._room_index.pop(session.room_key, None)
        try:
            if session._cached_client:
                session._cached_client.stop_channels()
                session._cached_client = None
        except Exception as e:
            logger.error(f"Error stopping kernel client channels {session_id}: {e}")
        try:
            if session.kernel_manager.is_alive():
                # Run blocking shutdown in executor to avoid blocking the event loop
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: session.kernel_manager.shutdown_kernel(now=True)
                )
            session.kernel_manager.cleanup_resources()
        except Exception as e:
            logger.error(f"Error stopping kernel {session_id}: {e}")
        logger.info(f"Kernel stopped: {session_id}")
        return True

    async def restart_kernel(self, session_id: str) -> Optional[KernelSession]:
        session = self._kernels.get(session_id)
        if not session:
            return None
        # Preserve room_key so get_session_by_room works during restart
        room_key = session.room_key
        await self.stop_kernel(session_id)
        if room_key:
            self._room_index[room_key] = session_id
        return await self.start_kernel(
            session_id, session.kernel_cmd,
            session.kernel_language, session.display_name,
            session.project_id, session.notebook_path,
            session.client_sid,
            room_key=room_key,
            runtime_kernel_env=session.runtime_kernel_env,
            env_path=session.env_path,
        )

    async def interrupt_kernel(self, session_id: str) -> bool:
        session = self._kernels.get(session_id)
        if not session:
            return False
        try:
            session.kernel_manager.interrupt_kernel()
            return True
        except Exception as e:
            logger.error(f"Error interrupting kernel {session_id}: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[KernelSession]:
        return self._kernels.get(session_id)

    def get_session_by_room(self, room_key: str) -> Optional[KernelSession]:
        """Look up kernel session by notebook room key (primary lookup)."""
        session_id = self._room_index.get(room_key)
        if session_id:
            return self._kernels.get(session_id)
        return None

    def get_session_by_sid(self, client_sid: str) -> Optional[KernelSession]:
        """Look up kernel session by client SID (backward compat / fallback)."""
        for session in self._kernels.values():
            if session.client_sid == client_sid:
                return session
        return None

    async def get_kernel_client(self, session_id: str):
        session = self._kernels.get(session_id)
        if not session:
            return None
        if not session.kernel_manager.is_alive():
            logger.error(f"Kernel process is not alive for session {session_id}")
            return None
        # Fast path: return cached client without locking
        if session._cached_client and session._cached_client.channels_running:
            return session._cached_client
        # Slow path: create client under lock to prevent concurrent creation
        lock = self._client_locks.get(session_id)
        if not lock:
            return None
        async with lock:
            # Re-check after acquiring lock
            if session._cached_client and session._cached_client.channels_running:
                return session._cached_client
            kc = session.kernel_manager.client()
            kc.start_channels()
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: kc.wait_for_ready(timeout=15)
                )
            except RuntimeError as e:
                logger.error(f"Kernel not ready for session {session_id}: {e}")
                kc.stop_channels()
                return None
            session._cached_client = kc
            return kc

    def heartbeat(self, session_id: str):
        session = self._kernels.get(session_id)
        if session:
            session.last_heartbeat = datetime.utcnow()

    def update_status(self, session_id: str, status: str):
        session = self._kernels.get(session_id)
        if session:
            session.status = status

    def list_kernels(self) -> list[dict]:
        return [
            {
                "session_id": s.session_id,
                "project_id": s.project_id,
                "notebook_path": s.notebook_path,
                "client_sid": s.client_sid,
                "status": s.status,
                "last_heartbeat": s.last_heartbeat.isoformat(),
                "alive": s.kernel_manager.is_alive()
            }
            for s in self._kernels.values()
        ]

    async def _idle_cleanup_loop(self):
        while True:
            await asyncio.sleep(60)
            now = datetime.utcnow()
            timeout = timedelta(seconds=KERNEL_IDLE_TIMEOUT_SECONDS)
            expired = [
                sid for sid, session in self._kernels.items()
                if now - session.last_heartbeat > timeout
            ]
            for sid in expired:
                logger.info(f"Idle timeout - stopping kernel: {sid}")
                await self.stop_kernel(sid)
