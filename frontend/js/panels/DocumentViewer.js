/**
 * DocumentViewer - Renders Markdown and PDF documents in the center pane.
 * Adapted from docbro's DocumentLoader + PdfRenderer for noted integration.
 */
export class DocumentViewer {
    constructor() {
        this._wrapper = document.createElement('div');
        this._wrapper.className = 'document-viewer-wrapper';

        this._content = document.createElement('div');
        this._content.className = 'document-viewer-content';
        this._wrapper.appendChild(this._content);

        this._currentDoc = null;
        this._pdfState = null; // { pdfDoc, pageDivs, observers, renderVersion }
        this._pdfModule = null; // lazy-loaded pdf.js module
    }

    get element() { return this._wrapper; }

    /**
     * Load and display a document.
     * @param {object} doc - { name, category, location }
     *   `location` is "<domain_id>/<rel_path>" (path-style; slashes preserved).
     *   The endpoint at /api/documents/files/{path:path} resolves to
     *   data/domains/<domain_id>/sources/<rel_path>.
     */
    async show(doc) {
        this._cleanup();
        this._currentDoc = doc;
        this._content.innerHTML = '';

        // Inline content (e.g. skill documents loaded from API JSON)
        if (doc.content) {
            this._content.className = 'document-viewer-content document-viewer-skill';
            const pre = document.createElement('pre');
            pre.style.cssText = 'white-space:pre-wrap;word-wrap:break-word;font-family:var(--font-mono);font-size:12px;line-height:1.6;padding:16px;margin:0;color:var(--text-primary,#333);background:none';
            pre.textContent = doc.content;
            this._content.appendChild(pre);
            return;
        }

        // encodeURIComponent on each segment so slashes in the location
        // survive into the URL path (FastAPI's path:path matcher would
        // otherwise see %2F and treat the whole thing as one segment).
        const locPath = (doc.location || '').replace(/^files\//, '');
        const url = 'api/documents/files/' + locPath.split('/').map(encodeURIComponent).join('/');
        const isPdf = locPath.toLowerCase().endsWith('.pdf');

        if (isPdf) {
            await this._renderPdf(url);
        } else {
            const slashIdx = locPath.lastIndexOf('/');
            const dir = slashIdx >= 0 ? locPath.substring(0, slashIdx + 1) : '';
            const imgResolver = rel => `api/documents/files/${dir}${rel}`;
            await this._renderMarkdown(url, imgResolver);
        }
    }

    clear() {
        this._cleanup();
        this._currentDoc = null;
        this._content.innerHTML = '';
    }

    // --- Citation deep-jump (PDF + Markdown) ---

    /** Scroll the PDF to `pageNo` (1-based) and outline the region at
     * `bbox` ([x0, y0, x1, y1] in PDF coords, bottom-left origin).
     * Replaces any prior highlight. No-op if the PDF isn't loaded or the
     * page index is out of range. Single-region wrapper around
     * showBboxHighlights; preserved for callers that haven't been
     * updated to pass a regions list. */
    async showBboxHighlight(pageNo, bbox) {
        return this.showBboxHighlights([{ page_no: pageNo, bbox }]);
    }

    /** Scroll to and outline EVERY region a chunk touches. Docling chunks
     * can span page breaks (HybridChunker merges peer doc_items across
     * pages); regions is a list of `{page_no, bbox}` so the highlight
     * paints on each affected page. Scrolls to the first region.
     * Replaces any prior highlight on every page. */
    async showBboxHighlights(regions) {
        if (!this._pdfState || !Array.isArray(regions) || regions.length === 0) return;

        // Drop any prior highlight from every page so a new citation
        // click never leaves stale rectangles behind on a previously
        // highlighted page.
        this._clearAllBboxHighlights();

        // Paint each region's page in order. The first region is the
        // chunk's anchor (earliest page seen at ingest time); scroll to
        // it after painting so the user lands on the start of the chunk.
        for (const r of regions) {
            await this._paintBboxOnPage(r.page_no, r.bbox);
        }

        const firstIdx = (regions[0].page_no || 1) - 1;
        const firstPage = this._pdfState.pageDivs[firstIdx];
        if (firstPage && this._wrapper) {
            const hostRect = this._wrapper.getBoundingClientRect();
            const targetRect = firstPage.getBoundingClientRect();
            this._wrapper.scrollTop += targetRect.top - hostRect.top;
        }
    }

    _clearAllBboxHighlights() {
        if (!this._pdfState) return;
        for (const pd of this._pdfState.pageDivs) {
            const old = pd.querySelector('.pdf-bbox-highlight-layer');
            if (old) {
                if (old._bboxResizeObserver) old._bboxResizeObserver.disconnect();
                old.remove();
            }
        }
    }

    async _paintBboxOnPage(pageNo, bbox) {
        if (!pageNo || pageNo < 1 || !Array.isArray(bbox) || bbox.length !== 4) return;
        const pageIndex = pageNo - 1;
        const pageDiv = this._pdfState.pageDivs[pageIndex];
        if (!pageDiv) return;

        // Force-render the page if it hasn't lazy-loaded. Wrapped in a
        // try/finally that resets _renderState on failure - otherwise a
        // worker-terminated render leaves the page stuck in 'rendering',
        // and subsequent citation clicks see "not idle" and skip the
        // re-render, then try to use a viewport that doesn't exist.
        if ((pageDiv._renderState === 'idle' || pageDiv._renderState === 'unloaded') && pageDiv._pdfPage) {
            pageDiv._renderState = 'rendering';
            try {
                await this._renderPdfPage(pageDiv, this._pdfState);
            } catch (err) {
                console.warn('[DocumentViewer] page render failed:', err);
                pageDiv._renderState = 'idle';
            }
        }
        const viewport = pageDiv._pdfViewport;
        if (!viewport) return;

        let left, top, width, height;
        try {
            const [vx1, vy1, vx2, vy2] = viewport.convertToViewportRectangle(bbox);
            left = Math.min(vx1, vx2);
            top = Math.min(vy1, vy2);
            width = Math.abs(vx2 - vx1);
            height = Math.abs(vy2 - vy1);
        } catch (err) {
            console.warn('[DocumentViewer] bbox conversion failed:', err);
            return;
        }

        const layer = document.createElement('div');
        layer.className = 'pdf-bbox-highlight-layer';
        layer.style.width = viewport.width + 'px';
        layer.style.height = viewport.height + 'px';
        // Match the canvas's transform-origin so scaling is anchored at the
        // top-left, the same point pdf.js anchors its own canvas to.
        layer.style.transformOrigin = '0 0';

        const rect = document.createElement('div');
        rect.className = 'pdf-bbox-highlight';
        rect.style.left = left + 'px';
        rect.style.top = top + 'px';
        rect.style.width = width + 'px';
        rect.style.height = height + 'px';
        layer.appendChild(rect);
        pageDiv.appendChild(layer);

        // Apply the initial scale, then keep it in sync with pageDiv's
        // rendered width via ResizeObserver. Without this, panel resizes
        // (or zoom changes) leave the highlight floating off the page.
        const _applyScale = () => {
            const dw = pageDiv.clientWidth;
            if (dw > 0) layer.style.transform = `scale(${dw / viewport.width})`;
        };
        _applyScale();
        if (typeof ResizeObserver !== 'undefined') {
            const ro = new ResizeObserver(_applyScale);
            ro.observe(pageDiv);
            // Stash on the layer so a subsequent highlight on the same
            // page disposes the prior observer when the layer is removed.
            layer._bboxResizeObserver = ro;
        }
    }

    /** Scroll a rendered Markdown document to a heading whose path matches
     * `sectionPath` (Docling joins headings with " > "). Matches the LAST
     * segment first (typically the leaf heading); falls back to a prefix
     * match. No-op if no heading matches. */
    scrollToHeading(sectionPath) {
        if (!sectionPath || this._pdfState) return;
        const headings = this._content.querySelectorAll('h1, h2, h3, h4, h5, h6');
        if (!headings.length) return;
        const segments = sectionPath.split(' > ').map(s => s.trim()).filter(Boolean);
        const leaf = segments[segments.length - 1];
        if (!leaf) return;
        let target = null;
        for (const h of headings) {
            if (h.textContent.trim() === leaf) { target = h; break; }
        }
        if (!target) {
            for (const h of headings) {
                if (h.textContent.trim().startsWith(leaf)) { target = h; break; }
            }
        }
        if (!target) return;
        // Scroll the wrapper directly (see showBboxHighlight comment) -
        // scrollIntoView can shift the page when the wrapper isn't
        // fully on-screen.
        const host = this._wrapper || target.parentElement;
        if (host) {
            const hostRect = host.getBoundingClientRect();
            const tRect = target.getBoundingClientRect();
            host.scrollTop += tRect.top - hostRect.top;
        } else {
            target.scrollIntoView({ behavior: 'instant', block: 'start' });
        }
    }

    // --- Markdown rendering ---

    async _renderMarkdown(url, imgResolver) {
        this._content.className = 'document-viewer-content document-viewer-markdown';

        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const markdown = await resp.text();
            const html = this._renderMarkdownToHtml(markdown, imgResolver);
            this._content.innerHTML = html;
            this._postProcessMarkdown();
        } catch (err) {
            this._content.innerHTML = `<div class="document-viewer-error">Failed to load document: ${err.message}</div>`;
        }
    }

