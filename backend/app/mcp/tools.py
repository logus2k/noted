"""MCP Tool Schema Definitions.

Converts noted's existing 24 tools into MCP-compatible JSON Schema format
for the tools/list endpoint. Each tool has a name, description, and
inputSchema following JSON Schema draft-07.

The tool metadata (read/write tier) is also defined here for use by the
approval middleware.
"""

import mcp.types as types


# ── Read-tier tools (auto-execute, no confirmation needed) ──────

_READ_TOOLS: list[types.Tool] = [
    types.Tool(
        name="get_experiment_runs",
        description="List recent MLflow runs for an experiment. Optionally filter by a tag (key=value), useful for sweep grouping via tags._sweep_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "experiment_name": {"type": "string", "description": "Name of the MLflow experiment"},
                "filter_tag": {
                    "type": "string",
                    "description": "Optional 'key=value' tag filter (e.g. '_sweep_id=abc123'). Empty = no filter.",
                },
            },
            "required": ["experiment_name"],
        },
    ),
    types.Tool(
        name="get_run_details",
        description="Get full details for a specific MLflow run: metrics, parameters, tags, and the list of logged artifacts (classic run artifacts classified into models/images/charts/files, plus MLflow 3.x Logged Model entities linked to the run).",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "MLflow run ID"},
            },
            "required": ["run_id"],
        },
    ),
    types.Tool(
        name="list_registered_models",
        description="List all models in the MLflow Model Registry with each model's current aliases (e.g. @champion -> v7). Use this to discover which model_name to pass to register_model, set_model_alias, or deploy_model, and to see which version each alias currently points at.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="list_model_versions",
        description="List all versions of a specific registered model, newest first, showing each version's run_id and any aliases it carries (e.g. v7 [@champion]). Use this when the user asks about a model's history or wants to pick a specific version to deploy or alias.",
        inputSchema={
            "type": "object",
            "properties": {
                "model_name": {"type": "string", "description": "Registered model name"},
            },
            "required": ["model_name"],
        },
    ),
    types.Tool(
        name="get_serving_status",
        description="Report the current state of the noted-serving container: whether a model is loaded, which model_name and version, the resolved alias (e.g. @champion), framework, and the originating run_id. Use this to answer 'is this model deployed?' or 'what model is currently serving predictions?' questions without having to tell the user to check the UI.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="get_serving_schema",
        description="Fetch the input/output schema of the model currently loaded in the serving container: input tensor shape, output shape, framework, and any example input hint. Call this before invoke_model when you need to know the payload shape for a real prediction. Returns an error if no model is currently loaded (in which case deploy one first).",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="invoke_model",
        description="Send a prediction request to the model currently loaded in the serving container. If 'data' is omitted, a zeros tensor matching the model's input shape is synthesized and used as a smoke test (useful to verify a deployment is wired up end-to-end). If 'data' is provided, it is forwarded as-is to the predict endpoint. Returns the model's predictions plus an output shape summary. Prefer this over generating a Python/curl snippet for the user to run - noted can hit the serving endpoint directly.",
        inputSchema={
            "type": "object",
            "properties": {
                "data": {
                    "description": "Optional prediction input. Usually a nested list shaped like the model's input tensor (e.g. [[[...]]] for shape (1, lookback, features)). Omit to run a zeros-tensor smoke test built from the model's declared input shape.",
                },
            },
        },
    ),
    types.Tool(
        name="list_run_artifacts",
        description="List the contents of a specific path inside a run's artifact tree. Use this to drill into a subdirectory (e.g. 'model', 'model/data', 'model/metadata') after get_run_details shows that the path exists. Returns one level at a time; call again with a deeper path to walk further down. An empty path lists the root of the run's artifact tree.",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "MLflow run ID"},
                "path": {"type": "string", "description": "Artifact path relative to the run's artifact root (e.g. 'model', 'model/data'). Empty string lists the root.", "default": ""},
            },
            "required": ["run_id"],
        },
    ),
    types.Tool(
        name="compare_runs",
        description="Compare two MLflow runs side by side",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id_a": {"type": "string", "description": "First run ID"},
                "run_id_b": {"type": "string", "description": "Second run ID"},
            },
            "required": ["run_id_a", "run_id_b"],
        },
    ),
    types.Tool(
        name="list_dags",
        description="List Airflow DAGs. Defaults to the current project; pass scope='all' to see every DAG Airflow tracks (other projects included).",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["current", "all"],
                    "description": "'current' (default) = only DAGs in the active project; 'all' = every DAG Airflow knows about.",
                },
            },
        },
    ),
    types.Tool(
        name="get_dag_status",
        description="Get DAG details and recent runs",
        inputSchema={
            "type": "object",
            "properties": {
                "dag_id": {"type": "string", "description": "Airflow DAG identifier"},
            },
            "required": ["dag_id"],
        },
    ),
    types.Tool(
        name="get_task_log",
        description="Get log output from a specific task in a DAG run",
        inputSchema={
            "type": "object",
            "properties": {
                "dag_id": {"type": "string", "description": "Airflow DAG identifier"},
                "dag_run_id": {"type": "string", "description": "DAG run identifier"},
                "task_id": {"type": "string", "description": "Task identifier"},
            },
            "required": ["dag_id", "dag_run_id", "task_id"],
        },
    ),
    types.Tool(
        name="get_dvc_data_overview",
        description="List all DVC-tracked data files across projects",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="get_dvc_file_history",
        description="Get version history for a DVC-tracked file in the current project. `dvc_file` is the project-relative path (e.g. data/dataset.csv); repo_path is auto-filled from the active project.",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Optional: absolute repo path. Defaults to the current project's filesystem root."},
                "dvc_file": {"type": "string", "description": "Project-relative path of the DVC-tracked file, e.g. data/dataset.csv"},
            },
            "required": ["dvc_file"],
        },
    ),
    types.Tool(
        name="get_file_contents",
        description="Read a file from the current project. Path is resolved from the active project context.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path, e.g. src/training/train.py"},
                "max_lines": {"type": "integer", "description": "Maximum lines to return (default 100)"},
            },
            "required": ["path"],
        },
    ),
    types.Tool(
        name="list_files",
        description="List files in the current project, with optional subdir and glob pattern. project_id is auto-filled from the active project context.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional - defaults to the active project."},
                "path": {"type": "string", "description": "Subdirectory path (optional)"},
                "pattern": {"type": "string", "description": "Glob pattern, e.g. *.py (optional)"},
            },
        },
    ),
    types.Tool(
        name="search_files",
        description="Search file contents across the current project (grep-like). project_id is auto-filled from the active project context.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional - defaults to the active project."},
                "query": {"type": "string", "description": "Search query string"},
                "path": {"type": "string", "description": "Subdirectory to search (optional)"},
                "file_pattern": {"type": "string", "description": "File pattern, e.g. *.py (optional)"},
                "max_results": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_hydra_config",
        description="Get the resolved Hydra configuration for the current project. project_id is auto-filled from context.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional - defaults to the active project."},
            },
        },
    ),
    types.Tool(
        name="query_knowledge_graph",
        description="Query the current project's knowledge graph for entity relationships. project_id is auto-filled from context.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional - defaults to the active project."},
            },
        },
    ),
    types.Tool(
        name="list_projects",
        description=(
            "List every project noted knows about (internal projects under "
            "data/projects/* AND mounted projects). Returns each project's "
            "id, source ('internal' or 'mount'), and notebook count. "
            "Call this to resolve a user's free-text reference like "
            "'the Jena project' to a real project_id BEFORE calling any "
            "project-scoped tool (get_experiment_runs, list_dags, "
            "list_files, get_notebook_cells, get_run_details). The active "
            "project from workspace context is the default for those tools, "
            "but if the user asks about a DIFFERENT project, use this tool "
            "to find the right id first."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="get_notebook_cells",
        description="Reads cells from a notebook. By default (no indices/from_index/to_index given) returns the entire notebook. project_id and notebook_path default to the currently open notebook (from workspace context); only supply them when targeting a different notebook. Pass indices or from_index/to_index only when a specific subset is needed. Result is capped at 80,000 chars; if truncated, use from_index to resume. Pass include_outputs=true for cell outputs.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Optional - defaults to the active project."},
                "notebook_path": {"type": "string", "description": "Optional - defaults to the currently open notebook."},
                "indices": {"type": "array", "items": {"type": "integer"}, "description": "Specific cell numbers to read (1-based)"},
                "from_index": {"type": "integer", "description": "Start cell number for range read (1-based)"},
                "to_index": {"type": "integer", "description": "End cell number for range read (1-based, inclusive)"},
                "include_outputs": {"type": "boolean", "description": "Include cell outputs (default false)"},
            },
        },
    ),
    types.Tool(
        name="scroll_to_cell",
        description="Scroll the notebook editor to a specific cell and select it",
        inputSchema={
            "type": "object",
            "properties": {
                "cell_index": {"type": "integer", "description": "Cell number to scroll to (1-based)"},
            },
            "required": ["cell_index"],
        },
    ),
    types.Tool(
        name="get_skill",
        description="Load detailed instructions for a specific topic. IMPORTANT: Check the ACTIVE SKILLS section of the current workspace context first - if the skill you need is already listed there, its content is already in your context and you MUST NOT call this tool for it (redundant fetch wastes tokens). Call this ONLY for skills that are NOT already active.",
        inputSchema={
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Skill name to load"},
                "reference": {"type": "string", "description": "Optional reference doc to load"},
            },
            "required": ["skill_name"],
        },
    ),
    types.Tool(
        name="run_agent",
        description="Delegate a reading/exploration task to a subagent that runs in a fresh context window",
        inputSchema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Detailed task description"},
                "agent_name": {"type": "string", "description": "Agent to use (e.g. notebook-explorer)"},
            },
            "required": ["task", "agent_name"],
        },
    ),
    types.Tool(
        name="fetch_url",
        description="Fetch the content of a web URL. Returns the page text (HTML stripped to readable text). Use this to read documentation, API references, articles, or any web resource the user shares.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
                "max_chars": {"type": "integer", "description": "Maximum characters to return (default 10000)"},
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="get_lint_diagnostics",
        description="Get current linter diagnostics (errors, warnings) for the open file",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    types.Tool(
        name="search_docs",
        description=(
            "Search across ALL active Knowledge Domains' documentation chunks. "
            "DOMAIN SELECTION IS AUTOMATIC: the tool fans out across every "
            "active Domain (eu_ai, sw_arch, noted, ...) and returns top-ranked "
            "chunks across the union. There is NO parameter to scope to a "
            "single Domain - do not pass Domain names or human-readable "
            "Domain labels in `tags` or `source_paths`. "
            "Returns ranked chunks with source section path for citation; "
            "if no chunk is a strong semantic match, returns a 'no strong "
            "match' notice - say so and do NOT fabricate. "
            "Do NOT use for live state (use get_run_details, get_dag_status, "
            "list_dags, ...), for the user's own notebook cells or project "
            "files (use get_notebook_cells, get_file_contents), or for topics "
            "already covered by an active skill - active skills' curated "
            "content wins."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language search query"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional 'key:value' filters on chunk metadata (AND'd). "
                        "Filters CHUNK CONTENT TYPE, not Domain. The only "
                        "supported key today is `doc_type`. Values are corpus-"
                        "specific (e.g. for the noted product corpus: "
                        "`user-manual`, `developer-manual`, `architecture`). "
                        "Do NOT pass Domain names here. Omit when in doubt."
                    ),
                },
                "top_k": {"type": "integer", "description": "Number of chunks to return. Defaults to 5.", "minimum": 1, "maximum": 10},
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional restriction to chunks whose source_path is "
                        "in this list. source_path is the FILENAME (e.g. "
                        "['eu_ai_act.pdf'], ['user_manual.md']) - NEVER a "
                        "Domain name. Use to scope to one specific document. "
                        "Omit to search the whole active-Domain corpus."
                    ),
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="graph_and_vector_search",
        description="Answer noted-domain questions by retrieving from BOTH the documentation chunks (vector RAG) AND the knowledge graph (entities + relationships) IN PARALLEL, then synthesizing one cohesive answer from both sources. Prefer this over picking just `search_docs` or `research_topic` - it gives stronger coverage (specific facts grounded in chunks PLUS thematic context from the graph) at the same wall-clock cost as either alone (parallel fan-out). Use for any noted-domain question; only fall back to single-source tools when you have a specific reason to want one and not the other.",
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural-language question. Phrase as a full sentence."},
                "domain_id": {
                    "type": "string",
                    "description": "Which Domain's knowledge to query. Pick from the active Domains shown in the workspace context (`Active knowledge domains`). Use the domain_id (machine slug like `sw_arch`, `eu_ai`, `noted`), NOT the human-readable name. Omit to use the first active Domain.",
                },
                "top_k_chunks": {"type": "integer", "description": "Number of doc chunks to fetch from vector RAG. Defaults to 5.", "minimum": 1, "maximum": 10, "default": 5},
                "source_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional restriction of the vector-search half to chunks whose source_path is in this list. Graph-search half is unaffected. Use to scope a query to a specific document.",
                },
            },
            "required": ["question"],
        },
    ),
    types.Tool(
        name="research_topic",
        description="Answer THEMATIC or RELATIONAL questions that span multiple documents by querying noted's knowledge graph. Use when the user asks 'what are the core...', 'how are X and Y connected', 'summarize the...', 'what themes emerge...'. Returns a synthesized answer plus the supporting subgraph (entities, relationships, and chunk citations). For specific-fact or single-document lookups use search_docs instead - this tool is slower and meant for synthesis across the corpus.",
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Natural-language question. Phrase as a full sentence, not keywords."},
                "domain_id": {
                    "type": "string",
                    "description": "Which Domain's knowledge to query. Pick from the active Domains shown in the workspace context (`Active knowledge domains`). Use the domain_id (machine slug like `sw_arch`, `eu_ai`, `noted`), NOT the human-readable name. Omit to use the first active Domain.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "global", "local"],
                    "description": "auto (default) runs both paths and picks the better-cited answer. global = thematic (community summaries + top entities). local = relational (N-hop Cypher traversal from entity matches).",
                    "default": "auto",
                },
            },
            "required": ["question"],
        },
    ),
]

