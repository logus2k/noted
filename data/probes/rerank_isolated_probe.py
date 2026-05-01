"""Isolated reranker latency probe.

Loads a captured (query, docs) dump from data/rerank_dumps/ and runs
bge-reranker-v2-m3 against it directly — bypassing HTTP, ChromaDB, the
RagService wrapper, and any other contender. Reports per-call timings
under several configurations so we can attribute the observed
~2700 ms-for-20-pairs cost.

Run from inside the noted-rag container:
  docker exec -it noted-rag python3 /data/rerank_dumps/rerank_isolated_probe.py \\
      [/data/rerank_dumps/<dump>.json] [--batch-size 32] [--max-length 512] [--repeat 5]

If no dump path is given, uses the most recent file in /data/rerank_dumps.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import sys

import torch
from sentence_transformers import CrossEncoder


def newest_dump(dump_dir: str) -> str | None:
    if not os.path.isdir(dump_dir):
        return None
    files = [f for f in os.listdir(dump_dir) if f.endswith(".json")]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(os.path.join(dump_dir, f)), reverse=True)
    return os.path.join(dump_dir, files[0])


def load_model(model_path: str) -> CrossEncoder:
    print(f"loading reranker from {model_path}", flush=True)
    t0 = time.perf_counter()
    model = CrossEncoder(model_path, device="cuda", trust_remote_code=True)
    # Some bge-reranker variants ignore the device kwarg under
    # trust_remote_code=True; force the underlying torch model to cuda.
    try:
        model.model.to("cuda")
    except Exception:
        pass
    elapsed = time.perf_counter() - t0
    print(f"  loaded in {elapsed*1000:.0f} ms", flush=True)
    return model


def time_predict(
    model: CrossEncoder,
    pairs: list[tuple[str, str]],
    batch_size: int,
    max_length: int | None,
    label: str,
) -> tuple[float, float]:
    """Returns (wall_ms, gpu_ms)."""
    kwargs: dict = {"batch_size": batch_size, "show_progress_bar": False}
    if max_length is not None:
        kwargs["activation_fct"] = None
        # CrossEncoder doesn't expose max_length as a predict kwarg directly,
        # but the underlying tokenizer does. Set it on the tokenizer once.
        if hasattr(model, "tokenizer") and model.tokenizer is not None:
            model.tokenizer.model_max_length = max_length

    # GPU event timing
    start_evt = torch.cuda.Event(enable_timing=True)
    end_evt = torch.cuda.Event(enable_timing=True)

    torch.cuda.synchronize()
    t_wall0 = time.perf_counter()
    start_evt.record()
    scores = model.predict(pairs, **kwargs)
    end_evt.record()
    torch.cuda.synchronize()
    wall_ms = (time.perf_counter() - t_wall0) * 1000
    gpu_ms = start_evt.elapsed_time(end_evt)
    print(f"  [{label:<30}] wall={wall_ms:7.1f} ms  gpu={gpu_ms:7.1f} ms  n_scores={len(scores)}",
          flush=True)
    return wall_ms, gpu_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump", nargs="?", default=None,
                    help="Path to dump JSON. Defaults to newest in /data/rerank_dumps.")
    ap.add_argument("--model", default=os.environ.get("RERANK_MODEL", "/data/models/bge-reranker-v2-m3"))
    ap.add_argument("--repeat", type=int, default=3,
                    help="Run each config N times to see warm-vs-cold and variance.")
    args = ap.parse_args()

    dump_path = args.dump or newest_dump("/data/rerank_dumps")
    if not dump_path or not os.path.exists(dump_path):
        print("No dump file found. Pass a path or run a chat turn to capture one.",
              file=sys.stderr)
        return 1
    print(f"loading dump: {dump_path}", flush=True)
    with open(dump_path) as f:
        dump = json.load(f)
    query = dump["query"]
    docs = dump["docs"]
    pairs = [(query, d) for d in docs]
    char_lengths = [len(d) for d in docs]
    print(f"  query ({len(query)} chars): {query!r}", flush=True)
    print(f"  docs: n={len(docs)} avg_chars={sum(char_lengths)//len(char_lengths)} "
          f"min={min(char_lengths)} max={max(char_lengths)}", flush=True)

    print(f"\ngpu state at start: {torch.cuda.memory_allocated()//1024//1024} MB allocated", flush=True)

    model = load_model(args.model)

    print(f"\ngpu state after load: {torch.cuda.memory_allocated()//1024//1024} MB allocated", flush=True)

    # Single small warmup pair to flush JIT/initialization on first use.
    print("\nwarmup (single pair):", flush=True)
    time_predict(model, [pairs[0]], batch_size=1, max_length=None, label="warmup")

    print(f"\nfull batch ({len(pairs)} pairs), various configurations:", flush=True)
    configs = [
        ("default (no kwargs)", {"batch_size": 32, "max_length": None}),
        ("batch_size=8 max=512", {"batch_size": 8, "max_length": 512}),
        ("batch_size=16 max=512", {"batch_size": 16, "max_length": 512}),
        ("batch_size=32 max=512", {"batch_size": 32, "max_length": 512}),
        ("batch_size=64 max=512", {"batch_size": 64, "max_length": 512}),
        ("batch_size=32 max=256", {"batch_size": 32, "max_length": 256}),
        ("batch_size=32 max=1024", {"batch_size": 32, "max_length": 1024}),
        ("batch_size=128 max=512", {"batch_size": 128, "max_length": 512}),
    ]
    for label, kw in configs:
        for r in range(args.repeat):
            tag = f"{label} run{r+1}"
            time_predict(model, pairs, batch_size=kw["batch_size"],
                         max_length=kw["max_length"], label=tag)

    print("\nsubsetting: how does cost scale with n_pairs (batch_size=32, max=512)?", flush=True)
    for n in [1, 5, 10, 15, 20]:
        if n > len(pairs):
            continue
        for r in range(args.repeat):
            time_predict(model, pairs[:n], batch_size=32, max_length=512,
                         label=f"n_pairs={n} run{r+1}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
