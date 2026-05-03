import { KernelClient } from './KernelClient.js';
import { NotebookEditor } from './NotebookEditor.js';
import { NotebookToolbar } from './NotebookToolbar.js';
import { InfoBar } from './InfoBar.js';
import { IconBar } from './IconBar.js';
import { SidebarPanel } from './SidebarPanel.js';
import { ExplorerPanel } from './panels/ExplorerPanel.js';
import { DisplaySettingsPanel } from './panels/DisplaySettingsPanel.js';
import { NotebookResizer } from './NotebookResizer.js';
import { ChatPanel } from './ChatPanel.js';
import { ChatService } from './ChatService.js';
import { RightPanel } from './RightPanel.js';
import { TabBar } from './TabBar.js';
import { TocPanel } from './TocPanel.js';
import { DocumentViewer } from './panels/DocumentViewer.js';
import { FileEditor, setOnAskAssistant } from './FileEditor.js';
import { DocPanel } from './DocPanel.js';
import { MediaViewer } from './MediaViewer.js';
import { isMediaViewable, mediaType } from './file-icons.js';
import { notify } from './Notify.js';
import { domainState } from './domain-state.js';
import { GitPanel } from './GitPanel.js';
import { RunManagerPanel } from './RunManagerPanel.js';
import { GitCommitViewer } from './GitCommitViewer.js';
import { DecorationService } from './services/DecorationService.js';
import { MenuBar } from './MenuBar.js';
import { ExportPanel } from './ExportPanel.js';
import { openProjectTerminal } from './ProjectTerminal.js';
import { MetricsPanel } from './MetricsPanel.js';
import { restoreWallpaper } from './wallpapers.js';
import { initStatusBar } from './app-status-bar.js';
import { initMenuCommands } from './app-menu.js';
import { initChat } from './app-chat.js';
import { initFileEditors } from './app-file-editors.js';
import { initNotebooks } from './app-notebooks.js';
import { initTabs } from './app-tabs.js';


/**
 * App - Entry point. Wires together all components.
 */
class App {
    constructor() {
        this._client = new KernelClient();
        initStatusBar(this);
        initMenuCommands(this);
        initChat(this);
        initFileEditors(this);
        initNotebooks(this);
        initTabs(this);
        /** @type {Map<string, {editor: NotebookEditor, container: HTMLElement, project: string, notebook: string, venv: object|null}>} */
        this._editors = new Map();
        this._activeEditorKey = null;
        this._lastContentKey = null; // last notebook/pyfile key; survives undocking
        this._toolbar = null;
        this._infoBar = null;
        this._iconBar = null;
        this._sidebar = null;
        this._explorerPanel = null;
        this._displaySettingsPanel = null;
        this._currentProject = null;
        this._currentNotebook = null;
        this._activeVenv = null; // { name, runtimeId, displayName } or null
        this._userName = this._generateUserName();
        this._kernelRunning = false;
        this._kernelStarting = false;
        this._chatVisible = false;
        this._documentViewer = null;
        /** @type {Map<string, object>} keyed by tab key "doc:category:name" → doc object */
        this._documentTabs = new Map();
        /** @type {Map<string, DocumentViewer>} keyed by tab key "doc:category:name".
         *  One DocumentViewer instance per open doc tab so each preserves its own
         *  scroll position + rendered PDF state across tab switches. The
         *  singleton _documentViewer above stays for shared markdown-rendering
         *  helpers used by md preview tabs and other non-doc-tab callers. */
        this._documentViewers = new Map();
        /** @type {Map<string, FileEditor>} keyed by tab key "pyfile:{projectId}:{filename}" */
        this._fileEditors = new Map();
        /** @type {Map<string, MediaViewer>} keyed by tab key "media:{projectId}:{filename}" */
        this._mediaViewers = new Map();
        /** @type {Map<string, {element:HTMLElement, title:string, render:function}>} keyed by tab key "detail:..." */
        this._detailTabs = new Map();
        this._gitPanel = null;
        this._decorationService = null;
    }

    /** Active notebook editor (null if no notebooks open) */
    get _editor() {
        const entry = this._editors.get(this._activeEditorKey);
        return entry ? entry.editor : null;
    }

