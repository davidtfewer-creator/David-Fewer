"""
baseline_check.py — prove the restored environment reproduces the published
book before anything new is measured on it (3 Oct 2026).

The container recycle took data_5min/, data_pm/ and every delivered workbook
(HANDOVER 3.28d). The 5-minute archive came back on 3 Oct and data_pm/ was
rebuilt from it by build_pm_cache.py, whose cut convention is a RECONSTRUCTION
— the original builder is gone. So the convention has to be checked against a
number it cannot have been fitted to.

The target is the published pooled baseline for the current roster on the live
config (09:00 cutoff, 4% pre-market rule both sides), HANDOVER 3.28:

    full 72.4 / train 43.9 / test 104.9   sheet convention
    full 88.5 / train 56.4 / test 125.4   with gap exits (exec-accurate)
    maxDD 24.7

If those come back, the archive, the caches, the loaders and the engine are
all the ones the findings were measured on, and new work can stand on them.

Usage: BAYES_WORKBOOK=<workbook.xlsx> python baseline_check.py
"""
import json
import pickle

from engine import Params
from fresh_opt_cands import aw_params
from book_sim import load_all, simulate, NAMES as N8

ROSTER = [n if n != 'RKLB' else 'AVGO' for n in N8] + ['MRVL']
PUBLISHED = dict(sheet=(72.4, 43.9, 104.9), gap=(88.5, 56.4, 125.4), maxdd=24.7)


def load(cut='09:00', thr=0.04):
    t0 = Params(capital=1_000_000, comm=0.005, interest=0.0314, stop_days=50,
                bayes_pct=0.5, years=2.2, ou_W=80)
    cands = json.load(open('fresh_opt_cands.json'))
    po = {'MRVL': aw_params(cands['MRVL']['reference']['vec'], t0),
          'AVGO': aw_params(cands['AVGO']['reference']['vec'], t0)}
    data, sleeves, cal = load_all(names=ROSTER, params_override=po)
    pm = pickle.load(open('data_pm/pm_last_cuts.pkl', 'rb'))[cut]

    def pm_rule(name, i, bid):
        pml = pm.get(name, {}).get(data[name]['dts'][i])
        return pml is not None and bid < pml * (1 - thr)
    return data, sleeves, cal, pm_rule


def row(tag, r, target=None):
    got = (r['full'] * 100, r['train'] * 100, r['test'] * 100)
    line = (f'  {tag:34s} {got[0]:7.1f} {got[1]:7.1f} {got[2]:7.1f}'
            f'   DD {r["maxdd"]*100:5.1f}  fills {r["fills"]:5d}')
    if target:
        d = max(abs(a - b) for a, b in zip(got, target))
        line += f'   vs published {target[0]}/{target[1]}/{target[2]}  max diff {d:.1f}pp'
        line += '  OK' if d < 0.15 else '  <-- MISMATCH'
    print(line)
    return got


def main():
    data, sleeves, cal, pm_rule = load()
    print(f'roster {ROSTER}')
    print(f'calendar {cal[0]} to {cal[-1]} ({len(cal)} sessions)\n')
    print(f'  {"":34s} {"full":>7s} {"train":>7s} {"test":>7s}')
    row('no overlay (sheet convention)',
        simulate(data, sleeves, cal, collect_trades=True))
    r1 = simulate(data, sleeves, cal, excl_fn=pm_rule, collect_trades=True)
    row('live config: 09:00 / 4% PM rule', r1, PUBLISHED['sheet'])
    r2 = simulate(data, sleeves, cal, excl_fn=pm_rule, gap_exit=True,
                  collect_trades=True)
    row('  + gap exits (exec-accurate)', r2, PUBLISHED['gap'])
    print(f'\n  maxDD {r1["maxdd"]*100:.1f} vs published {PUBLISHED["maxdd"]}'
          f'   stops {r1["stops"]}   fills/yr {r1["fills"]/len(cal)*252:.0f}')

    print('\n  cutoff sensitivity (3.16: 09:00 best on train, 09:25 best on test):')
    for cut in ('08:30', '09:00', '09:15', '09:25'):
        d2, s2, c2, f2 = load(cut=cut)
        row(f'  {cut}', simulate(d2, s2, c2, excl_fn=f2, collect_trades=True))


if __name__ == '__main__':
    main()
