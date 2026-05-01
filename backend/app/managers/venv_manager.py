"""Backward-compatible wrapper around EnvironmentManager.

Keeps old flat-name API (list_envs, create_env, get_python_path, etc.)
working while the system transitions to the new runtime-aware API.
"""
import os
from typing import Optional
from app.managers.env_manager import EnvironmentManager, RuntimeRegistry


# Default runtime used for legacy flat-name operations
_DEFAULT_RUNTIME_ID = "python/3.12"


class VenvManager:
    """Legacy API wrapper. Delegates to EnvironmentManager."""

    def __init__(self):
        self._registry = RuntimeRegistry()
        self._env_mgr = EnvironmentManager(registry=self._registry)

    @property
    def env_manager(self) -> EnvironmentManager:
        return self._env_mgr

    @property
    def registry(self) -> RuntimeRegistry:
        return self._registry

    def _find_env(self, name: str) -> Optional[str]:
        """Find the runtime_id for an env by name (scans all runtimes)."""
        for env in self._env_mgr.list_envs():
            if env["name"] == name:
                return env["runtime_id"]
        return None

    def get_python_path(self, name: str) -> str:
        """Legacy: resolve env name to python executable path."""
        runtime_id = self._find_env(name)
        if not runtime_id:
            raise FileNotFoundError(f"Environment not found: {name}")
        env_path = self._env_mgr._env_path(runtime_id, name)
        python_path = os.path.join(env_path, "bin", "python")
        if not os.path.exists(python_path):
            raise FileNotFoundError(f"Environment not found: {name}")
        return python_path

    def list_envs(self) -> list[dict]:
        """Legacy: return flat list with name + python_version."""
        envs = self._env_mgr.list_envs()
        result = []
        for env in envs:
            env_path = self._env_mgr._env_path(env["runtime_id"], env["name"])
            version = self._get_python_version(env_path)
            result.append({
                "name": env["name"],
                "python_version": version,
                "runtime_id": env["runtime_id"],
                "display_name": env["display_name"],
            })
        return result

    def _get_python_version(self, venv_path: str) -> Optional[str]:
        cfg = os.path.join(venv_path, "pyvenv.cfg")
        if not os.path.exists(cfg):
            return None
        try:
            with open(cfg) as f:
                for line in f:
                    key, _, val = line.partition("=")
                    if key.strip().lower() == "version":
                        return val.strip()
        except OSError:
            pass
        return None

    async def create_env(self, name: str,
                         requirements: Optional[list[str]] = None) -> dict:
        return await self._env_mgr.create_env(
            _DEFAULT_RUNTIME_ID, name, requirements
        )

    async def delete_env(self, name: str) -> dict:
        runtime_id = self._find_env(name)
        if not runtime_id:
            raise FileNotFoundError(f"Environment not found: {name}")
        return await self._env_mgr.delete_env(runtime_id, name)

    async def list_packages(self, name: str) -> list[dict]:
        runtime_id = self._find_env(name)
        if not runtime_id:
            raise FileNotFoundError(f"Environment not found: {name}")
        return await self._env_mgr.list_packages(runtime_id, name)

    async def install_packages(self, name: str, packages: list[str]) -> dict:
        runtime_id = self._find_env(name)
        if not runtime_id:
            raise FileNotFoundError(f"Environment not found: {name}")
        return await self._env_mgr.install_packages(runtime_id, name, packages)

    async def remove_packages(self, name: str, packages: list[str]) -> dict:
        runtime_id = self._find_env(name)
        if not runtime_id:
            raise FileNotFoundError(f"Environment not found: {name}")
        return await self._env_mgr.remove_packages(runtime_id, name, packages)
