# SPDX-License-Identifier: AGPL-3.0-only
"""Summarize measured host pressure without treating old swap as new paging."""
import argparse
import json
import math
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--telemetry', required=True, type=Path)
p.add_argument('--start', required=True, type=float)
p.add_argument('--end', required=True, type=float)
p.add_argument('--out', type=Path)
p.add_argument('--max-gap-seconds', type=float, default=10)
p.add_argument('--require-capacity-pass', action='store_true',
               help='Fail on low memory or new swapout; omit for throughput-only reports')
a = p.parse_args()
assert all(math.isfinite(x) for x in (a.start, a.end, a.max_gap_seconds))
assert a.start <= a.end and a.max_gap_seconds > 0
rows = [json.loads(x) for x in a.telemetry.read_text().splitlines() if x.strip()]
fields = ('unix', 'MemAvailable', 'pswpout_pages', 'pswpin_pages', 'SwapTotal', 'SwapFree')
assert rows, 'Telemetry is empty'
assert all(isinstance(row[k], (int, float)) and not isinstance(row[k], bool)
           and math.isfinite(row[k]) for row in rows for k in fields), 'Nonfinite telemetry'
assert all(rows[i]['unix'] < rows[i + 1]['unix'] for i in range(len(rows) - 1)), 'Unordered telemetry'
hosts = {row.get('host') for row in rows}
assert len(hosts) == 1, 'Summarize each host separately'
before = [x for x in rows if x['unix'] <= a.start]
after = [x for x in rows if x['unix'] >= a.end]
assert before and after, 'Telemetry must bracket the entire measurement'
first, last = before[-1], after[0]
s = [x for x in rows if first['unix'] <= x['unix'] <= last['unix']]
assert all(x[k] >= 0 for x in s for k in fields[1:]), 'Negative telemetry counter'
assert all(s[i][k] <= s[i + 1][k] for i in range(len(s) - 1)
           for k in ('pswpout_pages', 'pswpin_pages')), 'Paging counters reset during measurement'
gaps = [s[i + 1]['unix'] - s[i]['unix'] for i in range(len(s) - 1)]
maximum_gap = max(gaps, default=0)
r = {'start_unix': a.start, 'end_unix': a.end, 'host': first.get('host'),
     'sample_first_unix': first['unix'], 'sample_last_unix': last['unix'],
     'samples': len(s), 'all_samples_finite': True,
     'maximum_sample_gap_s': maximum_gap, 'maximum_allowed_gap_s': a.max_gap_seconds,
     'telemetry_coverage_pass': maximum_gap <= a.max_gap_seconds,
     'minimum_available_bytes': min(x['MemAvailable'] for x in s),
     'swapout_pages_delta': last['pswpout_pages'] - first['pswpout_pages'],
     'swapin_pages_delta': last['pswpin_pages'] - first['pswpin_pages'],
     'swap_used_start_bytes': first['SwapTotal'] - first['SwapFree'],
     'swap_used_end_bytes': last['SwapTotal'] - last['SwapFree']}
r['capacity_memory_pass'] = (r['telemetry_coverage_pass']
                             and r['minimum_available_bytes'] >= 2 * 1024**3
                             and r['swapout_pages_delta'] == 0)
if a.out:
    a.out.write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps(r))
raise SystemExit(0 if r['telemetry_coverage_pass'] and
                 (not a.require_capacity_pass or r['capacity_memory_pass']) else 1)
