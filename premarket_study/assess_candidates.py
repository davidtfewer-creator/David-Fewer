"""
Assess the four candidate names (CCL, LLY, CVNA, MU) for inclusion in the book.

Three passes:
  1. BASELINE  - engine at each workbook's current params: return, Sharpe, maxDD,
                 trades/yr, stops, and the Bayes<->OU daily-return correlation (hedge
                 quality; we want this LOW).
  2. ROBUST    - re-degrade each param +/-3% one-at-a-time; report worst-case and mean
                 annual-return retention. A structural edge barely moves; an overfit peak
                 collapses. This is the cheap robustness screen.
  3. (opt.)    - full DE re-optimisation and walk-forward live in optimise_candidates.py.

Run: python3 assess_candidates.py
"""
import math
from engine import run_model
from newcands import load, FILES


def tranche_returns(frames, tkey):
    t = frames[tkey]; C = frames['C']
    eq = [t['AA'][i] * C[i] if t['AE'][i] == 1 else t['Y'][i] for i in range(len(C))]
    return [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1] > 0]


def correl(a, b):
    n = min(len(a), len(b)); a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in a); vb = sum((x - mb) ** 2 for x in b)
    return cov / math.sqrt(va * vb) if va > 0 and vb > 0 else 0.0


def metrics(stock):
    dts, O, H, L, C, p, cached = load(stock)
    r = run_model(dts, O, H, L, C, p, collect=True)
    r.frames['C'] = C
    yrs = (dts[-1] - dts[0]).days / 365.25
    bayes_r = tranche_returns(r.frames, 't1')
    ou_r = tranche_returns(r.frames, 't2')
    return dict(
        stock=stock, N=len(C), years=yrs,
        profit=r.profit, ann=r.annual_return, sharpe=r.sharpe, maxdd=r.max_drawdown,
        trades=r.total_buys, bayes_buys=r.bayes_buys, ou_buys=r.ou_buys,
        trades_yr=r.total_buys / yrs, stops=r.stop_loss_exits,
        hedge_corr=correl(bayes_r, ou_r),
        fundY=r.fundY_final, fundAF=r.fundAF_final, p=p,
    )


def robustness(stock, pct=0.03):
    """One-at-a-time +/-pct on each continuous param; return worst & mean ann-ret retention."""
    dts, O, H, L, C, p, _ = load(stock)
    base = run_model(dts, O, H, L, C, p).annual_return
    fields = ['lam', 'phi_L', 'psi', 'k', 'premium', 'peak_cap',
              'ou_buf_k', 'ou_prem', 'ou_cap']
    rets = []
    for fld in fields:
        for f in (1 - pct, 1 + pct):
            import copy
            pp = copy.copy(p)
            setattr(pp, fld, getattr(p, fld) * f)
            a = run_model(dts, O, H, L, C, pp).annual_return
            rets.append(a)
    # retention = perturbed ann / base ann (in growth-factor terms to stay sane if base small)
    gb = 1 + base
    ret_ratio = [(1 + a) / gb for a in rets]
    return base, min(ret_ratio), sum(ret_ratio) / len(ret_ratio)


if __name__ == '__main__':
    print('=== BASELINE (engine @ current workbook params, $6M/name, full sample) ===\n')
    hdr = (f'{"stock":5s}{"yrs":>5s}{"ann.ret":>9s}{"Sharpe":>8s}{"maxDD":>8s}'
           f'{"trades":>8s}{"tr/yr":>7s}{"stops":>7s}{"B-OU corr":>11s}')
    print(hdr); print('-' * len(hdr))
    ms = []
    for s in FILES:
        m = metrics(s); ms.append(m)
        print(f'{m["stock"]:5s}{m["years"]:>5.1f}{m["ann"]:>9.1%}{m["sharpe"]:>8.2f}'
              f'{m["maxdd"]:>8.1%}{m["trades"]:>8d}{m["trades_yr"]:>7.0f}{m["stops"]:>7d}'
              f'{m["hedge_corr"]:>11.2f}')

    print('\n=== ROBUSTNESS (+/-3% one-at-a-time on 9 continuous params) ===')
    print('retention = (1+perturbed ann)/(1+base ann); 1.00 = unmoved, <1 = degrades\n')
    print(f'{"stock":5s}{"base ann":>10s}{"worst ret":>11s}{"mean ret":>10s}')
    print('-' * 36)
    for s in FILES:
        base, worst, mean = robustness(s)
        print(f'{s:5s}{base:>10.1%}{worst:>11.3f}{mean:>10.3f}')
