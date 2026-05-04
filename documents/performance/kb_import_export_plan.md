# KB Domain Import / Export — design sketch

Goal: backup, restore, share KB content. Document granularity preferred; domain-level acceptable as MVP.

## What a KB domain actually consists of

| Layer | Location | Per-document scoped? |
|---|---|---|
| Domain manifest | `data/domains/<id>/manifest.json` (top-level + per-file entries in `included_files`) | partial (`included_files[i]`) |
| Raw source files | `data/domains/<id>/sources/<filename>` | yes — one file each |
| Skills / tools / state | `data/domains/<id>/{skills,tools,state}/` | no — domain-wide |
| ArcadeDB graph | database `<id>` (entities + relationships) | partial — entities can be shared across documents |
| Vector corpus | `<id>__corpus` collection (chunk embeddings + text) | yes — chunks carry `source_path` |
| Entity cache | `<id>__gr_entities` collection | yes — keyed by source |
| Summary cache | `<id>__gr_summaries` collection | yes — keyed by source |

**Implication**: per-document export of vector chunks and caches is straightforward. Per-document export of graph entities is hard because entities are shared (e.g., `concept:transformer` is referenced by multiple papers — export the entity with one paper and you risk duplicating it on import; skip the entity and you lose context).

## Recommended phasing

### Phase 1 — domain-level export/import (MVP)
- Self-describing ZIP archive, suffix `.noteddomain`
- Format:
  ```
  manifest.json              (domain manifest, slightly normalised — drop absolute paths)
  meta.json                  (export schema version, source noted version, exported_at, embeddings_model)
  sources/                   (raw files exactly as on disk)
  skills/  tools/  state/    (domain-scoped extras, optional — may be empty)
  arcadedb_dump.json         (graph dump via ArcadeDB EXPORT DATABASE JSON)
  corpus.jsonl               (one chunk per line: id, embedding, text, metadata)
  caches.jsonl               (entity_cache + summary_cache rows, tagged by collection)
  ```
- Import = drop+recreate the named domain (or refuse if it exists, with `--overwrite` opt-in)
- Why this first: clean idempotency, no shared-entity ambiguity, fully restorable

### Phase 2 — per-document export/import (enhancement)
- Suffix `.noteddocument`
- Format:
  ```
  meta.json                  (source domain id, embeddings_model, schema version)
  manifest_entry.json        (the included_files[i] dict for this doc)
  source/<filename>          (single raw file)
  corpus.jsonl               (chunks where source_path == filename)
  caches.jsonl               (entity_cache + summary_cache rows for this source)
  graph_subgraph.json        (entities mentioned by this doc + edges that touch them, with a "shared_count" hint)
  ```
- Import semantics:
  - Refuse if domain doesn't exist (don't auto-create, since embeddings_model and other domain config matter)
  - Skip raw file copy if identical sha256 already present
  - MERGE entities (not replace) — if entity exists, leave it; if new, add
  - APPEND chunks (no dedup — re-import = explicit user intent)
- Why second: harder semantics around shared entities; MVP value mostly comes from full-domain backup

### Phase 3 — sharing (orthogonal)
- Same archives, different distribution mechanism
- Add a small "Share" UI in KB Manager: produces the archive then offers download / generates a single-use upload URL via a future `/api/kb/share` route
- Public sharing requires PII review of source files — explicit opt-in checkbox per export

## Backend touch points

| Endpoint | Method | Purpose | Reuses |
|---|---|---|---|
| `/api/kb/domains/{id}/export` | GET | streams `.noteddomain` archive | corpus + ArcadeDB readers |
| `/api/kb/domains/import` | POST (multipart) | accepts `.noteddomain`, returns job id | KB ingestion lifecycle |
| `/api/kb/jobs/{id}` | GET (SSE) | progress for long imports | existing SSE pattern in noted-rag |
| `/api/kb/domains/{id}/documents/{path}/export` | GET | `.noteddocument` (Phase 2) | corpus + entity-cache scoped readers |

## UI changes (KB Manager)

- New "Export domain" button next to each domain in the left list — downloads the archive immediately
- New "Import domain" button at the top of the left list — file picker for `.noteddomain`, opens progress modal
- Phase 2: per-row "Export" button on each document in the documents list

## Open questions for you

1. **Embeddings drift on import**: if the source noted instance ran `bge-m3` and the destination runs a different model, we either re-embed (slow, but correct) or refuse (safer). Which?
2. **Sharing channel**: download-to-disk only, or do we want a hosted share-by-URL flow (requires storage + auth model)?
3. **Domain id collisions on import**: prompt for rename, refuse, or auto-suffix?
4. **Per-document delete-and-replace**: when importing a `.noteddocument` whose filename already exists in the domain, replace or refuse? (Replace is risky if the previous version had downstream references in graph; refuse is safer.)

## Estimated effort

- Phase 1 (domain-level): ~1 focused day. Most of the time is the ArcadeDB dump/restore plumbing and stream-archiving without holding the whole thing in memory.
- Phase 2 (document-level): ~1.5 days. The shared-entity merge logic is the hard part.
- Phase 3 (sharing UX): ~half day on top of Phase 1 if download-only; more if hosted.

Recommend starting with Phase 1. Document granularity can come later; domain-level alone covers backup/restore/share for the common case.
