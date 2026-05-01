import { AgentClient } from './AgentClient.js';
import { AudioResampler } from './AudioResampler.js';

const AGENT_URL = 'https://logus2k.com/llm';
const STT_URL = 'https://logus2k.com/stt';
const STT_PATH = '/stt/socket.io';
const TTS_URL = 'https://logus2k.com/tts';
const TTS_PATH = '/tts/socket.io';
const AGENT_NAME = 'noted';

// Random welcome messages shown when chat opens with no prior history.
// Static (no LLM call) to avoid a race with the user's first message:
// a dynamic welcome streams tokens into ChatPanel's single _streamingMsg
// slot, and a fast user-send before that stream completes makes turn-2
// tokens append to the welcome bubble.
const WELCOME_MESSAGES = [
    "Hi, what can I help you with?",
    "Hi, what are we working on today?",
    "Hey, what can I do for you?",
    "Hi, I'm here to help. What do you need?",
    "Hi there, what's on your plate?",
    "Hello, where would you like to start?",
    "Hi, ask me anything.",
    "Hey, ready when you are.",
    "Hi, what's on your mind?",
    "Hello, how can I help?",
    "Hi, what would you like to do?",
    "Ready when you are. What's first?",
    "Hi, what's the question?",
    "Hi, let me know what you need.",
    "Hey, what can I look into for you?",
    "Hi, where shall we start?",
    "Hi, fire away.",
    "Hello, I'm listening.",
    "Hi, what can I look up or help with?",
    "Hey, what's the task?",
];

// Write tools whose `tool_badge` SSE event should NOT render a chip in the
// chat. The `pending_action(s)` event that follows renders a better-labeled
// chip ("3 cell changes" vs. raw "batch_update_cells"), and the tool_badge
// event is still visible to the harness (which reads the SSE stream, not
// the DOM). Keep in sync with backend/app/managers/llm_tools.py::WRITE_TOOLS.
const WRITE_TOOLS_UI = [
    'update_cell',
    'insert_cell',
    'batch_update_cells',
    'find_replace_in_cells',
    'update_file',
    'create_file',
    'fix_lint_issues',
];

/**
 * ChatService - Wires ChatPanel to AgentClient with STT and TTS support.
 * Supports two chat paths:
 *   1. Direct AgentClient (Socket.IO) - for simple chat, STT/TTS voice
 *   2. Context-enriched via /api/llm/chat (SSE) - for MLOps-aware queries
 */
function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

export class ChatService {

    constructor(chatPanel) {
        this.chatPanel = chatPanel;
        this.agentClient = null;
        this.clientId = _uuid();
        this.threadId = _uuid();
        this._streamBuffer = '';

        // Status callback
        this._onStatusChange = null;

        // Context provider - set via setContextProvider()
        this._contextProvider = null;

        // Write action callback - called when user approves a cell edit
        this._onWriteAction = null;

        // Navigate callback - called when LLM requests scroll_to_cell
        this._onNavigate = null;

        // Voice state
        this.voiceActive = false;
        this._audioContext = null;
        this._mediaStream = null;
        this._workletNode = null;
        this._resampler = null;
        this._sttSocket = null;

        // TTS state
        this._ttsSocket = null;
        this._ttsAudioContext = null;
        this._ttsPlayQueue = Promise.resolve();
        this.ttsEnabled = false;

        // The static greeting shown at chat-open (when there's no prior
        // history). Stashed so a late TTS-enable can replay it as voice.
        this._welcomeText = '';

        this._userMessagesSent = 0;

        this._wirePanel();
    }

    /**
     * Set a function that returns context descriptor from the app.
     * Called before each context-enriched chat request.
     * @param {Function} provider - () => { projectId, notebookPath, selectedCellIndex, activeRunId, ... }
     */
    setContextProvider(provider) {
        this._contextProvider = provider;
    }

    _wirePanel() {
        this.chatPanel.onSend((text) => this.sendMessage(text, { showUserMessage: false }));
        this.chatPanel.onSttToggle((active) => {
            if (active) this.startVoice();
            else this.stopVoice();
        });
        this.chatPanel.onTtsToggle(() => {
            if (this.ttsEnabled) this.disableTTS();
            else this.enableTTS();
        });
        this.chatPanel.onClear(() => this.clearHistory());
        this.chatPanel._onDebugToggle = (enabled) => this._toggleDebug(enabled);
    }

