"""
NVDA — pre-market VWAP / actual open as the SIGNAL that sets the bid (not the cap).

Execution is held fixed at the correct limit-order mechanics (cap = actual open),
so any difference is purely the signal. Two injection points:
  OU anchor : forecast = mean + phi*(SIGNAL - mean)     signal in {prev_close, PM-VWAP, open}
  Bayes fair: fair' = fair + gain*(SIGNAL - fair)        signal in {PM-VWAP, open}, gain swept

Hypothesis under test: a less-noisy (PM-VWAP) or fresher (open) signal -> different
bids -> more fills -> better profit. We report fills (buys) AND profit/Sharpe, because
this project already showed more fills != better (frequency-max halved returns).
"""
from engine import Params, run_model
from experiment_nvda import load, prev_close_series


def fmt(tag, r, base):
    dret = (r.annual_return - base.annual_return) * 100
    dbuys = r.total_buys - base.total_buys
    return (f'  {tag:32s} ann={r.annual_return*100:7.2f}%  buys={r.total_buys:4d}  '
            f'Sharpe={r.sharpe:5.2f}  maxDD={r.max_drawdown*100:5.1f}%   '
            f'Δann={dret:+6.1f}pp  Δbuys={dbuys:+d}')


if __name__ == '__main__':
    d = load('nvda_joined.csv')
    dates, O, H, L, C = d['dates'], d['O'], d['H'], d['L'], d['C']
    pmV = d['pmV']
    openp = list(O)                      # actual open as a signal series
    p = Params()

    base = run_model(dates, O, H, L, C, p)          # prev-close signal everywhere
    print(f'NVDA signal experiment  ({dates[0]} -> {dates[-1]})   execution fixed = correct limit mechanics\n')
    print(fmt('BASELINE (prev-close signal)', base, base))

    print('\n(1) OU forecast anchor  — swap the prev-close anchor:')
    for tag, sig in [('OU anchor = PM-VWAP', pmV), ('OU anchor = actual open', openp)]:
        print(fmt(tag, run_model(dates, O, H, L, C, p, ou_anchor=sig), base))

    print('\n(2) Bayes fair value — nudge toward a fresher signal (gain g):')
    for name, sig in [('PM-VWAP', pmV), ('open', openp)]:
        for g in (0.25, 0.50, 1.00):
            r = run_model(dates, O, H, L, C, p, bayes_signal=sig, bayes_gain=g)
            print(fmt(f'Bayes -> {name}  (g={g:.2f})', r, base))

    print('\n(3) Best-looking combo (both legs on the actual open):')
    r = run_model(dates, O, H, L, C, p, ou_anchor=openp, bayes_signal=openp, bayes_gain=0.5)
    print(fmt('OU=open + Bayes->open g=0.5', r, base))
