#!/usr/bin/env python3
"""cmp_long.py ARM.json... : t08 serial vs speculative inside each arm, speeds, and arm vs arm."""
import json, sys
def d(a, b):
    return next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None if len(a) == len(b) else min(len(a), len(b)))
arms = {p: json.load(open(p)) for p in sys.argv[1:]}
for p, rows in arms.items():
    t08 = [r for r in rows if r["turn"] == "t08"]
    full, ser, again = t08[0], t08[1], t08[2]
    same = ser["R"] == again["R"] and ser["C"] == again["C"]
    print(f"{p}:")
    print(f"  t08 serial vs speculative, same start, 250 tokens: {'IDENTICAL' if same else 'DIFFERENT at reasoning char ' + str(d(ser['R'], again['R']))} ({len(ser['R'])} / {len(again['R'])} reasoning chars; serial {ser['decode_tok_s']} tok/s)")
    print(f"  t08 first run (from t07's checkpoint) vs second (from its own): {'same first 250 tokens' if full['R'].startswith(again['R']) else 'part at reasoning char ' + str(d(full['R'], again['R']))}")
    for r in rows:
        if not r["serial"] and r["tokens"] > 1: print(f"  {r['turn']}: {r['tokens']} tok, {r['decode_tok_s']} tok/s, ttft {r['ttft_s']} s")
