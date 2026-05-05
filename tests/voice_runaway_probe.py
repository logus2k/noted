"""Reproduce the runaway-voice intermittent failure (open <voice> tag
that never closes) by driving noted's chat UI with prompts known to
elicit long synthesis responses.

Run from host:
    docker run --rm --network noted-network \
        -v ~/env/assets/noted/tests:/tests \
        --entrypoint python \
        services-noted-test:latest /tests/voice_runaway_probe.py

The probe drives the real chat UI (Chromium inside noted-test). Each
turn:
  - sends a prompt
  - waits for the assistant streaming to complete
  - captures the rendered assistant text + length
  - flags turns where text_len > 1500 — the regime where runaway
    should fire if Gemma forgot the </voice> closer

The diagnostic side of this test lives in agent_server logs (the
[VOICE_RUNAWAY_DIAG] / [VOICE_RUNAWAY_TRUNCATED] / [VOICE_INJECTION_*]
events emitted by `_LlamaServerProxy._stream_iter`). After the probe
finishes, run on the host:

    docker logs --since "<probe-start>" -t agent_server | grep -E \
        "VOICE_RUNAWAY|VOICE_INJECTION"

and cross-reference with the per-turn `text_len` reported below.
"""
import os
import re
import time

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
PER_TURN_TIMEOUT_S = int(os.environ.get("TURN_TIMEOUT", "240"))

# Prompts deliberately chosen to elicit long synthesis answers.
# Mix of languages (PT/ES/FR/IT/EN) since the multilingual loop change
# may interact with the runaway path. Long, foundational, definitional
# topics → Gemma reaches for the retrieval tool, then writes a multi-
# section answer with examples — the regime where the runaway-voice
# bug surfaces.
SCRIPT = [
    # Portuguese — historically reproduced the failure
    "Explica-me em detalhe a regulamentação GDPR e os seus princípios fundamentais.",
    # Spanish
    "Explícame en detalle qué es la inteligencia artificial generativa y sus aplicaciones principales.",
    # English (control)
    "Explain in detail what the Transformer architecture is and how attention mechanisms power it.",
    # French
    "Explique-moi en détail ce qu'est l'apprentissage automatique et ses applications principales.",
    # Italian
    "Spiegami in dettaglio cosa sono le reti neurali e come funzionano.",
    # Portuguese, agent design (often elicits long structured answer)
    "Explica-me em detalhe como criar um agente de IA, incluindo padrões de design e melhores práticas.",
]

# Long-text threshold: turns whose final text exceeds this many chars
# are the ones where the runaway guard SHOULD have fired (or the
# response cleanly contained both <voice> and </voice>).
LONG_TEXT_THRESHOLD = 1500

# Crypto polyfill — noted-test container's plain HTTP origin isn't a
# secure context, so crypto.randomUUID needs a polyfill.
CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def _wait_for_chat_ready(page):
    """Open the Assistant panel via the left icon-bar button, then wait
    for the chat input to be visible."""
    page.wait_for_selector('button[data-key="assistant"]', state="visible", timeout=60_000)
    page.click('button[data-key="assistant"]')
    page.wait_for_selector(".chat-input", state="visible", timeout=30_000)


def _send_one_turn(page, message: str, idx: int) -> dict:
    """Type a message, send via Enter, wait for the assistant to finish.
    Returns dict with text, html, length, and detection flags."""
    print(f"\n  [turn {idx+1}] sending: {message!r}", flush=True)
    page.fill(".chat-input", message)
    page.press(".chat-input", "Enter")

    deadline = time.time() + PER_TURN_TIMEOUT_S
    last_count = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
    # 1) wait for new assistant message to appear
    while time.time() < deadline:
        cur = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
        if cur > last_count:
            break
        time.sleep(0.5)
    # 2) wait until streaming finishes
    while time.time() < deadline:
        streaming = page.evaluate(
            "(() => { const m = document.querySelectorAll('.chat-message-assistant');"
            " const last = m[m.length-1];"
            " return !!(last && last.querySelector('.chat-streaming-content')); })()"
        )
        if not streaming:
            break
        time.sleep(0.7)
    elapsed = PER_TURN_TIMEOUT_S - (deadline - time.time())

    payload = page.evaluate(
        "(() => { const m = document.querySelectorAll('.chat-message-assistant');"
        " const last = m[m.length-1]; if (!last) return null;"
        " return { html: last.innerHTML, text: last.innerText }; })()"
    )
    text = (payload or {}).get("text", "") or ""
    text_len = len(text)
    is_long = text_len > LONG_TEXT_THRESHOLD
    # Detect the runaway symptom from the user's perspective: the
    # rendered assistant message contains the body but no audible voice
    # got dispatched. We can't directly observe TTS playback from
    # Playwright, but if the runaway bug fires the rendered text often
    # ends mid-flow with no clean closure (the body got swallowed into
    # the unclosed voice block, then either renders as raw text or
    # appears empty). If text is non-empty we treat it as a "could be
    # affected" candidate and lean on agent_server logs for truth.
    print(
        f"  [turn {idx+1}] elapsed={elapsed:.1f}s text_len={text_len} "
        f"long_synthesis={is_long}",
        flush=True,
    )
    return {
        "user": message,
        "elapsed_s": round(elapsed, 1),
        "text_len": text_len,
        "is_long_synthesis": is_long,
        "text_first_200": text[:200],
        "text_last_200": text[-200:] if text_len > 200 else text,
    }


def run_session(playwright) -> list:
    print(f"=== voice_runaway_probe session START at {time.strftime('%H:%M:%S')} ===", flush=True)
    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    context.add_init_script(CRYPTO_POLYFILL)
    page = context.new_page()
    # Surface only console errors — TTS may emit a lot of info logs we
    # don't need, but errors are diagnostic.
    page.on("console", lambda m: m.type == "error" and print(f"  [console-error] {m.text}", flush=True))
    transcript = []
    try:
        page.goto(NOTED_URL, wait_until="networkidle", timeout=60_000)
        _wait_for_chat_ready(page)
        for i, msg in enumerate(SCRIPT):
            try:
                r = _send_one_turn(page, msg, i)
                transcript.append(r)
            except Exception as e:
                print(f"  [turn {i+1}] ERROR: {type(e).__name__}: {e}", flush=True)
                transcript.append({"user": msg, "error": f"{type(e).__name__}: {e}"})
                break
    finally:
        context.close()
        browser.close()

    # Report
    print(f"\n=== voice_runaway_probe session END at {time.strftime('%H:%M:%S')} ===", flush=True)
    longs = [r for r in transcript if r.get("is_long_synthesis")]
    print(f"\nLong-synthesis turns ({len(longs)}/{len(transcript)}):", flush=True)
    for r in longs:
        print(f"  - text_len={r['text_len']} elapsed={r['elapsed_s']}s "
              f"q={r['user'][:60]!r}", flush=True)
    return transcript


def main():
    import json
    with sync_playwright() as p:
        transcript = run_session(p)
    out = "/tests/results/voice_runaway_capture.json"
    os.makedirs("/tests/results", exist_ok=True)
    with open(out, "w") as f:
        json.dump({"transcript": transcript}, f, indent=2, ensure_ascii=False)
    print(f"\nDump: {out}", flush=True)
    print(f"\nNext step (run on host):", flush=True)
    print(f"  docker logs --since 5m -t agent_server | grep -E "
          f"'VOICE_RUNAWAY|VOICE_INJECTION'", flush=True)


if __name__ == "__main__":
    main()
