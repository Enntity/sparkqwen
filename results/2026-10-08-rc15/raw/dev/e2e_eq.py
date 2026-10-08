#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""e2e_eq.py TAG | compare A B -- 8 greedy chat completions sent 4 at a time (thinking low, 320 tokens);
compare reports, per prompt, whether the texts match and where they first differ."""
import hashlib, json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

D = os.path.expanduser("~/sparkqwen-dev")
P = ["Write a calm, detailed essay about how lighthouses were staffed and maintained in the 1800s.",
     "Explain how sourdough starter cultures work, as plain paragraphs for a home baker.",
     "Write a Python function that parses ISO-8601 durations like P3DT4H5M into seconds, with tests.",
     "Return a JSON object describing three fictional planets with name, radius_km, moons and atmosphere.",
     "Describe the history of the printing press and its effect on literacy in Europe, in prose.",
     "Implement a thread-safe LRU cache in Rust with get and put, and explain the design briefly.",
     "List ten practical tips for reducing household energy use, each with a one-sentence reason.",
     "Explain how tides are caused by the moon and the sun, for a curious teenager, in paragraphs."]

if sys.argv[1] == "compare":
    a, b = (json.load(open(f"{D}/e2e-{t}.json")) for t in sys.argv[2:4])
    same = 0
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            same += 1
            continue
        n = next((j for j, (p, q) in enumerate(zip(x, y)) if p != q), min(len(x), len(y)))
        print(f"  prompt {i}: differ at char {n} of {len(x)}/{len(y)}: {x[max(0, n-30):n+30]!r} | {y[max(0, n-30):n+30]!r}")
    print(f"{sys.argv[2]} vs {sys.argv[3]}: {same}/{len(a)} identical")
    sys.exit()


def one(p):
    b = {"model": "qwen3.8-flash-next-atlas", "max_tokens": 320, "temperature": 0,
         "chat_template_kwargs": {"reasoning_effort": "low"}, "messages": [{"role": "user", "content": p}]}
    req = urllib.request.Request("http://127.0.0.1:8893/v1/chat/completions", json.dumps(b).encode(),
                                 {"Content-Type": "application/json"})
    m = json.load(urllib.request.urlopen(req, timeout=900))["choices"][0]["message"]
    return (m.get("reasoning_content") or "") + "\n---\n" + (m.get("content") or "")


with ThreadPoolExecutor(4) as ex:
    out = list(ex.map(one, P))
json.dump(out, open(f"{D}/e2e-{sys.argv[1]}.json", "w"))
print(sys.argv[1], [hashlib.sha1(t.encode()).hexdigest()[:6] for t in out])
