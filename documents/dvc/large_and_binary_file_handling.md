# Large and Binary File Handling in noted

## Problem

Clicking a file in the Explorer currently calls `file_manager.read_file()`, which reads the
entire file into memory as a single UTF-8 string and returns it to the frontend. The frontend
then hands the content to CodeMirror for rendering.

This works for source code and small text files, but breaks for:

1. **Binary blobs** (e.g. DVC cache entries under `.dvc/cache/`, like `9915f05bfafef18e471a97ae679535`).
   Reading them with `errors="replace"` produces a huge string of replacement characters that
   both wastes memory and feeds garbage to CodeMirror.
2. **Very large text files** (hundreds of MB, e.g. raw CSVs, JSON dumps). The read returns
   successfully but CodeMirror's initial parse, layout, and minimap rendering block the main
   thread long enough to freeze the UI.

The fetch itself is async and does not block - the freeze happens when CodeMirror starts
processing a multi-MB string. Disabling file previews for anything above a fixed size is not a
good answer because users legitimately need to edit large files.

## Proposed solution

A layered approach that keeps the UI responsive without capping what can be opened.

### 1. Backend: detect binary files early

In `file_manager.read_file()`, before reading the full file:

- Read the first 8 KB.
- If it contains null bytes, or fails a strict UTF-8 decode, treat it as binary.
- Return `{binary: true, size, mime}` without loading the rest.

This handles DVC cache files, object files, compiled binaries, etc. The frontend then shows a
dedicated "Binary file" panel with:

- File size and MIME type
- A Download button (uses the existing `/raw` endpoint)
- Optionally, an "Open as hex" action (future work)

No garbage data ever reaches CodeMirror.

### 2. Frontend: tiered CodeMirror configuration for large text

CodeMirror 6 handles large text files reasonably well on its own because it only renders the
visible viewport. The bottlenecks are the extensions that touch every line:

- **Syntax highlighting (Lezer parser)**: incremental but initial parse of huge files lags
- **Line wrapping**: forces layout of every line
- **Minimap**: renders the entire document
- **Diagnostics / LSP**: can choke on huge files

For text files above a threshold (e.g. 5 MB), `FileEditor.open()` disables these extensions
and loads the file in plain-text mode:

```
if (size > LARGE_TEXT_THRESHOLD) {
    // Disable: _languageForFile, EditorView.lineWrapping, minimap, LSP client
    // Keep: line numbers, history, basic keymap
}
```

Editing still works; the file just loads and scrolls without heavy processing.

### 3. Frontend: confirmation gate for huge files

For files above a second threshold (e.g. 50 MB), show a confirmation prompt before loading:

> This file is 87 MB. Previewing large files may slow down the editor.
> [Open anyway] [Cancel]

This matches VS Code's behaviour and prevents accidental hangs when a user clicks a file
without realising its size.

### 4. (Future) Sliding-window read for truly massive files

For files in the hundreds of MB, even CodeMirror's virtualised rendering is not enough because
the full document still lives in memory. A sliding-window approach would:

- Read chunks on demand via HTTP Range requests (`/api/files/.../read?offset=...&length=...`)
- Proxy the document in CodeMirror so only the currently-visible chunk is resident
- Allow read-only viewing (write-back for sliding windows is non-trivial)

This is explicitly out of scope for the initial fix - it only matters for the tiny minority of
files that are both text and hundreds of MB. It is documented here so the option is on record
when the need arises.

## Thresholds (suggested defaults)

| Tier | Size | Behaviour |
|------|------|-----------|
| Small | < 5 MB | Full CodeMirror experience |
| Large | 5-50 MB | Plain-text mode (no syntax highlighting, no minimap, no LSP, no wrapping) |
| Huge | > 50 MB | Confirmation gate before loading |
| Massive | > 500 MB | Sliding window (future) |
| Binary | any | Binary preview panel with size, MIME, download |

## Status

Not implemented. The current behaviour (UI hang on large or binary files) is a known issue and
will be addressed when this becomes a blocker. For now, users should avoid opening files under
`.dvc/cache/` or other known binary locations.
