/**
 * DomainKnowledgeTab - Vector RAG + Graph status cards + Rebuild button.
 *
 * Polls `/api/domains/{id}/status` (combined vector + graph) every 2s
 * while mounted. Stops on destroy(). Visual treatment reuses the
 * `grm-phase-*` classes from the Knowledge Base Monitor.
 *
 * Endpoints:
 *   GET  /api/domains/{id}/status
 *   GET  /api/rag/index/format_breakdown?collection={id}__corpus
 *   POST /api/domains/{id}/rebuild
 */

import { modalConfirm } from '../modal.js';
import { notify } from '../Notify.js';


const POLL_MS = 2000;


function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[ch]);
}


function fmtDuration(seconds) {
    if (!seconds || seconds < 0) return '-';
    const s = Math.round(seconds);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60), r = s % 60;
    if (m < 60) return `${m}m ${r}s`;
    const h = Math.floor(m / 60), mr = m % 60;
    return `${h}h ${mr}m`;
}


export class DomainKnowledgeTab {

    constructor(ctx) {
        this._ctx = ctx;
        this._els = {};
        this._timer = null;
        this._rebuildInFlight = false;
    }

    mount() {
        const d = this._ctx.domain;
        const root = document.createElement('div');
        root.className = 'dm-knowledge';

        if (!d.has_knowledge) {
            const info = document.createElement('div');
            info.className = 'dm-card dm-card-info';
            info.innerHTML = `
                <div class="dm-card-body">
                    This Domain is capability-only (skills + tools).
                    It has no Vector RAG or Knowledge Graph to display.
                </div>
            `;
            root.appendChild(info);
            this._ctx.container.appendChild(root);
            return;
        }

        root.innerHTML = `
            <div id="dm-recluster-banner" class="dm-recluster-banner" style="display:none">
                <i class="fa-solid fa-triangle-exclamation dm-i-warn"></i>
                <div class="dm-recluster-text">
                    <div class="dm-recluster-title">Knowledge graph is behind the corpus</div>
                    <div class="dm-recluster-reason" id="dm-recluster-reason"></div>
                </div>
            </div>

            <div class="dm-card">
                <div class="dm-card-head">
                    <span class="dm-card-title"><i class="fa-solid fa-bars-progress"></i> Vector RAG (ChromaDB)</span>
                </div>
                <div class="dm-card-body">
                    <div class="dm-info-row"><span>Total chunks</span><span id="dm-vec-chunks" class="dm-mono">-</span></div>
                    <div class="dm-info-row"><span>Sources indexed</span><span id="dm-vec-sources" class="dm-mono">-</span></div>
                    <div class="dm-info-row"><span>Format breakdown</span><span id="dm-vec-formats">-</span></div>
                </div>
            </div>

            <div class="dm-card">
                <div class="dm-card-head">
                    <span class="dm-card-title"><i class="fa-solid fa-share-nodes"></i> Knowledge Graph (ArcadeDB)</span>
                    <span id="dm-graph-phase" class="grm-phase grm-phase-idle">idle</span>
                </div>
                <div class="dm-card-body">
                    <div class="dm-info-row"><span>Entities</span><span id="dm-graph-entities" class="dm-mono">-</span></div>
                    <div class="dm-info-row"><span>Relationships</span><span id="dm-graph-rels" class="dm-mono">-</span></div>
                    <div class="dm-info-row"><span>Communities</span><span id="dm-graph-comm" class="dm-mono">-</span></div>
                    <div class="dm-info-row"><span>Last build</span><span id="dm-graph-last" class="dm-mono">-</span></div>
                    <div class="dm-info-row" id="dm-graph-progress-row" style="display:none">
                        <span>Progress</span>
                        <span class="dm-mono">
                            <span id="dm-graph-progress-text">-</span>
                            <span id="dm-graph-progress-pct" style="margin-left:6px"></span>
                        </span>
                    </div>
                </div>
                <div class="dm-card-actions">
                    <button class="rm-btn dm-btn-primary" id="dm-rebuild-btn">
                        <i class="fa-solid fa-rotate dm-i-rebuild"></i>
                        <span id="dm-rebuild-label">Rebuild Graph</span>
                    </button>
                    <span class="dm-card-note">Full re-extraction, ~25 minutes.</span>
                </div>
            </div>
        `;
        this._ctx.container.appendChild(root);

        // Refs
        this._els.root          = root;
        this._els.banner        = root.querySelector('#dm-recluster-banner');
        this._els.bannerReason  = root.querySelector('#dm-recluster-reason');
        this._els.vecChunks     = root.querySelector('#dm-vec-chunks');
        this._els.vecSources    = root.querySelector('#dm-vec-sources');
        this._els.vecFormats    = root.querySelector('#dm-vec-formats');
        this._els.phase         = root.querySelector('#dm-graph-phase');
        this._els.entities      = root.querySelector('#dm-graph-entities');
        this._els.rels          = root.querySelector('#dm-graph-rels');
        this._els.communities   = root.querySelector('#dm-graph-comm');
        this._els.lastBuild     = root.querySelector('#dm-graph-last');
        this._els.progressRow   = root.querySelector('#dm-graph-progress-row');
        this._els.progressText  = root.querySelector('#dm-graph-progress-text');
        this._els.progressPct   = root.querySelector('#dm-graph-progress-pct');
        this._els.rebuildBtn    = root.querySelector('#dm-rebuild-btn');
        this._els.rebuildLabel  = root.querySelector('#dm-rebuild-label');

        this._els.rebuildBtn.addEventListener('click', () => this._triggerRebuild());

        this._tick();
        this._timer = setInterval(() => this._tick(), POLL_MS);
    }

