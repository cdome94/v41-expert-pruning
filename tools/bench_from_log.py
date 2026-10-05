#!/usr/bin/env python3
"""Summarize ds4-server log: per-request prefill and decode speed.
Usage: bench_from_log.py SERVER.log [--since 'MMDD HH:MM:SS'] [--skip N]
Prefill speed = prompt tokens / 'prompt done' seconds; decode speed = last 'decoding ... avg=' per request.
"""
import re, sys, argparse, statistics as st
ap=argparse.ArgumentParser(); ap.add_argument('log'); ap.add_argument('--since'); ap.add_argument('--skip',type=int,default=0)
a=ap.parse_args()
re_start=re.compile(r'^(\d{4} \d\d:\d\d:\d\d) ds4-server: chat ctx=(\d+)\.\.(\d+):(\d+) prompt start')
re_done=re.compile(r'^(\d{4} \d\d:\d\d:\d\d) ds4-server: chat ctx=(\d+)\.\.(\d+):(\d+) prompt done ([\d.]+)s')
re_dec=re.compile(r'^(\d{4} \d\d:\d\d:\d\d) ds4-server: chat ctx=\S+ gen=(\d+)\S* decoding chunk=([\d.]+) t/s avg=([\d.]+) t/s ([\d.]+)s')
reqs=[]; cur=None
for line in open(a.log,errors='replace'):
    m=re_start.match(line)
    if m:
        if a.since and m.group(1)<a.since: cur=None; continue
        cur={'t':m.group(1),'prompt':int(m.group(3))-int(m.group(2)),'prefill_s':None,'gen':0,'dec_avg':None}; reqs.append(cur); continue
    m=re_done.match(line)
    if m and cur: cur['prefill_s']=float(m.group(5)); continue
    m=re_dec.match(line)
    if m and cur: cur['gen']=int(m.group(2)); cur['dec_avg']=float(m.group(4)); cur['dec_s']=float(m.group(5))
reqs=reqs[a.skip:]
pf=[r['prompt']/r['prefill_s'] for r in reqs if r['prefill_s']]
dc=[r['dec_avg'] for r in reqs if r['dec_avg']]
print(f'requests parsed: {len(reqs)}  with prefill: {len(pf)}  with decode: {len(dc)}')
if pf: print(f'prefill t/s: median {st.median(pf):.2f}  mean {st.mean(pf):.2f}  min {min(pf):.2f}  max {max(pf):.2f}   (prompt tokens median {st.median([r["prompt"] for r in reqs]):.0f})')
if dc: print(f'decode  t/s: median {st.median(dc):.2f}  mean {st.mean(dc):.2f}  min {min(dc):.2f}  max {max(dc):.2f}   (gen tokens median {st.median([r["gen"] for r in reqs if r["dec_avg"]]):.0f})')
if len(dc)>=4:
    h=len(dc)//2; print(f'decode first half median {st.median(dc[:h]):.2f}  second half median {st.median(dc[h:]):.2f} (warm-up trend)')
for r in reqs[-5:]: print('  ',r)
