"""Generic filesystem manager for browsing and manipulating files/folders.

Supports two root types:
  - projects:  DATA_DIR/projects/<project_id>/
  - mounts:    DATA_DIR/mounts/<mount_name>/

All paths are validated to stay within their respective root.
"""

import mimetypes
import os
import shutil
import subprocess

from app.config import DATA_DIR, PROJECTS_DIR, MOUNTS_DIR

# File extensions recognised as notebooks
NOTEBOOK_EXTENSIONS = {".ipynb"}

# Binary extensions that should not be read/written as text
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".whl", ".pyc", ".pyo", ".so", ".dll", ".exe",
    ".parquet", ".feather", ".h5", ".hdf5",
    ".mp3", ".wav", ".mp4", ".avi", ".mov",
    ".pickle", ".pkl",
}


_ICON_NAME_MAP = {
    "dockerfile": "dockerfile", "makefile": "makefile",
    "cmakelists.txt": "cmake",
    ".env": "env", ".env.local": "env", ".env.production": "env",
    ".env.development": "env", ".env.test": "env",
    "license": "license", "license.md": "license", "license.txt": "license",
    "readme.md": "readme", "readme.txt": "readme", "readme": "readme",
    "changelog.md": "changelog", "changelog": "changelog",
    "contributing.md": "contributing", "contributing": "contributing",
    "requirements.txt": "pip", "setup.py": "pip", "setup.cfg": "pip",
    "pipfile": "pip", "pyproject.toml": "pip",
    "package.json": "npm", "package-lock.json": "npm",
    "yarn.lock": "yarn", ".yarnrc": "yarn",
    "nginx.conf": "nginx",
    ".gitignore": "git", ".gitattributes": "git", ".gitmodules": "git",
    "tsconfig.json": "tsconfig", "jsconfig.json": "tsconfig",
    ".babelrc": "babel", "babel.config.js": "babel",
    ".eslintrc": "eslint", ".eslintrc.js": "eslint", ".eslintrc.json": "eslint",
    ".prettierrc": "prettier", ".prettierrc.js": "prettier",
    ".editorconfig": "editorconfig",
    "webpack.config.js": "webpack",
    "vite.config.js": "vite", "vite.config.ts": "vite",
    "rollup.config.js": "rollup",
    "jest.config.js": "jest", "jest.config.ts": "jest",
    ".gitlab-ci.yml": "gitlab",
    "jenkinsfile": "jenkins", "vagrantfile": "vagrant",
}

