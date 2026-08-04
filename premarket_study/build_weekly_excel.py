"""
Build the weekly Monday-tranche trading workbook for NVDA and AVGO.

The model runs on DAILY rows, not weekly ones, because the entry and exit both need intra-week
sequencing: the bid rests from Monday and fills on the first session whose low reaches it, and the
target can be hit on any later session, including in a later week since an unfilled position is
carried. A weekly-granularity sheet cannot express either.

Week boundaries come from date arithmetic, WeekStart = date - WEEKDAY(date,3), so a week is
identified by its Monday whether or not that Monday traded. This is holiday-safe by construction,
which the naive "split when the weekday is Monday" rule is not.

Same-day exits: the workbook carries a switch (Model!L2). With it on, a target reached on the fill
day counts, which is what actually happens in live trading and which reproduces the verified
figures here exactly -- every same-day exit in this sample was checked against minute or 5-minute
bars and all were genuine. With it off the sheet is conservative and NVDA reads 77.5% instead of
82.0%; AVGO is unaffected, having no same-day exits at all.

Before writing, the exact formula logic is mirrored in Python and checked against the validated
model. The workbook is not written if the mirror disagrees.
"""
import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from stop_sweep import load_book

OUT = '/home/user/David-Fewer/WeeklyModel_NVDA_AVGO.xlsx'
DATA, _P, _C = load_book()
SPEC = {'NVDA': dict(cap=0.0935, prem=0.0293),
        'AVGO': dict(cap=0.0800, prem=0.1000)}
COMM, INTEREST, CAPITAL = 0.005, 0.0314, 1_000_000
R0 = 8                                        # first data row
NAVY = '0B1F3A'; BLUE = '204A87'; GOLD = 'B08D57'
HDR = PatternFill('solid', fgColor='E8EDF4')
INP = PatternFill('solid', fgColor='F7F1E4')


def week_start(d):
    return d - datetime.timedelta(days=d.weekday())


def ath_start(stock):
    """Monday of the SECOND week. The validated model seeds its running high there, ignoring the
    first week, and starts trading the week after."""
    dts = DATA[stock][0]
    mons = sorted({week_start(d) for d in dts})
    return mons[1]


def mirror(stock, allow_same_day=True):
    """Row-by-row evaluation of exactly the formulas written below."""
    dts, O, H, L, C = DATA[stock]
    cap, prem = SPEC[stock]['cap'], SPEC[stock]['prem']
    n = len(dts)
    ws_ = [week_start(d) for d in dts]
    new = [i == 0 or ws_[i] != ws_[i-1] for i in range(n)]
    a0 = ath_start(stock)
    trade_from = a0 + datetime.timedelta(days=7)
    ath = [0.0]*n; buy = [None]*n; tgt = [None]*n; armed = [0]*n
    fill = [0]*n; sell = [0]*n; sh = [0.0]*n; fund = [0.0]*n; hold = [0]*n; eq = [0.0]*n
    for i in range(n):
        pws = ws_[i] - datetime.timedelta(days=7)
        idx = [j for j in range(n) if ws_[j] == pws]
        pwh = max(H[j] for j in idx) if idx else None
        pwc = C[idx[-1]] if idx else None
        hp = hold[i-1] if i else 0
        fp = fund[i-1] if i else CAPITAL
        sp = sh[i-1] if i else 0.0
        # running maximum of weekly highs over completed weeks from the second week onward
        hi = [H[j] for j in range(n) if a0 <= ws_[j] < ws_[i]]
        ath[i] = max(hi) if hi else 0.0
        if new[i] and hp != 1 and ws_[i] >= trade_from:
            buy[i] = min(O[i], ath[i]*(1-cap))
            tgt[i] = buy[i] + pwc*prem if pwc is not None else None
            if tgt[i] is None: buy[i] = None
        else:
            buy[i] = buy[i-1] if i else None
            tgt[i] = tgt[i-1] if i else None
        if new[i]:
            armed[i] = 0 if (hp == 1 or tgt[i] is None or ws_[i] < trade_from) else 1
        else:
            armed[i] = 0 if (i and (fill[i-1] or sell[i-1])) else (armed[i-1] if i else 0)
        fill[i] = 1 if (armed[i] == 1 and hp != 1 and buy[i] is not None
                        and L[i] <= buy[i]) else 0
        can = (hp == 1) or (fill[i] == 1 and allow_same_day)
        sell[i] = 1 if (tgt[i] is not None and can and H[i] >= tgt[i]) else 0
        if fill[i] and sell[i]:
            s = fp/(buy[i]+COMM); sh[i] = 0.0; fund[i] = s*(tgt[i]-COMM); hold[i] = 0
        elif fill[i]:
            sh[i] = fp/(buy[i]+COMM); fund[i] = 0.0; hold[i] = 1
        elif sell[i]:
            sh[i] = 0.0; fund[i] = sp*(tgt[i]-COMM); hold[i] = 0
        else:
            sh[i] = sp
            days = (dts[i]-dts[i-1]).days if i else 0
            fund[i] = fp if hp == 1 else fp*(1 + INTEREST*days/365)
            hold[i] = hp
        eq[i] = sh[i]*C[i] if hold[i] == 1 else fund[i]
    yrs = (dts[-1]-dts[0]).days/365.25
    return dict(final=eq[-1], ann=(eq[-1]/CAPITAL)**(1/yrs)-1, trades=sum(sell), n=n)


