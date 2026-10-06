#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""agentic_probe.py TAG [CONV=4] [TURNS=5] -- agent-shaped serving probe (stdlib only).
CONV conversations share one ~20K-token system prompt (a salted registry); each runs TURNS user
turns (a lookup each), sequentially within a conversation and concurrently across conversations.
Records TTFT per turn, cached tokens, and whether each answer is correct. Thinking low, temp 0.
Writes ./agentic-TAG.json. SQ_URL (default http://127.0.0.1:8893) and SQ_MODEL select the server."""
import json, os, random, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
TAG = sys.argv[1]; CONV = int(sys.argv[2]) if len(sys.argv) > 2 else 4; TURNS = int(sys.argv[3]) if len(sys.argv) > 3 else 5
URL = os.environ.get("SQ_URL", "http://127.0.0.1:8893") + "/v1/chat/completions"
MODEL = os.environ.get("SQ_MODEL", "qwen3.8-flash-next-atlas")
r = random.Random(2026)
keys = [f"svc-{r.randrange(10**6):06d}" for _ in range(900)]
vals = {k: f"{r.randrange(10**6):06d}" for k in keys}
system = "You are an operations assistant. Reference registry follows.\n" + "\n".join(
    f"{k}: port {vals[k]} owner team-{r.randrange(100)} region {r.choice(['east','west','north','south'])}" for k in keys)

def ask(msgs):
    b = {"model": MODEL, "messages": msgs, "max_tokens": 300, "temperature": 0, "stream": True,
         "stream_options": {"include_usage": True}, "chat_template_kwargs": {"reasoning_effort": "low"}}
    t0 = time.time(); first = None; txt = []; usage = {}
    with urllib.request.urlopen(urllib.request.Request(URL, json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=600) as resp:
        for line in resp:
            line = line.strip()
            if not line.startswith(b"data:") or line == b"data: [DONE]":
                continue
            d = json.loads(line[5:]); usage = d.get("usage") or usage
            for c in d.get("choices", []):
                p = c.get("delta", {}).get("content") or ""
                if p or c.get("delta", {}).get("reasoning_content"):
                    first = first or time.time()
                txt.append(p)
    return round((first or time.time()) - t0, 2), (usage.get("prompt_tokens_details") or {}).get("cached_tokens"), "".join(txt).strip()

def conv(ci):
    rr = random.Random(ci); msgs = [{"role": "system", "content": system}]; rows = []
    for t in range(TURNS):
        k = rr.choice(keys)
        msgs.append({"role": "user", "content": f"What port does {k} use? Reply with the port number only."})
        ttft, cached, ans = ask(msgs)
        rows.append({"conv": ci, "turn": t, "ttft": ttft, "cached": cached, "ok": vals[k] in ans})
        msgs.append({"role": "assistant", "content": ans[-200:]})
    return rows

with ThreadPoolExecutor(CONV) as ex:
    allrows = [x for rs in ex.map(conv, range(CONV)) for x in rs]
json.dump(allrows, open(f"agentic-{TAG}.json", "w"), indent=1)
t0 = [x["ttft"] for x in allrows if x["turn"] == 0]; tn = sorted(x["ttft"] for x in allrows if x["turn"] > 0)
print(f"{TAG}: correct {sum(x['ok'] for x in allrows)}/{len(allrows)}; turn-0 TTFT {sorted(t0)}; turns 1+ TTFT median {tn[len(tn)//2]} max {tn[-1]}")
