# SPDX-License-Identifier: AGPL-3.0-only
"""Batch alone-equality harness (T=0, streamed).

  bx.py alone OUT.json [--spec]        each prompt alone, C=1 (disable_mtp unless --spec), think on+off
  bx.py conc  OUT.json C [--serial]    all prompts through a pool of C workers (spec on unless --serial)
  bx.py cmp   REF.json RUN.json...     byte-compare every (prompt, think) against REF
"""
import hashlib, json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "http://127.0.0.1:8893/v1/chat/completions"
MODEL = "qwen3.8-27b-atlas"
import os
MAXTOK = int(os.environ.get("BX_MAXTOK", "700"))
PROMPTS = [
    "A train leaves at 9:40 and travels 237 km at 79 km/h, waits 18 minutes, then travels 154 km at 88 km/h. When does it arrive?",
    "How many distinct ways can you make change for 1 dollar using pennies, nickels, dimes and quarters? Reason step by step.",
    "Is 2^61 - 1 prime? Explain your reasoning briefly.",
    "Write a short proof that the square root of 2 is irrational.",
    "Write a Python function that merges two sorted lists, with a docstring and tests.",
    "Explain how a Bloom filter works and derive its false-positive rate.",
    "Write a Rust function that parses an ISO-8601 date string into (year, month, day) without external crates, with error handling.",
    "A farmer has 120 m of fence and wants a rectangular pen against a straight wall. What dimensions maximise the area? Show the calculus.",
]
THINK = {"on": {}, "off": {"reasoning_effort": "none"}}
THINK = {k: v for k, v in THINK.items() if k in os.environ.get("BX_THINK", "on,off").split(",")}


def one(p, think, disable_mtp):
    body = {"model": MODEL, "messages": [{"role": "user", "content": p}], "max_tokens": MAXTOK,
            "temperature": 0, "stream": True, "stream_options": {"include_usage": True},
            "disable_mtp": disable_mtp, **THINK[think]}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = None; R = []; C = []; usage = {}
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            line = line.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            ev = json.loads(line[5:])
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices") or []:
                dl = ch.get("delta", {})
                rt = dl.get("reasoning_content") or dl.get("reasoning")
                if rt:
                    R.append(rt)
                elif dl.get("content"):
                    C.append(dl["content"])
                if (rt or dl.get("content")) and first is None:
                    first = time.time()
    end = time.time()
    return {"text": "".join(R) + "\n<<>>\n" + "".join(C), "tokens": usage.get("completion_tokens", 0),
            "t0": t0, "first": first or end, "end": end}


def run_set(conc, disable_mtp):
    out = {}
    for think in THINK:
        jobs = [(i, p) for i, p in enumerate(PROMPTS)]
        t = time.time()
        with ThreadPoolExecutor(conc) as ex:
            rs = list(ex.map(lambda ip: one(ip[1], think, disable_mtp), jobs))
        wall = time.time() - t
        toks = sum(r["tokens"] for r in rs)
        out[think] = {"wall": wall, "tokens": toks, "agg_tok_s": toks / wall, "rows": rs}
        print(f"C={conc} think={think} serial={disable_mtp} wall={wall:.1f}s tokens={toks} agg={toks / wall:.1f} tok/s "
              + " ".join(hashlib.sha256(r["text"].encode()).hexdigest()[:8] for r in rs), flush=True)
    return out


def cmp(ref_path, paths):
    ref = json.load(open(ref_path))["runs"]
    for p in paths:
        run = json.load(open(p))
        cells = []
        for think in THINK:
            for i, (a, b) in enumerate(zip(ref[think]["rows"], run["runs"][think]["rows"])):
                ta, tb = a["text"], b["text"]
                if ta == tb:
                    cells.append(f"{think}{i}:=")
                else:
                    d = next((k for k in range(min(len(ta), len(tb))) if ta[k] != tb[k]), min(len(ta), len(tb)))
                    cells.append(f"{think}{i}:X@{d}")
        same = sum(c.endswith("=") for c in cells)
        print(f"{p}: {same}/{len(cells)} identical  " + " ".join(cells), flush=True)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "cmp":
        cmp(sys.argv[2], sys.argv[3:])
        sys.exit(0)
    out = sys.argv[2]
    if mode == "alone":
        res = run_set(1, "--spec" not in sys.argv)
        meta = {"mode": "alone", "c": 1}
    else:
        c = int(sys.argv[3])
        res = run_set(c, "--serial" in sys.argv)
        meta = {"mode": "conc", "c": c, "serial": "--serial" in sys.argv}
    json.dump({**meta, "runs": res}, open(out, "w"))
