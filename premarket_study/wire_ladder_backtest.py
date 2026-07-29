"""
Reflect the Option-C laddered backtest in the workbook, engine-validated (values).
Non-destructive: single-bid Model formulas kept as reference; adds per-sheet Ladder-C
summary + daily equity track, and a book-wide 'Ladder C Results' sheet.
"""
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from engine import Params, run_model
from ladder_engine import run_ladder
from multi_stock import load_stock, params_for, STOCKS

SRC = '/home/user/David-Fewer/TradingExcel_s1_laddering_OptionC.xlsx'   # has the Dashboard wiring
OUT = '/home/user/David-Fewer/TradingExcel_s1_laddering_OptionC_backtest.xlsx'
pj = json.load(open('params_all.json'))
NAVY = 'FF0B1F3A'; HDR = Font(name='Arial', size=10, bold=True, color='FF0B1F3A')
REG = Font(name='Arial', size=10); ITAL = Font(name='Arial', size=8, italic=True, color='FF5A6270')
THIN = Side(style='thin', color='FFBFBFBF')

wb = openpyxl.load_workbook(SRC, data_only=False)

results = {}
for s in STOCKS:
    dates, O, H, L, C, _ = load_stock(s)
    p = params_for(s, pj); k, b = p.k, p.ou_buf_k
    single = run_model(dates, O, H, L, C, p)
    lad = run_ladder(dates, O, H, L, C, p, [k, 1.3*k, 1.7*k], [b], 'first', [0.8, 0.15, 0.05], None)
    results[s] = (single, lad)

    ws = wb['Model ' + s]
    # per-sheet Ladder C block (free columns; sheet uses A..BF=58)
    ws['BH2'] = 'LADDER C  (Option C — Bayes-only, engine-validated)'; ws['BH2'].font = HDR
    block = [
        ('Annual return', lad['annual'], '0.0%'),
        ('Total trades', lad['trades'], '0'),
        ('  Bayes rung-fills', lad['bayes_trades'], '0'),
        ('  OU buys', lad['ou_trades'], '0'),
        ('Sharpe', lad['sharpe'], '0.00'),
        ('Max drawdown', lad['maxdd'], '0.0%'),
        ('Terminal equity', lad['terminal'], '"$"#,##0'),
        ('Bayes-OU corr', lad['corr'], '0.00'),
        ('vs single-bid ann', lad['annual'] - single.annual_return, '+0.0%;-0.0%'),
    ]
    for i, (lbl, val, fmt) in enumerate(block):
        r = 3 + i
        ws.cell(row=r, column=60, value=lbl).font = REG
        c = ws.cell(row=r, column=61, value=val); c.font = REG; c.number_format = fmt
    ws.cell(row=13, column=60,
            value='Engine-computed values for current data/params (single-bid formulas at left '
                  'remain the validated reference).').font = ITAL
    # daily laddered combined-equity track (values), aligned to data rows 8..
    ws.cell(row=7, column=63, value='Ladder C equity').font = HDR
    for i, e in enumerate(lad['equity']):
        cc = ws.cell(row=8 + i, column=63, value=e); cc.number_format = '"$"#,##0'
    ws.column_dimensions['BH'].width = 20; ws.column_dimensions['BK'].width = 14

# ---- book-wide summary sheet ----
if 'Ladder C Results' in wb.sheetnames:
    del wb['Ladder C Results']
idx = wb.sheetnames.index('Dashboard') + 1
sm = wb.create_sheet('Ladder C Results', idx)
sm['A1'] = 'LADDER C RESULTS — single-bid vs Option-C laddered (engine-validated backtest)'
sm['A1'].font = Font(name='Arial', size=12, bold=True, color='FF0B1F3A')
sm['A2'] = ('Option C = Bayes-only ladder, depths [1.0,1.3,1.7]×kσ, weights [0.80,0.15,0.05], '
            'first-rung take-profit; OU single-bid. Values from the validated Python engine.')
sm['A2'].font = ITAL
hdrs = ['Stock', 'Single ann', 'Single buys', 'Single Sharpe', 'Single DD',
        'Ladder ann', 'Ladder trades', 'Ladder Sharpe', 'Ladder DD', 'Δ ann', 'trades ×', 'Bayes-OU corr']
for j, h in enumerate(hdrs, 1):
    c = sm.cell(row=4, column=j, value=h); c.font = HDR
    c.alignment = Alignment(horizontal='center'); c.border = Border(bottom=THIN)
agg = [0.0]*len(hdrs)
for i, s in enumerate(STOCKS):
    single, lad = results[s]; r = 5 + i
    row = [s, single.annual_return, single.total_buys, single.sharpe, single.max_drawdown,
           lad['annual'], lad['trades'], lad['sharpe'], lad['maxdd'],
           lad['annual']-single.annual_return, lad['trades']/single.total_buys, lad['corr']]
    fmts = [None, '0.0%', '0', '0.00', '0.0%', '0.0%', '0', '0.00', '0.0%', '+0.0%;-0.0%', '0.00"×"', '0.00']
    for j, (v, f) in enumerate(zip(row, fmts), 1):
        c = sm.cell(row=r, column=j, value=v); c.font = REG
        if f: c.number_format = f
        if j > 1: agg[j-1] += v if isinstance(v, (int, float)) else 0
n = len(STOCKS); r = 5 + n
sm.cell(row=r, column=1, value='AVG').font = HDR
avgfmt = {2:'0.0%',3:'0',4:'0.00',5:'0.0%',6:'0.0%',7:'0',8:'0.00',9:'0.0%',10:'+0.0%;-0.0%',11:'0.00"×"',12:'0.00'}
for j in range(2, len(hdrs)+1):
    c = sm.cell(row=r, column=j, value=agg[j-1]/n); c.font = HDR
    c.number_format = avgfmt[j]; c.border = Border(top=THIN)
sm.column_dimensions['A'].width = 8
for col in 'BCDEFGHIJKL':
    sm.column_dimensions[col].width = 12

# note on the Notes sheet
nt = wb['Notes']
nt.cell(row=nt.max_row + 2, column=1,
        value='Ladder C Results tab + per-Model BH:BK blocks show the Option-C laddered backtest '
              '(engine-validated values). Single-bid Model formulas are the validated reference.').font = ITAL

wb.calculation.calcMode = 'auto'; wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print('saved', OUT)
print('Ladder C Results sheet + per-sheet blocks written for', len(STOCKS), 'names')
