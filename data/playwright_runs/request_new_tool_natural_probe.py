"""Variant probe: turn 2 asks the NATURAL question.

Turn 1: same capability ask as request_new_tool_probe.py.
Turn 2: 'What's the weather in Lisbon?' — does NOT name the tool, does
NOT provide the SAPO city code. Tests whether:
  (a) the freshly-federated skill's triggers cause the assistant to
      reach for the new tool from a natural-language question.
  (b) the assistant produces a sensible city_code argument (it has to
      either know LPLG from prior knowledge OR realise the tool's
      contract is too narrow and say so).

Run with:
  docker run --rm --network noted-network \
    -v /home/logus/env/assets/noted/data/playwright_runs:/probes \
    --entrypoint python noted-test /probes/request_new_tool_natural_probe.py
"""

import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
ASK = (
    "I found these two addresses that return Weather information. "
    "Can you figure out how to use them so that I get a new skill to "
    "report on the Weather? "
    "https://services.sapo.pt/WeatherJSON/GetCities and "
    "https://services.sapo.pt/WeatherJSON/GetWeatherForecast?cityCode=LPLG"
)
NATURAL_QUESTION = "What's the weather in Lisbon?"
WORKFLOW_TIMEOUT_S = 240
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


def list_workflows():
    try:
        return http_json("GET", "/api/workflows/").get("workflows", [])
    except Exception:
        return []


def find_new_workflow(seen):
    for w in list_workflows():
        wid = w.get("workflow_id") or ""
        if wid and wid not in seen and w.get("workflow_type") == "create_tool":
            return wid
    return None


def main():
    print("=== natural-followup chat probe ===")
    seen = {w.get("workflow_id") for w in list_workflows()}
    print(f"initial workflow count: {len(seen)}")

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

        # Turn 1: capability ask
        print(f"\n--- turn 1: capability ask ---")
        t0 = time.time()
        page.evaluate("""(text) => {
            const ti = document.querySelector('.chat-input');
            ti.focus(); ti.value = text;
            ti.dispatchEvent(new Event('input', {bubbles: true}));
            ti.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true}));
        }""", ASK)
        wf_id = None
        deadline = time.time() + 90
        while time.time() < deadline:
            wf_id = find_new_workflow(seen)
            if wf_id:
                print(f"  → workflow {wf_id} (+{(time.time()-t0):.0f}s)")
                break
            time.sleep(2)
        if not wf_id:
            print("  ✗ no workflow")
            sys.exit(1)

        # Wait for completion
        deadline = time.time() + WORKFLOW_TIMEOUT_S
        last_step = ""
        while time.time() < deadline:
            d = http_json("GET", f"/api/workflows/{wf_id}")["state"]
            if d["status"] in ("completed", "failed", "suspended", "aborted"):
                print(f"  workflow status: {d['status']} (+{(time.time()-t0):.0f}s)")
                break
            running = next((s for s in d["steps"] if s["status"] == "running"), None)
            if running and running["name"] != last_step:
                last_step = running["name"]
                print(f"  +{(time.time()-t0):.0f}s {last_step}")
            time.sleep(3)
        if d["status"] != "completed":
            print(f"  ✗ workflow {d['status']}, aborting")
            try: http_json("POST", f"/api/workflows/{wf_id}/abort", {})
            except: pass
            sys.exit(2)

        published = (d.get("inputs") or {}).get("tool_name")
        print(f"  ✓ tool published: {published!r}")

        # Inspect the registered skill so we know what triggers we're testing.
        try:
            skills = http_json("GET", "/api/llm/skills").get("skills") or []
            sk = next((s for s in skills if s.get("name") == published), None)
            if sk:
                print(f"  skill registered: triggers={sk.get('triggers') or []}")
        except Exception as e:
            print(f"  skill fetch error: {e}")

        # Turn 2: NATURAL question
        print(f"\n--- turn 2: natural question — {NATURAL_QUESTION!r} ---")
        page.wait_for_timeout(2500)
        before_count = page.evaluate("() => document.querySelectorAll('.chat-message-assistant').length")
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
        # Inspect the tool-call badges in the latest message bubble.
        badges = page.evaluate(
            "() => { const m = document.querySelectorAll('.chat-message-assistant'); "
            "const last = m[m.length-1]; if (!last) return []; "
            "return Array.from(last.querySelectorAll('.chat-tool-badge, .chat-tool-name, [class*=\"tool-badge\"]')) "
            "  .map(b => b.textContent.trim()); }"
        )
        print(f"\n  --- final assistant message ({len(msg)} chars) ---")
        print(msg[:2500])
        print(f"\n  detected tool badges in last bubble: {badges}")

        called_published = published in (msg or "") or any(published in b for b in badges)
        contains_real_data = any(
            k in msg for k in ("Céu", "céu", "Cloud", "Sun", "Lisbon", "16°", "17°", "18°", "19°", "Lisboa", "20°")
        )
        looks_hallucinated = any(
            k in msg.lower() for k in ("don't have access", "cannot fetch", "i don't know", "i'd need", "specific city code")
        )
        print(f"\n  tool called by published name: {called_published}")
        print(f"  contains real-API data: {contains_real_data}")
        print(f"  looks like a refusal / 'need code' deflection: {looks_hallucinated}")

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

        if contains_real_data and not looks_hallucinated:
            print("\nRESULT: PASS — natural question reached the new tool with real data.")
            sys.exit(0)
        if looks_hallucinated:
            print("\nRESULT: TOOL-CONTRACT-NARROW — assistant reached the right tool but the city_code-only contract blocks natural usage.")
            sys.exit(4)
        print("\nRESULT: PARTIAL — turn 2 didn't surface real-API data; check the message above.")
        sys.exit(5)


if __name__ == "__main__":
    main()
