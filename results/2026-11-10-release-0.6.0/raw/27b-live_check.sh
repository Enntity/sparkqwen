#!/usr/bin/env bash
# Live check of the LLooM-managed 27B runtime after the 0.6.0 deploy.
set -u
cd ~/q27/sscan/live
C=lloom-atlas-sparkqwen-27b
date -u +"%FT%TZ start"
docker inspect $C --format "image {{.Image}} version {{index .Config.Labels \"org.opencontainers.image.version\"}} install-tree {{index .Config.Labels \"io.enntity.sparkqwen.install-tree\"}}"
docker exec $C /usr/local/bin/spark --version 2>/dev/null | head -1
python3 ~/q27/decode_probe.py live 2 || echo "probe failed"
BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone ser.json && BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone spec.json --spec && BX_MAXTOK=250 python3 ~/q27/ba/bx.py conc c8.json 8
BX_MAXTOK=250 python3 ~/q27/ba/bx.py cmp ser.json spec.json c8.json
python3 ~/q27/sscan/long.py long.json || echo "long failed"
python3 ~/q27/sscan/cmp_long.py long.json
docker logs $C 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -E "ATLAS_ATTN_SHARED_SCAN|shared-scan attention workspace|warm context" | sed -E "s/^[0-9T:.-]+Z +//" | cut -c1-160
docker logs $C 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep "Done:" | sed -E "s/.*Done: ([0-9]+) tokens \(([a-z]+)\) ([0-9.]+) tok\/s.*serial=([0-9.]+).*tok_step=([0-9.]+).*/\1 \3 \5 \4/" | awk "{printf \"  %s tok  %.1f tok/s  tok_step %.3f  step %.1f ms  serial %s\n\", \$1,\$2,\$3,1000*\$3/\$2,\$4}" | tail -12
date -u +"%FT%TZ done"; touch DONE
