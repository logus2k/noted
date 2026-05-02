/**
 * marked math extension - intercepts $$...$$ and $...$ before marked processes
 * the text, so backslashes and underscores inside math are never corrupted by
 * markdown rules.  Renders directly via katex.renderToString().
 *
 * Must run once at module load time (marked.use is idempotent-safe when the
 * extension names are unique).
 */
(function _installMarkedMath() {
    if (typeof marked === 'undefined' || typeof katex === 'undefined') return;
    marked.use({
        extensions: [
            // Block math: $$...$$ (must be checked before inline $)
            {
                name: 'math_block',
                level: 'block',
                start(src) { return src.indexOf('$$'); },
                tokenizer(src) {
                    const m = src.match(/^\$\$([\s\S]+?)\$\$/);
                    if (m) return { type: 'math_block', raw: m[0], math: m[1] };
                },
                renderer(token) {
                    try {
                        return katex.renderToString(token.math.trim(), { displayMode: true, throwOnError: false });
                    } catch { return `<div>$$${token.math}$$</div>`; }
                },
            },
            // Inline math: $...$  (single-line, non-empty content)
            {
                name: 'math_inline',
                level: 'inline',
                start(src) { return src.indexOf('$'); },
                tokenizer(src) {
                    const m = src.match(/^\$([^$\n]+?)\$/);
                    if (m) return { type: 'math_inline', raw: m[0], math: m[1] };
                },
                renderer(token) {
                    try {
                        return katex.renderToString(token.math.trim(), { displayMode: false, throwOnError: false });
                    } catch { return `<span>$${token.math}$</span>`; }
                },
            },
        ],
    });
}());

/**
 * ChatPanel - Chat UI component for the assistant panel.
 * Builds header, messages area, typing indicator, and input area.
 */
export class ChatPanel {

    constructor() {
        this._onSendCallback = null;
        this._onClearCallback = null;
        this._onDebugToggle = null;
        this._onSttToggleCallback = null;
        this._onTtsToggleCallback = null;
        this._onModelChangeCallback = null;
        this._onShowGraphTrace = null;
        // Per-message trace button state. Attached as soon as the
        // graph_provenance SSE event arrives (before thinking/answer
        // streaming) so the user sees "Show graph" alongside "Show
        // reasoning" rather than only after the stream completes.
        this._traceButtonEl = null;
        this._pendingGraphTrace = null;
        // Live trace preview: when the user has the toggle on, typing
        // in the chat input fires a debounced retrieval and updates a
        // dedicated GraphPanel. State + callback wired by app-chat.js.
        this._onLiveTraceQuery = null;
        this._liveTraceTimer = null;
        this._sttActive = false;
        this._build();
    }

    get element() { return this._panel; }
    get titleBarElement() { return this._titleBarEl; }
    get clearButton() { return this._clearBtn; }

