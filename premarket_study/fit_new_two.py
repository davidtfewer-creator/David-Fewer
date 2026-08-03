"""Fit COIN and AMD properly, then assess on verified fills (in-sample ceiling + at-open floor)."""
from scipy.optimize import differential_evolution
from engine import Params, run_model
from verify_new_three import load_five, daily_from_five, index_from_five, make_checker
import newfeed

B=[(0.2,1.6),(0.1,1.0),(0.001,0.1),(0.3,3.0),(0.005,0.15),(0.002,0.07),(0.1,2.5),(0.005,0.15),(0.005,0.12),(30,150)]
POL=[3,4,6,7]; PERT=[0.97,1.03]
def mp(v,yrs): return Params(lam=v[0],phi_L=v[1],psi=v[2],k=v[3],premium=v[4],peak_cap=v[5],
    ou_buf_k=v[6],ou_prem=v[7],ou_cap=v[8],ou_W=int(round(v[9])),comm=0.005,capital=6_000_000,
    interest=0.0314,stop_days=50,bayes_pct=0.5,years=yrs)

def fit(name, dts,O,H,L,C, chk):
    yrs=(dts[-1]-dts[0]).days/365.25
    floor=max(20,int(0.3*len(C)/5))
    def sc(v):
        r=run_model(dts,O,H,L,C,mp(v,yrs),same_day_exit=chk)
        return -5.0+r.total_buys*1e-3 if r.total_buys<floor else r.annual_return
    def rob(v):
        base=sc(v); sm=[]
        for i in POL:
            for f in PERT:
                w=list(v); w[i]=min(max(w[i]*f,B[i][0]),B[i][1]); sm.append(sc(w))
        return 0.5*base+0.5*sum(sm)/len(sm)
    x0=[0.5,0.3,0.01,1.2,0.025,0.02,0.5,0.025,0.03,60]
    res=differential_evolution(lambda v:-rob(v),B,x0=x0,init='sobol',seed=42,maxiter=8,popsize=6,
        mutation=(0.5,1.0),recombination=0.7,tol=1e-3,polish=False,disp=False,updating='immediate',workers=1)
    return mp(list(res.x),yrs)

print(f'{"name":6s}{"optimistic":>12s}{"VERIFIED":>10s}{"at-open":>10s}{"fill rate":>11s}{"trades/yr":>11s}{"Sharpe":>8s}{"maxDD":>8s}',flush=True)
print('-'*77,flush=True)
for name in ('COIN','AMD'):
    by=load_five(name); idx=index_from_five(by)
    if name=='COIN':
        nf=newfeed.load(newfeed.NEW,['COIN']); dts,O,H,L,C=nf['COIN']
    else:
        dts,O,H,L,C=daily_from_five(by)
    chk=make_checker(idx,dts,O)
    p=fit(name,dts,O,H,L,C,chk)
    yrs=(dts[-1]-dts[0]).days/365.25
    ro=run_model(dts,O,H,L,C,p,collect=True)
    rv=run_model(dts,O,H,L,C,p,same_day_exit=chk)
    ra=run_model(dts,O,H,L,C,p,same_day_exit='at_open')
    real=fake=0
    for tk,bids in (('t1',ro.frames['X']),('t2',ro.frames['AM'])):
        t=ro.frames[tk]
        for i in range(len(C)):
            if t['Z'][i]==1 and t['AD'][i]==1 and bids[i] is not None and dts[i] in idx:
                if chk(i,bids[i],t['AB'][i]): real+=1
                else: fake+=1
    rate=real/(real+fake)*100 if real+fake else 0
    print(f'{name:6s}{ro.annual_return*100:>11.0f}%{rv.annual_return*100:>9.0f}%{ra.annual_return*100:>9.0f}%'
          f'{rate:>10.0f}%{rv.total_buys/yrs:>11.0f}{rv.sharpe:>8.2f}{rv.max_drawdown*100:>7.0f}%',flush=True)
    print(f'       fitted: k {p.k:.2f} prem {p.premium:.4f} ou_bufk {p.ou_buf_k:.2f} ou_prem {p.ou_prem:.4f} ou_W {p.ou_W}',flush=True)
print('DONE',flush=True)
