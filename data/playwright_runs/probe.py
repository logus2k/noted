import time
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(args=['--no-sandbox'])
    page = browser.new_context(viewport={'width': 1800, 'height': 1000}).new_page()
    T0 = time.time()
    page.goto('http://noted:8123/', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_function("""() => document.querySelectorAll('.chat-message-assistant').length >= 1 && (document.querySelectorAll('.chat-message-assistant')[0].textContent||'').length > 5""", timeout=60000)
    page.wait_for_timeout(5000)

    # Click the Assistant tab to make the chat panel visible
    page.evaluate("""() => {
        const tabs = document.querySelectorAll('.right-panel-tab');
        for (const t of tabs) {
            const lbl = t.querySelector('span:not(.right-panel-tab-close)');
            if (lbl && /assistant/i.test(lbl.textContent || '')) { lbl.click(); break; }
        }
    }""")
    page.wait_for_timeout(500)

    # Diagnostic: enumerate checkbox-bearing labels anywhere in DOM
    diag = page.evaluate("""() => {
        const all = document.querySelectorAll('.chat-think-checkbox');
        return {
            count: all.length,
            items: Array.from(all).map(c => ({
                label: (c.parentElement.textContent || '').trim(),
                checked: c.checked,
                visible: c.offsetParent !== null,
            })),
        };
    }""")
    print(f'checkboxes found: {diag["count"]}')
    for it in diag['items']:
        print(f'  {it}')

    # Toggle off Extended Thinking, Vector RAG, GraphRAG
    after = page.evaluate("""() => {
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
    print(f'\nafter toggling:')
    for x in after: print(f'  {x}')

    # Send Hello and watch
    print('\n--- sending "Hello" ---')
    t0 = time.time()
    page.evaluate("""() => {
        const ti = document.querySelector('.chat-input');
        ti.focus(); ti.value = 'Hello';
        ti.dispatchEvent(new Event('input', {bubbles: true}));
        ti.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true}));
    }""")
    deadline = time.time() + 20
    first = None; prev = 0; stable = None
    while time.time() < deadline:
        elapsed = (time.time() - t0) * 1000
        st = page.evaluate("""() => {
            const m = document.querySelectorAll('.chat-message-assistant');
            const last = m[m.length - 1];
            return {n: m.length, c: last ? (last.textContent||'').length : 0};
        }""")
        if first is None and st['c'] > 5: first = elapsed; print(f'  first content +{elapsed:.0f}ms')
        if first:
            if st['c'] != prev: prev = st['c']; stable = time.time()
            elif stable and time.time() - stable >= 3:
                print(f'  done +{elapsed:.0f}ms ({st["c"]} chars)')
                break
        time.sleep(0.3)

    msg = page.evaluate("""() => {
        const m = document.querySelectorAll('.chat-message-assistant');
        return m.length ? (m[m.length-1].textContent||'') : '';
    }""")
    print(f'\n--- last msg ({len(msg)} chars) ---\n{msg[:500]}')
    browser.close()
