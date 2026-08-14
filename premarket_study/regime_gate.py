"""
The regime gate: a 2-state volatility HMM as a data-driven entry filter.

Idea (session, 14 Aug 2026): the earnings pauses are calendar-driven special cases
of a general rule -- "know when the tape is stressed and change behaviour". Here
the stress state is estimated, not scheduled: a 2-state Gaussian HMM on log
realised volatility (daily RV from the 5-minute bars, the same series HAR used),
fitted by EM on the TRAIN half only. State probabilities are STRICTLY EX ANTE:
the gate for day t uses the forward-filter prediction from bars through day t-1.

Two measurements, kept separate as always:

  DIAGNOSTIC   reconstruct every verified round trip under the deployed baseline
               and bucket it by the predictive stress probability at ENTRY
               (calm < 0.5 <= stressed). If stressed entries are the bad trades,
               a gate has something to work with; if they are the good trades
               (the HAR lesson suggests they might be), it doesn't.

  INTERVENTION two gate actions on top of the DEPLOYED configuration (parameters
               untouched -- this is a structural rule, judged like the pauses):
                 PAUSE   suppress new entries when P(stressed) > tau
                 SCALE   multiply both bid buffers by (1 + gamma * P(stressed));
                         gamma > 0 bids deeper in stress, gamma < 0 bids closer.
               tau / gamma are chosen on the TRAIN half from a small grid, frozen,
               scored on the tested half. Every grid cell's test number is printed
               for transparency, but the verdict comes from the train-chosen cell.

Verified fills throughout; split 2025-05-23.
"""
import json
import math
import sys

import numpy as np

from engine import Params, run_model
from fresh_opt import SPLIT, annualise
from fresh_opt_cands import daily_from_5min, ref_params, aw_params
from har_rv import rv_daily
from live5_load import load as load_book, STOCKS as BOOK
from minute_index import make_checker
from earnings_pause import trades_from_frames

NAMES = BOOK + ['GM', 'VLO', 'CF', 'MRVL']
TAUS = [0.5, 0.7, 0.9]
GAMMAS = [-0.3, 0.3, 0.6, 1.0]


# ---------------------------------------------------------------- 2-state HMM
def hmm_fit(y, iters=200, tol=1e-7):
    """EM for a 2-state Gaussian HMM on 1-d series y. Returns (pi, A, mu, sd)."""
    y = np.asarray(y)
    mu = np.array([np.percentile(y, 25), np.percentile(y, 90)])
    sd = np.array([y.std(), y.std()])
    A = np.array([[0.95, 0.05], [0.10, 0.90]])
    pi = np.array([0.9, 0.1])
    T = len(y)
    prev = -np.inf
    for _ in range(iters):
        B = np.stack([np.exp(-0.5 * ((y - mu[s]) / sd[s]) ** 2) / (sd[s] * math.sqrt(2 * math.pi))
                      for s in (0, 1)], axis=1)          # T x 2
        B = np.maximum(B, 1e-300)
        # forward
        al = np.zeros((T, 2)); c = np.zeros(T)
        al[0] = pi * B[0]; c[0] = al[0].sum(); al[0] /= c[0]
        for t in range(1, T):
            al[t] = (al[t - 1] @ A) * B[t]
            c[t] = al[t].sum(); al[t] /= c[t]
        ll = np.log(c).sum()
        # backward
        be = np.zeros((T, 2)); be[-1] = 1.0
        for t in range(T - 2, -1, -1):
            be[t] = (A @ (B[t + 1] * be[t + 1])) / c[t + 1]
        g = al * be; g /= g.sum(axis=1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(T - 1):
            m = np.outer(al[t], B[t + 1] * be[t + 1]) * A / c[t + 1]
            xi += m
        # M step
        pi = g[0] / g[0].sum()
        A = xi / xi.sum(axis=1, keepdims=True)
        for s in (0, 1):
            w = g[:, s]
            mu[s] = (w * y).sum() / w.sum()
            sd[s] = math.sqrt(max(((w * (y - mu[s]) ** 2).sum() / w.sum()), 1e-8))
        if mu[0] > mu[1]:                                # keep state 1 = stressed
            mu, sd = mu[::-1].copy(), sd[::-1].copy()
            A = A[::-1, ::-1].copy(); pi = pi[::-1].copy()
        if abs(ll - prev) < tol * abs(prev):
            break
        prev = ll
    return pi, A, mu, sd


def hmm_predictive(y, pi, A, mu, sd):
    """P(state_t = stressed | y_1..y_{t-1}) for every t (frozen params)."""
    T = len(y)
    out = np.zeros(T)
    out[0] = pi[1]
    f = pi.copy()
    for t in range(T):
        B = np.array([math.exp(-0.5 * ((y[t] - mu[s]) / sd[s]) ** 2) / (sd[s] * math.sqrt(2 * math.pi))
                      for s in (0, 1)])
        f = f * np.maximum(B, 1e-300)
        f /= f.sum()
        f = f @ A                                        # predict t+1
        if t + 1 < T:
            out[t + 1] = f[1]
    return out


# ---------------------------------------------------------------- per-name study
def params_for(s, book_params):
    if s in BOOK:
        return book_params[s]
    if s == 'MRVL':
        t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                    bayes_pct=0.5, years=2.2, ou_W=80)
        return aw_params(json.load(open('fresh_opt_cands.json'))['MRVL']['reference']['vec'], t0)
    return ref_params(s)


