"""
Sub-period consistency ('walk-forward') for the Bayes-only ladder, all ten names.
Frozen params — nothing is fit — so the test is whether the ladder's profile (more trades,
≈neutral Sharpe) holds in each time slice / name, or the aggregate hides bad periods.

Three configs vs baseline single-bid:
  A: depths [k,1.5k,2k], weights [0.80,0.15,0.05]   (original)
  B: depths [k,1.5k,2k], weights [0.85,0.12,0.03]   (gentler weights)
  C: depths [k,1.3k,1.7k], weights [0.80,0.15,0.05] (gentler depths)
All: Bayes-only, first-rung TP. History split into 3 contiguous thirds per name (30 slices).
"""
import json, math
from engine import Params, run_model
from ladder_engine import run_ladder
from multi_stock import load_stock, params_for, STOCKS

pj = json.load(open('params_all.json'))


def seg(eq, lo, hi):
    r = eq[hi]/eq[lo] - 1 if eq[lo] > 0 else 0.0
    rets = [eq[i]/eq[i-1]-1 for i in range(lo+1, hi+1) if eq[i-1] > 0]
    if len(rets) > 1:
        mu = sum(rets)/len(rets)
        sd = math.sqrt(sum((x-mu)**2 for x in rets)/(len(rets)-1))
        sh = mu/sd*math.sqrt(252) if sd > 0 else 0.0
    else:
        sh = 0.0
    return r, sh


def cfg(s):
    p = params_for(s, pj); k, b = p.k, p.ou_buf_k
    return p, {
        'A': ([k, 1.5*k, 2.0*k], [0.80, 0.15, 0.05]),
        'B': ([k, 1.5*k, 2.0*k], [0.85, 0.12, 0.03]),
        'C': ([k, 1.3*k, 1.7*k], [0.80, 0.15, 0.05]),
    }, b


if __name__ == '__main__':
    stats = {c: {'dret': [], 'dsh': [], 'tr_ratio': [], 'sh_ge': 0, 'tr_up': 0,
                 'worst': 99, 'corr': []} for c in 'ABC'}
    nsl = 0
    for s in STOCKS:
        dates, O, H, L, C, _ = load_stock(s); N = len(C)
        p, cfgs, b = cfg(s)
        eb = run_model(dates, O, H, L, C, p, collect=True)
        eqb = eb.frames['equity']
        tb_day = [eb.frames['t1']['Z'][i] + eb.frames['t2']['Z'][i] for i in range(N)]
        cuts = [0, N//3, 2*N//3, N-1]
        slices = [(cuts[i], cuts[i+1]) for i in range(3)]
        for c in 'ABC':
            depths, w = cfgs[c]
            r = run_ladder(dates, O, H, L, C, p, depths, [b], 'first', w, None)
            stats[c]['corr'].append(r['corr'])
            eql = r['equity']; tl_day = r['daily_trades']
            for lo, hi in slices:
                rb, shb = seg(eqb, lo, hi); rl, shl = seg(eql, lo, hi)
                trb = sum(tb_day[lo:hi+1]); trl = sum(tl_day[lo:hi+1])
                stats[c]['dret'].append((rl-rb)*100)
                stats[c]['dsh'].append(shl-shb)
                if trb > 0: stats[c]['tr_ratio'].append(trl/trb)
                stats[c]['sh_ge'] += (shl >= shb - 1e-9)
                stats[c]['tr_up'] += (trl > trb)
                stats[c]['worst'] = min(stats[c]['worst'], (rl-rb)*100)
        nsl += 3
    print(f'Bayes-only ladder — sub-period consistency across {len(STOCKS)} names × 3 slices '
          f'= {nsl} slices\n')
    print(f'{"cfg":30s}{"avgΔret":>9s}{"avgΔSh":>8s}{"trades×":>8s}{"Sh≥base":>9s}'
          f'{"trades↑":>9s}{"worstΔret":>11s}{"avgCorr":>9s}')
    labels = {'A': 'A [.80,.15,.05] d[k,1.5,2]', 'B': 'B [.85,.12,.03] d[k,1.5,2]',
              'C': 'C [.80,.15,.05] d[k,1.3,1.7]'}
    for c in 'ABC':
        d = stats[c]; m = len(d['dret'])
        print(f'{labels[c]:30s}{sum(d["dret"])/m:>8.1f}{sum(d["dsh"])/m:>8.2f}'
              f'{sum(d["tr_ratio"])/len(d["tr_ratio"]):>8.2f}{d["sh_ge"]:>6d}/{m:<2d}'
              f'{d["tr_up"]:>6d}/{m:<2d}{d["worst"]:>11.1f}{sum(d["corr"])/len(d["corr"]):>9.2f}')
    print('\navgΔret/avgΔSh = ladder minus baseline, averaged over slices; trades× = avg trade ratio;'
          '\nSh≥base = slices where ladder Sharpe ≥ baseline; worstΔret = worst single-slice return gap.')
