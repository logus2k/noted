"""End-to-end trace of one assistant turn against the live noted stack.

Hits POST /api/llm/chat (the same endpoint the chat UI uses), reads the
SSE stream chunk by chunk, and timestamps every event. Produces a
per-event timeline AND, separately, isolates the noted-graph
/research/query call for comparison.

No mock, no synthetic. Real services, real Gemma calls.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime

NOTED_CHAT = "http://localhost:8123/api/llm/chat"
GRAPH_QUERY = "http://localhost:5523/research/query"

QUESTION = "summarize how MLflow and DVC connect in noted"  # thematic -> research_topic


def post_sse(url: str, body: dict, timeout: float = 60.0):
    """POST and yield (relative_seconds_from_start, event_type, raw_event_data) tuples
    until the stream closes. Uses urllib so we don't need an HTTP lib."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        cur_event = None
        cur_data_lines: list[str] = []
        for raw in r:
            line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
            if line == "":
                # Dispatch
                if cur_event or cur_data_lines:
                    data = "\n".join(cur_data_lines)
                    yield (time.perf_counter() - t0, cur_event or "message", data)
                cur_event = None
                cur_data_lines = []
                continue
            if line.startswith("event:"):
                cur_event = line[6:].strip()
            elif line.startswith("data:"):
                cur_data_lines.append(line[5:].lstrip())


def time_chat_turn(question: str) -> dict:
    """Trace one /api/llm/chat call. Returns events + summary."""
    body = {
        "message": question,
        "client_id": f"trace-{int(time.time())}",
        "think_enabled": False,  # /no_think to avoid Gemma's reasoning preamble dominating
        "temperature": 0.5,
        "max_tokens": 2048,
        # Provide project context so docs-rag skill fires (workspace_active trigger)
        "context_descriptor": {"project_id": "Examples"},
    }
    events = []
    text_first_token_at = None
    text_last_token_at = None
    text_token_events = 0
    text_chars = 0
    tool_result_at = None

    print(f"\n=== POST /api/llm/chat: {question!r} ===")
    print(f"{'time(s)':>9}  {'event':22s}  preview")
    print("-" * 80)

    for t, ev, data in post_sse(NOTED_CHAT, body, timeout=120.0):
        # Try to parse JSON payload
        payload = None
        try:
            payload = json.loads(data) if data else None
        except Exception:
            pass

        # Token events on this stream are emitted as event:message with
        # payload {"token": "..."}. Track each occurrence.
        if isinstance(payload, dict) and "token" in payload:
            tok = payload.get("token", "") or ""
            if tok.strip():
                if text_first_token_at is None:
                    text_first_token_at = t
                text_last_token_at = t
                text_token_events += 1
                text_chars += len(tok)
        if isinstance(payload, dict) and "tool_result" in payload and tool_result_at is None:
            tool_result_at = t

        # Skip per-token spam in the visible log; show milestones
        if ev not in ("content",):
            preview = ""
            if isinstance(payload, dict):
                # Trim large fields
                p = {k: (str(v)[:60] + "..." if len(str(v)) > 60 else v) for k, v in payload.items()}
                preview = json.dumps(p)[:80]
            elif data:
                preview = data[:80]
            print(f"{t:>9.3f}  {ev:22s}  {preview}")

        events.append({
            "t": t,
            "event": ev,
            "data": payload if payload is not None else data,
        })

    total = events[-1]["t"] if events else 0
    return {
        "question": question,
        "total_seconds": total,
        "first_content_token_at": text_first_token_at,
        "last_content_token_at": text_last_token_at,
        "tool_result_at": tool_result_at,
        "n_token_events": text_token_events,
        "content_chars": text_chars,
        "n_events": len(events),
        "events": events,
    }


def time_graph_query(question: str) -> dict:
    """Time noted-graph's /research/query directly. This is what
    research_topic calls under the hood, but without the Assistant
    Gemma wrapper turn."""
    body = {"question": question, "mode": "auto"}
    print(f"\n=== POST /research/query: {question!r} ===")
    t0 = time.perf_counter()
    req = urllib.request.Request(
        GRAPH_QUERY,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        envelope = json.loads(r.read())
    total = time.perf_counter() - t0
    print(f"  total: {total*1000:.0f} ms")
    print(f"  mode: {envelope.get('mode')}, citations: {len(envelope.get('citations') or [])}, answer chars: {len(envelope.get('answer') or '')}")
    return {"total_seconds": total, "envelope_summary": {
        "mode": envelope.get("mode"),
        "n_citations": len(envelope.get("citations") or []),
        "answer_chars": len(envelope.get("answer") or ""),
        "communities_used": envelope.get("communities_used"),
    }}


def main():
    out = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "question": QUESTION,
    }

    # Trace the full chat turn
    chat = time_chat_turn(QUESTION)
    out["chat_turn"] = {
        "total_seconds": chat["total_seconds"],
        "first_content_token_at": chat["first_content_token_at"],
        "content_chars": chat["content_chars"],
        "n_events": chat["n_events"],
        "events": chat["events"],
    }

    # Time the underlying graph call (single-shot, not from the assistant)
    out["graph_query_direct"] = time_graph_query(QUESTION)

    with open("trace_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n=== full trace -> trace_results.json ===")
    print(f"chat turn total:           {chat['total_seconds']:.2f} s")
    print(f"tool_result at:            {(chat.get('tool_result_at') or 0):.2f} s")
    print(f"first content token at:    {(chat['first_content_token_at'] or 0):.2f} s")
    print(f"last content token at:     {(chat.get('last_content_token_at') or 0):.2f} s")
    print(f"# token events emitted:    {chat.get('n_token_events', 0)}")
    print(f"content chars streamed:    {chat['content_chars']}")
    print(f"graph_query_direct total:  {out['graph_query_direct']['total_seconds']:.2f} s")


if __name__ == "__main__":
    main()
