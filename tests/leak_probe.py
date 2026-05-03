"""Reconstitute UI-level chat calls via Playwright to reproduce the
'tool-call-as-JSON-text leak' bug.

Drives noted's chat UI in Chromium (inside the noted-test container),
sends a multi-turn knowledge-question script, and inspects each
assistant message's rendered text for the JSON-tool-call signature
that would normally appear instead of a real answer when the model
emits a fake tool call into the content channel.

Run from host:
    docker run --rm --network noted-network \
        -v ~/env/assets/noted/tests:/tests \
        --entrypoint python \
        services-noted-test:latest /tests/leak_probe.py
"""
import os
import re
import time

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "4"))
PER_TURN_TIMEOUT_S = int(os.environ.get("TURN_TIMEOUT", "240"))

_BASE = [
    "Explain me the difference between supervised and unsupervised learning",
    "What is agentic computing?",
    "List some design patterns for agents that can be helpful when designing agentic systems",
    "Tell me about Gradient Descent and SGD",
    "Now tell me about the ADAM optimizer",
    "compare those two",
]
# Repeat all questions AFTER turn 6 to verify the critical "compare those
# two" turn doesn't poison the rest of the conversation (cascade test).
SCRIPT = _BASE + _BASE

LEAK_RE = re.compile(r'\{\s*"name"\s*:\s*"[a-z_]+"\s*,\s*"args"\s*:', re.IGNORECASE)

# Some noted JS APIs need crypto.randomUUID; on the test container's
# plain HTTP origin this isn't a secure context, so polyfill at page-init.
CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def _wait_for_chat_ready(page):
    """Open the Assistant panel via the left icon-bar button, then wait
    for the chat input to be visible. The chat panel is hidden until
    this button is clicked (button[data-key="assistant"] in IconBar.js)."""
    # Wait for the left icon-bar to mount
    page.wait_for_selector('button[data-key="assistant"]', state="visible", timeout=60_000)
    page.click('button[data-key="assistant"]')
    page.wait_for_selector(".chat-input", state="visible", timeout=30_000)


def _send_one_turn(page, message: str, idx: int) -> dict:
    """Type a message, send via Enter, wait for the assistant to finish.

    Returns dict with rendered_html + plain_text + leak_match (or None).
    """
    print(f"  [turn {idx+1}] sending: {message!r}", flush=True)
    page.fill(".chat-input", message)
    page.press(".chat-input", "Enter")

    # Wait until we see another assistant message appear and lose its
    # streaming class. ChatPanel uses `.chat-streaming-content` while
    # tokens are arriving; absence == done. Fall back on timeout.
    deadline = time.time() + PER_TURN_TIMEOUT_S
    last_count = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
    # 1) wait for new assistant message
    while time.time() < deadline:
        cur = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
        if cur > last_count:
            break
        time.sleep(0.5)
    # 2) wait until the LAST assistant message is no longer streaming
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

    # Extract the rendered text of the last assistant message
    payload = page.evaluate(
        "(() => { const m = document.querySelectorAll('.chat-message-assistant');"
        " const last = m[m.length-1]; if (!last) return null;"
        " return { html: last.innerHTML, text: last.innerText }; })()"
    )
    text = (payload or {}).get("text", "") or ""
    leak = LEAK_RE.search(text)
    print(
        f"  [turn {idx+1}] elapsed={elapsed:.1f}s text_len={len(text)} leak={'YES' if leak else 'no'}",
        flush=True,
    )
    return {
        "user": message,
        "elapsed_s": round(elapsed, 1),
        "text": text,
        "html": (payload or {}).get("html", ""),
        "leak_match": leak.group(0) if leak else None,
    }


def run_one_session(playwright, idx: int) -> dict | None:
    print(f"\n=== Session {idx} ===", flush=True)
    browser = playwright.chromium.launch(headless=HEADLESS)
    context = browser.new_context(viewport={"width": 1400, "height": 900})
    context.add_init_script(CRYPTO_POLYFILL)
    page = context.new_page()
    page.on("console", lambda m: m.type == "error" and print(f"  [console-error] {m.text}", flush=True))
    try:
        page.goto(NOTED_URL, wait_until="networkidle", timeout=60_000)
        _wait_for_chat_ready(page)
        transcript = []
        for i, msg in enumerate(SCRIPT):
            try:
                r = _send_one_turn(page, msg, i)
            except Exception as e:
                print(f"  [turn {i+1}] ERROR: {type(e).__name__}: {e}", flush=True)
                break
            transcript.append(r)
            if r["leak_match"]:
                print(f"\n*** LEAK on turn {i+1} of session {idx} ***", flush=True)
                print(f"    matched: {r['leak_match']!r}", flush=True)
                print(f"    text (first 800):\n{r['text'][:800]}\n", flush=True)
                print(f"    text (last 800):\n{r['text'][-800:]}\n", flush=True)
                # Persist to disk for follow-up
                import json as _json
                out = "/tests/results/leak_capture.json"
                os.makedirs("/tests/results", exist_ok=True)
                with open(out, "w") as f:
                    _json.dump({
                        "session_idx": idx,
                        "leak_turn_index": i,
                        "leak_user_message": msg,
                        "leak_match": r["leak_match"],
                        "transcript": transcript,
                    }, f, indent=2)
                print(f"    dump: {out}", flush=True)
                return {"session_idx": idx, "leak_turn_index": i}
    finally:
        context.close()
        browser.close()
    return None


def main():
    with sync_playwright() as p:
        for s in range(1, MAX_SESSIONS + 1):
            hit = run_one_session(p, s)
            if hit:
                print(f"\nDone — leak captured in session {hit['session_idx']} turn {hit['leak_turn_index']+1}.", flush=True)
                return
    print(f"\n{MAX_SESSIONS} sessions completed without a leak.", flush=True)


if __name__ == "__main__":
    main()
