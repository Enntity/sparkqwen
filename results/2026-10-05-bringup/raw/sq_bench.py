#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""sq_bench.py ARM [cells]  -- SparkQwen quick bench against 127.0.0.1:8893 (stdlib only).

Cells (default all): decode prefill conc warm. Writes ~/sparkqwen-dev/bench-ARM.json.
Every request streams, temperature 0, reasoning_effort low. Salts are seeded so every arm sends the
same prompts, and every cold prompt is unique within an arm (nothing hits the cache by accident).
  decode   C1 prose / code / JSON, 384 tokens, 3 reps each: TTFT and decode tok/s after the first token
  prefill  cold TTFT at ~2K, 8K, 16K, 28K prompt tokens (2 reps, 16 output tokens)
  conc     C1, C2, C4 aggregate decode tok/s, 256 tokens per stream, 2 reps
  warm     one 8K and one 20K conversation: cold turn, then 5 follow-ups (TTFT per turn, cached tokens)
"""
import json, os, random, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = os.environ.get("SQ_URL", "http://127.0.0.1:8893")
MODEL = os.environ.get("SQ_MODEL", "qwen3.8-flash-next-atlas")
KW = {"reasoning_effort": "low"}
ARM = sys.argv[1]
CELLS = sys.argv[2:] or ["decode", "prefill", "conc", "warm"]
rng = random.Random(20261005)

PROMPTS = {
    "prose": "Write a calm, detailed essay about how lighthouses were staffed and maintained in the 1800s. Plain paragraphs only.",
    "code": "Write a Python module implementing an LRU cache with TTL expiry, thread safety, and unit tests using unittest. Code only.",
    "json": "Return a JSON array of 12 fictional library books. Each object has title, author, year, isbn, genres (array) and a one-sentence summary. JSON only.",
}


def stream(messages, max_tokens, min_tokens=None, timeout=1800):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}, "chat_template_kwargs": KW}
    if min_tokens:
        body["min_tokens"] = min_tokens
    req = urllib.request.Request(URL + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = None; text = []; usage = {}
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            line = line.strip()
            if not line.startswith(b"data:") or line == b"data: [DONE]":
                continue
            d = json.loads(line[5:])
            if d.get("usage"):
                usage = d["usage"]
            for c in d.get("choices", []):
                delta = c.get("delta", {})
                piece = (delta.get("content") or "") + (delta.get("reasoning_content") or delta.get("reasoning") or "")
                if piece:
                    if first is None:
                        first = time.time()
                    text.append(piece)
    end = time.time()
    n = usage.get("completion_tokens", 0)
    ttft = (first or end) - t0
    rate = (n - 1) / (end - first) if first and n > 1 and end > first else 0.0
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    return {"ttft": round(ttft, 3), "wall": round(end - t0, 3), "out": n, "prompt": usage.get("prompt_tokens"),
            "cached": cached, "tok_s": round(rate, 2), "text_head": "".join(text)[:80]}


def registry(rows, salt):
    r = random.Random(salt)
    return "\n".join(f"Entry {i}: station-{r.randint(1000, 9999)} logs code {r.randint(100000, 999999)} on shelf {r.choice('ABCDEFGH')}{r.randint(1, 40)}."
                     for i in range(rows))


def ctx(tokens, salt):  # ~27.6 tokens per registry row (measured on this tokenizer)
    return registry(max(4, int(tokens / 27.6)), salt)


res = {"arm": ARM, "date": time.strftime("%Y-%m-%d %H:%M:%S"), "cells": {}}
out_path = os.path.expanduser(f"~/sparkqwen-dev/bench-{ARM}.json")


def save():
    json.dump(res, open(out_path, "w"), indent=1)


if "decode" in CELLS:
    rows = []
    for k, p in PROMPTS.items():
        for rep in range(3):
            r = stream([{"role": "user", "content": p}], 384, 384); r.update(kind=k, rep=rep); rows.append(r)
            print("decode", k, rep, r["ttft"], r["tok_s"], r["out"], flush=True)
    res["cells"]["decode"] = rows; save()

if "prefill" in CELLS:
    rows = []
    for size in (2048, 8192, 16384, 28672):
        for rep in range(2):
            c = ctx(size, f"pf-{size}-{rep}")
            r = stream([{"role": "user", "content": c + "\n\nWhich shelf holds Entry 3? Answer briefly."}], 16)
            r.update(size=size, rep=rep); rows.append(r)
            print("prefill", size, rep, r["prompt"], r["ttft"], flush=True)
    res["cells"]["prefill"] = rows; save()

if "conc" in CELLS:
    rows = []
    ks = list(PROMPTS)
    for c in (1, 2, 4):
        for rep in range(2):
            def one(i):
                return stream([{"role": "user", "content": PROMPTS[ks[i % 3]] + f" (variant {rep}-{i})"}], 256, 256)
            t = time.time()
            with ThreadPoolExecutor(c) as ex:
                rs = list(ex.map(one, range(c)))
            w = time.time() - t; n = sum(x["out"] for x in rs)
            rows.append({"c": c, "rep": rep, "wall": round(w, 2), "tokens": n, "agg_tok_s": round(n / w, 2),
                         "per_stream_tok_s": [x["tok_s"] for x in rs], "ttft": [x["ttft"] for x in rs]})
            print("conc", c, rep, rows[-1]["agg_tok_s"], flush=True)
    res["cells"]["conc"] = rows; save()

if "warm" in CELLS:
    rows = []
    for size in (8192, 20480):
        c = ctx(size, f"warm-{size}")
        msgs = [{"role": "user", "content": c + "\n\nRead the registry above. Reply only with OK."}]
        for turn in range(6):
            r = stream(msgs, 48); r.update(size=size, turn=turn); rows.append(r)
            print("warm", size, turn, r["prompt"], r["cached"], r["ttft"], flush=True)
            msgs.append({"role": "assistant", "content": "OK." if turn == 0 else r["text_head"]})
            msgs.append({"role": "user", "content": f"Which shelf holds Entry {3 + 7 * turn}? Answer with the shelf only."})
    res["cells"]["warm"] = rows; save()

print("wrote", out_path)
