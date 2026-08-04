"""
Walk-forward AVGO's Bayes-bid variant -- the one signal result that was stable across halves.

On the single half-sample split the Bayes bid beat mean reversion on AVGO in both halves (91.2%
then 106.0% against 72.3% and 96.3%), which is not what an overfit usually looks like. One split
is one observation, so this repeats it across three expanding folds.

Each fold fits on the train weeks only and scores the unseen test weeks against two references:

  MR refit     mean reversion fitted on the same train window -- the fair like-for-like, since
               both models then get the same information and the only difference is the six
               parameters versus two
  MR deployed  AVGO's specified cap 0.080 / prem 0.100, frozen -- the decision-relevant baseline,
               because that is what is actually running

The parameter spread across folds is reported too. A signal that is real should want roughly the
same Kalman settings in every window; one that is fitting noise will not.
"""
import statistics
from weekly_signal_test import Name, SPEC, simulate, fit, ann, MRP

STOCK = 'AVGO'
DEPLOYED = [0.080, 0.100]                      # AVGO's specified cap / prem
CUTS = (0.5, 0.667, 0.833, 1.0)

if __name__ == '__main__':
    nm = Name(STOCK)
    N = nm.N
    cuts = [int(N*f) for f in CUTS]
    _, t_all = simulate(nm, 'MR', DEPLOYED, 1, N-1)
    print(f'{STOCK}: {N} weeks; deployed MR makes {t_all} trades over the sample\n', flush=True)
    print(f'{"fold":5s}{"train":>10s}{"test":>10s}{"Bayes OOS":>12s}{"MR refit":>11s}'
          f'{"MR deployed":>14s}{"winner":>13s}', flush=True)
    print('-'*76, flush=True)

    wins_r = wins_d = 0; dr = []; dd = []; picks = []
    for k in range(3):
        trhi = cuts[k]; telo, tehi = cuts[k], cuts[k+1]-1
        _, t_tr = simulate(nm, 'MR', DEPLOYED, 1, trhi-1)
        floor = max(4, int(0.35*t_tr))
        vb = fit(nm, 'Bayes', 1, trhi-1, floor)
        vm = fit(nm, 'MR', 1, trhi-1, floor)
        picks.append(vb)
        b, _ = simulate(nm, 'Bayes', vb, telo, tehi)
        m, _ = simulate(nm, 'MR', vm, telo, tehi)
        d, _ = simulate(nm, 'MR', DEPLOYED, telo, tehi)
        wins_r += (b > m); wins_d += (b > d)
        dr.append((b-m)*100); dd.append((b-d)*100)
        best = 'Bayes' if b >= max(m, d) else ('MR refit' if m >= d else 'MR deployed')
        print(f'{k+1:<5d}{f"1-{trhi-1}":>10s}{f"{telo}-{tehi}":>10s}'
              f'{ann(nm,b,telo,tehi)*100:>11.1f}%{ann(nm,m,telo,tehi)*100:>10.1f}%'
              f'{ann(nm,d,telo,tehi)*100:>13.1f}%{best:>13s}', flush=True)
    print('-'*76, flush=True)
    print(f'Bayes beats MR refit in {wins_r}/3 (mean {statistics.mean(dr):+.1f}pp on segment '
          f'return); beats MR deployed in {wins_d}/3 (mean {statistics.mean(dd):+.1f}pp)',
          flush=True)

    print('\nBayes parameters fitted per fold:', flush=True)
    keys = SPEC['Bayes'][1]
    for i, v in enumerate(picks, 1):
        print(f'  fold {i}: ' + '  '.join(f'{k}={x:.4g}' for k, x in zip(keys, v)), flush=True)
    print('\nspread across folds (max/min):', flush=True)
    for j, k in enumerate(keys):
        vals = [v[j] for v in picks]
        print(f'  {k:9s} {min(vals):.4g} - {max(vals):.4g}   '
              f'ratio {max(vals)/max(min(vals),1e-9):.2f}x', flush=True)

    # consensus: median of the fold fits, applied to every test window
    cons = [statistics.median(v[j] for v in picks) for j in range(len(keys))]
    print('\nconsensus Bayes parameters on each test window:', flush=True)
    print('  ' + '  '.join(f'{k}={x:.4g}' for k, x in zip(keys, cons)), flush=True)
    cw = 0; cd = []
    for k in range(3):
        telo, tehi = cuts[k], cuts[k+1]-1
        a, _ = simulate(nm, 'Bayes', cons, telo, tehi)
        d, _ = simulate(nm, 'MR', DEPLOYED, telo, tehi)
        cw += (a > d); cd.append((a-d)*100)
        print(f'  fold {k+1}: consensus {ann(nm,a,telo,tehi)*100:6.1f}%   '
              f'MR deployed {ann(nm,d,telo,tehi)*100:6.1f}%', flush=True)
    print(f'  consensus beats MR deployed in {cw}/3; mean {statistics.mean(cd):+.1f}pp', flush=True)
    rc, tc = simulate(nm, 'Bayes', cons, 1, N-1)
    print(f'  full sample: {ann(nm,rc,1,N-1)*100:.1f}%, {tc} trades', flush=True)
    print('DONE', flush=True)
