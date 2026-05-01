# noted - Projects/Mounts Unification Plan

## Document Information

| Field         | Value                              |
|---------------|-------------------------------------|
| Document      | Projects/Mounts Unification Plan    |
| Project       | noted - Integrated MLOps Platform   |
| Version       | 1.0                                 |
| Date          | 2026-04-02                          |
| Status        | In Progress                         |

---

## 1. Purpose

Merge the separate "Projects" and "Mounts" concepts into a single "Projects" system. Every project is a directory on the filesystem, whether it comes from `data/projects/` or a host bind mount. The `__mount__:` prefix is eliminated entirely.

---

## 2. Current State

### Two parallel systems:

| Aspect | Projects | Mounts |
|---|---|---|
| Storage | `data/projects/<id>/` | Docker bind mount to `/app/mounts/<name>/` |
| ID format | `"myproject"` | `"__mount__:mount_name"` |
| Configuration | Filesystem (create dir) | `NOTED.md` YAML + docker-compose.mounts.yml |
| Explorer section | `root-projects` | `root-mounts` |
| Node keys | `project:`, `pdir:`, `pfile:` | `mount:`, `mdir:`, `mfile:` |
| Tree icon | clipboard-list | hard-drive |

### The `__mount__:` prefix appears ~97 times across the codebase.

### What's already unified (works the same for both):
- File CRUD (FileManager abstraction)
- Notebook operations (handles prefix transparently)
- Git operations (path resolution)
- DVC operations (uses git pattern)
- Kernel association (path resolution)
- Snapshots (path resolution)

### What's different:
- Explorer tree structure (two sections, different node keys)
- Detail views (separate functions)
- Context menus (different action sets)
- Project creation (dir vs config edit)
- File router URLs (`/api/files/{root_type}/{root_name}`)
- LLM tool paths (`__mount__:name/path` vs `name/path`)

---

## 3. Target State

### Single "Projects" section in Explorer

Every directory that noted knows about is a "project". Sources:
1. Directories in `data/projects/` (internal projects)
2. Host directories declared in `NOTED.md` (mounted projects)

Both appear in the same tree under "Projects" with the same icon, same context menu, same detail view.

### No `__mount__:` prefix anywhere

Project IDs are just names: `"Examples"`, `"jena_weather"`, `"my_project"`. The backend resolves the filesystem path through a registry.

### Single file API

`GET /api/files/{project_id}/read?path=src/train.py` - no `root_type` parameter.

### LLM tools

`get_file_contents({path: "jena_weather/src/train.py"})` - just project name + relative path.

---

## 4. Implementation Phases

### Phase 1: Backend - ProjectRegistry

**New file: `backend/app/managers/project_registry.py`**

```python
class ProjectRegistry:
    """Unified project path resolution.
    
    Scans data/projects/ and NOTED.md mounts on startup.
    Provides a single resolve(project_id) -> filesystem path.
    """
    
    _projects: dict[str, str]  # name -> absolute filesystem path
    
    def resolve(self, project_id: str) -> str:
        """Resolve project ID to filesystem path. Raises if not found."""
    
    def list_projects(self) -> list[dict]:
        """Return all projects with metadata (name, path, source)."""
    
    def is_internal(self, project_id: str) -> bool:
        """True if project is in data/projects/ (not a mount)."""
    
    def refresh(self):
        """Re-scan sources (called after NOTED.md changes)."""
```

**Update managers to use registry:**

| Manager | Change |
|---|---|
| `notebook_manager.py` | Remove `_is_mount()`, `_mount_name()`, `_project_root()`. Use `registry.resolve(project_id)` |
| `file_manager.py` | Remove `root_type` parameter from all methods. Use `registry.resolve(project_id)` |
| `git_manager.py` | Remove `__mount__:` prefix check in `_project_path()`. Use registry |
| `kernel_manager.py` | Remove prefix check for CWD (lines 72-82). Use registry |
| `snapshot_manager.py` | Remove `_resolve_project_path()` prefix check. Use registry |
| `dvc_manager.py` | Remove prefix check. Use registry |
| `hydra_manager.py` | Remove prefix check if present. Use registry |
| `config_manager.py` | `generate_compose_mounts_file()` reads from registry |

**Update file router:**

| Before | After |
|---|---|
| `GET /api/files/{root_type}/{root_name}` | `GET /api/files/{project_id}` |
| `GET /api/files/{root_type}/{root_name}/read?path=...` | `GET /api/files/{project_id}/read?path=...` |
| `PUT /api/files/{root_type}/{root_name}/write?path=...` | `PUT /api/files/{project_id}/write?path=...` |
| `POST /api/files/{root_type}/{root_name}` | `POST /api/files/{project_id}` |
| `DELETE /api/files/{root_type}/{root_name}` | `DELETE /api/files/{project_id}` |

**Update LLM tools:**

