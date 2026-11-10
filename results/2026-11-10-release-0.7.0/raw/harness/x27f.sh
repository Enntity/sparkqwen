#!/usr/bin/env bash
# 27B default profile on this Spark: timed runs on the fresh server, then checks and exactness, then stop.
Q=~/qual-20261110; T=27b-final-default; CO=~/q27/sparkqwen-sscan; D=$Q/$T
cd $Q; PROFILE=27b ./arm.sh $T $CO 27b greedy bench rig1 rig2 keep > $T.out 2>&1
NOSTART=1 PROFILE=27b ./arm.sh $T $CO 27b checks c8 keep >> $T.out 2>&1
mkdir -p $D/exact && cd $D/exact
python3 ~/q27/decode_probe.py rc 2 > probe.log 2>&1
(BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone ser.json && BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone spec.json --spec && BX_MAXTOK=250 python3 ~/q27/ba/bx.py conc c8.json 8; BX_MAXTOK=250 python3 ~/q27/ba/bx.py cmp ser.json spec.json c8.json) > bx.log 2>&1
python3 ~/q27/mixfix/mix.py mix.json > mix.log 2>&1
docker logs atlas-sparkqwen-27b 2>&1 | sed "s/\x1b\[[0-9;]*m//g" > $D/server.log
echo "mixed forwards: $(grep -c 'Mixed forward: prefill' $D/server.log) ctx_ptr errors: $(grep -c 'requires nonzero ctx_ptr' $D/server.log) failed copies: $(grep -c 'copy_d2d_async failed' $D/server.log) ERROR lines: $(grep -c ' ERROR ' $D/server.log)" > errors.txt
cd $CO && ./start.sh --model 27b stop > /dev/null 2>&1
echo X27_DONE
