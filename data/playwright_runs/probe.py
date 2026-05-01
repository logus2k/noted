import time
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(args=['--no-sandbox'])
    ctx = browser.new_context(viewport={'width': 1800, 'height': 1000})
    page = ctx.new_page()
    page.on('console', lambda m: print(f'[console.{m.type}] {m.text[:240]}', flush=True))
    page.on('pageerror', lambda e: print(f'[pageerror] {e.message}', flush=True))
    page.on('request', lambda r: print(f'[net REQ] {r.method} {r.url}', flush=True) if '/api/' in r.url else None)
    page.on('response', lambda r: print(f'[net RESP {r.status}] {r.url}', flush=True) if '/api/llm/chat' in r.url else None)

    t0 = time.time()
    page.goto('http://noted:8123/', wait_until='domcontentloaded', timeout=30000)
    print(f'domcontentloaded {(time.time()-t0)*1000:.0f}ms', flush=True)
    page.wait_for_function("""() => document.querySelectorAll('.chat-message-assistant').length >= 1""", timeout=60000)
    print(f'welcome rendered at {(time.time()-t0)*1000:.0f}ms', flush=True)

    # Force the chat panel visible: click the assistant tab (just the label,
    # not the close button), and force-show its element if needed.
    page.evaluate("""() => {
        // Click the right-panel tab labeled 'Assistant' (excluding the close X)
        const tabs = document.querySelectorAll('.right-panel-tab');
        for (const t of tabs) {
            const label = t.querySelector('span:not(.right-panel-tab-close)');
            if (label && (label.textContent || '').includes('Assistant')) {
                t.click();
                break;
            }
        }
        // Also force-display the chat-panel and the right-panel-content if hidden
        const cp = document.querySelector('.chat-panel');
        if (cp) cp.style.display = '';
        const rpc = document.querySelector('.right-panel-content');
        if (rpc) rpc.style.display = '';
        const rp = document.querySelector('.right-panel');
        if (rp) rp.style.display = '';
    }""")
    page.wait_for_timeout(300)
    visible = page.evaluate("""() => {
        const ti = document.querySelector('.chat-input');
        if (!ti) return {present: false};
        return {
            present: true,
            display: getComputedStyle(ti).display,
            offsetParent: !!ti.offsetParent,
            rect: ti.getBoundingClientRect().toJSON(),
        };
    }""")
    print(f'chat input state: {visible}', flush=True)

    # If still not visible, use evaluate to programmatically dispatch the same
    # send flow ChatPanel runs on Enter
    if not visible.get('offsetParent'):
        print('chat input still hidden — dispatching keydown on the textarea anyway', flush=True)
        # Make sure RAG flags are on (they default to true per ChatPanel)
        # Then set input value and dispatch Enter directly.
        t_send = time.time()
        page.evaluate("""(question) => {
            const ti = document.querySelector('.chat-input');
            ti.value = question;
            // Dispatch the same keydown the ChatPanel listener handles
            const ev = new KeyboardEvent('keydown', {key: 'Enter', shiftKey: false, bubbles: true, cancelable: true});
            ti.dispatchEvent(ev);
        }""", 'Explain me the difference between supervised and unsupervised learning')
    else:
        t_send = time.time()
        page.fill('.chat-input', 'Explain me the difference between supervised and unsupervised learning')
        page.press('.chat-input', 'Enter')
    print(f'-- Enter dispatched at {(time.time()-t0)*1000:.0f}ms (t_send=0) --', flush=True)

    # Watch for content + watch the loading indicator
    first_think = None
    first_answer = None
    deadline = time.time() + 60
    last_print = 0
    while time.time() < deadline:
        st = page.evaluate("""() => {
            const msgs = document.querySelectorAll('.chat-message-assistant');
            const last = msgs[msgs.length - 1];
            const indicator = document.querySelector('.chat-typing-indicator, .chat-loading, .typing-indicator, [class*="loading"], [class*="typing"]');
            const indState = indicator ? {cls: indicator.className, vis: indicator.offsetParent !== null} : null;
            if (!last) return {think:0, answer:0, msgs: msgs.length, ind: indState};
            const tb = last.querySelector('.chat-thinking-body');
            const thinkLen = (tb && tb.textContent.length) || 0;
            const all = (last.textContent || '').length;
            return {think: thinkLen, answer: Math.max(0, all - thinkLen - 30), msgs: msgs.length, ind: indState};
        }""")
        elapsed = (time.time() - t_send) * 1000
        if first_think is None and st['think'] > 5:
            first_think = elapsed
            print(f'  >>> first thinking at {first_think:.0f}ms <<<', flush=True)
        if first_answer is None and st['answer'] > 30:
            first_answer = elapsed
            print(f'  >>> first answer at {first_answer:.0f}ms <<<', flush=True)
        now = time.time()
        if now - last_print >= 2:
            print(f'  t+{elapsed:.0f}ms  msgs={st["msgs"]}  think={st["think"]}  answer={st["answer"]}  ind={st["ind"]}', flush=True)
            last_print = now
        if st['answer'] > 400:
            break
        time.sleep(0.3)
    print(f'\nfinal: first_think={first_think}ms  first_answer={first_answer}ms', flush=True)
    browser.close()
