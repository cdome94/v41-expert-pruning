#!/usr/bin/env python3
"""Analyze a DS4_EXPERT_HITS_OUT CSV: per-layer concentration and the
coverage curve 'fraction of expert calls served by the top-N experts per layer'.
Usage: analyze_hits.py HITS.csv [--ns 64,96,128,160,192,256] [--json OUT]
"""
import csv, sys, argparse, json
import numpy as np
ap=argparse.ArgumentParser(); ap.add_argument('csv'); ap.add_argument('--ns',default='48,64,96,128,160,192,224,256,320')
ap.add_argument('--json'); ap.add_argument('--expert-mib',type=float,default=18.98)
ap.add_argument('--budget',type=int,help='total live-expert slots; greedy per-layer allocation maximizing coverage')
ap.add_argument('--min-per-layer',type=int,default=16); ap.add_argument('--alloc-out')
a=ap.parse_args()
L=E=0; rows=[]
has_w=False
for r in csv.DictReader(open(a.csv)):
    w=float(r['weight']) if 'weight' in r and r['weight'] not in (None,'') else None
    if w is not None: has_w=True
    rows.append((int(r['layer']),int(r['expert']),int(float(r['hits'])),int(r['layer_rows']),w or 0.0))
L=max(r[0] for r in rows)+1; E=max(r[1] for r in rows)+1
H=np.zeros((L,E)); R=np.zeros(L); W=np.zeros((L,E))
for il,e,h,lr,w in rows: H[il,e]=h; R[il]=lr; W[il,e]=w
tot=H.sum(1); n_rows=int(R.max())
print(f'layers={L} experts={E} router rows (tokens) per layer={n_rows}  total expert calls={int(tot.sum())}')
ns=[int(x) for x in a.ns.split(',')]
S=-np.sort(-H,axis=1); C=np.cumsum(S,axis=1)/np.maximum(tot,1)[:,None]
print('\ncoverage of top-N experts per layer (mean over layers | worst layer):')
res={}
if has_w:
    # weight mass covered by the top-N experts ranked by HITS (same keep set the bias patch uses)
    order=np.argsort(-H,axis=1,kind='stable'); Wsorted=np.take_along_axis(W,order,axis=1)
    CW=np.cumsum(Wsorted,axis=1)/np.maximum(W.sum(1),1e-9)[:,None]
for n in ns:
    cov=C[:,n-1]; miss=1-cov
    gib=L*n*a.expert_mib/1024
    extra=f'  weight-mass cov {100*CW[:,n-1].mean():6.2f}%' if has_w else ''
    print(f'  N={n:3d} ({100*n/E:4.1f}%)  mean cov {100*cov.mean():6.2f}%  worst {100*cov.min():6.2f}% (layer {int(cov.argmin())})  mean miss {100*miss.mean():5.2f}%  cache {gib:6.1f} GiB{extra}')
    res[n]={'mean_cov':float(cov.mean()),'min_cov':float(cov.min()),'gib':gib}
    if has_w: res[n]['weight_cov']=float(CW[:,n-1].mean())
if has_w:
    meanw=W.sum()/max(H.sum(),1); print(f'\nmean router weight per selected expert: {meanw:.4f} (6 experts sum to 1.5)')
# experts per layer needed for 95/98/99% coverage
print('\nexperts needed per layer for a coverage target (mean | max over layers):')
for tgt in (0.90,0.95,0.98,0.99,0.999):
    need=(C<tgt).sum(1)+1
    print(f'  {100*tgt:5.1f}%  mean {need.mean():6.1f}  max {need.max():4d}  total {int(need.sum())} experts = {need.sum()*a.expert_mib/1024:.1f} GiB')
# never-used experts
never=(H==0).sum(1)
print(f'\nnever-selected experts per layer: mean {never.mean():.1f}, min {never.min()}, max {never.max()}')
# entropy / effective number
p=H/np.maximum(tot,1)[:,None]; ent=-(p*np.log(np.where(p>0,p,1))).sum(1); eff=np.exp(ent)
print(f'effective number of experts per layer (exp entropy): mean {eff.mean():.1f} min {eff.min():.1f} max {eff.max():.1f}')
if a.json: json.dump({'rows':n_rows,'coverage':res,'eff':eff.tolist()},open(a.json,'w'),indent=1)

if a.budget:
    # greedy: start every layer at min, then repeatedly give a slot to the layer whose next expert has the most hits (normalized per layer rows)
    import heapq
    keep=np.full(L,a.min_per_layer); left=a.budget-keep.sum()
    heap=[(-S[il,keep[il]]/max(tot[il],1),il) for il in range(L)]; heapq.heapify(heap)
    while left>0 and heap:
        g,il=heapq.heappop(heap); keep[il]+=1; left-=1
        if keep[il]<E: heapq.heappush(heap,(-S[il,keep[il]]/max(tot[il],1),il))
    cov=np.array([C[il,keep[il]-1] for il in range(L)])
    print(f'\nbudget {a.budget} slots ({a.budget*a.expert_mib/1024:.1f} GiB): per-layer keep min {keep.min()} max {keep.max()} mean {keep.mean():.1f}; coverage mean {100*cov.mean():.2f}% worst {100*cov.min():.2f}% (layer {int(cov.argmin())}); uniform N={a.budget//L} would give {100*C[:,a.budget//L-1].mean():.2f}%')
    print('  keep per layer:',keep.tolist())
    if a.alloc_out: json.dump({'budget':a.budget,'keep':keep.tolist(),'coverage':cov.tolist()},open(a.alloc_out,'w'))
