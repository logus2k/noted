# Ingestion quality notes

Working notes on improvements that affect what content lands in the
graph + RAG store, distinct from chat-latency tuning. Captured 2026-05-02.

## TOC / document-index filtering

### Problem

PDFs (especially books and academic papers) include tables of contents
and indexes. When ingested, these chunks polluted the system in three
ways:

1. **Retrieval noise** — TOC chunks contain section names like
   `"5.2 Gradient Descent ... 47"`. The reranker can score these high
   on keyword overlap, and the citation badge then deep-jumps the user
   to a page of headings instead of the actual content.
2. **Graph noise** — `pdf_scanner` extracts entities from chunks. TOC
   chunks generate one low-quality entity per section heading, which
   inflates PageRank for trivial concepts and pollutes Leiden community
   detection.
3. **Wasted tool-result tokens** — formatted tool result includes
   excerpts from retrieved chunks. TOC excerpts consume token budget
   without contributing grounding.

### Solution: filter on Docling's own DocItemLabel.DOCUMENT_INDEX

Docling's layout model already classifies TOC / index pages with the
explicit label `DocItemLabel.DOCUMENT_INDEX` (defined in
`docling-core/docling_core/types/doc/labels.py`). HybridChunker preserves
the label on the chunk's `meta.doc_items`, so we just inspect and skip.

This is strictly cleaner than a section-path heuristic because:
- It uses the layout model's own classification (no fragile string
  matching on `"Contents"`, `"Index"`, etc.)
- Works regardless of language ("Inhalt", "Sommaire", "Índice")
- Catches partial-page TOCs that don't have a section heading
- One label, one comparison — minimal code surface

Docling's HybridChunker does NOT auto-filter `DOCUMENT_INDEX`
(per [issue #287](https://github.com/docling-project/docling/issues/287)
the team plans to use TOC info for hierarchy hints but not as a chunk
filter). So we filter ourselves at the chunk-iteration boundary.

### Implementation (LANDED 2026-05-02)

In `noted/graph/app/scanners/pdf_scanner.py`:

```python
TOC_FILTER_RATIO: float = float(os.environ.get('TOC_FILTER_RATIO', '1.0'))

# Inside the chunk loop, lazy-imported:
from docling_core.types.doc import DocItemLabel
items = raw.meta.doc_items or []
if items and TOC_FILTER_RATIO > 0:
    n_toc = sum(1 for it in items
                if getattr(it, 'label', None) == DocItemLabel.DOCUMENT_INDEX)
    if n_toc / len(items) >= TOC_FILTER_RATIO:
        n_toc_dropped += 1
        continue
```

Per-doc log now includes `toc_dropped=N ratio=R.RR` for visibility.

### Tunable knob

`TOC_FILTER_RATIO` env var:

| Value | Behaviour |
|---|---|
| `1.0` (default) | Strict. Only drop chunks where 100 % of doc_items are DOCUMENT_INDEX. Near-zero false positives. |
| `0.5` | Majority vote. Drop chunks where most items are DOCUMENT_INDEX (catches mixed-content TOC merges). |
| `0.0` | Disabled. Keep all chunks regardless of label. |

Start with `1.0`; loosen to `0.5` only if logs show many TOC chunks are
being kept due to mixed-content merges.

### Pending — domain rebuilds required

The filter only affects FUTURE chunks. Existing TOC chunks already sit
in ChromaDB + ArcadeDB across all 5 Domains. To purge them, every
Domain needs a rebuild after `noted-graph` is rebuilt with this code.

**Plan:**
1. Wait for current `ml` rebuild (in progress with marginalia-only fix)
   to complete.
2. Rebuild `noted-graph` to deploy the TOC filter code.
3. Re-rebuild all 5 Domains in size order (smallest first):
   ```bash
   for d in eu_ai pt_digital_ai sw_arch noted ml; do
     curl -X POST --max-time 3600 http://localhost:8123/api/domains/$d/rebuild
   done
   ```
4. Validate: `docker logs noted-graph | grep toc_dropped` — confirm
   per-PDF drops are non-zero where expected.

Total cost: ~25 min × 5 Domains = ~2 hours of cumulative GPU time.
Pairs with the marginalia fix that's already in pdf_scanner — both
benefits land in the same rebuild pass.

### What this does NOT cover

- `PAGE_HEADER` / `PAGE_FOOTER` (running headers like
  "Chapter 5 — Methods, page 47") are NOT filtered by this change.
  Same approach would work; not implemented yet because the impact
  is smaller (these are usually short lines, not full chunks).
- `FOOTNOTE` content is kept (often legitimately useful).
- Mixed chunks where TOC is the minority pass through at the default
  ratio — adjust `TOC_FILTER_RATIO` to `0.5` if this becomes an issue.

### Sources / refs

- [docling-core/labels.py source](https://github.com/DS4SD/docling-core/blob/main/docling_core/types/doc/labels.py)
- [Docling issue #287 — TOC for hierarchy](https://github.com/docling-project/docling/issues/287)
- [Docling concepts: chunking](https://github.com/docling-project/docling/blob/main/docs/concepts/chunking.md)