| Tool | Before | After |
|---|---|---|
| `get_file_contents` | `path: "__mount__:jena_weather/src/train.py"` | `path: "jena_weather/src/train.py"` |
| `list_files` | `project_id: "__mount__:jena_weather"` | `project_id: "jena_weather"` |
| `search_files` | `project_id: "__mount__:jena_weather"` | `project_id: "jena_weather"` |
| `update_file` | Uses ctx with `__mount__:` | Uses ctx with clean name |

### Phase 2: Frontend - Merged tree

**ExplorerPanel.js:**
- Remove `root-mounts` from `treeData`
- Merge mount children into `root-projects` children
- Remove all `mount:`, `mdir:`, `mfile:` key handling
- Update `_onTreeClick`, `_onTreeActivate`, `_onTreeRender` to not differentiate
- Remove `_parseFileKey` mount handling

**ExplorerProjectViews.js:**
- Remove `showMountsRootDetail()` and `showMountDetail()`
- `showProjectDetail()` handles all projects (show host_path info for mounts if relevant)

**ExplorerContextMenu.js:**
- Remove `root-mounts` and `mount:` branches
- Same context menu for all projects (create notebook, terminal, git ops)
- "Delete Project" available for internal projects only (mounts can only be "unmounted" via config)

**app.js:**
- Remove `__mount__:` prefix construction when opening notebooks/files
- Clean `project_id` everywhere - just the name

**FileEditor.js:**
- Remove `__mount__:` handling in `_isMount()`, `_mountName()`

**Other frontend files:**
- `ChatService.js` - context descriptor uses clean names
- `NotebookEditor.js` - project_id is clean name
- All fetch URLs use `/api/files/{project_id}/...` instead of `/api/files/mount/{name}/...`

### Phase 3: Cleanup

- Remove `MOUNT_PREFIX` constant from `notebook_manager.py`
- Remove `MOUNTS_DIR` constant (registry handles paths)
- Remove all `__mount__:` string literals from codebase
- Update `docker-compose.mounts.yml` generation (still needed for Docker volumes, but project IDs are clean)
- Update LLM tool descriptions
- Update `python-linting` skill
- Update explorer guidelines document
- Run all tests

---

## 5. Migration Safety

### Backwards compatibility during migration:
- `ProjectRegistry.resolve()` handles both old (`__mount__:name`) and new (`name`) formats during transition
- File router keeps old URLs working temporarily with redirects
- Frontend changes can be done atomically (one commit that switches everything)

### What must NOT break:
- Opening existing notebooks (saved with `__mount__:` in URLs/metadata)
- Git/DVC operations on mounted projects
- Kernel association and PYTHONPATH injection
- LLM context (project_id in context descriptor)
- Airflow DAG discovery (compose mounts file)
- Knowledge Graph scanning (mount paths)

### Testing checklist:
- [ ] Open notebook from internal project
- [ ] Open notebook from mounted project
- [ ] Create/save/delete files in both
- [ ] Git status/commit in both
- [ ] DVC track/push in both
- [ ] Kernel starts with correct CWD for both
- [ ] LLM can read files from both
- [ ] LLM can edit files in both
- [ ] Explorer tree shows all projects in one section
- [ ] Context menus work for all projects
- [ ] Airflow discovers DAGs from mounted projects
- [ ] Knowledge Graph scans mounted projects

---

## 6. Files to Modify

### Backend (Python) - Phase 1

| File | Changes | Effort |
|---|---|---|
| `backend/app/managers/project_registry.py` | **NEW** - unified project registry | M |
| `backend/app/managers/notebook_manager.py` | Remove prefix logic, use registry | S |
| `backend/app/managers/file_manager.py` | Remove root_type, use registry | S |
| `backend/app/managers/git_manager.py` | Remove prefix check | S |
| `backend/app/managers/kernel_manager.py` | Remove prefix check | S |
| `backend/app/managers/snapshot_manager.py` | Remove prefix check | S |
| `backend/app/managers/dvc_manager.py` | Remove prefix check | S |
| `backend/app/managers/config_manager.py` | Update mount management | S |
| `backend/app/routers/files.py` | New URL pattern | M |
| `backend/app/routers/notebooks.py` | Remove prefix handling | S |
| `backend/app/managers/llm_tools.py` | Update tool descriptions, path resolution | S |
| `backend/app/managers/llm_context.py` | Remove __mount__ from context | S |
| `backend/app/main.py` | Initialize registry, inject into managers | S |

### Frontend (JavaScript) - Phase 2

| File | Changes | Effort |
|---|---|---|
| `frontend/js/panels/ExplorerPanel.js` | Merge tree sections, remove mount keys | L |
| `frontend/js/panels/explorer/ExplorerProjectViews.js` | Merge detail views | M |
| `frontend/js/panels/explorer/ExplorerContextMenu.js` | Merge context menus | S |
| `frontend/js/app.js` | Remove __mount__ prefix construction | M |
| `frontend/js/FileEditor.js` | Remove _isMount(), _mountName() | S |
| `frontend/js/ChatService.js` | Clean context descriptor | S |
| `frontend/js/NotebookEditor.js` | Clean project_id handling | S |

**Total estimated effort: 2-3 days**
