"""Notebook LSP Bridge - lints notebook cells via a Jupytext shadow file.

Converts a notebook's code cells into a percent-format .py script using
Jupytext, sends it to ruff via the existing LSP infrastructure, and maps
diagnostics back to individual cells.

Flow:
  1. notebook:open  -> generate shadow .py, open textDocument in ruff
  2. cell:update    -> regenerate shadow, send textDocument/didChange
  3. ruff publishes diagnostics -> map lines to cells -> emit cell:diagnostics
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Regex to detect cell markers in percent format (Python: # %%, JS: // %%)
_CELL_MARKER = re.compile(r'^(?:#|//) %%(.*)$')


class CellRegion:
    """Maps a cell to its line range in the shadow script."""
    __slots__ = ('cell_index', 'cell_type', 'start_line', 'end_line')

    def __init__(self, cell_index: int, cell_type: str, start_line: int, end_line: int):
        self.cell_index = cell_index
        self.cell_type = cell_type
        self.start_line = start_line   # 0-based, first line of cell content
        self.end_line = end_line       # 0-based, last line of cell content


class NotebookLSPBridge:
    """Manages the shadow script for a single open notebook.

    One instance per (project_id, notebook_path) pair.
    """

    def __init__(self, project_id: str, notebook_path: str, language: str = "python"):
        self.project_id = project_id
        self.notebook_path = notebook_path
        self.language = language
        # Per-language LSP needs the active env / runtime to dispatch the
        # right server (R uses these to pick the right /opt/R/<version>/).
        # Set by the caller after construction; not all languages use them.
        self.env_name: str | None = None
        self.runtime_id: str | None = None
        self._shadow_text: str = ""
        self._cell_regions: list[CellRegion] = []
        self._version: int = 0
        # In-memory cache of the latest source for each cell, keyed by
        # cell_index. Populated by update_cell on every cell:update event.
        # notebook_manager.get_notebook() reads from disk and does NOT
        # reflect unsaved cell edits, so without this cache the shadow
        # rebuild would silently revert any cell whose edit predates the
        # current one. That breaks cross-cell completion: define
        # `my_var = 1` in cell 0, type `my_v` in cell 1, jedi never sees
        # cell 0's new content because the wire_nb passed to update_cell
        # is the disk version of cell 0.
        self._latest_sources: dict[int, str] = {}
        # URI must be inside the project root for the linter to process it
        from app.managers.project_registry import get_registry
        try:
            root = get_registry().resolve(project_id)
        except Exception:
            root = f"/app/data/projects/{project_id}"
        ext_map = {"javascript": ".js", "r": ".R"}
        ext = ext_map.get(language, ".py")
        self._uri: str = f"file://{root}/{notebook_path}.nb{ext}"

    @property
    def uri(self) -> str:
        return self._uri

    @property
    def version(self) -> int:
        return self._version

    @property
    def shadow_text(self) -> str:
        return self._shadow_text

    def generate(self, notebook: dict) -> str:
        """Convert a notebook dict to a shadow script and build the line map.

        Python uses Jupytext percent format.
        JavaScript uses manual // %% markers (Jupytext does not support JS).
        R uses manual # %% markers (Jupytext support for R is limited).

        Args:
            notebook: The ipynb-format notebook dict (cells with source as strings).

        Returns:
            The shadow script text.
        """
        if self.language == "javascript":
            return self._generate_js(notebook)
        if self.language == "r":
            return self._generate_r(notebook)
        return self._generate_python(notebook)

    def _generate_python(self, notebook: dict) -> str:
        """Generate Python percent-format shadow via Jupytext."""
        import jupytext

        for cell in notebook.get("cells", []):
            for out in cell.get("outputs", []):
                out.pop("transient", None)

        nb_json = json.dumps(notebook)
        nb_obj = jupytext.reads(nb_json, fmt='ipynb')

        self._shadow_text = jupytext.writes(nb_obj, fmt='py:percent')
        self._version += 1
        self._build_cell_map()
        return self._shadow_text

    def _generate_r(self, notebook: dict) -> str:
        """Generate combined R shadow with `# %%` markers.

        R uses the same single-shadow approach as Python (one .R file with
        all cells separated by `# %%` comment markers) rather than the
        per-cell approach JS uses. languageserver handles a single file
        cleanly and combined shadows are simpler. The existing
        `_build_cell_map` already understands `# %%` markers and produces
        the right CellRegion list.
        """
        lines: list[str] = []
        for i, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "code")
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)

            tag = ""
            if cell_type == "markdown":
                tag = " [markdown]"
            elif cell_type == "raw":
                tag = " [raw]"

            lines.append(f"# %%{tag} Cell {i + 1}")
            cell_lines = source.split('\n') if source else ['']
            for cl in cell_lines:
                # Markdown / raw cells go in as comments so the linter
                # never sees them as R code
                if cell_type != "code":
                    lines.append(f"# {cl}" if cl else "#")
                else:
                    lines.append(cl)
            lines.append('')

        self._shadow_text = '\n'.join(lines)
        self._version += 1
        self._build_cell_map()
        return self._shadow_text

    def _generate_js(self, notebook: dict) -> str:
        """Generate per-cell JavaScript shadow files.

        Unlike Python (which uses a single Jupytext shadow), JS uses one
        shadow file per code cell. This prevents parse errors in one cell
        from bleeding into diagnostics for other cells.

        The per-cell files are stored in self._js_cell_shadows.
        The single shadow_text is kept for Debug All compatibility.
        """
        self._cell_regions = []
        self._js_cell_shadows = {}  # cell_index -> (uri, text, version)

        # Build per-cell shadows
        lines_all = []
        current_line = 0

        for i, cell in enumerate(notebook.get("cells", [])):
            cell_type = cell.get("cell_type", "code")
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)

            # Track in combined shadow (for Debug All)
            lines_all.append(f"// %% Cell {i + 1}")
            current_line += 1
            content_start = current_line
            cell_lines = source.split('\n') if source else ['']
            for cl in cell_lines:
                lines_all.append(cl)
                current_line += 1
            content_end = current_line - 1
            lines_all.append('')
            current_line += 1

            self._cell_regions.append(CellRegion(
                cell_index=i,
                cell_type=cell_type,
                start_line=content_start,
                end_line=content_end,
            ))

            # Per-cell shadow (for linting)
            if cell_type == "code":
                base_uri = self._uri.rsplit('.nb.', 1)[0]
                cell_uri = f"{base_uri}.nb.cell{i}.js"
                self._js_cell_shadows[i] = {
                    "uri": cell_uri,
                    "text": source,
                    "version": self._version + 1,
                }

        self._shadow_text = '\n'.join(lines_all)
        self._version += 1
        return self._shadow_text

    def update_cell(self, cell_index: int, source: str, notebook: dict) -> str:
        """Regenerate the shadow after a single cell edit.

        We regenerate the full shadow from the notebook dict with the
        updated cell source. This is simple and correct - Jupytext handles
        all edge cases.

        The notebook dict comes from notebook_manager which reads from
        disk and does NOT include in-flight edits to other cells. We
        therefore overlay self._latest_sources (populated by all prior
        update_cell calls in this session) on top of the disk view so
        cross-cell completion sees every edit, not just the current one.

        Args:
            cell_index: The index of the changed cell.
            source: The new source content.
            notebook: The full notebook dict (will be modified in place).

        Returns:
            The updated shadow text.
        """
        # Record this cell's latest source so future shadow rebuilds for
        # other cells include it.
        self._latest_sources[cell_index] = source
        cells = notebook.get("cells", [])
        # Apply every cached cell-source override on top of the disk
        # version. This makes the shadow reflect the live notebook state,
        # not the last-saved state.
        for idx, src in self._latest_sources.items():
            if 0 <= idx < len(cells):
                cells[idx]["source"] = src
        return self.generate(notebook)

    def map_diagnostics(self, diagnostics: list[dict]) -> dict[int, list[dict]]:
        """Map LSP diagnostics (global line numbers) to per-cell diagnostics.

        Args:
            diagnostics: List of LSP diagnostic objects with 'range' fields.

        Returns:
            Dict mapping cell_index -> list of diagnostics with cell-local line numbers.
        """
        per_cell: dict[int, list[dict]] = {}

        for diag in diagnostics:
            rng = diag.get("range", {})
            start_line = rng.get("start", {}).get("line", 0)  # 0-based

            region = self._find_region(start_line)
            if region is None or region.cell_type != 'code':
                continue

            # Translate to cell-local coordinates
            offset = region.start_line
            local_diag = dict(diag)
            local_range = {
                "start": {
                    "line": rng["start"]["line"] - offset,
                    "character": rng["start"].get("character", 0),
                },
                "end": {
                    "line": rng.get("end", rng["start"])["line"] - offset,
                    "character": rng.get("end", rng["start"]).get("character", 0),
                },
            }
            local_diag["range"] = local_range

            per_cell.setdefault(region.cell_index, []).append(local_diag)

        return per_cell

    def _build_cell_map(self):
        """Parse # %% markers in the shadow text to build cell regions."""
        lines = self._shadow_text.split('\n')
        self._cell_regions = []

        markers = []  # (line_index, cell_type)
        for i, line in enumerate(lines):
            m = _CELL_MARKER.match(line)
            if m:
                rest = m.group(1).strip()
                if '[markdown]' in rest or '[md]' in rest:
                    markers.append((i, 'markdown'))
                elif '[raw]' in rest:
                    markers.append((i, 'raw'))
                else:
                    markers.append((i, 'code'))

        # Build regions from marker pairs
        notebook_cell_index = 0
        for idx, (marker_line, cell_type) in enumerate(markers):
            content_start = marker_line + 1
            if idx + 1 < len(markers):
                content_end = markers[idx + 1][0] - 1
            else:
                content_end = len(lines) - 1

            # Trim trailing blank lines from region
            while content_end > content_start and not lines[content_end].strip():
                content_end -= 1

            self._cell_regions.append(CellRegion(
                cell_index=notebook_cell_index,
                cell_type=cell_type,
                start_line=content_start,
                end_line=content_end,
            ))
            notebook_cell_index += 1

    def _find_region(self, global_line: int) -> Optional[CellRegion]:
        """Find which cell region contains the given global line number."""
        for region in self._cell_regions:
            if region.start_line <= global_line <= region.end_line:
                return region
        return None


