#!/usr/bin/env python3
"""Replay real OMP turns at ~210K against a local Atlas server, greedy. Stdlib only.

long.py OUT.json [ctl] : prime t00, t06 and t07 speculative, then t08
speculative, serial (disable_mtp, 250 tokens) and speculative again (250). Text is collected per channel, so
it does not depend on how the stream was chunked.
"""
import json, sys, time, urllib.request, os
OUT = sys.argv[1]
B = os.path.expanduser("~/q27/warmctx/bodies")
URL = "http://127.0.0.1:8893/v1/chat/completions"

def send(turn, max_tokens, serial=False):
    b = json.load(open(f"{B}/{turn}.json")); b["model"] = "qwen3.8-27b-atlas"
    b.update(max_tokens=max_tokens, temperature=0)
    if serial: b["disable_mtp"] = True
    req = urllib.request.Request(URL, json.dumps(b).encode(), {"Content-Type": "application/json"})
    t0 = time.time(); first = last = None; usage = None; R = []; C = []; T = {}
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
                for tc in dl.get("tool_calls") or []:
                    f = tc.get("function", {}); cur = T.setdefault(tc.get("index", 0), ["", ""])
                    cur[0] += f.get("name") or ""; cur[1] += f.get("arguments") or ""; got = True
                if got:
                    last = time.time(); first = first or last
    n = usage["completion_tokens"] if usage else 0
    row = dict(turn=turn, serial=serial, tokens=n, prompt=usage and usage["prompt_tokens"], ttft_s=round((first or time.time()) - t0, 2),
               decode_tok_s=round((n - 1) / (last - first), 2) if n > 1 and last > first else None,
               R="".join(R), C="".join(C), T=[T[k] for k in sorted(T)])
    print(json.dumps({k: v for k, v in row.items() if k not in ("R", "C", "T")}), flush=True)
    return row

# t08 is ~630 reasoning tokens. Its first speculative run starts from t07's
# checkpoint; the serial run and the second speculative run both start from
# t08's own, so those two compare like for like.
if len(sys.argv) > 2 and sys.argv[2] == "ctl":
    rows = [send("t07", 1)]
else:
    rows = [send("t00", 1), send("t06", 700), send("t07", 700)]
rows += [send("t08", 700), send("t08", 250, serial=True), send("t08", 250)]
json.dump(rows, open(OUT, "w"), indent=1)
