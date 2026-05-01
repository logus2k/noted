# Domain & Document CRUD — Consolidated UX

## Goal

A single panel that exposes every read/write action for Domains and their documents. Replaces `KnowledgeBaseManagerPanel` outright — no second "manager" sibling.

## Trigger

- Click on a Domain root node in the Explorer tree.
- Right-click → "Manage Domain..." on a Domain root or any sub-node (selects that Domain in the left pane).
- Existing toolbar entry that today opens `KnowledgeBaseManagerPanel`.

One panel instance globally (re-uses if already open). Implemented as a jsPanel for consistency with the existing Monitor.

## Layout — master-detail

```
┌──────────────────────────────────────────────────────────────────┐
│ [+ New Domain]                                                   │
├─────────────────┬────────────────────────────────────────────────┤
│ Domain list     │ <selected Domain> — name + description         │
│                 ├────────────────────────────────────────────────┤
│ ⚪ general      │ [Documents] [Knowledge] [Settings]             │
│ ⚪ noted        │                                                │
│ ⚪ eu_ai        │ <tab content>                                  │
│ ⚫ sw_arch  [×] │                                                │
│                 │                                                │
└─────────────────┴────────────────────────────────────────────────┘
```

### Left pane — Domain list

| Element | Behavior |
|---|---|
| `+ New Domain` button | Opens the existing create-modal (`POST /api/domains`) |
| Per-row radio (active toggle) | Calls `PATCH /api/domains/active` with the updated set |
| Per-row name | Click selects the row; right pane fills in |
| Per-row delete `[×]` | Disabled when `deletable: false`; otherwise prompts confirmation, calls `DELETE /api/domains/{id}` |

### Right pane — selected Domain header + three tabs

#### Header

| Element | Behavior |
|---|---|
| Display name | Inline-editable; commits via `PATCH /api/domains/{id}` |
| Description | Inline-editable; same endpoint |

#### Tab: Documents

| Column | Source | Notes |
|---|---|---|
| Name | `display_name` or basename | Click → opens in DocumentViewer |
| Category | manifest entry | Inline edit |
| Mode | `read_only` / `read_store` | Read-only |
| Last modified | manifest entry | Sortable |
| Actions | per row | Rename, Set Category, Open, Delete |

Top toolbar: `Upload Document...` (existing modal); search filter; bulk-select for multi-delete.

Replaces the scattered tree leaves under `kb-documents:doc:*`, `kb-graph-doc:*`, and `emb:src:*` as the canonical surface. Tree leaves can stay as a power-user shortcut.

#### Tab: Knowledge

| Card | Contents | Source |
|---|---|---|
| Vector RAG | total chunks, sources indexed, format breakdown | `/api/rag/index/sources?collection={id}__corpus` |
| Graph | entities, relationships, communities, last build, phase chip | `/api/graph/research/{id}/status` |
| Action | `Rebuild Graph` button (disabled during rebuild); inline phase progress; `pending_recluster` banner if behind | `POST /api/graph/research/{id}/rebuild` |

Reuses `KnowledgeBaseMonitorPanel`'s phase chips, recluster banner, and timer logic verbatim.

#### Tab: Settings

| Field | Behavior |
|---|---|
| Display name | Inline edit (same as header) |
| Description | Inline edit (same as header) |
| Pinned | Read-only flag from registry |
| Embeddings model | Read-only (`bge-m3`) |
| Delete Domain | Same action as left-pane `[×]`, kept here for symmetry |

## Endpoints already in place

| Action | Endpoint | Status |
|---|---|---|
| Create Domain | `POST /api/domains` | Wired |
| Delete Domain | `DELETE /api/domains/{id}` | Wired |
| Rename / re-describe | `PATCH /api/domains/{id}` | Backend exists; no UI today |
| Set active set | `PATCH /api/domains/active` | Wired |
| List documents | `GET /api/graph/research/{id}/corpus` | Backend exists; UI today scatters across Explorer trees |
| Upload document | `POST /api/graph/research/{id}/corpus/upload` | Wired (modal) |
| Rename document | `PATCH /api/domains/{id}/documents/display_name` | Wired |
| Set category | `PATCH /api/domains/{id}/documents/category` | Wired |
| Delete document | `DELETE /api/domains/{id}/documents?path=...` | Wired |
| Rebuild graph | `POST /api/graph/research/{id}/rebuild` | Wired |
| Status / phase | `GET /api/graph/research/{id}/status` | Wired |

No backend work needed. The panel is a UI consolidation only.

## Implementation outline

| File | Role |
|---|---|
| `frontend/js/knowledge-graph/DomainManagerPanel.js` | Main panel. Master-detail container + left list + right pane router. Replaces `KnowledgeBaseManagerPanel.js`. |
| `frontend/js/knowledge-graph/DomainDocumentsTab.js` | Documents table + actions. |
| `frontend/js/knowledge-graph/DomainKnowledgeTab.js` | Stats + rebuild controls. Wraps existing Monitor logic. |
| `frontend/js/knowledge-graph/DomainSettingsTab.js` | Inline-edit form + delete. |
| `frontend/css/domain-manager.css` | Panel-scoped styles (master-detail layout). |
| `frontend/js/panels/explorer/ExplorerContextMenu.js` | Add `Manage Domain...` action that opens the panel and selects the right row. |
| Caller updates | Wherever `KnowledgeBaseManagerPanel` is opened (toolbar / shortcut), point at `DomainManagerPanel`. Delete the old class file. |

## What stays as-is

- Existing context-menu actions on individual tree leaves (Upload, Rename, Delete on `kb-documents:doc:*` etc.) — power-users prefer in-place context. The new panel is the canonical surface; tree leaves are shortcuts.
- `KnowledgeBaseMonitorPanel` (live polling view) — keep it as the lightweight always-on observer. The Knowledge tab inside the new panel covers the same data when the user is doing a focused operation.

## Out of scope

- Bulk operations across multiple Domains.
- Export / import of a Domain to disk.
- Permissions / sharing — single-user app today.
