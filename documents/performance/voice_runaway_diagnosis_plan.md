# Runaway-voice intermittent failure — diagnosis plan

**Symptom.** agent_server's `_VOICE_RUNAWAY_CAP=600` guard at `_LlamaServerProxy._stream_iter` (which injects synthetic `</voice>\n` when Gemma forgets to close its voice block) fires on some long-synthesis turns and silently skips others. When it skips, the user gets a silent turn — voice opener arrives but never closes, frontend parser stays in voice-buffer mode, `voiceText` never dispatches to TTS.

**Evidence from session 2026-05-04 ~13:30:**

| Turn (text_len) | Time | Runaway fired? |
|---|---|---|
| 2271 | 13:28:20 | No |
| 2919 | 13:28:37 | No |
| 2781 | 13:28:58 | No |
| 2502 | 13:30:10 | No |
| 1150 | 13:30:39 | No |
| (next turn) | 13:30:56 | **Yes** (`chars_after_open=604`) |
| 2866 | 13:32:08 | No |
| (next turn) | 13:32:18 | **Yes** (`chars_after_open=604`) |

Both fired events show **exactly** `chars_after_open=604` — deterministic boundary. Every "fail to fire" turn has body well past 600 chars after the voice opener.

## Hypothesis (best guess, not confirmed)

The runaway check requires `</think>` in the cumulative spliced buffer (it splits on `</think>` to extract the post-think portion before searching for `<voice>` opener). If the splice's THINKING→CONTENT state transition emits `</think>` in a non-standard chunk boundary OR reasoning is disabled for that turn, `post_think` could come back empty, `last_open` is `-1`, the check skips. Needs instrumentation to verify or refute.

## Plan: 4 phases

### Phase 1 — Add diagnostic logging (one-time agent_server change)

In `agent_server/app/llm_engine_server.py` `_LlamaServerProxy._stream_iter`, add per-yielded-content-chunk logging right before the runaway check:

```python
if not voice_runaway_truncated:
    full_so_far = "".join(spliced_content_buffer)
    has_close_think = "</think>" in full_so_far
    post_think = (
        full_so_far.split("</think>", 1)[-1]
        if has_close_think else ""
    )
    last_open = post_think.rfind("<voice>")
    body_after_open_len = (
        len(post_think) - last_open - len("<voice>")
        if last_open >= 0 else -1
    )
    has_close_voice = "</voice>" in post_think[last_open + len("<voice>"):] if last_open >= 0 else False
    # Sample at every 25th content-yielding chunk + always at the threshold
    if (len(spliced_content_buffer) % 25 == 0
            or (last_open >= 0 and body_after_open_len >= _VOICE_RUNAWAY_CAP - 50
                and not has_close_voice)):
        print(
            f"[VOICE_RUNAWAY_DIAG] full_len={len(full_so_far)} "
            f"has_</think>={has_close_think} "
            f"post_think_len={len(post_think)} "
            f"last_<voice>_at={last_open} "
            f"body_after_open={body_after_open_len} "
            f"has_</voice>_after_open={has_close_voice}",
            flush=True,
        )
    if last_open >= 0:
        body_after_open = post_think[last_open + len("<voice>"):]
        if "</voice>" not in body_after_open and len(body_after_open) >= _VOICE_RUNAWAY_CAP:
            voice_runaway_truncated = True
            ...
```

Then rebuild agent_server (`bash agent_server.sh && docker compose up -d --force-recreate agent_server`).

### Phase 2 — Playwright probe driving the real chat UI

The bug manifests in the user-visible audio path, which depends on the frontend's voice-text dispatch decision. To reproduce the EXACT failure mode, the test has to drive through the chat UI — not raw HTTP/curl.

Use the existing **noted-test container** (Playwright + Chromium + on noted-network, can reach `noted:8123`). Per `reference_playwright_for_browser_testing.md` memory.

Probe script (`data/probes/voice_runaway_probe.py`):

