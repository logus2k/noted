"""Chat-driven autonomous capability extension probe.

Exercises the full chat -> request_new_tool -> create_tool workflow
end-to-end through the browser.

Steps:
  1. Open noted in headless Chromium.
  2. Toggle off Extended Thinking + Vector RAG + GraphRAG so the assistant
     doesn't pull retrieval tools and the response is focused.
  3. Send a natural-language ask describing the SAPO weather endpoints.
  4. Watch /api/workflows/ for a new create_tool workflow to appear (this
     is the LLM autonomously calling request_new_tool, which dispatches a
     workflow under the hood).
  5. Poll the workflow until terminal (completed / suspended / aborted).
  6. If completed: send a follow-up turn asking for Lisbon's weather and
     confirm the assistant calls the freshly-published tool.
  7. Clean up by removing the published tool + skill via remove_tool.

Run with:
  docker run --rm --network noted-network \
    -v /home/logus/env/assets/noted/data/playwright_runs:/probes \
    --entrypoint python noted-test /probes/request_new_tool_probe.py
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright

NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
ASK = (
    "I found these two addresses that return Weather information. "
    "Can you figure out how to use them so that I get a new skill to "
    "report on the Weather? "
    "https://services.sapo.pt/WeatherJSON/GetCities and "
    "https://services.sapo.pt/WeatherJSON/GetWeatherForecast?cityCode=LPLG"
)
WORKFLOW_TIMEOUT_S = 240
FOLLOWUP_TIMEOUT_S = 90

# The crypto.randomUUID polyfill matches what the e2e tests inject — needed
# when noted is reached over plain http on a non-localhost hostname.
CRYPTO_POLYFILL = """
    if (!crypto.randomUUID) {
        crypto.randomUUID = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,
            c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    }