    _toggleDebug(enabled) {
        fetch('api/llm/debug', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        if (enabled) {
            this._openDebugPanel();
        } else if (this._debugPanel) {
            this._debugPanel.close();
            this._debugPanel = null;
        }
    }

    _openDebugPanel() {
        if (this._debugPanel) return;

        this._debugPanel = jsPanel.create({
            headerTitle: '<i class="fa-solid fa-bug" style="margin-right:6px;font-size:11px;color:#e67e22"></i>LLM Debug',
            theme: '#fff9e3 filled',
            borderRadius: '5px',
            contentSize: { width: Math.min(700, window.innerWidth - 100), height: Math.min(400, window.innerHeight - 100) },
            position: { my: 'right-bottom', at: 'right-bottom', offsetX: -20, offsetY: -40 },
            headerControls: 'closeonly',
            content: `<div class="llm-debug-log" style="height:100%;overflow:auto;font-size:12px;background:#fff;padding:0"></div>`,
            onclosed: () => {
                this._debugPanel = null;
                this.chatPanel._debugCheckbox.checked = false;
                this.chatPanel._debugEnabled = false;
                fetch('api/llm/debug', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: false }),
                });
                if (this._debugHandler && window._notedSocket) {
                    window._notedSocket.off('llm:debug_event', this._debugHandler);
                }
            },
        });

        this._debugHandler = (event) => this._addDebugEvent(event);
        if (window._notedSocket) {
            window._notedSocket.on('llm:debug_event', this._debugHandler);
        }

        // Reset turn-grouping state and clear previous events
        this._debugTurns = null;
        fetch('api/llm/debug/events', { method: 'DELETE' });
    }

    _addDebugEvent(event) {
        const logEl = this._debugPanel?.content?.querySelector('.llm-debug-log');
        if (!logEl) return;

        // ── Turn grouping state (initialized once per panel session) ──
        // Each turn = one user question -> answer. The boundary is the
        // `context.sent` event (carries `user_message`). Skill loads
        // arrive BEFORE that boundary; they buffer until context.sent
        // opens the new turn group.
        if (!this._debugTurns) {
            this._debugTurns = { count: 0, current: null, currentBody: null,
                currentCounts: null, pending: [] };
        }
        const turns = this._debugTurns;

        // Detect turn boundary
        const isTurnStart = (event.category === 'context' && event.action === 'sent');
        const isTurnEnd = (event.category === 'llm' && event.action === 'stream_end');

        if (isTurnStart) {
            turns.count += 1;
            const userMsg = event.detail?.user_message || '(no message)';
            const turnEl = document.createElement('details');
            turnEl.open = true;  // newest turn auto-expanded
            turnEl.style.cssText = 'border-bottom:2px solid #d0d0d0;background:#fff';
            const turnSummary = document.createElement('summary');
            turnSummary.style.cssText = 'padding:8px 10px;cursor:pointer;background:#fff9e3;font-size:12px;font-weight:600;display:flex;gap:10px;align-items:center';
            const counts = { skills: 0, tools: 0, api_calls: 0, started: Date.now() };
            turns.currentCounts = counts;
            // Counter spans get updated in-place as events stream in
            const countsSpan = document.createElement('span');
            countsSpan.className = 'turn-counts';
            countsSpan.style.cssText = 'color:#888;font-weight:400;font-size:11px;margin-left:auto';
            countsSpan.textContent = '0 skills · 0 tools';
            turnSummary.innerHTML = `
                <span style="color:#999">Turn ${turns.count}</span>
                <span style="color:#333;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${this._esc(userMsg)}</span>
            `;
            turnSummary.appendChild(countsSpan);
            turnEl.appendChild(turnSummary);
            const body = document.createElement('div');
            body.className = 'turn-body';
            turnEl.appendChild(body);
            logEl.appendChild(turnEl);

            // Collapse the previous turn so the new one is the focus
            if (turns.current) turns.current.open = false;

            turns.current = turnEl;
            turns.currentBody = body;
            turns.currentCountsEl = countsSpan;

            // Drain any pre-context skill events into this new turn
            if (turns.pending.length) {
                for (const e of turns.pending) this._appendEventLine(e, body, counts, countsSpan);
                turns.pending = [];
            }
        }

        // If no turn open yet (first events of session before context.sent),
        // buffer them; they'll flush when the next context.sent arrives.
        if (!turns.current) {
            turns.pending.push(event);
            return;
        }

        // Append event into current turn body + bump counters
        this._appendEventLine(event, turns.currentBody, turns.currentCounts, turns.currentCountsEl);

        if (isTurnEnd) {
            // Stamp duration into the counts span
            const elapsed = ((Date.now() - turns.currentCounts.started) / 1000).toFixed(1);
            const counts = turns.currentCounts;
            turns.currentCountsEl.textContent =
                `${counts.skills} skills · ${counts.tools} tools · ${counts.api_calls} api · ${elapsed}s`;
        }

        logEl.scrollTop = logEl.scrollHeight;
    }

    _appendEventLine(event, container, counts, countsEl) {
        const catColors = {
            api: '#4a9eda', tool: '#f9a825', skill: '#66bb6a',
            file: '#ce93d8', llm: '#ff7043', context: '#78909c',
        };
        const catIcons = {
            api: 'fa-satellite-dish', tool: 'fa-wrench', skill: 'fa-book',
            file: 'fa-file-code', llm: 'fa-robot', context: 'fa-cube',
        };
        const color = catColors[event.category] || '#888';
        const icon = catIcons[event.category] || 'fa-circle';
        const details = event.detail || {};
        const hasDetails = Object.keys(details).length > 0;

        // Bump turn counters
        if (counts) {
            if (event.category === 'skill' && event.action === 'load') counts.skills += 1;
            else if (event.category === 'tool' && event.action === 'call') counts.tools += 1;
            else if (event.category === 'api' && event.action === 'call') counts.api_calls += 1;
            if (countsEl) {
                countsEl.textContent =
                    `${counts.skills} skills · ${counts.tools} tools · ${counts.api_calls} api`;
            }
        }

        // Summary string
        let summary = event.action;
        if (details.name) summary += `: ${details.name}`;
        if (details.model) summary += ` (${details.model})`;
        if (details.messages) summary += ` - ${details.messages} msgs`;
        if (details.input_tokens_est) summary += `, ~${details.input_tokens_est} tokens`;
        if (details.result_chars) summary += ` - ${details.result_chars} chars`;
        if (details.tokens_in) summary += ` - in:${details.tokens_in} out:${details.tokens_out}`;
        if (details.path) summary += `: ${details.path}`;
        if (details.user_message) summary += `: "${details.user_message}"`;
        if (details.auto_injected) summary += ' (auto)';

        const item = document.createElement('details');
        item.style.cssText = 'border-bottom:1px solid #f5f5f5';

        const summaryEl = document.createElement('summary');
        summaryEl.style.cssText = 'padding:4px 10px 4px 22px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:12px';
        summaryEl.addEventListener('mouseenter', () => { summaryEl.style.background = '#f5f5f5'; });
        summaryEl.addEventListener('mouseleave', () => { summaryEl.style.background = ''; });

        const time = event.ts ? event.ts.split(' ')[1] : '';
        summaryEl.innerHTML = `
            <span style="color:#999;font-size:10px;min-width:56px">${time}</span>
            <i class="fa-solid ${icon}" style="color:${color};font-size:10px;min-width:14px"></i>
            <span style="color:${color};font-weight:600;min-width:50px;font-size:11px">${event.category}</span>
            <span style="flex:1;color:#333">${this._esc(summary)}</span>
        `;
        item.appendChild(summaryEl);

        if (hasDetails) {
            const detailEl = document.createElement('div');
            detailEl.style.cssText = 'padding:4px 10px 8px 100px;font-family:var(--font-mono,monospace);font-size:11px;color:#555;background:#fafafa';
            for (const [k, v] of Object.entries(details)) {
                const row = document.createElement('div');
                row.style.cssText = 'padding:1px 0';
                row.innerHTML = `<span style="color:#888">${k}:</span> <span style="color:#333">${this._esc(String(v).substring(0, 500))}</span>`;
                detailEl.appendChild(row);
            }
            item.appendChild(detailEl);
        }

        container.appendChild(item);
    }

    _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }

    /** Load chat history from backend and replay into the panel. Returns true if history was found. */
    async loadHistory() {
        const ctx = this._contextProvider?.();
        const projectId = ctx?.project_id || 'default';
        try {
            const resp = await fetch(`api/llm/history/${this.clientId}/${projectId}`);
            if (!resp.ok) return false;
            const data = await resp.json();
            const messages = data.messages || [];
            if (messages.length === 0) return false;

            for (const msg of messages) {
                this.chatPanel.addMessage(msg.role, msg.content);
            }
            return true;
        } catch (err) {
            console.warn('[ChatService] Failed to load history:', err);
            return false;
        }
    }

    /** Clear chat history on both frontend and backend. */
    async clearHistory() {
        this.chatPanel.clearMessages();
        const ctx = this._contextProvider?.();
        const projectId = ctx?.project_id || 'default';
        try {
            await fetch(`api/llm/history/${this.clientId}/${projectId}`, { method: 'DELETE' });
        } catch (err) {
            console.warn('[ChatService] Failed to clear history:', err);
        }
    }

    onStatusChange(callback) {
        this._onStatusChange = callback;
    }

    _emitStatus(status) {
        if (this._onStatusChange) this._onStatusChange(status);
    }

    /** Check LLM health via HTTP, update status LED and model dropdown. */
    async _checkHealth() {
        try {
            const resp = await fetch('api/llm/health');
            if (resp.ok) {
                const data = await resp.json();
                const ok = data.status === 'ok';
                this._emitStatus(ok ? 'connected' : 'disconnected');
                if (data.models && data.models.length > 0) {
                    this.chatPanel.setModels(data.models, data.active_model);
                } else if (data.active_model) {
                    this.chatPanel.setModelName(data.active_model);
                }
            } else {
                this._emitStatus('disconnected');
            }
        } catch {
            this._emitStatus('disconnected');
        }
    }

    static _SESSION_KEY = 'noted_terminal_secret';

    /** Show a password prompt dialog. Returns the entered string or null if cancelled. */
    static _promptSecret() {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:99999;display:flex;align-items:center;justify-content:center';
            overlay.innerHTML = `
                <div style="background:#fff;border-radius:6px;padding:24px;min-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.2);font-family:var(--font-family)">
                    <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:12px">
                        <i class="fa-solid fa-lock" style="margin-right:6px;color:#1a73e8"></i>Access Key Required
                    </div>
                    <div style="font-size:12px;color:#666;margin-bottom:14px">
                        Switching to a paid model requires the noted access key.
                    </div>
                    <input type="password" placeholder="Access key"
                           style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #ccc;border-radius:4px;font-size:13px;outline:none" />
                    <div class="err" style="color:#d32f2f;font-size:12px;margin-top:6px;display:none">Invalid access key</div>
                    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px">
                        <button data-cancel style="padding:6px 16px;border:1px solid #ccc;border-radius:4px;background:#fff;color:#333;cursor:pointer;font-size:12px">Cancel</button>
                        <button data-ok style="padding:6px 16px;border:none;border-radius:4px;background:#1a73e8;color:#fff;cursor:pointer;font-size:12px">Confirm</button>
                    </div>
                </div>`;
            document.body.appendChild(overlay);
            const input = overlay.querySelector('input');
            const cleanup = (val) => { overlay.remove(); resolve(val); };
            overlay.querySelector('[data-ok]').addEventListener('click', () => cleanup(input.value || null));
            overlay.querySelector('[data-cancel]').addEventListener('click', () => cleanup(null));
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') cleanup(input.value || null);
                if (e.key === 'Escape') cleanup(null);
            });
            overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(null); });
            requestAnimationFrame(() => input.focus());
        });
    }

    /** Wire the model dropdown to POST /api/llm/model on change. */
    _wireModelSelect() {
        this.chatPanel.onModelChange(async (modelId) => {
            const isPaid = modelId.startsWith('claude-');
            let secret = '';

            if (isPaid) {
                // Try cached secret first, otherwise prompt
                secret = sessionStorage.getItem(ChatService._SESSION_KEY) || '';
                if (!secret) {
                    secret = await ChatService._promptSecret();
                    if (!secret) {
                        this.chatPanel.revertModelSelect();
                        return;
                    }
                }
            }

            try {
                const resp = await fetch('api/llm/model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_id: modelId, secret }),
                });
                if (resp.status === 403) {
                    sessionStorage.removeItem(ChatService._SESSION_KEY);
                    this.chatPanel.revertModelSelect();
                    alert('Invalid access key');
                    return;
                }
                if (isPaid && secret) {
                    sessionStorage.setItem(ChatService._SESSION_KEY, secret);
                }
                this.chatPanel._lastConfirmedModel = modelId;
            } catch (err) {
                console.warn('[ChatService] Model switch failed:', err);
                this.chatPanel.revertModelSelect();
            }
        });
    }
    onWriteAction(cb) { this._onWriteAction = cb; }
    onNavigate(cb) { this._onNavigate = cb; }


    async connect() {
        this._wireModelSelect();
        this._emitStatus('connecting');
        this.agentClient = new AgentClient({ url: AGENT_URL });
        await this.agentClient.connect({
            onReconnect: () => {
                console.log('[ChatService] Agent reconnected');
                this._emitStatus('connected');
            },
        });

        // LED follows Socket.IO heartbeat (built-in ping/pong)
        this.agentClient.socket.on('disconnect', () => {
            this._emitStatus('disconnected');
        });
        this.agentClient.socket.on('reconnect', () => {
            this._emitStatus('connected');
        });

        // STT transcripts arrive via agent_server's UserTranscript event
        this.agentClient.onTranscripts({
            onFinal: (payload) => {
                if (payload.text && payload.text.trim()) {
                    this.sendMessage(payload.text.trim());
                }
            },
        });

        // LLM streaming responses (direct Socket.IO path - unused now, kept for agent events)
        this.agentClient.onStream({
            onStarted: () => { this._streamBuffer = ''; },
            onText: (fullText) => { this._streamBuffer = fullText; },
            onDone: () => { this.chatPanel.setLoading(false); this._streamBuffer = ''; },
            onError: (err) => {
                this.chatPanel.setLoading(false);
                this.chatPanel.addMessage('assistant', `Error: ${err.message}`);
                this._streamBuffer = '';
            },
        });

        console.log('[ChatService] Connected to agent server');

        // Check LLM health via HTTP (primary indicator)
        await this._checkHealth();

        // Restore previous chat history, or render a static random welcome.
        // Static (not dynamic) because a dynamic welcome streams tokens into
        // ChatPanel's single _streamingMsg slot — a fast user-send before
        // that stream completes makes turn-2 tokens append to the welcome
        // bubble (no second assistant message in DOM, GPU pinned, "no
        // response" perception). See project_static_welcome_fix.md.
        const hasHistory = await this.loadHistory();
        if (!hasHistory) {
            this._welcomeText = WELCOME_MESSAGES[Math.floor(Math.random() * WELCOME_MESSAGES.length)];
            this.chatPanel.addMessage('assistant', this._welcomeText);
            if (this.ttsEnabled) this._sendVoiceToTTS(this._welcomeText);
        }
    }


    /**
     * Strip <think>...</think> blocks from completed text.
     * Used for the direct AgentClient path where streaming isn't parsed incrementally.
     */
    static stripThinking(text) {
        const match = text.match(/^<think>([\s\S]*?)<\/think>\s*([\s\S]*)$/);
        if (match) {
            return { thinking: match[1].trim(), answer: match[2].trim() };
        }
        return { thinking: null, answer: text };
    }

    // --- Text chat ---

    async sendMessage(text, { showUserMessage = true, overrides = null } = {}) {
        // Remove stale error messages from previous failed requests
        this.chatPanel.clearTransientErrors();
        // Show user message in chat (unless already shown by ChatPanel._handleSend)
        if (showUserMessage) {
            this.chatPanel.addMessage('user', text);
        }
        // Once the user actually engages, the welcome no longer makes sense
        // to replay on a late TTS-enable. Mark it consumed.
        this._userMessagesSent++;
        // Always use the HTTP path for consistent usage tracking and memory
        const ctx = this._contextProvider?.() || {};
        return this._sendWithContext(text, ctx, overrides);
    }

    async _sendDirect(text) {
        if (!this.agentClient) return;
        this.chatPanel.setLoading(true);
        try {
            await this.agentClient.runText(text, {
                agent: AGENT_NAME,
                threadId: this.threadId,
            });
        } catch (err) {
            this.chatPanel.setLoading(false);
            this.chatPanel.addMessage('assistant', `Error: ${err.message}`);
        }
    }

    async _sendWithContext(text, contextDescriptor, overrides = null) {
        this.chatPanel.setLoading(true);

        const parser = new ThinkingParser();
        let fullAnswer = '';
        let thinkingContent = '';
        // Last graph_provenance payload received this turn. Surfaced on the
        // assistant message via finalizeStreamingMessage so the user can open
        // the per-answer KG trace.
        let graphProvenance = null;

        // Resolve per-call overrides (welcome path uses these to force
        // think_enabled=false and tools off without affecting the panel
        // toggle state visible to the user).
        const _think = overrides?.thinkEnabled ?? this.chatPanel.thinkEnabled;
        const _vec = overrides?.vectorRagEnabled ?? this.chatPanel.vectorRagEnabled;
        const _graph = overrides?.graphRagEnabled ?? this.chatPanel.graphRagEnabled;

        try {
            const response = await fetch('api/llm/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: text,
                    client_id: this.clientId,
                    context_descriptor: contextDescriptor,
                    think_enabled: _think,
                    vector_rag_enabled: _vec,
                    graph_rag_enabled: _graph,
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            // Keep the typing-dots indicator visible until real content
            // arrives. The previous setLoading(false) here hid the dots the
            // moment the SSE stream OPENED, before any payload had been
            // sent - leaving the user staring at a silent gap during the
            // ~1.5-2s of pre-Gemma routing. The indicator is now hidden
            // by the first content event (thinking_start sets a label;
            // answer_token hides the dots and starts rendering text).

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let sseBuffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                sseBuffer += decoder.decode(value, { stream: true });
                const lines = sseBuffer.split('\n');
                // Keep the last (possibly incomplete) line in the buffer
                sseBuffer = lines.pop();

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ') || trimmed === 'data: [DONE]') continue;

                    let data;
                    try {
                        data = JSON.parse(trimmed.slice(6));
                    } catch {
                        continue; // skip malformed chunks
                    }
                    if (data.error) throw new Error(data.error);

                    // Usage event (sent before [DONE])
                    if (data.usage) {
                        this.chatPanel.updateTokenUsage(data.usage);
                        continue;
                    }

                    // Skills event (sent before streaming starts) - debug-panel only
                    // The chat panel no longer renders skill badges; the same data
                    // flows to the Debug panel via llm_debug events when enabled.
                    if (data.skills) {
                        continue;
                    }

                    // Navigate event - scroll notebook to cell
                    if (data.navigate) {
                        if (this._onNavigate) this._onNavigate(data.navigate.cell_index);
                        continue;
                    }

                    // Tool badge event - debug-panel only (the SSE event is still
                    // visible to the harness; rendering moved to the Debug panel).
                    if (data.tool_badge) {
                        continue;
                    }

                    // Graph provenance event - structured KG payload from
                    // graph_and_vector_search, surfaced on the assistant
                    // message for the per-answer trace UI. Push it to the
                    // ChatPanel immediately so the "Show graph" button
                    // appears alongside "Show thinking" before answer
                    // tokens stream in (the event arrives right after the
                    // tool dispatch, well before thinking_start).
                    if (data.graph_provenance) {
                        graphProvenance = data.graph_provenance;
                        this.chatPanel.setPendingGraphTrace(data.graph_provenance);
                        continue;
                    }

                    // Pending write action(s) - skip badge render, just open
                    // the approval panel. Debug panel records the underlying
                    // tool_call event separately.
                    if (data.pending_actions) {
                        parser.voiceText = ''; // suppress voice - change not confirmed yet
                        this._showBatchConfirmationPanel(data.pending_actions);
                        continue;
                    }
                    if (data.pending_action) {
                        parser.voiceText = ''; // suppress voice - change not confirmed yet
                        this._showBatchConfirmationPanel([data.pending_action]);
                        continue;
                    }

                    if (typeof data.token !== 'string') continue;
                    const result = parser.processToken(data.token);

                    switch (result.type) {
                        case 'thinking_start':
                            // Hide the typing dots - the live reasoning panel
                            // is the visual indicator now; dots are redundant.
                            this.chatPanel.setLoading(false);
                            this.chatPanel.startLiveThinkingSection();
                            // The chunk that contained <think> may have ALSO
                            // carried the first slice of the body. The parser
                            // stashes it in thinkingBuffer but never emits it
                            // as a thinking_token, so it would silently disappear
                            // from the live display - causing visible char loss
                            // (e.g. "ser is asking" instead of "user is asking").
                            // Flush that initial slice now so the live body matches
                            // the captured content.
                            if (parser.thinkingBuffer) {
                                this.chatPanel.appendLiveThinkingToken(parser.thinkingBuffer);
                            }
                            break;
                        case 'thinking_end':
                            this.chatPanel.setThinkingIndicator(false);
                            // Same race in reverse: the chunk that carried </think>
                            // may have also carried the LAST slice of the body
                            // (parts[0] in ThinkingParser). result.thinking is the
                            // full captured content; sync the live body to it
                            // before collapsing so nothing is missing visually.
                            this.chatPanel.setLiveThinkingContent(result.thinking);
                            this.chatPanel.endLiveThinkingSection();
                            thinkingContent = result.thinking;
                            if (result.answer) {
                                fullAnswer += result.answer;
                                this.chatPanel.appendToken(result.answer);
                            }
                            break;
                        case 'thinking_token':
                            this.chatPanel.appendLiveThinkingToken(result.token);
                            break;
                        case 'tool_call':
                            // Tool badges no longer render in chat - moved to Debug panel
                            break;
                        case 'voice':
                            // Voice text collected - will be sent to TTS after finalization
                            break;
                        case 'answer_token':
                            // First answer token marks "real content arriving" -
                            // hide the typing dots if they're still up (e.g. when
                            // the model didn't emit a <think> block).
                            this.chatPanel.setLoading(false);
                            fullAnswer += result.token;
                            this.chatPanel.appendToken(result.token);
                            break;
                    }
                }
            }
        } catch (err) {
            this.chatPanel.setLoading(false);
            this.chatPanel.setThinkingIndicator(false);
            this.chatPanel.addMessage('assistant', `Error: ${err.message}`);
            return;
        }

        this.chatPanel.setThinkingIndicator(false);
        this.chatPanel.finalizeStreamingMessage(thinkingContent, graphProvenance);

        // Send voice summary to TTS if active
        if (this.ttsEnabled && parser.voiceText) {
            this._sendVoiceToTTS(parser.voiceText);
        }

        // History is managed server-side by ProjectMemory
    }

    /** Send extracted <voice> text to TTS for speech output. */
    _sendVoiceToTTS(text) {
        if (!this._ttsSocket?.connected || !text) return;
        try {
            this._ttsSocket.emit('tts_text_chunk', {
                chunk: text,
                target_client_id: this.clientId,
                final: true,
            });
        } catch (err) {
            console.warn('[ChatService] Voice TTS failed:', err);
        }
    }

    // --- Voice (STT) ---

    async startVoice() {
        try {
            this._mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, sampleRate: 48000, echoCancellation: true, noiseSuppression: true },
            });

            this._audioContext = new AudioContext({ sampleRate: 48000 });
            await this._audioContext.audioWorklet.addModule('static/js/recorder_worklet.js');

            const source = this._audioContext.createMediaStreamSource(this._mediaStream);
            this._workletNode = new AudioWorkletNode(this._audioContext, 'recorder-worklet');
            this._resampler = new AudioResampler(48000, 16000);

            // Connect STT socket
            const sttOrigin = new URL(STT_URL, window.location.origin).origin;
            this._sttSocket = io(sttOrigin, {
                path: STT_PATH,
                transports: ['websocket', 'polling'],
                forceNew: true,
                query: { client_id: this.clientId },
            });

            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('STT connection timeout')), 10000);
                this._sttSocket.once('connect', () => { clearTimeout(timeout); resolve(); });
                this._sttSocket.once('connect_error', (err) => { clearTimeout(timeout); reject(err); });
            });

            // Packetize and send audio (~100ms chunks)
            let pending = [];
            let pendingLength = 0;
            const sampleRate = this._audioContext.sampleRate;
            const samplesPerPacket = Math.round(sampleRate * 0.1);

            this._workletNode.port.onmessage = (event) => {
                const chunk = event.data;
                if (!chunk?.length) return;

                pending.push(chunk);
                pendingLength += chunk.length;

                if (pendingLength >= samplesPerPacket) {
                    const merged = new Float32Array(pendingLength);
                    let offset = 0;
                    for (const part of pending) {
                        merged.set(part, offset);
                        offset += part.length;
                    }
                    pending = [];
                    pendingLength = 0;

                    const pcm16 = this._resampler.pushFloat32(merged);
                    if (pcm16?.length > 0 && this._sttSocket?.connected) {
                        this._sttSocket.emit('audio_data', {
                            clientId: this.clientId,
                            audioData: pcm16.buffer,
                        });
                    }
                }
            };

            source.connect(this._workletNode);
            this._workletNode.connect(this._audioContext.destination);

            // Subscribe agent_server to STT transcripts (transcriptOnly: skip LLM, just forward)
            await this.agentClient.sttSubscribe({
                sttUrl: STT_URL,
                clientId: this.clientId,
                agent: AGENT_NAME,
                threadId: this.threadId,
                transcriptOnly: true,
            });

            this.voiceActive = true;
            console.log('[ChatService] Voice active');

        } catch (err) {
            console.error('[ChatService] Voice start failed:', err);
            this.stopVoice();
        }
    }

    async stopVoice() {
        if (this._workletNode) { this._workletNode.disconnect(); this._workletNode = null; }
        if (this._audioContext) { await this._audioContext.close().catch(() => {}); this._audioContext = null; }
        if (this._mediaStream) { this._mediaStream.getTracks().forEach(t => t.stop()); this._mediaStream = null; }
        if (this._resampler) { this._resampler.reset(); this._resampler = null; }
        if (this._sttSocket) { this._sttSocket.disconnect(); this._sttSocket = null; }
        if (this.agentClient && this.clientId) {
            try { await this.agentClient.sttUnsubscribe({ sttUrl: STT_URL, clientId: this.clientId }); } catch {}
        }
        this.voiceActive = false;
        console.log('[ChatService] Voice stopped');
    }

    // --- TTS ---

    async enableTTS() {
        if (this.ttsEnabled) return;
        try {
            // Create + resume the AudioContext NOW, while we're still in
            // the user-gesture stack from the TTS-toggle click. If we wait
            // for the first audio chunk to lazily create it, the gesture
            // is gone and Chrome puts the context in `suspended` state -
            // src.start() then plays into silence with no error.
            const actx = this._ensureTtsAudioContext();
            try { await actx.resume(); } catch {}

            const ttsOrigin = new URL(TTS_URL, window.location.origin).origin;
            this._ttsSocket = io(ttsOrigin, {
                path: TTS_PATH,
                transports: ['websocket', 'polling'],
                forceNew: true,
                query: { type: 'browser', format: 'binary', main_client_id: this.clientId },
            });

            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('TTS connection timeout')), 10000);
                this._ttsSocket.once('connect', () => { clearTimeout(timeout); resolve(); });
                this._ttsSocket.once('connect_error', (err) => { clearTimeout(timeout); reject(err); });
            });

            await new Promise((resolve) => {
                this._ttsSocket.emit('register_audio_client', {
                    main_client_id: this.clientId,
                    connection_type: 'browser',
                    mode: 'tts',
                }, () => resolve());
            });

            this._ttsSocket.on('tts_audio_chunk', async (evt) => {
                const buf = evt?.audio_buffer;
                if (!buf) return;

                const actx = this._ensureTtsAudioContext();
                let audioBuf;
                try {
                    audioBuf = await actx.decodeAudioData(buf.slice(0));
                } catch (e) {
                    console.warn('[ChatService] TTS decodeAudioData failed:', e);
                    return;
                }

                this._ttsPlayQueue = this._ttsPlayQueue.then(() => {
                    const src = actx.createBufferSource();
                    src.buffer = audioBuf;
                    src.connect(actx.destination);
                    src.start();
                    return new Promise(res => { src.onended = res; });
                });
            });

            this._ttsSocket.on('tts_stop_immediate', () => {
                // DO NOT close the AudioContext - it was created during the
                // user-gesture stack of the TTS-toggle click; closing it
                // means the next message has to recreate it OUTSIDE any
                // gesture, which Chrome forces into `suspended` state and
                // silently swallows playback. Just drain the play queue.
                this._ttsPlayQueue = Promise.resolve();
            });

            this.ttsEnabled = true;
            this.chatPanel.setTtsActive(true);
            console.log('[ChatService] TTS enabled');

        } catch (err) {
            console.error('[ChatService] TTS enable failed:', err);
            await this.disableTTS();
            this.chatPanel.addMessage('assistant', 'Error: Voice playback unavailable - TTS server unreachable.');
        }
    }

    async disableTTS() {
        if (this._ttsSocket) {
            try { this._ttsSocket.disconnect(); } catch {}
            this._ttsSocket = null;
        }
        this._closeTtsAudioContext();
        this.ttsEnabled = false;
        this.chatPanel.setTtsActive(false);
    }

    _ensureTtsAudioContext() {
        if (!this._ttsAudioContext) {
            this._ttsAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
        }
        return this._ttsAudioContext;
    }

    _closeTtsAudioContext() {
        if (this._ttsAudioContext) {
            try { this._ttsAudioContext.close(); } catch {}
            this._ttsAudioContext = null;
        }
        this._ttsPlayQueue = Promise.resolve();
    }

    // --- Cleanup ---

    disconnect() {
        this.stopVoice();
        if (this.agentClient) {
            this.agentClient.disconnect();
            this.agentClient = null;
        }
    }

    /**
     * Show a jsPanel confirmation dialog for one or more pending write actions.
     * All changes shown in one panel. Apply/Reject applies to all.
     */
    _showBatchConfirmationPanel(actions) {
        if (!actions || !actions.length) return;

        // Use batch_id if present, otherwise first action's id
        const confirmId = actions[0].batch_id || actions[0].id;
        const notebookName = (actions[0].notebook_path || '').split('/').pop() || 'current notebook';

        const title = actions.length === 1
            ? this._getActionTitle(actions[0])
            : `${actions.length} Proposed Changes in ${notebookName}`;

        // Build combined diff for all actions
        let diffHtml = '';
        for (let i = 0; i < actions.length; i++) {
            const action = actions[i];
            if (actions.length > 1) {
                diffHtml += `<div style="padding:6px 8px;background:#f5f5f5;border-bottom:1px solid #e0e0e0;font-weight:600;font-size:11px;color:#555">${i + 1}. ${this._getActionTitle(action)}</div>`;
            }
            if (action.args.description) {
                diffHtml += `<div style="padding:4px 8px;font-size:10px;color:#777;border-bottom:1px solid #eee">${this._escapeHtml(action.args.description)}</div>`;
            }
            const hasCurrentContent = action.current_content != null;
            const isUpdateWithDiff = (action.tool === 'update_cell' || action.tool === 'update_file') && hasCurrentContent;
            if (isUpdateWithDiff) {
                diffHtml += this._buildDiffHtml(action.current_content, action.args.new_content);
            } else {
                const content = action.args.new_content || action.args.content || '';
                const cleanContent = content.replace(/\\n/g, '\n');
                const label = action.tool === 'create_file' ? `New File` :
                              action.tool === 'update_file' ? `Updated File` :
                              `New Cell (${action.args.cell_type || 'code'})`;
                const lines = cleanContent.split('\n');
                const numStyle = 'padding:2px 4px;color:#999;text-align:right;font-size:10px;border-bottom:1px solid #eee;border-right:1px solid #e0e0e0;min-width:24px;user-select:none';
                const cellStyle = 'padding:2px 6px;white-space:pre;overflow-x:auto;font-size:11px;border-bottom:1px solid #eee;background:#e8f5e9';
                let tableHtml = `<table style="width:100%;border-collapse:collapse"><colgroup><col style="width:28px"><col></colgroup>
                    <thead><tr><th colspan="2" style="padding:4px 6px;background:#e8f5e9;color:#1b5e20;font-size:10px;font-weight:600;text-align:left">${label}</th></tr></thead><tbody>`;
                for (let j = 0; j < lines.length; j++) {
                    tableHtml += `<tr><td style="${numStyle}">${j + 1}</td><td style="${cellStyle}">${this._escapeHtml(lines[j]) || '&nbsp;'}</td></tr>`;
                }
                tableHtml += '</tbody></table>';
                diffHtml += tableHtml;
            }
            if (i < actions.length - 1) {
                diffHtml += '<div style="height:8px;background:#f0f0f0"></div>';
            }
        }

        const panel = jsPanel.create({
            headerTitle: `<i class="fa-solid fa-pen-to-square" style="margin-right:6px;font-size:11px"></i>${title}`,
            theme: '#ffe39e filled',
            borderRadius: '5px',
            contentSize: { width: Math.min(650, window.innerWidth - 80), height: Math.min(500, window.innerHeight - 100) },
            position: 'center',
            headerControls: 'closeonly',
            content: `
                <div style="height:100%;display:flex;flex-direction:column;font-size:12px">
                    <div style="flex:1;overflow:auto">
                        ${diffHtml}
                    </div>
                    <div style="padding:6px 12px;border-top:1px solid #e0e0e0;background:#fafafa">
                        <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
                            <input class="confirm-feedback-input" type="text" placeholder="Optional message to the assistant..." style="flex:1;padding:4px 8px;font-size:11px;border:1px solid #ddd;border-radius:3px;font-family:var(--font-sans);outline:none">
                        </div>
                        <div style="display:flex;gap:8px;justify-content:flex-end">
                            <button class="confirm-reject-btn" style="padding:4px 16px;font-size:12px;border:1px solid #e57373;border-radius:4px;background:#fff;color:#c62828;cursor:pointer">Reject</button>
                            <button class="confirm-apply-btn" style="padding:4px 16px;font-size:12px;border:1px solid #66bb6a;border-radius:4px;background:#e8f5e9;color:#2e7d32;cursor:pointer;font-weight:600">Apply All</button>
                        </div>
                    </div>
                </div>
            `,
            callback: (p) => {
                p.content.style.backgroundColor = '#fff';
                const applyBtn = p.content.querySelector('.confirm-apply-btn');
                const rejectBtn = p.content.querySelector('.confirm-reject-btn');
                const feedbackInput = p.content.querySelector('.confirm-feedback-input');

                applyBtn.addEventListener('click', () => {
                    applyBtn.disabled = true;
                    rejectBtn.disabled = true;
                    applyBtn.textContent = 'Applying...';
                    const feedback = feedbackInput.value.trim();
                    if (feedback) this.chatPanel.addMessage('user', feedback);
                    for (const action of actions) {
                        if (this._onWriteAction) this._onWriteAction(action);
                    }
                    this._sendConfirmation(confirmId, true, feedback);
                    p.close();
                });

                rejectBtn.addEventListener('click', () => {
                    applyBtn.disabled = true;
                    rejectBtn.disabled = true;
                    const feedback = feedbackInput.value.trim();
                    if (feedback) this.chatPanel.addMessage('user', feedback);
                    this._sendConfirmation(confirmId, false, feedback);
                    p.close();
                });

                // Allow Enter key to apply
                feedbackInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { applyBtn.click(); }
                });
            },
        });
    }

    _getActionTitle(action) {
        if (action.tool === 'update_file') {
            const fileName = (action.file_path || action.args.file_path || '').split('/').pop() || 'file';
            return `Update ${fileName}`;
        }
        if (action.tool === 'create_file') {
            const filePath = action.args.file_path || 'new file';
            return `Create ${filePath}`;
        }
        const isUpdate = action.tool === 'update_cell';
        const cellIndex = isUpdate ? action.args.cell_index : action.args.after_cell_index;
        const cellType = action.cell_type || action.args.cell_type || 'code';
        const notebookName = (action.notebook_path || '').split('/').pop() || 'current notebook';
        return isUpdate
            ? `Update Cell ${cellIndex} in ${notebookName}`
            : `Insert ${cellType} Cell after Cell ${cellIndex} in ${notebookName}`;
    }

    /**
     * Show a jsPanel confirmation dialog for a pending write action (legacy single-action).
     * On Apply/Reject, sends POST /api/llm/confirm and streams the follow-up.
     */
    _showConfirmationPanel(action) {
        this._showBatchConfirmationPanel([action]);
        return;
        const isUpdate = action.tool === 'update_cell';
        const cellIndex = isUpdate ? action.args.cell_index : action.args.after_cell_index;
        const cellType = action.cell_type || action.args.cell_type || 'code';
        const description = action.args.description || '';
        const notebookName = (action.notebook_path || '').split('/').pop() || 'current notebook';

        const title = isUpdate
            ? `Proposed Change - Cell ${cellIndex} in ${notebookName}`
            : `Insert ${cellType} Cell after Cell ${cellIndex} in ${notebookName}`;

        // Build diff content
        let diffHtml = '';
        if (isUpdate && action.current_content != null) {
            diffHtml = this._buildDiffHtml(action.current_content, action.args.new_content);
        } else {
            // Insert: show new content with line numbers
            const content = action.args.new_content || action.args.content || '';
            // Replace literal \n with actual newlines (in case LLM sent escaped)
            const cleanContent = content.replace(/\\n/g, '\n');
            const lines = cleanContent.split('\n');
            const numStyle = 'padding:2px 4px;color:#999;text-align:right;font-size:10px;border-bottom:1px solid #eee;border-right:1px solid #e0e0e0;min-width:24px;user-select:none';
            const cellStyle = 'padding:2px 6px;white-space:pre;overflow-x:auto;font-size:11px;border-bottom:1px solid #eee;background:#e8f5e9';
            let tableHtml = `<table style="width:100%;border-collapse:collapse"><colgroup><col style="width:28px"><col></colgroup>
                <thead><tr><th colspan="2" style="padding:4px 6px;background:#e8f5e9;color:#1b5e20;font-size:10px;font-weight:600;text-align:left">New Cell (${cellType})</th></tr></thead><tbody>`;
            for (let i = 0; i < lines.length; i++) {
                tableHtml += `<tr><td style="${numStyle}">${i + 1}</td><td style="${cellStyle}">${this._escapeHtml(lines[i]) || '&nbsp;'}</td></tr>`;
            }
            tableHtml += '</tbody></table>';
            diffHtml = tableHtml;
        }

        const panel = jsPanel.create({
            headerTitle: `<i class="fa-solid fa-pen-to-square" style="margin-right:6px;font-size:11px"></i>${title}`,
            theme: '#ffe39e filled',
            borderRadius: '5px',
            contentSize: { width: Math.min(600, window.innerWidth - 80), height: Math.min(450, window.innerHeight - 100) },
            position: 'center',
            headerControls: 'closeonly',
            content: `
                <div style="height:100%;display:flex;flex-direction:column;font-size:12px">
                    <div style="padding:8px 12px;background:#f9f9f9;border-bottom:1px solid #e0e0e0;color:#555;font-size:11px">
                        ${this._escapeHtml(description)}
                    </div>
                    <div style="flex:1;overflow:auto;padding:8px 12px;font-family:var(--font-mono);font-size:11px;line-height:1.5">
                        ${diffHtml}
                    </div>
                    <div style="display:flex;gap:8px;justify-content:flex-end;padding:8px 12px;border-top:1px solid #e0e0e0;background:#fafafa">
                        <button class="confirm-reject-btn" style="padding:4px 16px;font-size:12px;border:1px solid #e57373;border-radius:4px;background:#fff;color:#c62828;cursor:pointer">Reject</button>
                        <button class="confirm-apply-btn" style="padding:4px 16px;font-size:12px;border:1px solid #66bb6a;border-radius:4px;background:#e8f5e9;color:#2e7d32;cursor:pointer;font-weight:600">Apply</button>
                    </div>
                </div>
            `,
            callback: (p) => {
                p.content.style.backgroundColor = '#fff';
                const applyBtn = p.content.querySelector('.confirm-apply-btn');
                const rejectBtn = p.content.querySelector('.confirm-reject-btn');

                applyBtn.addEventListener('click', () => {
                    applyBtn.disabled = true;
                    rejectBtn.disabled = true;
                    applyBtn.textContent = 'Applying...';
                    // Apply the change in the editor first
                    if (this._onWriteAction) {
                        this._onWriteAction(action);
                    }
                    this._sendConfirmation(action.id, true);
                    p.close();
                });

                rejectBtn.addEventListener('click', () => {
                    applyBtn.disabled = true;
                    rejectBtn.disabled = true;
                    this._sendConfirmation(action.id, false);
                    p.close();
                });
            },
        });
    }

    /**
     * Send confirmation to backend and stream the follow-up response.
     */
    async _sendConfirmation(actionId, approved, feedback = '') {
        try {
            const resp = await fetch('api/llm/confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id: actionId, approved, feedback: feedback || undefined }),
            });

            if (!resp.ok) throw new Error(`Confirm failed: ${resp.status}`);

            // Stream the follow-up response
            this.chatPanel.startStreamingMessage();
            if (approved) {
                this.chatPanel.appendToken('*Change applied.* ');
            } else {
                this.chatPanel.appendToken('*Change rejected.* ');
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            const parser = new ThinkingParser();
            let thinkingContent = '';
            let fullAnswer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const text = decoder.decode(value, { stream: true });
                for (const line of text.split('\n')) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;
                    if (trimmed === 'data: [DONE]') continue;

                    let data;
                    try { data = JSON.parse(trimmed.slice(6)); } catch { continue; }
                    if (data.error) break;
                    if (data.usage) {
                        this.chatPanel.updateTokenUsage(data.usage);
                        continue;
                    }

                    // Chained write tool(s) - just open the confirmation panel.
                    // Tool badges no longer render in the chat (moved to Debug panel).
                    if (data.pending_actions) {
                        this.chatPanel.finalizeStreamingMessage(thinkingContent);
                        this._showBatchConfirmationPanel(data.pending_actions);
                        return;
                    }
                    if (data.pending_action) {
                        this.chatPanel.finalizeStreamingMessage(thinkingContent);
                        this._showBatchConfirmationPanel([data.pending_action]);
                        return;
                    }

                    if (!data.token) continue;
                    const result = parser.processToken(data.token);
                    switch (result.type) {
                        case 'thinking_start':
                            // Hide the typing dots; the live reasoning panel
                            // takes over as the visual indicator.
                            this.chatPanel.setLoading(false);
                            this.chatPanel.startLiveThinkingSection();
                            // Same fix as the primary consumer: flush the
                            // initial slice that arrived in the same chunk
                            // as the <think> tag so it's not lost from the
                            // live display.
                            if (parser.thinkingBuffer) {
                                this.chatPanel.appendLiveThinkingToken(parser.thinkingBuffer);
                            }
                            break;
                        case 'thinking_token':
                            this.chatPanel.appendLiveThinkingToken(result.token);
                            break;
                        case 'thinking_end':
                            this.chatPanel.setThinkingIndicator(false);
                            this.chatPanel.setLiveThinkingContent(result.thinking);
                            this.chatPanel.endLiveThinkingSection();
                            thinkingContent = result.thinking;
                            if (result.answer) {
                                fullAnswer += result.answer;
                                this.chatPanel.appendToken(result.answer);
                            }
                            break;
                        case 'voice':
                            break;
                        case 'answer_token':
                            // First answer token marks "real content arriving" -
                            // hide the typing dots if they're still up (e.g. when
                            // the model didn't emit a <think> block).
                            this.chatPanel.setLoading(false);
                            fullAnswer += result.token;
                            this.chatPanel.appendToken(result.token);
                            break;
                    }
                }
            }
            this.chatPanel.finalizeStreamingMessage(thinkingContent);
            if (this.ttsEnabled && parser.voiceText) {
                this._sendVoiceToTTS(parser.voiceText);
            }

        } catch (err) {
            console.error('[ChatService] Confirmation error:', err);
            this.chatPanel.appendToken(`\n\nError: ${err.message}`);
            this.chatPanel.finalizeStreamingMessage();
        }
    }

    /**
     * Build a side-by-side diff HTML view.
     */
    _buildDiffHtml(oldText, newText) {
        // Normalize escaped newlines to actual newlines
        const oldLines = (oldText || '').replace(/\\n/g, '\n').split('\n');
        const newLines = (newText || '').replace(/\\n/g, '\n').split('\n');

        // Simple LCS-based diff to pair lines
        const pairs = this._diffLines(oldLines, newLines);

        const cellStyle = 'padding:2px 6px;white-space:pre;overflow-x:auto;font-size:11px;border-bottom:1px solid #eee;vertical-align:top';
        const numStyle = 'padding:2px 4px;color:#999;text-align:right;font-size:10px;border-bottom:1px solid #eee;border-right:1px solid #e0e0e0;min-width:24px;user-select:none';

        let html = `<table style="width:100%;border-collapse:collapse;table-layout:fixed">
            <colgroup><col style="width:28px"><col style="width:calc(50% - 28px)"><col style="width:28px"><col style="width:calc(50% - 28px)"></colgroup>
            <thead><tr>
                <th colspan="2" style="padding:4px 34px;background:#fce4ec;color:#b71c1c;font-size:10px;font-weight:600;text-align:left">Current</th>
                <th colspan="2" style="padding:4px 34px;background:#e8f5e9;color:#1b5e20;font-size:10px;font-weight:600;text-align:left">Proposed</th>
            </tr></thead><tbody>`;

        for (const [oldIdx, oldLine, newIdx, newLine, status] of pairs) {
            const leftNum = oldIdx != null ? oldIdx + 1 : '';
            const rightNum = newIdx != null ? newIdx + 1 : '';
            const leftText = oldLine != null ? this._escapeHtml(oldLine) : '';
            const rightText = newLine != null ? this._escapeHtml(newLine) : '';

            let leftBg = '', rightBg = '';
            if (status === 'removed') {
                leftBg = 'background:#fce4ec';
            } else if (status === 'added') {
                rightBg = 'background:#e8f5e9';
            } else if (status === 'changed') {
                leftBg = 'background:#fce4ec';
                rightBg = 'background:#e8f5e9';
            }

            html += `<tr>
                <td style="${numStyle};${leftBg}">${leftNum}</td>
                <td style="${cellStyle};${leftBg}">${leftText || '&nbsp;'}</td>
                <td style="${numStyle};${rightBg}">${rightNum}</td>
                <td style="${cellStyle};${rightBg}">${rightText || '&nbsp;'}</td>
            </tr>`;
        }

        html += '</tbody></table>';
        return html;
    }

    /**
     * Simple line diff producing pairs: [oldIdx, oldLine, newIdx, newLine, status]
     * status: 'equal', 'removed', 'added', 'changed'
     */
    _diffLines(oldLines, newLines) {
        const pairs = [];
        let oi = 0, ni = 0;

        while (oi < oldLines.length || ni < newLines.length) {
            if (oi < oldLines.length && ni < newLines.length && oldLines[oi] === newLines[ni]) {
                pairs.push([oi, oldLines[oi], ni, newLines[ni], 'equal']);
                oi++; ni++;
            } else {
                // Look ahead to find next matching line
                let foundOld = -1, foundNew = -1;
                for (let look = 1; look < 10; look++) {
                    if (foundNew < 0 && ni + look < newLines.length && oi < oldLines.length && oldLines[oi] === newLines[ni + look]) {
                        foundNew = ni + look;
                    }
                    if (foundOld < 0 && oi + look < oldLines.length && ni < newLines.length && oldLines[oi + look] === newLines[ni]) {
                        foundOld = oi + look;
                    }
                }

                if (foundOld >= 0 && (foundNew < 0 || (foundOld - oi) <= (foundNew - ni))) {
                    // Lines were removed from old
                    while (oi < foundOld) {
                        pairs.push([oi, oldLines[oi], null, null, 'removed']);
                        oi++;
                    }
                } else if (foundNew >= 0) {
                    // Lines were added in new
                    while (ni < foundNew) {
                        pairs.push([null, null, ni, newLines[ni], 'added']);
                        ni++;
                    }
                } else {
                    // Lines changed
                    if (oi < oldLines.length && ni < newLines.length) {
                        pairs.push([oi, oldLines[oi], ni, newLines[ni], 'changed']);
                        oi++; ni++;
                    } else if (oi < oldLines.length) {
                        pairs.push([oi, oldLines[oi], null, null, 'removed']);
                        oi++;
                    } else {
                        pairs.push([null, null, ni, newLines[ni], 'added']);
                        ni++;
                    }
                }
            }
        }
        return pairs;
    }

    _escapeHtml(text) {
        return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}

