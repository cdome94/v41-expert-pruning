#!/usr/bin/env python3
"""Unisce più profili di hit (CSV layer,expert,hits,layer_rows[,weight]) pesandoli per quota di traffico.
Uso: merge_hits.py OUT.csv A.csv:0.7 B.csv:0.3 ...
Ogni profilo viene normalizzato alle sue righe (token) e riscalato alla quota indicata sul totale
di righe del primo profilo, così il CSV unito ha la stessa scala di hits/token del primo."""
import csv, sys, numpy as np
out = sys.argv[1]; parts = [(p.split(':')[0], float(p.split(':')[1])) for p in sys.argv[2:]]
assert abs(sum(w for _, w in parts) - 1.0) < 1e-6, "le quote devono sommare a 1"
def load(p):
    H = {}; W = {}; R = 0
    for r in csv.DictReader(open(p)):
        k = (int(r['layer']), int(r['expert'])); H[k] = float(r['hits']); W[k] = float(r.get('weight') or 0); R = max(R, int(r['layer_rows']))
    return H, W, R
profiles = [load(p) for p, _ in parts]
L = max(k[0] for k in profiles[0][0]) + 1; E = max(k[1] for k in profiles[0][0]) + 1
base_rows = profiles[0][2]
H = np.zeros((L, E)); W = np.zeros((L, E))
for (h, w, rows), (p, q) in zip(profiles, parts):
    scale = q * base_rows / max(rows, 1)
    for k, v in h.items(): H[k] += v * scale
    for k, v in w.items(): W[k] += v * scale
    print(f"{p}: {rows} righe, quota {q:.2f}, scala {scale:.3f}")
with open(out, 'w') as f:
    f.write('layer,expert,hits,layer_rows,weight\n')
    for il in range(L):
        for e in range(E): f.write(f"{il},{e},{H[il,e]:.3f},{base_rows},{W[il,e]:.6f}\n")
print('scritto', out)