    _renderMarkdownToHtml(markdown, imgResolver) {
        const mathExpressions = [];
        let mathIndex = 0;

        // Extract display math
        markdown = markdown.replace(/\$\$([\s\S]+?)\$\$/g, (match, math) => {
            const placeholder = `MATH_DISPLAY_${mathIndex}`;
            mathExpressions.push({ type: 'display', math: math.trim(), placeholder });
            mathIndex++;
            return placeholder;
        });

        // Extract inline math
        markdown = markdown.replace(/\$([^\$\n]+?)\$/g, (match, math) => {
            const placeholder = `MATH_INLINE_${mathIndex}`;
            mathExpressions.push({ type: 'inline', math: math.trim(), placeholder });
            mathIndex++;
            return placeholder;
        });

        // Custom image renderer: resolve relative paths via imgResolver.
        // Absolute URLs (https://, /, data:) pass through untouched.
        const renderer = new marked.Renderer();
        renderer.image = ({ href, title, text }) => {
            let src = href || '';
            if (imgResolver && src && !/^(https?:\/\/|\/|data:)/.test(src))
                src = imgResolver(src);
            const titleAttr = title ? ` title="${title}"` : '';
            return `<img src="${src}" alt="${text || ''}"${titleAttr} style="max-width:100%;height:auto">`;
        };

        // Parse markdown (marked is loaded as a UMD global)
        let html = marked.parse(markdown, { renderer });

        // Restore math with KaTeX (katex is loaded as a UMD global)
        for (const item of mathExpressions) {
            try {
                const rendered = katex.renderToString(item.math, {
                    displayMode: item.type === 'display',
                    throwOnError: false,
                });
                html = html.replace(item.placeholder, rendered);
            } catch {
                const fallback = item.type === 'display'
                    ? `$$${item.math}$$`
                    : `$${item.math}$`;
                html = html.replace(item.placeholder, fallback);
            }
        }

        return html;
    }

