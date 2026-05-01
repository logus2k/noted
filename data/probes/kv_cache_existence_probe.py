"""Prove the KV prefix cache mechanism exists and can be triggered.

We bypass noted entirely and hit agent_server's OpenAI-compatible endpoint
directly, so we have byte-level control over the messages array and can
guarantee that two requests are bit-identical at the input level.

Strategy:
  T1 = cold call with a long fixed prompt P
  T2 = repeat the SAME messages array (identical bytes -> identical chat-
       template render -> identical token sequence). If KV cache exists
       and works, T2 << T1 because every token in the prompt is restored
       from the RAM cache and only the 1 generated token costs compute.
  T3 = same P plus a short tail. If cache works on prefixes, prefill cost
       should be ~T1 - T2 worth of "marginal extension only", much less
       than T1.
  T4 = different long prompt of the same length. No shared prefix beyond
       the BOS / chat template skeleton, so T4 ~ T1.
  T5 = repeat P again. If P is still in the cache after T4 ran, T5 ~ T2.
       (Tests that the cache holds multiple distinct prefixes.)

Each call uses max_tokens=1 so wall clock is dominated by prefill, not
generation. Output is also logged so we can sanity-check the model is
still producing text rather than crashing.
"""
import json
import sys
import time
import urllib.request

URL = "http://localhost:7701/v1/chat/completions"
MODEL = "gemma-4-e4b-it-q4-kxl-gguf"  # bare model id => no preset system prompt

# Long stable paragraph repeated to make prefill cost meaningful.
BLOCK = (
    "The KV cache stores per-layer attention key and value tensors for tokens "
    "that have already been processed. When a new prompt arrives, llama.cpp "
    "looks for the longest contiguous prefix of the new prompt's tokens that "
    "matches a previously cached state, and restores that state instead of "
    "re-running the prefill pass for those tokens. Only the suffix beyond the "
    "match boundary needs fresh compute. This is why prefix stability across "
    "consecutive turns is so valuable: any change at position k invalidates "
    "the cache for every token from k onward.\n\n"
)


def make_long_prompt(repeat: int = 40, suffix: str = "") -> str:
    body = BLOCK * repeat
    if suffix:
        body += "\n" + suffix
    return body


def call(messages, label: str, max_tokens: int = 1):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=240) as resp:
        data = json.loads(resp.read().decode())
    wall = time.time() - t0
    usage = data.get("usage") or {}
    out_text = ""
    if data.get("choices"):
        out_text = (data["choices"][0].get("message") or {}).get("content", "")
    return {
        "label": label,
        "wall": wall,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "input_chars": sum(len(m.get("content", "")) for m in messages),
        "out_preview": (out_text or "").strip()[:60],
    }


def fmt(r: dict) -> str:
    return (
        f"[{r['label']:<8}] wall={r['wall']:6.3f}s  "
        f"prompt_tok={r['prompt_tokens']:>5}  "
        f"out_tok={r['completion_tokens']:>3}  "
        f"in_chars={r['input_chars']:>6}  "
        f"out={r['out_preview']!r}"
    )


def main():
    long_prompt = make_long_prompt(repeat=40)
    extended_prompt = long_prompt + "\n\nQuestion: respond with the single token 'OK'."
    different_prompt = (
        "The pomegranate is a fruit-bearing deciduous shrub native to a "
        "region from Iran to northern India. Cultivation traces back to "
        "antiquity in the Mediterranean basin. Its botanical taxonomy "
        "places it within the family Lythraceae. " * 40
    )

    P = [{"role": "user", "content": long_prompt}]
    P_ext = [{"role": "user", "content": extended_prompt}]
    P_diff = [{"role": "user", "content": different_prompt}]

    print("Sequence:")
    print("  T1 = first cold send of P")
    print("  T2 = identical repeat of P  (expect: cache full hit -> tiny wall)")
    print("  T3 = P + small suffix       (expect: cache hits long prefix)")
    print("  T4 = different long prompt  (expect: cold-equivalent for its content)")
    print("  T5 = repeat P again         (expect: cache still holds P -> tiny wall)")
    print()

    rows = []
    rows.append(call(P, "T1"))
    print(fmt(rows[-1]))
    rows.append(call(P, "T2"))
    print(fmt(rows[-1]))
    rows.append(call(P_ext, "T3"))
    print(fmt(rows[-1]))
    rows.append(call(P_diff, "T4"))
    print(fmt(rows[-1]))
    rows.append(call(P, "T5"))
    print(fmt(rows[-1]))

    print()
    print("Interpretation:")
    t = {r["label"]: r for r in rows}
    print(f"  T1 cold prefill on P:                {t['T1']['wall']:.3f}s "
          f"({t['T1']['prompt_tokens']} tok)")
    print(f"  T2 / T1 ratio (identical repeat):    {t['T2']['wall']/t['T1']['wall']:.3f}")
    print(f"  T3 / T1 ratio (P + small suffix):    {t['T3']['wall']/t['T1']['wall']:.3f}")
    print(f"  T4 / T1 ratio (different prompt):    {t['T4']['wall']/t['T1']['wall']:.3f}")
    print(f"  T5 / T1 ratio (P again, after T4):   {t['T5']['wall']/t['T1']['wall']:.3f}")
    print()
    if t["T2"]["wall"] < t["T1"]["wall"] * 0.5:
        print(f"  -> Cache HIT confirmed on T2 (>= 2x speedup vs T1).")
    else:
        print(f"  -> WARNING: T2 not significantly faster than T1. Cache may not be active.")
    if t["T5"]["wall"] < t["T1"]["wall"] * 0.5:
        print(f"  -> Cache PERSISTED across T4 (T5 still hits).")
    else:
        print(f"  -> NOTE: T5 didn't hit the cache. Eviction or capacity-based replacement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
