#!/usr/bin/env python3
"""Verify a ch20 UA draft part against the numbered PL source.

Usage: check_part.py <part-file> <start-unit>
Checks: line count (12), no empty lines, <sup> list parity, dash-prefix parity,
no Latin letters outside <sup>, balanced quote pairs («» and „“).
"""
import re
import sys

part_path, start = sys.argv[1], int(sys.argv[2])
exp_count = int(sys.argv[3]) if len(sys.argv) > 3 else 12  # short tail chunks pass explicit count
base = 'src/lalka/work/chapter-20'
pl = [re.sub(r'^\[\d+\] \* ', '', l)
      for l in open(f'{base}/pl-numbered.txt', encoding='utf-8') if l.strip()]
ua = open(part_path, encoding='utf-8').read().splitlines()

bad = 0
expected = exp_count
if len(ua) != expected:
    print(f'COUNT {len(ua)} != {expected}')
    bad += 1
for k, u in enumerate(ua):
    i = start + k
    if i >= len(pl):
        print('OUT OF RANGE', i)
        bad += 1
        continue
    p = pl[i]
    if not u.strip():
        print('EMPTY', i)
        bad += 1
    if re.findall(r'<sup>(\d+)</sup>', p) != re.findall(r'<sup>(\d+)</sup>', u):
        print('SUP', i, re.findall(r'<sup>(\d+)</sup>', p), re.findall(r'<sup>(\d+)</sup>', u))
        bad += 1
    if p.startswith('— ') != u.startswith('— '):
        print('DASH', i, p[:30], '|', u[:30])
        bad += 1
    if re.findall(r'[A-Za-z]', re.sub(r'<sup>\d+</sup>', '', u)):
        print('LATIN', i, u[:70])
        bad += 1
    # quote opener/closer counts must match PL per line (block quotes may span units)
    po, pc = p.count('«') + p.count('„'), p.count('»') + p.count('”') + p.count('“')
    uo, uc = u.count('«') + u.count('„'), u.count('»') + u.count('”') + u.count('“')
    if (po, pc) != (uo, uc):
        print('QUOTES', i, (po, pc), (uo, uc), '|', p[:40], '|', u[:40])
        bad += 1
print(f'{part_path} start={start} problems: {bad}')
sys.exit(1 if bad else 0)
