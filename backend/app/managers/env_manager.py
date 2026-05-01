import os
import json
import asyncio
import shutil
import logging
from typing import Optional
from app.config import ENVIRONMENTS_DIR, RUNTIMES_DIR

logger = logging.getLogger(__name__)


class RuntimeRegistry:
    """Discovers available runtimes from data/runtimes/{language}/{version}/runtime.json."""

    def __init__(self, runtimes_dir: str = RUNTIMES_DIR):
        self._runtimes_dir = runtimes_dir
        self._cache: dict[str, dict] = {}  # key: "language/version"
        self._loaded = False

    def _load(self):
        self._cache.clear()
        if not os.path.exists(self._runtimes_dir):
            self._loaded = True
            return
        required_keys = (
            "language", "version", "display_name", "executable",
            "env_create_cmd", "kernel_cmd", "kernel_language",
        )
        for language in sorted(os.listdir(self._runtimes_dir)):
            lang_dir = os.path.join(self._runtimes_dir, language)
            if not os.path.isdir(lang_dir):
                continue
            for version in sorted(os.listdir(lang_dir)):
                ver_dir = os.path.join(lang_dir, version)
                runtime_file = os.path.join(ver_dir, "runtime.json")
                if not os.path.isfile(runtime_file):
                    continue
                try:
                    with open(runtime_file) as f:
                        spec = json.load(f)
                    if not all(k in spec for k in required_keys):
                        logger.warning(f"Skipping incomplete runtime: {runtime_file}")
                        continue
                    self._cache[f"{language}/{version}"] = spec
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to load runtime {runtime_file}: {e}")
        self._loaded = True
        logger.info(f"Loaded {len(self._cache)} runtimes: {list(self._cache.keys())}")

    def list_runtimes(self) -> list[dict]:
        if not self._loaded:
            self._load()
        return [
            {
                "language": spec["language"],
                "version": spec["version"],
                "display_name": spec["display_name"],
                "runtime_id": runtime_id,
            }
            for runtime_id, spec in self._cache.items()
        ]

    def get_runtime(self, runtime_id: str) -> Optional[dict]:
        if not self._loaded:
            self._load()
        return self._cache.get(runtime_id)

    def resolve_template(self, template: list[str], **kwargs) -> list[str]:
        result = []
        for part in template:
            for key, value in kwargs.items():
                part = part.replace(f"{{{key}}}", value)
            result.append(part)
        return result