    async init() {
        // Restore wallpaper from localStorage before anything renders
        restoreWallpaper();

        // P3.3: prime the active-Domain cache once at boot. All Domain-aware fetches
        // (GraphPanel, ExplorerPanel, Domain Monitor, ...) read domainState
        // synchronously, so this needs to complete before those panels open.
        await domainState.bootstrap();

        // Make panels more opaque while dragging (default 0.8 → 0.95)
        jsPanel.defaults.dragit.opacity = 0.95;

        // Prevent wheel scroll from propagating through floating panels to content behind.
        // Also ensure panel content containers have proper overflow containment.
        const _origCreate = jsPanel.create.bind(jsPanel);
        jsPanel.create = function(options) {
            const origCallback = options.callback;
            options.callback = function(panel) {
                panel.addEventListener('wheel', (e) => e.stopPropagation(), { passive: false });
                if (panel.content) {
                    panel.content.style.overscrollBehavior = 'contain';
                }
                if (origCallback) origCallback(panel);
            };
            return _origCreate(options);
        };

        // Initialize notebook resizer (restores saved width)
        this._notebookResizer = new NotebookResizer();

        // Initialize icon bar (left vertical strip)
        this._iconBar = new IconBar(
            document.getElementById('icon-bar'),
            {
                onIconClick: (key) => this._onIconBarClick(key),
            }
        );

        // Initialize sidebar panel (between icon bar and content area)
        this._sidebar = new SidebarPanel({
            onResize: () => this._tocPanel?.refresh(),
            onViewChange: () => this._syncIconBar(),
        });

        // Initialize unified explorer panel (projects + environments)
        this._workspaceTitleEl = null;
        this._workspaceBreadcrumbBar = null;
        this._explorerPanel = new ExplorerPanel({
            onNotebookPreview: (projectId, notebookName) => this._onNotebookChange(projectId, notebookName, { preview: true }),
            onNotebookSelect: (projectId, notebookName) => this._onNotebookChange(projectId, notebookName),
            onVenvSelect: (venv) => this._onVenvSelect(venv),
            onVenvDeleted: (deletedName) => this._onVenvDeleted(deletedName),
            onSectionChange: (section) => this._updateWorkspaceTitle(section),
            onBreadcrumbChange: (crumbs) => this._updateWorkspaceBreadcrumbs(crumbs),
            onActivate: () => this._openWorkspaceTab(),
            onClosePreview: () => this._tabBar.closePreview(),
            onCloseWorkspace: () => {
                this._tabBar.closePreview();
                this._tabBar.closeTab('workspace');
                const active = this._tabBar.activeKey;
                if (active?.startsWith('detail:')) {
                    this._tabBar.closeTab(active);
                }
            },
            onOpenKnowledgeGraph: () => this._openKnowledgeGraphTab(),
            onDocumentPreview: (doc) => this._openDocumentTab(doc, { preview: true }),
            onDocumentOpen: (doc) => this._openDocumentTab(doc),
            onSrcFilePreview: (projectId, filename, hostPath) => this._previewFileTab(projectId, filename, hostPath),
            onSrcFileSelect: (projectId, filename, hostPath) => this._openFileTab(projectId, filename, hostPath),
            onMediaFilePreview: (projectId, filename, hostPath) => this._previewMediaTab(projectId, filename, hostPath),
            onMediaFileSelect: (projectId, filename, hostPath) => this._openMediaTab(projectId, filename, hostPath),
            onProjectDefaultVenvChanged: (projectId, venv) => this._onProjectDefaultVenvChanged(projectId, venv),
            onProjectCreated: () => this._gitPanel?.refresh(),
            onProjectDeleted: () => this._gitPanel?.refresh(),
            onProjectRenamed: () => this._gitPanel?.refresh(),
            onNotebookDeleted: () => this._gitPanel?.refresh(),
            onNotebookRenamed: () => this._gitPanel?.refresh(),
            onMetricsView: (runId, runName, metricsMap) => this._metricsPanel?.loadHistory(runId, runName, metricsMap),
            onDetailTab: (tabKey, label, element, opts) => this._openDetailTab(tabKey, label, element, opts),
            onPinTab: (tabKey) => this._tabBar.pinTab(tabKey),
            getSocket: () => this._client.socket,
        });

        // Wire app reference into the explorer's shared ctx so context-menu
        // actions can call e.g. app.showKnowledgeBaseMonitor().
        if (this._explorerPanel._ctx) {
            this._explorerPanel._ctx.app = this;
        }

        // Register sidebar views — tree from ExplorerPanel
        this._sidebar.registerView('projects', {
            tabLabel: 'Explorer',
            title: 'Assets Management',
            element: this._explorerPanel.treeElement,
            titleElement: this._explorerPanel.titleElement,
        });

        // Git panel — sidebar view for per-project version control
        this._gitPanel = new GitPanel();
        this._gitCommitViewer = new GitCommitViewer();
        this._gitPanel.setOnCommitOpen((repoPath, commit) => this._openGitCommitTab(repoPath, commit));
        this._gitPanel.setOnFileDiscarded((filePaths) => this._reloadDiscardedFiles(filePaths));
        this._sidebar.registerView('git', {
            tabLabel: 'Version Control',
            title: 'Version Control',
            element: this._gitPanel.element,
            titleElement: this._gitPanel.titleElement,
            onActivate: () => this._gitPanel.activate(),
        });

        // TOC panel — lives inside the sidebar as a view
        this._tocPanel = new TocPanel(
            () => this._editor?.cells || [],
            (index) => this._editor?.selection.selectCell(index)
        );
        this._sidebar.registerView('toc', {
            tabLabel: 'Table of Contents',
            title: '',
            element: this._tocPanel.element,
            onActivate: () => this._tocPanel.activate(),
            onDeactivate: () => this._tocPanel.deactivate(),
        });

        // Settings panel - sidebar view
        this._displaySettingsPanel = new DisplaySettingsPanel();
        this._sidebar.registerView('settings', {
            tabLabel: 'Settings',
            title: 'Application Settings',
            element: this._displaySettingsPanel.element,
        });

        // Decoration service — git status dots in explorer tree
        this._decorationService = new DecorationService(() => {
            this._explorerPanel.repaintDecorations();
        });
        this._explorerPanel.setDecorationService(this._decorationService);
        this._gitPanel.setOnStatusRefreshed((repoPath, repoInfo, statusData) => {
            this._decorationService.updateRepoStatus(repoPath, repoInfo, statusData);
        });
        this._gitPanel.setOnDvcStatusRefreshed((repoPath, repoInfo, dvcData) => {
            this._decorationService.updateDvcStatus(repoPath, repoInfo, dvcData);
        });

        // Restore display toggles
        const toggleMap = {
            'show-cell-titles': 'hide-cell-titles',
            'show-cell-borders': 'hide-cell-borders',
            'show-cell-bg': 'hide-cell-bg',
            'show-code-cells': 'hide-code-cells',
            'show-line-numbers': 'hide-line-numbers',
            'show-output': 'hide-output',
            'show-table-stripes': 'hide-table-stripes',
            'show-add-cell-areas': 'hide-add-cell-areas',
            'show-bg-image': 'hide-bg-image',
            'show-bg-color': 'hide-bg-color',
        };
        for (const [key, cls] of Object.entries(toggleMap)) {
            if (localStorage.getItem(`notebook-${key}`) === '0') {
                document.body.classList.add(cls);
            }
        }

        // Forward wheel events from page margins (dead zones) to notebook container
        const notebookContainer = document.getElementById('notebook-container');
        document.addEventListener('wheel', (e) => {
            if (notebookContainer.contains(e.target)) return;
            // Don't forward if the target is inside a panel with its own scroll
            if (e.target.closest('#sidebar-panel, #right-panel, #toolbar, .service-iframe-wrapper')) return;
            notebookContainer.scrollBy(0, e.deltaY);
        }, { passive: true });

        // Notebook container (parent for all editor containers)
        this._notebookContainer = document.getElementById('notebook-container');

        // Initialize toolbar (nav icons + file actions + settings + users)
        this._toolbar = new NotebookToolbar(
            document.getElementById('toolbar'),
            this._client,
            {
                onSave: () => this._editor?.save(),
                onSettingsToggle: () => this._onIconBarClick('settings'),
                getCells: () => this._editor?.cells || [],
                onSelectCell: (index) => this._editor?.selection?.selectCell(index),
            }
        );

        // Hamburger menu button - absolutely positioned in the top-left
        // corner of #app, above the icon bar (the icon bar has margin-top:56px
        // which leaves a ~48x56 empty area we can use).
        const menuBtn = document.createElement('button');
        menuBtn.className = 'icon-bar-menu';
        menuBtn.innerHTML = '<i class="fa-solid fa-bars"></i>';
        menuBtn.title = 'Menu';
        menuBtn.addEventListener('click', () => this._onIconBarClick('menu'));
        document.getElementById('app').appendChild(menuBtn);

        // Initialize menu bar
        this._menuBar = new MenuBar('#menubar');
        this._menuBar.load('static/menu.json').then(() => {
            this._registerMenuCommands();
        });

        // Initialize info bar (decorative)
        this._infoBar = new InfoBar(document.getElementById('info-bar'));

        // Initialize tab bar (above notebook, inside center-column)
        this._serviceIframes = {};
        this._undockedPanels = new Map(); // key -> jsPanel instance
        this._tabBar = new TabBar(
            document.getElementById('center-column'),
            {
                onActivateTab: (key) => this._onTabActivated(key),
                onCloseTab: (key) => this._onTabClosed(key),
                onUndockTab: (key) => this._onUndockTab(key),
                onDockTab: (key) => this._onDockTab(key),
            }
        );

        // Note: editor callbacks are wired in _wireEditorCallbacks(), called per editor

        // Run Manager
        this._runManager = new RunManagerPanel({
            getCells: () => this._editor?._cells || [],
            getMetadata: () => this._editor?.getNotebookMetadata() || {},
            onSave: () => { this._editor?.refreshRunBadges(); this._editor?.save(); },
            onExecuteRun: (runId, runName, cells, datasets) => {
                if (!this._editor) return;
                const hydraConfig = this._editor.hydraConfig;
                this._client.executeRun(cells, runName, datasets, this._editor.notebookKey, hydraConfig);
            },
            onActiveRunChange: (runId) => {
                this._editor?.setRunManagerActiveRun(runId);
            },
            getDvcFiles: async () => {
                const pid = this._currentProject;
                if (!pid) return [];
                try {
                    const resp = await fetch('api/dvc/status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ project_id: pid })
                    });
                    if (!resp.ok) return [];
                    const data = await resp.json();
                    return data.tracked_files || [];
                } catch { return []; }
            },
            getHydraDataFile: async () => {
                // Returns { file, hash } when the current notebook has a
                // Hydra config and its cfg.data.file resolves to a DVC
                // tracked path. Otherwise returns null.
                // Used by the Run Manager to render a read-only "Data:
                // <file> (from Hydra config)" line instead of the multi-
                // select picker, so the two UIs cannot disagree about
                // which data the run consumed.
                const pid = this._currentProject;
                if (!pid) return null;
                const meta = this._editor?.getNotebookMetadata() || {};
                const noted = meta.noted || {};
                const selections = noted.hydra_selections || null;
                if (!selections) return null;
                try {
                    const resp = await fetch('api/hydra/compose', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            project_id: pid,
                            overrides: selections.overrides || null,
                            group_selections: selections.group_selections || null,
                        }),
                    });
                    if (!resp.ok) return null;
                    const composed = await resp.json();
                    const dataFile = composed?.resolved?.data?.file || null;
                    if (!dataFile) return null;
                    // Look up the DVC hash for this file
                    try {
                        const dvcResp = await fetch('api/dvc/status', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ project_id: pid }),
                        });
                        if (dvcResp.ok) {
                            const dvc = await dvcResp.json();
                            const tracked = dvc.tracked_files || [];
                            const match = tracked.find(f => f.path === dataFile);
                            if (match) return { file: dataFile, hash: match.hash, tracked: true };
                        }
                    } catch {}
                    return { file: dataFile, hash: null, tracked: false };
                } catch {
                    return null;
                }
            },
        });
        // Run manager wiring is done per-editor in _wireEditorCallbacks()

        // Live metrics panel
        this._metricsPanel = new MetricsPanel();
        this._client.on('metrics:update', (data) => {
            const activeKey = this._activeEditorKey;
            if (activeKey && (!data.notebook_key || data.notebook_key === activeKey)) {
                this._metricsPanel.onMetricUpdate(data.metric);
                // Store run_id in notebook metadata for recovery after refresh
                if (data.metric?.run_id) {
                    const entry = this._editors.get(activeKey);
                    if (entry?.editor?._notebook) {
                        if (!entry.editor._notebook.metadata) entry.editor._notebook.metadata = {};
                        if (!entry.editor._notebook.metadata.noted) entry.editor._notebook.metadata.noted = {};
                        entry.editor._notebook.metadata.noted.last_run_id = data.metric.run_id;
                    }
                    // Update active run indicator in notebook bar
                    if (entry?.editor) {
                        entry.editor.updateRunIndicator(data.metric.run_id, data.metric.run_name || data.metric.run_id?.substring(0, 8));
                    }
                }
            }
        });

        // Pipeline status updates
        this._client.on('pipeline:status', (data) => {
            if (!data?.dag_id || !data?.dag_run_id) return;
            const nodeKey = `dagrun:${data.dag_id}:${data.dag_run_id}`;
            const node = this._explorerPanel?._tree?.findKey(nodeKey);
            if (node) {
                const stateIcons = {
                    success: 'fa-solid fa-circle-check',
                    running: 'fa-solid fa-circle-play',
                    failed: 'fa-solid fa-circle-xmark',
                    queued: 'fa-solid fa-clock',
                    skipped: 'fa-solid fa-forward',
                };
                node.icon = stateIcons[data.state] || 'fa-solid fa-circle-question';
                // Update title with new state
                const title = node.title || '';
                const dash = title.indexOf(' - ');
                if (dash >= 0) {
                    node.title = title.substring(0, dash) + ' - ' + data.state;
                }
                node.update();
                // Refresh task children on terminal states
                if (['success', 'failed', 'skipped', 'upstream_failed'].includes(data.state)) {
                    if (node.isExpanded() || node.children?.length) {
                        node.resetLazy();
                        if (node.isExpanded()) node.setExpanded(true);
                    }
                }
                // Show toast on terminal states
                if (data.state === 'success') {
                    notify.success(`Pipeline ${data.dag_id} completed`);
                } else if (data.state === 'failed') {
                    notify.error(`Pipeline ${data.dag_id} failed`);
                }
            }
        });

        this._client.on('pipeline:task_status', (data) => {
            if (!data?.dag_id || !data?.dag_run_id || !data?.task_id) return;
            const runKey = `dagrun:${data.dag_id}:${data.dag_run_id}`;
            const runNode = this._explorerPanel?._tree?.findKey(runKey);
            if (runNode?.children) {
                const taskNode = runNode.children.find(c => c.key === `dagtask:${data.dag_id}:${data.dag_run_id}:${data.task_id}`);
                if (taskNode) {
                    const stateIcons = {
                        success: 'fa-solid fa-circle-check',
                        running: 'fa-solid fa-circle-play',
                        failed: 'fa-solid fa-circle-xmark',
                        queued: 'fa-solid fa-clock',
                        skipped: 'fa-solid fa-forward',
                    };
                    taskNode.icon = stateIcons[data.state] || 'fa-solid fa-circle-question';
                    // Update title with state and timing
                    const start = data.start_date ? new Date(data.start_date).toLocaleTimeString() : '';
                    const dur = data.duration != null ? ` (${data.duration.toFixed(1)}s)` : '';
                    taskNode.title = `${data.task_id} (${data.state})${start ? ' - ' + start : ''}${dur}`;
                    taskNode.update();
                }
            }
            // Update DAG graph visualization in real-time
            this._explorerPanel?._externalViews?.updateGraphTaskState?.(
                data.dag_id, data.dag_run_id, data.task_id, data.state
            );
        });

        // Export panel
        this._exportPanel = new ExportPanel({
            onExport: async (format, options) => {
                if (!this._currentProject || !this._currentNotebook) {
                    notify.warning('No notebook open');
                    return;
                }
                this._exportPanel.setStatus('Exporting...');
                try {
                    const resp = await fetch(`api/export/${format}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            project_id: this._currentProject,
                            notebook_path: this._currentNotebook,
                            ...options,
                        }),
                    });
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({ detail: 'Export failed' }));
                        throw new Error(err.detail || 'Export failed');
                    }
                    const blob = await resp.blob();
                    const disposition = resp.headers.get('Content-Disposition') || '';
                    const match = disposition.match(/filename="?(.+?)"?$/);
                    const filename = match ? match[1] : `export.${format === 'word' ? 'docx' : format}`;
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    a.click();
                    URL.revokeObjectURL(url);
                    this._exportPanel.setStatus('Done!');
                    setTimeout(() => this._exportPanel.setStatus(''), 3000);
                } catch (e) {
                    this._exportPanel.setStatus('');
                    notify.error(e.message);
                }
            },
        });

        // Run execution events
        this._client.on('run:started', (data) => {
            notify.success(`Run "${data.run_name}" started`);
        });
        this._client.on('run:complete', (data) => {
            if (data.errored) {
                notify.error(`Run "${data.run_name}" stopped with errors`);
            } else {
                // Build summary with latest metric values from live metrics panel
                const traces = this._metricsPanel?._traces || {};
                const metricParts = Object.entries(traces).map(([key, t]) => {
                    const last = t.y?.length ? t.y[t.y.length - 1] : null;
                    if (last == null) return null;
                    const val = typeof last === 'number' ? (Number.isInteger(last) ? last : last.toFixed(4)) : last;
                    return `${key}: ${val}`;
                }).filter(Boolean).slice(0, 5);
                const summary = metricParts.length ? `\n${metricParts.join(' | ')}` : '';
                notify.success(`Run "${data.run_name}" completed${summary}`);
            }
            this._runManager.refresh();
        });

        // Listen for cell insertion requests (e.g., from Model Registry "Insert Predict Cell")
        document.addEventListener('noted:insert-cell', (e) => {
            const editor = this._editor;
            if (!editor) return;
            const code = e.detail?.code || '';
            const idx = editor._cells?.length || 0;
            editor._addCell(idx, 'code');
            const cell = editor._cells[idx];
            if (cell) cell.setSource(code);
        });

        // Initialize document viewer (for MD/PDF rendering in center pane)
        this._documentViewer = new DocumentViewer();

        // Initialize right panel (chat assistant)
        this._initRightPanel();

        // Track kernel running state
        this._client.on('kernel:status', (data) => {
            this._kernelRunning = data.status === 'idle' || data.status === 'busy';
            this._kernelStarting = data.status === 'starting';
            this._explorerPanel.setKernelRunning(this._kernelRunning);
        });

        // Connect Socket.IO
        this._client.connect();
        this._gitPanel.setSocket(this._client.socket);

        this._initialConnect = true;
        this._client.on('connected', () => {
            // Expose socket globally for debug panel events
            window._notedSocket = this._client._socket;
            if (this._initialConnect) {
                this._initialConnect = false;
                console.log('Connected to server');
                return;
            }
            console.log('Reconnected to server');
            // Re-open all notebooks that were open before disconnect
            for (const [key, entry] of this._editors) {
                entry.editor.openNotebook(entry.project, entry.notebook, this._userName);
                if (entry.venv) {
                    this._client.startKernel(entry.venv.runtimeId, entry.venv.name, entry.editor.notebookKey);
                }
            }
        });

        this._client.on('disconnected', (data) => {
            console.log('Disconnected:', data.reason);
        });

        this._client.on('error', (data) => {
            console.error('Server error:', data.message, data.code);
        });

        // Keyboard shortcuts (capture phase so they fire before CodeMirror)
        // Only intercept for notebook tabs; file editors handle their own navigation.
        document.addEventListener('keydown', (e) => {
            const isNotebook = notebookContainer.style.display !== 'none';
            if (!isNotebook) return;
            if ((e.ctrlKey || e.metaKey) && e.key === 'Home') {
                e.preventDefault();
                e.stopPropagation();
                notebookContainer.scrollTo({ top: 0 });
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'End') {
                e.preventDefault();
                e.stopPropagation();
                notebookContainer.scrollTo({ top: notebookContainer.scrollHeight });
            }
            if (e.key === 'PageUp') {
                e.preventDefault();
                e.stopPropagation();
                notebookContainer.scrollBy(0, -notebookContainer.clientHeight);
            }
            if (e.key === 'PageDown') {
                e.preventDefault();
                e.stopPropagation();
                notebookContainer.scrollBy(0, notebookContainer.clientHeight);
            }
            // Ctrl/Cmd+G: open the "Go to cell" modal (same as clicking
            // the status-bar cell ordinal).
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'g') {
                e.preventDefault();
                e.stopPropagation();
                this._showGoToCellModal?.();
            }
        }, true);

        // All sidebar panels closed by default
        requestAnimationFrame(() => {
            this._syncIconBar();
        });

        // Load workspace tree data, then fetch git decorations and health badges
        await this._explorerPanel.init();
        this._decorationService.refreshAll();

        // Check URL params for auto-open
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project');
        const notebook = params.get('notebook');
        if (projectId) {
            await this._onProjectChange(projectId);
            if (notebook) {
                this._onNotebookChange(projectId, notebook);
            }
        }

        // Expand tree to the active notebook
        this._explorerPanel.navigate({
            currentProject: this._currentProject,
            currentNotebook: this._currentNotebook,
        });

        // Populate status bar with system info, then update project/branch
        await this._initStatusBar();
        this._updateStatusProject(this._currentProject);
        this._updateStatusBranch(this._currentProject);
    }

    // Status bar methods extracted to app-status-bar.js

    // Notebook lifecycle extracted to app-notebooks.js

    // Tab management extracted to app-tabs.js

    /**
     * Open the GraphRAG rebuild monitor panel. Read-only / monitoring only -
     * the rebuild itself is triggered separately (admin context menu, future).
     * Safe to call any time. Lazily imports the module to keep startup small.
     */
    async showKnowledgeBaseMonitor(domainId = null) {
        if (!this._kbMonitor) {
            const { KnowledgeBaseMonitorPanel } = await import('./knowledge-graph/KnowledgeBaseMonitorPanel.js');
            this._kbMonitor = new KnowledgeBaseMonitorPanel();
        }
        this._kbMonitor.open(domainId);
    }

    /** Open the Domain Manager floating panel - the single canonical surface
     * for Domain CRUD plus per-Domain document and knowledge management.
     * Replaces the legacy KnowledgeBaseManagerPanel. Lazy-imported.
     *
     * `domainId` (optional) pre-selects a Domain in the left list. */
    async showKnowledgeBaseManager(domainId = null) {
        if (!this._kbManager) {
            const { DomainManagerPanel } = await import('./knowledge-graph/DomainManagerPanel.js');
            this._kbManager = new DomainManagerPanel();
        }
        this._kbManager.open(domainId);
    }

    async _openKnowledgeGraphTab(projectId) {
        if (!projectId) {
            const activeNode = this._explorerPanel?._tree?.getActiveNode();
            if (activeNode) {
                const key = activeNode.key || '';
                if (key.startsWith('project:')) projectId = key.substring(8);
                else if (key.startsWith('mount:')) projectId = key.substring(6);
                else if (key.startsWith('pfile:') || key.startsWith('pdir:') || key.startsWith('mfile:') || key.startsWith('mdir:')) {
                    projectId = key.split(':')[1];
                }
            }
            if (!projectId) projectId = 'Examples';
        }
        const tabKey = 'detail:kb-graph';
        // Reuse existing tab if open
        if (this._tabBar._tabs.has(tabKey)) {
            this._tabBar.activate(tabKey);
            return;
        }
        const { GraphPanel } = await import('./knowledge-graph/GraphPanel.js');
        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'display:flex;flex-direction:column;height:100%;background:#ffffff';
        const container = document.createElement('div');
        container.className = 'kg-panel';
        wrapper.appendChild(container);
        const gp = new GraphPanel(projectId, {
            onEntityNavigate: (entity) => {
                const node = this._explorerPanel?._tree?.findFirst(n =>
                    n.key?.includes(entity.id.split(':').pop())
                );
                if (node) node.setActive(true);
            },
        });
        gp._buildUI(container);
        this._openDetailTab(tabKey, 'Knowledge Graph', wrapper, { undockable: true, preview: true });
    }

    async _openKnowledgeGraph(projectId, entityId) {
        // Determine project from active context
        if (!projectId) {
            const activeNode = this._explorerPanel?._tree?.getActiveNode();
            if (activeNode) {
                const key = activeNode.key || '';
                if (key.startsWith('project:')) projectId = key.substring(8);
                else if (key.startsWith('mount:')) projectId = key.substring(6);
                else if (key.startsWith('pfile:') || key.startsWith('pdir:') || key.startsWith('mfile:') || key.startsWith('mdir:')) {
                    const parts = key.split(':');
                    projectId = parts[1];
                }
            }
            if (!projectId) projectId = 'Examples';
        }

        const { GraphPanel } = await import('./knowledge-graph/GraphPanel.js');
        const panel = new GraphPanel(projectId, {
            initialEntityId: entityId || null,
            onEntityClick: (entity) => {
                // Don't auto-navigate - detail panel has a Navigate button
            },
            onEntityNavigate: (entity) => {
                // Called when user explicitly clicks "Navigate" in KG detail panel
                const node = this._explorerPanel?._tree?.findFirst(n =>
                    n.key?.includes(entity.id.split(':').pop())
                );
                if (node) node.setActive(true);
            },
        });
        panel.open();
    }

    _openDetailTab(tabKey, label, element, opts = {}) {
        // If undocked, bring to front
        const undocked = this._undockedPanels.get(tabKey);
        if (undocked) { undocked.front(); return; }

        // Store element
        if (!this._detailTabs.has(tabKey)) {
            this._detailTabs.set(tabKey, { element, title: label });
        }

        this._tabBar.addTab({
            key: tabKey,
            label,
            tooltip: label,
            type: 'detail',
            closable: true,
            undockable: true,
            preview: opts.preview || false,
        });
    }

    _buildDetailBars(key) {
        const detail = this._detailTabs.get(key);
        const title = detail?.title || 'Detail';
        const frag = document.createDocumentFragment();

        // First bar: breadcrumb + undock + close
        const bar = document.createElement('div');
        bar.className = 'service-top-bar';
        const titleEl = document.createElement('span');
        titleEl.className = 'service-top-bar-title';
        titleEl.textContent = title;
        bar.appendChild(titleEl);

        const spacer = document.createElement('span');
        spacer.style.cssText = 'flex:1';
        bar.appendChild(spacer);

        const undockBtn = document.createElement('button');
        undockBtn.className = 'info-bar-text-btn';
        undockBtn.innerHTML = '<i class="fa-solid fa-up-right-from-square" style="font-size:12px;color:#555555"></i>';
        undockBtn.title = 'Undock to floating panel';
        undockBtn.addEventListener('click', () => this._tabBar.undockTab(key));
        bar.appendChild(undockBtn);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'info-bar-text-btn';
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark" style="font-size:12px;color:#555555"></i>';
        closeBtn.title = 'Close';
        closeBtn.addEventListener('click', () => this._tabBar.closeTab(key));
        bar.appendChild(closeBtn);

        frag.appendChild(bar);

        return frag;
    }

    _buildMediaBars(key) {
        // Parse key "media:{projectId}:{filename}" where projectId may contain ':'
        const rest = key.substring(6); // strip "media:"
        const colonIdx = rest.indexOf(':');
        const name = rest.substring(0, colonIdx);
        const filename = rest.substring(colonIdx + 1);
        const hostPath = this._explorerPanel?._mountHostPaths?.[name] || '';

        const frag = document.createDocumentFragment();

        // First bar: breadcrumbs
        const bar = document.createElement('div');
        bar.className = 'service-top-bar';
        const title = document.createElement('span');
        title.className = 'service-top-bar-title';
        const crumbParts = ['Projects', name, filename];
        crumbParts.forEach((text, i) => {
            if (i > 0) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-sep';
                sep.textContent = ' / ';
                title.appendChild(sep);
            }
            const span = document.createElement('span');
            span.className = 'breadcrumb-segment';
            if (i === crumbParts.length - 1) span.classList.add('breadcrumb-current');
            span.textContent = text;
            title.appendChild(span);
        });
        const spacerM = document.createElement('span');
        spacerM.style.cssText = 'flex:1';
        bar.appendChild(title);
        bar.appendChild(spacerM);

        const undockBtnM = document.createElement('button');
        undockBtnM.className = 'info-bar-text-btn';
        undockBtnM.innerHTML = '<i class="fa-solid fa-up-right-from-square" style="font-size:12px;color:#555555"></i>';
        undockBtnM.title = 'Undock to floating panel';
        undockBtnM.addEventListener('click', () => this._tabBar.undockTab(key));
        bar.appendChild(undockBtnM);

        const closeBtnM = document.createElement('button');
        closeBtnM.className = 'info-bar-text-btn';
        closeBtnM.innerHTML = '<i class="fa-solid fa-xmark" style="font-size:12px;color:#555555"></i>';
        closeBtnM.title = 'Close';
        closeBtnM.addEventListener('click', () => this._tabBar.closeTab(key));
        bar.appendChild(closeBtnM);

        frag.appendChild(bar);

        // Second bar: File Details button only (no save for media)
        const secondBar = this._buildSecondBar();
        const leftGroup = document.createElement('div');
        leftGroup.className = 'service-second-bar-left';

        const detailBtn = document.createElement('button');
        detailBtn.className = 'info-bar-text-btn';
        detailBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" fill="#4a90d9"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
        detailBtn.title = 'File Details';
        detailBtn.addEventListener('click', () => {
            const treePrefix = isMount ? 'm' : 'p';
            const treeKey = `${treePrefix}file:${name}:${filename}`;
            this._tabBar.activate('workspace');
            const node = this._explorerPanel._tree?.findKey(treeKey);
            if (node) node.setActive(true);
        });
        leftGroup.appendChild(detailBtn);

        secondBar.appendChild(leftGroup);

        // PDF zoom controls — centered in the bar
        const ext = filename.split('.').pop().toLowerCase();
        if (ext === 'pdf') {
            const viewer = this._mediaViewers.get(key);

            const centerGroup = document.createElement('div');
            centerGroup.className = 'pdf-zoom-controls';

            const S = 'stroke="#555" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

            const zoomOutBtn = document.createElement('button');
            zoomOutBtn.className = 'info-bar-text-btn';
            zoomOutBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" ${S}><circle cx="11" cy="11" r="8"/><line x1="7" y1="11" x2="15" y2="11"/></svg>`;
            zoomOutBtn.title = 'Zoom Out';
            zoomOutBtn.addEventListener('click', () => { if (viewer) viewer.zoomOut(); });
            centerGroup.appendChild(zoomOutBtn);

            const zoomLabel = document.createElement('span');
            zoomLabel.className = 'pdf-zoom-label';
            zoomLabel.textContent = '100%';
            centerGroup.appendChild(zoomLabel);

            const zoomInBtn = document.createElement('button');
            zoomInBtn.className = 'info-bar-text-btn';
            zoomInBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" ${S}><circle cx="11" cy="11" r="8"/><line x1="7" y1="11" x2="15" y2="11"/><line x1="11" y1="7" x2="11" y2="15"/></svg>`;
            zoomInBtn.title = 'Zoom In';
            zoomInBtn.addEventListener('click', () => { if (viewer) viewer.zoomIn(); });
            centerGroup.appendChild(zoomInBtn);

            const fitBtn = document.createElement('button');
            fitBtn.className = 'info-bar-text-btn';
            fitBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" ${S}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
            fitBtn.title = 'Fit to Width';
            fitBtn.addEventListener('click', () => { if (viewer) viewer.fitToWidth(); });
            centerGroup.appendChild(fitBtn);

            if (viewer) {
                viewer.onZoomChange = (pct) => { zoomLabel.textContent = pct + '%'; };
            }

            secondBar.appendChild(centerGroup);
        }

        frag.appendChild(secondBar);
        return frag;
    }

    _openDocumentTab(doc, opts = {}) {
        const tabKey = `doc:${doc.category}:${doc.name}`;
        this._documentTabs.set(tabKey, doc);
        // addTab synchronously fires the tab-activation callback, which
        // runs the 'doc:' case in app-tabs.js and calls
        // documentViewer.show(doc) + updates the TOC in its .then().
        // Do NOT call documentViewer.show(doc) again here - that would
        // race the tab handler's show() and render the PDF twice,
        // because both show() calls find _pdfState still null (the
        // first one hasn't created state yet when the second starts)
        // and so neither one cleans up the other's pageDivs.
        this._tabBar.addTab({
            key: tabKey,
            label: doc.name,
            type: 'document',
            closable: true,
            undockable: true,
            preview: !!opts.preview,
        });
    }

    _updateTocForTab(key) {
        if (!this._tocPanel) return;

        if (key && key.startsWith('notebook:')) {
            this._tocPanel.setNotebookMode();
        } else if (key && key.startsWith('doc:')) {
            // Document viewer — markdown or PDF
            const dv = this._documentViewer;
            if (dv && dv._pdfState && dv._pdfState.pdfDoc) {
                // PDF document
                this._tocPanel.setPdfMode(
                    dv._pdfState.pdfDoc,
                    dv._pdfState.pageDivs,
                    dv._wrapper,
                );
            } else if (dv && dv._content) {
                // Markdown document
                this._tocPanel.setMarkdownMode(dv._content, dv._wrapper);
            } else {
                this._tocPanel.clearMode();
            }
        } else if (key && key.startsWith('pyfile:')) {
            // File editor - check if markdown preview is active
            const editor = this._fileEditors.get(key);
            if (editor && editor._previewEl && editor._previewEl.style.display !== 'none') {
                this._tocPanel.setMarkdownMode(editor._previewEl, editor._el);
            } else {
                this._tocPanel.clearMode();
            }
        } else {
            this._tocPanel.clearMode();
        }
    }

    _buildWorkspaceBars() {
        const frag = document.createDocumentFragment();

        const bar = document.createElement('div');
        bar.className = 'service-top-bar';

        const title = document.createElement('span');
        title.className = 'service-top-bar-title';
        title.textContent = 'Explorer';
        this._workspaceTitleEl = title;
        bar.appendChild(title);

        const spacer = document.createElement('span');
        spacer.style.cssText = 'flex:1';
        bar.appendChild(spacer);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'info-bar-text-btn';
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark" style="font-size:11px;color:#555555"></i>';
        closeBtn.title = 'Close';
        closeBtn.addEventListener('click', () => this._tabBar.closeTab('workspace'));
        bar.appendChild(closeBtn);

        frag.appendChild(bar);
        this._workspaceBreadcrumbBar = this._buildSecondBar();
        frag.appendChild(this._workspaceBreadcrumbBar);
        return frag;
    }

    _buildDocumentBars(key) {
        const frag = document.createDocumentFragment();

        const bar = document.createElement('div');
        bar.className = 'service-top-bar';

        const title = document.createElement('span');
        title.className = 'service-top-bar-title';
        // Extract document name from key "doc:category:name"
        const parts = key.substring(4).split(':');
        title.textContent = parts.length > 1 ? parts.slice(1).join(':') : key;
        bar.appendChild(title);

        const spacer = document.createElement('span');
        spacer.style.flex = '1';
        bar.appendChild(spacer);
        // Undock button
        const undockBtn = document.createElement('button');
        undockBtn.className = 'info-bar-text-btn';
        undockBtn.innerHTML = '<i class="fa-solid fa-up-right-from-square" style="font-size:11px;color:#555555"></i>';
        undockBtn.title = 'Undock to floating panel';
        undockBtn.addEventListener('click', () => this._tabBar.undockTab(key));
        bar.appendChild(undockBtn);
        // Close button
        const closeBtn = document.createElement('button');
        closeBtn.className = 'info-bar-text-btn';
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark" style="font-size:11px;color:#555555"></i>';
        closeBtn.title = 'Close';
        closeBtn.addEventListener('click', () => this._tabBar.closeTab(key));
        bar.appendChild(closeBtn);

        frag.appendChild(bar);

        // Second bar with breadcrumbs
        const secondBar = this._buildSecondBar();
        const category = parts[0] || '';
        const docName = parts.slice(1).join(':') || '';
        const crumbs = ['Knowledge Base', category, docName].filter(Boolean);
        crumbs.forEach((text, i) => {
            if (i > 0) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-sep';
                sep.textContent = ' / ';
                secondBar.appendChild(sep);
            }
            const span = document.createElement('span');
            span.className = 'breadcrumb-segment';
            if (i === crumbs.length - 1) span.classList.add('breadcrumb-current');
            span.textContent = text;
            secondBar.appendChild(span);
        });
        frag.appendChild(secondBar);
        return frag;
    }

    _openGitCommitTab(repoPath, commit) {
        const tabKey = 'git-commit';
        if (!this._gitCommits) this._gitCommits = new Map();
        this._gitCommits.set(tabKey, { repoPath, commit });
        // Always update the viewer directly — activate() is a no-op when tab is already active
        this._gitCommitViewer.show(repoPath, commit);
        if (!this._tabBar._tabs.has(tabKey)) {
            this._tabBar.addTab({
                key: tabKey,
                label: 'Git History',
                type: 'git-commit',
                closable: true,
            });
        } else {
            this._tabBar.activate(tabKey);
        }
    }

    _buildGitCommitBars(_key) {
        const entry = this._gitCommits?.get('git-commit');
        const repoPath = entry?.repoPath || '';
        const repoLabel = repoPath.split('/').pop() || repoPath;
        const commit = entry?.commit;

        const frag = document.createDocumentFragment();

        // Top bar: breadcrumbs — "repoLabel | short_hash"
        const bar = document.createElement('div');
        bar.className = 'service-top-bar';
        [repoLabel, commit?.short_hash || ''].forEach((text, i) => {
            if (i > 0) {
                const sep = document.createElement('span');
                sep.className = 'breadcrumb-sep';
                sep.textContent = ' / ';
                bar.appendChild(sep);
            }
            const span = document.createElement('span');
            span.className = 'breadcrumb-segment';
            if (i === 1) span.classList.add('breadcrumb-current');
            span.textContent = text;
            bar.appendChild(span);
        });
        frag.appendChild(bar);

        // Second bar: commit message
        const secondBar = this._buildSecondBar();
        if (commit?.message) {
            const msg = document.createElement('span');
            msg.className = 'breadcrumb-segment breadcrumb-current';
            msg.textContent = commit.message;
            secondBar.appendChild(msg);
        }
        frag.appendChild(secondBar);
        return frag;
    }

    _buildSecondBar() {
        const bar = document.createElement('div');
        bar.className = 'service-second-bar';
        return bar;
    }

    _updateWorkspaceTitle(section) {
        if (this._workspaceTitleEl) {
            this._workspaceTitleEl.textContent = section;
        }
        if (this._tabBar._tabs.has('workspace')) {
            this._tabBar.setTabLabel('workspace', section);
        }
    }

    _getBreadcrumbIcons() {
        return {
            delete: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" fill="#f4a0a0"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
            rundag: '<i class="fa-solid fa-play" style="font-size:13px;color:#4caf50;-webkit-text-stroke:1px #555;paint-order:stroke fill"></i>',
            compare: '<i class="fa-solid fa-code-compare" style="font-size:13px;color:#7cb3a0;-webkit-text-stroke:1px #555;paint-order:stroke fill"></i>',
            popout: '<i class="fa-solid fa-chart-simple" style="font-size:16px;color:#42a5f5;-webkit-text-stroke:1px #555;paint-order:stroke fill"></i>',
            download: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
            newfile: '<i class="fa-solid fa-file-circle-plus" style="font-size:14px;color:#42a5f5"></i>',
            newfolder: '<i class="fa-solid fa-folder-plus" style="font-size:14px;color:#f0c040"></i>',
            importnb: '<i class="fa-solid fa-file-import" style="font-size:14px;color:#ab82d4"></i>',
            upload: '<i class="fa-solid fa-upload" style="font-size:14px;color:#f0a040"></i>',
            create: '<i class="fa-solid fa-plus" style="font-size:14px;color:#4caf50"></i>',
            clone: '<i class="fa-solid fa-code-branch" style="font-size:14px;color:#6fa374"></i>',
            addmount: '<i class="fa-solid fa-hard-drive" style="font-size:14px;color:#8fbcf0"></i>',
        };
    }

    _updateWorkspaceBreadcrumbs(info) {
        if (!this._workspaceBreadcrumbBar) return;
        this._workspaceBreadcrumbBar.innerHTML = '';
        const { crumbs, rootCount } = info;

        // Root level with actions: icons on left, count on right
        if (crumbs.length === 1 && rootCount !== undefined && info.actions?.length) {
            const section = crumbs[0];
            const singularMap = { Projects: 'Project', 'Environments': 'Environment', 'Knowledge Base': 'Document', Mounts: 'Mount' };
            const singular = singularMap[section] || section;

            const left = document.createElement('div');
            left.className = 'service-second-bar-left';
            left.style.cssText = 'display:flex;align-items:center;gap:4px';
            const ICONS = this._getBreadcrumbIcons();
            for (const action of info.actions) {
                const btn = document.createElement('button');
                btn.className = 'cell-delete-btn';
                btn.style.opacity = '1';
                btn.innerHTML = ICONS[action.icon] || '';
                btn.title = action.title || '';
                btn.addEventListener('click', action.handler);
                left.appendChild(btn);
            }

            const right = document.createElement('div');
            right.className = 'service-second-bar-right';
            const count = document.createElement('span');
            count.className = 'breadcrumb-segment';
            count.textContent = `${rootCount} ${rootCount !== 1 ? section : singular}`;
            right.appendChild(count);

            this._workspaceBreadcrumbBar.appendChild(left);
            this._workspaceBreadcrumbBar.appendChild(right);
            return;
        }

        // Root level without actions: label on left, count on right
        if (crumbs.length === 1 && rootCount !== undefined) {
            const section = crumbs[0];
            const singularMap = { Projects: 'Project', 'Environments': 'Environment', 'Knowledge Base': 'Document', Mounts: 'Mount' };
            const singular = singularMap[section] || section;
            const actionMap = { Projects: 'Create Project', 'Environments': 'Create Environment', 'Knowledge Base': 'Upload Document' };
            const actionText = actionMap[section] || `Create ${singular}`;

            const left = document.createElement('div');
            left.className = 'service-second-bar-left';
            const action = document.createElement('span');
            action.className = 'breadcrumb-segment breadcrumb-current';
            action.textContent = actionText;
            left.appendChild(action);

            const right = document.createElement('div');
            right.className = 'service-second-bar-right';
            const count = document.createElement('span');
            count.className = 'breadcrumb-segment';
            count.textContent = `${rootCount} ${rootCount !== 1 ? section : singular}`;
            right.appendChild(count);

            this._workspaceBreadcrumbBar.appendChild(left);
            this._workspaceBreadcrumbBar.appendChild(right);
            return;
        }

        // If actions are present, breadcrumbs go to top bar, icons go to second bar (left)
        if (info.actions && info.actions.length) {
            // Breadcrumbs in top bar
            if (this._workspaceTitleEl) {
                this._workspaceTitleEl.innerHTML = '';
                crumbs.forEach((text, i) => {
                    if (i > 0) {
                        const sep = document.createElement('span');
                        sep.className = 'breadcrumb-sep';
                        sep.textContent = ' / ';
                        this._workspaceTitleEl.appendChild(sep);
                    }
                    const span = document.createElement('span');
                    span.className = 'breadcrumb-segment';
                    if (i === crumbs.length - 1) span.classList.add('breadcrumb-current');
                    span.textContent = text;
                    this._workspaceTitleEl.appendChild(span);
                });
            }

            // Action icons in second bar (left-aligned)
            const left = document.createElement('div');
            left.className = 'service-second-bar-left';
            left.style.cssText = 'display:flex;align-items:center;gap:4px';
            const ICONS = this._getBreadcrumbIcons();
            for (const action of info.actions) {
                const btn = document.createElement('button');
                btn.className = 'cell-delete-btn';
                btn.style.opacity = '1';
                btn.innerHTML = ICONS[action.icon] || '';
                btn.title = action.title || '';
                btn.addEventListener('click', action.handler);
                left.appendChild(btn);
            }
            this._workspaceBreadcrumbBar.appendChild(left);
        } else {
            // Normal: breadcrumbs in second bar
            crumbs.forEach((text, i) => {
                if (i > 0) {
                    const sep = document.createElement('span');
                    sep.className = 'breadcrumb-sep';
                    sep.textContent = ' / ';
                    this._workspaceBreadcrumbBar.appendChild(sep);
                }
                const span = document.createElement('span');
                span.className = 'breadcrumb-segment';
                if (i === crumbs.length - 1) span.classList.add('breadcrumb-current');
                span.textContent = text;
                this._workspaceBreadcrumbBar.appendChild(span);
            });
        }
    }

    _checkServiceStatus(key, led, label) {
        const names = { airflow: 'Airflow', mlflow: 'MLflow', minio: 'MinIO', evidently: 'Evidently' };
        const name = names[key] || key;
        fetch(`/${key}/`)
            .then(res => {
                if (res.ok) {
                    led.classList.add('connected');
                    led.classList.remove('disconnected');
                    label.textContent = 'Connected';
                    notify.success(`${name} connected`);
                } else {
                    led.classList.add('disconnected');
                    led.classList.remove('connected');
                    label.textContent = 'unreachable';
                    notify.error(`${name} unreachable`);
                }
            })
            .catch(() => {
                led.classList.add('disconnected');
                led.classList.remove('connected');
                label.textContent = 'unreachable';
                notify.error(`${name} unreachable`);
            });
    }

    _onTabClosed(key) {
        // Clear last content key if the closed tab was our context reference
        if (this._lastContentKey === key) this._lastContentKey = null;

        // Clean up notebook editor when its tab is closed
        if (key.startsWith('notebook:')) {
            const entry = this._editors.get(key);
            if (entry) {
                // Stop kernel for this notebook if running
                if (entry.venv) {
                    this._client.stopKernel(entry.editor.notebookKey);
                }
                // Close the notebook on the server (leaves room)
                entry.editor.closeNotebook();
                // Unregister event listeners
                entry.editor.destroy?.();
                // Remove DOM container
                entry.container.remove();
                this._editors.delete(key);
            }
            // If no notebook tab is active after close, clear notebook state
            const activeKey = this._tabBar.activeKey;
            if (!activeKey || !activeKey.startsWith('notebook:')) {
                this._activeEditorKey = null;
                this._currentProject = null;
                this._currentNotebook = null;
                this._activeVenv = null;
            }
        }
        // Clean up pyfile editor when its tab is closed
        if (key.startsWith('pyfile:')) {
            const editor = this._fileEditors.get(key);
            if (editor) {
                editor.destroy();
                this._fileEditors.delete(key);
            }
        }
        // Clean up detail tab when closed (only if not undocked)
        if (key.startsWith('detail:') && !this._undockedPanels.has(key)) {
            this._detailTabs.delete(key);
        }
        // Clean up media viewer when its tab is closed
        if (key.startsWith('media:')) {
            const viewer = this._mediaViewers.get(key);
            if (viewer) {
                viewer.destroy();
                this._mediaViewers.delete(key);
            }
        }
        // Clean up document viewer when its tab is closed
        if (key.startsWith('doc:')) {
            this._documentTabs.delete(key);
            // Dispose the per-tab viewer so its PDF.js doc + rendered page
            // canvases get freed (otherwise the bitmaps leak in browser RAM).
            const perTab = this._documentViewers.get(key);
            if (perTab) {
                perTab.clear();
                this._documentViewers.delete(key);
            }
            // Singleton helper: clear if no doc tabs remain so its
            // _currentDoc state doesn't linger.
            const hasOtherDocTabs = [...this._documentTabs.keys()].length > 0;
            if (!hasOtherDocTabs && this._documentViewer) {
                this._documentViewer.clear();
            }
        }
        // Clean up markdown preview tab
        if (key.startsWith('mdpreview:')) {
            const previewData = this._mdPreviewTabs?.get(key);
            if (previewData) {
                // Remove onContentChange listener from source editor
                const sourceEditor = this._fileEditors.get(previewData.sourceKey);
                if (sourceEditor) sourceEditor.onContentChange = null;
            }
            this._mdPreviewTabs?.delete(key);
        }
        // Hide persistent service wrapper (visibility keeps iframe connections alive)
        if (this._serviceIframes[key]) {
            this._serviceIframes[key].style.visibility = 'hidden';
            this._serviceIframes[key].style.position = 'absolute';
            this._serviceIframes[key].style.width = '0';
            this._serviceIframes[key].style.height = '0';
            this._serviceIframes[key].style.overflow = 'hidden';
        }
        this._syncIconBar();
    }

    _generateUserName() {
        const adjectives = [
            'Swift', 'Bright', 'Calm', 'Dark', 'Eager',
            'Fair', 'Grand', 'Happy', 'Iron', 'Keen'
        ];
        const nouns = [
            'Fox', 'Owl', 'Bear', 'Wolf', 'Hawk',
            'Lynx', 'Crow', 'Deer', 'Hare', 'Dove'
        ];
        const adj = adjectives[Math.floor(Math.random() * adjectives.length)];
        const noun = nouns[Math.floor(Math.random() * nouns.length)];
        return `${adj}${noun}`;
    }
}

// --- Bootstrap ---
const app = new App();
app.init().catch(err => console.error('App init failed:', err));
