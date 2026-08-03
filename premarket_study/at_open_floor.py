"""
Tighten the same-day-exit bracket using the daily OPEN.

A same-day buy+sell is only ambiguous when the buy filled on an intraday DIP below the open;
if it filled AT the open (bid capped at Open), the open is the first price so the target sell
provably came later -> legitimate. This splits same-day trades into at-open (keep) vs dip
(drop) and gives an 'at_open' floor between the pessimistic floor and the optimistic backtest.

Step 1: count same-day trades that were bought at the open (both tranches).
Step 2: compare returns across three modes: optimistic / at-open floor / pessimistic floor.
"""
from stop_sweep import load_book
from engine import run_model

data, params, cached = load_book()
STOCKS = list(data)


def classify(s):
    """Per tranche: same-day trades split into at-open vs dip (intraday)."""
    dts, O, H, L, C = data[s]
    r = run_model(dts, O, H, L, C, params[s], collect=True)
    # rebuild the bid arrays actually used (X for Bayes, AM for OU)
    X = r.frames['X']; AM = r.frames['AM']
    out = {}
    for tkey, bid in (('t1', X), ('t2', AM)):
        t = r.frames[tkey]; Z = t['Z']; AD = t['AD']
        atopen = dip = 0
        for i in range(len(C)):
            if Z[i] == 1 and AD[i] == 1:                      # same-day round trip
                if bid[i] is not None and bid[i] >= O[i] - 1e-9:
                    atopen += 1
                else:
                    dip += 1
        out[tkey] = (atopen, dip)
    return out


def ann(s, mode):
    dts, O, H, L, C = data[s]
    return run_model(dts, O, H, L, C, params[s], same_day_exit=mode).annual_return


if __name__ == '__main__':
    print('=== STEP 1: same-day round trips -- bought AT OPEN vs on an intraday DIP ===')
    print(f'{"stock":6s}{"Bayes at-open/dip":>20s}{"%open":>7s}{"OU at-open/dip":>17s}{"%open":>7s}')
    print('-' * 57)
    tao = tdip = oao = odip = 0
    cl = {}
    for s in STOCKS:
        c = classify(s); cl[s] = c
        (bao, bdip) = c['t1']; (oao_, odip_) = c['t2']
        tao += bao; tdip += bdip; oao += oao_; odip += odip_
        bp = bao / (bao + bdip) * 100 if bao + bdip else 0
        op = oao_ / (oao_ + odip_) * 100 if oao_ + odip_ else 0
        print(f'{s:6s}{f"{bao}/{bdip}":>20s}{bp:>6.0f}%{f"{oao_}/{odip_}":>17s}{op:>6.0f}%')
    print('-' * 57)
    print(f'{"TOTAL":6s}{f"{tao}/{tdip}":>20s}{tao/(tao+tdip)*100:>6.0f}%'
          f'{f"{oao}/{odip}":>17s}{oao/(oao+odip)*100:>6.0f}%')

    print('\n=== STEP 2: annualised return by mode (optimistic / at-open floor / pessimistic) ===')
    print(f'{"stock":6s}{"optimistic":>12s}{"at-open floor":>15s}{"pess. floor":>13s}'
          f'{"floor lift":>12s}')
    print('-' * 64)
    for s in STOCKS:
        o = ann(s, True); a = ann(s, 'at_open'); f = ann(s, False)
        lift = (1 + a) / (1 + f)                       # how much the at-open info raises the floor
        print(f'{s:6s}{o*100:>11.0f}%{a*100:>14.0f}%{f*100:>12.0f}%{(lift-1)*100:>+11.0f}%')

    # RKLB OU spotlight
    import copy
    dts, O, H, L, C = data['RKLB']; p = copy.copy(params['RKLB']); p.bayes_pct = 0.0
    cap = p.capital
    xo = run_model(dts, O, H, L, C, p, same_day_exit=True)
    xa = run_model(dts, O, H, L, C, p, same_day_exit='at_open')
    xf = run_model(dts, O, H, L, C, p, same_day_exit=False)
    mult = lambda r: (r.fundY_final + r.fundAF_final) / cap
    print(f'\nRKLB OU-only: optimistic {mult(xo):.1f}x ({xo.annual_return*100:.0f}%) | '
          f'at-open floor {mult(xa):.1f}x ({xa.annual_return*100:.0f}%) | '
          f'pess floor {mult(xf):.1f}x ({xf.annual_return*100:.0f}%)')
