"""NVDA: blended TP vs 'first-rung target' TP (deep rungs ride to the shallow rung's target)."""
from engine import Params, run_model
from ladder_engine import run_ladder
from validate_nvda import load


def line(tag, r, base_ann):
    return (f'  {tag:24s} ann={r["annual"]*100:7.1f}%  Sharpe={r["sharpe"]:4.2f}  '
            f'maxDD={r["maxdd"]*100:5.1f}%  trades={r["trades"]:4d}'
            f'(B{r["bayes_trades"]}/O{r["ou_trades"]})  corr={r["corr"]:+.2f}  '
            f'Δann={(r["annual"]-base_ann)*100:+6.1f}pp')


if __name__ == '__main__':
    dates, O, H, L, C = load('nvda_ohlc.csv')
    p = Params(); k, b = p.k, p.ou_buf_k
    eb = run_model(dates, O, H, L, C, p)
    base = eb.annual_return
    print(f'Baseline (single bid): ann={base*100:.1f}%  Sharpe={eb.sharpe:.2f}  '
          f'maxDD={eb.max_drawdown*100:.1f}%  buys={eb.total_buys}\n')

    configs = {
        'span  [.6,1,1.4]×': ([0.6*k, k, 1.4*k], [0.6*b, b, 1.4*b]),
        'wide  [.5,1,1.8]×': ([0.5*k, k, 1.8*k], [0.5*b, b, 1.8*b]),
        'deep  [1,1.5,2]×':  ([k, 1.5*k, 2.0*k], [b, 1.5*b, 2.0*b]),
    }
    for name, (mb, mo) in configs.items():
        print(name)
        print(line('  blended TP', run_ladder(dates,O,H,L,C,p,mb,mo,'blended'), base))
        print(line('  first-rung TP', run_ladder(dates,O,H,L,C,p,mb,mo,'first'), base))
        print()