```python
import asyncio
import time
from playwright.async_api import async_playwright

PROMPTS = [
    # Long Portuguese synthesis — historically reproduces the failure
    "Explica-me em detalhe a regulamentação GDPR e os seus princípios fundamentais.",
    # Long Spanish synthesis
    "Explícame en detalle qué es la inteligencia artificial generativa y sus aplicaciones principales.",
    # Long English synthesis (control — should usually work)
    "Explain in detail what the Transformer architecture is and how attention mechanisms power it.",
    # Long French synthesis
    "Explique-moi en détail ce qu'est l'apprentissage automatique et ses applications.",
    # Long Italian synthesis
    "Spiegami in dettaglio cosa sono le reti neurali e come funzionano.",
]

async def run_probe(page, prompt: str, label: str):
    print(f"\n=== {label} ===\n  prompt: {prompt!r}", flush=True)
    # Locate chat input + send button (selectors from inspecting noted UI)
    await page.fill('textarea.chat-input', prompt)
    await page.click('button.chat-send-btn')
    # Wait for the assistant bubble to finish (typing indicator hides)
    await page.wait_for_function(
        "() => !document.querySelector('.chat-typing-indicator') || "
        "      document.querySelector('.chat-typing-indicator').style.display === 'none'",
        timeout=120000,
    )
    # Settle
    await asyncio.sleep(2.0)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on('console', lambda msg: print(f"  [browser-console:{msg.type}] {msg.text}", flush=True))
        await page.goto('http://noted:8123/')
        # Open chat panel if needed (selector depends on noted UI; adjust)
        await page.wait_for_selector('textarea.chat-input', timeout=30000)
        for i, prompt in enumerate(PROMPTS):
            await run_probe(page, prompt, f"probe_{i}")
        await browser.close()

asyncio.run(main())
```

Then run from inside noted-test container:

```bash
docker cp data/probes/voice_runaway_probe.py noted-test:/tmp/
docker exec noted-test python3 /tmp/voice_runaway_probe.py 2>&1 | tee /tmp/probe_out.log
```

### Phase 3 — Log collection

Capture across all four services with timestamps:

```bash
T0="<probe-start-time>"
docker logs --since "$T0" -t noted        > /tmp/diag_noted.log         2>&1
docker logs --since "$T0" -t agent_server > /tmp/diag_agent_server.log  2>&1
docker logs --since "$T0" -t llama-vision > /tmp/diag_llama_vision.log  2>&1
docker logs --since "$T0" -t tts_server   > /tmp/diag_tts.log           2>&1
```

### Phase 4 — Cross-reference

For each prompt's turn, line up:

| Source | Look for |
|---|---|
| noted | `CHAT_TURN_USER_MESSAGE` (turn start), `VOICE_MISSING` (turn end with no closer), `Follow-up text (first 300):` |
| agent_server | `[VOICE_RUNAWAY_DIAG] full_len=... has_</think>=... post_think_len=... last_<voice>_at=... body_after_open=...` (every 25th chunk + near threshold), `[VOICE_RUNAWAY_TRUNCATED]` (if fires), `[VOICE_INJECTION_*]` |
| llama-vision | image / vision activity (irrelevant for this test, but shows model engaged) |

For every `VOICE_MISSING has_open=True` event with `text_len > 800`, examine the corresponding agent_server `[VOICE_RUNAWAY_DIAG]` lines from that turn's stream. Specifically: at the moment `body_after_open` first exceeded 600, was `has_</think>` true? Was `last_<voice>_at >= 0`? If the diag shows `has_</think>=False` even though the body is clearly past the think section, the splice transition didn't emit `</think>` in this stream — that's the root cause.

## Expected outcomes and follow-up

| Diag finding | Root cause | Fix |
|---|---|---|
| `has_</think>=False` for the whole stream on failed turns | Splice didn't transition (model emitted no reasoning_content for this turn, or transitioned in a non-standard way) | Drop the `</think>` requirement from the runaway check; search for `<voice>` directly in `full_so_far` (with a special-case guard so `<voice>` inside reasoning doesn't trigger) |
| `last_<voice>_at = -1` even after body content past 600 | The `<voice>` opener never made it into `spliced_content_buffer` (e.g., it's emitted as a special token rather than content) | Check what's in the buffer at that point; possibly the opener arrived as a token type that splice routes differently |
| All values look correct, runaway condition met, yet log line for trigger missing | The check evaluates correctly but a yield/exception swallows the inject | Add try/except around the inject + log any exception |
| `body_after_open` plateaus below 600 across many chunks | Buffer not growing as expected — splice or chunk parsing issue upstream | Investigate splice's `feed()` output |

## Cleanup after diagnosis

Once the root cause is identified and fixed, REMOVE the per-25-chunks `[VOICE_RUNAWAY_DIAG]` log emission (keep the `[VOICE_RUNAWAY_TRUNCATED]` event log; that's already production-safe). The diag log is meant to be temporary instrumentation, not permanent traffic.

## Why Playwright (not curl)

Curl-against-API would skip the noted-frontend SSE consumer + ChatService streaming parser. The bug manifests in the user-visible audio path, which depends on the frontend's voice-text dispatch decision. To reproduce the EXACT failure mode, the test has to drive through the chat UI.