def stress_series(dts, rv, split):
    """Per-model-row predictive stress prob, HMM fitted on train RV only."""
    ds = sorted(rv)
    y = np.log(np.sqrt(np.array([rv[d] for d in ds])))
    tr = np.array([d < split for d in ds])
    pi, A, mu, sd = hmm_fit(y[tr])
    p_pred = hmm_predictive(y, pi, A, mu, sd)            # ex ante for RV day t
    # map to model rows: day i uses the prediction made from bars through i-1,
    # i.e. the p_pred of the first RV day >= dts[i] if aligned; safer: predictive
    # prob for the latest RV day <= dts[i] shifted forward one RV step.
    out = [None] * len(dts)
    j = 0
    for i, d in enumerate(dts):
        while j < len(ds) and ds[j] < d:
            j += 1
        # ds[j] is first RV day >= d; p_pred[j] uses bars through ds[j-1] < d -> ex ante
        if j < len(ds) and ds[j] == d and j > 0:
            out[i] = float(p_pred[j])
    occ_tr = float(np.mean([v > 0.5 for i, v in enumerate(out)
                            if v is not None and dts[i] < split]))
    occ_te = float(np.mean([v > 0.5 for i, v in enumerate(out)
                            if v is not None and dts[i] >= split]))
    return out, dict(mu=[float(m) for m in mu], sd=[float(x) for x in sd],
                     A=[[float(v) for v in row] for row in A],
                     occ_train=occ_tr, occ_test=occ_te)


def seg_g(dts, O, H, L, C, p, chk, lo, hi, **kw):
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                  collect=True, **kw)
    eq = r.frames['equity']
    buys = sum(r.frames['t1']['Z'][lo:hi + 1]) + sum(r.frames['t2']['Z'][lo:hi + 1])
    return (eq[hi] / eq[lo] - 1.0 if eq[lo] > 0 else -1.0), buys


