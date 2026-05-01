"""Probe what the user actually sees in the chat panel.

Submits the question via the real chat UI, polls until the assistant
message stabilises, then dumps the rendered text + HTML structure.
"""
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright


NOTED_URL = os.environ.get("NOTED_URL", "http://noted:8123")
PROJECT = os.environ.get("NOTED_PROJECT", "noted-testing")
QUESTION = "what is this whole app about"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[c.{m.type[:3]}] {m.text[:200]}"))
        page.on("pageerror", lambda e: print(f"[PAGEERR] {e}"))

        target = f"{NOTED_URL}/?project={PROJECT}"
        print(f"Goto {target}")
        page.goto(target, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Open the chat panel via the icon-bar button with data-key="assistant"
        clicked = page.evaluate("""() => {
            const b = document.querySelector('[data-key="assistant"]');
            if (!b) return false;
            b.click();
            return true;
        }""")
        print(f"Click [data-key=assistant]: {clicked}")
        page.wait_for_timeout(1500)

        # Submit the question
        ta = page.query_selector(".chat-input")
        if not ta:
            print("FAIL: no .chat-input")
            page.screenshot(path="/tests/results/probe_no_textarea.png", full_page=True)
            return

        ta.click()
        ta.fill(QUESTION)
        page.wait_for_timeout(200)
        ta.press("Enter")
        print(f"Submitted: {QUESTION!r}")

        # Poll: dump full chat-messages structure each tick so we can see
        # what's actually rendering as it streams.
        last_len = -1
        stable_for = 0
        deadline = time.time() + 120
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            snap = page.evaluate("""() => {
                const root = document.querySelector('.chat-messages');
                if (!root) return {err: 'no .chat-messages'};
                const all = root.querySelectorAll(':scope > *');
                const items = [];
                all.forEach((el, i) => {
                    items.push({
                        i, tag: el.tagName.toLowerCase(),
                        cls: el.className,
                        text_len: (el.innerText || '').length,
                        text_tail: (el.innerText || '').slice(-100),
                    });
                });
                return {n: all.length, items, html_len: root.innerHTML.length};
            }""")
            if snap.get('err'):
                print(f"  poll: {snap['err']}")
            else:
                print(f"  poll: n={snap['n']} html_len={snap['html_len']}")
                for it in snap['items']:
                    print(f"    [{it['i']}] {it['tag']}.{it['cls'][:50]} len={it['text_len']} tail={it['text_tail'][-50:]!r}")

                # stability based on total html length of the messages root
                cur = snap['html_len']
                if cur == last_len and cur > 200:
                    stable_for += 1
                    if stable_for >= 3:
                        print("STABLE - done")
                        break
                else:
                    stable_for = 0
                last_len = cur

        # Final dump
        final = page.evaluate("""() => {
            const root = document.querySelector('.chat-messages');
            if (!root) return null;
            const items = [];
            root.querySelectorAll(':scope > *').forEach((el, i) => {
                items.push({
                    i, tag: el.tagName.toLowerCase(), cls: el.className,
                    text: el.innerText || '',
                    inner_html_first_500: el.innerHTML.slice(0, 500),
                });
            });
            return items;
        }""")

        with open("/tests/results/probe_chat_dump.json", "w") as f:
            json.dump(final, f, indent=2)
        print(f"\nWrote /tests/results/probe_chat_dump.json ({len(final or [])} message items)")

        if final:
            print("\n=== ASSISTANT-LIKE MESSAGES (last 3) ===")
            for it in final[-3:]:
                print(f"\n--- item {it['i']} | {it['tag']}.{it['cls']} | text len={len(it['text'])} ---")
                print(it['text'])

        page.screenshot(path="/tests/results/probe_final.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
