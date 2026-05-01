/**
 * KnowledgeBaseMonitorPanel - floating jsPanel that polls /api/domains/{domain_id}/status
 * and renders combined progress for both the Vector RAG and the GraphRAG layers
 * of a knowledge base. Replaces the old GraphRebuildMonitorPanel which was
 * graph-only.
 *
 * Header has a Domain selector populated from `domainState.getDomains()`,
 * filtered to Domains with `has_knowledge: true` (capability-only Domains
 * like `general` have nothing to monitor). Caller can pre-select via
 * `open(domainId)`; default is the upload's target Domain when launched
 * from the upload flow, otherwise the first knowledge-bearing Domain.
 */

import { domainState } from '../domain-state.js';

const POLL_MS = 2000;

// Mirrors backend kb.py:_domain_collection. Convention only: every
// Domain (including noted) lives at `<domain_id>__corpus`. The legacy
// noted_corpus name is migrated to noted__corpus on noted-graph boot.
function _corpusCollection(domainId) {
    return `${domainId}__corpus`;
}

// Manual rebuild action. Auto-recluster runs after every doc-add queue
// drain (see `_doc_add_worker` in graph/app/domain_registry.py), so users
// no longer need to fire a manual "Recluster Now" - the only legitimate
// manual escape hatch is a Full Rebuild (full re-extraction, ~25 min)
// for a graph that's drifted irrecoverably.
const REBUILD_ACTION = {
    path: 'rebuild', label: 'Full Rebuild', running: 'Rebuilding...',
    etaNote: 'full re-extraction, ~25 minutes',
};

/** Pick a sensible default Domain when none is passed: prefer the first
 *  knowledge-bearing active Domain, otherwise the first knowledge-bearing
 *  Domain overall, otherwise null (no knowledge Domain exists - the panel
 *  shows an empty state). */
function _pickDefaultDomain() {
    const active = domainState.getActiveDomains();
    const all = domainState.getDomains();
    for (const id of active) {
        const d = all.find((x) => x.domain_id === id);
        if (d && d.has_knowledge) return id;
    }
    const firstWithKnowledge = all.find((d) => d.has_knowledge);
    return firstWithKnowledge ? firstWithKnowledge.domain_id : null;
}

export class KnowledgeBaseMonitorPanel {
    constructor() {
        this._panel = null;
        this._timer = null;
        this._lastDone = 0;
        this._lastDoneAt = 0;
        this._els = {};
        this._reclusterInFlight = false;
        this._domainId = null;
    }

    /** Open the Monitor. Optional `domainId` pre-selects the Domain in
     *  the header dropdown; if omitted (or the id has no knowledge half),
     *  we fall back to `_pickDefaultDomain()`. Reusing an open panel
     *  switches its target Domain to the requested one. */
    open(domainId = null) {
        const requested = domainId && domainState.getDomain(domainId)?.has_knowledge
            ? domainId : _pickDefaultDomain();
        if (this._panel) {
            this._panel.front();
            if (requested && requested !== this._domainId) {
                this._setDomain(requested);
            }
            return;
        }
        this._domainId = requested;
        this._panel = jsPanel.create({
            id: 'knowledge-base-monitor-panel',
            headerTitle: '<img src="static/images/arcadedb.png" width="13" height="13" style="vertical-align:middle;margin-right:6px"/>Knowledge Base Monitor',
            theme: 'none',
            borderRadius: '5px',
            border: '1px solid var(--border-color)',
            boxShadow: 3,
            position: 'center',
            panelSize: { width: 560, height: 620 },
            headerControls: { minimize: 'remove', smallify: 'remove', normalize: 'remove', maximize: 'remove' },
            onclosed: () => {
                this._stopPolling();
                this._panel = null;
            },
            callback: (panel) => {
                this._panel = panel;
                panel.content.style.overflowY = 'auto';
                panel.content.style.padding = '0';
                this._buildUI();
                this._startPolling();
            },
        });
    }

