"""NVDA laddering test: validate 1-rung == baseline, then sweep ladder configs (both sleeves)."""
from engine import Params, run_model
from ladder_engine import run_ladder
from validate_nvda import load


def line(tag, r, base):
    d = (r['annual']-base['annual'])*100
    return (f'  {tag:26s} ann={r["annual"]*100:7.1f}%  Sharpe={r["sharpe"]:4.2f}  '
            f'maxDD={r["maxdd"]*100:5.1f}%  trades={r["trades"]:4d} '
            f'(B{r["bayes_trades"]}/O{r["ou_trades"]})  corr={r["corr"]:+.2f}  Δann={d:+.1f}pp')


if __name__ == '__main__':
    dates, O, H, L, C = load('nvda_ohlc.csv')
    p = Params()
    k, b = p.k, p.ou_buf_k

    # engine baseline for reference
    eb = run_model(dates, O, H, L, C, p)
    print(f'run_model baseline:  ann={eb.annual_return*100:.1f}%  Sharpe={eb.sharpe:.2f}  '
          f'maxDD={eb.max_drawdown*100:.1f}%  buys={eb.total_buys}\n')

    # 1-rung ladder should reproduce baseline (within interest approx)
    base = run_ladder(dates, O, H, L, C, p, [k], [b])
    print('SANITY — 1-rung ladder (should ≈ baseline):')
    print(line('1-rung [k],[b]', base, base), '\n')

    print('LADDER SWEEP (both sleeves laddered, 3 equal rungs, blended TP):')
    configs = {
        'span  [.6,1,1.4]×': ([0.6*k, k, 1.4*k], [0.6*b, b, 1.4*b]),
        'deep  [1,1.5,2]×':  ([k, 1.5*k, 2.0*k], [b, 1.5*b, 2.0*b]),
        'wide  [.5,1,1.8]×':  ([0.5*k, k, 1.8*k], [0.5*b, b, 1.8*b]),
        'shallow[.4,.7,1]×': ([0.4*k, 0.7*k, k], [0.4*b, 0.7*b, b]),
    }
    for name, (mb, mo) in configs.items():
        print(line(name, run_ladder(dates, O, H, L, C, p, mb, mo), base))

    print('\nBAYES-ONLY ladder (OU stays 1-rung) for the best-looking depth:')
    for name, mb in {'span B-only': [0.6*k, k, 1.4*k], 'wide B-only': [0.5*k, k, 1.8*k]}.items():
        print(line(name, run_ladder(dates, O, H, L, C, p, mb, [b]), base))