def main(only=None):
    book_data, book_params, _ = load_book()
    try:
        results = json.load(open('regime_gate.json'))
    except FileNotFoundError:
        results = {}
    for s in (only or NAMES):
        dts, O, H, L, C = book_data[s] if s in BOOK else daily_from_5min(s)
        p = params_for(s, book_params)
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        rv = rv_daily(s)
        prob, hinfo = stress_series(dts, rv, SPLIT)
        print(f'\n===== {s}  (N={N}) =====', flush=True)
        print(f'  HMM (train-fit): calm/stressed log-vol mu {hinfo["mu"][0]:.2f}/{hinfo["mu"][1]:.2f}, '
              f'P(stay stressed) {hinfo["A"][1][1]:.2f}; '
              f'stressed days train {hinfo["occ_train"]*100:.0f}% / test {hinfo["occ_test"]*100:.0f}%',
              flush=True)

        # ---------------- diagnostic
        r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk, collect=True)
        fr = r.frames
        trades = (trades_from_frames(dts, fr, 't1', fr['X'])
                  + trades_from_frames(dts, fr, 't2', fr['AM']))
        buk = {'calm': [], 'stressed': [], 'n/a': []}
        stops = {'calm': 0, 'stressed': 0, 'n/a': 0}
        for (i, j, bp, xp, st) in trades:
            if j is None:
                continue
            b = 'n/a' if prob[i] is None else ('stressed' if prob[i] >= 0.5 else 'calm')
            buk[b].append(xp / bp - 1)
            stops[b] += st
        print(f'  DIAGNOSTIC by predictive regime at entry:', flush=True)
        for b in ('calm', 'stressed', 'n/a'):
            v = buk[b]
            if not v:
                continue
            print(f'    {b:9s} n {len(v):4d}  avg {np.mean(v)*100:+6.2f}%  '
                  f'med {np.median(v)*100:+6.2f}%  stops {stops[b]}', flush=True)

        # ---------------- interventions
        d_tr, _ = seg_g(dts, O, H, L, C, p, chk, 0, cut - 1)
        d_te, _ = seg_g(dts, O, H, L, C, p, chk, cut, N - 1)
        a = lambda r_, lo, hi: annualise(r_, dts, lo, hi)
        print(f'  baseline  : train {a(d_tr,0,cut-1)*100:6.1f}%  TEST {a(d_te,cut,N-1)*100:6.1f}%',
              flush=True)
        res = dict(hmm=hinfo, baseline=dict(train=a(d_tr, 0, cut - 1), test=a(d_te, cut, N - 1)))

        best = {}
        for label, grid in (('PAUSE', TAUS), ('SCALE', GAMMAS)):
            cells = []
            for gvar in grid:
                if label == 'PAUSE':
                    kw = dict(no_buy=[prob[i] is not None and prob[i] > gvar for i in range(N)])
                else:
                    kw = dict(k_mult=[None if prob[i] is None else 1.0 + gvar * prob[i]
                                      for i in range(N)])
                g_tr, _ = seg_g(dts, O, H, L, C, p, chk, 0, cut - 1, **kw)
                g_te, _ = seg_g(dts, O, H, L, C, p, chk, cut, N - 1, **kw)
                cells.append((gvar, a(g_tr, 0, cut - 1), a(g_te, cut, N - 1)))
                print(f'    {label} {gvar:+.1f}: train {cells[-1][1]*100:6.1f}%  '
                      f'test {cells[-1][2]*100:6.1f}%', flush=True)
            pick = max(cells, key=lambda cxy: cxy[1])
            best[label] = pick
            print(f'  {label:9s} train-pick {pick[0]:+.1f} -> frozen TEST {pick[2]*100:6.1f}% '
                  f'(baseline {a(d_te,cut,N-1)*100:.1f}%)', flush=True)
            res[label] = dict(cells=[(c[0], c[1], c[2]) for c in cells],
                              pick=pick[0], pick_train=pick[1], pick_test=pick[2])
        results[s] = res
        with open('regime_gate.json', 'w') as fh:
            json.dump(results, fh, indent=1, default=str)
        print(f'  wrote regime_gate.json ({len(results)} names)', flush=True)

    print(f'\n{"name":6s}{"base TEST":>10s}{"PAUSE pick TEST":>16s}{"SCALE pick TEST":>16s}', flush=True)
    for s, r_ in results.items():
        print(f'{s:6s}{r_["baseline"]["test"]*100:>9.1f}%'
              f'{r_["PAUSE"]["pick_test"]*100:>15.1f}%{r_["SCALE"]["pick_test"]*100:>15.1f}%', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or None)
