# xterm.js Terminal Scrollbar Guidelines

## Document Information

| Field | Value |
|-------|-------|
| Last Updated | 2026-03-28 |
| Component | xterm.js terminals in Explorer detail pane and jsPanels |
| Purpose | Reference for fixing scrollbar issues when embedding xterm.js terminals |

---

## 1. The Problem

noted uses xterm.js for terminal views (package installation logs, DAG task logs, etc.). The base CSS in `base.css` sets global xterm rules that cause issues when terminals are embedded inside scrollable containers:

```css
/* base.css - global rules that cause problems */
.xterm-viewport {
    background: transparent !important;
    z-index: 1;
    pointer-events: auto;
}

.xterm .xterm-screen {
    pointer-events: none;    /* Blocks mouse interaction */
}
```

### Common symptoms:
- **Double vertical scrollbar** - one from xterm viewport, one from parent container
- **Unwanted horizontal scrollbar** - xterm renders at fixed cols wider than container
- **Mouse scroll not working** - `pointer-events: none` on `.xterm-screen` blocks events
- **Terminal not fitting container width** - missing `fitTerminal` / `ResizeObserver`

---

## 2. The Fix Pattern

### CSS (add per-terminal class)

Every xterm terminal needs a wrapper class (e.g., `.dag-log-term`, `.package-install-term`) with these overrides:

```css
.my-term {
    margin: 8px 0;
    border-radius: 4px;
}

.my-term .xterm {
    height: 100%;
    padding: 4px;
}

/* Re-enable mouse interaction (blocked by global base.css) */
.my-term .xterm .xterm-screen {
    pointer-events: auto;
}

.my-term .xterm-viewport {
    overflow-y: auto !important;
    overflow-x: hidden !important;
    pointer-events: auto;
    margin: 10px 5px 10px 0;   /* Top/bottom 10px, right 5px for scrollbar spacing */
}
```

### Preventing double scrollbar

If the terminal is inside a scrollable parent (e.g., explorer detail pane), the parent must stop scrolling the terminal area:

```javascript
// Set parent to flex layout, terminal fills remaining space
el.style.overflow = 'hidden';
el.style.display = 'flex';
el.style.flexDirection = 'column';

// Terminal container takes all remaining height
termContainer.style.cssText = 'flex:1;min-height:200px;border-radius:4px;overflow:hidden';
```

### Terminal creation

```javascript
const inlineTheme = getTerminalTheme();
termContainer.style.background = inlineTheme.background;

await Promise.all([
    document.fonts.load('12px "MesloLGS NF"'),
    document.fonts.load('bold 12px "MesloLGS NF"'),
]).catch(() => {});

const term = new Terminal({
    convertEol: true,
    cursorBlink: false,
    disableStdin: true,
    fontSize: 12,
    fontFamily: '"MesloLGS NF", "JetBrains Mono", "Fira Code", "Consolas", monospace',
    theme: { ...inlineTheme, cursor: 'transparent' },
    cols: 120, scrollback: 5000, allowProposedApi: true,
});

onTerminalThemeChange((t) => {
    term.options.theme = { ...t, cursor: 'transparent' };
    termContainer.style.background = t.background;
});

term.open(termContainer);
```

### Fit to container (REQUIRED)

Without this, the terminal renders at fixed 120 cols regardless of container width:

```javascript
const fitTerminal = () => {
    const dims = term._core._renderService.dimensions;
    if (!dims || !dims.css?.cell?.height || !dims.css?.cell?.width) return;
    const cols = Math.max(20, Math.floor(termContainer.clientWidth / dims.css.cell.width));
    const rows = Math.max(4, Math.floor(termContainer.clientHeight / dims.css.cell.height));
    if (rows !== term.rows || cols !== term.cols) term.resize(cols, rows);
};

const resizeObs = new ResizeObserver(() => fitTerminal());
resizeObs.observe(termContainer);
fitTerminal();
```

---

## 3. Context-specific notes

### Inside explorer detail pane

The detail pane (`explorer-detail-content`) has `overflow-y: auto`. When embedding a terminal:
1. Set `el.style.overflow = 'hidden'` to kill the parent scrollbar
2. Use `flex:1` on the terminal container to fill remaining space
3. Only xterm's own viewport scrollbar should be visible

### Inside jsPanel (floating panel)

jsPanels manage their own scroll. The terminal container should be `width:100%;height:100%` and the ResizeObserver should watch `panel.content`:

```javascript
const resizeObs = new ResizeObserver(() => fitTerminal());
resizeObs.observe(panel.content);
```

Also add wheel event stopper to prevent scroll propagation:
```javascript
panel.addEventListener('wheel', (e) => e.stopPropagation(), { passive: false });
```

---

## 4. Checklist for new terminal views

- [ ] Wrapper element has a unique CSS class (e.g., `.my-feature-term`)
- [ ] CSS overrides added: `.xterm-screen { pointer-events: auto }`, `.xterm-viewport { overflow-x: hidden }`
- [ ] Scrollbar margins set on `.xterm-viewport` (10px top/bottom, 5px right)
- [ ] Parent container overflow set to `hidden` if inside a scrollable pane
- [ ] `fitTerminal()` + `ResizeObserver` wired up
- [ ] Font preload before `term.open()`
- [ ] Theme change listener registered
- [ ] Test: resize container, check single vertical scrollbar, no horizontal scrollbar

---

## 5. Current implementations

| Feature | Wrapper class | Location |
|---------|---------------|----------|
| Package install logs | `.package-install-term` | `ExplorerEnvViews.js` + `venv-panel.css` |
| DAG task logs | `.dag-log-term` | `ExplorerPipelineViews.js` + `base.css` |
| Environment terminal | (jsPanel-based) | `ExplorerEnvViews.js` |
