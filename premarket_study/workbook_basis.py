"""
Reconcile the workbook's own Annual return cell with the planning figure.

The live workbook reports 143% for TSM and 508% for RKLB on its Model sheets. The planning basis
says 55% and 156%. Both are arithmetically correct; they answer different questions, and only one
of them is a forecast.

Three things separate them, and this script sizes each:

  1. SAME-DAY FILL VERIFICATION. The sheet books a round trip whenever the day's low reaches the
     bid AND the day's high reaches the target, with no way to know the low came first. On a name
     trading a 3% daily range against a 1.6% premium that is a large share of all trades. The
     study checks every such day against 5-minute bars and keeps the trade only if the sequence
     actually occurred. The sheet cannot do this -- it has daily bars only -- which is a
     limitation of the medium, not an error in the formulas.

  2. THE HARD-CODED 2.2. Cell Y5 annualises with ^(1/2.2). The feed now runs to 2026-08-03, which
     is 2.34 years, so the exponent flatters every name slightly.

  3. IN SAMPLE AGAINST OUT OF SAMPLE. The sheet scores the same sessions the parameters were
     fitted on. The planning figure carries the walk-forward haircut on the Bayes tilt.

The output is the bridge to put in the memo, so nobody reads Y5 as a return expectation.
"""
import copy, datetime
import openpyxl
from engine import run_model
from daily_window_split import data, params
from five_min import make_checker as fm
from mu_rerun import from_workbook

data['MU'] = from_workbook()
DAILY = ['RKLB', 'TSM', 'VST', 'VRT', 'MU']
BUF = {'RKLB': 0.25, 'TSM': 0.20, 'VST': 0.65, 'VRT': 0.40, 'MU': 0.75}
PLAN = {'RKLB': 156, 'TSM': 55, 'VST': 60, 'VRT': 65, 'MU': 61}
WB = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
      'ca376547-TradingExcel_5stock_live.xlsx')
CHK = {}


def chk(s):
    if s not in CHK: CHK[s] = fm(s, data[s][0], data[s][1])[0]
    return CHK[s]


def ann(eq, dts):
    d = (dts[-1] - dts[0]).days
    return ((eq[-1]/eq[0])**(365.25/d) - 1)*100


def curve(s, mode):
    """mode: 'sheet' allows every same-day round trip, as the Model sheet does;
    'verified' keeps only those 5-minute bars confirm; 'none' allows none."""
    dts, O, H, L, C = data[s]
    p = copy.copy(params[s]); p.bayes_pct = 0.5; p.ou_buf_k = BUF[s]
    p.years = (dts[-1]-dts[0]).days/365.25
    sde = {'sheet': True, 'verified': chk(s), 'none': None}[mode]
    r = run_model(dts, O, H, L, C, p, ou_sigma='resid', collect=True, same_day_exit=sde)
    return dts, r.frames['equity']


if __name__ == '__main__':
    wb = openpyxl.load_workbook(WB, data_only=True)
    print(f'{"stock":7s}{"sheet Y5":>10s}{"engine, sheet rule":>20s}{"verified":>10s}'
          f'{"no same-day":>13s}{"planning":>10s}', flush=True)
    print('-'*72, flush=True)
    for s in DAILY:
        y5 = wb[f'Model {s}']['Y5'].value*100
        a = {m: ann(*curve(s, m)[::-1]) for m in ('sheet', 'verified', 'none')}
        print(f'{s:7s}{y5:>9.0f}%{a["sheet"]:>19.0f}%{a["verified"]:>9.0f}%'
              f'{a["none"]:>12.0f}%{PLAN[s]:>9d}%', flush=True)
    print('-'*72, flush=True)
    dts = data['TSM'][0]
    yrs = (dts[-1]-dts[0]).days/365.25
    print(f'\nstudy sample {dts[0]} to {dts[-1]} = {yrs:.2f} years; '
          f'the sheet annualises with 2.2.', flush=True)
    f = wb['Feed TSM']
    rows = [r[0] for r in f.iter_rows(min_row=2, values_only=True)
            if isinstance(r[4], (int, float)) and r[4] > 0]
    print(f'workbook feed {rows[0].date()} to {rows[-1].date()} = {len(rows)} sessions '
          f'= {(rows[-1]-rows[0]).days/365.25:.2f} years.', flush=True)
    print('DONE', flush=True)
