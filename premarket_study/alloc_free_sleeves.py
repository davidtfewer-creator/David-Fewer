"""
Make the machine-readable allocation block skip sleeves that are already holding stock.

As it stands, C25:C34 read M11:N15, which are a fixed fifth of capital split 50/50 regardless of
what the book is actually holding. A sleeve that bought yesterday and has not reached its target
still shows a full dollar allocation, so the IBKR script would fund it twice. Seven of the ten
sleeves are holding stock as at 3 August 2026, so this is not a corner case.

The rule implemented is the one asked for: a sleeve holding stock gets nothing, and the capital
is divided across the sleeves that are free. It is written as a weight renormalisation rather
than as "cash divided by the number of free sleeves" so it stays correct if the equal-weighting
is ever relaxed:

    base weight   w_i   = K_stock x Bayes share        (or x (1 - Bayes share) for the OU sleeve)
    free weight   f_i   = w_i x (1 - held_i)
    allocation    $_i   = B5 x f_i / sum(f)

Under the deployed settings -- floor = cap = 0.20, split 50/50 -- every w_i is 0.10 and this
reduces exactly to B5 divided by the number of free sleeves.

Two things are deliberately NOT changed:

  L11:L15, M11:M15, N11:N15 keep their existing static definition. 'Active Trading'!B7:B11 read
  L11:L15 as each stock's Day-1 starting fund and derive P&L and return from it. If that baseline
  moved with the holding state, the blotter's return column would change every morning for no
  reason. The standing capital plan and today's order sizes are different quantities and now sit
  in different places.

  The held flags are read from each Model sheet's carry-forward hold columns, AE for Bayes and AL
  for OU, at row 867 -- the same convention the Dashboard already uses for fair value and ATH.
  They therefore describe the MODEL's position. If a live fill diverged from the model, type over
  D25:D34 directly; they are ordinary inputs.
"""
import shutil
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

SRC = ('/root/.claude/uploads/2d71f10a-e19f-51b2-8457-2cd547c34dff/'
       '3e1130ba-TradingExcel_5stock_live.xlsx')
OUT = '/home/user/David-Fewer/TradingExcel_5stock_live_freesleeves.xlsx'
NAMES = ['TSM', 'VRT', 'VST', 'RKLB', 'MU']

BLUE = PatternFill('solid', fgColor='DCE6F1')
HDR = Font(bold=True, color='0B1F3A')
GREY = Font(italic=True, color='5A6270', size=9)


def build(ws):
    ws['A23'] = ('MACHINE-READABLE OUTPUT  (stock x tranche dollar allocation - read by the IBKR '
                 'script). A sleeve already holding stock is allocated nothing; today\'s cash is '
                 'divided across the sleeves that are free.')
    ws['D24'] = 'Held?'
    ws['E24'] = 'Base wt'
    ws['F24'] = 'Free wt'
    for c in ('D24', 'E24', 'F24'):
        ws[c].font = HDR
        ws[c].alignment = Alignment(horizontal='right')

    for i, s in enumerate(NAMES):
        srow = 11 + i                      # the stock's row in the main table
        for t, tranche in enumerate(('Bayes', 'OU')):
            r = 25 + 2*i + t
            flag = 'AE' if tranche == 'Bayes' else 'AL'
            share = f'$R${srow}' if tranche == 'Bayes' else f'(1-$R${srow})'
            ws.cell(r, 4, f"=IF('Model {s}'!${flag}$867=1,1,0)")
            ws.cell(r, 5, f'=$K${srow}*{share}')
            ws.cell(r, 6, f'=E{r}*(1-D{r})')
            ws.cell(r, 3, f'=IF(SUM($F$25:$F$34)=0,0,$B$5*F{r}/SUM($F$25:$F$34))')
            ws.cell(r, 4).fill = BLUE
            ws.cell(r, 3).number_format = '#,##0.00'
            ws.cell(r, 5).number_format = '0.0000'
            ws.cell(r, 6).number_format = '0.0000'

    ws['A36'] = 'Sleeves free today'
    ws['B36'] = '=COUNT(D25:D34)-SUM(D25:D34)'
    ws['A37'] = '$ per free sleeve (equal weights)'
    ws['B37'] = '=IF(B36=0,0,$B$5/B36)'
    ws['A38'] = 'Check: allocated = cash available'
    ws['B38'] = '=IF(ABS(SUM(C25:C34)-$B$5)<0.01,"OK","MISMATCH")'
    for c in ('A36', 'A37', 'A38'):
        ws[c].font = HDR
    ws['B37'].number_format = '#,##0.00'

    ws['A40'] = ('D25:D34 are read from each Model sheet\'s hold flag (AE for Bayes, AL for OU) '
                 'and describe the MODEL\'s position. Type over them if a live fill diverged.')
    ws['A41'] = ('B5 must be the CASH available this morning, not the total value of the book. '
                 'With seven sleeves holding stock the three free ones take the whole of B5 '
                 'between them, so entering total portfolio value here would commit capital that '
                 'is already invested.')
    for c in ('A40', 'A41'):
        ws[c].font = GREY

    # the input label, so B5 cannot be misread
    ws['A5'] = 'Cash available today ($)'


if __name__ == '__main__':
    shutil.copy(SRC, OUT)
    wb = openpyxl.load_workbook(OUT)
    build(wb['Allocation'])
    n = wb['Notes']
    n['A19'] = 'Free-sleeve allocation'
    n['B19'] = ('Allocation!C25:C34 now skip any sleeve already holding stock and divide the '
                'available cash across the free ones. Previously every sleeve showed a full '
                'fifth-of-capital allocation whatever the book held, so a sleeve that bought '
                'yesterday would have been funded again. Column D carries the held flag, E and F '
                'the base and free weights. L11:L15 are unchanged and still feed the Active '
                'Trading blotter as the Day-1 baseline.')
    wb.save(OUT)
    print('wrote', OUT, flush=True)
    print('DONE', flush=True)
