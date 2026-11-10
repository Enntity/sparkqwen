#!/usr/bin/env bash
# One SparkQwen arm: start it from CHECKOUT, run STEPs, keep receipts in ~/qual-20261110/TAG, stop.
# usage: arm.sh TAG CHECKOUT fn|27b STEP...    settings from the environment: MODE PROFILE DRAFTER IMAGE WORKER
#   STEP: checks | bench | greedy | c8 | rig1 | rig2 | keep (leave it running); NOSTART=1 uses the running server
set -u
T=$1; CO=$2; KIND=$3; shift 3
Q=~/qual-20261110; D=$Q/$T; mkdir -p "$D"; K=$CO/bench
if [[ $KIND == fn ]]; then export SQ_MODEL=qwen3.8-flash-next-atlas; C0=atlas-sparkqwen-rank0; W=${WORKER:-10.100.112.2}; START=(./start.sh)
else export SQ_MODEL=qwen3.8-27b-atlas; C0=atlas-sparkqwen-27b; W=; START=(./start.sh --model 27b); fi
say() { echo "$(date -u +%FT%TZ) $*" | tee -a "$D/arm.log"; }
cd "$CO"
say "up ($KIND MODE=${MODE:-} PROFILE=${PROFILE:-} DRAFTER=${DRAFTER:-} IMAGE=${IMAGE:-})"
if [[ ${NOSTART:-0} != 1 ]]; then
  "${START[@]}" > "$D/start.log" 2>&1; rc=$?; say "start exit $rc: $(tail -1 "$D/start.log" | cut -c1-160)"
  [[ $rc == 0 ]] || { "${START[@]}" stop >> "$D/start.log" 2>&1; exit 1; }
fi
"${START[@]}" status > "$D/status.txt" 2>&1
ident() { docker inspect "$1" | python3 -c '
import json,sys;c=json.load(sys.stdin)[0];l=c["Config"]["Labels"]
print(json.dumps({"container":c["Name"],"image":c["Config"]["Image"],"imageId":c["Image"],"version":l.get("org.opencontainers.image.version"),
 "installTree":l.get("io.enntity.sparkqwen.install-tree"),"env":sorted(e for e in c["Config"]["Env"] if e.startswith(("SPARKQWEN_","ATLAS_","FABRIC_","NCCL_")))},indent=1))'
  docker exec "$1" sha256sum /usr/local/bin/spark; }
ident "$C0" > "$D/identity-rank0.json" 2>&1
[[ -z $W ]] || ssh -o BatchMode=yes "$W" "$(declare -f ident); ident atlas-sparkqwen-rank1" > "$D/identity-rank1.json" 2>&1
nvidia-smi --query-gpu=clocks.sm,clocks.max.sm,temperature.gpu --format=csv,noheader > "$D/gpu-before.txt"
python3 $Q/meta.py "$D" $KIND "$CO" > "$D/meta.log" 2>&1 || say "metadata failed: $(tail -1 "$D/meta.log")"
cd "$D"
for step in "$@"; do
  say "step $step"
  case $step in
    checks) for s in "greedy_eq.py run $T" "lp_dump.py $T" "tool_probe.py $T" "quality_probe.py $T"; do
              n=${s%%.py*}; python3 $K/$s > $n.log 2>&1; echo "$n $?" >> exits; done ;;
    bench)  SQ_CONC=1,2,4,8 python3 $K/sq_bench.py $T decode prefill conc warm > sq_bench.log 2>&1; echo "sq_bench $?" >> exits ;;
    greedy) python3 $K/greedy_eq.py run $T > greedy_eq.log 2>&1; echo "greedy_eq $?" >> exits ;;
    c8)     python3 $K/greedy_eq.py run $T-c8 8 > greedy_eq-c8.log 2>&1; echo "greedy_c8 $?" >> exits
            python3 $K/greedy_eq.py run $T-c8p 8 --prefix > greedy_eq-c8p.log 2>&1; echo "greedy_c8p $?" >> exits ;;
    rig1|rig2) r=${step#rig}
            $Q/tele.sh start "$D/rigmark-$r" $W
            python3 $Q/run_rigmark.py --model $SQ_MODEL --out "$D/rigmark-$r/run" --metadata "$D/metadata.json" --round $r \
              --comparison sparkqwen-070-20261110 --harness $Q/rigmark >> rig.log 2>&1; echo "rig$r $?" >> exits
            $Q/tele.sh stop "$D/rigmark-$r" $W ;;
    keep)   say "left running"; exit 0 ;;
  esac
done
docker logs "$C0" > "$D/rank0.log" 2>&1
[[ -z $W ]] || ssh -o BatchMode=yes "$W" docker logs atlas-sparkqwen-rank1 > "$D/rank1.log" 2>&1
nvidia-smi --query-gpu=clocks.sm,clocks.max.sm,temperature.gpu --format=csv,noheader > "$D/gpu-after.txt"
cd "$CO"; "${START[@]}" stop >> "$D/start.log" 2>&1
say "done: $(tr '\n' ' ' < "$D/exits" 2>/dev/null)"
