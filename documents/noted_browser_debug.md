# Browser JavaScript Debugging - Investigation Notes

## Date: 2026-04-06

## Summary

Investigated feasibility of debugging browser-side JavaScript from noted's editor (setting breakpoints in .js files that pause execution in the browser).

## What We Have

- vscode-js-debug (vendored v1.112.0) fully supports Chrome debugging
- DAP server accepts `adapterID: 'chrome'` and returns full breakpoint capabilities
- DAP transport, breakpoint gutter, child session handling all reusable from Node.js debug
- The gap is small from a protocol perspective

## The Constraint

noted runs server-side in a Docker container. Browser JS debugging requires launching or connecting to a Chrome instance on the user's machine. VS Code solves this via `runInTerminal` which executes commands locally - not possible from a web-based IDE.

## Approaches Considered

| Approach | Feasibility | Notes |
|---|---|---|
| Launch Chrome from container | Not possible | Container has no display, Chrome runs on user's machine |
| `runInTerminal` reverse request | Not possible | Would need to run on user's machine, not in container |
| User launches Chrome with `--remote-debugging-port` | Awkward UX | Requires manual Chrome restart with special flags |
| Browser extension | Feasible but complex | Extension connects to noted backend, proxies CDP |
| Companion desktop app | Feasible but complex | Electron/Tauri app with embedded Chrome debug |
| `debugger;` statement injection | Simple but limited | Visual breakpoints insert `debugger;` lines in source, browser DevTools pauses there |

## Recommended Path

The `debugger;` injection approach is the simplest with immediate value:
- Breakpoint gutter click inserts/removes `debugger;` statement at that line
- Browser DevTools must be open (F12) for `debugger;` to pause
- No special Chrome flags, no extensions, no companion app
- Works with any browser, not just Chrome
- Limited: no conditional breakpoints, no variable inspection from noted

For full browser debugging, a browser extension would be needed. This is how cloud IDEs (Gitpod, Codespaces, StackBlitz) handle it - they either delegate to local VS Code or use browser extensions.

## Status

Documented as planned improvement. Not blocking for current deliverables.
