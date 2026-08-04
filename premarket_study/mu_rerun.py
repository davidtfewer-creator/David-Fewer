"""
Re-run MU's daily model on the corrected and extended price history.

The workbook MU was originally scored on ran to 24 June 2026 and had a part-session value for
that last day. It now runs to 3 August 2026 with 24 June rebuilt, which adds 27 sessions covering
a fall from about 1233 to 739 -- a period the earlier figures never saw.

Reported on three bases so the change is separable from the change in horizon:
  * the workbook's fixed 2.2-year annualisation, matching every MU figure quoted so far
  * the true span of each sample
  * the old window alone (to 24 June) on the corrected data, which isolates the 24 June repair
Same-day exits are verified against MU's 5-minute bars throughout.
"""
import copy, datetime, openpyxl
from engine import run_model
from newcands import load as load_cand
import five_min

five_min.FILES['MU'] = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
                        '94f1080f-MU_5min_Apr2024Aug2026.xlsx')
BOOK = '/home/user/David-Fewer/TradingExcel_5stock_MUfilled.xlsx'


def to_date(v):
    if isinstance(v, datetime.datetime): return v.date()
    if isinstance(v, datetime.date): return v
    if isinstance(v, (int, float)):
        return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))
    return None


def from_workbook():
    wb = openpyxl.load_workbook(BOOK, data_only=True)
    q = wb['Query']
    dts, O, H, L, C = [], [], [], [], []
    for r in range(2, q.max_row + 1):
        o = q.cell(r, 18).value
        if not isinstance(o, (int, float)) or o <= 0: continue
        dts.append(to_date(q.cell(r, 1).value)); O.append(o)
        H.append(q.cell(r, 19).value); L.append(q.cell(r, 20).value)
        C.append(q.cell(r, 21).value)
    return dts, O, H, L, C


def run(dts, O, H, L, C, p0, bayes, years, chk):
    p = copy.copy(p0); p.bayes_pct = bayes; p.years = years
    return run_model(dts, O, H, L, C, p, collect=True, same_day_exit=chk)


if __name__ == '__main__':
    odts, oO, oH, oL, oC, p0, _ = load_cand('MU')          # the original series
    ndts, nO, nH, nL, nC = from_workbook()                 # corrected and extended
    print(f'original : {len(odts)} sessions {odts[0]} -> {odts[-1]}')
    print(f'corrected: {len(ndts)} sessions {ndts[0]} -> {ndts[-1]}\n')

    chk_o = five_min.make_checker('MU', odts, oO)[0]
    chk_n = five_min.make_checker('MU', ndts, nO)[0]
    span_o = (odts[-1] - odts[0]).days/365.25
    span_n = (ndts[-1] - ndts[0]).days/365.25

    # the old window on corrected data, to isolate the 24 June repair
    k = max(i for i, d in enumerate(ndts) if d <= odts[-1]) + 1
    cdts, cO, cH, cL, cC = ndts[:k], nO[:k], nH[:k], nL[:k], nC[:k]
    chk_c = five_min.make_checker('MU', cdts, cO)[0]

    print(f'{"basis":34s}{"50/50":>9s}{"75% Bayes":>12s}{"Sharpe":>9s}{"maxDD":>8s}'
          f'{"buys":>7s}{"stops":>7s}', flush=True)
    print('-'*86)
    cases = [
        ('original, to 24 Jun (2.2y conv)', odts, oO, oH, oL, oC, 2.2, chk_o),
        ('corrected, to 24 Jun (2.2y conv)', cdts, cO, cH, cL, cC, 2.2, chk_c),
        ('corrected + extended (2.2y conv)', ndts, nO, nH, nL, nC, 2.2, chk_n),
        ('original, own span', odts, oO, oH, oL, oC, span_o, chk_o),
        ('corrected + extended, own span', ndts, nO, nH, nL, nC, span_n, chk_n),
    ]
    for lbl, d, o, h, l, c, y, chk in cases:
        a = run(d, o, h, l, c, p0, 0.5, y, chk)
        b = run(d, o, h, l, c, p0, 0.75, y, chk)
        print(f'{lbl:34s}{a.annual_return*100:>8.0f}%{b.annual_return*100:>11.0f}%'
              f'{b.sharpe:>9.2f}{b.max_drawdown*100:>7.0f}%{b.total_buys:>7d}'
              f'{b.stop_loss_exits:>7d}', flush=True)

    # what the added month did on its own
    print('\nthe added month alone (25 Jun - 3 Aug, 75% Bayes, verified):', flush=True)
    r = run(ndts, nO, nH, nL, nC, p0, 0.75, span_n, chk_n)
    eq = r.frames['equity']
    seg = eq[len(ndts)-1]/eq[k-1] - 1
    print(f'  equity {eq[k-1]:,.0f} -> {eq[len(ndts)-1]:,.0f}   {seg*100:+.1f}% over 27 sessions',
          flush=True)
    print(f'  MU close {nC[k-1]:,.2f} -> {nC[-1]:,.2f}   {(nC[-1]/nC[k-1]-1)*100:+.1f}%', flush=True)
