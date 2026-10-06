#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""long_probe.py needle|exhaust -- 77K needle + warm follow-up, or 4 concurrent distinct ~100K prompts (KV exhaustion).
Needs a long-context profile (4x262k). SQ_URL (default http://127.0.0.1:8893) and SQ_MODEL select the server."""
import json, os, random, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
URL = os.environ.get("SQ_URL", "http://127.0.0.1:8893") + "/v1/chat/completions"
MODEL = os.environ.get("SQ_MODEL", "qwen3.8-flash-next-atlas")
def chat(msgs, mt):
    b = {"model": MODEL, "messages": msgs, "max_tokens": mt, "temperature": 0, "stream": True,
         "stream_options": {"include_usage": True}, "chat_template_kwargs": {"reasoning_effort": "low"}}
    t0 = time.time(); first = None; out = []; usage = {}
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=900) as resp:
            for line in resp:
                line = line.strip()
                if not line.startswith(b"data:") or line == b"data: [DONE]": continue
                d = json.loads(line[5:]); usage = d.get("usage") or usage
                if "error" in d: return {"error": str(d["error"])[:200]}
                for c in d.get("choices", []):
                    dl = c.get("delta", {}); p = (dl.get("content") or "") + (dl.get("reasoning_content") or "")
                    if p: first = first or time.time(); out.append(dl.get("content") or "")
    except Exception as e:
        return {"error": repr(e)[:200]}
    end = time.time(); n = usage.get("completion_tokens", 0)
    return {"prompt": usage.get("prompt_tokens"), "ttft": round((first or end) - t0, 1), "n": n,
            "tps": round((n - 1) / max(1e-6, end - first), 1) if first and n > 1 else 0, "ans": "".join(out).strip()[-40:]}
def registry(seed, n):
    r = random.Random(seed); keys = [f"k{r.randrange(10**6):06d}" for _ in range(n)]; vals = [f"{r.randrange(10**8):08d}" for _ in range(n)]
    i = r.randrange(n); reg = "\n".join(f"{k} => {v}" for k, v in zip(keys, vals))
    return f"{reg}\n\nWhat value is stored for key {keys[i]}? Reply with the 8-digit value only.", vals[i]
if sys.argv[1] == "needle":
    q, v = registry(77, 4300); r1 = chat([{"role": "user", "content": q}], 400)
    print("needle", r1, "ok", v in r1.get("ans", ""))
    r2 = chat([{"role": "user", "content": q}, {"role": "assistant", "content": v},
               {"role": "user", "content": "Now write 300 words about why registries like this are useful."}], 500)
    print("follow-up", {k: r2.get(k) for k in ("prompt", "ttft", "n", "tps", "error")})
else:
    jobs = [registry(1000 + s, 5600) for s in range(4)]
    with ThreadPoolExecutor(4) as ex:
        rs = list(ex.map(lambda j: chat([{"role": "user", "content": j[0]}], 400), jobs))
    for (q, v), r in zip(jobs, rs): print("exhaust", r, "ok", v in r.get("ans", ""))
