#!/usr/bin/env python3
"""A long prompt joining two decoding requests, against a local Atlas server. Greedy. Stdlib only.

mix.py OUT.json
  P    : a ~20K-token prompt. Primed cold (1 token), then alone speculative, alone serial,
         then again while D1 and D2 decode (its last prefill chunk continues beside two decoders).
  P2   : a second ~20K-token prompt sent cold while D3 and D4 decode.
  D1-4 : short prompts with long answers; D1 and D2 are also run alone, serial.
"""
import glob, hashlib, json, os, sys, threading, time, urllib.request
OUT = sys.argv[1]
URL = "http://127.0.0.1:8893/v1/chat/completions"
SRC = os.path.expanduser("~/q27/atlas-sscan/crates")

def corpus(sub, chars):
    out = []; n = 0
    for f in sorted(glob.glob(f"{SRC}/{sub}/*.rs")):
        t = open(f).read(); out.append(f"// FILE {os.path.basename(f)}\n{t}"); n += len(t)
        if n >= chars: break
    return "\n".join(out)[:chars]

LONG = {
    "P": corpus("spark-server/src/scheduler", 70000) + "\n\nList the ten most important functions above, one line each, with what each does.",
    "P2": corpus("spark-model/src/layers", 70000) + "\n\nList the ten most important functions above, one line each, with what each does.",
}
SHORT = {
    "D1": "Write a careful 500-word explanation of how a B-tree insert splits a full node, with a worked example.",
    "D2": "Write a Python class implementing an LRU cache with O(1) get and put, with docstrings and a short test.",
    "D3": "Explain in about 500 words how TCP congestion control moves between slow start and congestion avoidance.",
    "D4": "Write a Rust function that merges k sorted vectors using a binary heap, with comments and a unit test.",
}

def send(name, max_tokens, serial=False, started=None, tag=""):
    b = dict(model="qwen3.8-27b-atlas", messages=[dict(role="user", content=(LONG | SHORT)[name])],
             max_tokens=max_tokens, temperature=0, stream=True, stream_options=dict(include_usage=True))
    if serial: b["disable_mtp"] = True
    req = urllib.request.Request(URL, json.dumps(b).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; usage = None; R = []; C = []
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            if not line.startswith(b"data:"): continue
            d = line[5:].strip()
            if d == b"[DONE]": break
            e = json.loads(d)
            if e.get("usage"): usage = e["usage"]
            for c in e.get("choices", []):
                dl = c.get("delta", {}); got = False
                rt = dl.get("reasoning_content") or dl.get("reasoning")
                if rt: R.append(rt); got = True
                if dl.get("content"): C.append(dl["content"]); got = True
                if got:
                    last = time.time()
                    if first is None:
                        first = last
                        if started is not None: started.set()
    n = usage["completion_tokens"] if usage else 0
    text = "".join(R) + "\x00" + "".join(C)
    row = dict(name=name, tag=tag, serial=serial, tokens=n, prompt=usage and usage["prompt_tokens"],
               ttft_s=round((first or time.time()) - t0, 2),
               decode_tok_s=round((n - 1) / (last - first), 2) if n > 1 and last and last > first else None,
               chars=len(text) - 1, sha=hashlib.sha256(text.encode()).hexdigest()[:16], text=text)
    print(json.dumps({k: v for k, v in row.items() if k != "text"}), flush=True)
    return row

rows = []
def run(*a, **k): rows.append(send(*a, **k)); return rows[-1]

def beside(long_name, d_a, d_b, long_tokens, tag):
    """Start two decoders; once both stream, send the long prompt."""
    res = {}; ev = [threading.Event(), threading.Event()]
    def go(n, e): res[n] = send(n, 600, started=e, tag=tag)
    th = [threading.Thread(target=go, args=(d_a, ev[0])), threading.Thread(target=go, args=(d_b, ev[1]))]
    for t in th: t.start()
    for e in ev: e.wait(600)
    res[long_name] = send(long_name, long_tokens, tag=tag)
    for t in th: t.join()
    rows.extend(res[n] for n in (d_a, d_b, long_name))

run("P", 1, tag="prime")
run("P", 300, tag="alone")
run("P", 300, serial=True, tag="alone")
run("D1", 600, serial=True, tag="alone")
run("D2", 600, serial=True, tag="alone")
beside("P", "D1", "D2", 300, "warm-join")
beside("P2", "D3", "D4", 300, "cold-join")
json.dump(rows, open(OUT, "w"), indent=1)

def same(a, b): return "IDENTICAL" if a["text"] == b["text"] else f"DIFFERENT (first {next((i for i,(x,y) in enumerate(zip(a['text'], b['text'])) if x != y), min(len(a['text']), len(b['text'])))} of {len(a['text'])}/{len(b['text'])} chars agree)"
by = {(r["name"], r["tag"], r["serial"]): r for r in rows}
print("P alone speculative vs alone serial:", same(by[("P", "alone", False)], by[("P", "alone", True)]))
print("P joining two decoders vs alone serial:", same(by[("P", "warm-join", False)], by[("P", "alone", True)]))
print("D1 beside the join vs alone serial:", same(by[("D1", "warm-join", False)], by[("D1", "alone", True)]))
print("D2 beside the join vs alone serial:", same(by[("D2", "warm-join", False)], by[("D2", "alone", True)]))