    close() {
        if (this._panel) this._panel.close();
    }

    _buildUI() {
        const root = document.createElement('div');
        root.style.cssText = 'padding:14px 16px;font-size:13px;color:var(--text-color)';
        const domains = domainState.getDomains().filter((d) => d.has_knowledge);
        const options = domains.map((d) =>
            `<option value="${d.domain_id}"${d.domain_id === this._domainId ? ' selected' : ''}>${d.name || d.domain_id}</option>`
        ).join('');
        root.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:8px">
                <span style="color:var(--text-secondary);font-size:11px;display:flex;align-items:center;gap:6px">
                    Domain
                    <select id="grm-domain-select" class="rm-input" style="padding:2px 22px 2px 6px;font-size:11px;border:1px solid var(--border-color);background-color:#fdfaf3">${options}</select>
                </span>
                <span id="grm-poll-state" class="grm-pill grm-pill-on">live</span>
            </div>

            <div id="grm-recluster-banner" class="grm-card" style="display:none;background:#fff8e1;border:1px solid #ffd54f;color:#5d4e1a">
                <div style="display:flex;align-items:center;gap:8px">
                    <i class="fa-solid fa-triangle-exclamation" style="color:#f9a825"></i>
                    <div style="flex:1">
                        <div style="font-weight:500;font-size:12px">Knowledge graph is behind the corpus</div>
                        <div id="grm-recluster-reason" style="font-size:11px;color:#7b6a30;margin-top:2px"></div>
                        <div id="grm-action-note" style="font-size:11px;color:#7b6a30;margin-top:2px;font-style:italic">${REBUILD_ACTION.etaNote}</div>
                    </div>
                    <button id="grm-recluster-btn" class="rm-btn" style="padding:4px 12px;font-size:11px;flex-shrink:0">${REBUILD_ACTION.label}</button>
                </div>
            </div>

            <div class="grm-card">
                <div style="font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Vector RAG (ChromaDB)</div>
                <div class="grm-row"><span class="grm-k">total chunks</span><span id="grm-vec-chunks" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">sources indexed</span><span id="grm-vec-sources" class="grm-v">-</span></div>
                <div class="grm-row" style="align-items:flex-start"><span class="grm-k">by format</span><span id="grm-vec-formats" class="grm-fmt-chips">-</span></div>
            </div>

            <div class="grm-card">
                <div style="font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">GraphRAG (ArcadeDB)</div>
                <div class="grm-row"><span class="grm-k">phase</span><span id="grm-phase" class="grm-phase grm-phase-idle">idle</span></div>
                <div class="grm-row"><span class="grm-k">rebuild_in_progress</span><span id="grm-in-progress" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">started_at</span><span id="grm-started-at" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">elapsed</span><span id="grm-elapsed" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">graph entities</span><span id="grm-db-entities" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">graph relationships</span><span id="grm-db-rels" class="grm-v">0</span></div>
            </div>

            <div class="grm-card">
                <div class="grm-row"><span class="grm-k">chunks extracted</span><span id="grm-chunks" class="grm-v">0 / 0</span></div>
                <div class="grm-progress-outer"><div id="grm-progress-bar" class="grm-progress-inner"></div></div>
                <div class="grm-progress-label">
                    <span id="grm-progress-pct">0.0%</span>
                    <span id="grm-rate">-</span>
                </div>
                <div class="grm-row" style="margin-top:10px">
                    <span class="grm-k">current source</span>
                    <span id="grm-current-doc" class="grm-v grm-mono" style="text-align:right;overflow:hidden;text-overflow:ellipsis;max-width:55%">-</span>
                </div>
                <div class="grm-row"><span class="grm-k">entities accepted</span><span id="grm-entities" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">docs scanned</span><span id="grm-md-docs" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">communities</span><span id="grm-communities" class="grm-v">0 / 0 summarized</span></div>
            </div>

            <div id="grm-last-build" class="grm-card" style="display:none">
                <div style="font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Last completed build</div>
                <pre id="grm-last-build-json" style="margin:0;font-size:11px;color:var(--text-color);overflow:auto;max-height:120px"></pre>
            </div>

            <div id="grm-error-card" class="grm-card" style="display:none;background:var(--error-bg, #3a2020);color:var(--error-fg, #e57373)">
                <span id="grm-error-msg"></span>
            </div>
        `;
        this._panel.content.appendChild(root);

        for (const id of [
            'domain-select',
            'poll-state', 'recluster-banner', 'recluster-reason', 'action-note',
            'recluster-btn',
            'vec-chunks', 'vec-sources', 'vec-formats',
            'phase', 'in-progress', 'started-at', 'elapsed',
            'chunks', 'progress-bar', 'progress-pct', 'rate', 'current-doc',
            'entities', 'md-docs', 'communities', 'db-entities', 'db-rels',
            'last-build', 'last-build-json', 'error-card', 'error-msg',
        ]) {
            this._els[id] = document.getElementById('grm-' + id);
        }

        this._els['recluster-btn'].addEventListener('click', () => this._triggerAction());

        if (this._els['domain-select']) {
            this._els['domain-select'].addEventListener('change', (e) => {
                this._setDomain(e.target.value);
            });
        }
    }

    /** Switch the panel's target Domain. Resets cumulative counters
     *  (lastDone / lastDoneAt) so the rate / ETA don't carry over from
     *  the previous Domain, then re-ticks immediately. */
    _setDomain(domainId) {
        if (!domainId || domainId === this._domainId) return;
        this._domainId = domainId;
        this._lastDone = 0;
        this._lastDoneAt = 0;
        this._reclusterInFlight = false;
        if (this._els['domain-select']) this._els['domain-select'].value = domainId;
        this._tick();
    }

    _statusUrl() { return `api/domains/${this._domainId}/status`; }
    _reclusterUrl() { return `api/domains/${this._domainId}/recluster`; }
    _rebuildUrl() { return `api/domains/${this._domainId}/rebuild`; }
    _formatBreakdownUrl() {
        return `api/rag/index/format_breakdown?collection=${encodeURIComponent(_corpusCollection(this._domainId))}`;
    }

    _startPolling() {
        this._tick();
        this._timer = setInterval(() => this._tick(), POLL_MS);
    }

    _stopPolling() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    async _tick() {
        if (!this._domainId) {
            this._applyError('No knowledge-bearing Domain available to monitor.');
            return;
        }
        try {
            const [statusResp, fmtResp] = await Promise.all([
                fetch(this._statusUrl(), { cache: 'no-store' }),
                fetch(this._formatBreakdownUrl(), { cache: 'no-store' }).catch(() => null),
            ]);
            if (!statusResp.ok) throw new Error('HTTP ' + statusResp.status);
            const data = await statusResp.json();
            this._applyStatus(data);
            if (fmtResp && fmtResp.ok) {
                const fmt = await fmtResp.json();
                this._applyFormatBreakdown(fmt);
            } else {
                this._applyFormatBreakdown(null);
            }
        } catch (e) {
            this._applyError('noted backend unreachable: ' + e.message);
        }
    }

    _applyFormatBreakdown(data) {
        const el = this._els['vec-formats'];
        if (!el) return;
        if (!data || data.status === 'unavailable') {
            el.textContent = '-';
            return;
        }
        const by = data.by_format || {};
        const entries = Object.entries(by).sort((a, b) => b[1] - a[1]);
        if (entries.length === 0) {
            el.textContent = '-';
            return;
        }
        el.innerHTML = entries
            .map(([fmt, n]) => `<span class="grm-fmt-chip" data-fmt="${fmt}">${fmt} ${n}</span>`)
            .join('');
    }

    _applyStatus(data) {
        const pending = data.pending_recluster;
        const graph = data.graph || {};
        const inProgress = !!graph.rebuild_in_progress;
        const progress = graph.progress || {};

        // Auto-clear the in-flight flag from SERVER state, not UI state:
        // when neither pending nor in_progress is set, the backend has
        // finished the op we triggered. (The previous watcher checked
        // "is banner visible" - circular, so the button got stuck on
        // "Running..." after the op completed.)
        if (this._reclusterInFlight && !pending && !inProgress) {
            this._reclusterInFlight = false;
        }

        // Recluster banner: three states.
        //   1. We triggered an op and the backend is still running it
        //      -> "Running..." with live phase progress inline
        //   2. The KB has a pending_recluster marker and nothing's
        //      running -> show the action picker + "Run" button
        //   3. Otherwise hide the banner
        if (this._reclusterInFlight) {
            this._els['recluster-banner'].style.display = '';
            this._els['recluster-reason'].textContent =
                `${REBUILD_ACTION.running} - ${_runningProgressText(progress)}`;
            this._els['action-note'].textContent = REBUILD_ACTION.etaNote;
            this._els['recluster-btn'].disabled = true;
            this._els['recluster-btn'].textContent = 'Running...';
        } else if (pending && !inProgress) {
            this._els['recluster-banner'].style.display = '';
            const setAt = pending.set_at ? new Date(pending.set_at).toLocaleString() : 'unknown time';
            const reason = pending.reason ? ` - ${pending.reason}` : '';
            this._els['recluster-reason'].textContent = `Marked at ${setAt}${reason}`;
            this._els['action-note'].textContent = REBUILD_ACTION.etaNote;
            this._els['recluster-btn'].disabled = false;
            this._els['recluster-btn'].textContent = REBUILD_ACTION.label;
        } else {
            this._els['recluster-banner'].style.display = 'none';
        }

        // Vector RAG block
        const vec = data.vector || {};
        if (vec.error) {
            this._els['vec-chunks'].textContent = `error: ${vec.error}`;
            this._els['vec-sources'].textContent = '-';
        } else {
            this._els['vec-chunks'].textContent = vec.total_chunks ?? 0;
            this._els['vec-sources'].textContent = (vec.sources || []).length;
        }

        // Graph block - same as before but reading from data.graph
        // (`progress` is already in scope from the banner block above).
        const phase = progress.phase || 'idle';
        const phaseEl = this._els['phase'];
        phaseEl.textContent = phase;
        phaseEl.className = 'grm-phase grm-phase-' + phase;

        this._els['in-progress'].textContent = inProgress ? 'true' : 'false';

        const started = progress.started_at;
        // The builder's `progress` dict only carries `started_at` +
        // `duration_seconds` (set on completion). `finished_at` lives in
        // the sibling `last_build` block. Freeze the timer when the phase
        // is done OR rebuild_in_progress is false, using whichever
        // authoritative finished/duration source is available; otherwise
        // count up from start. Without this the timer grew forever past
        // completion (the previous code only checked progress.finished_at,
        // which was never populated).
        const lastBuild = data.last_build || {};
        const finishedAt = progress.finished_at || lastBuild.finished_at;
        const durationSec = progress.duration_seconds;
        const isDone = !inProgress && (progress.phase === 'done' || finishedAt || durationSec != null);
        this._els['started-at'].textContent = started || '-';
        if (started) {
            let elapsed;
            if (isDone) {
                elapsed = (typeof durationSec === 'number')
                    ? durationSec
                    : (finishedAt ? (Date.parse(finishedAt) - Date.parse(started)) / 1000 : 0);
            } else {
                elapsed = (Date.now() - Date.parse(started)) / 1000;
            }
            this._els['elapsed'].textContent = fmtDuration(elapsed);
        } else {
            this._els['elapsed'].textContent = '-';
        }

        const done = progress.extraction_chunks_done || 0;
        const total = progress.extraction_chunks_total || 0;
        this._els['chunks'].textContent = `${done} / ${total}`;
        const pct = total ? (done / total) * 100 : 0;
        this._els['progress-bar'].style.width = pct.toFixed(1) + '%';
        this._els['progress-pct'].textContent = pct.toFixed(1) + '%';

        const now = Date.now();
        if (this._lastDoneAt && done > this._lastDone) {
            const dt = (now - this._lastDoneAt) / 1000;
            const d = done - this._lastDone;
            const rate = d / dt;
            const remaining = total - done;
            if (rate > 0 && remaining > 0) {
                this._els['rate'].textContent =
                    `${(rate * 60).toFixed(1)} chunks/min · ETA ~ ${fmtDuration(remaining / rate)}`;
            } else {
                this._els['rate'].textContent = '';
            }
        }
        this._lastDone = done;
        this._lastDoneAt = now;

        const curDoc = progress.current_doc || '';
        const curIdx = progress.current_chunk_in_doc;
        this._els['current-doc'].textContent = curDoc
            ? (curIdx !== undefined ? `${curDoc}  #${curIdx}` : curDoc)
            : '-';

        this._els['entities'].textContent = progress.entities_accepted || 0;
        this._els['md-docs'].textContent = progress.md_docs || 0;
        this._els['communities'].textContent =
            (progress.communities_summarized || 0) + ' / ' + (progress.communities_total || 0) + ' summarized';

        const counts = graph.global_counts || {};
        this._els['db-entities'].textContent = counts.entities ?? 0;
        this._els['db-rels'].textContent = counts.relationships ?? 0;

        if (graph.last_build) {
            this._els['last-build'].style.display = '';
            this._els['last-build-json'].textContent = JSON.stringify(graph.last_build, null, 2);
        }

        this._els['error-card'].style.display = 'none';
        this._els['poll-state'].textContent = 'live';
        this._els['poll-state'].className = 'grm-pill grm-pill-on';
    }

