# noted - Scrollbar and Scroll Containment Patterns

## Document Information

| Field         | Value                              |
|---------------|------------------------------------|
| Document      | UI Pattern Reference               |
| Project       | noted - Integrated MLOps Platform  |
| Version       | 1.0                                |
| Date          | 2026-04-04                         |
| Status        | Active                             |

---

## 1. Problem

The noted UI has a global scrollbar track rule in `base.css`:

```css
::-webkit-scrollbar-track {
    background: transparent;
    margin: 25px 0 90px;
}
```

This applies a large top/bottom margin to ALL scrollbar tracks on the page. Panels, floating windows, and other scrollable containers inherit this global rule, causing:

1. **Truncated scrollbar tracks** - the scrollbar doesn't reach the top or bottom of the panel
2. **Scroll-through** - mouse wheel events propagate from floating panels to the content underneath (e.g., notebook scrolls when scrolling a jsPanel)
3. **Missing right margin** - scrollbars sit flush against the panel border with no visual gap

---

## 2. Solution Architecture

### 2.1 Floating Panels (jsPanel)

All jsPanels use a two-layer approach defined globally in `base.css`:

**Layer 1: jsPanel-content (container)**
```css
.jsPanel-content {
    overscroll-behavior: contain;
    min-height: 0;
    overflow: hidden !important;  /* disable scrolling on the container */
}
```

**Layer 2: First child element (scrollable)**
```css
.jsPanel-content > :first-child {
    height: 100%;
    overflow-y: auto;
    overscroll-behavior: contain;
    margin-right: 5px;           /* gap between scrollbar and panel edge */
}
```

The scrollbar styling on the first child matches the platform pattern:
```css
.jsPanel-content > :first-child::-webkit-scrollbar {
    width: 8px;
}

.jsPanel-content > :first-child::-webkit-scrollbar-track {
    background: transparent;
    margin: 10px 0;              /* override global 25px/90px margins */
}

.jsPanel-content > :first-child::-webkit-scrollbar-thumb {
    background: transparent;     /* invisible until hover */
    border-radius: 4px;
}

.jsPanel-content > :first-child:hover::-webkit-scrollbar-thumb {
    background: #6096e5ad;       /* blue on hover */
}
```

**Wheel event isolation** is applied globally via a monkey-patch on `jsPanel.create` in `app.js`:

```js
const _origCreate = jsPanel.create.bind(jsPanel);
jsPanel.create = function(options) {
    const origCallback = options.callback;
    options.callback = function(panel) {
        panel.addEventListener('wheel', (e) => e.stopPropagation(), { passive: false });
        if (origCallback) origCallback(panel);
    };
    return _origCreate(options);
};
```

### 2.2 Sidebar Panels (Explorer, Git, TOC)

Sidebar panels use `margin-right: 5px` on the scrollable content element, same as jsPanels:

```css
.explorer-detail-content {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
    margin-right: 5px;
}
```

Each overrides the global scrollbar track margin:
```css
.explorer-detail-content::-webkit-scrollbar-track {
    margin: 10px 0;
}
```

### 2.3 Right Panel (Chat, Debug, Documentation)

Same pattern - the scrollable element gets `margin-right: 5px` and its own scrollbar track margin:

```css
.chat-messages {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
    margin-right: 5px;
}

.chat-messages::-webkit-scrollbar-track {
    margin: 4px 0;
}
```

---

## 3. Key Rules

1. **Every scrollable container** must override the global scrollbar track margin (`margin: 25px 0 90px`) with an appropriate value (typically `10px 0` or `4px 0`).

2. **Every scrollable container** should have `overscroll-behavior: contain` to prevent scroll chaining to parent elements.

3. **Floating panels (jsPanel)** get wheel event isolation automatically via the global monkey-patch. No per-panel code needed.

4. **The scrollbar gap** from the right edge is achieved with `margin-right: 5px` on the scrollable element, NOT on the scrollbar itself.

5. **jsPanel content** must have a single wrapper div as its first child. The CSS targets `.jsPanel-content > :first-child` for scroll behavior. When creating jsPanel content, always wrap in a single div:
   ```js
   content: `<div class="my-scroll">${html}</div>`
   ```

6. **Scrollbar thumb** is transparent by default and appears on hover (`#6096e5ad` blue). This is the platform-wide convention.

---

## 4. Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| No scrollbar track margin override | Scrollbar truncated at top/bottom | Add `::-webkit-scrollbar-track { margin: 10px 0; }` |
| Missing `overscroll-behavior: contain` | Parent content scrolls when panel content is at boundary | Add `overscroll-behavior: contain` |
| Using `height: 100%; overflow: auto` on jsPanel content div | Two competing scroll containers | Let CSS handle it via `.jsPanel-content > :first-child` |
| Putting multiple root elements in jsPanel content | Only first child gets scroll styling | Wrap in a single div |
| Adding per-panel `stopPropagation` on wheel | Redundant, already global | Remove; rely on the `app.js` monkey-patch |

---

## 5. Files

| File | Role |
|------|------|
| `frontend/css/base.css` | Global scrollbar rules, jsPanel scroll fixes |
| `frontend/js/app.js` | jsPanel.create monkey-patch for wheel isolation |
| `frontend/css/chat-panel.css` | Chat panel scrollbar (reference implementation) |
| `frontend/css/explorer-panel.css` | Explorer scrollbar |
| `frontend/css/git-panel.css` | Git panel scrollbar |
| `frontend/css/sidebar.css` | Sidebar scrollbar |
