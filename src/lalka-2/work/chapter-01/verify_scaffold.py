#!/usr/bin/env python3
"""Verify scaffold UA against pl-numbered.txt for Tom 2 ch01.

Checks: per-unit <sup> parity, dash-prefix parity, Latin letters outside <sup>,
quote opener/closer parity, empty UA.
Usage: python3 verify_scaffold.py  (from bookcast root)
"""
import re
import sys

scaf = 'src/lalka-2/work/chapter-01/scaffold.txt'
pl_file = 'src/lalka-2/work/chapter-01/pl-numbered.txt'

# Extract PL text (strip [N] * **PL:** prefix)
pl_lines = [l for l in open(pl_file, encoding='utf-8').read().splitlines() if l.strip()]
pl = [re.sub(r'^\[\d+\] \* ', '', l) for l in pl_lines]

# Extract UA text (strip **UA:** prefix)
ua_lines = re.findall(r'^\*\*UA:\*\*\s*(.*)$', open(scaf, encoding='utf-8').read(), re.M)
ua = [re.sub(r'^\*\*UA:\*\*\s*', '', l) for l in open(scaf, encoding='utf-8').read().splitlines()
      if l.startswith('**UA:**')]

assert len(pl) == len(ua), f'count mismatch: pl={len(pl)} ua={len(ua)}'

bad = 0
filled = sum(1 for u in ua if u.strip())
empty = [i for i, u in enumerate(ua) if not u.strip()]

for i, (p, u) in enumerate(zip(pl, ua)):
    if not u.strip():
        continue
    psup = re.findall(r'<sup>(\d+)</sup>', p)
    usup = re.findall(r'<sup>(\d+)</sup>', u)
    if psup != usup:
        print(f'SUP {i}: pl={psup} ua={usup}')
        bad += 1
    if p.startswith('—') != u.startswith('—'):
        print(f'DASH {i}: pl={p[:40]} | ua={u[:40]}')
        bad += 1
    if re.findall(r'[A-Za-z]', re.sub(r'<sup>\d+</sup>', '', u)) and not re.findall(r'[A-Za-z]', re.sub(r'<sup>\d+</sup>', '', p)):
        print(f'LATIN {i}: ua={u[:70]}')
        bad += 1
    po, pc = p.count('«') + p.count('„'), p.count('»') + p.count('”') + p.count('“')
    uo, uc = u.count('«') + u.count('„'), u.count('»') + u.count('”') + u.count('“')
    if (po, pc) != (uo, uc):
        print(f'QUOTES {i}: pl=({po},{pc}) ua=({uo},{uc}) | ua={u[:60]}')
        bad += 1

# ranges for empty units
def ranges(idxs):
    if not idxs: return []
    out = []
    start = prev = idxs[0]
    for x in idxs[1:]:
        if x == prev + 1:
            prev = x
        else:
            out.append((start, prev))
            start = prev = x
    out.append((start, prev))
    return out

print(f'units={len(ua)} filled={filled} empty={len(empty)} problems={bad}')
if empty:
    r = ranges(empty)
    print('empty units:', ', '.join(f'{a}' if a == b else f'{a}-{b}' for a, b in r))
sys.exit(1 if bad else 0)