/**
 * ThinkingParser - State machine for parsing <think>...</think> blocks
 * from Qwen 3's streaming output.
 *
 * Buffers thinking tokens separately so the UI can show a "Reasoning..."
 * indicator instead of raw <think> content.
 */
class ThinkingParser {
    constructor() {
        this._inThinking = false;
        this._inToolCall = false;
        this._inVoice = false;
        this._voiceBuffer = '';
        this._buffer = '';       // Accumulates partial tags at chunk boundaries
        this.thinkingBuffer = '';
        this.voiceText = '';     // Collected <voice>...</voice> text
    }

    /** Pull `<voice>...</voice>` out of a same-chunk post-</think> answer.
     *  Sets this.voiceText (preserving any prior content via append) and
     *  returns the cleaned answer with the voice block removed. Without this,
     *  responses that arrive as one big token (think + answer + voice all
     *  together) leak the voice text into the visible chat AND leave
     *  voiceText empty so TTS never fires. */
    _extractVoiceFromAnswer(answer) {
        if (!answer) return answer;
        const m = answer.match(/<voice>([\s\S]*?)<\/voice>/);
        if (!m) return answer;
        this.voiceText = (this.voiceText ? this.voiceText + ' ' : '') + m[1].trim();
        return (answer.slice(0, m.index) + answer.slice(m.index + m[0].length)).trim();
    }

