"""
What are the six sleeves of the pooled weekly book actually doing?

The weekly model gives each name three tranches, staggered a week apart, each
with a third of that name's capital. The stated purpose is entry-timing
diversification. This audits whether that is what happens.

It is not. All three run the SAME model with the SAME fitted (cap, prem), so
they compute the same bid, fill or fail to fill together, carry the same target,
exit together and come free together. The stagger is consumed in the first three
weeks and from week 4 they never separate again. Output: per-sleeve fills, exits
and holding periods, plus a count of how many of a name's sleeves bid in each
week and how often their bids are identical.

See HANDOVER 3.48. Run after any change to weekly_book_sim.py's entry rules.

Usage:  python3 weekly_sleeve_audit.py
"""
import sys, math, statistics, collections
from weekly_book_sim import load, VEC, COMM, INTEREST, _as_date
from weekly_name import pr

NAMES=['RTX','NEM']
per,N,cal=load(NAMES); starts,ends=cal
params={s:pr(*VEC[s]) for s in NAMES}
W_LO=1; W_HI=N-1
sl=[dict(name=s,t=t,start=W_LO+t,holding=False,shares=0.,buy=None,tgt=None,
         ath=None,own=1_000_000/6,entry=None,fills=0,trades=0,hold_wk=[],
         bidwk=0, live_wk=[]) for s in NAMES for t in range(3)]
cash=1_000_000
same_bid=collections.Counter(); samefill=collections.Counter()
for wi in range(W_LO,W_HI+1):
    live=[]
    for x in sl:
        nd=per[x['name']]; p=params[x['name']]
        if wi<=x['start']: x['_sk']=True; continue
        prev,cwk=nd['WS'][wi-1],nd['WS'][wi]
        if x['ath'] is None: x['ath']=max(nd['H'][i] for i in nd['WS'][x['start']]['idxs'])
        x['ath']=max(x['ath'],prev['h'])
        rng=prev['h']-prev['l']
        if rng<=0: x['_sk']=True; continue
        x['_sk']=False
        raw=statistics.mean([p['m']*(prev['h']+prev['l'])/2,prev['c']*p['w']])+math.log10(rng)*p['g']
        Lp=min(raw,cwk['o'])
        if not x['holding']:
            x['buy']=min(Lp,x['ath']*(1-p['cap'])); x['tgt']=x['buy']+prev['c']*p['prem']
            live.append(x); x['bidwk']+=1
    # how many sleeves of each name bid this week, and are their bids identical?
    for s in NAMES:
        g=[x for x in live if x['name']==s]
        same_bid[(s,len(g))]+=1
        if len(g)>1:
            same_bid[(s,'identical')] += all(abs(g[0]['buy']-y['buy'])<1e-9 for y in g)
    share=cash/len(live) if live else 0.
    for x in live: x['_a']=share
    spent=0.
    for x in sl:
        if x.get('_sk'): continue
        nd=per[x['name']]; idxs=nd['WS'][wi]['idxs']; H,L,C=nd['H'],nd['L'],nd['C']
        if not x['holding']:
            bd=next((k for k,i in enumerate(idxs) if L[i]<=x['buy']),None)
            if bd is None: continue
            x['shares']=x['_a']/(x['buy']+COMM); spent+=x['_a']; x['holding']=True
            x['entry']=wi; x['fills']+=1
            for k in range(bd,len(idxs)):
                i=idxs[k]
                if H[i]>=x['tgt']:
                    if k==bd and nd['chk'](i,x['buy'],x['tgt']) is False: continue
                    cash+=x['shares']*(x['tgt']-COMM); x['shares']=0.; x['holding']=False
                    x['trades']+=1; x['hold_wk'].append(0); break
        else:
            for i in idxs:
                if H[i]>=x['tgt']:
                    cash+=x['shares']*(x['tgt']-COMM); x['shares']=0.; x['holding']=False
                    x['trades']+=1; x['hold_wk'].append(wi-x['entry']); break
    cash-=spent
print(f'{"sleeve":12s}{"first bid wk":>13s}{"wks bidding":>13s}{"fills":>7s}{"exits":>7s}'
      f'{"median hold":>13s}{"max hold":>10s}{"open at end":>13s}')
for x in sl:
    h=sorted(x['hold_wk'])
    print(f'{x["name"]+" t"+str(x["t"]):12s}{x["start"]+1:>13d}{x["bidwk"]:>13d}{x["fills"]:>7d}'
          f'{x["trades"]:>7d}{(h[len(h)//2] if h else 0):>12d}w{(max(h) if h else 0):>9d}'
          f'{("YES" if x["holding"] else "-"):>13s}')
print()
for s in NAMES:
    tot=sum(v for (n,k),v in same_bid.items() if n==s and isinstance(k,int))
    print(f'{s}: weeks with k of its 3 sleeves bidding -> ' +
          '  '.join(f'{k}:{same_bid[(s,k)]}' for k in (0,1,2,3)) +
          f'   (of {tot} weeks)')
    multi=same_bid[(s,2)]+same_bid[(s,3)]
    print(f'   of the {multi} weeks with 2+ bidding, bids identical in {same_bid[(s,"identical")]}')
