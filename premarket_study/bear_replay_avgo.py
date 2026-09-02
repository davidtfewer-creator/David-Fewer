"""
The 2022 bear replay for the CURRENT roster (AVGO in the fourth slot, 2 Sep 2026).

Closes the pending item in the bear paper's roster note: the user exported AVGO
5-minute bars (Sep 2021 - Jun 2023; September is the earliest available, giving
83 warm-up sessions before calendar 2022 against ~90 for the incumbents' August
files -- AVGO's OU sleeve, W=113, comes live ~mid-Feb 2022 either way).

Runs BOTH rosters through the identical machinery so the RKLB-era numbers are
reproduced in the same breath as the new ones (the invariance check), and adds
the breadth-conditional gate (K=4, the adopted rule) alongside the original
protection matrix. AVGO's parameters are the reference vector wired into the
live workbook (fresh_opt_cands 'reference'; REF entry is None by design for
fitted-here names, so it is built from the vector as book_sim runs do).

Output: bear_avgo.json + console tables.
"""
import datetime
import json

from engine import Params
from fresh_opt_cands import aw_params
import book_sim
from bear_replay import (_load, bear_checker, params_for, dma_gate_dates,
                         wstat, Y22a, Y22b)
from engine import run_model
from live5_load import load as load_book

OUT = 'bear_avgo.json'
ROSTER_OLD = ['TSM', 'VRT', 'VST', 'RKLB', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
ROSTER_NEW = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'GM', 'VLO', 'CF', 'MRVL']
JUN23 = datetime.date(2023, 6, 30)


def avgo_params():
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    vec = json.load(open('fresh_opt_cands.json'))['AVGO']['reference']['vec']
    return aw_params(vec, t0)


def load_name(s, book_params):
    (dts, O, H, L, C), idx = _load(s)
    p = avgo_params() if s == 'AVGO' else params_for(s, book_params)
    chk = bear_checker(idx, dts, O)
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
    return dict(dts=dts, O=O, H=H, L=L, C=C, p=p,
                idx={d: i for i, d in enumerate(dts)}, chk=chk,
                X=r.frames['X'], AM=r.frames['AM']), r


def breadth_no_buy(data, names, K=4):
    """Per-name no-buy dates under the breadth-conditional gate: own close below
    its trailing 200dma AND at least K of the nine below theirs (ex ante)."""
    own = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in names}
    alldays = sorted(set().union(*own.values()))
    count = {d: sum(1 for s in names if d in own[s]) for d in alldays}
    return {s: {d for d in own[s] if count[d] >= K} for s in names}


def run_roster(names, data, label):
    sleeves = []
    for s in names:
        p = data[s]['p']
        sleeves.append(dict(name=s, kind='B', bids='X', prem=p.premium))
        sleeves.append(dict(name=s, kind='O', bids='AM', prem=p.ou_prem))
    common = None
    for s in names:
        common = set(data[s]['dts']) if common is None else common & set(data[s]['dts'])
    cal = sorted(common)
    gate = {s: dma_gate_dates(data[s]['dts'], data[s]['C']) for s in names}
    bgate = breadth_no_buy(data, names, K=4)
    brk = (0.15, 0.075, 0.5)
    configs = [('nothing', {}),
               ('200dma gate (per name)', dict(no_buy=gate)),
               ('breadth gate K=4 (adopted)', dict(no_buy=bgate)),
               ('gate + breaker', dict(no_buy=gate, breaker=brk)),
               ('gate + breaker + stop -25%', dict(no_buy=gate, breaker=brk, price_stop=0.25))]
    out = {}
    for wlabel, lo, hi in [('2022', Y22a, Y22b), ('full', Y22a, JUN23)]:
        out[wlabel] = {}
        print(f'\n===== {label}, pooled equal weights, '
              f'{"CALENDAR 2022" if wlabel == "2022" else "Jan 2022 - Jun 2023"} =====')
        print(f'{"config":30s}{"ann":>8s}{"total":>8s}{"maxDD":>7s}{"fills":>7s}{"stops":>6s}')
        for name_, kw in configs:
            r = book_sim.simulate(data, sleeves, cal, capital=9_000_000,
                                  collect_trades=True, date_lo=lo, date_hi=hi, **kw)
            eq = r['equity']
            tot = eq[-1] / eq[0] - 1
            out[wlabel][name_] = dict(ann=r['full'], total=tot, maxdd=r['maxdd'],
                                      fills=r['fills'], stops=r['stops'])
            print(f'{name_:30s}{r["full"]*100:>7.1f}%{tot*100:>7.1f}%'
                  f'{r["maxdd"]*100:>6.1f}%{r["fills"]:>7d}{r["stops"]:>6d}')
    return out


def main():
    _, book_params, _ = load_book()
    data = {}
    for s in sorted(set(ROSTER_OLD + ROSTER_NEW)):
        data[s], _ = load_name(s, book_params)

    # per-name AVGO row, calendar 2022 (same construction as bear_replay main)
    d = data['AVGO']
    dts, C = d['dts'], d['C']
    i0 = next(i for i, dd in enumerate(dts) if dd >= Y22a)
    i1 = max(i for i, dd in enumerate(dts) if dd <= Y22b)
    r = run_model(d['dts'], d['O'], d['H'], d['L'], d['C'], d['p'],
                  ou_sigma='resid', same_day_exit=d['chk'], collect=True)
    m_ann, m_dd = wstat(r.frames['equity'], dts, Y22a, Y22b)
    bh = C[i1] / C[i0] - 1
    buys = (sum(r.frames['t1']['Z'][i0:i1 + 1]) + sum(r.frames['t2']['Z'][i0:i1 + 1]))
    stps = sum(1 for t in ('t1', 't2') for i in range(i0, i1 + 1)
               if r.frames[t]['AD'][i] == 1 and r.frames[t]['AC'][i] is not None
               and r.frames[t]['AC'][i] < r.frames[t]['AB'][i] - 1e-9)
    print('===== AVGO per-name replay, calendar 2022 (reference params, verified fills) =====')
    print(f'B&H 2022 {bh*100:+.1f}%   model 2022 {m_ann*100:+.1f}%   model DD {m_dd*100:.1f}%'
          f'   stops {stps}   buys {buys}   span {dts[0]}..{dts[-1]}')
    avgo_row = dict(bh=bh, model=m_ann, dd=m_dd, stops=stps, buys=buys)

    res_old = run_roster(ROSTER_OLD, data, 'RKLB-era roster (reproduction)')
    res_new = run_roster(ROSTER_NEW, data, 'CURRENT roster (AVGO in slot 4)')

    with open(OUT, 'w') as f:
        json.dump(dict(avgo=avgo_row, old=res_old, new=res_new), f, indent=1)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
