"""
The half-sample blade (HANDOVER sec.5) applied to the weekly model.

The three-fold walk-forward in weekly_name.report() asks a softer question than the
protocol that chose the daily book: each fold refits, so a name can pass on the
strength of three different parameter vectors none of which you would have been
holding. This does what the daily book did instead -- fit once on the first half,
freeze the vector, and score the second half with it. One vector, chosen blind.

Split date is the book's own: 2025-05-23. The cut week is the first week whose
first session falls on or after it; the train half is weeks [1, cut-1] and the
test half is [cut, N-1].

Reported against three references on the same test half:
  * NVDA params      -- the no-fit baseline (what you get without fitting at all)
  * frozen           -- the train-half pick, the honest number
  * test optimum     -- the best cell on the test half, which carries lookahead and
                        is printed only to show how much of the ceiling was reached
  * full-sample opt  -- the number report() prints, also lookahead, for continuity
The frozen cell's neighbourhood median on the test half is reported too, since a
frozen vector that only works on its own cell is a spike, not a result.

Usage:  python3 weekly_freeze.py RTX NEM
"""
import datetime as dt
import json
import statistics
import sys

from weekly_mr import P
from weekly_name import Name, pr

SPLIT = dt.date(2025, 5, 23)


def _as_date(x):
    return x.date() if hasattr(x, 'date') else x


def cut_week(nm):
    """First week index whose opening session is on or after the split date."""
    for wi in range(1, nm.N):
        if _as_date(nm.DTS[nm.WS[wi]['idxs'][0]]) >= SPLIT:
            return wi
    return None


