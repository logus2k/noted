# Seamless AI ↔ Text Editor Integration  
Best Practices & Implementation Guide (Vanilla ES6 + OpenAI-compatible API – 2026)

## Context

- Vanilla ES6 JavaScript (no frameworks like React/Vue)
- On-premises LLM via **OpenAI-compatible API** (e.g. `/v1/chat/completions` endpoint)
- Two-panel layout: persistent text editor + AI chat panel
- Goal: seamless, low-friction consultation of the current document without manual copy-paste

## Core Principle: Context Engineering
Treat the editor content as **live, dynamic prompt context**.  
Automatically inject relevant portions of the document into **every** (or selected) chat request so the LLM “sees” what the user is writing in real time.

## Comparison of Main Approaches

| Approach                        | Complexity (Vanilla JS) | Token Efficiency | Allows AI → Editor Writes | Real-time Feel | Recommended For Your Case |
|-------------------------------|--------------------------|------------------|----------------------------|----------------|----------------------------|
| 1. Implicit Context (Auto-Sync) | ★☆☆ low                 | medium–high     | no (unless parsed)         | excellent      | Yes – strongest v1 choice  |
| 2. Selection-Aware              | ★★☆ medium              | high            | no                         | very good      | Yes – best UX upgrade      |
| 3. Bidirectional with CRDT/OT   | ★★★ high                | medium          | yes                        | magical        | Later (v2+)                |
| 4. Agentic / Tools (MCP style)  | ★★★ high                | very high       | yes (structured)           | good           | Optional – if model supports strong tool use |

**Recommendation order for vanilla ES6 project**  
Start with **1 + 2** → add parsing for apply rewrites → consider bidirectional later.

## 1. Implicit Context – Auto-Sync (Recommended Starting Point)

**Every chat message automatically includes current editor content.**

### Frontend – Vanilla ES6 Implementation

```js
// editor.js
const editor = document.getElementById('editor-textarea'); // or contenteditable div
let currentDoc = '';

// Optional: debounce heavy documents
function getRelevantContext() {
    return editor.value;                     // full document
    // or: return getSelectedTextOrSurrounding(); // smarter variant (see below)
}

// chat.js
const chatInput = document.getElementById('chat-input');
const messagesContainer = document.getElementById('messages');

async function sendMessage() {
    const userText = chatInput.value.trim();
    if (!userText) return;

    // Show user message
    appendMessage('user', userText);
    chatInput.value = '';

    const context = getRelevantContext();

    const payload = {
        model: 'your-on-prem-model',
        messages: [
            {
                role: 'system',
                content: `You are an expert writing assistant. The user is editing this document right now.\n` +
                         `Always refer to and improve based on this exact text:\n` +
                         `---\n${context}\n---\n` +
                         `Be concise unless asked otherwise. If suggesting edits, use clear markers.`
            },
            ...getConversationHistory(), // your array of {role, content}
            { role: 'user', content: userText }
        ],
        temperature: 0.7,
        max_tokens: 2000,
        stream: true   // strongly recommended for good UX
    };

    // Use fetch + ReadableStream for streaming
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    // Handle streaming response (append chunks to last AI message)
    handleStreamingResponse(response);
}
```

**Pro tip** — Add a visual indicator  
```js
document.getElementById('context-status').textContent = 
    context.length > 10000 ? 'Large document synced (~' + Math.round(context.length/1000) + 'k chars)' : 'Document synced';
```

## 2. Selection-Aware (Strongly Recommended UX Upgrade)

Only send selected text when something is highlighted → saves tokens and makes intent clearer.

### Quick Implementation

```js
function getRelevantContext() {
    const start = editor.selectionStart;
    const end   = editor.selectionEnd;

    if (start !== end) {
        // Selection mode
        const selected = editor.value.slice(start, end);
        document.getElementById('context-mode').textContent = 'Selected text';
        return selected;
    }

    // Fallback: whole document or paragraph around cursor
    document.getElementById('context-mode').textContent = 'Full document';
    return editor.value;
}
```

Bonus: one-click “Ask about selection”  
```js
editor.addEventListener('mouseup', () => {
    if (editor.selectionStart !== editor.selectionEnd) {
        document.getElementById('quick-ask-btn').style.display = 'inline-block';
    }
});
```

## 3. Bidirectional – Let AI Edit the Document

Parse LLM replies for rewrite blocks and offer “Apply” button.

Common patterns the LLM can be instructed to use:

    **Rewrite suggestion:**
    ```replace
    New paragraph text here...
    ```

    Or use special instruction:

    ```text
    When suggesting a replacement, output ONLY this format:
    <replace start="charIndex" end="charIndex">new text</replace>
    ```

Frontend parser example:

```js
function tryApplyRewrite(aiText) {
    const match = aiText.match(/<replace start="(\d+)" end="(\d+)">(.*?)<\/replace>/s);
    if (match) {
        const [_, start, end, replacement] = match;
        editor.value = 
            editor.value.slice(0, start) + 
            replacement + 
            editor.value.slice(end);
        // move cursor, flash highlight, etc.
    }
}
```

## 4. Agentic / Tools Approach (MCP-inspired)

MCP (Model Context Protocol – standardized in late 2024) allows the LLM to **call functions** like `get_document()`, `replace_text(start, end, newText)`.

**Feasibility in 2026 with on-prem OpenAI-compatible endpoint**  
- Works **only if** your local model & inference engine has good **tool/function calling** (many do: Llama-3.1+, Mistral-Nemo, Qwen-2.5, etc.)
- You implement a **tool executor** loop in your backend proxy
- Frontend stays almost the same → backend handles tool calls

**When to consider**  
- You already see poor context usage with plain injection  
- You want the LLM to decide **when** to read the document  
- You plan bidirectional editing soon

**Minimal MCP-like pattern (no full MCP server needed)**

```json
// in messages array – add once at beginning
{
  "role": "system",
  "content": "... You can use tools: get_current_document(), replace_text(start:int, end:int, text:string)"
}
```

Then backend must detect tool_calls in response and execute them.

## Quick Start Checklist (v1 in ~1–2 days)

1. Global access to editor value (simple `window.editor` or closure)
2. Auto-append context string in **system** prompt on every send
3. Add selection detection → send only selection when present
4. Enable **streaming** responses (`stream: true`)
5. Show “AI sees document” / “AI sees selection (X words)” indicator
6. (Nice-to-have) Parse ```replace:disable-run

This pattern delivers 80–90 % of the magic users expect from modern AI editors while remaining lightweight and fully controllable in vanilla ES6.
```