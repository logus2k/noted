import os
from app.config import PROJECTS_DIR


class SourceFileManager:
    """Handles CRUD operations for Python source files in project src/ directories."""

    def _project_src_dir(self, project_id: str) -> str:
        return os.path.join(PROJECTS_DIR, project_id, "src")

    def _file_path(self, project_id: str, filename: str) -> str:
        return os.path.join(self._project_src_dir(project_id), filename)

    def _validate_filename(self, name: str) -> str:
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("Invalid filename")
        if not name.endswith(".py"):
            name += ".py"
        return name

    def _validate_project(self, project_id: str):
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project ID")

    def _secure_path(self, project_id: str, filename: str) -> str:
        """Resolve and verify the path stays within the project src/ dir."""
        full = os.path.realpath(self._file_path(project_id, filename))
        src_dir = os.path.realpath(self._project_src_dir(project_id))
        if not full.startswith(src_dir + os.sep) and full != src_dir:
            raise ValueError("Path traversal denied")
        return full

    def list_files(self, project_id: str) -> list[dict]:
        self._validate_project(project_id)
        src_dir = self._project_src_dir(project_id)
        if not os.path.exists(src_dir):
            return []
        files = []
        for name in sorted(os.listdir(src_dir)):
            if name.endswith(".py"):
                filepath = os.path.join(src_dir, name)
                stat = os.stat(filepath)
                files.append({
                    "name": name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
        return files

    def get_file(self, project_id: str, filename: str) -> dict:
        self._validate_project(project_id)
        filename = self._validate_filename(filename)
        filepath = self._secure_path(project_id, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filename}")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        stat = os.stat(filepath)
        return {
            "name": filename,
            "content": content,
            "size": stat.st_size,
            "modified": stat.st_mtime,
        }

    def create_file(self, project_id: str, filename: str) -> dict:
        self._validate_project(project_id)
        filename = self._validate_filename(filename)
        src_dir = self._project_src_dir(project_id)
        os.makedirs(src_dir, exist_ok=True)
        filepath = self._secure_path(project_id, filename)
        if os.path.exists(filepath):
            raise FileExistsError(f"File already exists: {filename}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("")
        return {"name": filename, "created": True}

    def update_file(self, project_id: str, filename: str, content: str) -> dict:
        self._validate_project(project_id)
        filename = self._validate_filename(filename)
        filepath = self._secure_path(project_id, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filename}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"name": filename, "updated": True}

    def delete_file(self, project_id: str, filename: str) -> dict:
        self._validate_project(project_id)
        filename = self._validate_filename(filename)
        filepath = self._secure_path(project_id, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filename}")
        os.remove(filepath)
        return {"name": filename, "deleted": True}

    def rename_file(self, project_id: str, filename: str, new_name: str) -> dict:
        self._validate_project(project_id)
        filename = self._validate_filename(filename)
        new_name = self._validate_filename(new_name)
        old_path = self._secure_path(project_id, filename)
        new_path = self._secure_path(project_id, new_name)
        if not os.path.exists(old_path):
            raise FileNotFoundError(f"File not found: {filename}")
        if os.path.exists(new_path):
            raise FileExistsError(f"File already exists: {new_name}")
        os.rename(old_path, new_path)
        return {"old_name": filename, "new_name": new_name, "renamed": True}
