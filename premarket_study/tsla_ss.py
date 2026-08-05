"""
Does Schwartz-Smith work for TSLA specifically?

TSLA was rejected from the book -- 20% on the daily model, 17% weekly -- and then turned up as the
one name where SS beat the Bayes+OU blend in every fold of the laggard walk-forward (3/3). Three
folds on one name out of four is exactly the sort of result this work has been fooled by before,
so it gets its own file and a harder test.

Four things are fixed relative to the earlier run, all of which cut AGAINST SS:

  1. SYMMETRY OF FITTING. In the laggard test SS re-fitted seven numbers per fold (six MLE
     parameters plus the discount k) while Bayes and OU ran frozen workbook parameters. Here
     every sleeve gets exactly one P&L-fitted parameter chosen on the training window -- SS's k,
     Bayes's k, OU's buffer -- so the comparison is signal against signal, not adaptation against
     none. TSLA is also missing from BUF_RESID, so the frozen OU it was beaten by was running a
     level-fitted buffer against residual sigma: a handicapped opponent.

  2. THE NULL. bid = min(open, ATH x (1-cap)) has no signal in it at all. It is the weekly model's
     rule transplanted to daily, it fits nothing, and if it matches SS then SS's fair value is
     decoration. The weekly work showed this constraint binding 100% of the time; the binding
     column here says how often SS's own term is the one that sets the bid.

  3. MORE FOLDS. Six expanding folds instead of three, so a 3/3 cannot happen by coin-flip.

  4. THE k NEIGHBOURHOOD. A parameter that only works at the fitted value is not a parameter, it
     is a coincidence. Each fold reports the out-of-sample result across the whole k grid, so a
     lucky pick is visible as a spike rather than a plateau.

Absolute levels here are NOT comparable to the memo: this harness is a simplified replica that
reads about 8pp high on TSM. Only differences within the table mean anything.
"""
import copy, statistics, sys
import numpy as np
from ss_sleeve import DATA, PARAMS, KGRID, sleeve_run, blend, rets, corr
from ss_model import fit_ss, ss_signal
from engine import run_model

S = 'TSLA'
NFOLD = 6
BUFGRID = [round(0.1 * i, 2) for i in range(0, 26)]


def ss_bid(th, k, cap):
    dts, O, H, L, C = DATA[S]
    fair, sig = ss_signal(C, th)
    G = np.maximum.accumulate(np.array(H, dtype=float))
    out = np.full(len(C), np.nan)
    out[1:] = np.minimum(np.minimum(fair[1:] - k * sig[1:], np.array(O, dtype=float)[1:]),
                         G[:-1] * (1 - cap))
    return out, fair, sig


def eng_bid(kind, val, ou_sigma='resid'):
    dts, O, H, L, C = DATA[S]
    p = copy.copy(PARAMS[S])
    if kind == 'bayes':
        p.k = val
    else:
        p.ou_buf_k = val
    fr = run_model(dts, O, H, L, C, p, ou_sigma=ou_sigma, collect=True).frames
    src = fr['X'] if kind == 'bayes' else fr['AM']
    return np.array([x if x is not None else np.nan for x in src], dtype=float)


def null_bid(cap):
    dts, O, H, L, C = DATA[S]
    G = np.maximum.accumulate(np.array(H, dtype=float))
    out = np.full(len(C), np.nan)
    out[1:] = np.minimum(np.array(O, dtype=float)[1:], G[:-1] * (1 - cap))
    return out


def seg(eq, lo, hi):
    return (eq[hi] / eq[lo] - 1) * 100


def aseg(eq, lo, hi):
    """Annualised, so the numbers sit on the same footing as the book's figures."""
    d = (DATA[S][0][hi] - DATA[S][0][lo]).days
    return ((eq[hi] / eq[lo]) ** (365.25 / d) - 1) * 100 if d else float('nan')