    _postProcessMarkdown() {
        // Syntax highlighting (hljs is loaded as a UMD global)
        if (typeof hljs !== 'undefined') {
            this._content.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }
        // Copy buttons on code blocks
        const copyIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#202020" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" fill="#a8d8a0"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
        const checkIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22863a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
        this._content.querySelectorAll('pre').forEach(pre => {
            const code = pre.querySelector('code');
            if (!code || !code.textContent.trim()) return;
            const btn = document.createElement('button');
            btn.className = 'doc-copy-btn';
            btn.innerHTML = copyIcon;
            btn.title = 'Copy to clipboard';
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const text = code.textContent;
                const onSuccess = () => {
                    btn.innerHTML = checkIcon + '<span style="font-size:10px;margin-left:4px;font-family:var(--font-sans);color:#22863a">Copied!</span>';
                    btn.classList.add('copied');
                    btn.onanimationend = () => {
                        btn.innerHTML = copyIcon;
                        btn.classList.remove('copied');
                        btn.onanimationend = null;
                    };
                };
                if (navigator.clipboard?.writeText) {
                    navigator.clipboard.writeText(text).then(onSuccess).catch(() => {
                        // Fallback for non-secure contexts
                        const ta = document.createElement('textarea');
                        ta.value = text;
                        ta.style.cssText = 'position:fixed;opacity:0';
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        ta.remove();
                        onSuccess();
                    });
                } else {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.cssText = 'position:fixed;opacity:0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    ta.remove();
                    onSuccess();
                }
            });
            pre.appendChild(btn);
        });
    }

    // --- PDF rendering ---

    async _renderPdf(url) {
        this._content.className = 'document-viewer-content document-viewer-pdf';

        try {
            if (!this._pdfModule) {
                this._pdfModule = await import('../../vendor/pdf.min.mjs');
                this._pdfModule.GlobalWorkerOptions.workerSrc = 'static/vendor/pdf.worker.min.mjs';
            }

            const pdfDoc = await this._pdfModule.getDocument({ url }).promise;
            const renderVersion = Date.now();

            const state = {
                pdfDoc,
                pageDivs: [],
                overlayEntries: [],
                intersectionObserver: null,
                unloadObserver: null,
                renderQueue: [],
                activeRenders: 0,
                renderVersion,
                resizeObserver: null,
            };
            this._pdfState = state;

            await this._setupPdfPlaceholders(state);
            this._startPdfLazyRendering(state);
        } catch (err) {
            this._content.innerHTML = `<div class="document-viewer-error">Failed to load PDF: ${err.message}</div>`;
        }
    }

    async _setupPdfPlaceholders(state) {
        const { pdfDoc, renderVersion } = state;
        const numPages = pdfDoc.numPages;

        for (let i = 0; i < numPages; i++) {
            const pageDiv = document.createElement('div');
            pageDiv.className = 'pdf-page';

            try {
                const page = await pdfDoc.getPage(i + 1);
                if (state.renderVersion !== renderVersion) return;

                // Placeholder viewport is only used for the page's aspect
                // ratio reservation and as a fallback when the actual
                // displayed width isn't known yet. The actual render uses
                // `page.clientWidth × DPR` for crisp pixel-aligned output;
                // see _renderPdfPage.
                const viewport = page.getViewport({ scale: 1 });
                pageDiv.style.aspectRatio = `${viewport.width} / ${viewport.height}`;
                pageDiv._pdfPage = page;
                pageDiv._pdfViewport = viewport;
            } catch {
                pageDiv.style.aspectRatio = '8.5 / 11';
            }

            pageDiv._renderState = 'idle';
            pageDiv._pageRenderVersion = 0;
            pageDiv._pageIndex = i;

            this._content.appendChild(pageDiv);
            state.pageDivs.push(pageDiv);
        }

        // Resize observer for annotation overlays
        state.resizeObserver = new ResizeObserver(() => {
            for (const entry of state.overlayEntries) {
                const pd = entry.div.parentElement;
                if (pd) {
                    const dw = pd.clientWidth;
                    if (dw > 0) {
                        entry.div.style.transform = `scale(${dw / entry.viewport.width})`;
                    }
                }
            }
        });
        state.resizeObserver.observe(this._content);
    }

    _startPdfLazyRendering(state) {
        const { renderVersion, pageDivs } = state;

        // Render observer: trigger when pages approach viewport
        state.intersectionObserver = new IntersectionObserver((entries) => {
            if (state.renderVersion !== renderVersion) return;
            for (const entry of entries) {
                const pageDiv = entry.target;
                if (entry.isIntersecting) {
                    if (pageDiv._renderState === 'idle' || pageDiv._renderState === 'unloaded') {
                        if (!state.renderQueue.includes(pageDiv)) {
                            state.renderQueue.push(pageDiv);
                        }
                    }
                }
            }
            this._processPdfRenderQueue(state);
        }, {
            root: this._wrapper,
            rootMargin: '200% 0px',
        });

        // Unload observer: reclaim memory for far-away pages
        state.unloadObserver = new IntersectionObserver((entries) => {
            if (state.renderVersion !== renderVersion) return;
            for (const entry of entries) {
                if (!entry.isIntersecting && entry.target._renderState === 'rendered') {
                    this._unloadPdfPage(entry.target, state);
                }
            }
        }, {
            root: this._wrapper,
            rootMargin: '500% 0px',
        });

        for (const pageDiv of pageDivs) {
            state.intersectionObserver.observe(pageDiv);
            state.unloadObserver.observe(pageDiv);
        }
    }

    _processPdfRenderQueue(state) {
        const maxConcurrent = 2;
        while (state.activeRenders < maxConcurrent && state.renderQueue.length > 0) {
            // Sort: pages closest to scroll center first
            const scrollCenter = this._wrapper.scrollTop + this._wrapper.clientHeight / 2;
            state.renderQueue.sort((a, b) => {
                const aDist = Math.abs(a.offsetTop + a.offsetHeight / 2 - scrollCenter);
                const bDist = Math.abs(b.offsetTop + b.offsetHeight / 2 - scrollCenter);
                return aDist - bDist;
            });

            const pageDiv = state.renderQueue.shift();
            if (pageDiv._renderState === 'rendered' || pageDiv._renderState === 'rendering') continue;
            if (!pageDiv._pdfPage) continue;

            state.activeRenders++;
            pageDiv._renderState = 'rendering';

            this._renderPdfPage(pageDiv, state).then(() => {
                state.activeRenders--;
                this._processPdfRenderQueue(state);
            });
        }
    }

    async _renderPdfPage(pageDiv, state) {
        const page = pageDiv._pdfPage;
        const placeholderViewport = pageDiv._pdfViewport;
        const pageRenderVersion = ++pageDiv._pageRenderVersion;
        const { renderVersion, pdfDoc } = state;

        if (!page || !placeholderViewport) {
            pageDiv._renderState = 'idle';
            return;
        }

        // Render at the EXACT display resolution × DPR so one canvas pixel
        // maps to one device pixel - no browser resampling, no softness.
        // The previous fixed scale=1.5 + OutputScale approach left the
        // canvas at 612*1.5*DPR while CSS displayed it at clientWidth*DPR;
        // the resulting non-1:1 ratio (typically ~1.02 to ~1.5) made the
        // browser bilinear-resample, which is the visible softness.
        const dpr = window.devicePixelRatio || 1;
        const nativeWidth = page.getViewport({ scale: 1 }).width;
        const displayedWidth = pageDiv.clientWidth || placeholderViewport.width;
        const renderScale = (displayedWidth / nativeWidth) * dpr;
        const viewport = page.getViewport({ scale: renderScale });

        const canvas = document.createElement('canvas');
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        const ctx = canvas.getContext('2d');

        try {
            await page.render({
                canvasContext: ctx,
                viewport,
            }).promise;
        } catch {
            pageDiv._renderState = pageDiv._renderState === 'rendering' ? 'idle' : pageDiv._renderState;
            return;
        }

        // Staleness checks
        if (state.renderVersion !== renderVersion) return;
        if (pageDiv._pageRenderVersion !== pageRenderVersion) return;
        if (pageDiv._renderState !== 'rendering') return;

        pageDiv.appendChild(canvas);
        pageDiv.style.aspectRatio = '';

        // Text layer
        try {
            const textContent = await page.getTextContent();
            if (state.renderVersion !== renderVersion || pageDiv._pageRenderVersion !== pageRenderVersion) return;

            const displayedWidth = pageDiv.clientWidth || viewport.width;
            const textScale = displayedWidth / page.getViewport({ scale: 1 }).width;
            const textViewport = page.getViewport({ scale: textScale });

            const textLayerDiv = document.createElement('div');
            textLayerDiv.className = 'textLayer';
            textLayerDiv.style.setProperty('--scale-factor', textScale);
            pageDiv.appendChild(textLayerDiv);

            const textLayer = new this._pdfModule.TextLayer({
                textContentSource: textContent,
                container: textLayerDiv,
                viewport: textViewport,
            });
            await textLayer.render();
        } catch {
            // Text layer is optional
        }

        // Annotation overlay (links)
        try {
            const annotations = await page.getAnnotations();
            if (state.renderVersion !== renderVersion || pageDiv._pageRenderVersion !== pageRenderVersion) return;

            const linkAnnotations = annotations.filter(a => a.subtype === 'Link' && (a.dest || a.url));
            if (linkAnnotations.length > 0) {
                const annotationDiv = document.createElement('div');
                annotationDiv.className = 'annotationLayer';
                annotationDiv.style.width = viewport.width + 'px';
                annotationDiv.style.height = viewport.height + 'px';
                pageDiv.appendChild(annotationDiv);

                for (const annot of linkAnnotations) {
                    const [x1, y1, x2, y2] = viewport.convertToViewportRectangle(annot.rect);
                    const left = Math.min(x1, x2);
                    const top = Math.min(y1, y2);
                    const width = Math.abs(x2 - x1);
                    const height = Math.abs(y2 - y1);

                    const link = document.createElement('a');
                    link.style.cssText = `position:absolute;left:${left}px;top:${top}px;width:${width}px;height:${height}px;`;

                    if (annot.url) {
                        link.href = annot.url;
                        link.target = '_blank';
                        link.rel = 'noopener noreferrer';
                    } else if (annot.dest) {
                        link.href = 'javascript:void(0)';
                        link.addEventListener('click', async (e) => {
                            e.preventDefault();
                            try {
                                let dest = annot.dest;
                                if (typeof dest === 'string') dest = await pdfDoc.getDestination(dest);
                                if (!Array.isArray(dest)) return;
                                const ref = dest[0];
                                const pageIndex = typeof ref === 'number' ? ref : await pdfDoc.getPageIndex(ref);
                                const targetDiv = state.pageDivs[pageIndex];
                                if (!targetDiv) return;
                                // Scroll ONLY the document-viewer-wrapper, not any ancestor.
                                // Using scrollIntoView() here walks every scrollable ancestor
                                // (including html/body in some Chromium builds even with
                                // overflow:hidden), which visually translates the whole #app
                                // upward. The scoped scrollTop arithmetic below cannot leak.
                                const host = this._wrapper;
                                if (host) {
                                    const hostRect = host.getBoundingClientRect();
                                    const targetRect = targetDiv.getBoundingClientRect();
                                    host.scrollTop += targetRect.top - hostRect.top;
                                }
                            } catch {}
                        });
                    }

                    annotationDiv.appendChild(link);
                }

                state.overlayEntries.push({ div: annotationDiv, viewport });
            }
        } catch {
            // Annotations are optional
        }

        pageDiv._renderState = 'rendered';
    }

    _unloadPdfPage(pageDiv, state) {
        if (pageDiv._renderState !== 'rendered') return;
        pageDiv._pageRenderVersion++;

        const canvas = pageDiv.querySelector('canvas');
        if (canvas) {
            canvas.width = 0;
            canvas.height = 0;
            canvas.remove();
        }

        const textLayer = pageDiv.querySelector('.textLayer');
        if (textLayer) textLayer.remove();

        const annotLayer = pageDiv.querySelector('.annotationLayer');
        if (annotLayer) {
            state.overlayEntries = state.overlayEntries.filter(e => e.div !== annotLayer);
            annotLayer.remove();
        }

        if (pageDiv._pdfViewport) {
            const vp = pageDiv._pdfViewport;
            pageDiv.style.aspectRatio = `${vp.width} / ${vp.height}`;
        }

        pageDiv._renderState = 'unloaded';
    }

    _cleanup() {
        if (!this._pdfState) return;
        const state = this._pdfState;

        state.renderVersion = -1; // invalidate any in-flight renders

        if (state.intersectionObserver) state.intersectionObserver.disconnect();
        if (state.unloadObserver) state.unloadObserver.disconnect();
        if (state.resizeObserver) state.resizeObserver.disconnect();

        for (const pageDiv of state.pageDivs) {
            const canvas = pageDiv.querySelector('canvas');
            if (canvas) {
                canvas.width = 0;
                canvas.height = 0;
            }
        }

        if (state.pdfDoc) {
            state.pdfDoc.destroy();
        }

        this._pdfState = null;
    }
}