    processToken(token) {
        // Accumulate into buffer to handle tags split across chunks
        this._buffer += token;

        // Check for <think> opening
        if (!this._inThinking && !this._inToolCall && this._buffer.includes('<think>')) {
            this._inThinking = true;
            const after = this._buffer.split('<think>').pop();
            this._buffer = '';
            this.thinkingBuffer = '';
            // If </think> is already in the remainder (same chunk), handle it immediately
            if (after.includes('</think>')) {
                this._inThinking = false;
                const parts = after.split('</think>');
                this.thinkingBuffer = parts[0];
                const answer = this._extractVoiceFromAnswer(parts.slice(1).join('</think>').trimStart());
                return { type: 'thinking_end', thinking: this.thinkingBuffer, answer };
            }
            this.thinkingBuffer = after;
            return { type: 'thinking_start' };
        }

        // Check for </think> closing
        if (this._inThinking && this._buffer.includes('</think>')) {
            this._inThinking = false;
            const parts = this._buffer.split('</think>');
            this.thinkingBuffer += parts[0];
            const answer = this._extractVoiceFromAnswer(parts.slice(1).join('</think>').trimStart());
            this._buffer = '';
            return { type: 'thinking_end', thinking: this.thinkingBuffer, answer };
        }

        // Check for <tool_call> opening
        if (!this._inToolCall && !this._inThinking && this._buffer.includes('<tool_call>')) {
            this._inToolCall = true;
            this._toolCallBuffer = '';
            const before = this._buffer.split('<tool_call>')[0];
            this._buffer = '';
            if (before.trim()) return { type: 'answer_token', token: before };
            return { type: 'pending' };
        }

        // Check for </tool_call> closing - emit tool_call event with parsed details
        if (this._inToolCall && this._buffer.includes('</tool_call>')) {
            this._inToolCall = false;
            const content = this._buffer.split('</tool_call>')[0];
            this._toolCallBuffer += content;
            const after = this._buffer.split('</tool_call>').slice(1).join('</tool_call>');
            this._buffer = after || '';
            let toolInfo = this._toolCallBuffer.trim();
            try { toolInfo = JSON.parse(toolInfo); } catch { toolInfo = { raw: toolInfo }; }
            this._toolCallBuffer = '';
            return { type: 'tool_call', tool: toolInfo };
        }

        // Check for <voice> opening
        if (!this._inVoice && !this._inThinking && !this._inToolCall && this._buffer.includes('<voice>')) {
            this._inVoice = true;
            const before = this._buffer.split('<voice>')[0];
            const after = this._buffer.split('<voice>').slice(1).join('<voice>');
            this._voiceBuffer = after; // preserve content that arrived after <voice> in same chunk
            this._buffer = '';
            // Handle same-chunk open+close
            if (after.includes('</voice>')) {
                this._inVoice = false;
                const parts = after.split('</voice>');
                this.voiceText = parts[0].trim();
                this._voiceBuffer = '';
                this._buffer = parts.slice(1).join('</voice>');
                if (before.trim()) return { type: 'answer_token', token: before };
                return { type: 'voice', text: this.voiceText };
            }
            if (before.trim()) return { type: 'answer_token', token: before };
            return { type: 'pending' };
        }

        // Check for </voice> closing
        if (this._inVoice && this._buffer.includes('</voice>')) {
            this._inVoice = false;
            const content = this._buffer.split('</voice>')[0];
            this._voiceBuffer += content;
            this.voiceText = this._voiceBuffer.trim();
            const after = this._buffer.split('</voice>').slice(1).join('</voice>');
            this._buffer = after || '';
            return { type: 'voice', text: this.voiceText };
        }

        // Partial tag at boundary - wait for more data
        if (!this._inThinking && !this._inToolCall && !this._inVoice && this._buffer.endsWith('<')) return { type: 'pending' };
        if (!this._inThinking && !this._inToolCall && !this._inVoice && /<t(?:h(?:i(?:n(?:k)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };
        if (!this._inThinking && !this._inToolCall && !this._inVoice && /<t(?:o(?:o(?:l(?:_(?:c(?:a(?:l(?:l)?)?)?)?)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };
        if (!this._inThinking && !this._inToolCall && !this._inVoice && /<v(?:o(?:i(?:c(?:e)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };
        if (this._inThinking && /<\/(?:t(?:h(?:i(?:n(?:k)?)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };
        if (this._inToolCall && /<\/(?:t(?:o(?:o(?:l(?:_(?:c(?:a(?:l(?:l)?)?)?)?)?)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };
        if (this._inVoice && /<\/(?:v(?:o(?:i(?:c(?:e)?)?)?)?)?$/.test(this._buffer)) return { type: 'pending' };

        // Normal token flow
        const content = this._buffer;
        this._buffer = '';

        if (this._inThinking) {
            this.thinkingBuffer += content;
            return { type: 'thinking_token', token: content };
        }
        if (this._inToolCall) {
            this._toolCallBuffer += content;
            return { type: 'pending' };
        }
        if (this._inVoice) {
            this._voiceBuffer += content;
            return { type: 'pending' };
        }
        return { type: 'answer_token', token: content };
    }
}
