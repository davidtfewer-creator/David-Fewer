"""
Breadth-conditional 200dma gate study (user, 26 Aug 2026).

Observation from live trading: VST sits below its 200dma and is gated while it
recovers — the per-name gate may be taxing recoverable single-name drawdowns.
Proposal: fire the gate only when SEVERAL names breach at once — breadth as the
bear indicator. Rule tested: a name below its own 200dma is gated ONLY when at
least K of the nine names are below theirs that morning (breached names gated,
un-breached names never gated). K=1 reproduces the deployed per-name gate.

DIAGNOSTIC (2024-26): how often is a breach isolated vs broad, which names, and
what did the forgone trades on ISOLATED-breach days go on to earn (verified
entry, target-vs-50-day-stop outcome follower)?

INTERVENTION: pooled nine-name book.
  2024-26  live config (09:00/4% PM rule both sides), both halves + April-2025
           episode DD.
  2022     bear replay (PM rule off, as recorded): the gate's reason to exist —
           does breadth-conditioning keep the -2.6% save?
"""
import datetime
import json
import pickle

import numpy as np

import bear_replay
from book_sim import NAMES as N8, load_all, simulate
from engine import Params, run_model
from fresh_opt_cands import aw_params
from live5_load import load as load_book

APR_LO, APR_HI = datetime.date(2025, 2, 1), datetime.date(2025, 7, 31)
OUT = 'breadth_gate.json'


def window_dd(eq, cal, lo, hi):
    seg = [e for e, d in zip(eq, cal) if lo <= d <= hi]
    peak, dd = -1e30, 0.0
    for e in seg:
        peak = max(peak, e)
        if peak > 0:
            dd = max(dd, (peak - e) / peak)
    return dd


def breadth(gate, names):
    count = {}
    for s in names:
        for d in gate[s]:
            count[d] = count.get(d, 0) + 1
    return count


def breadth_gate(gate, count, names, K):
    return {s: {d for d in gate[s] if count.get(d, 0) >= K} for s in names}


def forgone(data, s, days, chk):
    """Outcomes of the would-be entries on the given gated days (both sleeves)."""
    nd = data[s]
    dts, O, H, L, C = nd['dts'], nd['O'], nd['H'], nd['L'], nd['C']
    out = []
    for tkey, prem in (('X', nd['p'].premium), ('AM', nd['p'].ou_prem)):
        bids = nd[tkey]
        for i, d in enumerate(dts):
            if d not in days:
                continue
            bid = bids[i]
            if bid is None or L[i] > bid + 1e-12:
                continue
            tgt = bid + C[i - 1] * prem
            if H[i] >= tgt - 1e-12 and chk(i, bid, tgt):
                out.append(tgt / bid - 1)
                continue
            done = False
            for j in range(i + 1, len(dts)):
                if H[j] >= tgt - 1e-12:
                    out.append(tgt / bid - 1)
                    done = True
                    break
                if (dts[j] - dts[i]).days >= 50:
                    out.append(O[j] / bid - 1)
                    done = True
                    break
            if not done:
                out.append(C[-1] / bid - 1)      # still open at sample end
    return out


def run_sample(label, data, sleeves, cal, names, extra_kw, apr=True, ks=(1, 2, 3, 4, 5)):
    gate = {s: bear_replay.dma_gate_dates(data[s]['dts'], data[s]['C']) for s in names}
    count = breadth(gate, names)
    rows = {}
    print(f'\n===== {label} =====')
    hdr = (f"  {'config':22s}{'full':>8s}{'train':>8s}{'test':>8s}{'maxDD':>8s}"
           f"{'Apr25':>7s}{'gated nd':>9s}") if apr else \
          (f"  {'config':22s}{'total':>9s}{'maxDD':>8s}{'gated nd':>9s}{'fills':>7s}")
    print(hdr)
    cfgs = [('no gate', None)] + [
        (('per-name gate' if K == 1 else f'breadth K>={K}'),
         breadth_gate(gate, count, names, K)) for K in ks]
    for lab, nb in cfgs:
        r = simulate(data, sleeves, cal, mode='pooled', no_buy=nb, **extra_kw)
        nd_gated = sum(len(v) for v in nb.values()) if nb else 0
        if apr:
            a = window_dd(r['equity'], cal, APR_LO, APR_HI)
            rows[lab] = dict(full=r['full'], train=r['train'], test=r['test'],
                             maxdd=r['maxdd'], apr=a, gated=nd_gated)
            print(f"  {lab:22s}{r['full']*100:>7.1f}%{r['train']*100:>7.1f}%"
                  f"{r['test']*100:>7.1f}%{r['maxdd']*100:>7.1f}%{a*100:>6.1f}%"
                  f"{nd_gated:>9d}", flush=True)
        else:
            eq = r['equity']
            tot = eq[-1] / eq[0] - 1
            rows[lab] = dict(total=tot, maxdd=r['maxdd'], gated=nd_gated,
                             fills=r['fills'])
            print(f"  {lab:22s}{tot*100:>8.1f}%{r['maxdd']*100:>7.1f}%"
                  f"{nd_gated:>9d}{r['fills']:>7d}", flush=True)
    return rows, gate, count


