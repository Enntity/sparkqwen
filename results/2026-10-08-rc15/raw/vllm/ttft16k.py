import json,random,time,urllib.request,sys
words=open("/usr/share/dict/words").read().split() if __import__("os").path.exists("/usr/share/dict/words") else [f"w{i}" for i in range(50000)]
for seed in (1,2,3):
    r=random.Random(seed*7919+int(time.time()))
    text=" ".join(r.choice(words) for _ in range(7150))
    body={"model":"qwen3.8-flash-next","messages":[{"role":"user","content":text+"\nSummarize."}],"max_tokens":1,"temperature":0,"stream":True,"stream_options":{"include_usage":True},"chat_template_kwargs":{"enable_thinking":False}}
    req=urllib.request.Request("http://127.0.0.1:8888/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    t0=time.time(); first=None; usage=None
    with urllib.request.urlopen(req) as resp:
        for line in resp:
            line=line.decode().strip()
            if not line.startswith("data:") or line=="data: [DONE]": continue
            d=json.loads(line[5:])
            if d.get("usage"): usage=d["usage"]
            if first is None and d.get("choices") and (d["choices"][0]["delta"].get("content") or d["choices"][0]["delta"].get("reasoning_content") or d["choices"][0]["delta"].get("reasoning")): first=time.time()
    t1=time.time()
    pt=usage["prompt_tokens"]; tt=(first or t1)-t0; print(f"prompt_tokens={pt} ttft={tt:.3f}s total={t1-t0:.3f}s prefill_tok_s={pt/tt:.0f}")
