"""
diversify_check.py — are PLTR, TSLA and RKLB "not fully correlated in the same
way" as the book's AI names? (user, 21 Oct 2026)

The book's own G1 rule classifies by BETA to the AI factor (>=0.27 = AI-related),
so beta is reported. But for a book whose problem is drawdowns, the question that
matters is narrower than overall correlation: does the name fall WHEN the AI
names fall? A name can look loosely correlated on average yet move with the
factor on exactly the bad days. So three lenses:

  all days   beta and correlation to the equal-weight AI factor (G1's definition)
  down days  the same, restricted to days the factor fell
  tail       the name's average return on the factor's 20 worst days

The factor is built from the six AI book names, so those six are partly
correlated with themselves; names outside it (everything else here) are clean.
"""
import numpy as np

from screen_universe import AI, build_factor, closes

BOOK = ['TSM', 'VRT', 'VST', 'AVGO', 'MU', 'MRVL', 'NVDA', 'GM', 'VLO', 'CF', 'RTX', 'DE']
CANDS = ['PLTR', 'TSLA', 'RKLB']


def profile(nm, cal, f):
    c = closes(nm)
    r = np.array([np.nan] + [(c[cal[i]]/c[cal[i-1]] - 1)
                             if (cal[i] in c and cal[i-1] in c) else np.nan
                             for i in range(1, len(cal))])
    m = ~(np.isnan(f) | np.isnan(r))
    F, R = f[m], r[m]
    b = np.polyfit(F, R, 1)[0]
    rho = np.corrcoef(F, R)[0, 1]
    d = F < 0
    bd = np.polyfit(F[d], R[d], 1)[0]
    rd = np.corrcoef(F[d], R[d])[0, 1]
    worst = np.argsort(F)[:20]
    return dict(beta=b, corr=rho, beta_dn=bd, corr_dn=rd,
                tail=R[worst].mean(), ftail=F[worst].mean(),
                vol=R.std() * np.sqrt(252))


def main():
    cal, f = build_factor()
    print(f'AI factor = equal-weight {", ".join(AI)}, {len(cal)} sessions\n')
    print(f'  {"name":6s}{"":10s}{"beta":>7s}{"corr":>7s}{"| down beta":>12s}{"down corr":>10s}'
          f'{"| worst-20":>11s}{"ann vol":>9s}   G1')
    res = {}
    for grp, names in (('BOOK', BOOK), ('CANDIDATE', CANDS)):
        for nm in names:
            p = profile(nm, cal, f)
            res[nm] = p
            tag = '(in factor)' if nm in AI else ''
            g1 = 'uncorr' if p['beta'] < 0.20 else 'AI-rel' if p['beta'] >= 0.27 else 'border'
            print(f'  {nm:6s}{tag:10s}{p["beta"]:>7.2f}{p["corr"]:>7.2f}'
                  f'{p["beta_dn"]:>12.2f}{p["corr_dn"]:>10.2f}'
                  f'{p["tail"]*100:>10.1f}%{p["vol"]*100:>8.0f}%   {g1}'
                  + ('   <-- candidate' if grp == 'CANDIDATE' else ''))
        print()
    ft = res['PLTR']['ftail']
    print(f'  the AI factor itself averaged {ft*100:.1f}% on its 20 worst days.')
    print(f'  "worst-20" = the name\'s own average on those same days.\n')
    out = {}
    for nm in CANDS:
        p = res[nm]
        out[nm] = p
        print(f'  {nm}: beta {p["beta"]:.2f} -> {"AI-related" if p["beta"]>=0.27 else "not AI-related"} '
              f'under G1; on the factor\'s worst days it averaged {p["tail"]*100:.1f}% '
              f'({p["tail"]/ft:.1f}x the factor)')
    import json
    json.dump({k: {a: float(b) for a, b in v.items()} for k, v in res.items()},
              open('diversify_check.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