class EnvironmentManager:
    """Manages environments across all runtime types. Language-agnostic."""

    def __init__(self, environments_dir: str = ENVIRONMENTS_DIR,
                 registry: Optional[RuntimeRegistry] = None):
        self._environments_dir = environments_dir
        self._registry = registry or RuntimeRegistry()
        self._install_procs = {}  # key: "runtime_id:env_name" -> asyncio.subprocess.Process
        self._migrate_flat_environments()
        self._repair_environments()

    def _migrate_flat_environments(self):
        """Move old flat data/environments/{name} to data/environments/python/3.12/{name}."""
        if not os.path.exists(self._environments_dir):
            return
        default_runtime = "python/3.12"
        for item in os.listdir(self._environments_dir):
            item_path = os.path.join(self._environments_dir, item)
            if not os.path.isdir(item_path):
                continue
            # Old flat env: has bin/python directly (even if symlink is broken)
            if os.path.lexists(os.path.join(item_path, "bin", "python")):
                target_dir = os.path.join(self._environments_dir, default_runtime)
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, item)
                if not os.path.exists(target_path):
                    try:
                        shutil.move(item_path, target_path)
                        self._fix_shebangs(target_path, item_path)
                        logger.info(f"Migrated environment '{item}' to {default_runtime}/{item}")
                    except OSError as e:
                        logger.warning(f"Failed to migrate environment '{item}': {e}")

    def _fix_shebangs(self, new_env_path: str, old_env_path: str):
        """Rewrite shebangs in bin/ scripts after moving an environment."""
        bin_dir = os.path.join(new_env_path, "bin")
        if not os.path.isdir(bin_dir):
            return
        old_prefix = old_env_path
        new_prefix = new_env_path
        for entry in os.listdir(bin_dir):
            entry_path = os.path.join(bin_dir, entry)
            if os.path.islink(entry_path) or not os.path.isfile(entry_path):
                continue
            try:
                with open(entry_path, "rb") as f:
                    first_line = f.readline()
                if not first_line.startswith(b"#!"):
                    continue
                shebang = first_line.decode("utf-8", errors="replace")
                if old_prefix not in shebang:
                    continue
                with open(entry_path, "rb") as f:
                    content = f.read()
                content = content.replace(
                    old_prefix.encode(), new_prefix.encode()
                )
                with open(entry_path, "wb") as f:
                    f.write(content)
                logger.info(f"Fixed shebang in {entry_path}")
            except OSError:
                pass

    def _repair_environments(self):
        """Repair venvs whose Python symlinks point to a stale path.

        This runs at every startup so that image rebuilds (new Python patch
        versions, path changes like /usr/local -> /usr/bin) are handled
        transparently without requiring users to recreate environments.

        Only Python venvs are repaired here. Other languages (R via renv,
        JavaScript via pnpm) have their own layouts that are not symlink-
        based and do not need this kind of fixup.
        """
        if not os.path.exists(self._environments_dir):
            return
        for language in os.listdir(self._environments_dir):
            if language != "python":
                continue  # repair logic is Python-specific
            lang_dir = os.path.join(self._environments_dir, language)
            if not os.path.isdir(lang_dir):
                continue
            if os.path.lexists(os.path.join(lang_dir, "bin", "python")):
                continue  # un-migrated flat env
            for version in os.listdir(lang_dir):
                ver_dir = os.path.join(lang_dir, version)
                if not os.path.isdir(ver_dir):
                    continue
                runtime_id = f"{language}/{version}"
                runtime = self._registry.get_runtime(runtime_id)
                if not runtime:
                    continue
                correct_executable = runtime["executable"]
                correct_home = os.path.dirname(correct_executable)
                for env_name in os.listdir(ver_dir):
                    env_path = os.path.join(ver_dir, env_name)
                    if not os.path.isdir(env_path):
                        continue
                    self._repair_venv(env_path, correct_executable, correct_home, env_name)

    def _repair_venv(self, env_path: str, correct_executable: str,
                     correct_home: str, env_name: str):
        """Fix a single venv's symlinks and pyvenv.cfg if they point to a stale path."""
        bin_dir = os.path.join(env_path, "bin")
        if not os.path.isdir(bin_dir):
            return

        # Check if the main python symlink resolves correctly
        python_ok = False
        python_link = os.path.join(bin_dir, "python")
        if os.path.lexists(python_link) and os.path.exists(python_link):
            resolved = os.path.realpath(python_link)
            if resolved == os.path.realpath(correct_executable):
                python_ok = True

        # Always fix shebangs (e.g. pip scripts with stale paths)
        self._repair_shebangs(env_path, env_name)

        if python_ok:
            return

        # Find and fix versioned python symlinks (e.g. python3.12)
        repaired = False
        for entry in os.listdir(bin_dir):
            entry_path = os.path.join(bin_dir, entry)
            if not os.path.islink(entry_path):
                continue
            target = os.readlink(entry_path)
            # Only fix python symlinks that point outside the venv (absolute paths)
            if not entry.startswith("python"):
                continue
            if os.path.isabs(target) and not os.path.exists(target):
                # Broken absolute symlink — repoint to correct executable
                os.remove(entry_path)
                os.symlink(correct_executable, entry_path)
                repaired = True
                logger.info(f"Repaired symlink {entry_path} → {correct_executable}")

        # Update pyvenv.cfg
        cfg_path = os.path.join(env_path, "pyvenv.cfg")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path) as f:
                    lines = f.readlines()
                new_lines = []
                changed = False
                for line in lines:
                    if line.startswith("home = "):
                        old_home = line.strip().split(" = ", 1)[1]
                        if old_home != correct_home:
                            line = f"home = {correct_home}\n"
                            changed = True
                    elif line.startswith("executable = "):
                        old_exec = line.strip().split(" = ", 1)[1]
                        if old_exec != correct_executable:
                            line = f"executable = {correct_executable}\n"
                            changed = True
                    new_lines.append(line)
                if changed:
                    with open(cfg_path, "w") as f:
                        f.writelines(new_lines)
                    logger.info(f"Updated pyvenv.cfg for {env_name}")
                    repaired = True
            except OSError as e:
                logger.warning(f"Failed to update pyvenv.cfg for {env_name}: {e}")

        if repaired:
            logger.info(f"Repaired environment: {env_name}")

    def _repair_shebangs(self, env_path: str, env_name: str):
        """Fix shebangs in bin/ scripts that reference a wrong env path."""
        bin_dir = os.path.join(env_path, "bin")
        if not os.path.isdir(bin_dir):
            return
        correct_bin = bin_dir
        for entry in os.listdir(bin_dir):
            entry_path = os.path.join(bin_dir, entry)
            if os.path.islink(entry_path) or not os.path.isfile(entry_path):
                continue
            try:
                with open(entry_path, "rb") as f:
                    first_line = f.readline()
                if not first_line.startswith(b"#!"):
                    continue
                shebang = first_line.decode("utf-8", errors="replace").strip()
                # Only fix shebangs that reference a path ending in /bin/pythonX.Y
                # but whose directory doesn't match this env's bin dir
                if "/bin/python" not in shebang:
                    continue
                # Extract the interpreter path from the shebang
                interp = shebang[2:].strip()
                if interp.startswith(correct_bin):
                    continue  # already correct
                if os.path.exists(interp):
                    continue  # interpreter exists, no fix needed
                # Derive the correct interpreter from the basename
                basename = os.path.basename(interp)
                correct_interp = os.path.join(correct_bin, basename)
                if not os.path.exists(correct_interp):
                    continue  # can't fix if correct interpreter doesn't exist
                with open(entry_path, "rb") as f:
                    content = f.read()
                content = content.replace(
                    interp.encode(), correct_interp.encode()
                )
                with open(entry_path, "wb") as f:
                    f.write(content)
                logger.info(f"Fixed shebang in {entry_path}: {interp} → {correct_interp}")
            except OSError:
                pass

    def _validate_name(self, name: str):
        if ".." in name or "/" in name or "\\" in name or not name:
            raise ValueError("Invalid environment name")

    def _env_path(self, runtime_id: str, name: str) -> str:
        return os.path.join(self._environments_dir, runtime_id, name)

    def _apply_post_create_files(self, runtime: dict, env_path: str):
        """Install noted-managed files into a freshly created env.

        Each entry in `env_post_create_files` is a dict with:
          - src: path to the template/source file
          - dst: destination path ({env_path} placeholder resolved)
          - template (optional, default false): if true, the file
            content is read and {env_path} / {version} placeholders
            are substituted before writing. Used by the R launcher
            script which needs the R version baked in.
          - executable (optional, default false): if true, the
            destination file is made executable (chmod +x). Used by
            shell launcher scripts.
        """
        version = runtime.get("version", "")
        for entry in runtime.get("env_post_create_files") or []:
            src = entry.get("src")
            dst_template = entry.get("dst")
            if not src or not dst_template:
                continue
            dst = dst_template.replace("{env_path}", env_path)
            if not os.path.isfile(src):
                logger.warning(
                    "env_post_create_files: missing source %s for runtime %s/%s",
                    src, runtime.get("language"), version,
                )
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if entry.get("template"):
                with open(src, "r") as f:
                    content = f.read()
                content = content.replace("{env_path}", env_path)
                content = content.replace("{version}", version)
                with open(dst, "w") as f:
                    f.write(content)
            else:
                shutil.copyfile(src, dst)
            if entry.get("executable"):
                os.chmod(dst, 0o755)
            logger.info("Installed env file %s -> %s", src, dst)

    def _ensure_post_create_files(self, runtime: dict, env_path: str):
        """Lazy-generate any post_create_files that are missing or stale.

        Called from list_envs so envs created before a new
        post_create_file was added (e.g. the Rscript launcher for
        T-5.R5) get it without requiring env recreation. Also
        regenerates template-based files when the source template is
        newer than the destination (handles template upgrades like
        adding RENV_CONFIG_SYNCHRONIZED_CHECK after initial ship).
        """
        for entry in runtime.get("env_post_create_files") or []:
            dst_template = entry.get("dst")
            if not dst_template:
                continue
            dst = dst_template.replace("{env_path}", env_path)
            src = entry.get("src")
            if os.path.exists(dst):
                # For template files, check if the source is newer
                if entry.get("template") and src and os.path.isfile(src):
                    if os.path.getmtime(src) > os.path.getmtime(dst):
                        pass  # fall through to regenerate
                    else:
                        continue
                else:
                    continue
            # Missing file - generate it now using the same logic
            # as _apply_post_create_files
            src = entry.get("src")
            if not src or not os.path.isfile(src):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            version = runtime.get("version", "")
            if entry.get("template"):
                with open(src, "r") as f:
                    content = f.read()
                content = content.replace("{env_path}", env_path)
                content = content.replace("{version}", version)
                with open(dst, "w") as f:
                    f.write(content)
            else:
                shutil.copyfile(src, dst)
            if entry.get("executable"):
                os.chmod(dst, 0o755)
            logger.info("Lazy-generated missing env file %s -> %s", src, dst)

    def list_envs(self) -> list[dict]:
        envs = []
        if not os.path.exists(self._environments_dir):
            return envs
        for language in sorted(os.listdir(self._environments_dir)):
            lang_dir = os.path.join(self._environments_dir, language)
            if not os.path.isdir(lang_dir):
                continue
            # Skip un-migrated flat envs (have bin/python at top level)
            if os.path.lexists(os.path.join(lang_dir, "bin", "python")):
                continue
            for version in sorted(os.listdir(lang_dir)):
                ver_dir = os.path.join(lang_dir, version)
                if not os.path.isdir(ver_dir):
                    continue
                runtime_id = f"{language}/{version}"
                runtime = self._registry.get_runtime(runtime_id)
                for env_name in sorted(os.listdir(ver_dir)):
                    env_path = os.path.join(ver_dir, env_name)
                    if not os.path.isdir(env_path):
                        continue
                    # Lazy-generate post_create_files that are missing
                    # (e.g. the Rscript launcher for R envs created
                    # before T-5.R5 shipped). Avoids requiring users
                    # to recreate envs after an upgrade.
                    if runtime:
                        self._ensure_post_create_files(runtime, env_path)
                    envs.append({
                        "name": env_name,
                        "runtime_id": runtime_id,
                        "language": language,
                        "version": version,
                        "display_name": runtime["display_name"] if runtime else f"{language} {version}",
                    })
        return envs

    async def create_env(self, runtime_id: str, name: str,
                         requirements: Optional[list[str]] = None) -> dict:
        self._validate_name(name)
        runtime = self._registry.get_runtime(runtime_id)
        if not runtime:
            raise ValueError(f"Unknown runtime: {runtime_id}")

        env_path = self._env_path(runtime_id, name)
        if os.path.exists(env_path):
            raise FileExistsError(f"Environment already exists: {name}")

        os.makedirs(os.path.dirname(env_path), exist_ok=True)

        # Run create command
        create_cmd = self._registry.resolve_template(
            runtime["env_create_cmd"],
            executable=runtime["executable"],
            env_path=env_path,
        )
        proc = await asyncio.create_subprocess_exec(
            *create_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            if os.path.exists(env_path):
                shutil.rmtree(env_path)
            raise RuntimeError(f"Failed to create environment: {stderr.decode()}")

        # Run post-create commands (e.g., install ipykernel)
        for post_cmd_template in runtime.get("env_post_create_cmds", []):
            post_cmd = self._registry.resolve_template(
                post_cmd_template,
                executable=runtime["executable"],
                env_path=env_path,
            )
            proc = await asyncio.create_subprocess_exec(
                *post_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                shutil.rmtree(env_path)
                raise RuntimeError(f"Post-create step failed: {stderr.decode()}")

        # Copy noted-managed files into the env (e.g. R's .Rprofile)
        try:
            self._apply_post_create_files(runtime, env_path)
        except OSError as e:
            shutil.rmtree(env_path)
            raise RuntimeError(f"Failed to install env file: {e}")

        # Install additional packages if requested
        if requirements:
            await self.install_packages(runtime_id, name, requirements)

        return {"name": name, "runtime_id": runtime_id, "created": True}

    async def create_env_stream(self, runtime_id: str, name: str):
        """Create an environment with streaming output via PTY."""
        self._validate_name(name)
        runtime = self._registry.get_runtime(runtime_id)
        if not runtime:
            raise ValueError(f"Unknown runtime: {runtime_id}")

        env_path = self._env_path(runtime_id, name)
        if os.path.exists(env_path):
            raise FileExistsError(f"Environment already exists: {name}")

        os.makedirs(os.path.dirname(env_path), exist_ok=True)

        import pty, subprocess, struct, fcntl, termios

        async def _run_with_pty(cmd, step_label):
            yield f"\x1b[1m> {step_label}\x1b[0m\r\n"
            master_fd, slave_fd = pty.openpty()
            winsize = struct.pack('HHHH', 24, 120, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
            clean_env = {k: v for k, v in os.environ.items()
                         if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
            clean_env.update({"PYTHONUNBUFFERED": "1", "TERM": "xterm-256color",
                              "SETUPTOOLS_USE_DISTUTILS": "stdlib",
                              "UV_LINK_MODE": "copy"})
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=slave_fd, stderr=slave_fd,
                stdin=subprocess.DEVNULL,
                env=clean_env,
            )
            os.close(slave_fd)
            loop = asyncio.get_event_loop()
            try:
                while True:
                    try:
                        chunk = await loop.run_in_executor(
                            None, lambda: os.read(master_fd, 4096)
                        )
                        if not chunk:
                            break
                        yield chunk.decode(errors="replace")
                    except OSError:
                        break
                await proc.wait()
                if proc.returncode != 0:
                    yield f"\r\n\x1b[31m[ERROR] Step failed with code {proc.returncode}\x1b[0m\r\n"
                    raise RuntimeError(f"Step failed: {step_label}")
            finally:
                os.close(master_fd)

        try:
            # Create venv
            create_cmd = self._registry.resolve_template(
                runtime["env_create_cmd"],
                executable=runtime["executable"],
                env_path=env_path,
            )
            async for chunk in _run_with_pty(create_cmd, " ".join(create_cmd)):
                yield chunk

            # Post-create commands
            for post_cmd_template in runtime.get("env_post_create_cmds", []):
                post_cmd = self._registry.resolve_template(
                    post_cmd_template,
                    executable=runtime["executable"],
                    env_path=env_path,
                )
                async for chunk in _run_with_pty(post_cmd, " ".join(post_cmd)):
                    yield chunk

            # Copy noted-managed files into the env (e.g. R's .Rprofile)
            try:
                self._apply_post_create_files(runtime, env_path)
            except OSError as e:
                yield f"\r\n\x1b[31m[ERROR] Failed to install env file: {e}\x1b[0m\r\n"
                raise RuntimeError(f"Failed to install env file: {e}")

            yield "\r\n\x1b[32m[Done] Environment created successfully.\x1b[0m\r\n"
        except RuntimeError:
            # Cleanup on failure
            if os.path.exists(env_path):
                shutil.rmtree(env_path)
            return

    async def delete_env(self, runtime_id: str, name: str) -> dict:
        self._validate_name(name)
        # Cancel any running install before deleting
        await self.cancel_install(runtime_id, name)
        env_path = self._env_path(runtime_id, name)
        if not os.path.exists(env_path):
            raise FileNotFoundError(f"Environment not found: {name}")
        shutil.rmtree(env_path)
        return {"name": name, "runtime_id": runtime_id, "deleted": True}

    def get_kernel_cmd(self, runtime_id: str, name: str) -> tuple[list[str], str]:
        """Returns (kernel_cmd, kernel_language) for starting a kernel."""
        runtime = self._registry.get_runtime(runtime_id)
        if not runtime:
            raise ValueError(f"Unknown runtime: {runtime_id}")
        env_path = self._env_path(runtime_id, name)
        if not os.path.exists(env_path):
            raise FileNotFoundError(f"Environment not found: {name}")
        kernel_cmd = self._registry.resolve_template(
            runtime["kernel_cmd"],
            env_path=env_path,
            executable=runtime["executable"],
        )
        return kernel_cmd, runtime["kernel_language"]

    # ── Package management ──────────────────────────────────────────
    # These methods are thin dispatchers over per-language strategies in
    # app.managers.package_managers. Adding a new language means writing a
    # BasePackageManager subclass and registering it - no changes here.

    def _make_pm_context(self, runtime_id: str, name: str):
        """Build a PmContext for a (runtime_id, env_name) pair.

        Resolves the runtime spec, validates the env exists, and binds the
        template resolver and process registration callbacks for the
        selected env. Returns (manager, context).
        """
        from app.managers.package_managers import PmContext, get_package_manager

        runtime = self._registry.get_runtime(runtime_id)
        if not runtime or "package_manager" not in runtime:
            raise ValueError(f"No package manager for runtime: {runtime_id}")
        env_path = self._env_path(runtime_id, name)
        if not os.path.exists(env_path):
            raise FileNotFoundError(f"Environment not found: {name}")

        manager = get_package_manager(runtime.get("language", ""))
        if manager is None:
            raise ValueError(
                f"No package manager strategy for language: {runtime.get('language')}"
            )

        proc_key = f"{runtime_id}:{name}"

        def _resolve_template(template):
            return self._registry.resolve_template(
                template,
                env_path=env_path,
                executable=runtime["executable"],
            )

        def _register(proc):
            self._install_procs[proc_key] = proc

        def _unregister(proc):
            current = self._install_procs.get(proc_key)
            if current is proc:
                self._install_procs.pop(proc_key, None)

        ctx = PmContext(
            runtime=runtime,
            env_path=env_path,
            resolve_template=_resolve_template,
            register_proc=_register,
            unregister_proc=_unregister,
        )
        return manager, ctx

    async def list_packages(self, runtime_id: str, name: str) -> list[dict]:
        manager, ctx = self._make_pm_context(runtime_id, name)
        return await manager.list_packages(ctx)

    async def install_packages(self, runtime_id: str, name: str,
                               packages: list[str],
                               installer: str = "uv") -> dict:
        manager, ctx = self._make_pm_context(runtime_id, name)
        return await manager.install_packages(ctx, packages, installer=installer)

    async def install_packages_stream(self, runtime_id: str, name: str,
                                       packages: list[str],
                                       installer: str = "uv"):
        """Yield install output lines as they happen.

        Args:
            installer: "uv" (default, fast) or "pip" (classic). Strategy
                implementations may ignore the value if their language has
                a single canonical installer.
        """
        manager, ctx = self._make_pm_context(runtime_id, name)
        async for chunk in manager.install_stream(ctx, packages, installer=installer):
            yield chunk

    async def cancel_install(self, runtime_id: str, name: str) -> bool:
        proc_key = f"{runtime_id}:{name}"
        proc = self._install_procs.get(proc_key)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            return True
        return False

    async def remove_packages(self, runtime_id: str, name: str,
                              packages: list[str]) -> dict:
        manager, ctx = self._make_pm_context(runtime_id, name)
        return await manager.remove_packages(ctx, packages)