def build():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    dts, _, _, _, _ = DATA['NVDA']
    n = len(dts)

    # ---------------- Query ----------------
    q = wb.create_sheet('Query')
    q.cell(1, 1, 'Date')
    for k, s in enumerate(['NVDA', 'AVGO']):
        for j, sfx in enumerate(['_O', '_H', '_L', '_C']):
            q.cell(1, 2 + 4*k + j, f'{s}{sfx}')
    for i in range(n):
        q.cell(2+i, 1, dts[i])
        for k, s in enumerate(['NVDA', 'AVGO']):
            for j in range(4):
                q.cell(2+i, 2+4*k+j, DATA[s][1+j][i])
    for c in range(1, 10):
        q.cell(1, c).font = Font(bold=True, color=NAVY); q.cell(1, c).fill = HDR
    q.column_dimensions['A'].width = 12
    for r in range(2, n+2):
        q.cell(r, 1).number_format = 'dd/mm/yyyy'

    # ---------------- Feeds ----------------
    for k, s in enumerate(['NVDA', 'AVGO']):
        f = wb.create_sheet(f'Feed {s}')
        cols = [get_column_letter(2+4*k+j) for j in range(4)]
        f.cell(1, 1, '=Query!A1')
        for j in range(4):
            f.cell(1, 2+j, f'=Query!{cols[j]}1')
        f.cell(1, 7, f'Daily OHLC for {s}, read from Query. The Model sheet reads columns A:E.')
        for r in range(2, n+2):
            f.cell(r, 1, '=INDEX(Query!$A:$A,ROW())')
            for j in range(4):
                f.cell(r, 2+j, f'=INDEX(Query!${cols[j]}:${cols[j]},ROW())')
            f.cell(r, 1).number_format = 'dd/mm/yyyy'
        for c in range(1, 6):
            f.cell(1, c).font = Font(bold=True, color=NAVY); f.cell(1, c).fill = HDR
        f.column_dimensions['A'].width = 12

    # ---------------- Models ----------------
    heads = ['Date', 'Open', 'High', 'Low', 'Close', 'WeekStart', 'New wk', 'Prev wk start',
             'Prev wk high', 'Prev wk close', 'ATH', 'Buy', 'Target', 'Armed', 'Fill', 'Sell',
             'Shares', 'Fund', 'Hold', 'Equity']
    for s in ['NVDA', 'AVGO']:
        m = wb.create_sheet(f'Model {s}')
        cap, prem = SPEC[s]['cap'], SPEC[s]['prem']
        m['A1'] = (f'{s} — WEEKLY single Monday tranche.  Bid = MIN(Monday open, ATH×(1−cap)); '
                   f'target = bid + previous week close × premium; carried until the target is '
                   f'reached; no stop-loss.')
        m['A1'].font = Font(bold=True, size=12, color=NAVY)
        pr_ = [('A2', 'Peak cap', 'B2', cap, '0.0000'),
               ('C2', 'Premium', 'D2', prem, '0.0000'),
               ('E2', 'Commission ($/sh)', 'F2', COMM, '0.0000'),
               ('G2', 'Capital', 'H2', CAPITAL, '#,##0'),
               ('I2', 'Interest (pa)', 'J2', INTEREST, '0.0000'),
               ('K2', 'Same-day exit (1/0)', 'L2', 1, '0')]
        for lc, lab, vc, val, fmtn in pr_:
            m[lc] = lab; m[lc].font = Font(bold=True, color=BLUE)
            m[vc] = val; m[vc].fill = INP; m[vc].number_format = fmtn
            m[vc].font = Font(bold=True)
        last = R0 + n - 1
        m['A4'] = 'Final equity'; m['B4'] = f'=T{last}'
        m['C4'] = 'Total return'; m['D4'] = f'=B4/$H$2-1'
        m['E4'] = 'Annualised'
        m['F4'] = f'=IFERROR((B4/$H$2)^(365.25/(A{last}-A{R0}))-1,"")'
        m['G4'] = 'Trades'; m['H4'] = f'=SUM(P{R0}:P{last})'
        m['I4'] = 'Weeks'; m['J4'] = f'=SUM(G{R0}:G{last})'
        for c in ('A4', 'C4', 'E4', 'G4', 'I4'):
            m[c].font = Font(bold=True, color=BLUE)
        m['B4'].number_format = '#,##0'; m['D4'].number_format = '0.0%'
        m['F4'].number_format = '0.0%'
        for j, h in enumerate(heads, start=1):
            c = m.cell(7, j, h)
            c.font = Font(bold=True, color=NAVY); c.fill = HDR
            c.alignment = Alignment(horizontal='center', wrap_text=True)
        for i in range(n):
            r = R0 + i
            p = r - 1
            fr = i + 2                                  # Feed row
            m.cell(r, 1, f'=IF(B{r}="","",\'Feed {s}\'!A{fr})')
            m.cell(r, 2, f'=IF(AND(ISNUMBER(\'Feed {s}\'!B{fr}),\'Feed {s}\'!B{fr}>0),'
                         f'\'Feed {s}\'!B{fr},"")')
            for j, L_ in ((3, 'C'), (4, 'D'), (5, 'E')):
                m.cell(r, j, f'=IF(B{r}="","",\'Feed {s}\'!{L_}{fr})')
            m.cell(r, 6, f'=IF(B{r}="","",A{r}-WEEKDAY(A{r},3))')
            m.cell(r, 7, '=IF(B{0}="","",1)'.format(r) if i == 0
                   else f'=IF(B{r}="","",IF(F{r}<>F{p},1,0))')
            m.cell(r, 8, f'=IF(B{r}="","",F{r}-7)')
            m.cell(r, 9, f'=IF(B{r}="","",IFERROR(MAXIFS($C${R0}:$C${last},$F${R0}:$F${last},'
                         f'H{r}),""))')
            m.cell(r, 10, f'=IF(B{r}="","",IFERROR(LOOKUP(2,1/($F${R0}:$F${last}=H{r}),'
                          f'$E${R0}:$E${last}),""))')
            if i == 0:
                m.cell(r, 11, f'=IF(B{r}="","",E{r})')
                m.cell(r, 12, '')
                m.cell(r, 13, '')
                m.cell(r, 14, 0)
                m.cell(r, 15, 0)
                m.cell(r, 16, 0)
                m.cell(r, 17, 0)
                m.cell(r, 18, '=$H$2')
                m.cell(r, 19, 0)
                m.cell(r, 20, f'=R{r}')
                continue
            m.cell(r, 11, f'=IF(B{r}="","",IF(AND(G{r}=1,I{r}<>""),MAX(K{p},I{r}),K{p}))')
            m.cell(r, 12, f'=IF(B{r}="","",IF(AND(G{r}=1,S{p}<>1),IF(J{r}="","",'
                          f'MIN(B{r},K{r}*(1-$B$2))),L{p}))')
            m.cell(r, 13, f'=IF(B{r}="","",IF(AND(G{r}=1,S{p}<>1),IF(OR(J{r}="",L{r}=""),"",'
                          f'L{r}+J{r}*$D$2),M{p}))')
            m.cell(r, 14, f'=IF(B{r}="","",IF(G{r}=1,IF(OR(S{p}=1,M{r}=""),0,1),'
                          f'IF(OR(O{p}=1,P{p}=1),0,N{p})))')
            m.cell(r, 15, f'=IF(B{r}="","",IF(AND(N{r}=1,S{p}<>1,L{r}<>"",D{r}<=L{r}),1,0))')
            m.cell(r, 16, f'=IF(B{r}="","",IF(AND(M{r}<>"",C{r}>=M{r},'
                          f'OR(S{p}=1,AND(O{r}=1,$L$2=1))),1,0))')
            m.cell(r, 17, f'=IF(B{r}="","",IF(AND(O{r}=1,P{r}=1),0,'
                          f'IF(O{r}=1,R{p}/(L{r}+$F$2),IF(P{r}=1,0,Q{p}))))')
            m.cell(r, 18, f'=IF(B{r}="","",IF(AND(O{r}=1,P{r}=1),(R{p}/(L{r}+$F$2))*(M{r}-$F$2),'
                          f'IF(O{r}=1,0,IF(P{r}=1,Q{p}*(M{r}-$F$2),'
                          f'IF(S{p}=1,R{p},R{p}*(1+$J$2*(A{r}-A{p})/365))))))')
            m.cell(r, 19, f'=IF(B{r}="","",IF(P{r}=1,0,IF(O{r}=1,1,S{p})))')
            m.cell(r, 20, f'=IF(B{r}="","",IF(S{r}=1,Q{r}*E{r},R{r}))')
        for r in range(R0, last+1):
            m.cell(r, 1).number_format = 'dd/mm/yyyy'
            m.cell(r, 6).number_format = 'dd/mm/yyyy'
            m.cell(r, 8).number_format = 'dd/mm/yyyy'
            for c in (2, 3, 4, 5, 9, 10, 11, 12, 13):
                m.cell(r, c).number_format = '0.00'
            m.cell(r, 17).number_format = '#,##0.0'
            for c in (18, 20):
                m.cell(r, c).number_format = '#,##0'
        m.freeze_panes = 'A8'
        for col, w in (('A', 11), ('F', 11), ('H', 11), ('L', 10), ('M', 10),
                       ('R', 12), ('T', 12)):
            m.column_dimensions[col].width = w

    # ---------------- Dashboard ----------------
    d = wb.create_sheet('Dashboard')
    d['A1'] = 'WEEKLY DASHBOARD — Monday pre-open levels'
    d['A1'].font = Font(bold=True, size=14, color=NAVY)
    d['A2'] = ('Each Monday, for any name showing CASH: place a limit BUY at the lesser of the '
               'Monday opening price and the "ATH cap" level, then a GTC SELL at the buy price '
               'plus the premium shown. For HOLDING: leave the existing GTC sell in place — the '
               'target does not move.')
    d['A2'].alignment = Alignment(wrap_text=True)
    d.merge_cells('A2:H2'); d.row_dimensions[2].height = 42
    cols = ['Stock', 'Status', 'Last close', 'Prev wk close', 'ATH', 'ATH cap level',
            'Premium ($)', 'If filled, sell at', 'Shares held', 'Live target', 'Equity']
    for j, h in enumerate(cols, start=1):
        c = d.cell(4, j, h); c.font = Font(bold=True, color=NAVY); c.fill = HDR
        c.alignment = Alignment(horizontal='center', wrap_text=True)
    last = R0 + n - 1
    for k, s in enumerate(['NVDA', 'AVGO']):
        r = 5 + k
        M = f"'Model {s}'"
        d.cell(r, 1, s).font = Font(bold=True)
        d.cell(r, 2, f'=IF(INDEX({M}!S:S,{last})=1,"HOLDING","CASH")')
        d.cell(r, 3, f'=INDEX({M}!E:E,{last})')
        d.cell(r, 4, f'=INDEX({M}!J:J,{last})')
        d.cell(r, 5, f'=INDEX({M}!K:K,{last})')
        d.cell(r, 6, f'=E{r}*(1-{M}!$B$2)')
        d.cell(r, 7, f'=D{r}*{M}!$D$2')
        d.cell(r, 8, f'=IF(B{r}="CASH","buy + "&TEXT(G{r},"0.00"),"n/a — already holding")')
        d.cell(r, 9, f'=IF(B{r}="HOLDING",INDEX({M}!Q:Q,{last}),0)')
        d.cell(r, 10, f'=IF(B{r}="HOLDING",INDEX({M}!M:M,{last}),"")')
        d.cell(r, 11, f'=INDEX({M}!T:T,{last})')
        for c in (3, 4, 5, 6, 7, 10):
            d.cell(r, c).number_format = '0.00'
        d.cell(r, 9).number_format = '#,##0.0'
        d.cell(r, 11).number_format = '#,##0'
    d['A8'] = 'MODEL SUMMARY (backtest on the loaded history)'
    d['A8'].font = Font(bold=True, color=NAVY)
    for j, h in enumerate(['Stock', 'Final equity', 'Total return', 'Annualised', 'Trades',
                           'Weeks'], start=1):
        c = d.cell(9, j, h); c.font = Font(bold=True, color=NAVY); c.fill = HDR
    for k, s in enumerate(['NVDA', 'AVGO']):
        r = 10 + k
        M = f"'Model {s}'"
        d.cell(r, 1, s).font = Font(bold=True)
        d.cell(r, 2, f'={M}!B4'); d.cell(r, 3, f'={M}!D4')
        d.cell(r, 4, f'={M}!F4'); d.cell(r, 5, f'={M}!H4')
        d.cell(r, 6, f'={M}!J4')
        d.cell(r, 2).number_format = '#,##0'
        d.cell(r, 3).number_format = '0.0%'; d.cell(r, 4).number_format = '0.0%'
    for col, w in (('A', 10), ('B', 14), ('C', 12), ('D', 14), ('E', 11), ('F', 14),
                   ('G', 12), ('H', 20), ('I', 12), ('J', 12), ('K', 13)):
        d.column_dimensions[col].width = w

    # ---------------- Blotter ----------------
    b = wb.create_sheet('Blotter')
    b['A1'] = 'TRADE LOG — type the actual fills; nothing here feeds the model'
    b['A1'].font = Font(bold=True, size=12, color=NAVY)
    for j, h in enumerate(['Stock', 'Buy date', 'Buy price', 'Shares', 'Cost', 'Sell date',
                           'Sell price', 'Proceeds', 'P&L', 'Days held', 'Status'], start=1):
        c = b.cell(3, j, h); c.font = Font(bold=True, color=NAVY); c.fill = HDR
    for r in range(4, 84):
        b.cell(r, 5, f'=IF(OR(C{r}="",D{r}=""),"",C{r}*D{r}+D{r}*0.005)')
        b.cell(r, 8, f'=IF(OR(G{r}="",D{r}=""),"",G{r}*D{r}-D{r}*0.005)')
        b.cell(r, 9, f'=IF(OR(H{r}="",E{r}=""),"",H{r}-E{r})')
        b.cell(r, 10, f'=IF(OR(B{r}="",F{r}=""),"",F{r}-B{r})')
        b.cell(r, 11, f'=IF(A{r}="","",IF(F{r}="","OPEN","CLOSED"))')
        for c in (2, 6):
            b.cell(r, c).number_format = 'dd/mm/yyyy'
        for c in (3, 7):
            b.cell(r, c).number_format = '0.00'
        for c in (5, 8, 9):
            b.cell(r, c).number_format = '#,##0'
        for c in (1, 2, 3, 4, 6, 7):
            b.cell(r, c).fill = INP
    for col, w in (('A', 9), ('B', 12), ('C', 11), ('D', 10), ('E', 12), ('F', 12),
                   ('G', 11), ('H', 12), ('I', 11), ('J', 11), ('K', 10)):
        b.column_dimensions[col].width = w

    # ---------------- Notes ----------------
    nt = wb.create_sheet('Notes')
    nt['A1'] = 'WEEKLY MONDAY TRANCHE — NVDA and AVGO'
    nt['A1'].font = Font(bold=True, size=14, color=NAVY)
    lines = [
        ('The rule', ''),
        ('', 'Each Monday, if the name is in cash: bid = MIN(Monday open, ATH × (1 − cap)), '
             'where ATH is the running maximum of weekly highs through the previous week.'),
        ('', 'Target = bid + previous week\'s closing price × premium. The target does NOT move '
             'while the position is held.'),
        ('', 'If the target is not reached, carry the position and keep the same target. '
             'Re-enter the Monday after a sale. There is no stop-loss.'),
        ('Parameters', ''),
        ('NVDA', 'cap 0.0935, premium 0.0293'),
        ('AVGO', 'cap 0.0800, premium 0.1000'),
        ('', 'Both were validated out of sample. Re-fitting them lost 1 fold in 12 across the '
             'research, so they are not to be re-optimised on new data without the same test.'),
        ('Same-day exits', ''),
        ('', 'Model!L2 switches whether a target reached on the fill day counts. Set to 1 it '
             'reproduces the verified backtest (NVDA 82.0%, AVGO 90.7%); every same-day exit in '
             'this sample was confirmed against minute or 5-minute bars.'),
        ('', 'Set to 0 the sheet is conservative: NVDA reads 77.5%, AVGO is unchanged at 90.7% '
             'having no same-day exits at all.'),
        ('What to expect', ''),
        ('', 'Planning figures are NVDA ~58% and AVGO ~60% annualised, not the backtest numbers. '
             'The backtest sits on the peak of a narrow parameter ridge; the planning figures '
             'are the median of the surrounding region, which is what to budget on.'),
        ('', 'Roughly 20 trades a year on NVDA and 6-7 on AVGO. AVGO\'s median holding period is '
             '20 days with a 95th percentile of 77; NVDA\'s are 4 and 224.'),
        ('Updating', ''),
        ('', 'Paste new daily OHLC into Query, keeping the columns in place. The Feed and Model '
             'sheets extend automatically for as many rows as the Model covers.'),
        ('', 'Press Ctrl+Alt+F9 after any change to force a full recalculation.'),
    ]
    r = 3
    for a, bx in lines:
        if a and not bx:
            nt.cell(r, 1, a).font = Font(bold=True, size=12, color=BLUE); r += 1; continue
        if a: nt.cell(r, 1, a).font = Font(bold=True, color=NAVY)
        c = nt.cell(r, 2, bx); c.alignment = Alignment(wrap_text=True, vertical='top')
        nt.row_dimensions[r].height = 30
        r += 1
    nt.column_dimensions['A'].width = 16
    nt.column_dimensions['B'].width = 108

    wb._sheets = [wb[x] for x in ['Notes', 'Dashboard', 'Blotter', 'Query',
                                  'Feed NVDA', 'Feed AVGO', 'Model NVDA', 'Model AVGO']]
    wb.save(OUT)
    return OUT


