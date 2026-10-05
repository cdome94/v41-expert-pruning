#!/usr/bin/env python3
"""Router-bias expert pruning for ds4 DeepSeek V4.1 GGUFs.

Subcommands:
  dump    MODEL OUT.npy            save all blk.N.exp_probs_b.bias (n_layer x n_expert f32)
  apply   MODEL HITS.csv --keep N  [--keep-frac F] [--bias -1e4] [--orig OUT.npy]
                                   keep the N most-hit experts per layer, write -1e4 on the rest
  restore MODEL ORIG.npy           write the saved biases back
  show    MODEL [--layer L]        print per-layer count of pruned experts (bias < -1e3)
The file is modified in place; only the 384*4-byte bias tensors are touched.
"""
import argparse, struct, sys, csv, os
import numpy as np

FMT={0:'<B',1:'<b',2:'<H',3:'<h',4:'<I',5:'<i',6:'<f',7:'<?',10:'<Q',11:'<q',12:'<d'}

def read_header(path):
    f=open(path,'rb'); pos=[0]
    def rd(fmt):
        n=struct.calcsize(fmt); b=f.read(n); pos[0]+=n; return struct.unpack(fmt,b)
    def rs():
        (n,)=rd('<Q'); b=f.read(n); pos[0]+=n; return b.decode('utf-8','replace')
    def val(t):
        if t==8: return rs()
        if t==9:
            (et,)=rd('<I'); (n,)=rd('<Q')
            if et==8: return [rs() for _ in range(n)]
            sz=struct.calcsize(FMT[et]); f.read(sz*n); pos[0]+=sz*n; return None
        return rd(FMT[t])[0]
    assert f.read(4)==b'GGUF'; pos[0]=4
    (ver,)=rd('<I'); (nt,)=rd('<Q'); (nkv,)=rd('<Q')
    kv={}
    for _ in range(nkv):
        k=rs(); (t,)=rd('<I'); kv[k]=val(t)
    align=kv.get('general.alignment',32)
    tens={}
    for _ in range(nt):
        name=rs(); (nd,)=rd('<I'); dims=list(rd('<%dQ'%nd)); (tt,)=rd('<I'); (off,)=rd('<Q')
        tens[name]=(dims,tt,off)
    data_start=(pos[0]+align-1)//align*align
    f.close()
    return kv,tens,data_start

def bias_offsets(path):
    kv,tens,ds=read_header(path)
    n_layer=kv['deepseek41.num_hidden_layers']; n_exp=kv['deepseek41.n_routed_experts']
    offs=[]
    for il in range(n_layer):
        dims,tt,off=tens['blk.%d.exp_probs_b.bias'%il]
        assert tt==0 and dims==[n_exp], (il,dims,tt)
        offs.append(ds+off)
    return n_layer,n_exp,offs

def read_all(path):
    n_layer,n_exp,offs=bias_offsets(path)
    out=np.zeros((n_layer,n_exp),dtype=np.float32)
    with open(path,'rb') as f:
        for il,o in enumerate(offs):
            f.seek(o); out[il]=np.frombuffer(f.read(n_exp*4),dtype='<f4')
    return out

def write_all(path,arr):
    n_layer,n_exp,offs=bias_offsets(path)
    assert arr.shape==(n_layer,n_exp)
    with open(path,'r+b') as f:
        for il,o in enumerate(offs):
            f.seek(o); f.write(arr[il].astype('<f4').tobytes())
        f.flush(); os.fsync(f.fileno())

def load_hits(csv_path,n_layer,n_exp):
    hits=np.zeros((n_layer,n_exp),dtype=np.float64); rows=np.zeros(n_layer)
    with open(csv_path) as fp:
        for r in csv.DictReader(fp):
            il=int(r['layer']); e=int(r['expert'])
            if il<n_layer and e<n_exp:
                hits[il,e]=float(r['hits']); rows[il]=float(r['layer_rows'])
    return hits,rows

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('dump'); p.add_argument('model'); p.add_argument('out')
    p=sub.add_parser('apply'); p.add_argument('model'); p.add_argument('hits')
    p.add_argument('--keep',type=int); p.add_argument('--keep-frac',type=float)
    p.add_argument('--bias',type=float,default=-1.0e4); p.add_argument('--orig')
    p.add_argument('--min-keep',type=int,default=8); p.add_argument('--alloc',help='JSON from analyze_hits.py --alloc-out with per-layer keep counts')
    p=sub.add_parser('restore'); p.add_argument('model'); p.add_argument('orig')
    p=sub.add_parser('show'); p.add_argument('model'); p.add_argument('--layer',type=int)
    a=ap.parse_args()
    if a.cmd=='dump':
        arr=read_all(a.model); np.save(a.out,arr)
        print('saved',arr.shape,'min',arr.min(),'max',arr.max(),'->',a.out)
    elif a.cmd=='show':
        arr=read_all(a.model)
        for il in range(arr.shape[0]):
            if a.layer is not None and il!=a.layer: continue
            pr=(arr[il]<-1e3).sum()
            print('layer %2d pruned=%3d live=%3d  bias range live [%.2f, %.2f]'%(il,pr,arr.shape[1]-pr,
                  arr[il][arr[il]>-1e3].min(), arr[il][arr[il]>-1e3].max()))
    elif a.cmd=='restore':
        orig=np.load(a.orig); write_all(a.model,orig); print('restored',orig.shape)
    elif a.cmd=='apply':
        cur=read_all(a.model)
        if a.orig:
            if os.path.exists(a.orig):
                orig=np.load(a.orig)
            else:
                orig=cur.copy(); np.save(a.orig,orig); print('saved originals ->',a.orig)
        else:
            orig=cur
        if (orig<-1e3).any():
            sys.exit('refusing: the "original" biases already contain pruning values')
        n_layer,n_exp=orig.shape
        hits,rows=load_hits(a.hits,n_layer,n_exp)
        new=orig.copy(); tot_live=0; cov=[]
        alloc=None
        if a.alloc:
            import json; alloc=json.load(open(a.alloc))['keep']; assert len(alloc)==n_layer
        for il in range(n_layer):
            if alloc is not None: keep=int(alloc[il])
            else: keep=a.keep if a.keep else max(a.min_keep,int(round(a.keep_frac*n_exp)))
            keep=max(keep,a.min_keep)
            order=np.argsort(-hits[il],kind='stable')
            live=order[:keep]; dead=order[keep:]
            new[il,dead]=a.bias
            tot_live+=keep
            cov.append(hits[il,live].sum()/max(hits[il].sum(),1))
        write_all(a.model,new)
        print('applied: keep=%s live total=%d (%.1f%%) bias=%g'%(a.alloc or a.keep or a.keep_frac,tot_live,100.0*tot_live/(n_layer*n_exp),a.bias))
        print('profile hit coverage per layer: min %.3f mean %.3f max %.3f'%(min(cov),sum(cov)/len(cov),max(cov)))
if __name__=='__main__': main()