def pick(build, grid, prem, trhi, floor=4):
    """Choose the one parameter on the training window only."""
    best = None
    for v in grid:
        b = build(v)
        e, t = sleeve_run(S, b, prem, lo=0, hi=trhi - 1)
        if t < floor:
            continue
        a = e[trhi - 1] / e[0]
        if best is None or a > best[0]:
            best = (a, v)
    return best[1] if best else grid[len(grid) // 2]


def main():
    dts, O, H, L, C = DATA[S]
    n = len(C)
    p = PARAMS[S]
    prem, cap = p.premium, p.peak_cap
    print(f'{S}: {n} sessions, {dts[0]} to {dts[-1]}', flush=True)
    print(f'workbook premium {prem:.4f}  peak cap {cap:.4f}  '
          f'frozen Bayes k {p.k:.3f}  frozen OU buffer {p.ou_buf_k:.3f}\n', flush=True)

    # ---------------------------------------------------------------- walk-forward
    cuts = [int(n * (0.4 + 0.1 * j)) for j in range(NFOLD + 1)]
    print('=' * 96, flush=True)
    print(f'EXPANDING WALK-FORWARD, {NFOLD} folds; every sleeve fits ONE parameter on train',
          flush=True)
    print('=' * 96, flush=True)
    print(f'{"fold":>4s}{"train":>7s}{"test":>10s}{"kappa":>7s}{"h-life":>8s}{"k":>5s}'
          f'{"SS":>8s}{"Bayes":>8s}{"OU":>8s}{"B+O":>8s}{"null":>8s}{"bind":>7s}{"winner":>9s}',
          flush=True)
    print('-' * 96, flush=True)
    wins = tot = 0
    dss = []
    thetas = []
    kgrid_oos = []
    bgrid_oos = []
    ogrid_oos = []
    folds = []
    fitted_k = []
    for j in range(NFOLD):
        trhi = cuts[j]
        telo, tehi = cuts[j], cuts[j + 1] - 1
        th, _ = fit_ss(np.log(np.array(C[:trhi], dtype=float)))
        thetas.append(th)
        kappa = th[0]
        hl = np.log(2) / kappa if kappa > 1e-8 else float('inf')

        k = pick(lambda v: ss_bid(th, v, cap)[0], KGRID, prem, trhi)
        fitted_k.append(k)
        kb = pick(lambda v: eng_bid('bayes', v), KGRID, prem, trhi)
        ko = pick(lambda v: eng_bid('ou', v), BUFGRID, prem, trhi)

        bS, fair, sig = ss_bid(th, k, cap)
        eS, _ = sleeve_run(S, bS, prem)
        eB, _ = sleeve_run(S, eng_bid('bayes', kb), prem)
        eO, _ = sleeve_run(S, eng_bid('ou', ko), prem)
        eN, _ = sleeve_run(S, null_bid(cap), prem)

        # how often is the SS term itself the binding constraint, out of sample
        G = np.maximum.accumulate(np.array(H, dtype=float))
        idx = np.arange(telo, tehi + 1)
        ssterm = fair[idx] - k * sig[idx]
        other = np.minimum(np.array(O, dtype=float)[idx], G[idx - 1] * (1 - cap))
        bind = float(np.mean(ssterm < other)) * 100

        vS, vB, vO, vN = (seg(e, telo, tehi) for e in (eS, eB, eO, eN))
        vBO = seg(blend([eB, eO]), telo, tehi)
        wins += vS > vBO
        tot += 1
        dss.append(vS - vBO)
        cands = {'SS': vS, 'Bayes': vB, 'OU': vO, 'null': vN}
        w = max(cands, key=cands.get)
        print(f'{j+1:>4d}{trhi:>7d}{telo:>5d}-{tehi:<4d}{kappa:>7.3f}{hl:>8.1f}{k:>5.1f}'
              f'{vS:>7.1f}%{vB:>7.1f}%{vO:>7.1f}%{vBO:>7.1f}%{vN:>7.1f}%{bind:>6.0f}%'
              f'{w:>9s}', flush=True)

        kgrid_oos.append([seg(sleeve_run(S, ss_bid(th, v, cap)[0], prem)[0], telo, tehi)
                          for v in KGRID])
        bgrid_oos.append([seg(sleeve_run(S, eng_bid('bayes', v), prem)[0], telo, tehi)
                          for v in KGRID])
        ogrid_oos.append([seg(sleeve_run(S, eng_bid('ou', v), prem)[0], telo, tehi)
                          for v in BUFGRID])
        folds.append((telo, tehi))
    print('-' * 96, flush=True)
    print(f'  SS alone beats Bayes+OU in {wins}/{tot} folds; mean {statistics.mean(dss):+.1f}pp',
          flush=True)

    # ---------------------------------------------------------------- k neighbourhood
    print(f'\n{"="*96}\nOUT-OF-SAMPLE RETURN ACROSS THE WHOLE k GRID (fitted k marked *)\n{"="*96}',
          flush=True)
    show = [i for i, v in enumerate(KGRID) if abs(v * 10 - round(v * 10)) < 1e-9 and
            round(v * 10) % 2 == 0]
    print(f'{"k":>6s}' + ''.join(f'{f"f{j+1}":>9s}' for j in range(NFOLD)) +
          f'{"median":>10s}', flush=True)
    for i in show:
        row = [kgrid_oos[j][i] for j in range(NFOLD)]
        print(f'{KGRID[i]:>6.1f}' + ''.join(f'{v:>8.1f}%' for v in row) +
              f'{statistics.median(row):>9.1f}%', flush=True)
    print('\nk chosen on train, by fold: ' +
          '  '.join(f'f{j+1}={v:.1f}' for j, v in enumerate(fitted_k)), flush=True)

    # ---------------------------------------------------------------- best reachable ridge
    print(f'\n{"="*96}\nCAN THE EXISTING SLEEVES BE TUNED TO DO THIS? Best out-of-sample fold '
          f'median\n{"="*96}', flush=True)
    print('For each sleeve, every parameter on its grid is scored on all six out-of-sample\n'
          'windows and the median taken. The best row is the ceiling that sleeve could reach\n'
          'even with hindsight -- nobody could have picked it in advance. If Bayes\'s ceiling\n'
          'matches SS\'s, SS is a recalibration of a sleeve the book already owns, not a new one.'
          '\n', flush=True)
    print(f'{"sleeve":9s}{"best param":>12s}{"ceiling median":>17s}{"at fitted param":>18s}',
          flush=True)
    print('-' * 96, flush=True)
    for label, grid, mat, chosen in (('SS', KGRID, kgrid_oos, fitted_k),
                                     ('Bayes', KGRID, bgrid_oos, None),
                                     ('OU', BUFGRID, ogrid_oos, None)):
        meds = [statistics.median([mat[j][i] for j in range(NFOLD)]) for i in range(len(grid))]
        bi = max(range(len(grid)), key=lambda i: meds[i])
        at = (statistics.median([mat[j][grid.index(chosen[j])] for j in range(NFOLD)])
              if chosen else float('nan'))
        print(f'{label:9s}{grid[bi]:>12.1f}{meds[bi]:>16.1f}%'
              + (f'{at:>17.1f}%' if chosen else f'{"n/a":>18s}'), flush=True)

    # ---------------------------------------------------------------- exposure matching
    th_full, _ = fit_ss(np.log(np.array(C, dtype=float)))
    print(f'\n{"="*96}\nIS THE EDGE JUST SELECTIVITY? Return against time spent holding stock'
          f'\n{"="*96}', flush=True)
    print('Descriptive, whole sample, SS fitted in sample -- the returns here are not evidence,\n'
          'the exposure column is. If SS only wins because it sits in cash, Bayes tuned to the\n'
          'same exposure should win too.\n', flush=True)
    print(f'{"sleeve":9s}{"param":>7s}{"held":>7s}{"trades":>8s}{"full ann":>11s}', flush=True)
    print('-' * 96, flush=True)
    for label, grid, build in (('SS', KGRID, lambda v: ss_bid(th_full, v, cap)[0]),
                               ('Bayes', KGRID, lambda v: eng_bid('bayes', v)),
                               ('OU', BUFGRID, lambda v: eng_bid('ou', v))):
        for v in grid:
            if abs(v * 10 - round(v * 10)) > 1e-9 or round(v * 10) % 5:
                continue
            e, t, m = sleeve_run(S, build(v), prem, with_mask=True)
            print(f'{label:9s}{v:>7.1f}{m.mean()*100:>6.0f}%{t:>8d}{aseg(e,0,n-1):>10.1f}%',
                  flush=True)

    # ---------------------------------------------------------------- MLE stability
    print(f'\n{"="*96}\nFITTED STATE-SPACE PARAMETERS BY FOLD (stability of the model itself)'
          f'\n{"="*96}', flush=True)
    nm = ['kappa', 'sig_chi', 'sig_xi', 'mu', 'rho', 'sig_v']
    print(f'{"param":>9s}' + ''.join(f'{f"fold {j+1}":>11s}' for j in range(NFOLD)) +
          f'{"spread":>11s}', flush=True)
    for i, name in enumerate(nm):
        row = [t[i] for t in thetas]
        sp = max(row) - min(row)
        print(f'{name:>9s}' + ''.join(f'{v:>11.4f}' for v in row) + f'{sp:>11.4f}', flush=True)
    hl = [np.log(2) / t[0] for t in thetas]
    print(f'{"half-life":>9s}' + ''.join(f'{v:>11.1f}' for v in hl) +
          f'{max(hl)-min(hl):>11.1f}', flush=True)

    # ---------------------------------------------------------------- full / half sample
    print(f'\n{"="*96}\nFULL SAMPLE AND HALF-SAMPLE SPLIT (all parameters fitted on the FIRST '
          f'half only)\n{"="*96}', flush=True)
    half = int(n * 0.5)
    th, _ = fit_ss(np.log(np.array(C[:half], dtype=float)))
    k = pick(lambda v: ss_bid(th, v, cap)[0], KGRID, prem, half)
    kb = pick(lambda v: eng_bid('bayes', v), KGRID, prem, half)
    ko = pick(lambda v: eng_bid('ou', v), BUFGRID, prem, half)
    curves = {
        'SS': sleeve_run(S, ss_bid(th, k, cap)[0], prem, with_mask=True),
        'Bayes': sleeve_run(S, eng_bid('bayes', kb), prem, with_mask=True),
        'OU': sleeve_run(S, eng_bid('ou', ko), prem, with_mask=True),
        'null': sleeve_run(S, null_bid(cap), prem, with_mask=True),
    }
    print(f'{"sleeve":9s}{"param":>8s}{"trades":>7s}{"held":>7s}{"full ann":>11s}'
          f'{"train half":>13s}{"tested half":>14s}{"max DD":>9s}', flush=True)
    print('-' * 96, flush=True)
    eq, hold = {}, {}
    for nmn, (e, t, m) in curves.items():
        eq[nmn], hold[nmn] = e, m
        dd = float(np.max(1 - e / np.maximum.accumulate(e))) * 100
        pv = {'SS': k, 'Bayes': kb, 'OU': ko, 'null': float('nan')}[nmn]
        print(f'{nmn:9s}{pv:>8.1f}{t:>7d}{m.mean()*100:>6.0f}%{aseg(e,0,n-1):>10.1f}%'
              f'{aseg(e,0,half-1):>12.1f}%{aseg(e,half,n-1):>13.1f}%{dd:>8.1f}%', flush=True)
    bo = blend([eq['Bayes'], eq['OU']])
    b3 = blend([eq['Bayes'], eq['OU'], eq['SS']])
    for nmn, e in (('B+O', bo), ('B+O+SS', b3)):
        dd = float(np.max(1 - e / np.maximum.accumulate(e))) * 100
        print(f'{nmn:9s}{"":>8s}{"":>7s}{"":>7s}{aseg(e,0,n-1):>10.1f}%'
              f'{aseg(e,0,half-1):>12.1f}%{aseg(e,half,n-1):>13.1f}%{dd:>8.1f}%', flush=True)

    # ------------------------------------------------------- what the harness reads high by
    ed, td = sleeve_run(S, eng_bid('bayes', p.k, ou_sigma='level'), prem)
    eu, tu = sleeve_run(S, eng_bid('ou', p.ou_buf_k, ou_sigma='level'), prem)
    dep = blend([ed, eu])
    print(f'\ndeployed configuration through THIS harness (frozen workbook parameters, level '
          f'sigma):\n  Bayes {aseg(ed,0,n-1):.1f}%  OU {aseg(eu,0,n-1):.1f}%  '
          f'50/50 {aseg(dep,0,n-1):.1f}% annualised, against the ~20% the full engine gives for '
          f'TSLA.\n  Subtract that gap from every figure above before comparing with the memo.',
          flush=True)

    # ---------------------------------------------------------------- correlation
    print(f'\n{"="*96}\nDAILY-RETURN CORRELATION (a third sleeve only pays if it is '
          f'decorrelated)\n{"="*96}', flush=True)
    keys = ['SS', 'Bayes', 'OU', 'null']
    print('all sessions (cash days included, which drags every pair towards zero):', flush=True)
    print(f'{"":9s}' + ''.join(f'{a:>9s}' for a in keys), flush=True)
    for a in keys:
        print(f'{a:9s}' + ''.join(f'{corr(rets(eq[a]), rets(eq[b])):>9.2f}' for b in keys),
              flush=True)

    print('\nboth sleeves actually holding stock -- the number that matters for diversification:',
          flush=True)
    print(f'{"":9s}' + ''.join(f'{a:>9s}' for a in keys), flush=True)
    for a in keys:
        row = ''
        for b in keys:
            m = hold[a][1:] & hold[b][1:]
            ra, rb = rets(eq[a]), rets(eq[b])
            row += (f'{corr(ra[m], rb[m]):>9.2f}' if m.sum() > 5 else f'{"-":>9s}')
        print(f'{a:9s}{row}', flush=True)

    print('', flush=True)
    for a in keys:
        print(f'  {a:6s} holding stock on {hold[a].mean()*100:.0f}% of sessions', flush=True)
    ov = (hold['SS'] & (hold['Bayes'] | hold['OU'])).sum() / max(hold['SS'].sum(), 1) * 100
    print(f'  SS holds stock at the same time as Bayes or OU on {ov:.0f}% of its own held days',
          flush=True)
    print('\nDONE', flush=True)


if __name__ == '__main__':
    main()
