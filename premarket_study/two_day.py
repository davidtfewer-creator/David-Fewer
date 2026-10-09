"""
The daily Bayes/OU model on an N-session clock.

The weekly model was declined on holding period, not on return: 4-week median
holds pull against the trading character of the entity. This asks the other
question -- keep the DAILY architecture (Kalman local-linear-trend Bayes sleeve
+ AR(1) OU sleeve, 50-calendar-day stop, both sleeves on one name) and slow only
the CLOCK, pricing off 2-session bars instead of 1.

The engine needs no change. It already measures interest and the stop in
CALENDAR days off the `dates` array rather than in rows, so feeding it bars
stamped with each block's last session is correct by construction. Three things
do need care and are handled here:

  * PHASE. An N-session clock has N phases (which session the first block starts
    on). Phase is a free parameter and fitting it is overfitting, so every phase
    is run and reported; a result that depends on phase is not a result. Leading
    and trailing partial blocks are dropped so every bar holds exactly N sessions.

  * FILL VERIFICATION. On a 1-day bar a same-bar round trip is ambiguous and needs
    5-minute bars. On an N-day bar most of that ambiguity disappears: if the bid
    is touched in session 1 and the target high falls in session 2, the ordering
    is PROVABLE from daily bars alone. Only a round trip inside one session still
    needs the 5-minute checker. make_block_checker does exactly that, so the
    2-day clock is verified at least as strictly as the daily book.

  * BOUNDS. Premium, caps and the OU lookback are clock-dependent. A 2-session bar
    has about sqrt(2) the range of a 1-session bar, so the price-scale bounds are
    widened by that factor and the OU lookback (in BARS) is halved to hold the
    calendar lookback fixed. Every fit reports any parameter landing on a bound.

Scored on the half-sample blade (HANDOVER sec.5): fit the first half, freeze,
score the second. n=1 is run as the control, so the 2-day number is read against
the daily model fitted in the same harness rather than against a published figure.

Usage:  python3 two_day.py RTX            # n = 1, 2, all phases, with the freeze
        python3 two_day.py RTX --frontier # return vs holding period at the fit
"""
import datetime
import json
import statistics
import sys

from engine import Params, run_model
from fresh_opt_cands import REF, daily_from_5min
from minute_index import make_checker
from optimise_candidates import BOUNDS as D_BOUNDS, NAMES as PNAMES, POLICY, PERTURB, bvec

SPLIT = datetime.date(2025, 5, 23)
COMM, INTEREST, STOP_DAYS = 0.005, 0.0314, 50
# clock-dependent bound indices: premium, peak_cap, ou_prem, ou_cap scale with the
# bar's range (~sqrt(n)); ou_W is a lookback in BARS and scales as 1/n.
SCALE_IDX = [4, 5, 7, 8]
W_IDX = 9


def bounds_for(n):
    b = [list(x) for x in D_BOUNDS]
    s = n ** 0.5
    for i in SCALE_IDX:
        b[i][1] *= s
    b[W_IDX] = [max(4, D_BOUNDS[W_IDX][0]/n), D_BOUNDS[W_IDX][1]/n]
    return [tuple(x) for x in b]


def x0_vector(n):
    """Component-wise median of the stored reference vectors; RTX has none."""
    rows = [v for v in REF.values() if v]
    v = [statistics.median(r[k] for r in rows) for k in PNAMES]
    s = n ** 0.5
    for i in SCALE_IDX:
        v[i] *= s
    v[W_IDX] = max(4.0, v[W_IDX]/n)
    b = bounds_for(n)
    return [min(max(v[i], b[i][0]), b[i][1]) for i in range(len(v))]


# ------------------------------------------------------------------ the clock
def make_blocks(dts, n, phase):
    """Consecutive n-session blocks starting at `phase`; partials at both ends dropped."""
    out, i = [], phase
    while i + n <= len(dts):
        out.append(list(range(i, i + n)))
        i += n
    return out


def resample(stock, n, phase):
    dts, O, H, L, C = daily_from_5min(stock)
    bl = make_blocks(dts, n, phase)
    bar = (
        [dts[b[-1]] for b in bl],                 # stamp: the block's last session
        [O[b[0]] for b in bl],                    # open of the first session
        [max(H[i] for i in b) for b in bl],
        [min(L[i] for i in b) for b in bl],
        [C[b[-1]] for b in bl],
    )
    return (dts, O, H, L, C), bl, bar


def make_block_checker(stock, dts, O, H, L, bl):
    """Is a same-BLOCK round trip legitimate? Cross-session ordering is provable
    from daily bars; only a round trip inside one session needs 5-minute data."""
    base = make_checker(stock, dts, O)
    def chk(bi, bid, tgt):
        b = bl[bi]
        k = next((j for j, i in enumerate(b) if L[i] <= bid + 1e-9), None)
        if k is None:
            return False
        for j in range(k + 1, len(b)):           # target in a LATER session: provable
            if H[b[j]] >= tgt - 1e-9:
                return True
        return bool(base(b[k], bid, tgt))        # same session: ask the 5-minute index
    return chk


