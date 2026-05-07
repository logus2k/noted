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
};

// Phase sequences per operation. Mirrors the order in
// noted/graph/app/research_builder.py — keep in sync when phases are
// added/reordered there. Each entry maps the backend `phase` string to
// a human-readable station label. The `operation` field on the progress
// dict picks which sequence to render.
const PHASE_SEQUENCES = {
    rebuild: [
        { key: 'scanning',       label: 'Scanning' },
        { key: 'extracting',     label: 'Extracting' },
        { key: 'sameas',         label: 'sameAs' },
        { key: 'merge_identity', label: 'Merge identity' },
        { key: 'similar_to',     label: 'similarTo' },
        { key: 'analytics',      label: 'Analytics' },
        { key: 'summarizing',    label: 'Summaries' },
        { key: 'caching',        label: 'Caching' },
        { key: 'writing',        label: 'Writing' },
        { key: 'done',           label: 'Done' },
    ],
    doc_add: [
        { key: 'adding_doc', label: 'Loading' },
        { key: 'extracting', label: 'Extracting' },
        { key: 'writing',    label: 'Writing' },
        { key: 'caching',    label: 'Caching' },
        { key: 'done',       label: 'Done' },
    ],
    recluster: [
        { key: 'recluster_loading', label: 'Loading' },
        { key: 'sameas',            label: 'sameAs' },
        { key: 'similar_to',        label: 'similarTo' },
        { key: 'analytics',         label: 'Analytics' },
        { key: 'summarizing',       label: 'Summaries' },
        { key: 'caching',           label: 'Caching' },
        { key: 'writing',           label: 'Writing' },
        { key: 'done',              label: 'Done' },
    ],
    doc_remove: [
        { key: 'removing_doc', label: 'Removing' },
        { key: 'caching',      label: 'Caching' },
        { key: 'done',         label: 'Done' },
    ],
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
            headerTitle: '<i class="fa-solid fa-landmark" style="color:#ffffff;-webkit-text-stroke:1.5px #666666;paint-order:stroke fill;margin-right:6px"></i>Knowledge Base Monitor',
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

            <div id="grm-failed-banner" class="grm-card" style="display:none;background:#ffeaea;border:1px solid #ef9a9a;color:#8e3a3a">
                <div style="display:flex;align-items:center;gap:8px">
                    <i class="fa-solid fa-circle-exclamation" style="color:#e53935"></i>
                    <div style="flex:1">
                        <div style="font-weight:500;font-size:12px">Last build failed</div>
                        <div id="grm-failed-meta" style="font-size:11px;color:#8e3a3a;margin-top:2px"></div>
                    </div>
                    <button id="grm-failed-btn" class="rm-btn" style="padding:4px 12px;font-size:11px;flex-shrink:0">Retry</button>
                </div>
            </div>

            <div id="grm-recluster-banner" class="grm-card" style="display:none;background:#fff8e1;border:1px solid #ffd54f;color:#5d4e1a">
                <div style="display:flex;align-items:center;gap:8px">
                    <i class="fa-solid fa-triangle-exclamation" style="color:#f9a825"></i>
                    <div style="flex:1">
                        <div style="font-weight:500;font-size:12px">Knowledge graph is behind the corpus</div>
                        <div id="grm-recluster-reason" style="font-size:11px;color:#7b6a30;margin-top:2px"></div>
                    </div>
                    <button id="grm-recluster-btn" class="rm-btn" style="padding:4px 12px;font-size:11px;flex-shrink:0">${REBUILD_ACTION.label}</button>
                </div>
            </div>

            <div class="grm-card">
                <div class="grm-row"><span id="grm-bar-label" class="grm-k">chunks extracted</span><span id="grm-chunks" class="grm-v">0 / 0</span></div>
                <div class="grm-progress-outer"><div id="grm-progress-bar" class="grm-progress-inner"></div></div>
                <div class="grm-progress-label">
                    <span id="grm-progress-pct">0.0%</span>
                    <span id="grm-rate">-</span>
                </div>
                <div class="grm-row" style="margin-top:10px">
                    <span class="grm-k">current source</span>
                    <span id="grm-current-doc" class="grm-v grm-mono" style="text-align:right;overflow:hidden;text-overflow:ellipsis;max-width:55%">-</span>
                </div>
                <div id="grm-sub-row" class="grm-row" style="display:none">
                    <span class="grm-k">step</span>
                    <span id="grm-sub" class="grm-v grm-mono" style="text-align:right;overflow:hidden;text-overflow:ellipsis;max-width:55%">-</span>
                </div>
                <div class="grm-row"><span class="grm-k">entities accepted</span><span id="grm-entities" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">docs scanned</span><span id="grm-md-docs" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">communities</span><span id="grm-communities" class="grm-v">0 / 0 summarized</span></div>
            </div>

            <div class="grm-card">
                <div style="font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Vector Database</div>
                <div class="grm-row"><span class="grm-k">total chunks</span><span id="grm-vec-chunks" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">sources indexed</span><span id="grm-vec-sources" class="grm-v">-</span></div>
                <div class="grm-row" style="align-items:flex-start"><span class="grm-k">by format</span><span id="grm-vec-formats" class="grm-fmt-chips">-</span></div>
            </div>

            <div class="grm-card">
                <div style="font-size:10px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">Graph Database</div>
                <div id="grm-stepper-row" style="display:none;margin:4px 0 30px">
                    <div id="grm-stepper" class="grm-stepper"></div>
                </div>
                <div class="grm-row"><span class="grm-k">phase</span><span id="grm-phase" class="grm-phase grm-phase-idle">idle</span></div>
                <div class="grm-row"><span class="grm-k">rebuild_in_progress</span><span id="grm-in-progress" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">started_at</span><span id="grm-started-at" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">elapsed</span><span id="grm-elapsed" class="grm-v">-</span></div>
                <div class="grm-row"><span class="grm-k">graph entities</span><span id="grm-db-entities" class="grm-v">0</span></div>
                <div class="grm-row"><span class="grm-k">graph relationships</span><span id="grm-db-rels" class="grm-v">0</span></div>
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
            'poll-state', 'recluster-banner', 'recluster-reason',
            'recluster-btn',
            'failed-banner', 'failed-meta', 'failed-btn',
            'vec-chunks', 'vec-sources', 'vec-formats',
            'phase', 'in-progress', 'started-at', 'elapsed',
            'bar-label', 'chunks', 'progress-bar', 'progress-pct', 'rate', 'current-doc',
            'sub-row', 'sub',
            'stepper-row', 'stepper',
            'entities', 'md-docs', 'communities', 'db-entities', 'db-rels',
            'last-build', 'last-build-json', 'error-card', 'error-msg',
        ]) {
            this._els[id] = document.getElementById('grm-' + id);
        }

        this._els['recluster-btn'].addEventListener('click', () => this._triggerAction());
        this._els['failed-btn'].addEventListener('click', () => {
            const scope = this._els['failed-btn'].dataset.scope || 'rebuild';
            this._triggerRetry(scope);
        });

        if (this._els['domain-select']) {
            this._els['domain-select'].addEventListener('change', (e) => {
                this._setDomain(e.target.value);
            });
        }
    }

    /** Switch the panel's target Domain and re-tick immediately. Rate /
     *  ETA derive from server-provided started_at + done counts, so no
     *  client-side counters need resetting on a domain change. */
    _setDomain(domainId) {
        if (!domainId || domainId === this._domainId) return;
        this._domainId = domainId;
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
        // when the backend has finished the op we triggered. Terminal
        // phases (done / failed) clear unconditionally; otherwise we
        // need both pending cleared AND no rebuild in progress. Without
        // the terminal-phase escape, a recluster retry that *fails*
        // would leave the banner stuck on "Running..." forever, because
        // pending_recluster is only cleared on success.
        const phaseDone = progress.phase === 'done';
        const phaseFailed = progress.phase === 'failed';
        if (this._reclusterInFlight && !inProgress && (phaseDone || phaseFailed || !pending)) {
            this._reclusterInFlight = false;
        }

        // Failed banner takes priority. Shown when the most recent op
        // ended in `failed` AND we're not currently retrying it. The
        // retry button's scope (recluster vs full rebuild) is derived
        // from progress.failed_op so the user only re-runs what they
        // need to: analytics-layer failures retry the analytics layer;
        // anything else falls back to Full Rebuild.
        const showFailed = phaseFailed && !inProgress && !this._reclusterInFlight;
        if (showFailed) {
            const failedOp = progress.failed_op || 'unknown';
            const failedAt = progress.failed_at;
            const time = failedAt
                ? new Date(failedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : '';
            const meta = [failedOp, time].filter(Boolean).join(' · ');
            this._els['failed-banner'].style.display = '';
            this._els['failed-meta'].textContent = meta;
            const isReclusterFailure = failedOp === 'auto_recluster' || failedOp === 'recluster';
            const btn = this._els['failed-btn'];
            btn.dataset.scope = isReclusterFailure ? 'recluster' : 'rebuild';
            btn.textContent = isReclusterFailure ? 'Retry Recluster' : 'Full Rebuild';
            btn.disabled = false;
            this._els['recluster-banner'].style.display = 'none';
        } else {
            this._els['failed-banner'].style.display = 'none';
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
                this._els['recluster-btn'].disabled = true;
                this._els['recluster-btn'].textContent = 'Running...';
            } else if (pending && !inProgress) {
                this._els['recluster-banner'].style.display = '';
                const setAt = pending.set_at ? new Date(pending.set_at).toLocaleString() : 'unknown time';
                const reason = pending.reason ? ` - ${pending.reason}` : '';
                this._els['recluster-reason'].textContent = `Marked at ${setAt}${reason}`;
                this._els['recluster-btn'].disabled = false;
                this._els['recluster-btn'].textContent = REBUILD_ACTION.label;
            } else {
                this._els['recluster-banner'].style.display = 'none';
            }
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

        this._renderStepper(progress);

        this._els['in-progress'].textContent = inProgress ? 'true' : 'false';

        const started = progress.started_at;
        // The builder's `progress` dict only carries `started_at` +
        // `duration_seconds` (set on completion) and `failed_at` (set on
        // terminal failure). `finished_at` lives in the sibling
        // `last_build` block. Freeze the timer on any terminal phase
        // (done OR failed) using whichever timestamp is authoritative;
        // otherwise count up from start. Without folding `failed_at` in,
        // the timer kept ticking forever past a failed run because phase
        // is "failed", not "done", and last_build/duration_seconds are
        // both empty for failures.
        const lastBuild = data.last_build || {};
        const failedAt = progress.failed_at;
        const finishedAt = progress.finished_at || lastBuild.finished_at || failedAt;
        const durationSec = progress.duration_seconds;
        const terminalPhase = progress.phase === 'done' || progress.phase === 'failed';
        const isDone = !inProgress && (terminalPhase || finishedAt || durationSec != null);
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

        // Phase-agnostic progress bar. Picks (done, total) from whichever
        // counter the current phase publishes, so the same bar reflects
        // every step of the build for visual consistency. Phases without
        // their own counter (sameas, similar_to, analytics, caching,
        // scanning, …) fill instantly so the user sees the bar "cross
        // through" rather than stalling at zero.
        const bar = _phaseBarStats(phase, progress);
        this._els['bar-label'].textContent = bar.label;
        this._els['chunks'].textContent = bar.total > 0
            ? `${bar.done} / ${bar.total}`
            : (bar.done >= 1 ? '—' : '0 / 0');
        const pct = bar.total > 0 ? (bar.done / bar.total) * 100 : 0;
        this._els['progress-bar'].style.width = pct.toFixed(1) + '%';
        this._els['progress-pct'].textContent = pct.toFixed(1) + '%';

        // Session-average rate + ETA, only when we have a meaningful
        // total to project against. `started` is the operation start, so
        // the rate is honest across phases — but we only display it for
        // phases with their own counter (extracting, summarizing) where
        // the per-minute number actually means something. Sub-phase-
        // driven phases (writing) get a rate from the sub_phase counter
        // when available; fast/instrumentation-less phases skip it.
        if (!isDone && bar.showRate && started && bar.done > 0 && bar.total > 0 && bar.total > bar.done) {
            const elapsedSec = (Date.now() - Date.parse(started)) / 1000;
            if (elapsedSec > 0) {
                const rate = bar.done / elapsedSec;
                const eta = (bar.total - bar.done) / rate;
                this._els['rate'].textContent =
                    `${(rate * 60).toFixed(1)} ${bar.unit}/min (avg) · ETA ~ ${fmtDuration(eta)}`;
            } else {
                this._els['rate'].textContent = '';
            }
        } else {
            this._els['rate'].textContent = '';
        }

        const curDoc = progress.current_doc || '';
        const curIdx = progress.current_chunk_in_doc;
        this._els['current-doc'].textContent = curDoc
            ? (curIdx !== undefined ? `${curDoc}  #${curIdx}` : curDoc)
            : '-';

        // Sub-phase line — fills the gap between phase changes during long
        // silent steps. The builder emits `sub_phase` / `sub_done` /
        // `sub_total` from add_doc_merge today; full-rebuild instrumentation
        // can attach later without UI changes. Hidden when no sub-phase
        // field is present so the row doesn't add noise during extraction
        // (where the chunk progress bar above is the better signal).
        const subPhase = progress.sub_phase;
        if (subPhase) {
            const subDone = progress.sub_done;
            const subTotal = progress.sub_total;
            let label = subPhase;
            if (typeof subDone === 'number' && typeof subTotal === 'number' && subTotal > 0) {
                label += `  ${subDone} / ${subTotal}`;
                if (typeof progress.sub_pct === 'number') {
                    label += ` (${progress.sub_pct.toFixed(0)}%)`;
                }
            }
            this._els['sub'].textContent = label;
            this._els['sub-row'].style.display = '';
        } else {
            this._els['sub-row'].style.display = 'none';
        }

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

    /** Render the per-operation phase stepper inside the GraphRAG card.
     *  Reads `progress.operation` to pick the sequence and `progress.phase`
     *  to mark current/done; falls back to hidden when no operation is
     *  set (default state, before any op has run since process start).
     *  Failed phases use `failed_op` to mark the exact station that
     *  exploded; everything before it is rendered as done. The active
     *  station's name is rendered inline beneath its dot — left-aligned
     *  on the first station, right-aligned on the last, otherwise
     *  centered around the dot — so the label always points at the
     *  station it describes. */
    _renderStepper(progress) {
        const row = this._els['stepper-row'];
        const stepperEl = this._els['stepper'];
        const op = progress && progress.operation;
        const phase = progress && progress.phase;
        const sequence = op ? PHASE_SEQUENCES[op] : null;
        if (!sequence || !phase || phase === 'idle') {
            row.style.display = 'none';
            return;
        }
        const isFailed = phase === 'failed';
        const isTerminalDone = phase === 'done';
        const failedAtIdx = isFailed && progress.failed_op
            ? sequence.findIndex((s) => s.key === progress.failed_op)
            : -1;
        const currentIdx = sequence.findIndex((s) => s.key === phase);

        // Which index gets the inline label?
        let activeIdx = -1;
        if (isFailed) activeIdx = failedAtIdx;
        else if (isTerminalDone) activeIdx = sequence.length - 1;
        else activeIdx = currentIdx;

        stepperEl.innerHTML = '';
        sequence.forEach((s, i) => {
            const station = document.createElement('div');
            station.className = 'grm-stepper-station';
            const dotWrap = document.createElement('div');
            dotWrap.className = 'grm-stepper-dot-wrap';
            const dot = document.createElement('div');
            dot.className = 'grm-stepper-dot';
            dot.title = s.label;
            dot.setAttribute('aria-label', s.label);

            // State of THIS dot
            let dotClass = '';
            if (isFailed) {
                if (failedAtIdx >= 0 && i < failedAtIdx) dotClass = 'done';
                else if (failedAtIdx >= 0 && i === failedAtIdx) dotClass = 'failed';
            } else if (isTerminalDone) {
                dotClass = 'done';
            } else if (currentIdx >= 0 && i < currentIdx) {
                dotClass = 'done';
            } else if (currentIdx >= 0 && i === currentIdx) {
                dotClass = 'current';
            }
            if (dotClass) dot.classList.add(dotClass);
            dotWrap.appendChild(dot);

            // Inline label, only on the active/failed/terminal-done station.
            // Alignment follows position so the text always points at its
            // own dot: first station → left edge; last → right edge;
            // anything in between → centered.
            if (i === activeIdx) {
                const label = document.createElement('div');
                label.className = 'grm-stepper-label';
                if (i === 0) label.classList.add('align-left');
                else if (i === sequence.length - 1) label.classList.add('align-right');
                label.textContent = isFailed ? `Failed at ${s.label}` : s.label;
                dotWrap.appendChild(label);
            }
            station.appendChild(dotWrap);

            // Connecting line to the next station
            if (i < sequence.length - 1) {
                const line = document.createElement('div');
                line.className = 'grm-stepper-line';
                let lineClass = '';
                if (isFailed) {
                    if (failedAtIdx >= 0 && i < failedAtIdx) lineClass = 'done';
                    else if (failedAtIdx >= 0 && i === failedAtIdx) lineClass = 'failed';
                } else if (isTerminalDone) {
                    lineClass = 'done';
                } else if (currentIdx >= 0 && i < currentIdx) {
                    lineClass = 'done';
                }
                if (lineClass) line.classList.add(lineClass);
                station.appendChild(line);
            }
            stepperEl.appendChild(station);
        });

        row.style.display = '';
    }

    /** Fire the scoped retry from the failed-state banner. `scope` is
     * either 'recluster' (analytics-layer rerun) or 'rebuild' (full
     * re-extraction). Reuses the in-flight flag so the running banner
     * picks up live progress on the next /status tick. */
    _triggerRetry(scope) {
        if (this._reclusterInFlight || !this._domainId) return;
        this._reclusterInFlight = true;
        const btn = this._els['failed-btn'];
        btn.disabled = true;
        btn.textContent = 'Starting...';
        const url = scope === 'recluster'
            ? `api/domains/${this._domainId}/recluster`
            : `api/domains/${this._domainId}/rebuild`;
        fetch(url, { method: 'POST' })
            .catch((e) => {
                this._reclusterInFlight = false;
                this._applyError(`Retry failed to start: ${e.message}`);
            });
    }
}

/** Phase-aware bar driver. Returns `{done, total, label, unit, showRate}`
 *  for the current phase so a single shared progress bar can represent
 *  every step of the build:
 *
 *    - extracting → extraction_chunks_done / total      (chunks)
 *    - summarizing → communities_summarized / total     (communities)
 *    - writing → sub_done / sub_total                   (sub-phase batches)
 *    - sameas / similar_to / analytics / caching / …    (full bar so the
 *        user sees the bar "cross through" instead of stalling at 0)
 *    - idle / starting / failed                         (empty bar)
 *
 *  `showRate` gates the chunks/min · ETA line: only meaningful for
 *  phases where the counter changes monotonically over a non-trivial
 *  duration (extracting, summarizing, writing batches). Fast /
 *  instrumentation-less phases blank it. */
function _phaseBarStats(phase, progress) {
    const sub = progress.sub_phase;
    const subDone = progress.sub_done;
    const subTotal = progress.sub_total;
    const hasSub = typeof subDone === 'number' && typeof subTotal === 'number' && subTotal > 0;

    if (phase === 'extracting') {
        const done = progress.extraction_chunks_done || 0;
        const total = progress.extraction_chunks_total || 0;
        return { done, total, label: 'chunks extracted', unit: 'chunks', showRate: true };
    }
    if (phase === 'summarizing') {
        const done = progress.communities_summarized || 0;
        const total = progress.communities_total || 0;
        return { done, total, label: 'communities summarized', unit: 'communities', showRate: true };
    }
    if (phase === 'writing') {
        if (hasSub) {
            // sub_phase comes through as e.g. 'writing.relationships' — strip
            // the prefix so the label reads cleanly next to the bar.
            const tail = (sub && sub.includes('.')) ? sub.split('.').slice(1).join('.') : (sub || 'writing');
            return { done: subDone, total: subTotal, label: tail, unit: 'batches', showRate: subTotal > 1 };
        }
        return { done: 1, total: 1, label: 'writing', unit: '', showRate: false };
    }
    // Fast / instrumentation-less phases: fill the bar so the user sees
    // we're moving through it rather than staring at a 0% bar.
    const FAST = ['scanning', 'caching', 'sameas', 'merge_identity', 'similar_to',
                  'analytics', 'adding_doc', 'removing_doc', 'recluster_loading',
                  'parsing'];
    if (FAST.includes(phase)) {
        return { done: 1, total: 1, label: phase.replace('_', ' '), unit: '', showRate: false };
    }
    if (phase === 'done') {
        return { done: 1, total: 1, label: 'done', unit: '', showRate: false };
    }
    if (phase === 'failed') {
        return { done: 0, total: 0, label: 'failed', unit: '', showRate: false };
    }
    // idle / starting / unknown — empty bar.
    return { done: 0, total: 0, label: phase || 'idle', unit: '', showRate: false };
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
