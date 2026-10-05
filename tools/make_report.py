#!/usr/bin/env python3
"""Compila REPORT.md dagli artefatti presenti in pruning/ (robusto ai file mancanti)."""
import os, re, csv, json, glob, subprocess, statistics as st, time
import numpy as np
P=os.path.dirname(os.path.abspath(__file__)); os.chdir(P)
out=[]; w=out.append
def exists(p): return os.path.exists(p) and os.path.getsize(p)>0
def ppl(tag):
    r={}
    for f in sorted(glob.glob(f'quality/{tag}_ppl_*.txt')):
        n=f.split('_ppl_')[1][:-4]; m=re.search(r'ppl=([\d.]+)',open(f).read())
        if m: r[n]=float(m.group(1))
    return r
def scores(tag):
    f=f'quality/{tag}_scores.tsv'
    if not exists(f): return None
    lines=[l.rstrip('\n') for l in open(f) if l.strip()]
    hdr=lines[0].lstrip('#').split('\t'); rows=[l.split('\t') for l in lines[1:] if not l.startswith('#')]
    try:
        i=hdr.index('avg_nll'); j=hdr.index('nll'); k=hdr.index('target_tokens')
        tot_nll=sum(float(r[j]) for r in rows); tot_tok=sum(float(r[k]) for r in rows)
        res={'avg_nll_per_token':tot_nll/max(tot_tok,1),'cases':len(rows)}
    except (ValueError,IndexError): res={'rows':len(rows)}
    logf=f'quality/{tag}_scores.log'
    if exists(logf):
        for l in open(logf):
            m=re.search(r'top1_rate=([\d.]+)',l)
            if m: res['api_top1_rate']=float(m.group(1))
            m=re.search(r'^summary .*avg_lcp=([\d.]+)',l)
            if m: res['avg_greedy_lcp']=float(m.group(1))
    return res
def bench(logf,skip=0):
    if not exists(logf): return None
    try: return subprocess.run(['python3','bench_from_log.py',logf,'--skip',str(skip)],capture_output=True,text=True).stdout
    except Exception as e: return str(e)
def pruned_check(hits_csv,alloc_json,profile_csv):
    if not (exists(hits_csv) and exists(alloc_json) and exists(profile_csv)): return None
    keep=json.load(open(alloc_json))['keep']
    H=np.zeros((40,384)); Hp=np.zeros((40,384))
    for r in csv.DictReader(open(profile_csv)): H[int(r['layer']),int(r['expert'])]=int(float(r['hits']))
    for r in csv.DictReader(open(hits_csv)): Hp[int(r['layer']),int(r['expert'])]=int(float(r['hits']))
    bad=0
    for il in range(40):
        live=set(np.argsort(-H[il],kind='stable')[:keep[il]]); dead=[e for e in range(384) if e not in live]
        bad+=Hp[il,dead].sum()
    return int(bad), int(Hp.sum())
w(f'# Pruning V4.1 Flash via bias del router — report automatico\n\nGenerato: {time.strftime("%F %H:%M")}\n')
for T,name,plog in (('q4','Q4_K (Fase 1)','profile_server.log'),('q2','Q2 antirez (Fase 3)','profile_q2_server.log')):
    an=f'analysis_{T}.txt'
    if not exists(an) and not exists(plog): continue
    w(f'\n## {name}\n')
    if exists(an):
        txt=open(an).read()
        m=re.search(r'layers=.*',txt); w(f'Profilo: {m.group(0) if m else ""}\n')
        w('```\n'+'\n'.join(l for l in txt.splitlines() if l.startswith('  N=') or l.startswith('budget') or 'needed' in l or l.strip().startswith(('90','95','98','99')))+'\n```\n')
    allocs=sorted(glob.glob(f'alloc_{T}_[0-9]*.json'))
    b0=bench(plog); b1=open(f'bench_{T}_pruned.txt').read() if exists(f'bench_{T}_pruned.txt') else None
    w('### Velocità\n')
    if b0: w('Non potato (run di profilo, stessa macchina):\n```\n'+'\n'.join(b0.splitlines()[:4])+'\n```\n')
    if b1: w('Potato al budget cache (passata misurata dopo warm-up):\n```\n'+'\n'.join(b1.splitlines()[:4])+'\n```\n')
    if allocs:
        chk=pruned_check(f'pruned_{T}_hits.csv',allocs[0],f'profile_hits.csv' if T=='q4' else 'profile_q2_hits.csv')
        if chk: w(f'Verifica meccanismo: chiamate a expert esclusi durante il bench = **{chk[0]}** su {chk[1]} (atteso 0).\n')
    w('### Qualità\n')
    base=ppl(f'{T}_unpruned'); pr=ppl(f'{T}_pruned'); x13=ppl(f'{T}_pruned_x13')
    if base or pr:
        w('| testo held-out | ppl intatto | ppl potato (budget) | Δ | ppl potato (x1.3) |\n|---|---|---|---|---|')
        for n in sorted(set(base)|set(pr)|set(x13)):
            a=base.get(n); b=pr.get(n); c=x13.get(n)
            d=f'{100*(b/a-1):+.1f}%' if a and b else ''
            w(f'| {n} | {a if a else ""} | {b if b else ""} | {d} | {c if c else ""} |')
        w('')
    for tag,label in ((f'{T}_unpruned','intatto'),(f'{T}_pruned','potato budget'),(f'{T}_pruned_x13','potato x1.3')):
        s=scores(tag)
        if s: w(f'Continuazioni ufficiali V4.1 ({label}, {s.get("cases","?")} casi): '+', '.join(f'{k}={v:.4f}' if isinstance(v,float) else f'{k}={v}' for k,v in s.items() if k!='cases')+'\n')
w('\n## File\n- profilo: profile_hits.csv / profile_q2_hits.csv (colonne layer,expert,hits,layer_rows[,weight])\n- allocazioni: alloc_*.json\n- risposte: profile_outputs_*.jsonl, bench_outputs_*.jsonl, profile40_outputs_*_pruned.jsonl (confronto prima/dopo sulle stesse 40 richieste)\n- log: pipeline.log, *_server.log, quality/*.log\n')
print('\n'.join(out))
