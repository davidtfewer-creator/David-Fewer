"""
NVDA and AVGO on residual OU sigma -- done properly, which is not a setting flip.

Why it is not a setting flip
---------------------------
`ou_buf_k` is measured IN SIGMAS. NVDA's 0.9073 and AVGO's 0.1902 were fitted against the LEVEL
sigma. The residual sigma is a different scale entirely -- measured here at 0.41x the level for
NVDA and 0.28x for AVGO -- so changing the convention while keeping the number silently narrows
the dollar buffer to a third of what was fitted. That is precisely the failure that put MU's
tranche 23% below market in the live book: not a wrong setting, a right setting in the wrong
units.

So three treatments, and only the last two are meaningful comparisons:

  NAIVE      resid sigma, buffer left alone. Shown because it is what flipping the switch does,
             and the size of the damage is the argument for not doing it.
  MATCHED    resid sigma, buffer divided by the measured sigma ratio so the DOLLAR buffer is
             roughly what the level-sigma configuration was bidding. This is a change of units,
             not a re-optimisation.
  SWEPT      resid sigma across a band of buffers, reported as a neighbourhood median. The
             deployed five were not simply rescaled when they were corrected -- TSM went
             0.399 -> 0.20 and VST 0.239 -> 0.65 -- so there is no universal factor, and a band
             is the honest way to ask what the convention is worth without fitting a number.

Also measured: how often the sigma term actually SETS the OU bid. The bid is
min(forecast - k*sigma, open, ATH*(1-cap)); if a clamp binds most days the sigma convention is
close to irrelevant and the whole question is smaller than it looks.

Both names have 5-minute data, so everything is on verified fills.

Run:  python3 resid_sigma_pair.py
"""
import numpy as np

import ramp_premium as R
from engine import Params, run_model

PAIR = ('NVDA', 'AVGO')
HIGH = (0.040, 0.045, 0.050, 0.060)
HIGH_STOP = 200
BUF_BAND = (0.6, 0.8, 1.0, 1.25, 1.5)      # multiples of the scale-matched buffer
PERTURB = (0.90, 0.95, 1.00, 1.05, 1.10)


def wret(eq, dates, start, end=None):
    i0 = next(i for i, x in enumerate(dates) if x >= start)
    i1 = (len(dates) - 1) if end is None else max(i for i, x in enumerate(dates) if x <= end)
    yrs = (dates[i1] - dates[i0]).days / 365.25
    return (eq[i1] / eq[i0]) ** (1 / yrs) - 1 if eq[i0] > 0 and yrs > 0 else float('nan')


def sigma_ratio(d, O, H, L, C, p):
    a = run_model(d, O, H, L, C, p, ou_sigma='level', collect=True)
    b = run_model(d, O, H, L, C, p, ou_sigma='resid', collect=True)
    sl = np.array([x for x in a.frames['OUsig'] if x is not None])
    sr = np.array([x for x in b.frames['OUsig'] if x is not None])
    return float(sr.mean() / sl.mean())


def which_binds(d, O, H, L, C, p, sigma):
    """How often is the OU bid set by the sigma term rather than by a clamp?"""
    r = run_model(d, O, H, L, C, p, ou_sigma=sigma, collect=True)
    f = r.frames
    G = f['G']
    n = {'sigma': 0, 'open': 0, 'cap': 0}
    for i in range(len(O)):
        if f['AM'][i] is None or f['OUf'][i] is None:
            continue
        cands = {'sigma': f['OUf'][i] - p.ou_buf_k * f['OUsig'][i],
                 'open': O[i], 'cap': G[i - 1] * (1 - p.ou_cap)}
        n[min(cands, key=cands.get)] += 1
    tot = sum(n.values()) or 1
    return {k: 100 * v / tot for k, v in n.items()}


def run(stock, args, p, sigma, buf, band, stop, chk):
    d = args[0]
    prems = [None] if band is None else list(band)
    out = []
    for prem in prems:
        q = Params(**{**p.__dict__, 'ou_buf_k': buf, 'stop_days': stop})
        if prem is not None:
            q = Params(**{**q.__dict__, 'premium': prem, 'ou_prem': prem})
        r = run_model(*args, q, ou_sigma=sigma, same_day_exit=chk, collect=True)
        eq = r.frames['equity']
        tr = R.trades_of(r.frames['t1']) + R.trades_of(r.frames['t2'])
        out.append((wret(eq, d, d[0]), wret(eq, d, d[0], R.SPLIT), wret(eq, d, R.SPLIT),
                    r.ou_buys, len(tr)))
    return [float(np.median([o[j] for o in out])) for j in range(5)]


