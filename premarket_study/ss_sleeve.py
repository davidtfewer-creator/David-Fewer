"""
Schwartz-Smith as a sleeve: a third engine, a replacement, or neither?

Two questions:
  1. Does it belong as a THIRD sleeve alongside Bayes and OU, or would it work better as a single
     sleeve replacing both? A third sleeve only earns its place if it is decorrelated from the
     other two -- if SS is simply a blend of what they already do, it adds capital dilution and
     nothing else.
  2. What does it do with the four names rejected from the book -- TSLA, SPOT, SOFI, PLTR?

Every sleeve runs through the SAME execution: fill when the low reaches the bid, exit at
bid + prem*prev close, carry until the target or the 50-day stop, commission and interest as
deployed, same-day exits verified against intraday bars, marked to market. The only difference
between sleeves is where the bid comes from, which is what makes them comparable and blendable.

Only one parameter is fitted for the SS sleeve -- the discount k -- with the premium and peak cap
taken from each name's existing workbook. That mirrors how the OU buffer was handled and keeps
the comparison structural rather than a fit.
"""
import copy, datetime, statistics
import numpy as np
from engine import run_model
from stop_sweep import load_book
from five_min import make_checker as fm
from minute_engine import make_checker as nv
from ss_model import fit_ss, ss_signal
import five_min
five_min.FILES.setdefault('MU', '/root/.claude/uploads/'
                          '2d71f10a-e19f-51b2-8457-2cd547c34dff/94f1080f-MU_5min_Apr2024Aug2026.xlsx')

DATA, PARAMS, _ = load_book()
from mu_rerun import from_workbook
DATA['MU'] = from_workbook()
from newcands import load as _lc
PARAMS['MU'] = _lc('MU')[5]

BOOK = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
LAGGARDS = ['TSLA', 'SPOT', 'SOFI', 'PLTR']
BUF_RESID = {'RKLB': 0.25, 'TSM': 0.20, 'VST': 0.65, 'VRT': 0.40, 'MU': 0.75}
CUT = datetime.date(2025, 5, 23)
COMM, INTEREST, CAPITAL = 0.005, 0.0314, 1_000_000.0
KGRID = [round(0.1*i, 2) for i in range(1, 26)]
_CHK, _SS = {}, {}


def chk(s):
    if s not in _CHK:
        d = DATA[s]
        _CHK[s] = nv(d[0], d[1])[0] if s == 'NVDA' else fm(s, d[0], d[1])[0]
    return _CHK[s]


def sleeve_run(s, bid, prem, stop_days=50, lo=None, hi=None, with_mask=False):
    """Returns (equity, trades), or (equity, trades, holding mask) when with_mask."""
    dts, O, H, L, C = DATA[s]
    n = len(C); lo = 0 if lo is None else lo; hi = n-1 if hi is None else hi
    check = chk(s)
    fund, shares, holding = CAPITAL, 0.0, False
    tgt = entry = None; trades = 0
    eq = np.zeros(n); msk = np.zeros(n, dtype=bool)
    for i in range(n):
        if i < lo or i > hi:
            eq[i] = fund if not holding else shares*C[i]
            continue
        if holding:
            if H[i] >= tgt:
                fund = shares*(tgt-COMM); shares = 0.0; holding = False; trades += 1
            elif (dts[i]-entry).days >= stop_days:
                fund = shares*(O[i]-COMM); shares = 0.0; holding = False; trades += 1
        if not holding and i > lo:
            b = bid[i]
            if b is not None and np.isfinite(b) and b > 0 and L[i] <= b:
                px = min(b, O[i])
                shares = fund/(px+COMM); fund = 0.0; holding = True
                entry = dts[i]; tgt = px + C[i-1]*prem
                if H[i] >= tgt and check(i, px, tgt) is not False:
                    fund = shares*(tgt-COMM); shares = 0.0; holding = False; trades += 1
        if not holding:
            d = (dts[i]-dts[i-1]).days if i else 0
            fund *= (1 + INTEREST*d/365)
        eq[i] = fund if not holding else shares*C[i]
        msk[i] = holding
    return (eq, trades, msk) if with_mask else (eq, trades)


def bids(s, kind, k=None):
    dts, O, H, L, C = DATA[s]
    p = PARAMS[s]
    if kind in ('bayes', 'ou'):
        q = copy.copy(p); q.ou_buf_k = BUF_RESID.get(s, p.ou_buf_k)
        fr = run_model(dts, O, H, L, C, q, ou_sigma='resid', collect=True).frames
        src = fr['X'] if kind == 'bayes' else fr['AM']
        return np.array([x if x is not None else np.nan for x in src], dtype=float)
    if s not in _SS:
        _SS[s] = fit_ss(np.log(np.array(C, dtype=float)))[0]
    fair, sig = ss_signal(C, _SS[s])
    G = np.maximum.accumulate(np.array(H, dtype=float))
    out = np.full(len(C), np.nan)
    out[1:] = np.minimum(np.minimum(fair[1:] - k*sig[1:], np.array(O, dtype=float)[1:]),
                         G[:-1]*(1-p.peak_cap))
    return out


def ann(eq, dts, lo, hi):
    d = (dts[hi]-dts[lo]).days
    return ((eq[hi]/eq[lo])**(365.25/d)-1)*100 if eq[lo] > 0 and d else float('nan')


def blend(curves):
    return np.vstack(curves).mean(axis=0)


def rets(eq):
    r = eq[1:]/eq[:-1]-1
    return r[np.isfinite(r)]


def corr(a, b):
    n = min(len(a), len(b)); a, b = a[:n], b[:n]
    if n < 3 or a.std() == 0 or b.std() == 0: return 0.0
    return float(np.corrcoef(a, b)[0, 1])