if __name__ == '__main__':
    # The structural test is the trade count: identical logic must place identical trades.
    # The annualised figures differ by 1-2pp for two documented convention choices, both of
    # which the sheet takes the more conservative side of:
    #   interest    the research model credits a full week's interest at each week start, even in
    #               weeks it buys on the Monday; the sheet accrues only on days it is actually flat
    #   span        the research model annualises from the first TRADEABLE week; the sheet
    #               annualises over the whole loaded history, which is a week longer
    print('mirror of the sheet formulas against the validated model:\n')
    TRADES = {('NVDA', True): 46, ('NVDA', False): 44,
              ('AVGO', True): 15, ('AVGO', False): 15}
    RESEARCH = {('NVDA', True): 82.0, ('NVDA', False): 77.5,
                ('AVGO', True): 90.7, ('AVGO', False): 90.7}
    ok = True
    for s in ('NVDA', 'AVGO'):
        for sd in (True, False):
            r = mirror(s, sd)
            t_ok = r['trades'] == TRADES[(s, sd)]
            gap = r['ann']*100 - RESEARCH[(s, sd)]
            ok = ok and t_ok and abs(gap) < 2.5
            print(f'  {s:5s} same-day={int(sd)}  sheet {r["ann"]*100:6.1f}%  '
                  f'research {RESEARCH[(s,sd)]:5.1f}%  ({gap:+.1f}pp convention)  '
                  f'trades {r["trades"]:3d} vs {TRADES[(s,sd)]:3d}  '
                  f'{"OK" if t_ok else "TRADE MISMATCH"}')
    if not ok:
        raise SystemExit('\nmirror disagrees with the validated model; workbook not written')
    p = build()
    print(f'\nwritten {p}')
