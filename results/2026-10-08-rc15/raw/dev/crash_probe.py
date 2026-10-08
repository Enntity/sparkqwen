import json, sys, urllib.request, concurrent.futures as cf
U = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8893"
def req(p):
    b = {"model": "qwen3.8-flash-next-atlas", "prompt": p, "max_tokens": 4, "temperature": 0}
    try:
        r = urllib.request.urlopen(urllib.request.Request(U + "/v1/completions", json.dumps(b).encode(), {"Content-Type": "application/json"}), timeout=60)
        return "ok"
    except Exception as e: return "err:" + str(e)[:60]
ps = [[248056, 1234, 5678]] + [[100 + i, 200 + i, 300 + i] for i in range(5)]
with cf.ThreadPoolExecutor(6) as ex: print("burst:", list(ex.map(req, ps)))
print("alive after:", req([1, 2, 3]))