def main():
    for stock in PAIR:
        d, O, H, L, C = R.load_feed(stock)
        args = (d, O, H, L, C)
        p, _ = R.load_params(stock, years=(d[-1] - d[0]).days / 365.25)
        chk = R.make_checker(R.build_index(stock), d, O)
        ratio = sigma_ratio(*args, p)
        matched = p.ou_buf_k / ratio

        print(f'\n{"="*96}')
        print(f'{stock}: deployed buffer {p.ou_buf_k:.4f} sigmas on LEVEL sigma. '
              f'resid/level = {ratio:.3f}')
        print(f'  scale-matched buffer on resid = {p.ou_buf_k:.4f} / {ratio:.3f} = {matched:.4f}')
        print(f'{"="*96}')

        print(f'\n  what sets the OU bid?  (share of sessions each term is the binding minimum)')
        for sg, bf, nm in (('level', p.ou_buf_k, 'level, deployed buffer'),
                           ('resid', matched, 'resid, scale-matched buffer')):
            q = Params(**{**p.__dict__, 'ou_buf_k': bf})
            b = which_binds(d, O, H, L, C, q, sg)
            print(f'    {nm:30s} sigma term {b["sigma"]:5.1f}%   open {b["open"]:5.1f}%   '
                  f'ATH cap {b["cap"]:5.1f}%')

        for pname, band, stop in (('deployed premium, 50d stop', None, p.stop_days),
                                  ('4-6% premium, 200d stop', HIGH, HIGH_STOP)):
            print(f'\n  -- {pname} (verified fills) --')
            print(f"    {'configuration':38s} {'buffer':>8s} {'full':>8s} {'fitted':>8s} "
                  f"{'tested':>8s} {'OU buys':>8s} {'trips':>6s}")
            base = run(stock, args, p, 'level', p.ou_buf_k, band, stop, chk)
            print(f"    {'LEVEL sigma (as fitted)':38s} {p.ou_buf_k:8.4f} {100*base[0]:7.2f}% "
                  f"{100*base[1]:7.2f}% {100*base[2]:7.2f}% {base[3]:8.0f} {base[4]:6.0f}")
            naive = run(stock, args, p, 'resid', p.ou_buf_k, band, stop, chk)
            print(f"    {'resid, NAIVE (buffer untouched)':38s} {p.ou_buf_k:8.4f} "
                  f"{100*naive[0]:7.2f}% {100*naive[1]:7.2f}% {100*naive[2]:7.2f}% "
                  f"{naive[3]:8.0f} {naive[4]:6.0f}"
                  f"   ({100*(naive[0]-base[0]):+.2f})")
            mres = run(stock, args, p, 'resid', matched, band, stop, chk)
            print(f"    {'resid, SCALE-MATCHED':38s} {matched:8.4f} {100*mres[0]:7.2f}% "
                  f"{100*mres[1]:7.2f}% {100*mres[2]:7.2f}% {mres[3]:8.0f} {mres[4]:6.0f}"
                  f"   ({100*(mres[0]-base[0]):+.2f})")
            swept = []
            for m in BUF_BAND:
                v = run(stock, args, p, 'resid', matched * m, band, stop, chk)
                swept.append(v)
                print(f"    {'  resid, buffer x'+format(m,'.2f'):38s} {matched*m:8.4f} "
                      f"{100*v[0]:7.2f}% {100*v[1]:7.2f}% {100*v[2]:7.2f}% {v[3]:8.0f} {v[4]:6.0f}")
            med = [float(np.median([s[j] for s in swept])) for j in range(3)]
            print(f"    {'resid, BAND MEDIAN over the sweep':38s} {'':8s} {100*med[0]:7.2f}% "
                  f"{100*med[1]:7.2f}% {100*med[2]:7.2f}%"
                  f"   ({100*(med[0]-base[0]):+.2f} / {100*(med[1]-base[1]):+.2f} / "
                  f"{100*(med[2]-base[2]):+.2f} vs level)")


if __name__ == '__main__':
    main()
