#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Needle gate: needle_gate.py run TAG [CONC] | needle_gate.py compare TAG_A TAG_B

60 deterministic two-hop retrievals (key -> code in table A, code -> value in a
shuffled table B), temperature 0, thinking off, at four context sizes (~24K, ~48K,
~80K, ~128K prompt tokens, 15 items each), the key placed at a spread of depths so
the hops cross prefill chunk boundaries. The release gate for lossy opt-ins
(all-to-all o_proj, E4M3 paths): compare against the same image without it.
run writes ./needle-TAG.jsonl; compare prints both scores, the discordant pairs
and an exact two-sided McNemar p-value. Env NEEDLE_URL / NEEDLE_MODEL point it at
another server or served model name (defaults: the TP-4 GLM server); NEEDLE_MAX_TOKENS
raises the 24-token answer budget for a server that reasons before answering
(GLM-5.3 at Reasoning Effort Max). NEEDLE_THINK=<effort> (e.g. low) sends that reasoning_effort
instead of thinking off (the budget then defaults to 2048); only the content after the reasoning is graded."""
import json, math, os, random, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = os.environ.get("NEEDLE_URL", "http://127.0.0.1:8893/v1/chat/completions")
MODEL = os.environ.get("NEEDLE_MODEL", "glm-5.3-flash-atlas")
THINK = os.environ.get("NEEDLE_THINK")
MAX_TOKENS = int(os.environ.get("NEEDLE_MAX_TOKENS", "2048" if THINK else "24"))
SIZES = [900, 1800, 3000, 4800]  # table rows: ~24K, ~48K, ~80K, ~128K prompt tokens
PER_SIZE = 15


def ask(prompt, max_tokens):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0, "top_p": 1,
            "chat_template_kwargs": {"reasoning_effort": THINK} if THINK else {"enable_thinking": False}}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    msg = json.loads(urllib.request.urlopen(req, timeout=1800).read())["choices"][0]["message"]
    return msg.get("content") or ""


def item(rng, rows, depth):
    keys, seen = [], set()
    while len(keys) < rows:
        k = f"k{rng.randrange(10**6):06d}"
        if k not in seen:
            seen.add(k); keys.append(k)
    codes = [f"c{rng.randrange(10**6):06d}" for _ in keys]
    vals = [f"{rng.randrange(10**8):08d}" for _ in keys]
    i = min(rows - 1, int(depth * rows))
    a = "\n".join(f"{k} -> {c}" for k, c in zip(keys, codes))
    order = list(range(rows)); rng.shuffle(order)
    b = "\n".join(f"{codes[j]} = {vals[j]}" for j in order)
    q = (f"Table A maps keys to codes:\n{a}\n\nTable B maps codes to values:\n{b}\n\n"
         f"Find the code for key {keys[i]} in Table A, then that code's value in Table B. "
         "Reply with the 8-digit value only.")
    return {"rows": rows, "depth": round(depth, 3), "b_pos": order.index(i) / rows, "q": q, "answer": vals[i]}


def items():
    rng = random.Random(int(os.environ.get("NEEDLE_SEED", "20261018")))
    out = []
    for rows in SIZES:
        for n in range(PER_SIZE):
            out.append(item(rng, rows, (n + 0.5) / PER_SIZE))
    return out


def run(tag, conc):
    its = items()

    def one(it):
        o = ask(it["q"], MAX_TOKENS)
        return {"tag": tag, "rows": it["rows"], "depth": it["depth"], "b_pos": round(it["b_pos"], 3),
                "ok": it["answer"] in o, "answer": it["answer"], "out": o[-60:]}

    with ThreadPoolExecutor(conc) as ex:
        res = list(ex.map(one, its))
    with open(f"needle-{tag}.jsonl", "w") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    by = {}
    for r in res:
        by.setdefault(r["rows"], []).append(r["ok"])
    print(f"{tag} needle60: {sum(r['ok'] for r in res)}/{len(res)}  by size: " +
          " ".join(f"{rows}:{sum(v)}/{len(v)}" for rows, v in sorted(by.items())))


def compare(a, b):
    ra = [json.loads(l) for l in open(f"needle-{a}.jsonl")]
    rb = [json.loads(l) for l in open(f"needle-{b}.jsonl")]
    only_a = sum(1 for x, y in zip(ra, rb) if x["ok"] and not y["ok"])
    only_b = sum(1 for x, y in zip(ra, rb) if y["ok"] and not x["ok"])
    n = only_a + only_b
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(only_a, only_b) + 1)) / 2 ** n) if n else 1.0
    print(f"{a} {sum(x['ok'] for x in ra)}/60  {b} {sum(y['ok'] for y in rb)}/60  "
          f"only {a}: {only_a}  only {b}: {only_b}  McNemar p={p:.3f}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4)
    else:
        compare(sys.argv[2], sys.argv[3])
