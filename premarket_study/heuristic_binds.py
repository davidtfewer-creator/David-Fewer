"""
Which term of the fitted heuristic bid actually binds?

    B_t = min( formula, O_t, (1-c)·peak )

If the open floor binds nearly always, the fitted "mean-reversion" heuristic has degenerated
to "queue at the open, exit at +π" — the daily analogue of the weekly finding that the MR
term never binds and the clamp is the model. Also reports the fill mix (at-open vs intraday
dip): at-open fills make same-day exits self-verifying, so minute data is only needed where
intraday-dip fills carry the P&L.

Usage: python3 heuristic_binds.py '{"TSM": [w,a,rho,prem,cap], ...}'
       (or import and call binds(stock, vec))
"""
import json, math, sys

from heuristic_fixed import load, hp
from heuristic_engine import heuristic_bid, run_heuristic


def binds(stock, vec):
    dts, O, H, L, C, p = load(stock)
    q = hp(vec, p)
    B = heuristic_bid(O, H, L, C, q)
    N = len(B)
    n = f_bind = o_bind = c_bind = 0
    for i in range(1, N):
        anchor = 0.5 * (q.a * 0.5 * (H[i - 1] + L[i - 1]) + q.w * C[i - 1])
        raw = anchor + q.rho * math.log10(max(H[i - 1] - L[i - 1], 1e-2))
        cap = (max(H[:i]) if i else H[0]) * (1 - q.cap)
        n += 1
        m = min(raw, O[i], cap)
        if m == O[i] and O[i] <= raw and O[i] <= cap:
            o_bind += 1
        elif m == raw and raw <= cap:
            f_bind += 1
        else:
            c_bind += 1
    r = run_heuristic(dts, O, H, L, C, q, same_day_exit='at_open')
    Z = r.frames['Z']
    fills = sum(Z)
    at_open = sum(1 for i in range(1, N) if Z[i] == 1 and B[i] >= O[i] - 1e-9)
    return dict(formula=f_bind / n, open=o_bind / n, peak=c_bind / n,
                fills=fills, at_open_fills=at_open)


if __name__ == '__main__':
    vecs = json.loads(sys.argv[1])
    print(f'{"stock":6s}{"formula":>9s}{"open":>7s}{"peak":>7s}{"fills":>7s}{"@open":>7s}')
    for s, v in vecs.items():
        b = binds(s, v)
        print(f'{s:6s}{b["formula"] * 100:>8.0f}%{b["open"] * 100:>6.0f}%'
              f'{b["peak"] * 100:>6.0f}%{b["fills"]:>7d}{b["at_open_fills"]:>7d}')
