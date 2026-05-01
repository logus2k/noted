# ipykernel Control Thread Deadlock After Debug Session

## Context

We are building a web-based notebook IDE (similar to JupyterLab) with DAP (Debug Adapter Protocol) debugging support. The debugger uses ipykernel's built-in Debugger class, communicating via Jupyter's `debug_request`/`debug_reply` messages on the ZMQ control channel.

**Environment:**
- ipykernel 7.2.0
- debugpy 1.8.20
- jupyter_client 8.8.0
- Python 3.12

## The Problem

After a debug session that is stopped while paused at a breakpoint, the kernel's **control channel becomes permanently unresponsive**. All subsequent `debug_request` messages (including `initialize` for a new debug session) time out. The shell channel remains responsive - normal code execution works. Only the control channel is deadlocked.

The only recovery is a full kernel restart, which destroys all in-memory state (variables, imports, dataframes).

## Exact Reproduction Steps

1. Connect a kernel client to the kernel
2. Send `debug_request` with `initialize` command on control channel - succeeds
3. Send `debug_request` with `attach` command - succeeds
4. Send `debug_request` with `dumpCell` + `setBreakpoints` - succeeds, breakpoint verified
5. Send `debug_request` with `configurationDone` - succeeds
6. Send `execute_request` on shell channel with the cell code - kernel starts executing
7. Receive `debug_event` `stopped` on iopub - breakpoint hit, kernel paused
8. **Close the debug client's channels** (simulating user clicking "Stop" - disconnects the WebSocket without sending `continue` or `disconnect` DAP commands)
9. From a NEW client, send `debug_request` with `debugInfo` on control channel
10. **Result: control channel never responds. Deadlock.**

## What We've Tried

### Sending `continue` + `disconnect` before closing
```
control_channel.send(debug_request: continue, threadId=1)
control_channel.send(debug_request: disconnect, restart=false)
```
**Result:** Messages are sent but never processed. The control channel is already stuck by the time we send them, or the messages queue behind whatever is blocking.

### Killing the debugpy adapter process
```
pkill -f "debugpy/adapter"
```
**Result:** The debugpy adapter process dies, but the control channel remains blocked. The deadlock is in ipykernel's Python control thread, not in the debugpy adapter.

### Sending `interrupt_kernel()` (SIGINT)
**Result:** SIGINT goes to the main process. The shell thread receives it, but the control thread remains stuck. The control thread runs on a separate Python thread that doesn't receive SIGINT.

### Sending `evaluate` with `_thread.interrupt_main()` while paused
**Result:** Can't send it - the control channel is already blocked and won't process the evaluate request.

### Sending `evaluate` with `ctypes.pythonapi.PyThreadState_SetAsyncExc`
**Result:** Same problem - control channel blocked, evaluate never reaches the kernel.

## Analysis

The control thread in ipykernel 7 runs on its own tornado I/O loop (`self.control_thread.io_loop`). It processes:
1. `debug_request` messages from the control ZMQ channel
2. debugpy TCP stream callbacks (via `debugpy_stream` ZMQ STREAM socket)
3. `poll_stopped_queue` coroutine (for forwarding stopped events)

When paused at a breakpoint:
- `poll_stopped_queue` has called `handle_stopped_event()` which sent a `threads` request to debugpy and is awaiting the response via `message_queue.get()`
- The debugpy TCP stream callback processes incoming messages and routes them to either `event_callback` (for events) or `message_queue` (for responses)

When the debug client disconnects without sending `continue`:
- The kernel's shell thread remains blocked by debugpy's trace hooks (paused at breakpoint)
- The debugpy adapter may or may not still be running
- The `handle_stopped_event` coroutine may be stuck waiting for a debugpy response
- The control thread's I/O loop may be blocked on the `message_queue.get()` await

**Hypothesis:** The `handle_stopped_event` coroutine is holding the control thread's event loop. When we send new `debug_request` messages, they arrive on the ZMQ socket but the event loop can't process them because it's stuck in `await message_queue.get()` - waiting for a debugpy response that will never come because the debug client disconnected.

## What We Need

A way to reset the kernel's debugger state (make `isStarted = False`, clear stopped threads, release the control thread) **without restarting the kernel**. Specifically:

1. Unblock the control thread so it can process new `debug_request` messages
2. Release debugpy's hold on the shell thread (so paused execution either aborts or completes)
3. Reset `Debugger.is_started` to `False` so a new `initialize` works

## Key ipykernel Source References

```python
# ipykernel/debugger.py - handle_stopped_event blocks on message_queue
async def handle_stopped_event(self):
    event = await self.stopped_queue.get()
    req = {"seq": event["seq"] + 1, "type": "request", "command": "threads"}
    rep = await self._forward_message(req)  # <-- blocks on message_queue.get()
    ...

# ipykernel/debugger.py - _forward_message waits for debugpy response
async def _forward_message(self, msg):
    return await self.debugpy_client.send_dap_request(msg)

# ipykernel/debugger.py - send_dap_request waits on message_queue
async def send_dap_request(self, msg):
    self._send_request(msg)
    rep = await self._wait_for_response()  # <-- message_queue.get()
    return rep

# ipykernel/ipkernel.py - poll_stopped_queue runs on control thread
async def poll_stopped_queue(self):
    while True:
        await self.debugger.handle_stopped_event()  # <-- blocks here
```

## Architecture

```
[Browser] --WebSocket--> [noted backend (dap.py)]
                              |
                              | debug_request (ZMQ control channel)
                              v
                         [ipykernel]
                              |
                              +-- Control Thread (tornado I/O loop)
                              |       |-- processes debug_request
                              |       |-- debugpy_stream callback
                              |       |-- poll_stopped_queue coroutine
                              |       
                              +-- Shell Thread  
                              |       |-- processes execute_request
                              |       |-- blocked by debugpy trace hooks when paused
                              |
                              +-- debugpy adapter (subprocess or in-process)
                                      |-- DAP server on internal TCP port
                                      |-- communicates with ipykernel via ZMQ STREAM
```
