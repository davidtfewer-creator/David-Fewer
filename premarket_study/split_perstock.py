"""
Per-stock Bayes/OU split on VERIFIED fills, with honest trade counting.

Fixes two things in the uniform sweep:
  * trade counts must ignore phantom buys -- at a 0%/100% split the empty sleeve still raises a
    buy flag with zero shares, which made the book count look constant.
  * the split should be per name: the verified curves diverge sharply (most names want maximum
    Bayes; RKLB and TSLA lean OU).

Applies a 5% floor on the minor sleeve, per the earlier finding that corners destroy the trade
count while a small floor restores it at negligible cost.
"""
import copy, statistics
from stop_sweep import load_book
from engine import run_model
from five_min import make_checker as fm
from minute_engine import make_checker as nv

data, params, cached = load_book()
STOCKS = list(data)
CHK = {}
for s in STOCKS:
    dts, O, H, L, C = data[s]
    CHK[s] = nv(dts, O)[0] if s == 'NVDA' else fm(s, dts, O)[0]

GRID = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
YRS = (data['NVDA'][0][-1] - data['NVDA'][0][0]).days / 365.25


def run(s, bp):
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = bp
    r = run_model(dts, O, H, L, C, p, collect=True, same_day_exit=CHK[s])
    fr = r.frames
    # count only buys that actually deployed capital
    nb = sum(1 for i in range(len(C)) if fr['t1']['Z'][i] == 1 and fr['t1']['AA'][i] > 1e-9)
    no = sum(1 for i in range(len(C)) if fr['t2']['Z'][i] == 1 and fr['t2']['AA'][i] > 1e-9)
    return r, nb + no


if __name__ == '__main__':
    print('=== PER-STOCK OPTIMAL BAYES SHARE (verified fills, 5% floor on the minor sleeve) ===')
    print(f'{"stock":6s}{"best-ret":>10s}{"ret":>7s}{"best-Sh":>9s}{"Sh":>6s}'
          f'{"@50% ret":>10s}{"gain":>7s}{"trades @best/@50":>18s}')
    print('-' * 73)
    rec = {}
    tot_best = tot_50 = 0
    for s in STOCKS:
        rows = [(g,) + run(s, g) for g in GRID]
        bi = max(rows, key=lambda x: x[1].annual_return)
        si = max(rows, key=lambda x: x[1].sharpe)
        r50 = next(x for x in rows if abs(x[0]-0.5) < 1e-9)
        rec[s] = bi[0]
        tot_best += bi[1].annual_return; tot_50 += r50[1].annual_return
        print(f'{s:6s}{bi[0]*100:>9.0f}%{bi[1].annual_return*100:>6.0f}%'
              f'{si[0]*100:>8.0f}%{si[1].sharpe:>6.2f}'
              f'{r50[1].annual_return*100:>9.0f}%{(bi[1].annual_return-r50[1].annual_return)*100:>+7.1f}'
              f'{f"{bi[2]}/{r50[2]}":>18s}')
    n = len(STOCKS)
    print('-' * 73)
    print(f'{"MEAN":6s}{"":>10s}{tot_best/n*100:>6.0f}%{"":>15s}{tot_50/n*100:>9.0f}%'
          f'{(tot_best-tot_50)/n*100:>+7.1f}')

    print('\n=== recommended per-stock Bayes% (Allocation split mode 2) ===')
    for s in STOCKS:
        print(f'  {s:6s} Bayes {rec[s]*100:>3.0f}%   OU {100-rec[s]*100:>3.0f}%')

    print('\n=== book comparison (equal weight, verified) ===')
    for label, getter in (('uniform 50% (current)', lambda s: 0.5),
                          ('uniform 80%', lambda s: 0.8),
                          ('per-stock optimal', lambda s: rec[s])):
        anns, shs, dds, trs = [], [], [], 0
        for s in STOCKS:
            r, t = run(s, getter(s))
            anns.append(r.annual_return); shs.append(r.sharpe); dds.append(r.max_drawdown); trs += t
        print(f'  {label:22s} ann {statistics.mean(anns)*100:5.0f}%  Sharpe {statistics.mean(shs):4.2f}  '
              f'maxDD {statistics.mean(dds)*100:3.0f}%  trades {trs/YRS:.0f}/yr')
