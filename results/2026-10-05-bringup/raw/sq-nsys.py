#!/usr/bin/env python3
"""nsys-marginal.py DB [top]: per-step time attributed to each kernel as end_i - max(prev_end, start_i) (PDL overlap removed)."""
import sqlite3, sys, collections
db=sqlite3.connect(sys.argv[1]); top=int(sys.argv[2]) if len(sys.argv)>2 else 30
names=dict(db.execute("select id,value from StringIds").fetchall())
rows=db.execute("select coalesce(shortName,demangledName),start,end,gridX,gridY,gridZ from CUPTI_ACTIVITY_KIND_KERNEL order by start").fetchall()
steps=sum(1 for r in rows if names.get(r[0],"")=="ple_gate")
agg=collections.defaultdict(lambda:[0.0,0]); last=rows[0][1]; idle=0.0; cls=collections.Counter(); cnt=collections.Counter()
for n,s,e,gx,gy,gz in rows:
    if s>last: idle+=s-last
    m=max(0,e-max(last,s)); last=max(last,e)
    nm=names.get(n,"")
    a=agg[nm[:50]]; a[0]+=m; a[1]+=1
    k="moe" if nm.startswith("moe_") else "small(<60us marginal)" if m<60e3 else "other-large"
    cls[k]+=m; cnt[k]+=1
span=rows[-1][2]-rows[0][1]
print(f"steps {steps:.1f} step {span/steps/1e6:.1f} ms idle {idle/steps/1e6:.1f} ms launches/step {len(rows)/steps:.0f}")
for k in cls: print(f"  class {k:24s} {cls[k]/steps/1e6:6.2f} ms/step {cnt[k]/steps:7.1f} launches/step  mean {cls[k]/cnt[k]/1e3:6.1f} us")
for k,(d,c) in sorted(agg.items(), key=lambda kv:-kv[1][0])[:top]: print(f"{d/steps/1e6:6.2f} ms {c/steps:6.1f}/st {d/c/1e3:7.1f} us  {k}")
