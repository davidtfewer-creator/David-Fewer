"""All-ten confirmation: does a less-noisy/fresher SIGNAL give more fills / more profit?"""
from engine import run_model
from multi_stock import STOCKS, load_stock, params_for, prevC
import json

pjson = json.load(open('params_all.json'))
print('Signal experiment across all 10 (execution fixed; frozen params). '
      'Δ vs prev-close-signal baseline.\n')
print(f'{"stock":6s}{"base ann":>9s}{"base buys":>10s}   '
      f'{"OU=PMVWAP":>18s}{"OU=open":>16s}{"Bayes->open g.5":>20s}')
print('-'*82)
agg = {'ou_pm':[0,0], 'ou_op':[0,0], 'bz_op':[0,0]}
for s in STOCKS:
    dates,O,H,L,C,PMV = load_stock(s)
    p = params_for(s, pjson)
    pm = [PMV[i] if PMV[i] is not None else prevC(C)[i] for i in range(len(C))]
    op = list(O)
    b  = run_model(dates,O,H,L,C,p)
    r1 = run_model(dates,O,H,L,C,p, ou_anchor=pm)
    r2 = run_model(dates,O,H,L,C,p, ou_anchor=op)
    r3 = run_model(dates,O,H,L,C,p, bayes_signal=op, bayes_gain=0.5)
    def d(r): return (f'{(r.annual_return-b.annual_return)*100:+6.1f}pp/'
                      f'{r.total_buys-b.total_buys:+d}b')
    print(f'{s:6s}{b.annual_return*100:8.0f}%{b.total_buys:9d}   '
          f'{d(r1):>18s}{d(r2):>16s}{d(r3):>20s}')
    for key,r in [('ou_pm',r1),('ou_op',r2),('bz_op',r3)]:
        agg[key][0]+=(r.annual_return-b.annual_return)*100
        agg[key][1]+=(1 if r.annual_return>b.annual_return else 0)
print('-'*82)
n=len(STOCKS)
for key,label in [('ou_pm','OU anchor=PM-VWAP'),('ou_op','OU anchor=open'),('bz_op','Bayes->open g=0.5')]:
    tot,wins=agg[key]
    print(f'  {label:22s}: avg Δann {tot/n:+.1f}pp   beats baseline in {wins}/{n} stocks')