# ------------------------------------------------------------------ scoring
class Clock:
    def __init__(self, stock, n, phase):
        self.stock, self.n, self.phase = stock, n, phase
        (dts, O, H, L, C), bl, bar = resample(stock, n, phase)
        self.sessions = len(dts)
        self.bl = bl
        self.D, self.Ob, self.Hb, self.Lb, self.Cb = bar
        self.N = len(self.D)
        self.chk = make_block_checker(stock, dts, O, H, L, bl)
        self.bounds = bounds_for(n)
        self.yrs = (self.D[-1] - self.D[0]).days/365.25
        self.cut = next(i for i, d in enumerate(self.D) if d >= SPLIT)

    def params(self, vec, years=None):
        return Params(lam=vec[0], phi_L=vec[1], psi=vec[2], k=vec[3], premium=vec[4],
                      peak_cap=vec[5], ou_buf_k=vec[6], ou_prem=vec[7], ou_cap=vec[8],
                      ou_W=int(round(vec[9])), comm=COMM, capital=1_000_000,
                      interest=INTEREST, stop_days=STOP_DAYS, bayes_pct=0.5,
                      years=years or self.yrs)

    def run(self, vec):
        return run_model(self.D, self.Ob, self.Hb, self.Lb, self.Cb, self.params(vec),
                         ou_sigma='resid', same_day_exit=self.chk, collect=True)

    def seg(self, vec, lo, hi):
        """Equity-curve return and fill count over bars [lo, hi]."""
        fr = self.run(vec).frames
        eq = fr['equity']
        r = eq[hi]/eq[lo] - 1.0 if eq[lo] > 0 else -1.0
        b = sum(fr['t1']['Z'][lo:hi+1]) + sum(fr['t2']['Z'][lo:hi+1])
        return r, b

    def ann(self, r, lo, hi):
        y = (self.D[hi] - self.D[lo]).days/365.25
        return ((1 + r) ** (1/y) - 1)*100 if r > -1 else -100.0

    def robust(self, vec, lo, hi, floor):
        def one(v):
            r, b = self.seg(v, lo, hi)
            return -5.0 + b*1e-3 if b < floor else r
        base = one(vec)
        s = []
        for i in POLICY:
            for f in PERTURB:
                v = list(vec)
                v[i] = min(max(v[i]*f, self.bounds[i][0]), self.bounds[i][1])
                s.append(one(v))
        return 0.5*base + 0.5*sum(s)/len(s)

    def fit(self, lo, hi, floor, maxiter=8, popsize=8, seed=42):
        from scipy.optimize import differential_evolution
        neg = lambda v: -self.robust(v, lo, hi, floor)
        res = differential_evolution(neg, self.bounds, x0=x0_vector(self.n), init='sobol',
                                     seed=seed, maxiter=maxiter, popsize=popsize,
                                     mutation=(0.5, 1.0), recombination=0.7, tol=1e-3,
                                     polish=False, disp=False, updating='immediate',
                                     workers=1)
        return list(res.x)

    def holds(self, vec):
        """Per-trade holding periods in CALENDAR DAYS and in SESSIONS, both sleeves."""
        fr = self.run(vec).frames
        out_d, out_s, stops = [], [], 0
        for key in ('t1', 't2'):
            t = fr[key]
            entry_bar = None
            for i in range(self.N):
                if t['Z'][i] == 1:
                    entry_bar = i
                if t['AD'][i] == 1 and entry_bar is not None:
                    out_d.append((self.D[i] - self.D[entry_bar]).days)
                    out_s.append((i - entry_bar)*self.n + self.n)
                    if t['AC'][i] is not None and t['AC'][i] < t['AB'][i]:
                        stops += 1
                    entry_bar = None
        return out_d, out_s, stops

    def on_bound(self, vec, tol=0.02):
        hit = []
        for i, (lo, hi) in enumerate(self.bounds):
            span = hi - lo
            if vec[i] <= lo + tol*span or vec[i] >= hi - tol*span:
                hit.append(PNAMES[i])
        return hit


# ------------------------------------------------------------------ the study
# Trade floor set per YEAR, not per bar, so it does not quietly bias the
# comparison between clocks: a slower clock has fewer bars and would clear a
# fixed floor less easily for reasons that have nothing to do with the model.
FILLS_PER_YEAR_FLOOR = 10