    _applyError(message) {
        this._els['poll-state'].textContent = 'offline';
        this._els['poll-state'].className = 'grm-pill grm-pill-off';
        this._els['error-card'].style.display = '';
        this._els['error-msg'].textContent = message;
    }

    /** Fire the action chosen in the dropdown (recluster or rebuild) and
     * let the polling loop track progress + clear the in-flight flag when
     * the backend reports !pending && !inProgress. Synchronous on the
     * backend (recluster ~minutes, rebuild ~25 min); we don't await. */
    _triggerAction() {
        if (this._reclusterInFlight || !this._domainId) return;
        this._reclusterInFlight = true;
        this._els['recluster-btn'].disabled = true;
        this._els['recluster-btn'].textContent = 'Starting...';
        // Fire-and-forget. The next /status tick after the op completes
        // will clear _reclusterInFlight via _applyStatus's auto-clear.
        fetch(this._rebuildUrl(), { method: 'POST' })
            .catch((e) => {
                this._reclusterInFlight = false;
                this._applyError(`${REBUILD_ACTION.label} failed to start: ` + e.message);
            });
    }
}

/** Compose a one-line "extracting 12/29, 47 entities" status string from
 * the noted-graph progress dict, used in the running banner. */
function _runningProgressText(progress) {
    if (!progress) return 'starting...';
    const phase = progress.phase || 'starting';
    const done = progress.extraction_chunks_done;
    const total = progress.extraction_chunks_total;
    const ent = progress.entities_accepted;
    const cs = progress.communities_summarized;
    const ct = progress.communities_total;
    const parts = [`phase: ${phase}`];
    if (total) parts.push(`chunks ${done || 0}/${total}`);
    if (ent) parts.push(`${ent} entities`);
    if (ct) parts.push(`communities ${cs || 0}/${ct}`);
    if (progress.current_doc) parts.push(progress.current_doc);
    return parts.join(' · ');
}

function fmtDuration(seconds) {
    if (seconds === undefined || seconds === null) return '-';
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const r = s % 60;
    if (h > 0) return `${h}h ${m}m ${r}s`;
    if (m > 0) return `${m}m ${r}s`;
    return `${r}s`;
}
