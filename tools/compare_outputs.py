#!/usr/bin/env python3
"""Confronta due file di risposte (stesso corpus, temp 0): quante identiche, similarità media."""
import json, sys, difflib
a={json.loads(l)['id']:json.loads(l) for l in open(sys.argv[1])}
b={json.loads(l)['id']:json.loads(l) for l in open(sys.argv[2])}
ids=[i for i in a if i in b and a[i].get('content') and b[i].get('content')]
ident=sum(a[i]['content']==b[i]['content'] for i in ids)
sims=[difflib.SequenceMatcher(None,a[i]['content'],b[i]['content']).ratio() for i in ids]
print(f'pairs {len(ids)}  identical {ident}  mean similarity {sum(sims)/max(len(sims),1):.3f}  min {min(sims) if sims else 0:.3f}')
for i in ids:
    if a[i]['content']!=b[i]['content']:
        x,y=a[i]['content'],b[i]['content']; k=0
        while k<min(len(x),len(y)) and x[k]==y[k]: k+=1
        print(f'  {i}: diverge at char {k}/{min(len(x),len(y))}'); 