class NotebookLSPManager:
    """Manages NotebookLSPBridge instances for all open notebooks."""

    def __init__(self):
        # Key: (project_id, notebook_path) -> NotebookLSPBridge
        self._bridges: dict[tuple[str, str], NotebookLSPBridge] = {}

    def get_or_create(self, project_id: str, notebook_path: str,
                      language: str = "python") -> NotebookLSPBridge:
        key = (project_id, notebook_path)
        if key not in self._bridges:
            self._bridges[key] = NotebookLSPBridge(project_id, notebook_path, language)
        return self._bridges[key]

    def get(self, project_id: str, notebook_path: str) -> Optional[NotebookLSPBridge]:
        return self._bridges.get((project_id, notebook_path))

    def remove(self, project_id: str, notebook_path: str):
        self._bridges.pop((project_id, notebook_path), None)

    def find_by_uri(self, uri: str) -> Optional[NotebookLSPBridge]:
        """Find a bridge by its shadow file URI (combined or per-cell)."""
        for bridge in self._bridges.values():
            if bridge.uri == uri:
                return bridge
            # Check per-cell JS shadow URIs
            for cell_info in getattr(bridge, '_js_cell_shadows', {}).values():
                if cell_info["uri"] == uri:
                    return bridge
        return None

    def find_cell_by_uri(self, uri: str) -> Optional[int]:
        """Find which cell index a per-cell shadow URI belongs to."""
        for bridge in self._bridges.values():
            for cell_idx, cell_info in getattr(bridge, '_js_cell_shadows', {}).items():
                if cell_info["uri"] == uri:
                    return cell_idx
        return None
