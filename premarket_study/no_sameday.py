"""
Bound the same-day-exit assumption. Re-run the whole book with same_day_exit=False (a position
bought today cannot hit its target until a LATER day -- the conservative daily-bar floor, since
we cannot confirm the intraday peak followed the dip). Report optimistic (current) vs floor.
"""
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()
STOCKS = list(data)


def metrics(s, sde):
    dts, O, H, L, C = data[s]
    r = run_model(dts, O, H, L, C, params[s], collect=False, same_day_exit=sde)
    return r.annual_return, r.total_buys, r.stop_loss_exits, r.max_drawdown, r.sharpe


if __name__ == '__main__':
    print('Same-day-exit assumption: optimistic (current) vs conservative floor (no same-day exits)\n')
    print(f'{"stock":6s}{"ann opt":>9s}{"ann floor":>11s}{"retained":>10s}'
          f'{"buys o/f":>12s}{"stops o/f":>11s}{"DD o/f":>13s}')
    print('-' * 72)
    keep = []
    for s in STOCKS:
        ao, bo, so, ddo, sho = metrics(s, True)
        af, bf, sf, ddf, shf = metrics(s, False)
        ret = (1 + af) / (1 + ao)                     # growth-factor retention
        keep.append(ret)
        print(f'{s:6s}{ao*100:>8.0f}%{af*100:>10.0f}%{ret*100:>9.0f}%'
              f'{str(bo)+"/"+str(bf):>12s}{str(so)+"/"+str(sf):>11s}'
              f'{f"{ddo*100:.0f}%/{ddf*100:.0f}%":>13s}')
    print('-' * 72)
    print(f'\nMean growth-factor retained under the floor: {sum(keep)/len(keep)*100:.0f}%')
    print('(retained = (1+floor ann)/(1+optimistic ann); 100% = unaffected)')

    # spotlight RKLB OU sleeve (the 92%-same-day case)
    import copy
    dts, O, H, L, C = data['RKLB']
    p = copy.copy(params['RKLB']); p.bayes_pct = 0.0
    ro = run_model(dts, O, H, L, C, p, same_day_exit=True)
    rf = run_model(dts, O, H, L, C, p, same_day_exit=False)
    yrs = (dts[-1] - dts[0]).days / 365.25
    to = ro.fundY_final + ro.fundAF_final; tf = rf.fundY_final + rf.fundAF_final
    print(f'\nRKLB OU-only (capital ${p.capital:,.0f}):')
    print(f'  optimistic: {to/p.capital:.1f}x  ({ro.annual_return*100:.0f}% ann)  buys {ro.total_buys}')
    print(f'  floor     : {tf/p.capital:.1f}x  ({rf.annual_return*100:.0f}% ann)  buys {rf.total_buys}')