    _build() {
        const panel = document.createElement('div');
        panel.className = 'chat-panel';

        // Title bar element (placed in RightPanel's title area)
        this._titleBarEl = document.createElement('div');
        this._titleBarEl.className = 'chat-title-bar-content';

        // Model selector (leftmost)
        this._modelSelect = document.createElement('select');
        this._modelSelect.className = 'chat-model-select';
        this._modelSelect.title = 'Active model';
        this._lastConfirmedModel = null;
        this._modelSelectHandler = () => {
            if (this._onModelChangeCallback) this._onModelChangeCallback(this._modelSelect.value);
        };
        this._modelSelect.addEventListener('change', this._modelSelectHandler);
        this._titleBarEl.appendChild(this._modelSelect);

        // Think checkbox
        this._thinkEnabled = true;
        const thinkLabel = document.createElement('label');
        thinkLabel.className = 'chat-think-label';
        this._thinkCheckbox = document.createElement('input');
        this._thinkCheckbox.type = 'checkbox';
        this._thinkCheckbox.checked = true;
        this._thinkCheckbox.className = 'chat-think-checkbox';
        this._thinkCheckbox.addEventListener('change', () => {
            this._thinkEnabled = this._thinkCheckbox.checked;
        });
        thinkLabel.appendChild(this._thinkCheckbox);
        const thinkText = document.createElement('span');
        thinkText.textContent = 'Extended Thinking';
        thinkLabel.appendChild(thinkText);
        this._titleBarEl.appendChild(thinkLabel);

        // Debug checkbox
        this._debugEnabled = false;
        const debugLabel = document.createElement('label');
        debugLabel.className = 'chat-think-label';
        this._debugCheckbox = document.createElement('input');
        this._debugCheckbox.type = 'checkbox';
        this._debugCheckbox.checked = false;
        this._debugCheckbox.className = 'chat-think-checkbox';
        this._debugCheckbox.addEventListener('change', () => {
            this._debugEnabled = this._debugCheckbox.checked;
            if (this._onDebugToggle) this._onDebugToggle(this._debugEnabled);
        });
        debugLabel.appendChild(this._debugCheckbox);
        const debugText = document.createElement('span');
        debugText.textContent = 'Debug';
        debugLabel.appendChild(debugText);
        this._titleBarEl.appendChild(debugLabel);

        // Live trace preview checkbox - when on, typing in the chat
        // textarea fires a debounced graph_provenance retrieval and
        // updates a dedicated GraphPanel in trace mode in real time.
        this._liveTraceEnabled = false;
        const liveTraceLabel = document.createElement('label');
        liveTraceLabel.className = 'chat-think-label';
        this._liveTraceCheckbox = document.createElement('input');
        this._liveTraceCheckbox.type = 'checkbox';
        this._liveTraceCheckbox.checked = false;
        this._liveTraceCheckbox.className = 'chat-think-checkbox';
        this._liveTraceCheckbox.addEventListener('change', () => {
            this._liveTraceEnabled = this._liveTraceCheckbox.checked;
            // When the toggle is turned off, cancel any pending live fire.
            if (!this._liveTraceEnabled && this._liveTraceTimer) {
                clearTimeout(this._liveTraceTimer);
                this._liveTraceTimer = null;
            }
        });
        liveTraceLabel.title = 'When on, typing in the chat fires a live KG trace preview as you type';
        liveTraceLabel.appendChild(this._liveTraceCheckbox);
        const liveTraceText = document.createElement('span');
        liveTraceText.textContent = 'Live trace';
        liveTraceLabel.appendChild(liveTraceText);
        this._titleBarEl.appendChild(liveTraceLabel);

        // Vector RAG checkbox — when off, the LLM's tool list excludes
        // search_docs (and graph_and_vector_search, which needs both
        // halves), so the model won't fire vector retrieval this turn.
        this._vectorRagEnabled = true;
        const vectorLabel = document.createElement('label');
        vectorLabel.className = 'chat-think-label';
        this._vectorRagCheckbox = document.createElement('input');
        this._vectorRagCheckbox.type = 'checkbox';
        this._vectorRagCheckbox.checked = true;
        this._vectorRagCheckbox.className = 'chat-think-checkbox';
        this._vectorRagCheckbox.addEventListener('change', () => {
            this._vectorRagEnabled = this._vectorRagCheckbox.checked;
        });
        vectorLabel.title = 'Disable to suppress vector RAG retrieval (search_docs + graph_and_vector_search) for the next turn.';
        vectorLabel.appendChild(this._vectorRagCheckbox);
        const vectorText = document.createElement('span');
        vectorText.textContent = 'Vector RAG';
        vectorLabel.appendChild(vectorText);
        this._titleBarEl.appendChild(vectorLabel);

        // GraphRAG checkbox — when off, the LLM's tool list excludes
        // research_topic, query_knowledge_graph, and graph_and_vector_search.
        this._graphRagEnabled = true;
        const graphLabel = document.createElement('label');
        graphLabel.className = 'chat-think-label';
        this._graphRagCheckbox = document.createElement('input');
        this._graphRagCheckbox.type = 'checkbox';
        this._graphRagCheckbox.checked = true;
        this._graphRagCheckbox.className = 'chat-think-checkbox';
        this._graphRagCheckbox.addEventListener('change', () => {
            this._graphRagEnabled = this._graphRagCheckbox.checked;
        });
        graphLabel.title = 'Disable to suppress GraphRAG retrieval (research_topic, query_knowledge_graph, graph_and_vector_search) for the next turn.';
        graphLabel.appendChild(this._graphRagCheckbox);
        const graphText = document.createElement('span');
        graphText.textContent = 'GraphRAG';
        graphLabel.appendChild(graphText);
        this._titleBarEl.appendChild(graphLabel);

        // Clear button
        this._clearBtn = document.createElement('button');
        this._clearBtn.className = 'chat-clear-btn';
        this._clearBtn.title = 'Clear chat';
        this._clearBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" fill="#f4a0a0"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>';
        this._clearBtn.addEventListener('click', () => {
            if (this._onClearCallback) this._onClearCallback();
        });

        // Messages area
        this._messagesArea = document.createElement('div');
        this._messagesArea.className = 'chat-messages';
        // Delegated handler: chat-citation badges (rendered by
        // _renderCitations) carry their tag in data-citation-tag.
        this._messagesArea.addEventListener('click', (e) => {
            const cite = e.target.closest('a.chat-citation');
            if (cite && this._onCitationClick) {
                e.preventDefault();
                this._onCitationClick(cite.dataset.citationTag, cite);
            }
        });
        panel.appendChild(this._messagesArea);

        // Typing indicator
        this._typingIndicator = document.createElement('div');
        this._typingIndicator.className = 'chat-typing-indicator';
        this._typingIndicator.innerHTML = '<span></span><span></span><span></span>';
        this._typingIndicator.style.display = 'none';
        this._messagesArea.appendChild(this._typingIndicator);

        // Input area
        const inputArea = document.createElement('div');
        inputArea.className = 'chat-input-area';

        // STT button
        this._sttBtn = document.createElement('button');
        this._sttBtn.className = 'chat-stt-btn';
        this._sttBtn.title = 'Voice input';
        // Two icon variants: OFF shows the mic with a small X to the upper
        // right (mirrors the speaker's off-state pattern so the user can
        // tell the active/inactive state at a glance). ON drops the X.
        this._sttIconOn = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="1" width="6" height="12" rx="3" fill="#f4b4b4"/><path d="M12 1a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>';
        this._sttIconOff = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="1" width="6" height="12" rx="3" fill="#dddddd"/><path d="M12 1a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="18" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/><line x1="22" y1="2" x2="16" y2="8"/><line x1="16" y1="2" x2="22" y2="8"/></svg>';
        this._sttBtn.innerHTML = this._sttIconOff;
        this._sttBtn.addEventListener('click', () => {
            this._sttActive = !this._sttActive;
            this._sttBtn.classList.toggle('active', this._sttActive);
            this._sttBtn.innerHTML = this._sttActive ? this._sttIconOn : this._sttIconOff;
            if (this._onSttToggleCallback) this._onSttToggleCallback(this._sttActive);
        });
        inputArea.appendChild(this._sttBtn);

        // Text input
        this._input = document.createElement('textarea');
        this._input.className = 'chat-input';
        this._input.placeholder = 'Type a message...';
        this._input.rows = 1;
        this._input.spellcheck = false;
        this._input.addEventListener('input', () => {
            this._autoGrow();
            this._scheduleLiveTrace();
        });
        this._input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._handleSend();
            }
        });
        inputArea.appendChild(this._input);

        // Send button
        const sendBtn = document.createElement('button');
        sendBtn.className = 'chat-send-btn';
        sendBtn.title = 'Send message';
        sendBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 2 15 22 11 13 2 9" fill="#b4e4b4"/><line x1="22" y1="2" x2="11" y2="13"/></svg>';
        sendBtn.addEventListener('click', () => this._handleSend());
        inputArea.appendChild(sendBtn);

        // TTS button
        this._ttsBtn = document.createElement('button');
        this._ttsBtn.className = 'chat-tts-btn';
        this._ttsBtn.title = 'Text to speech';
        this._ttsIconOff = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19" fill="#b4d4f4"/><line x1="22" y1="9" x2="16" y2="15"/><line x1="16" y1="9" x2="22" y2="15"/></svg>';
        this._ttsIconOn = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19" fill="#b4d4f4"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
        this._ttsBtn.innerHTML = this._ttsIconOff;
        this._ttsActive = false;
        this._ttsBtn.addEventListener('click', () => {
            this._ttsActive = !this._ttsActive;
            this._ttsBtn.classList.toggle('active', this._ttsActive);
            this._ttsBtn.innerHTML = this._ttsActive ? this._ttsIconOn : this._ttsIconOff;
            if (this._onTtsToggleCallback) this._onTtsToggleCallback();
        });
        inputArea.appendChild(this._ttsBtn);

        panel.appendChild(inputArea);

        // Bottom bar (token count)
        const bottomBar = document.createElement('div');
        bottomBar.className = 'chat-bottom-bar';

        // Token counter
        this._tokenCounter = document.createElement('div');
        this._tokenCounter.className = 'chat-token-counter';
        this._tokenCounter.title = 'Estimated token usage';
        bottomBar.appendChild(this._tokenCounter);

        panel.appendChild(bottomBar);

        this._panel = panel;
    }

    _autoGrow() {
        this._input.style.height = 'auto';
        this._input.style.height = Math.min(this._input.scrollHeight, 120) + 'px';
    }

    get thinkEnabled() { return this._thinkEnabled; }
    get vectorRagEnabled() { return this._vectorRagEnabled; }
    get graphRagEnabled() { return this._graphRagEnabled; }

    /** Populate the model dropdown. Called after health check. */
    setModels(models, activeModel) {
        const prev = this._modelSelect.value;
        this._modelSelect.innerHTML = '';
        for (const m of models) {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.display_name || m.id;
            if (m.id === activeModel) opt.selected = true;
            this._modelSelect.appendChild(opt);
        }
        if (!activeModel && prev) {
            this._modelSelect.value = prev;
        }
        this._lastConfirmedModel = this._modelSelect.value;
    }

    /** Legacy: called from onModelInfo path. Adds a single option if empty. */
    setModelName(name) {
        if (!name || this._modelSelect.options.length > 0) return;
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        this._modelSelect.appendChild(opt);
    }

    onModelChange(cb) { this._onModelChangeCallback = cb; }

    /** Register a click handler for citation badges. The callback receives
     * the tag (e.g. `markdown_chunk:abc123def4`) and the anchor element. */
    onCitationClick(cb) { this._onCitationClick = cb; }

    /** Revert the dropdown to the previously confirmed model without firing the change event. */
    revertModelSelect() {
        if (this._lastConfirmedModel) {
            this._modelSelect.removeEventListener('change', this._modelSelectHandler);
            this._modelSelect.value = this._lastConfirmedModel;
            this._modelSelect.addEventListener('change', this._modelSelectHandler);
        }
    }

    _handleSend() {
        const text = this._input.value.trim();
        if (!text) return;

        // Cancel any pending live-trace fire - the real chat flow takes
        // over and will emit the actual graph_provenance event.
        if (this._liveTraceTimer) {
            clearTimeout(this._liveTraceTimer);
            this._liveTraceTimer = null;
        }

        this.addMessage('user', text);
        this._input.value = '';
        this._input.style.height = 'auto';

        if (this._onSendCallback) {
            this._onSendCallback(text);
        }
    }

    /** Register a callback for live trace previews. Receives the typed
     * question text whenever the user pauses typing (debounced) and the
     * "Live trace" checkbox is on. */
    onLiveTraceQuery(callback) {
        this._onLiveTraceQuery = callback;
    }

    /** Schedule a live trace fire after the user pauses typing. Skipped
     * when: toggle is off, callback unset, input too short (< 8 chars),
     * or a streaming message is already in flight (the real chat flow
     * is currently producing an answer). 350ms debounce keeps the
     * noted-rag GPU embed queue manageable even for fast typists. */
    _scheduleLiveTrace() {
        if (this._liveTraceTimer) {
            clearTimeout(this._liveTraceTimer);
            this._liveTraceTimer = null;
        }
        if (!this._liveTraceEnabled || !this._onLiveTraceQuery) return;
        if (this._streamingMsg) return; // chat flow already producing an answer
        const text = (this._input.value || '').trim();
        if (text.length < 8) return;
        this._liveTraceTimer = setTimeout(() => {
            this._liveTraceTimer = null;
            try { this._onLiveTraceQuery(text); } catch {}
        }, 350);
    }

    addMessage(role, text, thinkingContent = null, actionLabel = null) {
        const msg = document.createElement('div');
        msg.className = `chat-message chat-message-${role}`;

        if (role === 'assistant') {
            // Check if this is an error message
            if (text.startsWith('Error:')) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'chat-error';
                errorDiv.textContent = text;
                msg.appendChild(errorDiv);
            } else {
                // Optional collapsible reasoning section. Reuse the
                // streamed-message builder so history-restored thinking
                // gets markdown rendering + citation badges, same as
                // freshly-streamed messages.
                if (thinkingContent && thinkingContent.trim()) {
                    msg.appendChild(this._buildThinkingDetails(thinkingContent.trim()));
                }

                const answerDiv = document.createElement('div');
                answerDiv.innerHTML = this._renderMarkdown(text);
                answerDiv.querySelectorAll('pre code[class*="language-"]').forEach((block) => {
                    hljs.highlightElement(block);
                });
                this._renderMath(answerDiv);
                this._addCopyButtons(answerDiv);
                // History-restored messages must run the citation transform too;
                // finalizeStreamingMessage handles fresh streams, this handles
                // anything reloaded from server-side memory. Without this call
                // the bracket tags (`[markdown_chunk:hex]`, `[E:..]`, etc.)
                // appear as raw text on page reload.
                this._renderCitations(answerDiv);
                msg.appendChild(answerDiv);
                // Stash raw text so the top-right action bar's Copy and
                // Copy-All buttons can copy the original tagged text rather
                // than the rendered DOM (rendered badges have textContent
                // = ordinal "1", "2", etc., which is useless when copied).
                msg._answerRaw = text || '';
                msg._thinkingRaw = (thinkingContent || '').trim();
                this._createMessageActions(msg);
            }
        } else {
            // Action badge for assistant menu actions
            if (actionLabel) {
                const badge = document.createElement('span');
                badge.className = 'chat-action-badge';
                badge.textContent = actionLabel;
                msg.appendChild(badge);
            }
            // User messages: render markdown for code blocks
            const userDiv = document.createElement('div');
            userDiv.innerHTML = this._renderMarkdown(text);
            userDiv.querySelectorAll('pre code[class*="language-"]').forEach((block) => {
                hljs.highlightElement(block);
            });
            this._renderMath(userDiv);
            msg.appendChild(userDiv);
        }

        // Insert before typing indicator
        this._messagesArea.insertBefore(msg, this._typingIndicator);
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** Start a new streaming assistant message. Returns nothing - tokens go to appendToken(). */
    startStreamingMessage() {
        this._streamingMsg = document.createElement('div');
        this._streamingMsg.className = 'chat-message chat-message-assistant';
        this._streamingToolBar = document.createElement('div');
        this._streamingToolBar.className = 'chat-tool-bar';
        this._streamingMsg.appendChild(this._streamingToolBar);
        this._streamingContent = document.createElement('div');
        this._streamingContent.className = 'chat-streaming-content';
        this._streamingMsg.appendChild(this._streamingContent);
        this._streamingRaw = '';
        this._messagesArea.insertBefore(this._streamingMsg, this._typingIndicator);
        // Top-right action bar (Copy All / Copy answer) — created immediately
        // so a Show graph icon can be lazily attached when graph_provenance
        // arrives. Raw text is empty until finalizeStreamingMessage stashes it.
        this._streamingMsg._answerRaw = '';
        this._streamingMsg._thinkingRaw = '';
        this._createMessageActions(this._streamingMsg);
    }

    /** Show skill badges for statically injected skills. */
    showSkillBadges(skillNames) {
        if (!skillNames || !skillNames.length) return;
        if (!this._streamingMsg) this.startStreamingMessage();
        for (const name of skillNames) {
            const badge = document.createElement('span');
            badge.className = 'chat-skill-badge';
            // Icon matches Explorer's Skills folder (fa-book-open).
            badge.innerHTML = `<i class="fa-solid fa-book-open"></i> ${name}`;
            badge.title = `Skill: ${name} (auto-injected)`;
            this._streamingToolBar.appendChild(badge);
        }
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** Append a tool call badge to the tool bar (persistent, not overwritten by markdown). */
    appendToolBadge(toolInfo) {
        if (!this._streamingMsg) this.startStreamingMessage();
        const badge = document.createElement('span');
        badge.className = 'chat-tool-badge';
        const name = toolInfo?.name || 'tool';
        const args = toolInfo?.args ? JSON.stringify(toolInfo.args, null, 2) : '';
        // Icon matches Explorer's Tools folder (fa-wrench).
        badge.innerHTML = `<i class="fa-solid fa-wrench"></i> ${name}`;
        badge.title = args ? `${name}(${args})` : name;
        this._streamingToolBar.appendChild(badge);
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** Append a token to the current streaming message. */
    appendToken(token) {
        if (!this._streamingMsg) this.startStreamingMessage();
        // Deferred-collapse hand-off: if reasoning finished but the
        // collapse was held back waiting for the answer to start, do it
        // on the first non-empty answer token. Skip empty/whitespace-
        // only tokens so a stray "\n" doesn't fire the collapse early.
        if (this._liveThinkingPendingCollapse && this._liveThinkingDetails && token && token.trim()) {
            this._liveThinkingDetails.open = false;
            const label = this._liveThinkingDetails._summaryLabel;
            if (label) label.textContent = 'Show thinking';
            this._liveThinkingPendingCollapse = false;
        }
        this._recordStreamingChars(token);
        this._streamingRaw += token;
        // Re-render markdown on each token (marked.js is fast enough for this)
        this._streamingContent.innerHTML = this._renderMarkdown(this._streamingRaw);
        // Transform citation tags into badges live as they stream in.
        // Cheap (TreeWalker over text nodes only) and gives the user
        // immediate visual feedback instead of seeing raw `[markdown_chunk:hex]`
        // brackets until finalize.
        this._renderCitations(this._streamingContent);
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** Finalize the streaming message - apply syntax highlighting and optional thinking section.
     *
     * @param {string|null} thinkingContent - reasoning text, if any
     * @param {object|null} graphProvenance - per-answer KG payload from
     *        graph_and_vector_search, when the model used that tool.
     *        Triggers a "Show graph trace" button next to the reasoning section.
     */
    finalizeStreamingMessage(thinkingContent = null, graphProvenance = null) {
        if (!this._streamingMsg) return;

        // Insert thinking collapsible before the content (skip if empty/
        // whitespace, OR if a live thinking section already exists from
        // streaming - which is the normal path now).
        const thinkingDetails = (thinkingContent && thinkingContent.trim() && !this._liveThinkingDetails)
            ? this._buildThinkingDetails(thinkingContent.trim())
            : this._liveThinkingDetails;
        if (thinkingDetails && !thinkingDetails.parentNode) {
            this._streamingMsg.insertBefore(thinkingDetails, this._streamingContent);
        }
        // Defense-in-depth: re-run citation transform on the (possibly
        // streamed) thinking body. setLiveThinkingContent calls this at
        // thinking_end, but if the thinking_end signal was missed or
        // short-circuited, the live body would still hold raw `[tag]`
        // text. _renderCitations only mutates matching text nodes, so
        // a second pass over already-badged content is a no-op.
        if (thinkingDetails && this._liveThinkingBody) {
            this._renderCitations(this._liveThinkingBody);
        }

        // Trace button: normally attached early via setPendingGraphTrace
        // when the graph_provenance SSE event arrives (before answer
        // streaming starts). If for some reason that didn't happen but
        // the payload still made it to finalize, attach now as a fallback.
        const traceData = graphProvenance || this._pendingGraphTrace;
        if (traceData && !this._traceButtonEl && this._onShowGraphTrace && this._graphRagEnabled) {
            this._traceButtonEl = this._attachTraceButton(thinkingDetails, traceData);
        }

        // Reset per-message state for the next message
        this._traceButtonEl = null;
        this._pendingGraphTrace = null;
        this._liveThinkingDetails = null;
        this._liveThinkingBody = null;
        this._liveThinkingSummary = null;
        this._liveThinkingRaw = '';
        this._liveThinkingComplete = false;

        // Final render with syntax highlighting
        this._streamingContent.innerHTML = this._renderMarkdown(this._streamingRaw);
        this._streamingContent.querySelectorAll('pre code[class*="language-"]').forEach((block) => {
            hljs.highlightElement(block);
        });
        this._renderMath(this._streamingContent);
        this._addCopyButtons(this._streamingContent);
        this._renderCitations(this._streamingContent);
        this._streamingContent.classList.remove('chat-streaming-content');

        // Stash the raw text on the message element so the action bar's
        // Copy and Copy-All buttons read original tagged text rather than
        // the rendered DOM (which has badge ordinals, not chunk ids).
        this._streamingMsg._answerRaw = this._streamingRaw || '';
        this._streamingMsg._thinkingRaw = (thinkingContent || '').trim();

        this._streamingMsg = null;
        this._streamingContent = null;
        this._streamingRaw = '';
    }

    /** Defang any `[citation_tag]:` line that would otherwise be parsed by
     * marked as a markdown reference-link definition. The model often
     * lists chunks like:
     *
     *     [markdown_chunk:abc123]:
     *     Defines layer normalization as ...
     *
     * Marked sees `[label]:\n<paragraph>` and CONSUMES the bracket as a
     * link-ref definition, so the tag never reaches `_renderCitations`
     * and no badge is rendered. We insert a zero-width space between
     * `]` and `:` for any bracketed token whose content matches our
     * citation forms. The colon is still visible to the reader; the
     * ZWSP is invisible; marked no longer recognizes the definition;
     * the bracket survives for badge rendering.
     */
    _defuseCitationRefDefs(text) {
        if (!text) return text;
        // Mirror the citation forms from _renderCitations. Any bracket
        // whose body matches one of these followed immediately by `]:`
        // gets a ZWSP injected.
        return text.replace(
            /(\[(?:markdown_chunk:[0-9a-f]{8,16}|[0-9a-f]{8,16}|E:[^,\]]+|R:[^,\]]+|C\d+)\]):/g,
            '$1​:',
        );
    }

    _renderMarkdown(text) {
        return marked.parse(this._defuseCitationRefDefs(text || ''));
    }

    /** Replace citation tags in the rendered message with clickable badges.
     * Per-message dedup: same tag → same number. Skips text inside
     * <pre>/<code>. Click dispatched via delegated handler on `_messagesArea`.
     *
     * Four tag forms (Phase 1A + Phase 2):
     *   `[markdown_chunk:hex]` / `[hex]`   - chunk (green badge)
     *   `[E:entity_id]`                    - entity (blue badge)
     *   `[R:src>type>tgt]`                 - relationship (orange badge)
     *   `[Cn]`                             - community (purple badge)
     * Comma-joined inside one bracket is supported for any combination.
     * Bare hex is normalized to `markdown_chunk:hex` for the data-tag.
     */
    _renderCitations(rootEl) {
        if (!rootEl) return;
        // Each tag part. Note R: uses `[^,\]]+` (no comma/bracket) so
        // comma-separated groups parse correctly; the model's R-form
        // always includes `>` separators inside the body.
        const _PART = [
            'markdown_chunk:[0-9a-f]{8,16}',
            '[0-9a-f]{8,16}',          // bare-hex chunk (model often abbreviates)
            'E:[^,\\]]+',
            'R:[^,\\]]+',
            'C\\d+',
        ].join('|');
        const GROUP_RE = new RegExp(`\\[((?:${_PART})(?:\\s*,\\s*(?:${_PART}))*)\\]`, 'g');
        // Stateless clone (no /g) for the walker's yes/no acceptNode test.
        // Using GROUP_RE.test() here is a JS gotcha: /g-flag .test() advances
        // lastIndex between calls, so when the walker visits multiple text
        // nodes that each contain a tag, every subsequent .test() resumes
        // from the previous lastIndex and returns false if the new node's
        // text is shorter than that index — silently rejecting valid nodes
        // and stranding their tags as raw bracket text.
        const TEST_RE = new RegExp(`\\[((?:${_PART})(?:\\s*,\\s*(?:${_PART}))*)\\]`);
        const TAG_RE = new RegExp(_PART, 'g');
        const numbering = new Map(); // canonical tag -> ordinal
        const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
            acceptNode: (node) => {
                if (node.parentElement && node.parentElement.closest('pre, code')) {
                    return NodeFilter.FILTER_REJECT;
                }
                return TEST_RE.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
            },
        });
        const targets = [];
        let n;
        while ((n = walker.nextNode())) targets.push(n);
        for (const textNode of targets) {
            GROUP_RE.lastIndex = 0;
            const text = textNode.nodeValue;
            const frag = document.createDocumentFragment();
            let lastIdx = 0;
            let m;
            while ((m = GROUP_RE.exec(text)) !== null) {
                if (m.index > lastIdx) {
                    frag.appendChild(document.createTextNode(text.slice(lastIdx, m.index)));
                }
                const parts = m[1].match(TAG_RE) || [];
                parts.forEach((rawTag) => {
                    // Normalize + classify
                    let tag = rawTag.trim();
                    let typeClass;
                    let title;
                    if (tag.startsWith('E:')) {
                        typeClass = 'cite-entity';
                        title = 'Open entity in graph trace';
                    } else if (tag.startsWith('R:')) {
                        typeClass = 'cite-edge';
                        title = 'Open relationship in graph trace';
                    } else if (/^C\d+$/.test(tag)) {
                        typeClass = 'cite-community';
                        title = 'Open community summary';
                    } else {
                        // chunk: normalize bare hex to canonical
                        if (/^[0-9a-f]{8,16}$/.test(tag)) tag = `markdown_chunk:${tag}`;
                        typeClass = 'cite-chunk';
                        title = 'Open source document';
                    }
                    if (!numbering.has(tag)) numbering.set(tag, numbering.size + 1);
                    const ord = numbering.get(tag);
                    const a = document.createElement('a');
                    a.className = `chat-citation ${typeClass}`;
                    a.href = 'javascript:void(0)';
                    a.dataset.citationTag = tag;
                    a.title = title;
                    a.textContent = String(ord);
                    frag.appendChild(a);
                });
                lastIdx = m.index + m[0].length;
            }
            if (lastIdx < text.length) {
                frag.appendChild(document.createTextNode(text.slice(lastIdx)));
            }
            textNode.parentNode.replaceChild(frag, textNode);
        }
    }

    /** Build a `<details class="chat-thinking">` element for finalized
     * (non-streaming) reasoning. Used when the live thinking section
     * never opened (e.g. think_enabled was off but the model emitted
     * a thinking block anyway). */
    _buildThinkingDetails(thinkingText) {
        const details = document.createElement('details');
        details.className = 'chat-thinking';
        const summary = document.createElement('summary');
        // Same label-span pattern as the live section so a sibling trace
        // button inside <summary> doesn't get clobbered on toggle.
        const labelEl = document.createElement('span');
        labelEl.className = 'chat-thinking-summary-label';
        labelEl.textContent = 'Show thinking';
        summary.appendChild(labelEl);
        details.addEventListener('toggle', () => {
            labelEl.textContent = details.open ? 'Hide thinking' : 'Show thinking';
        });
        details.appendChild(summary);
        details._summaryLabel = labelEl;
        const thinkBody = document.createElement('div');
        thinkBody.className = 'chat-thinking-body';
        // Render the reasoning as markdown so lists/code/bold land
        // formatted, same as the answer body. Models often write
        // numbered plans + inline `code` here.
        thinkBody.innerHTML = this._renderMarkdown(thinkingText || '');
        thinkBody.querySelectorAll('pre code[class*="language-"]').forEach((block) => {
            try { hljs.highlightElement(block); } catch (_) { /* noop */ }
        });
        // Transform any valid citation tags in the reasoning into badges,
        // same as the answer body.
        this._renderCitations(thinkBody);
        details.appendChild(thinkBody);
        return details;
    }

    /** Place a "Show graph" affordance next to the reasoning section
     * (or just above the answer if no reasoning exists). Uses a <span> with
     * role="button" rather than a real <button> so it inherits the inline
     * baseline of the adjacent <summary> and avoids the native button's
     * pressed-down effect. Click invokes the registered onShowGraphTrace
     * callback with the payload so the app can open the GraphPanel in
     * trace mode. */
    _attachTraceButton(thinkingDetails, payload) {
        const btn = document.createElement('button');
        btn.className = 'chat-msg-action-btn chat-trace-btn-icon';
        btn.type = 'button';
        btn.title = 'Show Graph';
        btn.innerHTML = '<i class="fa-solid fa-share-nodes"></i>';
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            // Pass the button as second arg so the handler can track a
            // per-button GraphPanel ref and reuse it instead of opening a
            // duplicate panel on every click of the same icon.
            if (this._onShowGraphTrace) this._onShowGraphTrace(payload, btn);
        });
        // Insert at the START of the message-level action bar (top-right).
        // Falls back to placing next to the streaming content if the bar
        // isn't there yet (defensive — startStreamingMessage normally
        // creates it before this method ever runs).
        const msg = this._streamingMsg
            || (thinkingDetails && thinkingDetails.closest('.chat-message-assistant'));
        const bar = msg && msg._actionsBar;
        if (bar) {
            bar.insertBefore(btn, bar.firstChild);
        } else if (this._streamingMsg && this._streamingContent) {
            this._streamingMsg.insertBefore(btn, this._streamingContent);
        }
        return btn;
    }

    /** Called by ChatService as soon as the `graph_provenance` SSE event
     * arrives (which happens RIGHT AFTER the tool dispatch, well before
     * thinking and answer tokens stream in). Bootstraps the streaming
     * message bubble if needed and attaches the "Show graph" button now,
     * so the user sees the affordance early instead of only at finalize. */
    setPendingGraphTrace(payload) {
        this._pendingGraphTrace = payload;
        if (this._traceButtonEl) return; // already attached this turn
        // If the user disabled GraphRAG for this turn, suppress the
        // "Show graph" affordance even if a provenance event happens to
        // arrive — defense in depth so the UI honors the toggle.
        if (!this._graphRagEnabled) return;
        if (!this._streamingMsg) this.startStreamingMessage();
        this._traceButtonEl = this._attachTraceButton(this._liveThinkingDetails, payload);
    }

    /** Register a callback invoked when the user clicks "Show graph trace"
     * on an assistant message. Receives the graph_provenance payload. */
    onShowGraphTrace(callback) {
        this._onShowGraphTrace = callback;
    }

    setThinkingIndicator(visible) {
        if (visible) {
            this._typingIndicator.style.display = 'flex';
            this._typingIndicator.setAttribute('data-label', 'Reasoning...');
        } else {
            this._typingIndicator.style.display = 'none';
            this._typingIndicator.removeAttribute('data-label');
        }
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** Start a live reasoning section ABOVE the answer-streaming area.
     * Returns silently if a streaming message isn't started yet (defensive).
     * Creates a <details open> element so the reasoning is visible while it
     * streams; endLiveThinkingSection() collapses it once thinking is done.
     */
    startLiveThinkingSection() {
        // Auto-create the streaming message bubble if it doesn't exist yet.
        // Badge rendering paths used to do this implicitly; they're gone now,
        // so the reasoning panel needs its own bootstrap or it never attaches
        // to anything and the live stream silently disappears.
        if (!this._streamingMsg) this.startStreamingMessage();
        if (this._liveThinkingDetails) return;
        const details = document.createElement('details');
        details.className = 'chat-thinking chat-thinking-live';
        details.open = true;
        const summary = document.createElement('summary');
        // Keep the label as its own span so we can update its text
        // without nuking sibling children (e.g. the "Show graph" trace
        // button that gets appended into <summary>). textContent on the
        // <summary> itself would clobber every child element.
        const labelEl = document.createElement('span');
        labelEl.className = 'chat-thinking-summary-label';
        labelEl.textContent = 'Thinking…';
        summary.appendChild(labelEl);
        // Per-instance "thinking finished" flag captured by the toggle
        // closure. We CANNOT rely on `this._liveThinkingComplete` here
        // because that's panel-level state - reset to false at every
        // finalizeStreamingMessage(), which would then mute the toggle
        // handlers of all earlier finalized messages.
        let completedForThisMessage = false;
        details.addEventListener('toggle', () => {
            if (completedForThisMessage) {
                labelEl.textContent = details.open ? 'Hide thinking' : 'Show thinking';
            }
        });
        // Stash a setter so endLiveThinkingSection can flip the per-message
        // flag without reaching into this closure.
        details._markThinkingComplete = () => { completedForThisMessage = true; };
        // Stash the label for endLiveThinkingSection's text update.
        details._summaryLabel = labelEl;
        details.appendChild(summary);
        const body = document.createElement('div');
        body.className = 'chat-thinking-body';
        details.appendChild(body);
        // If the trace button was attached BEFORE the thinking section
        // (because graph_provenance arrived before thinking_start), it
        // sits at "before _streamingContent". Inserting thinking at the
        // same position pushes the button after thinking, but only if we
        // insert thinking BEFORE the button. The simplest fix: insert
        // thinking before the trace button if the button exists, else
        // before the streaming content.
        const insertionAnchor = (this._traceButtonEl && this._traceButtonEl.parentNode === this._streamingMsg)
            ? this._traceButtonEl
            : this._streamingContent;
        this._streamingMsg.insertBefore(details, insertionAnchor);
        this._liveThinkingDetails = details;
        this._liveThinkingBody = body;
        this._liveThinkingSummary = summary;
        this._liveThinkingRaw = '';
        this._liveThinkingComplete = false;
    }

    /** Append streamed reasoning content to the live thinking body. */
    appendLiveThinkingToken(token) {
        if (!this._liveThinkingBody || !token) return;
        this._recordStreamingChars(token);
        this._liveThinkingRaw += token;
        // Strip leading whitespace at display time only - models often
        // emit one or two blank lines at the start of <think>, which
        // pre-wrap renders as visible empty paragraphs at the top of
        // every reasoning block. Keep the raw buffer intact in case the
        // sync at thinking_end depends on exact byte parity.
        this._liveThinkingBody.innerHTML = this._renderMarkdown(
            this._liveThinkingRaw.replace(/^\s+/, '')
        );
        this._updateLiveThinkingLabel();
        this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
    }

    /** While the thinking block is streaming, surface the most recent
     * level-1 markdown heading (`# Title`) as the summary label so the
     * user sees the model's current step instead of a static "Thinking…".
     * Falls back to "Thinking…" until the first heading arrives. Skips
     * `#` lines inside fenced code blocks. Reverts to the standard
     * Show/Hide labels at endLiveThinkingSection. */
    _updateLiveThinkingLabel() {
        const labelEl = this._liveThinkingDetails && this._liveThinkingDetails._summaryLabel;
        if (!labelEl) return;
        let lastHeading = null;
        let inCode = false;
        for (const line of this._liveThinkingRaw.split('\n')) {
            if (line.trimStart().startsWith('```')) {
                inCode = !inCode;
                continue;
            }
            if (inCode) continue;
            const m = line.match(/^#\s+(.+?)\s*$/);
            if (m) lastHeading = m[1];
        }
        labelEl.textContent = lastHeading || 'Thinking…';
    }

    /** Replace the live thinking body content with the provided text.
     * Used at thinking_end to sync the live body with the parser's
     * fully captured thinkingBuffer in case any chunk-boundary slice
     * was missed (the chunk carrying </think> may have also carried the
     * tail of the body that the parser appended but didn't emit). */
    setLiveThinkingContent(text) {
        if (!this._liveThinkingBody) return;
        this._liveThinkingRaw = text || '';
        this._liveThinkingBody.innerHTML = this._renderMarkdown(
            this._liveThinkingRaw.replace(/^\s+/, '')
        );
        // Apply syntax highlighting once the body is finalized.
        this._liveThinkingBody.querySelectorAll('pre code[class*="language-"]').forEach((block) => {
            try { hljs.highlightElement(block); } catch (_) { /* noop */ }
        });
        // Transform any valid citation tags in the reasoning into badges,
        // same as the answer body. Done at finalize (not per token) so we
        // pay the regex pass once. Invalid tags stay as raw text — that
        // matches the answer-body behavior and is a visible signal of
        // model fabrication.
        this._renderCitations(this._liveThinkingBody);
    }

    /** Mark the reasoning section complete. The auto-collapse is
     * DEFERRED until the first answer token arrives in appendToken(),
     * so the user keeps seeing the reasoning content while the model is
     * still preparing the answer (tool execution + synthesis prefill).
     * Collapsing immediately at thinking_end leaves the user staring at
     * a blank space until the answer starts streaming. */
    endLiveThinkingSection() {
        if (!this._liveThinkingDetails) return;
        this._liveThinkingComplete = true;
        if (this._liveThinkingDetails._markThinkingComplete) {
            this._liveThinkingDetails._markThinkingComplete();
        }
        // Revert the summary label from the live "current heading" form
        // back to the standard Show/Hide labels reflecting the section's
        // current open state. Without this, the last-heading text would
        // remain visible after the model finished thinking.
        if (this._liveThinkingDetails._summaryLabel) {
            this._liveThinkingDetails._summaryLabel.textContent =
                this._liveThinkingDetails.open ? 'Hide thinking' : 'Show thinking';
        }
        // Arm the deferred collapse — appendToken will trigger it when
        // the first non-empty answer token actually arrives.
        this._liveThinkingPendingCollapse = true;
    }

    clearMessages() {
        const messages = this._messagesArea.querySelectorAll('.chat-message');
        messages.forEach(m => m.remove());
    }

    /** Render LaTeX math expressions in a container using KaTeX auto-render. */
    _renderMath(container) {
        if (typeof renderMathInElement !== 'undefined') {
            renderMathInElement(container, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false },
                    { left: '\\(', right: '\\)', display: false },
                    { left: '\\[', right: '\\]', display: true },
                ],
                throwOnError: false,
            });
        }
    }

    /** Create the top-right action bar for an assistant message bubble.
     * Holds (left → right): Show graph icon (lazy-attached when
     * graph_provenance arrives), Copy All (thinking + answer). The Copy
     * button reads the raw text stashed on the message element by
     * addMessage / finalizeStreamingMessage — copying from the rendered
     * DOM would lose the citation tags (badges have textContent = ordinal
     * number) so the stashed raw is the source of truth. */
    _createMessageActions(messageEl) {
        const bar = document.createElement('div');
        bar.className = 'chat-msg-actions';

        // Two-square icon (a back document + a front document) for "Copy All"
        // — the classic "copy multiple" affordance.
        const copyAllIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        const checkIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22863a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

        const copyAll = document.createElement('button');
        copyAll.className = 'chat-msg-action-btn';
        copyAll.type = 'button';
        copyAll.title = 'Copy Answer';
        copyAll.innerHTML = copyAllIcon;
        copyAll.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const t = messageEl._thinkingRaw || '';
            const a = messageEl._answerRaw || '';
            const text = t ? (t.trim() + '\n\n---\n\n' + a.trim()) : a.trim();
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                copyAll.innerHTML = checkIcon;
                setTimeout(() => { copyAll.innerHTML = copyAllIcon; }, 1200);
            }).catch(() => { /* swallow */ });
        });

        // Order in DOM: trace (lazy, prepended later) | Copy All.
        bar.appendChild(copyAll);
        messageEl.appendChild(bar);
        messageEl._actionsBar = bar;
        return bar;
    }

    /** Add copy buttons to all <pre> blocks in a container. */
    _addCopyButtons(container) {
        container.querySelectorAll('pre').forEach((pre) => {
            if (pre.querySelector('.chat-copy-btn')) return; // already added
            const code = pre.querySelector('code');
            if (!code || !code.textContent.trim()) return; // skip empty blocks
            const btn = document.createElement('button');
            btn.className = 'chat-copy-btn';
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" fill="#a8d8a0"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
            btn.title = 'Copy to clipboard';
            const copyIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" fill="#a8d8a0"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
            const checkIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22863a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
            btn.addEventListener('click', () => {
                navigator.clipboard.writeText(code.textContent).then(() => {
                    btn.innerHTML = checkIcon;
                    btn.classList.add('copied');
                    btn.onanimationend = () => {
                        btn.innerHTML = copyIcon;
                        btn.classList.remove('copied');
                        btn.onanimationend = null;
                    };
                });
            });
            pre.style.position = 'relative';
            pre.appendChild(btn);
        });
    }

    /** Update token usage display.
     *
     * Also caches input + budget so the live streaming accumulator
     * (_recordStreamingChars) can refresh the bar with running output
     * estimates without waiting for the authoritative end-of-turn
     * usage event. The backend now emits an EARLY usage event with
     * input_tokens populated before tokens stream, so the cache is
     * primed by the time the first token arrives.
     */
    updateTokenUsage(usage) {
        if (!usage || !this._tokenCounter) return;
        this._lastUsageInput = usage.input_tokens || 0;
        this._lastUsageBudget = usage.context_budget || 131072;
        // A real usage event resets the streaming-output accumulator —
        // its output_tokens supersede whatever we estimated locally.
        this._streamingOutputChars = 0;
        this._renderUsageBar(usage.input_tokens, usage.output_tokens, this._lastUsageBudget);
    }

    /** Render the bar text from explicit numbers. */
    _renderUsageBar(inputTokens, outputTokens, budget) {
        if (!this._tokenCounter) return;
        const total = (inputTokens || 0) + (outputTokens || 0);
        const pct = Math.round((total / budget) * 100);
        const inputK = ((inputTokens || 0) / 1024).toFixed(1);
        const outputK = ((outputTokens || 0) / 1024).toFixed(1);
        this._tokenCounter.textContent = `${inputK}K in / ${outputK}K out (${pct}%)`;
        this._tokenCounter.title = `Input: ~${inputTokens} tokens, Output: ~${outputTokens} tokens, Budget: ${budget} tokens`;
        if (pct > 75) this._tokenCounter.style.color = '#d32f2f';
        else if (pct > 50) this._tokenCounter.style.color = '#e65100';
        else this._tokenCounter.style.color = '#666';
    }

    /** Accumulate streamed chars and refresh the bar at most once per
     * animation frame. Called from appendToken AND appendLiveThinkingToken
     * so reasoning + answer both contribute (matches what the backend's
     * end-of-turn usage event reports). */
    _recordStreamingChars(token) {
        if (!token || !this._tokenCounter) return;
        if (this._streamingOutputChars === undefined) this._streamingOutputChars = 0;
        this._streamingOutputChars += token.length;
        if (this._barUpdateScheduled) return;
        this._barUpdateScheduled = true;
        requestAnimationFrame(() => {
            this._barUpdateScheduled = false;
            const outTok = Math.floor((this._streamingOutputChars || 0) / 4);
            this._renderUsageBar(
                this._lastUsageInput || 0,
                outTok,
                this._lastUsageBudget || 131072,
            );
        });
    }

    onClear(callback) {
        this._onClearCallback = callback;
    }

    /** Remove transient error messages and orphaned streaming bubbles left by failed requests. */
    clearTransientErrors() {
        const msgs = this._messagesArea.querySelectorAll('.chat-message-assistant');
        for (const msg of msgs) {
            // Error-only bubbles (contain a .chat-error and nothing else meaningful)
            if (msg.querySelector('.chat-error') && !msg.querySelector('.chat-streaming-content, .chat-thinking')) {
                msg.remove();
                continue;
            }
            // Orphaned streaming bubbles: still have .chat-streaming-content (never finalized)
            // This happens when a request fails mid-stream
            if (msg.querySelector('.chat-streaming-content')) {
                msg.remove();
                if (msg === this._streamingMsg) {
                    this._streamingMsg = null;
                    this._streamingContent = null;
                    this._streamingRaw = '';
                }
                continue;
            }
            // Empty bubbles (streaming started but nothing emitted before error)
            if (!msg.textContent.trim() && !msg.querySelector('.chat-tool-bar')?.childElementCount) {
                msg.remove();
            }
        }
    }

    setLoading(loading) {
        this._typingIndicator.style.display = loading ? 'flex' : 'none';
        if (loading) {
            this._messagesArea.scrollTop = this._messagesArea.scrollHeight;
        }
    }

    onSend(callback) {
        this._onSendCallback = callback;
    }

    onSttToggle(callback) {
        this._onSttToggleCallback = callback;
    }

    onTtsToggle(callback) {
        this._onTtsToggleCallback = callback;
    }

    setTtsActive(active) {
        this._ttsActive = active;
        this._ttsBtn.classList.toggle('active', active);
        this._ttsBtn.innerHTML = active ? this._ttsIconOn : this._ttsIconOff;
    }
}
