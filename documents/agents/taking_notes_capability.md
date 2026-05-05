# Take-Notes capability for the noted Assistant

## Goal

Let the user ask the Assistant to create or update a note-taking document inline with the conversation, with live preview in the middle panel and undo. General-domain feature, not noted-specific.

## Two cases

| # | Trigger | Storage | Approval | Save |
|---|---|---|---|---|
| 1 | "open foo.md and update it for me" | on-disk file | per-write (existing approval panel) | already saved |
| 2 | "create a notes file and write a report" | in-memory buffer (no path) | none until Save | Save button / Ctrl+S triggers Save-As dialog |

Case 2 sidesteps the approval-cadence problem because writes never touch disk. Approval kicks in only at Save time, exactly when the user expects to be in control.

## Tool surface (general domain)

| Tool | Case | Effect |
|---|---|---|
| `create_doc(name?, initial_content?)` | 2 | New in-memory buffer, returns buffer_id, opens in viewer |
| `append_to_doc(buffer_id, content, separator?)` | 2 | Append to buffer, viewer redraws |
| `replace_doc(buffer_id, content)` | 2 | Full rewrite of buffer |
| `read_doc(buffer_id)` | 2 | Re-read buffer (Assistant uses before non-append edits) |
| `append_to_file(path, content, separator?)` | 1 | New tool, append-mode write to existing file |
| `update_file(path, ...)` | 1 | Existing tool, moved from noted to general domain |
| `undo_last_change(target)` | both | Restore previous snapshot |

All write tools push a snapshot before applying. Undo restores the most recent snapshot for the named target.

## Live preview

- Case 2: every buffer write emits SSE `data.doc = {buffer_id, name, content, path}` with the full new content. Document viewer matches by buffer_id and re-renders.
- Case 1: every disk write emits SSE `data.file_changed = {path}`. Document viewer re-fetches if it is currently displaying that path.

## Phasing

| ID | Scope | Effort |
|---|---|---|
| NOTES-1 | Case 2 backend: buffer registry + 4 tools + SSE `data.doc` + viewer hookup that renders the buffer | 1 day |
| NOTES-2 | Case 2 Save flow: Save button + Ctrl+S on viewer with no path triggers Save-As dialog (project picker, folder tree, filename), backend writes the file, buffer becomes path-bound | 1/2 day |
| NOTES-3 | Case 1 edits: `append_to_file`, move `update_file` to general domain, `data.file_changed` SSE + viewer auto-reload | 1/2 day |
| NOTES-4 | Undo: per-conversation snapshot ring (last N=10) + `undo_last_change` tool | 1/2 day |
| NOTES-5 | System-prompt guidance: prefer `create_doc` for ad-hoc note-taking, always `read_doc`/`get_file_contents` before any non-append edit | small |

NOTES-1 alone unlocks "create a notes file and take notes as we go" for the ephemeral path.

## Open questions (non-blocking)

- Buffer lifetime: tied to chat session, or persisted server-side keyed by chat_id, or held in browser localStorage. Defer to NOTES-2 since Save flow forces the answer.
- Concurrent edits: user typing in the viewer while the Assistant is mid-write. Defer (low priority for a v1; the viewer is read-mostly today).

## Out of scope (deferred to a later feature phase)

- Assistant-triggered Save (user case 3 in the design discussion).
- Branching or diff-based undo. v1 is a linear ring buffer of the last 10 snapshots per target.
- Multi-buffer cross-references (one notes file referencing another).
