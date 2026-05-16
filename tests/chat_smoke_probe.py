"""Minimal Playwright probe: open noted's Assistant panel, send 'Hello!',
verify a real answer renders. Fail loudly if the assistant message is
empty or never streams.

Driven the same way as voice_runaway_probe.py. Run from host:

    docker run --rm --network noted-network \
        -v ~/env/assets/noted/tests:/tests \
        --entrypoint python \
        services-noted-test:latest /tests/chat_smoke_probe.py

Reports concrete numbers:
  - elapsed seconds from prompt to "streaming finished"
  - rendered text length
  - first 300 chars of the assistant's reply
  - PASS / FAIL with reason
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
TURN_TIMEOUT_S = int(os.environ.get("TURN_TIMEOUT", "120"))
PROMPT = os.environ.get("PROMPT", "Hello!")

# Plain HTTP origin in the container isn't a secure context, so
# crypto.randomUUID needs a polyfill (per existing probes).
CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        ctx.add_init_script(CRYPTO_POLYFILL)
        page = ctx.new_page()

        errors = []
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}")
                                     if m.type in ("error", "warning") else None)

        try:
            print(f"[probe] loading {NOTED_URL} ...", flush=True)
            # `networkidle` never settles because noted holds persistent SSE
            # streams (doc events, workflow events). Use `domcontentloaded`
            # and let the subsequent selector waits gate on real readiness.
            page.goto(NOTED_URL, wait_until="domcontentloaded", timeout=60_000)

            print("[probe] opening Assistant panel ...", flush=True)
            page.wait_for_selector('button[data-key="assistant"]', state="visible", timeout=60_000)
            page.click('button[data-key="assistant"]')
            page.wait_for_selector(".chat-input", state="visible", timeout=30_000)

            print(f"[probe] sending: {PROMPT!r}", flush=True)
            t0 = time.time()
            before = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
            page.fill(".chat-input", PROMPT)
            page.press(".chat-input", "Enter")

            # 1) Wait for assistant message element to appear
            deadline = t0 + TURN_TIMEOUT_S
            appeared_at = None
            while time.time() < deadline:
                cur = page.evaluate("document.querySelectorAll('.chat-message-assistant').length")
                if cur > before:
                    appeared_at = time.time() - t0
                    print(f"[probe] assistant message appeared at t+{appeared_at:.1f}s", flush=True)
                    break
                time.sleep(0.3)
            else:
                print("[probe] FAIL: assistant message never appeared in DOM", flush=True)
                return 2

            # 2) Wait for streaming to finish (chat-streaming-content gone)
            while time.time() < deadline:
                streaming = page.evaluate(
                    "(() => { const m = document.querySelectorAll('.chat-message-assistant');"
                    " const last = m[m.length-1];"
                    " return !!(last && last.querySelector('.chat-streaming-content')); })()"
                )
                if not streaming:
                    break
                time.sleep(0.5)
            done_at = time.time() - t0

            # 3) Grab the rendered text
            payload = page.evaluate(
                "(() => { const m = document.querySelectorAll('.chat-message-assistant');"
                " const last = m[m.length-1]; if (!last) return null;"
                " return { text: last.innerText, html: last.innerHTML }; })()"
            ) or {}
            text = (payload.get("text") or "").strip()
            text_len = len(text)

            print(f"[probe] streaming finished at t+{done_at:.1f}s", flush=True)
            print(f"[probe] rendered text length: {text_len} chars", flush=True)
            print(f"[probe] rendered text (first 300 chars):", flush=True)
            print(f"        {text[:300]!r}", flush=True)

            if errors:
                print(f"[probe] console errors/warnings captured: {len(errors)}", flush=True)
                for e in errors[-5:]:
                    print(f"        {e[:200]}", flush=True)

            # Pass/fail
            if text_len < 3:
                print("[probe] FAIL: assistant answer is empty / near-empty", flush=True)
                return 3
            if done_at >= TURN_TIMEOUT_S - 1:
                print("[probe] FAIL: timed out before streaming completed", flush=True)
                return 4

            print(f"[probe] PASS — answer rendered in {done_at:.1f}s, {text_len} chars", flush=True)
            return 0
        finally:
            ctx.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