    destroy() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
        this._els = {};
        this._rebuildInFlight = false;
    }

    _statusUrl()           { return `api/domains/${encodeURIComponent(this._ctx.domain.domain_id)}/status`; }
    _rebuildUrl()          { return `api/domains/${encodeURIComponent(this._ctx.domain.domain_id)}/rebuild`; }
    _formatBreakdownUrl()  { return `api/rag/index/format_breakdown?collection=${encodeURIComponent(this._ctx.domain.domain_id)}__corpus`; }

    async _tick() {
        try {
            const [statusResp, fmtResp] = await Promise.all([
                fetch(this._statusUrl(), { cache: 'no-store' }),
                fetch(this._formatBreakdownUrl(), { cache: 'no-store' }).catch(() => null),
            ]);
            if (!statusResp.ok) throw new Error('HTTP ' + statusResp.status);
            const data = await statusResp.json();
            this._renderStatus(data);
            if (fmtResp && fmtResp.ok) {
                this._renderFormatBreakdown(await fmtResp.json());
            } else {
                this._renderFormatBreakdown(null);
            }
        } catch (e) {
            // Surface the error once, but keep polling - the backend may
            // come back. Avoid spamming the parent's error banner per tick;
            // we only set our own phase chip to "error" instead.
            if (this._els.phase) {
                this._els.phase.textContent = 'unreachable';
                this._els.phase.className = 'grm-phase grm-phase-error';
            }
        }
    }

    _renderFormatBreakdown(data) {
        const el = this._els.vecFormats;
        if (!el) return;
        if (!data || data.status === 'unavailable') {
            el.textContent = '-';
            return;
        }
        const by = data.by_format || {};
        const entries = Object.entries(by).sort((a, b) => b[1] - a[1]);
        if (!entries.length) {
            el.textContent = '-';
            return;
        }
        el.innerHTML = entries
            .map(([fmt, n]) => `<span class="grm-fmt-chip">${escapeHtml(fmt)} ${n}</span>`)
            .join(' ');
    }

    _renderStatus(data) {
        const pending = data.pending_recluster;
        const graph = data.graph || {};
        const inProgress = !!graph.rebuild_in_progress;
        const progress = graph.progress || {};
        const lastBuild = graph.last_build || {};

        // Auto-clear our in-flight flag when the server settles.
        if (this._rebuildInFlight && !pending && !inProgress) {
            this._rebuildInFlight = false;
        }

        // Recluster / running banner
        if (this._rebuildInFlight) {
            this._els.banner.style.display = '';
            this._els.bannerReason.textContent = `Rebuilding... phase: ${progress.phase || 'starting'}`;
        } else if (pending && !inProgress) {
            this._els.banner.style.display = '';
            const setAt = pending.set_at ? new Date(pending.set_at).toLocaleString() : 'unknown time';
            const reason = pending.reason ? ` - ${pending.reason}` : '';
            this._els.bannerReason.textContent = `Marked at ${setAt}${reason}`;
        } else {
            this._els.banner.style.display = 'none';
        }

        // Vector RAG block
        const vec = data.vector || {};
        if (vec.error) {
            this._els.vecChunks.textContent = `error: ${vec.error}`;
            this._els.vecSources.textContent = '-';
        } else {
            this._els.vecChunks.textContent = vec.total_chunks ?? 0;
            this._els.vecSources.textContent = (vec.sources || []).length;
        }

        // Graph block
        const phase = progress.phase || 'idle';
        this._els.phase.textContent = phase;
        this._els.phase.className = 'grm-phase grm-phase-' + phase;

        const counts = graph.global_counts || {};
        this._els.entities.textContent = counts.entities ?? 0;
        this._els.rels.textContent = counts.relationships ?? 0;
        const cs = (progress.communities_summarized != null && progress.communities_total != null)
            ? `${progress.communities_summarized} / ${progress.communities_total}`
            : (counts.communities ?? '-');
        this._els.communities.textContent = cs;

        if (lastBuild.finished_at) {
            const when = new Date(lastBuild.finished_at).toLocaleString();
            const dur = fmtDuration(lastBuild.duration_seconds);
            this._els.lastBuild.textContent = `${when} (${dur})`;
        } else {
            this._els.lastBuild.textContent = inProgress ? 'in progress' : '-';
        }

        // Progress row only while in flight
        if (inProgress) {
            const done = progress.extraction_chunks_done || 0;
            const total = progress.extraction_chunks_total || 0;
            this._els.progressRow.style.display = '';
            this._els.progressText.textContent = `${done} / ${total} chunks`;
            const pct = total ? (done / total) * 100 : 0;
            this._els.progressPct.textContent = total ? `(${pct.toFixed(1)}%)` : '';
        } else {
            this._els.progressRow.style.display = 'none';
        }

        // Rebuild button state
        this._els.rebuildBtn.disabled = inProgress || this._rebuildInFlight;
        this._els.rebuildLabel.textContent = (inProgress || this._rebuildInFlight)
            ? 'Rebuilding...'
            : 'Rebuild Graph';
    }

    async _triggerRebuild() {
        const d = this._ctx.domain;
        const ok = await modalConfirm(
            `Rebuild the knowledge graph for "${d.name || d.domain_id}"? Full re-extraction takes ~25 minutes.`,
            { title: 'Rebuild Graph', confirmText: 'Rebuild', cancelText: 'Cancel' },
        );
        if (!ok) return;
        this._rebuildInFlight = true;
        this._els.rebuildBtn.disabled = true;
        this._els.rebuildLabel.textContent = 'Starting...';
        try {
            const r = await fetch(this._rebuildUrl(), { method: 'POST' });
            if (!r.ok) {
                const detail = await r.text().catch(() => '');
                throw new Error(`HTTP ${r.status}: ${detail.slice(0, 200)}`);
            }
            notify.info(`Rebuild started for ${d.domain_id}.`);
            this._tick();
        } catch (e) {
            this._rebuildInFlight = false;
            this._ctx.showError(`Rebuild failed: ${e.message}`);
            this._els.rebuildBtn.disabled = false;
            this._els.rebuildLabel.textContent = 'Rebuild Graph';
        }
    }
}
