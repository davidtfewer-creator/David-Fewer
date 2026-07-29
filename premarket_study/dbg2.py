import json, re
import verify_all_ladder as V
from mirror_exact import mirror_exact
from multi_stock import params_for
pj=json.load(open('params_all.json')); q=V.srcdo['Query']; i=V.STOCKS.index('RKLB')
dts,O,H,L,C=[],[],[],[],[]
for row in q.iter_rows(min_row=2, values_only=True):
    d=V.to_date(row[0]); o=row[1+4*i]
    if d is None or not isinstance(o,(int,float)) or o<=0: continue
    dts.append(d);O.append(o);H.append(row[2+4*i]);L.append(row[3+4*i]);C.append(row[4+4*i])
p=params_for('RKLB',pj)
REC=mirror_exact(dts,O,H,L,C,p)

# evaluate RKLB formula grid
do=V.srcdo['Model RKLB']; fo=V.srcf['Model RKLB']; cache={}
for row in do.iter_rows():
    for c in row:
        if c.value is not None and c.value!='' : cache[c.coordinate]=V.to_serial(c.value)
for r in range(2,7): cache[f'{V.CFG_VAL_COL}{r}']=fo[f'{V.CFG_VAL_COL}{r}'].value
grid={}
def cv(ref):
    ref=ref.replace('$',''); col=re.match(r'[A-Z]+',ref).group()
    return grid.get(ref) if col in V.LAD_COLS else cache.get(ref)
ns={'cv':cv,'IF':V.IF,'AND':V.AND,'OR':V.OR,'ISNUMBER':V.ISNUMBER,'MIN':min,'MAX':max,'None':None}
fc={}
for n in V.NAMES:
    for r in range(8,868):
        v=fo[f'{V.COL[n]}{r}'].value
        if isinstance(v,str) and v.startswith('='): fc[(n,r)]=V.translate(v)
        else: grid[f'{V.COL[n]}{r}']=0 if v is None else v
for r in range(8,868):
    for n in V.EVAL_ORDER:
        e=fc.get((n,r))
        if e is not None: grid[f'{V.COL[n]}{r}']=eval(e,ns)

def g(n,r): return grid.get(f'{V.COL[n]}{r}')
N=len(C)
for idx in range(N):
    r=idx+8
    ff=g('FUND',r); ms=REC['fund'][idx]
    fb=[g('FIL1',r),g('FIL2',r),g('FIL3',r)]; mb=REC['fills'][idx]
    if abs((ff or 0)-ms)>0.01 or fb!=mb:
        print('first divergence i=%d r=%d date=%s'%(idx,r,dts[idx]))
        print('  FORMULA: fresh=%s F0=%.2f B=[%.1f,%.1f,%.1f] fills=%s FUND=%.2f SH=%.2f ANC=%.4f'%(
            g('FRESH',r), g('F0',r) or 0, g('B1',r) or 0, g('B2',r) or 0, g('B3',r) or 0, fb, ff or 0, g('SH',r) or 0, g('ANC',r) or 0))
        print('  ENGINE : fresh=%s f0=%.2f B=%s fills=%s fund=%.2f sh=%.2f anc=%.4f'%(
            REC['fresh'][idx], REC['f0'][idx], [round(x,1) for x in (REC['B'][idx] or [0,0,0])], mb, ms, REC['sh'][idx], REC['anc'][idx]))
        print('  prices formula pr=[%.4f,%.4f,%.4f] engine pr=%s  low=%.4f'%(
            g('PR1',r) or 0, g('PR2',r) or 0, g('PR3',r) or 0, [round(x,4) for x in REC['pr'][idx]] if REC['pr'][idx] else None, L[idx]))
        # prior row state
        print('  prior FORMULA SH=%.2f FUND=%.2f exit=%s | prior ENGINE sh=%.2f fund=%.2f exit=%s'%(
            g('SH',r-1) or 0, g('FUND',r-1) or 0, g('EXIT',r-1), REC['sh'][idx-1], REC['fund'][idx-1], REC['exit'][idx-1]))
        break