def main():
    # ---------------- 2024-26
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    mrvl = aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    names = N8 + ['MRVL']
    data, sleeves, cal = load_all(names=names, params_override={'MRVL': mrvl})
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))['09:00']
    def pm_rule(name, i, bid):
        pml = pm[name].get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - 0.04)

    gate = {s: bear_replay.dma_gate_dates(data[s]['dts'], data[s]['C']) for s in names}
    count = breadth(gate, names)

    print('===== DIAGNOSTIC, 2024-26: breach breadth =====')
    dist = {}
    for d, c in count.items():
        dist[c] = dist.get(c, 0) + 1
    for c in sorted(dist):
        print(f'  {c} name(s) below dma: {dist[c]:4d} days')
    print('  per-name gated days:', {s: len(gate[s]) for s in names})

    print('\n  forgone trades on ISOLATED breach days (breadth < 3), by name:')
    print(f"  {'name':6s}{'gated d':>8s}{'iso d':>7s}{'entries':>9s}{'avg ret':>9s}"
          f"{'med ret':>9s}{'min':>8s}")
    iso_all = []
    for s in names:
        iso = {d for d in gate[s] if count.get(d, 0) < 3}
        rets = forgone(data, s, iso, data[s]['chk'])
        iso_all += rets
        if gate[s]:
            a = np.array(rets) if rets else np.array([np.nan])
            print(f"  {s:6s}{len(gate[s]):>8d}{len(iso):>7d}{len(rets):>9d}"
                  f"{np.nanmean(a)*100:>8.2f}%{np.nanmedian(a)*100:>8.2f}%"
                  f"{np.nanmin(a)*100:>7.1f}%")
    a = np.array(iso_all)
    if len(a):
        print(f"  ALL: {len(a)} forgone entries, avg {a.mean()*100:+.2f}%, "
              f"median {np.median(a)*100:+.2f}%, "
              f"losers {(a<0).sum()}/{len(a)}")

    res = {}
    res['2024-26'], _, _ = run_sample(
        'INTERVENTION 2024-26 (pooled, 09:00/4% PM rule both sides)',
        data, sleeves, cal, names, dict(excl_fn=pm_rule), apr=True)

    # ---------------- 2022 replay
    _, book_params, _ = load_book()
    bdata = {}
    for s in bear_replay.NAMES:
        (dts, O, H, L, C), idx = bear_replay._load(s)
        p = bear_replay.params_for(s, book_params)
        chk = bear_replay.bear_checker(idx, dts, O)
        rm = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                       collect=True)
        bdata[s] = dict(dts=dts, O=O, H=H, L=L, C=C, p=p,
                        idx={d: i for i, d in enumerate(dts)}, chk=chk,
                        X=rm.frames['X'], AM=rm.frames['AM'])
    bsleeves = []
    for s in bear_replay.NAMES:
        p = bdata[s]['p']
        bsleeves.append(dict(name=s, kind='B', bids='X', prem=p.premium))
        bsleeves.append(dict(name=s, kind='O', bids='AM', prem=p.ou_prem))
    common = None
    for s in bear_replay.NAMES:
        common = set(bdata[s]['dts']) if common is None else common & set(bdata[s]['dts'])
    bcal = sorted(common)

    bg = {s: bear_replay.dma_gate_dates(bdata[s]['dts'], bdata[s]['C'])
          for s in bear_replay.NAMES}
    bc = breadth(bg, bear_replay.NAMES)
    dist = {}
    for d in bcal:
        if d < bear_replay.Y22a or d > bear_replay.Y22b:
            continue
        c = bc.get(d, 0)
        dist[c] = dist.get(c, 0) + 1
    print('\n===== DIAGNOSTIC, calendar 2022: breach breadth =====')
    for c in sorted(dist):
        print(f'  {c} name(s) below dma: {dist[c]:4d} days')

    res['2022'], _, _ = run_sample(
        'INTERVENTION 2022 (pooled, calendar year)',
        bdata, bsleeves, bcal, bear_replay.NAMES,
        dict(capital=9_000_000, date_lo=bear_replay.Y22a, date_hi=bear_replay.Y22b),
        apr=False)

    with open(OUT, 'w') as f:
        json.dump({k: v for k, v in res.items()}, f, indent=1)
    print(f'\nsaved {OUT}')


if __name__ == '__main__':
    main()
