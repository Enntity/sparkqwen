# SPDX-License-Identifier: AGPL-3.0-only
"""C1 decode rate with thinking off (MTP active) and on (inside <think>), T=0.

usage: decode_probe.py TAG [REPS=3]   -> decode-TAG.json
Decode rate = (completion tokens - 1) / (last token time - first token time),
from the server's usage count on a streamed request.
"""
import json, os, statistics, sys, time, urllib.request

URL = os.environ.get("SQ_URL", "http://127.0.0.1:8893")
MODEL = os.environ.get("SQ_MODEL", "qwen3.8-27b-atlas")
TAG = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CODE = ("Write a complete Python MinHeap class with push, pop, peek, heapify and __len__, "
        "with docstrings and a short usage example. Output only the code.")
THINK = ("A train leaves at 9:40 and travels 237 km at an average of 79 km/h, then waits 18 minutes, "
         "then travels 154 km at 88 km/h. When does it arrive? Think it through carefully.")
CASES = {
    "think_off_code": ({"reasoning_effort": "none"}, CODE),
    "think_on": ({}, THINK),
}


def run(extra, prompt, max_tokens=1500):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
            "temperature": 0, "stream": True, "stream_options": {"include_usage": True}, **extra}
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter(); first = last = None; usage = None; think_chars = text_chars = 0
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            ev = json.loads(line[5:])
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices", []):
                d = ch.get("delta", {})
                r_txt = d.get("reasoning_content") or d.get("reasoning") or ""
                c_txt = d.get("content") or ""
                if r_txt or c_txt:
                    now = time.perf_counter()
                    first = first or now; last = now
                    think_chars += len(r_txt); text_chars += len(c_txt)
    n = usage["completion_tokens"]
    return {"tokens": n, "ttft_ms": (first - t0) * 1e3, "decode_tok_s": (n - 1) / (last - first),
            "think_chars": think_chars, "text_chars": text_chars}


out = {}
for name, (extra, prompt) in CASES.items():
    run(extra, prompt, 64)  # warm this shape
    reps = [run(extra, prompt) for _ in range(REPS)]
    out[name] = {"reps": reps, "median_tok_s": statistics.median(r["decode_tok_s"] for r in reps)}
    print(name, [round(r["decode_tok_s"], 1) for r in reps], "tokens", [r["tokens"] for r in reps],
          "think/text chars", [(r["think_chars"], r["text_chars"]) for r in reps], flush=True)
json.dump(out, open(f"decode-{TAG}.json", "w"), indent=1)