def study(stock, clocks=(1, 2, 3), seeds=(42,)):
    out = []
    for n in clocks:
        for phase in range(n):
            c = Clock(stock, n, phase)
            f_full = max(6, int(FILLS_PER_YEAR_FLOOR*c.yrs))
            y_tr = (c.D[c.cut-1] - c.D[0]).days/365.25
            y_te = (c.D[c.N-1] - c.D[c.cut]).days/365.25
            f_tr = max(4, int(FILLS_PER_YEAR_FLOOR*y_tr))
            print(f'\n{"="*86}\n{stock}  n={n} phase={phase}: {c.N} bars, {c.yrs:.2f}y, '
                  f'split bar {c.cut} ({c.D[c.cut]}), floors {f_full}/{f_tr}', flush=True)

            # no-fit baseline: the neutral seed vector, scored on both halves
            r0, b0 = c.seg(x0_vector(n), 0, c.N-1)
            rt0, bt0 = c.seg(x0_vector(n), c.cut, c.N-1)
            print(f'  no fit (seed vector): full {c.ann(r0,0,c.N-1):6.1f}%  '
                  f'test {c.ann(rt0,c.cut,c.N-1):6.1f}%  ({b0}/{bt0} fills)', flush=True)

            best = None
            for sd in seeds:
                v = c.fit(0, c.N-1, f_full, seed=sd)
                r, b = c.seg(v, 0, c.N-1)
                a = c.ann(r, 0, c.N-1)
                hd, hs, st = c.holds(v)
                hd.sort(); hs.sort()
                print(f'  FULL fit seed {sd}: {a:6.1f}% ann, {b} fills ({b/c.yrs:.1f}/yr), '
                      f'prem {v[4]:.4f}/{v[7]:.4f}, hold median {hd[len(hd)//2] if hd else 0}d '
                      f'95th {hd[int(len(hd)*0.95)] if hd else 0}d, {st} stops', flush=True)
                if c.on_bound(v):
                    print(f'    ON BOUND: {", ".join(c.on_bound(v))}', flush=True)
                if best is None or a > best[1]:
                    best = (v, a, b, hd, hs, st)
            v_full, a_full, b_full, hd, hs, st = best

            # the blade
            v_fr = c.fit(0, c.cut-1, f_tr, seed=42)
            r_tri, b_tri = c.seg(v_fr, 0, c.cut-1)
            r_tef, b_tef = c.seg(v_fr, c.cut, c.N-1)
            a_tri, a_tef = c.ann(r_tri, 0, c.cut-1), c.ann(r_tef, c.cut, c.N-1)
            hdf, hsf, stf = c.holds(v_fr)
            hdf.sort()
            print(f'  FROZEN (train pick): train {a_tri:6.1f}% -> test {a_tef:6.1f}%  '
                  f'edge {a_tef - c.ann(rt0,c.cut,c.N-1):+.1f}pp vs no fit, '
                  f'{b_tef} test fills ({b_tef/y_te:.1f}/yr), '
                  f'prem {v_fr[4]:.4f}/{v_fr[7]:.4f}, hold median '
                  f'{hdf[len(hdf)//2] if hdf else 0}d', flush=True)
            if c.on_bound(v_fr):
                print(f'    ON BOUND: {", ".join(c.on_bound(v_fr))}', flush=True)

            out.append(dict(stock=stock, n=n, phase=phase, bars=c.N, yrs=c.yrs,
                            nofit_full=c.ann(r0, 0, c.N-1),
                            nofit_test=c.ann(rt0, c.cut, c.N-1),
                            full=a_full, full_fills=b_full, full_fills_yr=b_full/c.yrs,
                            full_vec=v_full, full_bound=c.on_bound(v_full),
                            hold_med_d=(hd[len(hd)//2] if hd else None),
                            hold_95_d=(hd[int(len(hd)*0.95)] if hd else None),
                            hold_med_sess=(hs[len(hs)//2] if hs else None),
                            stops=st,
                            frozen_train=a_tri, frozen_test=a_tef,
                            frozen_edge=a_tef - c.ann(rt0, c.cut, c.N-1),
                            frozen_vec=v_fr, frozen_bound=c.on_bound(v_fr),
                            frozen_test_fills=b_tef, frozen_test_fills_yr=b_tef/y_te,
                            frozen_hold_med_d=(hdf[len(hdf)//2] if hdf else None)))
    print(f'\n{"="*86}\nSUMMARY  {stock}', flush=True)
    print(f'{"clock":10s}{"no fit test":>13s}{"FROZEN test":>13s}{"edge":>8s}'
          f'{"fills/yr":>10s}{"hold med":>10s}{"full fit":>10s}{"hold":>7s}', flush=True)
    for r in out:
        lbl = f'n={r["n"]} ph{r["phase"]}'
        print(f'{lbl:10s}'
              f'{r["nofit_test"]:>12.1f}%{r["frozen_test"]:>12.1f}%{r["frozen_edge"]:>+7.1f}p'
              f'{r["frozen_test_fills_yr"]:>10.1f}{(r["frozen_hold_med_d"] or 0):>9d}d'
              f'{r["full"]:>9.1f}%{(r["hold_med_d"] or 0):>6d}d', flush=True)
    return out


if __name__ == '__main__':
    stock = next((a for a in sys.argv[1:] if not a.startswith('--')), 'RTX')
    clocks = (1, 2, 3)
    res = study(stock, clocks=clocks, seeds=(42, 7))
    try:
        prev = json.load(open('two_day.json'))
    except (FileNotFoundError, ValueError):
        prev = []
    done = {(r['stock'], r['n'], r['phase']) for r in res}
    merged = [r for r in prev if (r['stock'], r['n'], r['phase']) not in done] + res
    with open('two_day.json', 'w') as f:
        json.dump(merged, f, indent=1)
    print('DONE', flush=True)
