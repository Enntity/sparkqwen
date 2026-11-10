#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""evict_probe.py TAG [CONVS=12] [RECORDS=600]: push conversations out of the prefix cache, then return to them.

Turn 1 of every conversation is cold and sequential; with a small diagnostic pool the later ones evict the earlier
ones. Turn 2 is then asked of conversations 0-2 (evicted by then) and of the last one (still resident). Every answer's
text and token count are recorded (greedy, 96 tokens; token logprobs too where the server streams them) so two runs
can be compared exactly: one with the disk prefix tier, one
without (which recomputes the evicted prompts). Writes ./evict-TAG.json. SQ_URL / SQ_MODEL select the server."""
import json, os, random, sys, time, urllib.request
URL = os.environ.get("SQ_URL", "http://127.0.0.1:8893") + "/v1/chat/completions"
MODEL = os.environ.get("SQ_MODEL", "qwen3.8-flash-next-atlas")
tag = sys.argv[1]; C = int(sys.argv[2]) if len(sys.argv) > 2 else 12; R = int(sys.argv[3]) if len(sys.argv) > 3 else 600


def doc(c):
    rng = random.Random(1000 + c)
    rows = [(i, rng.randint(100000, 999999), rng.randint(1, 99)) for i in range(R)]
    head = f"Ledger {c}-{rng.randint(1000, 9999)}\n"
    return head + "\n".join(f"Record {i}: unit-{c:02d}-{i:05d} has access code {k} and owner team-{t}." for i, k, t in rows), rows


def chat(msgs):
    body = {"model": MODEL, "max_tokens": 96, "temperature": 0, "stream": True, "stream_options": {"include_usage": True},
            "logprobs": True, "chat_template_kwargs": {"enable_thinking": False}, "messages": msgs}
    t = time.time(); ttft = None; text = ""; ids = []; usage = {}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            d = json.loads(line[5:]); usage = d.get("usage") or usage
            for ch in d.get("choices", []):
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece and ttft is None:
                    ttft = time.time() - t
                text += piece
                for lp in ((ch.get("logprobs") or {}).get("content") or []):
                    ids.append([lp.get("token"), round(lp.get("logprob", 0.0), 5)])
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    return text, ids, round(ttft or -1, 2), usage.get("prompt_tokens"), cached, usage.get("completion_tokens")


hist, out = {}, []
for c in range(C):
    text, rows = doc(c); i = (37 * c + 11) % R
    msgs = [{"role": "user", "content": text + f"\n\nWhat is the access code and owner of unit-{c:02d}-{i:05d}? "
             "Answer in one sentence, then list the three records after it."}]
    a, ids, ttft, n, cached, m = chat(msgs)
    hist[c] = (msgs + [{"role": "assistant", "content": a}], rows)
    out.append({"conv": c, "turn": 1, "ttft": ttft, "prompt": n, "cached": cached, "completion": m, "correct": str(rows[i][1]) in a,
                "text": a, "ids": ids})
    print({k: v for k, v in out[-1].items() if k not in ("ids", "text")}, flush=True)
for c in (0, 1, 2, C - 1):
    msgs, rows = hist[c]; i = (53 * c + 29) % R
    a, ids, ttft, n, cached, m = chat(msgs + [{"role": "user", "content": f"And unit-{c:02d}-{i:05d}? Same format."}])
    out.append({"conv": c, "turn": 2, "ttft": ttft, "prompt": n, "cached": cached, "completion": m, "correct": str(rows[i][1]) in a,
                "text": a, "ids": ids})
    print({k: v for k, v in out[-1].items() if k not in ("ids", "text")}, flush=True)
json.dump(out, open(f"evict-{tag}.json", "w"), indent=1)
print(f"{tag}: {sum(o['correct'] for o in out)}/{len(out)} correct; turn-2 TTFT", [o["ttft"] for o in out if o["turn"] == 2])
