"""
NVDA experiment: does pre-market VWAP beat previous close as a live signal?

Two distinct places the model uses a 'current price' signal that must be proxied live:
  (A) The open cap O_t shared by both bids. The workbook backtest uses the TRUE open
      (unknowable pre-open). Live you must proxy it. We compare prev-close vs PM-VWAP
      as that proxy, both traded against ACTUAL OHLC.
  (B) The OU forecast anchor, forecast = mean + phi*(anchor - mean). Baseline anchor
      is prev close; we try PM VWAP as a fresher anchor.

Baseline (oracle) uses the true open as cap and prev close as OU anchor — the workbook.
Everything trades against real OHLC; only the *signal used to price the bid* changes.
"""
import csv
from datetime import date
from engine import Params, run_model


def load(path):
    d = dict(dates=[], O=[], H=[], L=[], C=[], pmH=[], pmL=[], pmV=[])
    with open(path) as f:
        for r in csv.DictReader(f):
            d['dates'].append(date.fromisoformat(r['date']))
            d['O'].append(float(r['open'])); d['H'].append(float(r['high']))
            d['L'].append(float(r['low']));  d['C'].append(float(r['close']))
            d['pmH'].append(float(r['pm_high'])); d['pmL'].append(float(r['pm_low']))
            d['pmV'].append(float(r['pm_vwap']))
    return d


def prev_close_series(C):
    return [C[0]] + [C[i - 1] for i in range(1, len(C))]


def fmt(name, r, base=None):
    def d(x, b):
        return '' if b is None else f'  ({x-b:+.3f})' if isinstance(x, float) else f'  ({x-b:+d})'
    ar = f'{r.annual_return*100:7.2f}%'
    tf = f'${r.terminal_fund:>13,.0f}'
    line = (f'  {name:34s} ann={ar}  term={tf}  buys={r.total_buys:>4d}  '
            f'Sharpe={r.sharpe:5.2f}  maxDD={r.max_drawdown*100:5.1f}%  stops={r.stop_loss_exits}')
    return line


if __name__ == '__main__':
    d = load('nvda_joined.csv')
    dates, O, H, L, C = d['dates'], d['O'], d['H'], d['L'], d['C']
    N = len(C)
    prevC = prev_close_series(C)
    pmV = d['pmV']
    p = Params()

    print(f'NVDA  {dates[0]} -> {dates[-1]}  ({N} days)\n')

    # ---- Baseline (workbook: true open as cap, prev close as OU anchor) ----
    base = run_model(dates, O, H, L, C, p)
    print('BASELINE (oracle — true open cap, prev-close OU anchor):')
    print(fmt('baseline', base), '\n')

    # ---- (A) Open-cap proxy: prev-close vs PM-VWAP, both vs the oracle ----
    a_prev = run_model(dates, O, H, L, C, p, open_cap=prevC)
    a_pm   = run_model(dates, O, H, L, C, p, open_cap=pmV)
    print('(A) OPEN-CAP PROXY  (live-fidelity: how well does the proxy reproduce oracle fills?):')
    print(fmt('A: prev-close cap', a_prev, base.annual_return and None))
    print(fmt('A: PM-VWAP cap',   a_pm))
    print()

    # ---- (B) OU anchor: prev-close (baseline) vs PM-VWAP ----
    b_pm = run_model(dates, O, H, L, C, p, ou_anchor=pmV)
    print('(B) OU FORECAST ANCHOR  (alpha: prev-close baseline vs PM-VWAP):')
    print(fmt('B: prev-close anchor (=baseline)', base))
    print(fmt('B: PM-VWAP anchor', b_pm))
    print()

    # ---- (A+B) both, in the realistic live configuration (PM-VWAP for the cap too) ----
    ab_prev = run_model(dates, O, H, L, C, p, open_cap=prevC)             # live w/ prev-close everywhere
    ab_pm   = run_model(dates, O, H, L, C, p, open_cap=pmV, ou_anchor=pmV)  # live w/ PM-VWAP everywhere
    print('(A+B) REALISTIC LIVE CONFIG  (all live signals from one source):')
    print(fmt('live: prev-close (cap + anchor)', ab_prev))
    print(fmt('live: PM-VWAP  (cap + anchor)',   ab_pm))
    print()

    print('Reading: baseline is the unattainable oracle. The live question is which proxy'
          ' (prev-close vs PM-VWAP) gets closest to it — higher term/Sharpe, lower maxDD.')