_ICON_EXT_MAP = {
    # Notebooks & data science
    ".py": "python_color", ".pyi": "python_color", ".pyx": "python_color",
    ".ipynb": "notebook", ".r": "r", ".rmd": "r", ".jl": "julia",
    ".m": "matlab", ".mat": "matlab",
    # Documents
    ".pdf": "pdf", ".md": "markdown", ".txt": "text", ".rst": "text",
    ".tex": "latex", ".bib": "latex", ".log": "log",
    # Data formats
    ".csv": "csv", ".tsv": "csv",
    ".json": "json", ".jsonc": "json", ".json5": "json",
    ".xml": "xml", ".xsl": "xml", ".xslt": "xml", ".xsd": "xml",
    ".graphql": "graphql", ".gql": "graphql",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".cfg": "config", ".ini": "config", ".conf": "config", ".properties": "config",
    ".proto": "protobuf",
    ".sql": "sql", ".sqlite": "sqlite", ".db": "sqlite",
    ".prisma": "prisma", ".plist": "plist",
    # Web
    ".html": "html", ".htm": "html", ".xhtml": "html",
    ".ejs": "ejs", ".pug": "pug", ".jade": "pug",
    ".hbs": "handlebars",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".styl": "stylus",
    ".js": "javascript_color", ".jsx": "react", ".mjs": "javascript_color", ".cjs": "javascript_color",
    ".ts": "typescript", ".tsx": "react", ".mts": "typescript",
    ".vue": "vue", ".svelte": "svelte",
    ".wasm": "wasm", ".wat": "wasm",
    # Shell & scripting
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".fish": "shell",
    ".ps1": "powershell", ".psm1": "powershell",
    ".bat": "bat", ".cmd": "bat",
    ".lua": "lua", ".pl": "perl", ".pm": "perl", ".rb": "ruby",
    ".php": "php",
    # Compiled languages
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
    ".cs": "csharp",
    ".java": "java", ".jar": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".go": "go", ".rs": "rust", ".swift": "swift",
    ".hs": "haskell", ".lhs": "haskell",
    ".cu": "cuda", ".cuh": "cuda",
    ".dart": "dart",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang", ".hrl": "erlang",
    ".clj": "clojure", ".cljs": "clojure", ".cljc": "clojure",
    ".fs": "fsharp", ".fsi": "fsharp", ".fsx": "fsharp",
    ".ml": "ocaml", ".mli": "ocaml",
    ".zig": "zig", ".nim": "nim",
    ".asm": "assembly", ".s": "assembly",
    ".mm": "objectivecpp",
    ".groovy": "groovy", ".gradle": "groovy",
    ".f90": "fortran", ".f95": "fortran", ".f03": "fortran",
    ".cob": "cobol", ".cbl": "cobol",
    ".vb": "vb", ".vbs": "vb",
    # Infrastructure
    ".tf": "terraform", ".tfvars": "terraform",
    # Images
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".webp": "image", ".bmp": "image", ".ico": "image",
    ".svg": "svg",
    # Media
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".flac": "audio",
    ".mp4": "video", ".avi": "video", ".mkv": "video", ".mov": "video", ".webm": "video",
    # Fonts
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
    # Archives
    ".zip": "zip", ".tar": "zip", ".gz": "zip", ".bz2": "zip", ".xz": "zip",
    ".7z": "zip", ".rar": "zip", ".whl": "zip", ".egg": "zip",
    # Security
    ".pem": "cert", ".crt": "cert", ".cer": "cert",
    ".key": "key", ".p12": "key", ".pfx": "key",
    # Binary
    ".bin": "binary", ".so": "binary", ".dll": "binary", ".dylib": "binary",
    ".o": "binary", ".a": "binary", ".pyc": "binary", ".pyo": "binary",
    ".exe": "binary",
    # DVC
    ".dvc": "dvc",
    # Env
    ".env": "env",
}


def _icon_for_entry(name: str, is_dir: bool) -> str:
    """Return an icon key that maps to static/vendor/icons/{key}.svg."""
    if is_dir:
        return "folder"
    lower_name = name.lower()
    # Check special filenames first
    icon = _ICON_NAME_MAP.get(lower_name)
    if icon:
        return icon
    # Dockerfile variants (Dockerfile.prod, etc.)
    if lower_name.startswith("dockerfile"):
        return "dockerfile"
    ext = os.path.splitext(name)[1].lower()
    return _ICON_EXT_MAP.get(ext, "file")


