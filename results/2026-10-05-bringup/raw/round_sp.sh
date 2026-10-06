#!/usr/bin/env bash
# round_sp.sh BIN -- SP prefill: hash-diff exactness check (SP=0 vs SP=1), then TTFT with SP (exact, + TC2R).
set -uo pipefail
B=$1; D=$HOME/sparkqwen-dev; cd "$D"
S="--speculative --num-drafts 3"
prompt16k() { python3 - <<'PY'
import json,random,urllib.request,time
r=random.Random(16)
c="\n".join(f"Entry {i}: station-{r.randint(1000,9999)} logs code {r.randint(100000,999999)} on shelf {r.choice('ABCDEFGH')}{r.randint(1,40)}." for i in range(590))
b={"model":"qwen3.8-flash-next-atlas","messages":[{"role":"user","content":c+"\n\nWhich shelf holds Entry 3?"}],"max_tokens":8,"temperature":0}
t=time.time(); d=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8893/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900)); print("prompt",d["usage"]["prompt_tokens"],"ttft-ish",round(time.time()-t,2), repr(d["choices"][0]["message"].get("content")))
PY
}
for sp in 0 1; do
  (cat best3.list; printf "ATLAS_QWEN4EXP_PREFILL_SP=$sp\nATLAS_QWEN4EXP_PREFILL_SP_CHECK=1\n") > spchk$sp.list
  SEQS=8 EXTRA="$S" ENVF=spchk$sp.list bash go_sq_tp.sh SPchk$sp "$B" none > SPchk$sp.out 2>&1
  grep -E "up after|FAILED" SPchk$sp.out; prompt16k
  docker logs atlas-sparkglm-rank0 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -aoE "QWEN4EXP_SP_CHECK .*" | sed -E "s/ sp=[^ ]+//" > spchk$sp.rank0.txt
  ssh -n <rank1-cable-ip> "docker logs atlas-sparkglm-rank1 2>&1" | sed "s/\x1b\[[0-9;]*m//g" | grep -aoE "QWEN4EXP_SP_CHECK .*" | sed -E "s/ sp=[^ ]+//" > spchk$sp.rank1.txt
  echo "sp=$sp lines: $(wc -l < spchk$sp.rank0.txt) / $(wc -l < spchk$sp.rank1.txt)"
done
echo "## SP exactness (diff must be empty)"
diff spchk0.rank0.txt spchk1.rank0.txt | head -6; diff spchk0.rank1.txt spchk1.rank1.txt | head -6; echo "## end diff"
(cat best3.list; echo ATLAS_QWEN4EXP_PREFILL_SP=1) > best3sp.list; (cat best3sp.list; echo ATLAS_QWEN4EXP_PREFILL_QSA_TC2R=1) > best3spt.list
for a in best3sp:PSP best3spt:PSPt; do e=${a%%:*}; n=${a##*:}; SEQS=8 EXTRA="$S" ENVF=$e.list bash go_sq_tp.sh $n "$B" prefill > $n.out 2>&1; python3 lp_dump.py $n > /dev/null 2>&1; echo "## $n"; grep -E "up after|FAILED|^prefill" $n.out; done
echo "## PSP vs P2 prompt logprobs (HC+SP exact => identical)"; python3 lp_dump.py compare P2 PSP | tail -4