"""


def http_json(method: str, path: str, body=None, timeout: int = 10):
    url = f"{NOTED_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_workflows() -> list[dict]:
    try:
        return http_json("GET", "/api/workflows/").get("workflows", [])
    except Exception as e:
        print(f"  list_workflows error: {type(e).__name__}: {e}")
        return []


def workflow_status(wf_id: str) -> dict:
    return http_json("GET", f"/api/workflows/{wf_id}")


def find_new_create_tool_workflow(seen_ids: set[str]) -> str | None:
    """Return the workflow_id of any newly-appeared create_tool workflow."""
    for w in list_workflows():
        wid = w.get("workflow_id") or ""
        if wid and wid not in seen_ids and w.get("workflow_type") == "create_tool":
            return wid
    return None


def main():
    print(f"=== chat-driven request_new_tool probe ===")
    print(f"target: {NOTED_URL}")
    print(f"ask: {ASK[:80]}...")

    # Snapshot initial workflow IDs so we know what's "new" once the LLM
    # autonomously calls request_new_tool.
    initial_workflows = {w.get("workflow_id") for w in list_workflows()}
    print(f"initial workflow count: {len(initial_workflows)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1800, "height": 1000})
        page = ctx.new_page()
        page.add_init_script(CRYPTO_POLYFILL)

        print("\n--- opening noted ---")
        t0 = time.time()
        page.goto(NOTED_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_function(
            "() => document.querySelectorAll('.chat-message-assistant').length >= 1 "
            "&& (document.querySelectorAll('.chat-message-assistant')[0].textContent||'').length > 5",
            timeout=60000,
        )
        page.wait_for_timeout(3000)
        print(f"  page loaded + initial greeting in {(time.time()-t0):.1f}s")

        # Make sure the Assistant tab is the active panel so chat-input is reachable.
        page.evaluate("""() => {
            const tabs = document.querySelectorAll('.right-panel-tab');
            for (const t of tabs) {
                const lbl = t.querySelector('span:not(.right-panel-tab-close)');
                if (lbl && /assistant/i.test(lbl.textContent || '')) { lbl.click(); break; }
            }
        }""")
        page.wait_for_timeout(500)

        # Toggle off Thinking + RAG so the LLM goes straight to tool dispatch.
        toggled = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.chat-think-checkbox').forEach(c => {
                const lbl = (c.parentElement.textContent || '').trim();
                const lo = lbl.toLowerCase();
                const target = lo.includes('thinking') || lo === 'vector rag' || lo === 'graphrag';
                if (target && c.checked) c.click();
                out.push({label: lbl, checked: c.checked});
            });
            return out;
        }""")
        print("  checkboxes after toggle:", toggled)

        # ── Turn 1: ask the assistant to build the tool ──────────────
        print(f"\n--- turn 1: sending capability ask ---")
        send_t0 = time.time()
        page.evaluate("""(text) => {
            const ti = document.querySelector('.chat-input');
            if (!ti) throw new Error('.chat-input not found');
            ti.focus();
            ti.value = text;
            ti.dispatchEvent(new Event('input', {bubbles: true}));
            ti.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true}));
        }""", ASK)

        # ── Watch for a new create_tool workflow to appear ──────────
        print(f"  watching /api/workflows/ for a new create_tool workflow...")
        wf_id = None
        deadline = time.time() + 90
        while time.time() < deadline:
            wf_id = find_new_create_tool_workflow(initial_workflows)
            if wf_id:
                print(f"  → new workflow detected: {wf_id} (+{(time.time()-send_t0):.1f}s)")
                break
            time.sleep(2)
        if wf_id is None:
            print(f"  ✗ FAIL: no new create_tool workflow appeared within 90s")
            print(f"    last assistant message:")
            last = page.evaluate(
                "() => { const m = document.querySelectorAll('.chat-message-assistant'); "
                "return m[m.length-1] ? (m[m.length-1].textContent||'').slice(0, 1200) : ''; }"
            )
            print(f"    {last}")
            sys.exit(1)

        # ── Poll workflow until terminal ────────────────────────────
        print(f"\n--- polling workflow {wf_id} until terminal (≤{WORKFLOW_TIMEOUT_S}s) ---")
        deadline = time.time() + WORKFLOW_TIMEOUT_S
        last_step = ""
        final_state = None
        while time.time() < deadline:
            try:
                detail = workflow_status(wf_id)
            except Exception as e:
                print(f"  poll error: {type(e).__name__}: {e}")
                time.sleep(3)
                continue
            s = detail["state"]
            steps = s.get("steps") or []
            current = next((st for st in steps if st.get("status") == "running"), None)
            current_name = current["name"] if current else (
                steps[-1]["name"] if steps else "?"
            )
            if current_name != last_step:
                print(f"  +{(time.time()-send_t0):4.0f}s  status={s['status']} step={current_name}")
                last_step = current_name
            if s["status"] in ("completed", "failed", "suspended", "aborted"):
                final_state = s
                break
            time.sleep(3)

        if final_state is None:
            print(f"  ✗ FAIL: workflow did not terminate within {WORKFLOW_TIMEOUT_S}s")
            sys.exit(2)

        print(f"\n  final status: {final_state['status']}")
        for st in final_state.get("steps") or []:
            print(f"    [{st['index']}] {st['name']}: {st['status']} (retries={st.get('retries', 0)})")

        if final_state["status"] != "completed":
            print(f"\n  ✗ FAIL: workflow ended in {final_state['status']!r}")
            # Surface the failed step's error for diagnosis
            failed = next((st for st in final_state.get("steps") or [] if st.get("status") == "failed"), None)
            if failed:
                err = (failed.get("error") or "")[-1500:]
                print(f"    error tail of {failed['name']}: {err}")
            sys.exit(3)

        published_tool = (final_state.get("inputs") or {}).get("tool_name")
        print(f"\n  ✓ workflow completed, tool published: {published_tool!r}")

        # ── Turn 2: ask the assistant to use the new tool ──────────
        print(f"\n--- turn 2: asking the assistant to use the new tool ---")
        page.wait_for_timeout(2000)  # let federation settle
        followup_text = (
            f"Use the new {published_tool} tool to fetch the weather for "
            f"Lisbon (city code LPLG) and tell me what the current "
            f"conditions are."
        )
        before_count = page.evaluate(
            "() => document.querySelectorAll('.chat-message-assistant').length"
        )
        send_t1 = time.time()
        page.evaluate("""(text) => {
            const ti = document.querySelector('.chat-input');
            ti.focus();
            ti.value = text;
            ti.dispatchEvent(new Event('input', {bubbles: true}));
            ti.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true}));
        }""", followup_text)

        # Wait for a new assistant message to appear and stabilise.
        deadline = time.time() + FOLLOWUP_TIMEOUT_S
        first = None; prev = 0; stable_since = None
        last_text = ""
        while time.time() < deadline:
            elapsed = time.time() - send_t1
            st = page.evaluate(
                "(before) => { const m = document.querySelectorAll('.chat-message-assistant'); "
                "if (m.length <= before) return {n: m.length, c: 0}; "
                "const last = m[m.length-1]; "
                "return {n: m.length, c: (last.textContent||'').length}; }",
                before_count,
            )
            if first is None and st["c"] > 5:
                first = elapsed
                print(f"  first response token at +{elapsed:.0f}s")
            if first:
                if st["c"] != prev:
                    prev = st["c"]
                    stable_since = time.time()
                elif stable_since and time.time() - stable_since >= 4:
                    print(f"  response stabilised at +{elapsed:.0f}s ({st['c']} chars)")
                    break
            time.sleep(0.4)

        last_text = page.evaluate(
            "() => { const m = document.querySelectorAll('.chat-message-assistant'); "
            "return (m[m.length-1].textContent||''); }"
        )
        print(f"\n  --- final assistant message ---\n{last_text[:2000]}")

        # ── Heuristic checks on the followup response ──────────────
        ok_temp = any(k in last_text.lower() for k in ("temperature", "°c", "lisbon", "céu", "céu", "ceu", "clear", "sunny", "cloud"))
        called_tool = published_tool and (published_tool in last_text or "weather" in last_text.lower())
        print(f"\n  contains weather-ish content: {ok_temp}")
        print(f"  references the new tool / topic: {called_tool}")

        # ── Cleanup: remove the tool ────────────────────────────────
        print(f"\n--- cleanup: remove_tool {published_tool!r} ---")
        try:
            r = http_json("POST", "/api/workflows/run", {
                "type": "remove_tool",
                "inputs": {"tool_name": published_tool},
            })
            cleanup_id = r.get("workflow_id")
            print(f"  remove_tool dispatched: {cleanup_id}")
            cdl = time.time() + 60
            while time.time() < cdl:
                cs = workflow_status(cleanup_id)["state"]["status"]
                if cs in ("completed", "failed", "suspended", "aborted"):
                    print(f"  cleanup done: {cs}")
                    break
                time.sleep(2)
        except Exception as e:
            print(f"  cleanup error: {type(e).__name__}: {e}")

        print("\n=== probe done ===")
        if ok_temp:
            print("RESULT: PASS — turn 2 produced weather-shaped output via the autonomous loop.")
            sys.exit(0)
        print("RESULT: PARTIAL — workflow ran but turn-2 response did not look weather-shaped.")
        sys.exit(4)


if __name__ == "__main__":
    main()
