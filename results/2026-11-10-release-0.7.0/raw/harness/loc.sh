#!/usr/bin/env bash
# Which step leaves the server slower at C4/C8? One server start; RigMark's concurrency cell after each step.
Q=~/qual-20261110; T=fn-rc-locate; D=$Q/$T; K=$Q/sparkqwen/bench; export SQ_MODEL=qwen3.8-flash-next-atlas
cd $Q; MODE=spark PROFILE=8x262k ./arm.sh $T $Q/sparkqwen fn keep > loc.out 2>&1
cd $D
conc() { (cd $Q/rigmark && ./rigmark run --base-url http://127.0.0.1:8893 --model $SQ_MODEL --label loc-$1 --comparison-id sparkqwen-070-locate-$1 \
  --metadata $D/metadata.json --runs 1 --decode-tokens 64 --skip-prefill --concurrency 4,8 --concurrency-runs 2 \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' --output $D/conc-$1.json) > conc-$1.log 2>&1
  echo "$(date -u +%T) after $1: $(grep AGGREGATE $Q/rigmark/*.card.txt $D/conc-$1*.card.txt 2>/dev/null | tail -1 | sed 's/.*AGGREGATE//; s/│//')"; }
conc fresh
python3 $K/lp_dump.py $T > /dev/null 2>&1; conc lp_dump
python3 $K/tool_probe.py $T > /dev/null 2>&1; conc tool_probe
python3 $K/quality_probe.py $T > /dev/null 2>&1; conc quality_probe
SQ_CONC=1,2,4,8 python3 $K/sq_bench.py $T decode prefill conc warm > /dev/null 2>&1; conc sq_bench
python3 $K/greedy_eq.py run $T-c8 8 > /dev/null 2>&1; conc greedy_c8
python3 $K/greedy_eq.py run $T-c8p 8 --prefix > /dev/null 2>&1; conc greedy_c8p
docker logs atlas-sparkqwen-rank0 > rank0.log 2>&1