def nbhd(nm, cap, prem, w0, w1):
    """+/-20% box in 13 steps around a cell, scored over one range."""
    vals = []
    for i in range(13):
        c = round(cap*(0.80 + 0.0333*i), 5)
        for j in range(13):
            q = round(prem*(0.80 + 0.0333*j), 6)
            r, _ = nm.seg(pr(c, q), w0, w1)
            vals.append(nm.ann(r, w0, w1)*100)
    vals.sort()
    return statistics.median(vals), vals[len(vals)//4], vals[-1]


def freeze(stock):
    nm = Name(stock)
    N = nm.N
    cut = cut_week(nm)
    if cut is None or cut < 10 or N - cut < 10:
        print(f'{stock}: split unusable (cut {cut} of {N} weeks)', flush=True)
        return None
    d0 = _as_date(nm.DTS[nm.WS[1]['idxs'][0]])
    dc = _as_date(nm.DTS[nm.WS[cut]['idxs'][0]])
    dn = _as_date(nm.DTS[nm.WS[N-1]['idxs'][-1]])
    print(f'\n{"="*78}\n{stock}: {N} weeks {d0} .. {dn}', flush=True)
    print(f'  split at week {cut} ({dc}): train {cut-1} weeks, test {N-cut} weeks', flush=True)

    # trade floors, set on each half's own NVDA-parameter trade count
    r_tr0, t_tr0 = nm.seg(P, 1, cut-1)
    r_te0, t_te0 = nm.seg(P, cut, N-1)
    r_fu0, t_fu0 = nm.seg(P, 1, N-1)
    f_tr = max(4, int(0.4*t_tr0))
    f_te = max(4, int(0.4*t_te0))
    a_tr0 = nm.ann(r_tr0, 1, cut-1)*100
    a_te0 = nm.ann(r_te0, cut, N-1)*100
    a_fu0 = nm.ann(r_fu0, 1, N-1)*100
    print(f'  NVDA params:   full {a_fu0:6.1f}%  train {a_tr0:6.1f}%  test {a_te0:6.1f}%'
          f'   ({t_fu0}/{t_tr0}/{t_te0} trades, floors {f_tr}/{f_te})', flush=True)

    # --- the blade: fit on train only, freeze, score test
    c, q = nm.grid(1, cut-1, f_tr)
    r_tri, t_tri = nm.seg(pr(c, q), 1, cut-1)
    r_tef, t_tef = nm.seg(pr(c, q), cut, N-1)
    a_tri = nm.ann(r_tri, 1, cut-1)*100
    a_tef = nm.ann(r_tef, cut, N-1)*100
    print(f'  FROZEN cap {c:.3f} prem {q:.3f}: train {a_tri:6.1f}% ({t_tri} tr) '
          f'-> test {a_tef:6.1f}% ({t_tef} tr)', flush=True)
    print(f'                 test edge over NVDA params {a_tef-a_te0:+.1f}pp', flush=True)

    # --- references, both carrying lookahead
    tc, tq = nm.grid(cut, N-1, f_te)
    r_teo, t_teo = nm.seg(pr(tc, tq), cut, N-1)
    a_teo = nm.ann(r_teo, cut, N-1)*100
    fc, fq = nm.grid(1, N-1, max(8, int(0.4*t_fu0)))
    r_fuo, _ = nm.seg(pr(fc, fq), 1, N-1)
    r_fuo_te, _ = nm.seg(pr(fc, fq), cut, N-1)
    a_fuo = nm.ann(r_fuo, 1, N-1)*100
    a_fuo_te = nm.ann(r_fuo_te, cut, N-1)*100
    print(f'  [lookahead] test optimum  cap {tc:.3f} prem {tq:.3f}: {a_teo:6.1f}% '
          f'-- frozen reached {a_tef/a_teo*100 if a_teo > 0 else float("nan"):.0f}% of it',
          flush=True)
    print(f'  [lookahead] full-sample   cap {fc:.3f} prem {fq:.3f}: {a_fuo:6.1f}% full, '
          f'{a_fuo_te:6.1f}% on test', flush=True)

    # --- is the frozen cell a region or a spike, on the half it did not see?
    m_te, q25_te, pk_te = nbhd(nm, c, q, cut, N-1)
    m_tr, q25_tr, pk_tr = nbhd(nm, c, q, 1, cut-1)
    print(f'  frozen neighbourhood: train median {m_tr:6.1f}% 25th {q25_tr:6.1f}%  |  '
          f'test median {m_te:6.1f}% 25th {q25_te:6.1f}% peak {pk_te:6.1f}%', flush=True)

    # --- distance between the two halves' own picks: a stable surface picks nearby
    print(f'  pick drift: train {c:.3f}/{q:.3f}  test {tc:.3f}/{tq:.3f}  '
          f'full {fc:.3f}/{fq:.3f}', flush=True)

    return dict(stock=stock, weeks=N, cut=cut, split=str(dc),
                train_weeks=cut-1, test_weeks=N-cut,
                nvda_full=a_fu0, nvda_train=a_tr0, nvda_test=a_te0,
                trades_full=t_fu0, trades_train=t_tr0, trades_test=t_te0,
                frozen_cap=c, frozen_prem=q,
                frozen_train=a_tri, frozen_test=a_tef,
                frozen_train_trades=t_tri, frozen_test_trades=t_tef,
                edge_pp=a_tef-a_te0,
                test_opt_cap=tc, test_opt_prem=tq, test_opt=a_teo,
                full_opt_cap=fc, full_opt_prem=fq, full_opt=a_fuo, full_opt_on_test=a_fuo_te,
                nbhd_test_median=m_te, nbhd_test_q25=q25_te, nbhd_test_peak=pk_te,
                nbhd_train_median=m_tr, nbhd_train_q25=q25_tr)


if __name__ == '__main__':
    names = sys.argv[1:] or ['RTX', 'NEM']
    out = [r for r in (freeze(s) for s in names) if r]
    print(f'\n{"="*78}\nSUMMARY  (test half only; frozen is the honest column)', flush=True)
    print(f'{"stock":7s}{"NVDA":>8s}{"FROZEN":>9s}{"edge":>8s}{"nbhd med":>10s}'
          f'{"25th":>8s}{"[look] test opt":>17s}', flush=True)
    for r in out:
        print(f'{r["stock"]:7s}{r["nvda_test"]:>7.1f}%{r["frozen_test"]:>8.1f}%'
              f'{r["edge_pp"]:>+7.1f}p{r["nbhd_test_median"]:>9.1f}%{r["nbhd_test_q25"]:>7.1f}%'
              f'{r["test_opt"]:>16.1f}%', flush=True)
    # merge into the tracked record rather than overwriting it (HANDOVER 3.28d)
    try:
        prev = json.load(open('weekly_freeze.json'))
    except (FileNotFoundError, ValueError):
        prev = []
    done = {r['stock'] for r in out}
    merged = [r for r in prev if r['stock'] not in done] + out
    merged.sort(key=lambda r: -r['frozen_test'])
    with open('weekly_freeze.json', 'w') as f:
        json.dump(merged, f, indent=1)
    print('DONE', flush=True)
