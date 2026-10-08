#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""e2e_c1.py TAG -- the 8 e2e_eq prompts sent ONE AT A TIME (C1), thinking low, 320 tokens; writes e2e-TAG.json (compare with e2e_eq.py compare)."""
import json, os, sys, urllib.request
sys.argv = [sys.argv[0], sys.argv[1]]
import importlib.util
spec = importlib.util.spec_from_file_location("e", os.path.expanduser("~/sparkqwen-dev/e2e_eq.py"))
src = open(spec.origin).read().split("with ThreadPoolExecutor(4)")[0]
ns = {"__name__": "x"}; exec(compile(src.replace('if sys.argv[1] == "compare":', 'if False:'), "e2e", "exec"), ns)
out = [ns["one"](p) for p in ns["P"]]
json.dump(out, open(os.path.expanduser(f"~/sparkqwen-dev/e2e-{sys.argv[1]}.json"), "w"))
print(sys.argv[1], "done", len(out))