class FileManager:
    """Generic file operations scoped to projects and mounts."""

    # ── Path resolution ──────────────────────────────────────────────

    def _resolve_root(self, root_type: str, root_name: str) -> str:
        """Resolve and validate a root directory."""
        if ".." in root_name or "/" in root_name or "\\" in root_name:
            raise ValueError(f"Invalid name: {root_name}")

        if root_type == "project":
            base = os.path.join(PROJECTS_DIR, root_name)
        elif root_type == "mount":
            base = os.path.join(MOUNTS_DIR, root_name)
        else:
            raise ValueError(f"Invalid root type: {root_type}")

        if not os.path.isdir(base):
            raise FileNotFoundError(f"Root not found: {root_type}/{root_name}")
        return os.path.realpath(base)

    def _secure_path(self, root: str, rel_path: str) -> str:
        """Resolve a relative path within a root, preventing traversal."""
        if rel_path in ("", ".", "/"):
            return root
        # Normalize but don't resolve symlinks yet — just clean the path
        joined = os.path.normpath(os.path.join(root, rel_path))
        real = os.path.realpath(joined)
        real_root = os.path.realpath(root)
        if real != real_root and not real.startswith(real_root + os.sep):
            raise ValueError("Path traversal denied")
        return real

    # ── List directory contents (for lazy loading) ───────────────────

    def list_dir(self, root_type: str, root_name: str,
                 rel_path: str = "") -> list[dict]:
        """List immediate children of a directory.
        Returns sorted list: folders first, then files, both alphabetical.
        """
        root = self._resolve_root(root_type, root_name)
        target = self._secure_path(root, rel_path)

        if not os.path.isdir(target):
            raise FileNotFoundError(f"Directory not found: {rel_path}")

        entries = []
        try:
            names = os.listdir(target)
        except PermissionError:
            return []

        for name in names:
            full = os.path.join(target, name)
            # Skip directory symlinks to avoid duplicate tree keys
            if os.path.islink(full) and os.path.isdir(full):
                continue
            is_dir = os.path.isdir(full)
            try:
                st = os.stat(full)
            except OSError:
                continue
            entry = {
                "name": name,
                "path": os.path.relpath(full, root),
                "is_dir": is_dir,
                "size": st.st_size if not is_dir else None,
                "modified": st.st_mtime,
                "icon": _icon_for_entry(name, is_dir),
            }
            if is_dir:
                # Check if directory has children (for lazy expansion indicator)
                try:
                    has_children = any(
                        not n.startswith(".")
                        for n in os.listdir(full)
                    )
                except (PermissionError, OSError):
                    has_children = False
                entry["has_children"] = has_children
            entries.append(entry)

        # Sort: folders first (alphabetical), then files (alphabetical)
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return entries

    # ── Read file ────────────────────────────────────────────────────

    def read_file(self, root_type: str, root_name: str,
                  rel_path: str) -> dict:
        """Read a file's content. Returns text content for text files,
        base64 for binary, or raw dict for notebooks."""
        root = self._resolve_root(root_type, root_name)
        filepath = self._secure_path(root, rel_path)

        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"File not found: {rel_path}")

        name = os.path.basename(filepath)
        ext = os.path.splitext(name)[1].lower()
        st = os.stat(filepath)

        result = {
            "name": name,
            "path": os.path.relpath(filepath, root),
            "size": st.st_size,
            "modified": st.st_mtime,
        }

        if ext in BINARY_EXTENSIONS:
            import base64
            with open(filepath, "rb") as f:
                result["content"] = base64.b64encode(f.read()).decode("ascii")
            result["encoding"] = "base64"
            result["mime"] = mimetypes.guess_type(name)[0] or "application/octet-stream"
        elif ext in NOTEBOOK_EXTENSIONS:
            import json
            with open(filepath, "r", encoding="utf-8") as f:
                result["content"] = json.load(f)
            result["encoding"] = "notebook"
        else:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                result["content"] = f.read()
            result["encoding"] = "text"

        return result

    # ── Write / update file ──────────────────────────────────────────

    def write_file(self, root_type: str, root_name: str,
                   rel_path: str, content: str) -> dict:
        """Write text content to a file. Creates parent dirs if needed."""
        root = self._resolve_root(root_type, root_name)
        filepath = self._secure_path(root, rel_path)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "path": os.path.relpath(filepath, root),
            "written": True,
        }

    # ── Create file or folder ────────────────────────────────────────

    def create(self, root_type: str, root_name: str,
               rel_path: str, is_dir: bool = False,
               content: str = "") -> dict:
        """Create a new file or directory."""
        root = self._resolve_root(root_type, root_name)
        filepath = self._secure_path(root, rel_path)

        if os.path.exists(filepath):
            raise FileExistsError(f"Already exists: {rel_path}")

        if is_dir:
            os.makedirs(filepath, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            ext = os.path.splitext(filepath)[1].lower()
            if ext in NOTEBOOK_EXTENSIONS:
                import json
                import uuid
                notebook = {
                    "nbformat": 4,
                    "nbformat_minor": 5,
                    "metadata": {
                        "kernelspec": {
                            "display_name": "Python 3",
                            "language": "python",
                            "name": "python3"
                        },
                        "language_info": {"name": "python", "version": "3.10.0"},
                    },
                    "cells": [{
                        "cell_type": "code",
                        "id": str(uuid.uuid4())[:8],
                        "metadata": {},
                        "source": [],
                        "outputs": [],
                        "execution_count": None,
                    }]
                }
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(notebook, f, indent=2)
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

        return {
            "path": os.path.relpath(filepath, root),
            "is_dir": is_dir,
            "created": True,
        }

    # ── Delete file or folder ────────────────────────────────────────

    def delete(self, root_type: str, root_name: str,
               rel_path: str) -> dict:
        """Delete a file or directory (recursively)."""
        root = self._resolve_root(root_type, root_name)
        filepath = self._secure_path(root, rel_path)

        # Don't allow deleting the root itself
        if os.path.realpath(filepath) == os.path.realpath(root):
            raise ValueError("Cannot delete root directory")

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Not found: {rel_path}")

        if os.path.isdir(filepath):
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)

        return {"path": rel_path, "deleted": True}

    # ── Rename / move ────────────────────────────────────────────────

    def rename(self, root_type: str, root_name: str,
               rel_path: str, new_name: str) -> dict:
        """Rename a file or folder (same parent directory)."""
        root = self._resolve_root(root_type, root_name)
        filepath = self._secure_path(root, rel_path)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Not found: {rel_path}")

        if ".." in new_name or "/" in new_name or "\\" in new_name:
            raise ValueError(f"Invalid name: {new_name}")

        parent = os.path.dirname(filepath)
        new_path = os.path.join(parent, new_name)
        # Validate new path stays within root
        self._secure_path(root, os.path.relpath(new_path, root))

        if os.path.exists(new_path):
            raise FileExistsError(f"Already exists: {new_name}")

        os.rename(filepath, new_path)
        return {
            "old_path": rel_path,
            "new_path": os.path.relpath(new_path, root),
            "renamed": True,
        }

    # ── Git repo discovery ───────────────────────────────────────────

    def discover_git_repos(self, max_depth: int = 3) -> list[dict]:
        """Scan projects and mounts for .git directories.
        Returns list of {path, root_type, root_name, rel_path, has_changes}.
        """
        repos = []

        for root_type, base_dir in [("project", PROJECTS_DIR), ("mount", MOUNTS_DIR)]:
            if not os.path.isdir(base_dir):
                continue
            for root_name in sorted(os.listdir(base_dir)):
                root_path = os.path.join(base_dir, root_name)
                if not os.path.isdir(root_path):
                    continue
                self._scan_for_git(root_path, root_type, root_name,
                                   "", 0, max_depth, repos)
        return repos

    def _scan_for_git(self, path: str, root_type: str, root_name: str,
                      rel_path: str, depth: int, max_depth: int,
                      repos: list):
        """Recursively scan for .git directories."""
        git_dir = os.path.join(path, ".git")
        if os.path.isdir(git_dir):
            has_changes = False
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=path, capture_output=True, text=True, timeout=5
                )
                has_changes = bool(result.stdout.strip())
            except Exception:
                pass
            repos.append({
                "abs_path": path,
                "root_type": root_type,
                "root_name": root_name,
                "rel_path": rel_path or ".",
                "label": root_name if not rel_path else f"{root_name}/{rel_path}",
                "has_changes": has_changes,
            })
            # Don't recurse into git repos (nested repos are rare)
            return

        if depth >= max_depth:
            return

        try:
            for name in os.listdir(path):
                if name.startswith("."):
                    continue
                child = os.path.join(path, name)
                if os.path.isdir(child):
                    child_rel = os.path.join(rel_path, name) if rel_path else name
                    self._scan_for_git(child, root_type, root_name,
                                       child_rel, depth + 1, max_depth, repos)
        except PermissionError:
            pass

    # ── List mounts ──────────────────────────────────────────────────

    def list_mounts(self) -> list[dict]:
        """List all mount directories."""
        if not os.path.isdir(MOUNTS_DIR):
            return []
        mounts = []
        for name in sorted(os.listdir(MOUNTS_DIR)):
            path = os.path.join(MOUNTS_DIR, name)
            if os.path.isdir(path):
                mounts.append({"name": name, "path": path})
        return mounts

    # ── List projects ────────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        """List all project directories."""
        if not os.path.isdir(PROJECTS_DIR):
            return []
        projects = []
        for name in sorted(os.listdir(PROJECTS_DIR)):
            path = os.path.join(PROJECTS_DIR, name)
            if os.path.isdir(path):
                projects.append({"id": name, "path": path})
        return projects
