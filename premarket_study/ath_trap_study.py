"""
The ATH-trap investigation (user flag, 10 Aug 2026).

The deployed peak cap constrains the BUY: bid <= ATH*(1-cap). The target is
bid + prevclose*premium, so a cap-bound fill needs its exit ABOVE the prior ATH
whenever prevclose/ATH > cap/premium -- for sleeves with premium > cap this is
any fill near the peak. Exposed sleeves: VST-Bayes, RKLB-Bayes, CF-Bayes, GM-OU,
VLO-OU. Live evidence at 10 Aug 2026: VLO's OU order rested with a target 0.5%
ABOVE its ATH.

Census (baseline, verified): 27 trap fills in sample (RKLB 11, VLO 9, GM 5,
CF 2); 25 exited via a new ATH within 5-14 days (bull sample bails the flaw
out), 2 became stop-losses. The backtest therefore cannot price the risk; in a
market that stops printing highs these become 50-day stops by construction.

Fixes tested, frozen parameters:
  cap_on_target   (blunt swap: cap the sale everywhere) -- REJECTED. It deepens
                  every cap-bound bid by the premium and costs 2-22pp/yr per
                  name (CF 46.9 -> 25.4).
  ath_target_guard=eps (targeted: bid also <= ATH*(1-eps) - prevclose*premium,
                  everything else untouched):
        eps=0   blocks only trades whose exit needs a print above the prior
                ATH. Cost ~zero: worst VLO -1.4pp full; RKLB/CF tested halves
                slightly improve. TSM/VRT/VST/MU unchanged.
        eps=1%  adds headroom below the ATH; costs VLO -10.7pp and GM -4.3pp
                (their OU premiums are ~4.2-4.5%).
        eps=2%  also starts re-capping VST (its Bayes cap is 1.37% < eps).

Recommendation: adopt eps=0 as a design invariant (no trade may require a
record print to exit); the 'near-ATH' margin beyond that is bought at real
cost and is a policy choice, not a free fix.
"""
import numpy as np
from engine import run_model
from earnings_pause import trades_from_frames
from live5_load import load as load_book, STOCKS as BOOK
from fresh_opt_cands import daily_from_5min, ref_params
from fresh_opt import SPLIT, annualise
from minute_index import make_checker


def main():
    book_data, book_params, _ = load_book()
    for s in BOOK + ['GM', 'VLO', 'CF']:
        if s in BOOK:
            dts, O, H, L, C = book_data[s]; p = book_params[s]
        else:
            dts, O, H, L, C = daily_from_5min(s); p = ref_params(s)
        chk = make_checker(s, dts, O)
        N = len(C)
        cut = next(i for i, d in enumerate(dts) if d >= SPLIT)
        G = [H[0]]
        for i in range(1, N):
            G.append(max(G[-1], H[i]))
        r0 = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                       collect=True)
        fr = r0.frames
        trap = ex = st = 0
        for tkey, bids, prem in (('t1', fr['X'], p.premium), ('t2', fr['AM'], p.ou_prem)):
            for (i, j, bp, xp, stop) in trades_from_frames(dts, fr, tkey, bids):
                if bp + C[i - 1] * prem > G[i - 1] + 1e-9:
                    trap += 1
                    st += bool(j is not None and stop)
                    ex += bool(j is not None and not stop)
        print(f'{s}: {trap} trap fills ({ex} exited via new ATH, {st} stopped)')
        for label, kw in [('baseline', {}), ('guard 0%', dict(ath_target_guard=0.0)),
                          ('guard 1%', dict(ath_target_guard=0.01))]:
            r = run_model(dts, O, H, L, C, p, ou_sigma='resid', same_day_exit=chk,
                          collect=True, **kw)
            eq = r.frames['equity']
            fu = annualise(eq[N - 1] / eq[0] - 1, dts, 0, N - 1)
            te = annualise(eq[N - 1] / eq[cut] - 1, dts, cut, N - 1)
            print(f'   {label:9s} full {fu*100:6.1f}%  test {te*100:6.1f}%  '
                  f'buys {r.total_buys}  stops {r.stop_loss_exits}')


if __name__ == '__main__':
    main()