# ── Write-tier tools (require user confirmation) ────────────────

_WRITE_TOOLS: list[types.Tool] = [
    types.Tool(
        name="register_model",
        description="Register a run's model artifact into the MLflow Model Registry under the given name. This is the required first step before deploy_model can reference a model by version number. Creates the registered-model entry if it does not exist yet, then creates a new version pointing at 'runs:/<run_id>/<artifact_path>'. Returns the new version number. After registering, you typically either call set_model_alias(..., 'champion') to promote it, or call deploy_model with the new version. Requires user confirmation.",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "MLflow run_id whose model artifact you want to register"},
                "model_name": {"type": "string", "description": "Target name in the Model Registry (e.g. 'Jena Weather Forecaster'). Reuses an existing registered-model entry if it exists, otherwise creates it."},
                "artifact_path": {"type": "string", "description": "Sub-path inside the run's artifact tree that holds the model. Almost always 'model' (the default).", "default": "model"},
            },
            "required": ["run_id", "model_name"],
        },
    ),
    types.Tool(
        name="set_model_alias",
        description="Move an alias (e.g. 'champion', 'staging', 'challenger') to point at a specific version of a registered model. In MLflow 3.x, aliases are movable pointers - 'promoting' a model means reassigning @champion to the new version. Requires user confirmation.",
        inputSchema={
            "type": "object",
            "properties": {
                "model_name": {"type": "string", "description": "Registered model name"},
                "version": {"type": "string", "description": "Version number (e.g. '7') that the alias should point at"},
                "alias": {"type": "string", "description": "Alias name (e.g. 'champion', 'staging')"},
            },
            "required": ["model_name", "version", "alias"],
        },
    ),
    types.Tool(
        name="deploy_model",
        description="Deploy (load) a registered MLflow model into the noted-serving container so it can serve predictions at POST /api/serving/predict. Accepts either a specific version number or an alias (e.g. 'champion'). This replaces whatever model is currently loaded - downstream clients already hitting the prediction endpoint will next see this model. The operation takes 10-60 seconds (artifact download + framework load). Requires user confirmation.",
        inputSchema={
            "type": "object",
            "properties": {
                "model_name": {"type": "string", "description": "Registered model name in the MLflow Model Registry (e.g. 'Jena Weather Forecaster')"},
                "version": {"type": "string", "description": "Specific version number to deploy (e.g. '7'). Provide either version or alias."},
                "alias": {"type": "string", "description": "Alias to resolve at deploy time (e.g. 'champion', 'staging'). Provide either version or alias."},
            },
            "required": ["model_name"],
        },
    ),
    types.Tool(
        name="update_cell",
        description="Modify a single notebook cell",
        inputSchema={
            "type": "object",
            "properties": {
                "cell_index": {"type": "integer", "description": "Cell number to update (1-based)"},
                "new_content": {"type": "string", "description": "New cell content"},
                "description": {"type": "string", "description": "Description of the change"},
                "project_id": {"type": "string", "description": "Project identifier (optional)"},
                "notebook_path": {"type": "string", "description": "Notebook path (optional)"},
            },
            "required": ["cell_index", "new_content", "description"],
        },
    ),
    types.Tool(
        name="insert_cell",
        description="Insert a new cell into the notebook",
        inputSchema={
            "type": "object",
            "properties": {
                "after_cell_index": {"type": "integer", "description": "Insert after this cell number (1-based)"},
                "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Cell type"},
                "content": {"type": "string", "description": "Cell content"},
                "description": {"type": "string", "description": "Description of what this cell does"},
                "project_id": {"type": "string", "description": "Project identifier (optional)"},
                "notebook_path": {"type": "string", "description": "Notebook path (optional)"},
            },
            "required": ["after_cell_index", "cell_type", "content", "description"],
        },
    ),
    types.Tool(
        name="batch_update_cells",
        description=("Change MULTIPLE notebook cells with the SAME semantic op in a single confirmation. "
                     "REQUIRES at least 2 items in 'ops' - this tool amortizes cost across a batch, "
                     "so single-op cases must use the op-specific tool instead "
                     "(update_cell for one update, insert_cell for one insert). "
                     "Use this ONLY for homogeneous batches: many updates, OR many inserts, OR many patches. "
                     "Emit one ordered list 'ops' where every item uses the same op type. "
                     "Supported op types: "
                     "'update' (rewrite an existing cell, requires new_content), "
                     "'patch' (local find-and-replace inside one cell, requires find + replace; cheaper than update for small edits), "
                     "'insert' (add a new cell after a given index). "
                     "DO NOT mix op types in the same ops list - that has been observed to lose ops. "
                     "For mixed actions in one turn (e.g. update cell N AND insert a new cell after it), "
                     "emit SEPARATE insert_cell + update_cell tool calls in the same response - "
                     "the backend batches every write tool call from one response into ONE approval, "
                     "so the user still sees a single confirmation. "
                     "Prefer 'patch' over 'update' for local edits so the call stays compact."),
        inputSchema={
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["update", "patch", "insert"], "description": "Op type discriminator"},
                            "cell_index": {"type": "integer", "description": "update/patch only: 1-based cell"},
                            "new_content": {"type": "string", "description": "update only: complete new cell body"},
                            "find": {"type": "string", "description": "patch only: literal substring to locate inside the cell"},
                            "replace": {"type": "string", "description": "patch only: replacement text"},
                            "after_cell_index": {"type": "integer", "description": "insert only: 1-based cell to insert after; 0 = insert at top"},
                            "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "insert only"},
                            "content": {"type": "string", "description": "insert only: body of the new cell"},
                            "description": {"type": "string", "description": "Short human-readable label for this op"},
                        },
                        "required": ["op", "description"],
                    },
                    "description": "Ordered list of cell operations. MUST contain at least 2 ops - single-op cases must use update_cell or insert_cell directly.",
                },
                "description": {"type": "string", "description": "Overall description of the batch change"},
                "project_id": {"type": "string", "description": "Project identifier (optional)"},
                "notebook_path": {"type": "string", "description": "Notebook path (optional)"},
            },
            "required": ["ops", "description"],
        },
    ),
    types.Tool(
        name="find_replace_in_cells",
        description=("Find-and-replace a literal substring (or regex pattern) across notebook cells. "
                     "Preferred over batch_update_cells for renames, alias additions, or any small local "
                     "edit - the backend reads each cell and builds the full update, so you only emit the "
                     "pattern and replacement, never the full cell content."),
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Literal substring to find (or regex pattern if is_regex=true)"},
                "replacement": {"type": "string", "description": "Replacement text"},
                "cell_indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "1-based cell numbers to target. Omit to scan all code cells.",
                },
                "is_regex": {"type": "boolean", "description": "Treat pattern as a Python regex. Default false (literal)."},
                "description": {"type": "string", "description": "Short human-readable description of the change"},
                "project_id": {"type": "string", "description": "Project identifier (optional)"},
                "notebook_path": {"type": "string", "description": "Notebook path (optional)"},
            },
            "required": ["pattern", "replacement", "description"],
        },
    ),
    types.Tool(
        name="update_file",
        description=("Modify a text file with complete-rewrite content. "
                     "Two usage patterns: "
                     "(a) file already open in the editor - FILE CONTEXT shows its content; emit only new_content + description, the path is inferred from the open file. "
                     "(b) file NOT open but was fetched earlier via get_file_contents - you MUST emit file_path carrying the same relative path you passed to get_file_contents, otherwise the executor does not know which file to write and the call errors out."),
        inputSchema={
            "type": "object",
            "properties": {
                "new_content": {"type": "string", "description": "Complete new file content"},
                "description": {"type": "string", "description": "Description of the change"},
                "file_path": {"type": "string", "description": "Relative path to the file, e.g. 'src/training/pipeline.py'. REQUIRED when the file was fetched via get_file_contents in a prior turn OR when no file is currently open in FILE CONTEXT. Omit only when the target file is already open in the editor and its path is implicit from FILE CONTEXT."},
            },
            "required": ["new_content", "description"],
        },
    ),
    types.Tool(
        name="create_file",
        description="Create a new file in the project",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File path to create"},
                "content": {"type": "string", "description": "File content"},
                "description": {"type": "string", "description": "Description of the new file"},
                "project_id": {"type": "string", "description": "Project identifier (optional)"},
            },
            "required": ["file_path", "content", "description"],
        },
    ),
    types.Tool(
        name="fix_lint_issues",
        description="Auto-fix lint issues in the open file by rule code",
        inputSchema={
            "type": "object",
            "properties": {
                "codes": {"type": "string", "description": "Rule codes to fix, e.g. 'F401' or 'F401,PIE790' (optional, fixes all if omitted)"},
            },
        },
    ),
]


