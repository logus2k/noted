"""Two-phase probe: publish the tool first, then OPEN A FRESH PAGE and
ask naturally. Tests whether a user who comes back later (no recollection
of asking the assistant to build a tool) can ask 'what's the weather in
Lisbon?' and have the new skill kick in.

Run with:
  docker run --rm --network noted-network \
    -v /home/logus/env/assets/noted/data/playwright_runs:/probes \
    --entrypoint python noted-test /probes/fresh_conversation_natural_probe.py
"""

import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
NATURAL_QUESTION = "What's the weather in Lisbon?"
PUBLISH_TIMEOUT_S = 240
FOLLOWUP_TIMEOUT_S = 90

CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def http_json(method, path, body=None, timeout=10):
    url = f"{NOTED_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=== fresh-conversation natural probe ===")

    # Phase 1: publish the tool via from-request (no browser needed for this part).
    print("\n--- phase 1: publish tool via /api/workflows/from-request ---")
    publish_resp = http_json("POST", "/api/workflows/from-request", {
        "request": (
            "I found these two addresses that return Weather information. "
            "Can you figure out how to use them so that I get a new skill "
            "to report on the Weather? "
            "https://services.sapo.pt/WeatherJSON/GetCities and "
            "https://services.sapo.pt/WeatherJSON/GetWeatherForecast?cityCode=LPLG"
        ),
    }, timeout=60)
    wf_id = publish_resp["workflow_id"]
    print(f"  workflow {wf_id} ({publish_resp.get('workflow_type')})")
    deadline = time.time() + PUBLISH_TIMEOUT_S
    last_step = ""
    t0 = time.time()
    while time.time() < deadline:
        d = http_json("GET", f"/api/workflows/{wf_id}")["state"]
        if d["status"] in ("completed", "failed", "suspended", "aborted"):
            print(f"  status: {d['status']} (+{(time.time()-t0):.0f}s)")
            break
        running = next((s for s in d["steps"] if s["status"] == "running"), None)
        if running and running["name"] != last_step:
            last_step = running["name"]
            print(f"  +{(time.time()-t0):.0f}s {last_step}")
        time.sleep(3)
    if d["status"] != "completed":
        print(f"  ✗ workflow {d['status']}, aborting probe")
        try: http_json("POST", f"/api/workflows/{wf_id}/abort", {})
        except: pass
        sys.exit(2)

    published = (d.get("inputs") or {}).get("tool_name")
    print(f"  ✓ published: {published!r}")

    # Inspect published skill triggers
    skills = http_json("GET", "/api/llm/skills").get("skills") or []
    sk = next((s for s in skills if s.get("name") == published), None)
    if sk:
        print(f"  skill triggers: {sk.get('triggers') or []}")

    # Settle a moment for federation
    time.sleep(3)

    # Phase 2: fresh browser context, no chat history -> ask naturally
    print(f"\n--- phase 2: fresh page, ask {NATURAL_QUESTION!r} ---")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1800, "height": 1000})
        page = ctx.new_page()
        page.add_init_script(CRYPTO_POLYFILL)
        page.goto(NOTED_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_function(
            "() => document.querySelectorAll('.chat-message-assistant').length >= 1 "
            "&& (document.querySelectorAll('.chat-message-assistant')[0].textContent||'').length > 5",
            timeout=60000,
        )
        page.wait_for_timeout(3000)
        page.evaluate("""() => {
            const tabs = document.querySelectorAll('.right-panel-tab');
            for (const t of tabs) {
                const lbl = t.querySelector('span:not(.right-panel-tab-close)');
                if (lbl && /assistant/i.test(lbl.textContent || '')) { lbl.click(); break; }
            }
        }""")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            document.querySelectorAll('.chat-think-checkbox').forEach(c => {
                const lbl = (c.parentElement.textContent || '').trim().toLowerCase();
                if ((lbl.includes('thinking') || lbl === 'vector rag' || lbl === 'graphrag') && c.checked) c.click();
            });
        }""")

        # Confirm we're not carrying turn-1 history (only the assistant's
        # initial greeting should be in the thread).
        msg_count = page.evaluate("() => document.querySelectorAll('.chat-message-assistant').length")
        print(f"  initial chat messages: {msg_count} (expecting 1: the greeting)")

        before_count = msg_count
        t1 = time.time()
        page.evaluate("""(text) => {
            const ti = document.querySelector('.chat-input');
            ti.focus(); ti.value = text;
            ti.dispatchEvent(new Event('input', {bubbles: true}));
            ti.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true}));
        }""", NATURAL_QUESTION)
        deadline = time.time() + FOLLOWUP_TIMEOUT_S
        first = None; prev = 0; stable = None
        while time.time() < deadline:
            st = page.evaluate(
                "(b) => { const m = document.querySelectorAll('.chat-message-assistant'); "
                "if (m.length <= b) return {n: m.length, c: 0}; "
                "const last = m[m.length-1]; return {n: m.length, c: (last.textContent||'').length}; }",
                before_count,
            )
            if first is None and st["c"] > 5:
                first = time.time() - t1
                print(f"  first token at +{first:.0f}s")
            if first:
                if st["c"] != prev: prev = st["c"]; stable = time.time()
                elif stable and time.time() - stable >= 4:
                    print(f"  stabilised at +{(time.time()-t1):.0f}s ({st['c']} chars)")
                    break
            time.sleep(0.4)

        msg = page.evaluate(
            "() => { const m = document.querySelectorAll('.chat-message-assistant'); "
            "return (m[m.length-1].textContent||''); }"
        )
        print(f"\n  --- final assistant message ({len(msg)} chars) ---")
        print(msg[:2500])

        called_published = published in (msg or "")
        contains_real_data = any(
            k in msg for k in ("Céu", "céu", "Cloud", "Sun", "Lisboa", "16°", "17°", "18°", "19°", "20°", "limpo")
        )
        deflected = any(
            k in msg.lower() for k in ("don't have access", "cannot fetch", "i don't know", "i'd need", "not currently")
        )
        print(f"\n  references published tool name: {called_published}")
        print(f"  contains real-API data: {contains_real_data}")
        print(f"  deflected / refused: {deflected}")

    # Cleanup
    print(f"\n--- cleanup remove_tool {published!r} ---")
    try:
        cw = http_json("POST", "/api/workflows/run", {"type": "remove_tool", "inputs": {"tool_name": published}})
        cid = cw.get("workflow_id")
        for _ in range(30):
            cs = http_json("GET", f"/api/workflows/{cid}")["state"]["status"]
            if cs in ("completed", "failed", "suspended", "aborted"):
                print(f"  cleanup: {cs}")
                break
            time.sleep(2)
    except Exception as e:
        print(f"  cleanup error: {e}")

    if contains_real_data and not deflected:
        print("\nRESULT: PASS — natural ask in a fresh conversation found and used the new tool.")
        sys.exit(0)
    if deflected:
        print("\nRESULT: TOOL-NOT-FOUND — assistant refused; the new skill's triggers may not match the natural phrasing OR Lisbon-code lookup is missing.")
        sys.exit(4)
    print("\nRESULT: PARTIAL — see message above.")
    sys.exit(5)


if __name__ == "__main__":
    main()
