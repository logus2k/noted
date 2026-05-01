const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  page.on('console', msg => console.log(`[console.${msg.type()}]`, msg.text().slice(0, 200)));
  page.on('pageerror', err => console.log('[pageerror]', err.message));

  const t0 = Date.now();
  console.log('navigating to noted...');
  await page.goto('http://noted:8123/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  console.log('domcontentloaded at', Date.now() - t0, 'ms');

  // Wait for chat panel to be ready
  await page.waitForSelector('.chat-input-textarea', { timeout: 30000 });
  console.log('chat input present at', Date.now() - t0, 'ms');

  // Wait for welcome message: any assistant message in the messages area
  await page.waitForFunction(() => {
    return document.querySelectorAll('.chat-message-assistant').length >= 1;
  }, { timeout: 60000 });
  console.log('welcome rendered at', Date.now() - t0, 'ms');

  // Snapshot welcome state
  const welcomeChars = await page.$$eval('.chat-message-assistant', els =>
    (els[els.length - 1].textContent || '').length
  );
  console.log('welcome chars:', welcomeChars);

  // Send a question
  const tSend = Date.now();
  await page.fill('.chat-input-textarea', 'Explain me the difference between supervised and unsupervised learning');
  await page.keyboard.press('Enter');
  console.log('question sent at', Date.now() - t0, 'ms');

  // Watch for first thinking content arriving
  let firstThinkAt = null;
  let firstAnswerAt = null;
  const startWatch = Date.now();
  while (Date.now() - startWatch < 60000) {
    const state = await page.evaluate(() => {
      const msgs = document.querySelectorAll('.chat-message-assistant');
      const last = msgs[msgs.length - 1];
      if (!last) return { thinkLen: 0, answerLen: 0, msgIdx: -1 };
      const tb = last.querySelector('.chat-thinking-body');
      const ab = last.children[last.querySelector('.chat-thinking') ? 1 : 0];
      return {
        thinkLen: (tb && tb.textContent.length) || 0,
        answerLen: (ab && ab !== last.querySelector('.chat-thinking') && ab.textContent.length) || 0,
        msgIdx: msgs.length - 1,
      };
    });
    if (!firstThinkAt && state.thinkLen > 5) firstThinkAt = Date.now() - tSend;
    if (!firstAnswerAt && state.answerLen > 5) firstAnswerAt = Date.now() - tSend;
    if (state.thinkLen > 100 || state.answerLen > 100) {
      console.log(`  poll t=${Date.now() - tSend}ms  think=${state.thinkLen}  answer=${state.answerLen}`);
      if (state.answerLen > 200) break;
    }
    await page.waitForTimeout(500);
  }
  console.log('first-think after send:', firstThinkAt, 'ms');
  console.log('first-answer after send:', firstAnswerAt, 'ms');

  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