# ── Public API ──────────────────────────────────────────────────

ALL_TOOLS: list[types.Tool] = _READ_TOOLS + _WRITE_TOOLS


# ── Per-Domain attribution ──────────────────────────────────────────
#
# Each MCP tool belongs to exactly one Domain. Tools tagged `general` are
# universal helpers (file IO, knowledge-base search that fans out across
# active Domains, web fetch, skill loader). Anything else defaults to
# `noted` since the platform-specific tools (notebook editing, MLflow,
# Hydra, DVC, Airflow, serving) live in the noted Domain.
#
# When the user activates noted in the Domain Manager, all tagged-`noted`
# tools become available to the model. When noted is deactivated, those
# tools are filtered out of the system prompt + Explorer tree, leaving
# only the universal `general` set.
_GENERAL_TOOL_NAMES: set[str] = {
    'fetch_url',
    'get_skill',
    'list_projects',
    'list_files',
    'get_file_contents',
    'search_files',
    'search_docs',
    'create_file',
    'graph_and_vector_search',
    'query_knowledge_graph',
    'research_topic',
    'run_agent',
}


def get_tool_domain(tool_name: str) -> str:
    """Return the domain_id this tool belongs to. Default 'noted' for any
    tool not in the explicit `general` set."""
    return 'general' if tool_name in _GENERAL_TOOL_NAMES else 'noted'


def tools_for_domains(active_domains: list[str] | None) -> list[types.Tool]:
    """Filter ALL_TOOLS to those whose owning Domain is in `active_domains`.
    When `active_domains` is None or empty, returns the full list (no filter)."""
    if not active_domains:
        return ALL_TOOLS
    active = set(active_domains)
    return [t for t in ALL_TOOLS if get_tool_domain(t.name) in active]

WRITE_TOOL_NAMES: set[str] = {t.name for t in _WRITE_TOOLS}

READ_TOOL_NAMES: set[str] = {t.name for t in _READ_TOOLS}


def get_all_tools() -> list[types.Tool]:
    """Return all MCP tool definitions (read + write)."""
    return ALL_TOOLS


def is_write_tier(tool_name: str) -> bool:
    """Check if a tool requires write-tier approval."""
    return tool_name in WRITE_TOOL_NAMES
